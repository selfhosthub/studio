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
    mint_poll_token,
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


async def _insert_enrollment(
    session: Any, label: str, queues: List[str], join_token_id: Optional[uuid.UUID]
) -> Dict[str, Any]:
    """Insert a credential row on an open session; the plaintext is returned only."""
    credential = mint_credential()
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
    return {"id": result.one()[0], "credential": credential}


async def create_enrollment(
    label: str, queues: List[str], join_token_id: Optional[uuid.UUID]
) -> Dict[str, Any]:
    """Issue the per-worker credential. The plaintext is returned here only."""
    async with db.get_session_factory()() as session:
        created = await _insert_enrollment(session, label, queues, join_token_id)
        await session.commit()
    return created


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


async def enrollment_is_live(enrollment_id: uuid.UUID) -> bool:
    """True while the enrollment exists and is not revoked."""
    async with db.get_session_factory()() as session:
        result = await session.execute(
            text(
                "SELECT 1 FROM worker_enrollments "
                "WHERE id = :id AND revoked_at IS NULL"
            ),
            {"id": enrollment_id},
        )
        return result.fetchone() is not None


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
    """Revoke a credential and deregister its workers. Returns False if it does not exist or was already revoked."""
    async with db.get_session_factory()() as session:
        result = await session.execute(
            text(
                "UPDATE worker_enrollments SET revoked_at = now() "
                "WHERE id = :id AND revoked_at IS NULL RETURNING id"
            ),
            {"id": enrollment_id},
        )
        row = result.fetchone()
        if row is not None:
            await session.execute(
                text(
                    "UPDATE workers SET is_deregistered = true, updated_at = now() "
                    "WHERE enrollment_id = :id"
                ),
                {"id": enrollment_id},
            )
        await session.commit()
    return row is not None


# Pending requests beyond this are refused, so a leaked secret cannot flood the list.
MAX_PENDING_REQUESTS = 100

# Requests older than this are dropped on the next write, whatever their status.
REQUEST_RETENTION = timedelta(days=7)

_REQUEST_COLUMNS = (
    "id, name, hostname, ip_address, queues, status, enrollment_id, "
    "decided_by, decided_at, created_at"
)


def _request_row(r: Any) -> Dict[str, Any]:
    return {
        "id": r[0],
        "name": r[1],
        "hostname": r[2],
        "ip_address": r[3],
        "queues": list(r[4] or []),
        "status": r[5],
        "enrollment_id": r[6],
        "decided_by": r[7],
        "decided_at": r[8],
        "created_at": r[9],
    }


async def create_enrollment_request(
    name: str,
    hostname: Optional[str],
    ip_address: Optional[str],
    queues: List[str],
) -> Optional[Dict[str, Any]]:
    """File a pending request; returns its id and poll token, or None when the pending list is full."""
    poll_token = mint_poll_token()
    async with db.get_session_factory()() as session:
        await session.execute(
            text("DELETE FROM worker_enrollment_requests WHERE created_at < :cutoff"),
            {"cutoff": datetime.now(UTC) - REQUEST_RETENTION},
        )
        pending = (
            await session.execute(
                text(
                    "SELECT count(*) FROM worker_enrollment_requests "
                    "WHERE status = 'pending'"
                )
            )
        ).scalar_one()
        if pending >= MAX_PENDING_REQUESTS:
            await session.commit()
            return None
        result = await session.execute(
            text(
                "INSERT INTO worker_enrollment_requests "
                "(id, poll_token_hash, name, hostname, ip_address, queues, status, created_at) "
                "VALUES (:id, :h, :name, :host, :ip, :queues, 'pending', now()) "
                "RETURNING id"
            ),
            {
                "id": uuid.uuid4(),
                "h": hash_secret(poll_token),
                "name": name,
                "host": hostname,
                "ip": ip_address,
                "queues": queues,
            },
        )
        row = result.one()
        await session.commit()
    return {"id": row[0], "poll_token": poll_token}


async def list_enrollment_requests() -> List[Dict[str, Any]]:
    """Every retained request, pending first, newest first within a status."""
    async with db.get_session_factory()() as session:
        result = await session.execute(
            text(
                f"SELECT {_REQUEST_COLUMNS} FROM worker_enrollment_requests "
                "ORDER BY (status = 'pending') DESC, created_at DESC"
            )
        )
        return [_request_row(r) for r in result.fetchall()]


async def decide_enrollment_request(
    request_id: uuid.UUID,
    approve: bool,
    queues: Optional[List[str]],
    decided_by: Optional[uuid.UUID],
) -> Optional[Dict[str, Any]]:
    """Approve (with the granted queues) or reject a pending request; None when it is not pending."""
    async with db.get_session_factory()() as session:
        result = await session.execute(
            text(
                "UPDATE worker_enrollment_requests SET "
                "status = :status, queues = COALESCE(:queues, queues), "
                "decided_by = :by, decided_at = now() "
                "WHERE id = :id AND status = 'pending' "
                f"RETURNING {_REQUEST_COLUMNS}"
            ),
            {
                "id": request_id,
                "status": "approved" if approve else "rejected",
                "queues": queues if approve else None,
                "by": decided_by,
            },
        )
        row = result.fetchone()
        await session.commit()
    return _request_row(row) if row else None


async def poll_enrollment_request(
    request_id: uuid.UUID, poll_token: str
) -> Optional[Dict[str, Any]]:
    """The request's status for its own worker; an approved one is claimed once and carries the credential."""
    async with db.get_session_factory()() as session:
        claimed = (
            await session.execute(
                text(
                    "UPDATE worker_enrollment_requests SET status = 'claimed' "
                    "WHERE id = :id AND poll_token_hash = :h AND status = 'approved' "
                    "RETURNING name, queues"
                ),
                {"id": request_id, "h": hash_secret(poll_token)},
            )
        ).fetchone()
        if claimed:
            created = await _insert_enrollment(
                session, claimed[0], list(claimed[1] or []), None
            )
            await session.execute(
                text(
                    "UPDATE worker_enrollment_requests SET enrollment_id = :eid "
                    "WHERE id = :id"
                ),
                {"eid": created["id"], "id": request_id},
            )
            await session.commit()
            return {
                "status": "approved",
                "credential": created["credential"],
                "queues": list(claimed[1] or []),
            }
        row = (
            await session.execute(
                text(
                    "SELECT status FROM worker_enrollment_requests "
                    "WHERE id = :id AND poll_token_hash = :h"
                ),
                {"id": request_id, "h": hash_secret(poll_token)},
            )
        ).fetchone()
    if not row:
        return None
    return {"status": row[0], "credential": None, "queues": []}
