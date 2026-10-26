# api/alembic/versions/78ea318eae92_redact_secret_trigger_headers_on_.py

"""redact secret trigger headers on instances

Revision ID: 78ea318eae92
Revises: 5b23a9e3e395
Create Date: 2026-10-21 04:50:55.856337

"""
import json
import logging
from typing import Any, Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '78ea318eae92'
down_revision: Union[str, Sequence[str], None] = '5b23a9e3e395'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

logger = logging.getLogger("alembic.runtime.migration")


def redact_rows(bind: Any) -> int:
    """Redact secret header values kept on trigger-started instances; returns rows updated."""
    from app.infrastructure.security.trigger_headers import redact_trigger_headers

    rows = bind.execute(
        sa.text(
            "SELECT i.id, i.client_metadata, w.webhook_auth_header_name, w.webhook_config "
            "FROM instances i JOIN workflows w ON w.id = i.workflow_id "
            "WHERE jsonb_typeof(i.client_metadata -> 'headers') = 'object'"
        )
    ).fetchall()
    updated = 0
    for row_id, metadata, header_name, webhook_config in rows:
        headers = metadata["headers"]
        redacted = redact_trigger_headers(headers, header_name, webhook_config)
        if redacted == headers:
            continue
        bind.execute(
            sa.text("UPDATE instances SET client_metadata = CAST(:meta AS JSONB) WHERE id = :id"),
            {"meta": json.dumps({**metadata, "headers": redacted}), "id": row_id},
        )
        updated += 1
    return updated


def upgrade() -> None:
    """Redact auth, signature, cookie and secret-class header values on stored trigger instances."""
    updated = redact_rows(op.get_bind())
    if updated:
        logger.info(f"instances.client_metadata.headers: redacted {updated} rows")


def downgrade() -> None:
    raise NotImplementedError('Downgrades are not supported. Redeploy the previous major image.')
