# api/app/presentation/api/worker_auth.py

"""Worker authentication after registration: every call carries the worker JWT."""

from dataclasses import dataclass
from typing import List, Optional
from uuid import UUID

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.queue.models import QueuedJob
from app.infrastructure.auth.worker_jwt import verify_worker_token
from app.infrastructure.persistence.database import get_db_session_service
from app.infrastructure.repositories.queue_job_repository import (
    SQLAlchemyQueuedJobRepository,
)
from app.infrastructure.repositories.worker_repository import (
    SQLAlchemyWorkerRepository,
)


@dataclass(frozen=True)
class WorkerIdentity:
    """The worker a verified JWT speaks for."""

    worker_id: UUID
    queue_labels: List[str]


def worker_token_claims(
    authorization: Optional[str] = Header(None, alias="Authorization"),
) -> WorkerIdentity:
    """Verify the Bearer worker JWT; 401 when missing, malformed, expired or not a worker token."""
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header required. Use: Authorization: Bearer <token>",
        )
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Expected: Authorization: Bearer <token>",
        )
    claims = verify_worker_token(parts[1])
    try:
        worker_id = UUID(str(claims["worker_id"]))
    except (KeyError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid worker token",
        )
    return WorkerIdentity(
        worker_id=worker_id, queue_labels=list(claims.get("queue_labels") or [])
    )


async def require_worker(
    identity: WorkerIdentity = Depends(worker_token_claims),
    session: AsyncSession = Depends(get_db_session_service),
) -> WorkerIdentity:
    """Worker JWT whose worker row exists and is not deregistered; 403 otherwise."""
    worker = await SQLAlchemyWorkerRepository(session).get_by_id(identity.worker_id)
    if not worker or worker.is_deregistered:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Worker is not registered",
        )
    return identity


async def resolve_worker_job(
    worker_id: UUID,
    job_id: Optional[str],
    session: AsyncSession,
) -> Optional[QueuedJob]:
    """The named RUNNING job if this worker owns it, else the worker's claimed job."""
    repo = SQLAlchemyQueuedJobRepository(session)
    if not job_id:
        return await repo.get_claimed_job_by_worker(worker_id)
    try:
        job_uuid = UUID(job_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid job_id format",
        )
    return await repo.get_job_for_worker_upload(job_uuid, worker_id)


async def require_worker_job(
    worker_id: UUID,
    job_id: Optional[str],
    session: AsyncSession,
) -> QueuedJob:
    """resolve_worker_job, raising 403 for a named job the worker does not own and 404 when it holds none."""
    job = await resolve_worker_job(worker_id, job_id, session)
    if job:
        return job
    if job_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Job not found or not owned by this worker",
        )
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="No active job found for this worker",
    )
