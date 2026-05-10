# api/app/infrastructure/security/oauth_state.py

"""Postgres-backed OAuth CSRF state store. Any API instance can validate callbacks."""

import logging
from datetime import UTC, datetime, timedelta
from typing import Optional

from sqlalchemy import text

from app.infrastructure.persistence.database import db

logger = logging.getLogger(__name__)


async def set_state(key: str, data: str, ttl: int) -> None:
    """Store state with TTL (seconds). Upserts so retried authorize calls don't error."""
    expires_at = datetime.now(UTC) + timedelta(seconds=ttl)
    async with db.get_session_factory()() as session:
        await session.execute(
            text(
                "INSERT INTO oauth_states (key, data, expires_at) "
                "VALUES (:key, :data, :expires_at) "
                "ON CONFLICT (key) DO UPDATE SET data = EXCLUDED.data, expires_at = EXCLUDED.expires_at"
            ),
            {"key": key, "data": data, "expires_at": expires_at},
        )
        # Lazily purge expired rows on every write - cheap at OAuth-flow volume
        await session.execute(text("DELETE FROM oauth_states WHERE expires_at < now()"))
        await session.commit()


async def get_state(key: str) -> Optional[str]:
    """Return state data if the key exists and hasn't expired; None otherwise."""
    async with db.get_session_factory()() as session:
        result = await session.execute(
            text(
                "SELECT data FROM oauth_states "
                "WHERE key = :key AND expires_at > now()"
            ),
            {"key": key},
        )
        row = result.fetchone()
        return row[0] if row else None


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
