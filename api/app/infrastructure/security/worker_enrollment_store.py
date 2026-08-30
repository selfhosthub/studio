# api/app/infrastructure/security/worker_enrollment_store.py

"""Postgres-backed storage for worker join tokens and enrollment credentials.

Every read that also marks a row (consume, touch) is a single UPDATE ...
RETURNING, so two workers presenting the same token cannot both win.
"""

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from app.infrastructure.persistence.database import db
from app.infrastructure.security.worker_enrollment import (
    hash_secret,
    mint_credential,
    mint_join_token,
)

logger = logging.getLogger(__name__)


async def create_join_token(
    label: str,
    queues: List[str],
    ttl_seconds: int,
    created_by: Optional[uuid.UUID],
) -> Dict[str, Any]:
    """Mint a join token. The plaintext is returned here and never stored."""
    token = mint_join_token()
    expires_at = datetime.now(UTC) + timedelta(seconds=ttl_seconds)
    async with db.get_session_factory()() as session:
        result = await session.execute(
            text(
                "INSERT INTO worker_join_tokens "
                "(id, token_hash, label, queues, created_by, expires_at, created_at) "
                "VALUES (:id, :h, :label, :queues, :by, :exp, now()) "
                "RETURNING id, expires_at"
            ),
            {
                "id": uuid.uuid4(),
                "h": hash_secret(token),
                "label": label,
                "queues": queues,
                "by": created_by,
                "exp": expires_at,
            },
        )
        row = result.one()
        # Expired tokens have no value and no audit meaning; drop them on write.
        await session.execute(
            text("DELETE FROM worker_join_tokens WHERE expires_at < now() AND used_at IS NULL")
        )
        await session.commit()
    return {"id": row[0], "token": token, "expires_at": row[1]}


async def consume_join_token(token: str) -> Optional[Dict[str, Any]]:
    """Claim an unused, unexpired token. Returns its id and queue scope, or None."""
    async with db.get_session_factory()() as session:
        result = await session.execute(
            text(
                "UPDATE worker_join_tokens SET used_at = now() "
                "WHERE token_hash = :h AND used_at IS NULL AND expires_at > now() "
                "RETURNING id, label, queues"
            ),
            {"h": hash_secret(token)},
        )
        row = result.fetchone()
        await session.commit()
    if not row:
        return None
    return {"id": row[0], "label": row[1], "queues": list(row[2] or [])}


async def list_join_tokens() -> List[Dict[str, Any]]:
    """Outstanding tokens. The plaintext is unrecoverable, so it is never listed."""
    async with db.get_session_factory()() as session:
        result = await session.execute(
            text(
                "SELECT id, label, queues, expires_at, used_at, created_at "
                "FROM worker_join_tokens ORDER BY created_at DESC"
            )
        )
        return [
            {
                "id": r[0],
                "label": r[1],
                "queues": list(r[2] or []),
                "expires_at": r[3],
                "used_at": r[4],
                "created_at": r[5],
            }
            for r in result.fetchall()
        ]


async def create_enrollment(
    label: str, queues: List[str], join_token_id: Optional[uuid.UUID]
) -> Dict[str, Any]:
    """Issue the per-worker credential. The plaintext is returned here only."""
    credential = mint_credential()
    async with db.get_session_factory()() as session:
        result = await session.execute(
            text(
                "INSERT INTO worker_enrollments "
                "(id, credential_hash, label, queues, join_token_id, created_at) "
                "VALUES (:id, :h, :label, :queues, :jt, now()) "
                "RETURNING id"
            ),
            {
                "id": uuid.uuid4(),
                "h": hash_secret(credential),
                "label": label,
                "queues": queues,
                "jt": join_token_id,
            },
        )
        row = result.one()
        await session.commit()
    return {"id": row[0], "credential": credential}


async def resolve_enrollment(credential: str) -> Optional[Dict[str, Any]]:
    """Resolve a live credential to its queue scope.

    Read-only on purpose: this runs on the claim path, which every worker polls
    continuously, so it must not write a row per poll. Registration calls
    touch_enrollment separately.
    """
    async with db.get_session_factory()() as session:
        result = await session.execute(
            text(
                "SELECT id, label, queues FROM worker_enrollments "
                "WHERE credential_hash = :h AND revoked_at IS NULL"
            ),
            {"h": hash_secret(credential)},
        )
        row = result.fetchone()
    if not row:
        return None
    return {"id": row[0], "label": row[1], "queues": list(row[2] or [])}


async def touch_enrollment(enrollment_id: uuid.UUID) -> None:
    """Record that a credential was used. Called on registration, not on claim."""
    async with db.get_session_factory()() as session:
        await session.execute(
            text("UPDATE worker_enrollments SET last_used_at = now() WHERE id = :id"),
            {"id": enrollment_id},
        )
        await session.commit()


async def list_enrollments() -> List[Dict[str, Any]]:
    async with db.get_session_factory()() as session:
        result = await session.execute(
            text(
                "SELECT id, label, queues, revoked_at, last_used_at, created_at "
                "FROM worker_enrollments ORDER BY created_at DESC"
            )
        )
        return [
            {
                "id": r[0],
                "label": r[1],
                "queues": list(r[2] or []),
                "revoked_at": r[3],
                "last_used_at": r[4],
                "created_at": r[5],
            }
            for r in result.fetchall()
        ]


async def revoke_enrollment(enrollment_id: uuid.UUID) -> bool:
    """Revoke a credential. Returns False if it does not exist or was already revoked."""
    async with db.get_session_factory()() as session:
        result = await session.execute(
            text(
                "UPDATE worker_enrollments SET revoked_at = now() "
                "WHERE id = :id AND revoked_at IS NULL RETURNING id"
            ),
            {"id": enrollment_id},
        )
        row = result.fetchone()
        await session.commit()
    return row is not None
