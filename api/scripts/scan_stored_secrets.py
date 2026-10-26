# api/scripts/scan_stored_secrets.py

"""Read-only scan of a database for plaintext secrets, with the stored-secret guard's detection; prints locations, never values."""

import argparse
import asyncio
import json
import os
import sys
from typing import List, Optional, Sequence

from dotenv import load_dotenv

API_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, API_ROOT)
sys.path.insert(0, os.path.join(API_ROOT, "..", "workers"))

from sqlalchemy import Text, cast, column, select, table, text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

from app.infrastructure.persistence.stored_secret_guard import (  # noqa: E402
    JSON_TEXT_COLUMNS,
    UNCHECKED_JSON_COLUMNS,
    find_plaintext_secrets,
    is_secret_column,
)

JSON_TYPES = ("json", "jsonb")
STRING_TYPES = ("text", "character varying")

COLUMNS = text(
    "SELECT c.table_schema, c.table_name, c.column_name, c.data_type "
    "FROM information_schema.columns c "
    "JOIN information_schema.tables t USING (table_schema, table_name) "
    "WHERE t.table_type = 'BASE TABLE' "
    "AND c.table_schema NOT IN ('pg_catalog', 'information_schema') "
    "AND c.data_type IN ('json', 'jsonb', 'text', 'character varying') "
    "ORDER BY 1, 2, 3"
)


def _scanned(table_name: str, column_name: str, data_type: str) -> bool:
    """Whether the guard has a rule for this column."""
    if data_type in JSON_TYPES:
        return (table_name, column_name) not in UNCHECKED_JSON_COLUMNS
    return (table_name, column_name) in JSON_TEXT_COLUMNS or is_secret_column(column_name)


async def scan_connection(conn: AsyncConnection, schema: Optional[str] = None) -> List[str]:
    """Sorted schema.table.column locations, with JSON paths, of every plaintext secret the connection can read."""
    found = set()
    for schema_name, table_name, column_name, data_type in (await conn.execute(COLUMNS)).all():
        if (schema and schema_name != schema) or not _scanned(table_name, column_name, data_type):
            continue
        col = column(column_name)
        query = select(cast(col, Text)).select_from(table(table_name, col, schema=schema_name)).where(col.isnot(None))
        is_json = data_type in JSON_TYPES
        for (raw,) in await conn.execute(query):
            value = json.loads(raw) if is_json else raw
            found.update(f"{schema_name}.{f}" for f in find_plaintext_secrets(table_name, column_name, value, is_json))
    return sorted(found)


async def scan(url: str) -> List[str]:
    """Findings for the database at url, read in a read-only transaction."""
    engine = create_async_engine(url, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SET TRANSACTION READ ONLY"))
            return await scan_connection(conn)
    finally:
        await engine.dispose()


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Scan the database and return 1 when any plaintext secret is found."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", help="dotenv file to load before reading the database URL")
    parser.add_argument("--url", help="database URL; defaults to SHS_TEST_DATABASE_URL")
    args = parser.parse_args(argv)
    if args.env_file:
        load_dotenv(args.env_file, override=True)
    url = args.url or os.environ.get("SHS_TEST_DATABASE_URL")
    if not url:
        print("No database URL: pass --url or set SHS_TEST_DATABASE_URL.", file=sys.stderr)
        return 2
    findings = asyncio.run(scan(url))
    for finding in findings:
        print(f"plaintext secret: {finding}")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
