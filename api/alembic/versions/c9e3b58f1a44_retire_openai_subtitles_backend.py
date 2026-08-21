# api/alembic/versions/c9e3b58f1a44_retire_openai_subtitles_backend.py

"""retire_openai_subtitles_backend

Revision ID: c9e3b58f1a44
Revises: b7c2e4a91d05
Create Date: 2026-08-18 00:00:00.000000

"""
import json
import logging
from typing import Any, Sequence, Tuple, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c9e3b58f1a44'
down_revision: Union[str, Sequence[str], None] = 'b7c2e4a91d05'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

logger = logging.getLogger("alembic.runtime.migration")

# Authoring surfaces only. step_executions and queued_jobs record what already
# ran; rewriting them would state that a finished job used an engine it did not.
AUTHORING_SURFACES = (
    ("workflow_versions", "steps", ""),
    (
        "instances",
        "workflow_snapshot",
        " AND status NOT IN ('COMPLETED', 'FAILED', 'CANCELLED')",
    ),
)


def retarget(node: Any) -> Tuple[Any, bool]:
    """Return the document with every subtitles_backend openai set to faster."""
    if isinstance(node, dict):
        changed = False
        out = {}
        for key, value in node.items():
            if key == "subtitles_backend" and value == "openai":
                out[key] = "faster"
                changed = True
                continue
            out[key], child_changed = retarget(value)
            changed = changed or child_changed
        return out, changed
    if isinstance(node, list):
        results = [retarget(item) for item in node]
        return [item for item, _ in results], any(c for _, c in results)
    return node, False


def upgrade() -> None:
    """Point stored subtitles_backend values at the engine the image ships."""
    bind = op.get_bind()
    for table, column, condition in AUTHORING_SURFACES:
        rows = bind.execute(
            sa.text(
                f"SELECT id, {column} FROM {table} "
                f"WHERE {column}::text LIKE '%%subtitles_backend%%'{condition}"
            )
        ).fetchall()
        updated = 0
        for row_id, document in rows:
            new_document, changed = retarget(document)
            if not changed:
                continue
            bind.execute(
                sa.text(f"UPDATE {table} SET {column} = :doc WHERE id = :id"),
                {"doc": json.dumps(new_document), "id": row_id},
            )
            updated += 1
        if updated:
            logger.info(
                f"subtitles_backend: rewrote openai to faster in "
                f"{updated} {table}.{column} rows"
            )


def downgrade() -> None:
    raise NotImplementedError('Downgrades are not supported. Redeploy the previous major image.')
