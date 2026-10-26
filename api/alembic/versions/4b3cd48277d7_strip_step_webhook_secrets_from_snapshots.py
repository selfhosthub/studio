# api/alembic/versions/4b3cd48277d7_strip_step_webhook_secrets_from_snapshots.py

"""strip step webhook secrets from snapshots

Revision ID: 4b3cd48277d7
Revises: 1a86d7a45ebf
Create Date: 2026-10-21 04:33:32.750678

"""
import json
import logging
from typing import Any, Dict, Sequence, Tuple, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4b3cd48277d7'
down_revision: Union[str, Sequence[str], None] = '1a86d7a45ebf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

logger = logging.getLogger("alembic.runtime.migration")

META_KEYS = ("webhook_token", "webhook_secret", "webhook_token_hash")
PARAMETER_KEYS = ("webhook_auth_header_value", "webhook_jwt_secret")


def strip_snapshot(snapshot: Any) -> Tuple[Any, bool]:
    """Snapshot with node webhook secrets removed from every step, and whether any were removed."""
    steps = snapshot.get("steps") if isinstance(snapshot, dict) else None
    if not isinstance(steps, dict):
        return snapshot, False
    changed = False
    out: Dict[str, Any] = {}
    for step_id, step in steps.items():
        if isinstance(step, dict):
            meta = step.get("client_metadata")
            if isinstance(meta, dict) and any(k in meta for k in META_KEYS):
                step = {**step, "client_metadata": {k: v for k, v in meta.items() if k not in META_KEYS}}
                changed = True
            job = step.get("job")
            if isinstance(job, dict):
                params = job.get("parameters")
                if isinstance(params, dict) and any(k in params for k in PARAMETER_KEYS):
                    kept = {k: v for k, v in params.items() if k not in PARAMETER_KEYS}
                    step = {**step, "job": {**job, "parameters": kept}}
                    changed = True
        out[step_id] = step
    return {**snapshot, "steps": out}, changed


def strip(bind: Any) -> int:
    """Remove node webhook secrets from every instance snapshot holding one; returns rows updated."""
    rows = bind.execute(
        sa.text(
            "SELECT id, workflow_snapshot FROM instances "
            "WHERE workflow_snapshot::text LIKE '%\"webhook_token\"%' "
            "OR workflow_snapshot::text LIKE '%\"webhook_secret\"%' "
            "OR workflow_snapshot::text LIKE '%\"webhook_token_hash\"%' "
            "OR workflow_snapshot::text LIKE '%\"webhook_auth_header_value\"%' "
            "OR workflow_snapshot::text LIKE '%\"webhook_jwt_secret\"%'"
        )
    ).fetchall()
    updated = 0
    for row_id, snapshot in rows:
        new_snapshot, changed = strip_snapshot(snapshot)
        if not changed:
            continue
        bind.execute(
            sa.text("UPDATE instances SET workflow_snapshot = CAST(:snap AS jsonb) WHERE id = :id"),
            {"snap": json.dumps(new_snapshot), "id": row_id},
        )
        updated += 1
    return updated


def upgrade() -> None:
    """Strip node webhook tokens, secrets and auth values from stored run snapshots."""
    updated = strip(op.get_bind())
    if updated:
        logger.info(f"step webhook secrets: stripped {updated} instance snapshots")


def downgrade() -> None:
    raise NotImplementedError('Downgrades are not supported. Redeploy the previous major image.')
