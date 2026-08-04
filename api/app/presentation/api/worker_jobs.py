# api/app/presentation/api/worker_jobs.py

"""Internal worker endpoints: job claim, result submission, status."""

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any, Dict, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.services.result_processing.step_result_enrichment import (
    build_step_result_payload,
)
from app.application.services.result_processing.worker_error_codes import (
    client_message_for_worker_error,
)
from app.domain.queue.repository import QueuedJobRepository, WorkerRepository
from app.config.queues import allowed_queues
from app.infrastructure.auth.worker_jwt import verify_worker_token
from app.infrastructure.repositories.queue_job_repository import (
    SQLAlchemyQueuedJobRepository,
)
from app.presentation.api.dependencies import (
    get_db_session_service,
    get_queued_job_repository_bypass,
    get_worker_repository,
    verify_worker_secret,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal", tags=["worker-jobs"])


# --- Request/Response Models ---


class ClaimJobResponse(BaseModel):
    """Response when a job is claimed."""

    job_id: str
    step_id: str
    queue_name: str
    payload: Dict[str, Any]
    claimed_at: str


# --- Dependencies ---


def verify_worker_jwt(
    authorization: Optional[str] = Header(None, alias="Authorization"),
) -> Dict[str, Any]:
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header required. Use: Authorization: Bearer <token>",
        )

    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header format. Expected: Bearer <token>",
        )

    token = parts[1]

    try:
        return verify_worker_token(token)
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"Worker JWT verification failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid worker token"
        )


get_job_repository = get_queued_job_repository_bypass


# --- Endpoints ---


@router.get("/jobs/claim", response_model=Optional[ClaimJobResponse])
async def claim_job(
    queue_name: str = Query(
        ..., description="Queue name to claim from (e.g., 'step_jobs', 'video_jobs')"
    ),
    authorization: Optional[str] = Header(None, alias="Authorization"),
    _: None = Depends(verify_worker_secret),
    repo: QueuedJobRepository = Depends(get_job_repository),
) -> Optional[ClaimJobResponse]:
    """
    Claim the next available job from a queue.

    Authentication:
    - Requires Authorization: Bearer <token> header (JWT from registration/heartbeat)
    - Also requires X-Worker-Secret header for transport security
    - Worker's queue_labels (from JWT) must include the requested queue_name

    This endpoint atomically claims a pending job using PostgreSQL's
    SELECT FOR UPDATE SKIP LOCKED, ensuring only one worker can claim
    each job even under concurrent access.

    Returns:
        - 200 with job data if a job was claimed
        - 204 (No Content) if no jobs available
        - 401 if worker authentication fails
        - 403 if worker not authorized for requested queue
    """
    # Validate JWT - worker_id and queue_labels come from token
    worker_info = verify_worker_jwt(authorization)
    worker_id = worker_info["worker_id"]
    queue_labels = worker_info.get("queue_labels", [])
    # Silenced: fires on every claim with unchanging queue_labels; not actionable.
    # logger.debug(f"JWT auth: worker_id={worker_id}, queue_labels={queue_labels}")

    # Defense in depth: the queue must be in the system allowlist even when
    # the token would authorize it (ruling 2026-08-03).
    if queue_name not in allowed_queues():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Queue '{queue_name}' is not in the allowed set.",
        )

    # Validate worker is authorized to claim from this queue
    if queue_name not in queue_labels:
        logger.warning(
            f"Worker {worker_id} attempted to claim from unauthorized queue: "
            f"{queue_name} (allowed: {queue_labels})"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Worker not authorized to claim from queue '{queue_name}'. "
            f"Allowed queues: {queue_labels}",
        )

    logger.info(f"Worker {worker_id} claiming job from queue: {queue_name}")

    job = await repo.claim_next_pending_by_queue_name(
        queue_name=queue_name,
        worker_id=worker_id,
    )

    if not job:
        # logger.debug(f"No jobs available in queue: {queue_name}")
        raise HTTPException(
            status_code=status.HTTP_204_NO_CONTENT, detail="No jobs available"
        )

    logger.debug(f"Worker {worker_id} claimed job {job.id} from queue {queue_name}")

    # storage_mode=local workers need `organization_id` to compute the
    # canonical /workspace/orgs/{org}/instances/{inst}/{file} write path.
    # The API has been deriving it server-side; surfacing it on the claim
    # avoids a DB round-trip per upload while keeping it advisory (the
    # /files/register handler still re-derives the path from the JWT-bound
    # job - clients can lie about org_id but the API never trusts it).
    payload = dict(job.input_data)
    payload.setdefault("organization_id", str(job.organization_id))
    if job.instance_id is not None:
        payload.setdefault("instance_id", str(job.instance_id))

    return ClaimJobResponse(
        job_id=str(job.id),
        step_id=payload.get("step_id", ""),
        queue_name=queue_name,
        payload=payload,
        claimed_at=datetime.now(UTC).isoformat(),
    )


class StepResultRequest(BaseModel):
    model_config = {"extra": "forbid"}

    status: str  # PROCESSING, COMPLETED, FAILED, etc.
    result: Dict[str, Any] = {}
    error: Optional[str] = None  # Log-only detail; never rendered to clients.
    error_code: Optional[str] = None
    job_id: Optional[str] = None
    # Worker fired async + released without polling.
    webhook_pending: bool = False


@router.post("/step-results")
async def publish_step_result(
    request: StepResultRequest,
    http_request: Request,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    session: AsyncSession = Depends(get_db_session_service),
) -> Dict[str, str]:
    """Publish step result or progress update."""
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header required",
        )
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Expected: Authorization: Bearer <token>",
        )
    try:
        token_data = verify_worker_token(parts[1])
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid worker token",
        )

    try:
        worker_uuid = UUID(token_data["worker_id"])
    except (KeyError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing worker_id",
        )

    job_repo = SQLAlchemyQueuedJobRepository(session)

    if request.job_id:
        try:
            job_uuid = UUID(request.job_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid job_id format",
            )
        job = await job_repo.get_job_for_worker_upload(job_uuid, worker_uuid)
        if not job:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Job not found or not owned by this worker",
            )
    else:
        job = await job_repo.get_claimed_job_by_worker(worker_uuid)
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No active job found for this worker",
            )

    client_error = client_message_for_worker_error(request.error_code)
    if request.status == "COMPLETED":
        await job_repo.complete_job(job.id, request.result or {})
    elif request.status == "FAILED":
        logger.warning(
            "Step job %s FAILED [code=%s]: %s",
            job.id,
            request.error_code,
            request.error,
        )
        await job_repo.fail_job(job.id, client_error)

    # Single source of truth for the routing payload - shared with dead-letter
    # replay so a result delivered after an outage is routed identically (Bug #2).
    payload = build_step_result_payload(
        job,
        status=request.status,
        result=request.result,
        error=client_error if request.status == "FAILED" else None,
        webhook_pending=request.webhook_pending,
    )
    instance_id = payload["instance_id"]
    step_id = payload["step_id"]

    result_processor = http_request.app.state.result_processor

    async def _run() -> None:
        try:
            await result_processor.process_result(payload)
            logger.debug(
                f"Processed step result: instance={instance_id}, step={step_id}, status={request.status}"
            )
        except Exception as e:
            logger.error(f"Background result processing failed: {e}")

    asyncio.create_task(_run())
    return {"status": "published"}


@router.get("/jobs/{job_id}/status")
async def get_job_status(
    job_id: str,
    _: None = Depends(verify_worker_secret),
    repo: QueuedJobRepository = Depends(get_job_repository),
) -> Dict[str, Any]:
    """
    Get the current status of a job.

    Useful for workers to check if a job they're working on has been
    cancelled or if they should continue.
    """
    job = await repo.get_by_id(UUID(job_id))

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Job not found"
        )

    return {
        "job_id": str(job.id),
        "status": job.status.value if job.status else "UNKNOWN",
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "failed_at": job.failed_at.isoformat() if job.failed_at else None,
    }


@router.post("/workers/cleanup")
async def cleanup_stale_workers(
    http_request: Request,
    _: None = Depends(verify_worker_secret),
    worker_repo: WorkerRepository = Depends(get_worker_repository),
    session: AsyncSession = Depends(get_db_session_service),
) -> Dict[str, Any]:
    """
    Periodic cleanup (admin/cron endpoint). Mirrors the in-process cleanup cycle.

    1. Stale workers - marks workers with heartbeats > WORKER_HEARTBEAT_TIMEOUT_MINUTES
       as deregistered so they can't claim new jobs; requeues jobs abandoned by a
       vanished/moved-on worker (the crash-recovery path - no timer fails a step).
    2. Webhook notify sweep - fires the once-per-step "still awaiting provider
       callback" notification for WFW steps idle past their notify window. Never
       fails a step on a timer (I-13).

    Should be called periodically (e.g., every minute via cron).

    Returns:
        Combined cleanup statistics
    """
    from app.application.services.instance_notifier import InstanceNotifier
    from app.application.services.webhook_reconcile_sweep_service import (
        WebhookReconcileSweepService,
    )
    from app.application.services.worker_cleanup_service import WorkerCleanupService
    from app.infrastructure.repositories.instance_repository import (
        SQLAlchemyInstanceRepository,
    )
    from app.infrastructure.repositories.queue_job_repository import (
        SQLAlchemyQueuedJobRepository,
    )
    from app.infrastructure.repositories.step_execution_repository import (
        SQLAlchemyStepExecutionRepository,
    )

    step_repo = SQLAlchemyStepExecutionRepository(session)
    job_repo = SQLAlchemyQueuedJobRepository(session)

    # Full wiring so the requeue half actually fires (resumes jobs abandoned
    # by a vanished/moved-on worker).
    cleanup_service = WorkerCleanupService(
        worker_repository=worker_repo,
        queued_job_repository=job_repo,
        step_execution_repository=step_repo,
    )
    worker_result = await cleanup_service.run_cleanup()

    # Reuse the long-lived notifier from app.state (set up at startup with
    # the WebSocket broadcast closures). Falls back to None in tests where
    # the notifier isn't registered.
    notifier: Optional[InstanceNotifier] = getattr(
        http_request.app.state, "notifier", None
    )

    notify_result = await WebhookReconcileSweepService(
        step_execution_repository=step_repo,
        instance_repository=SQLAlchemyInstanceRepository(session),
        notifier=notifier,
        session=session,
    ).reconcile_webhook_steps()

    return {
        **worker_result,
        "webhook_steps_examined": notify_result.steps_examined,
        "webhook_steps_notified": notify_result.steps_notified,
    }
