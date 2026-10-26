# api/alembic/versions/6981f74a54cb_hash_and_encrypt_workflow_webhook_token.py

"""hash and encrypt workflow webhook token

Revision ID: 6981f74a54cb
Revises: 4b3cd48277d7
Create Date: 2026-10-21 04:41:04.999310

"""
import hashlib
import logging
from typing import Any, Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6981f74a54cb'
down_revision: Union[str, Sequence[str], None] = '4b3cd48277d7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

logger = logging.getLogger("alembic.runtime.migration")

TABLE = "workflows"
COLUMN = "webhook_token"
HASH_COLUMN = "webhook_token_hash"


def _encryption() -> Any:
    """CredentialEncryption built from the configured key."""
    from app.config.settings import settings
    from app.infrastructure.security.credential_encryption import CredentialEncryption

    return CredentialEncryption(settings.CREDENTIAL_ENCRYPTION_KEY)


def seal_rows(bind: Any) -> int:
    """Encrypt each plaintext token and store its SHA-256 lookup hash; returns rows updated."""
    rows = bind.execute(
        sa.text(f"SELECT id, {COLUMN} FROM {TABLE} WHERE {HASH_COLUMN} IS NULL AND {COLUMN} IS NOT NULL AND {COLUMN} <> ''")
    ).fetchall()
    if not rows:
        return 0
    encryption = _encryption()
    for row_id, token in rows:
        bind.execute(
            sa.text(f"UPDATE {TABLE} SET {COLUMN} = :sealed, {HASH_COLUMN} = :token_hash WHERE id = :id"),
            {"sealed": encryption.encrypt(token), "token_hash": hashlib.sha256(token.encode("utf-8")).hexdigest(), "id": row_id},
        )
    return len(rows)


def open_rows(bind: Any) -> int:
    """Decrypt each sealed token and clear its lookup hash; returns rows updated."""
    rows = bind.execute(sa.text(f"SELECT id, {COLUMN} FROM {TABLE} WHERE {HASH_COLUMN} IS NOT NULL")).fetchall()
    if not rows:
        return 0
    encryption = _encryption()
    for row_id, sealed in rows:
        bind.execute(
            sa.text(f"UPDATE {TABLE} SET {COLUMN} = :token, {HASH_COLUMN} = NULL WHERE id = :id"),
            {"token": encryption.decrypt(sealed), "id": row_id},
        )
    return len(rows)


def upgrade() -> None:
    """Store each workflow webhook token encrypted beside a unique SHA-256 lookup hash."""
    op.add_column(TABLE, sa.Column(HASH_COLUMN, sa.String(length=64), nullable=True))
    op.drop_index(op.f(f"ix_{TABLE}_{COLUMN}"), table_name=TABLE)
    op.alter_column(TABLE, COLUMN, type_=sa.Text(), existing_type=sa.String(length=64), existing_nullable=True)
    updated = seal_rows(op.get_bind())
    if updated:
        logger.info(f"{TABLE}.{COLUMN}: encrypted {updated} rows")
    op.create_index(op.f(f"ix_{TABLE}_{HASH_COLUMN}"), TABLE, [HASH_COLUMN], unique=True)


def downgrade() -> None:
    raise NotImplementedError('Downgrades are not supported. Redeploy the previous major image.')
