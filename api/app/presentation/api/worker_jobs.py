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

from app.domain.queue.repository import QueuedJobRepository, WorkerRepository
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


class SubmitResultRequest(BaseModel):
    """Request to submit job result."""

    model_config = {"extra": "forbid"}

    status: str  # "COMPLETED" or "FAILED"
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class SubmitResultResponse(BaseModel):
    """Response after submitting result."""

    job_id: str
    status: str
    completed_at: Optional[str] = None
    failed_at: Optional[str] = None


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
    logger.debug(f"JWT auth: worker_id={worker_id}, queue_labels={queue_labels}")

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
        logger.debug(f"No jobs available in queue: {queue_name}")
        raise HTTPException(
            status_code=status.HTTP_204_NO_CONTENT, detail="No jobs available"
        )

    logger.debug(f"Worker {worker_id} claimed job {job.id} from queue {queue_name}")

    return ClaimJobResponse(
        job_id=str(job.id),
        step_id=job.input_data.get("step_id", ""),  # step_id is in payload
        queue_name=queue_name,
        payload=job.input_data,  # Full job payload
        claimed_at=datetime.now(UTC).isoformat(),
    )


@router.post("/jobs/{job_id}/result", response_model=SubmitResultResponse)
async def submit_job_result(
    job_id: str,
    request: SubmitResultRequest,
    http_request: Request,
    _: None = Depends(verify_worker_secret),
    repo: QueuedJobRepository = Depends(get_job_repository),
) -> SubmitResultResponse:
    """
    Submit the result of a job execution.

    Workers call this after executing a job to report success or failure.
    This endpoint:
    1. Updates PostgreSQL job status (for audit/tracking)
    2. Feeds result to ResultProcessor for workflow orchestration

    Args:
        job_id: The job ID (from claim response)
        request: Result data (status, result/error)

    Returns:
        Confirmation of result submission
    """
    logger.info(f"Receiving result for job {job_id}: status={request.status}")

    job_uuid = UUID(job_id)

    # First, fetch the job to get instance_id and step_id for ResultConsumer
    job = await repo.get_by_id(job_uuid)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Job not found"
        )

    # Extract instance_id and step_id from job payload
    instance_id = str(job.instance_id) if job.instance_id else None
    step_id = job.input_data.get("step_id", "") if job.input_data else ""

    if request.status == "COMPLETED":
        job = await repo.complete_job(
            job_id=job_uuid,
            output_data=request.result or {},
        )
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Job not found"
            )

        logger.info(f"Job {job_id} marked as COMPLETED in PostgreSQL")

        # Fire-and-forget orchestration so the worker gets an immediate
        # response and the event loop stays free for other requests.
        _schedule_result_processing(
            http_request,
            instance_id=instance_id,
            step_id=step_id,
            status="COMPLETED",
            result=request.result or {},
            error=None,
            input_data=job.input_data,
        )

        return SubmitResultResponse(
            job_id=job_id,
            status="COMPLETED",
            completed_at=job.completed_at.isoformat() if job.completed_at else None,
        )

    elif request.status == "FAILED":
        job = await repo.fail_job(
            job_id=job_uuid,
            error_message=request.error or "Unknown error",
        )
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Job not found"
            )

        logger.info(f"Job {job_id} marked as FAILED in PostgreSQL: {request.error}")

        # Fire-and-forget orchestration (same as COMPLETED path)
        _schedule_result_processing(
            http_request,
            instance_id=instance_id,
            step_id=step_id,
            status="FAILED",
            result=None,
            error=request.error or "Unknown error",
            input_data=job.input_data,
        )

        return SubmitResultResponse(
            job_id=job_id,
            status="FAILED",
            failed_at=job.failed_at.isoformat() if job.failed_at else None,
        )

    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid status: {request.status}. Must be 'COMPLETED' or 'FAILED'",
        )


def _build_result_payload(
    instance_id: Optional[str],
    step_id: str,
    status: str,
    result: Optional[Dict[str, Any]],
    error: Optional[str],
    input_data: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Build the result payload dict, or None if instance_id is missing."""
    if not instance_id:
        logger.warning("Cannot process result: no instance_id")
        return None

    payload: Dict[str, Any] = {
        "instance_id": instance_id,
        "step_id": step_id,
        "status": status,
        "result": result or {},
        "error": error,
        "input_data": input_data or {},
        "published_at": datetime.now(UTC).isoformat(),
    }

    # Include iteration metadata if present in job input_data
    if input_data:
        if "iteration_index" in input_data:
            payload["iteration_index"] = input_data["iteration_index"]
        if "iteration_count" in input_data:
            payload["iteration_count"] = input_data["iteration_count"]
        if "iteration_group_id" in input_data:
            payload["iteration_group_id"] = input_data["iteration_group_id"]

    return payload


def _schedule_result_processing(
    http_request: Request,
    instance_id: Optional[str],
    step_id: str,
    status: str,
    result: Optional[Dict[str, Any]],
    error: Optional[str],
    input_data: Optional[Dict[str, Any]] = None,
) -> None:
    """Fire-and-forget result processing as an async background task."""
    payload = _build_result_payload(
        instance_id,
        step_id,
        status,
        result,
        error,
        input_data,
    )
    if payload is None:
        return

    result_processor = http_request.app.state.result_processor

    async def _run() -> None:
        try:
            await result_processor.process_result(payload)
            logger.debug(
                f"Processed step result: instance={instance_id}, "
                f"step={step_id}, status={status}"
            )
        except Exception as e:
            logger.error(f"Background result processing failed: {e}")

    asyncio.create_task(_run())


class StepResultRequest(BaseModel):
    model_config = {"extra": "forbid"}

    status: str  # PROCESSING, COMPLETED, FAILED, etc.
    result: Dict[str, Any] = {}
    error: Optional[str] = None
    job_id: Optional[str] = None


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

    instance_id = str(job.instance_id) if job.instance_id else None
    input_data = job.input_data or {}
    step_id = input_data.get("step_id", "")

    if request.status == "COMPLETED":
        await job_repo.complete_job(job.id, request.result or {})
    elif request.status == "FAILED":
        await job_repo.fail_job(job.id, request.error or "")

    payload: Dict[str, Any] = {
        "instance_id": instance_id,
        "step_id": step_id,
        "status": request.status,
        "result": request.result,
        "error": request.error,
        "input_data": input_data,
        "request_body": None,
        "published_at": datetime.now(UTC).isoformat(),
    }

    if "iteration_index" in input_data:
        payload["iteration_index"] = input_data["iteration_index"]
    if "iteration_count" in input_data:
        payload["iteration_count"] = input_data["iteration_count"]
    if "iteration_group_id" in input_data:
        payload["iteration_group_id"] = input_data["iteration_group_id"]

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
    Periodic cleanup (admin/cron endpoint).

    Runs two sweeps on the same cadence:
    1. Stale workers - marks workers with heartbeats > WORKER_HEARTBEAT_TIMEOUT_MINUTES
       as deregistered so they can't claim new jobs.
    2. Stale steps - fails steps stuck in QUEUED/RUNNING/PENDING beyond
       STALE_STEP_TIMEOUT_MINUTES. Catches worker crashes, result-publish
       failures, network partitions - any path that leaves a step orphaned.
       Also fails the parent instance and notifies operators.

    Should be called periodically (e.g., every minute via cron).

    Returns:
        Combined cleanup statistics
    """
    from app.application.services.stale_step_sweep_service import (
        StaleStepSweepService,
    )
    from app.application.services.worker_cleanup_service import WorkerCleanupService
    from app.infrastructure.repositories.instance_repository import (
        SQLAlchemyInstanceRepository,
    )
    from app.infrastructure.repositories.step_execution_repository import (
        SQLAlchemyStepExecutionRepository,
    )

    cleanup_service = WorkerCleanupService(worker_repo)
    worker_result = await cleanup_service.run_cleanup()

    # Reuse the long-lived notifier from app.state (set up at startup with
    # the WebSocket broadcast closures). Falls back to None in tests where
    # the notifier isn't registered.
    notifier = getattr(http_request.app.state, "notifier", None)

    sweep_service = StaleStepSweepService(
        session=session,
        step_execution_repository=SQLAlchemyStepExecutionRepository(session),
        instance_repository=SQLAlchemyInstanceRepository(session),
        notifier=notifier,
    )
    sweep_result = await sweep_service.sweep_stale_steps()

    return {
        **worker_result,
        "stale_steps_failed": sweep_result.steps_failed,
        "stale_instances_failed": sweep_result.instances_failed,
        "stale_step_threshold_minutes": sweep_result.threshold_minutes,
    }
