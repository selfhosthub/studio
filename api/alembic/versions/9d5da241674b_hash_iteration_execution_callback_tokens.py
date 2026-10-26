# api/alembic/versions/9d5da241674b_hash_iteration_execution_callback_tokens.py

"""hash iteration execution callback tokens

Revision ID: 9d5da241674b
Revises: 78ea318eae92
Create Date: 2026-10-21 04:50:58.373329

"""
import hashlib
import logging
from typing import Any, Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9d5da241674b'
down_revision: Union[str, Sequence[str], None] = '78ea318eae92'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

logger = logging.getLogger("alembic.runtime.migration")

TOKEN_ROWS = sa.text(
    "SELECT ie.id, ie.external_id FROM iteration_executions ie "
    "JOIN step_executions se ON se.id = ie.step_id "
    "JOIN instances i ON i.id = se.instance_id "
    "WHERE ie.external_id IS NOT NULL AND ie.external_id !~ '^[0-9a-f]{64}$' "
    "AND (i.workflow_snapshot -> 'steps' -> se.step_key -> 'job' ->> 'service_id') IN ("
    "SELECT ps.service_id FROM provider_services ps "
    "WHERE CAST(ps.client_metadata AS JSONB) -> 'webhook_completion' ->> 'routing' = 'execution_token')"
)


def hash_rows(bind: Any) -> int:
    """Replace each execution-token row's plaintext callback token with its SHA-256 hash; returns rows updated."""
    rows = bind.execute(TOKEN_ROWS).fetchall()
    for row_id, token in rows:
        bind.execute(
            sa.text("UPDATE iteration_executions SET external_id = :token_hash WHERE id = :id"),
            {"token_hash": hashlib.sha256(token.encode("utf-8")).hexdigest(), "id": row_id},
        )
    return len(rows)


def upgrade() -> None:
    """Store each execution-token iteration row's callback token as its SHA-256 lookup hash."""
    updated = hash_rows(op.get_bind())
    if updated:
        logger.info(f"iteration_executions.external_id: hashed {updated} callback tokens")


def downgrade() -> None:
    raise NotImplementedError('Downgrades are not supported. Redeploy the previous major image.')
