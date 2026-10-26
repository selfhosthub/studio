# api/alembic/versions/5b23a9e3e395_encrypt_plaintext_secret_data.py

"""encrypt plaintext secret data

Revision ID: 5b23a9e3e395
Revises: 80722adb034d
Create Date: 2026-10-21 04:41:25.658136

"""
import json
import logging
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Sequence, Tuple, Union

from alembic import op
import sqlalchemy as sa

if TYPE_CHECKING:
    from app.infrastructure.security.credential_encryption import CredentialEncryption


# revision identifiers, used by Alembic.
revision: str = '5b23a9e3e395'
down_revision: Union[str, Sequence[str], None] = '80722adb034d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

logger = logging.getLogger("alembic.runtime.migration")

TABLES = ("organization_secrets", "provider_credentials")
SEALED_MARKER = "_sealed"

Data = Dict[str, Any]


def is_unsealed(data: Any) -> bool:
    """Whether secret_data holds plaintext or per-key ciphertext instead of one sealed ciphertext."""
    return isinstance(data, dict) and bool(data) and SEALED_MARKER not in data


def is_sealed(data: Any) -> bool:
    """Whether secret_data is one sealed ciphertext."""
    return isinstance(data, dict) and SEALED_MARKER in data


def convert(
    bind: Any,
    key: Optional[str],
    select: Callable[[Any], bool],
    transform: Callable[["CredentialEncryption", Data], Optional[Data]],
) -> int:
    """Rewrite secret_data of every selected row in TABLES with transform; returns rows updated."""
    pending: List[Tuple[str, Any, Data]] = []
    # Opens the forced row level security on both tables to every org's rows.
    bind.execute(sa.text("SELECT set_config('app.is_service_account', 'true', true)"))
    for table in TABLES:
        rows = bind.execute(sa.text(f"SELECT id, secret_data FROM {table}")).fetchall()
        pending.extend((table, row_id, data) for row_id, data in rows if select(data))
    if not pending:
        return 0
    if not key:
        raise RuntimeError(
            f"{len(pending)} secret_data rows need converting and SHS_CREDENTIAL_ENCRYPTION_KEY is not set"
        )
    from app.infrastructure.security.credential_encryption import CredentialEncryption

    encryption = CredentialEncryption(key)
    for table, row_id, data in pending:
        bind.execute(
            sa.text(f"UPDATE {table} SET secret_data = CAST(:data AS json) WHERE id = :id"),
            {"data": json.dumps(transform(encryption, data)), "id": row_id},
        )
    return len(pending)


def seal_rows(bind: Any, key: Optional[str]) -> int:
    """Seal every plaintext or per-key encrypted secret_data row as one ciphertext; returns rows updated."""
    return convert(bind, key, is_unsealed, lambda enc, data: enc.seal_secret_data(enc.open_secret_data(data)))


def open_rows(bind: Any, key: Optional[str]) -> int:
    """Open every sealed secret_data row back to plaintext; returns rows updated."""
    return convert(bind, key, is_sealed, lambda enc, data: enc.open_secret_data(data))


def _key() -> Optional[str]:
    """The configured credential encryption key."""
    from app.config.settings import settings

    return settings.CREDENTIAL_ENCRYPTION_KEY


def upgrade() -> None:
    """Seal organization_secrets and provider_credentials secret_data as one ciphertext per row."""
    updated = seal_rows(op.get_bind(), _key())
    if updated:
        logger.info(f"secret_data: sealed {updated} rows")


def downgrade() -> None:
    raise NotImplementedError('Downgrades are not supported. Redeploy the previous major image.')
