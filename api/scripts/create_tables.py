# api/scripts/create_tables.py
"""
RLS policy application + pgvector extension.

Schema management has moved to Alembic (see api/alembic/). This module is
retained for the post-migration RLS apply step, which is idempotent and
runs on every boot from bootstrap.py.

The legacy `create_tables()` function is kept for tests and emergency recovery
paths only - production schema lifecycle is `alembic upgrade head`.
"""

import asyncio
import os
import pathlib
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy.ext.asyncio import create_async_engine
from app.infrastructure.persistence.database import DATABASE_URL


async def apply_rls() -> bool:
    """Apply RLS policy + enforcement SQL. Both files are idempotent."""
    engine = create_async_engine(DATABASE_URL, echo=False)
    try:
        async with engine.connect() as conn:
            raw_conn = await conn.get_raw_connection()
            driver_conn = raw_conn.driver_connection
            assert driver_conn is not None, "No driver connection available"
            await driver_conn.execute("CREATE EXTENSION IF NOT EXISTS vector;")

        migrations_dir = pathlib.Path(__file__).resolve().parent / "migrations"
        for sql_file in ["add_rls_policies.sql", "add_rls_enforcement.sql"]:
            sql_path = migrations_dir / sql_file
            if not sql_path.exists():
                print(f"⚠️  RLS migration not found: {sql_path}")
                continue

            print(f"Applying {sql_file}...")
            async with engine.connect() as conn:
                raw_conn = await conn.get_raw_connection()
                driver_conn = raw_conn.driver_connection
                assert driver_conn is not None, "No driver connection available"
                await driver_conn.execute(sql_path.read_text())
            print(f"✅ {sql_file} applied")

        return True
    except Exception as e:
        print(f"❌ Error applying RLS: {e}")
        return False
    finally:
        await engine.dispose()


async def create_tables() -> bool:
    """Legacy: create tables from models, enable pgvector, apply RLS.

    Production uses `alembic upgrade head` instead. This is retained for
    test fixtures and emergency recovery only.
    """
    from app.infrastructure.persistence.models import Base

    display_url = DATABASE_URL
    if "@" in display_url:
        parts = display_url.split("@")
        display_url = f"postgresql+asyncpg://***@{parts[1]}"

    print(f"Creating tables in database: {display_url.split('/')[-1]}")
    engine = create_async_engine(DATABASE_URL, echo=False)

    try:
        print("Enabling pgvector extension...")
        async with engine.connect() as conn:
            raw_conn = await conn.get_raw_connection()
            driver_conn = raw_conn.driver_connection
            assert driver_conn is not None, "No driver connection available"
            await driver_conn.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        print("✅ pgvector extension enabled")

        print("Creating all tables...")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        print("✅ Tables created successfully!")
    except Exception as e:
        print(f"❌ Error creating tables: {e}")
        await engine.dispose()
        return False

    await engine.dispose()
    return await apply_rls()


if __name__ == "__main__":
    success = asyncio.run(create_tables())
    sys.exit(0 if success else 1)
