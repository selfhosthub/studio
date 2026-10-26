# api/alembic/versions/9b8f40cf5558_encrypt_oauth_state_code_verifier.py

"""encrypt oauth state code verifier

Revision ID: 9b8f40cf5558
Revises: 35979a8bd84b
Create Date: 2026-10-21 15:12:44.355978

"""
import logging
from typing import Any, Dict, Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9b8f40cf5558'
down_revision: Union[str, Sequence[str], None] = '35979a8bd84b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

logger = logging.getLogger("alembic.runtime.migration")


def seal_all(bind: Any) -> Dict[str, int]:
    """Drop expired and unreadable OAuth states and encrypt the secret values of the rest; returns rows per action."""
    from app.infrastructure.security.oauth_state import seal_state

    counts = {"deleted": 0, "sealed": 0}
    counts["deleted"] += bind.execute(sa.text("DELETE FROM oauth_states WHERE expires_at <= now()")).rowcount
    for key, data in bind.execute(sa.text("SELECT key, data FROM oauth_states")).fetchall():
        try:
            sealed = seal_state(data)
        except ValueError:
            bind.execute(sa.text("DELETE FROM oauth_states WHERE key = :k"), {"k": key})
            counts["deleted"] += 1
            continue
        if sealed != data:
            bind.execute(sa.text("UPDATE oauth_states SET data = :d WHERE key = :k"), {"d": sealed, "k": key})
            counts["sealed"] += 1
    return counts


def upgrade() -> None:
    """Encrypt the PKCE code verifier held in live OAuth states and drop expired ones."""
    counts = seal_all(op.get_bind())
    logger.info(f"oauth states sealed: {counts}")


def downgrade() -> None:
    raise NotImplementedError('Downgrades are not supported. Redeploy the previous major image.')
