# api/alembic/versions/1a86d7a45ebf_encrypt_step_webhook_secrets.py

"""encrypt step webhook secrets

Revision ID: 1a86d7a45ebf
Revises: 4dae3f602a9f
Create Date: 2026-10-21 04:23:05.143693

"""
import hashlib
import json
import logging
from typing import TYPE_CHECKING, Any, Callable, Dict, Optional, Sequence, Tuple, Union

from alembic import op
import sqlalchemy as sa

if TYPE_CHECKING:
    from app.infrastructure.security.credential_encryption import CredentialEncryption


# revision identifiers, used by Alembic.
revision: str = '1a86d7a45ebf'
down_revision: Union[str, Sequence[str], None] = '4dae3f602a9f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

logger = logging.getLogger("alembic.runtime.migration")

TOKEN = "webhook_token"
SECRET = "webhook_secret"
TOKEN_HASH = "webhook_token_hash"
PARAMETER_SECRETS = ("webhook_auth_header_value", "webhook_jwt_secret")

Meta = Dict[str, Any]


def _filled(meta: Meta, key: str) -> bool:
    """Whether meta holds a non-empty string under key."""
    value = meta.get(key)
    return isinstance(value, str) and bool(value)


def seal(meta: Meta, encryption: "CredentialEncryption") -> Optional[Meta]:
    """Plaintext webhook metadata encrypted with the token hash added, or None when already sealed or empty."""
    if TOKEN_HASH in meta or not (_filled(meta, TOKEN) or _filled(meta, SECRET)):
        return None
    sealed = dict(meta)
    for key in (TOKEN, SECRET):
        if _filled(meta, key):
            sealed[key] = encryption.encrypt(meta[key])
    if _filled(meta, TOKEN):
        sealed[TOKEN_HASH] = hashlib.sha256(meta[TOKEN].encode("utf-8")).hexdigest()
    return sealed


def unseal(meta: Meta, encryption: "CredentialEncryption") -> Optional[Meta]:
    """Sealed webhook metadata decrypted with the token hash removed, or None when not sealed."""
    if TOKEN_HASH not in meta:
        return None
    opened = {k: v for k, v in meta.items() if k != TOKEN_HASH}
    for key in (TOKEN, SECRET):
        if _filled(opened, key):
            opened[key] = encryption.decrypt(opened[key])
    return opened


def _is_ciphertext(value: str, encryption: "CredentialEncryption") -> bool:
    """Whether value decrypts under the configured key."""
    try:
        encryption.decrypt(value)
        return True
    except ValueError:
        return False


def seal_params(params: Meta, encryption: "CredentialEncryption") -> Optional[Meta]:
    """Node auth values encrypted, or None when every one is already ciphertext or empty."""
    pending = [k for k in PARAMETER_SECRETS if _filled(params, k) and not _is_ciphertext(params[k], encryption)]
    if not pending:
        return None
    return {**params, **{k: encryption.encrypt(params[k]) for k in pending}}


def unseal_params(params: Meta, encryption: "CredentialEncryption") -> Optional[Meta]:
    """Node auth values decrypted, or None when none is ciphertext."""
    pending = [k for k in PARAMETER_SECRETS if _filled(params, k) and _is_ciphertext(params[k], encryption)]
    if not pending:
        return None
    return {**params, **{k: encryption.decrypt(params[k]) for k in pending}}


Transform = Callable[[Meta, "CredentialEncryption"], Optional[Meta]]


def rewrite_steps(
    steps: Any,
    meta_fn: Callable[[Meta], Optional[Meta]],
    params_fn: Callable[[Meta], Optional[Meta]],
) -> Tuple[Any, bool]:
    """Steps with meta_fn applied to each client_metadata and params_fn to each job.parameters, and whether any changed."""
    if not isinstance(steps, dict):
        return steps, False
    changed = False
    out: Dict[str, Any] = {}
    for step_id, step in steps.items():
        if isinstance(step, dict):
            meta = step.get("client_metadata")
            new_meta = meta_fn(meta) if isinstance(meta, dict) else None
            if new_meta is not None:
                step = {**step, "client_metadata": new_meta}
                changed = True
            job = step.get("job")
            params = job.get("parameters") if isinstance(job, dict) else None
            new_params = params_fn(params) if isinstance(params, dict) else None
            if new_params is not None:
                step = {**step, "job": {**job, "parameters": new_params}}
                changed = True
        out[step_id] = step
    return out, changed


def rewrite(bind: Any, meta_fn: Transform, params_fn: Transform) -> int:
    """Apply meta_fn and params_fn to every workflow_versions row holding a node webhook secret; returns rows updated."""
    rows = bind.execute(
        sa.text(
            "SELECT id, steps FROM workflow_versions "
            "WHERE steps::text LIKE '%\"webhook_token\"%' "
            "OR steps::text LIKE '%\"webhook_secret\"%' "
            "OR steps::text LIKE '%\"webhook_auth_header_value\"%' "
            "OR steps::text LIKE '%\"webhook_jwt_secret\"%'"
        )
    ).fetchall()
    if not rows:
        return 0
    from app.config.settings import settings
    from app.infrastructure.security.credential_encryption import CredentialEncryption

    encryption = CredentialEncryption(settings.CREDENTIAL_ENCRYPTION_KEY)
    updated = 0
    for row_id, steps in rows:
        new_steps, changed = rewrite_steps(
            steps,
            lambda m: meta_fn(m, encryption),
            lambda p: params_fn(p, encryption),
        )
        if not changed:
            continue
        bind.execute(
            sa.text("UPDATE workflow_versions SET steps = CAST(:steps AS jsonb) WHERE id = :id"),
            {"steps": json.dumps(new_steps), "id": row_id},
        )
        updated += 1
    return updated


def upgrade() -> None:
    """Encrypt each node's webhook token, secret and auth values and store the token's lookup hash."""
    updated = rewrite(op.get_bind(), seal, seal_params)
    if updated:
        logger.info(f"step webhook secrets: encrypted {updated} workflow_versions rows")


def downgrade() -> None:
    raise NotImplementedError('Downgrades are not supported. Redeploy the previous major image.')
