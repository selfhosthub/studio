# api/app/infrastructure/security/oauth_state.py

"""Postgres-backed OAuth CSRF state store. Any API instance can validate callbacks."""

import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Optional

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert

from app.infrastructure.persistence.database import db
from app.infrastructure.persistence.models import OAuthStateModel
from app.infrastructure.persistence.stored_secret_guard import is_ciphertext, named_secret_paths
from app.infrastructure.security.credential_encryption import get_credential_encryption

logger = logging.getLogger(__name__)


def seal_state(data: str) -> str:
    """State JSON with each top-level value the stored-secret guard names secret encrypted."""
    state = json.loads(data)
    if not isinstance(state, dict):
        return data
    secret = {path[0] for path in named_secret_paths(state) if len(path) == 1}
    encrypt = get_credential_encryption().encrypt
    return json.dumps({k: encrypt(v) if k in secret else v for k, v in state.items()})


def open_state(data: str) -> str:
    """State JSON with every encrypted top-level value decrypted; text that is not a JSON object as is."""
    try:
        state = json.loads(data)
    except ValueError:
        return data
    if not isinstance(state, dict):
        return data
    decrypt = get_credential_encryption().decrypt
    return json.dumps(
        {k: decrypt(v) if isinstance(v, str) and is_ciphertext(v) else v for k, v in state.items()}
    )


async def set_state(key: str, data: str, ttl: int) -> None:
    """Store state JSON, its secret values encrypted, with TTL (seconds). Upserts so retried authorize calls don't error."""
    expires_at = datetime.now(UTC) + timedelta(seconds=ttl)
    statement = insert(OAuthStateModel).values(key=key, data=seal_state(data), expires_at=expires_at)
    statement = statement.on_conflict_do_update(
        index_elements=[OAuthStateModel.key],
        set_={"data": statement.excluded.data, "expires_at": statement.excluded.expires_at},
    )
    async with db.get_session_factory()() as session:
        await session.execute(statement)
        # Lazily purge expired rows on every write - cheap at OAuth-flow volume
        await session.execute(text("DELETE FROM oauth_states WHERE expires_at < now()"))
        await session.commit()


async def get_state(key: str) -> Optional[str]:
    """Return state data, secret values decrypted, if the key exists, hasn't expired and opens; None otherwise."""
    async with db.get_session_factory()() as session:
        result = await session.execute(
            text(
                "SELECT data FROM oauth_states "
                "WHERE key = :key AND expires_at > now()"
            ),
            {"key": key},
        )
        row = result.fetchone()
    if not row:
        return None
    try:
        return open_state(row[0])
    except ValueError:
        logger.warning("OAuth state could not be decrypted")
        return None


async def delete_state(key: str) -> None:
    """Delete a state entry (called after single-use validation)."""
    async with db.get_session_factory()() as session:
        await session.execute(
            text("DELETE FROM oauth_states WHERE key = :key"),
            {"key": key},
        )
        await session.commit()


# No-op stubs kept for callers that haven't been updated yet.
# main.py lifespan still calls these; they're removed in the lifespan cleanup pass.
async def start_cleanup_task(interval: int = 60) -> None:
    pass


async def stop_cleanup_task() -> None:
    pass
