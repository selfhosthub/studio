# api/app/presentation/api/workers.py

"""Worker self-registration / heartbeat / deregistration. JWT issued on register, refreshed on heartbeat."""

import logging
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Path, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.services.queue_service import QueueService
from app.application.interfaces import EntityNotFoundError, ValidationError
from app.domain.queue.models import WorkerStatus
from app.infrastructure.auth.worker_jwt import create_worker_token
from app.domain.queue.repository import WorkerRepository
from app.infrastructure.persistence.database import get_db_session
from app.presentation.api.dependencies import (
    get_queue_service_bypass,
    get_worker_repository,
)
from app.presentation.api.models.worker import (
    WorkerDeregistrationRequest,
    WorkerDeregistrationResponse,
    WorkerHeartbeatRequest,
    WorkerHeartbeatResponse,
    WorkerRegistrationRequest,
    WorkerRegistrationResponse,
)
from app.infrastructure.errors import safe_error_message

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/register",
    response_model=WorkerRegistrationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new worker",
    description="""
    Worker self-registration endpoint. Workers call this on startup to register
    themselves with the system using a shared secret.

    No user authentication required - workers authenticate via shared secret.
    """,
)
async def register_worker(
    request: WorkerRegistrationRequest,
    service: QueueService = Depends(get_queue_service_bypass),
) -> WorkerRegistrationResponse:
    """400 invalid secret/validation; 404 queue not found."""
    try:
        result = await service.register_worker(
            secret=request.secret,
            name=request.name,
            queue_id=request.queue_id,
            capabilities=request.capabilities,
            queue_labels=request.queue_labels,
            ip_address=request.ip_address,
            hostname=request.hostname,
            cpu_percent=request.cpu_percent,
            memory_percent=request.memory_percent,
            memory_used_mb=request.memory_used_mb,
            memory_total_mb=request.memory_total_mb,
            disk_percent=request.disk_percent,
            gpu_percent=request.gpu_percent,
            gpu_memory_percent=request.gpu_memory_percent,
        )
        token = create_worker_token(
            worker_id=str(result.id),
            queue_labels=request.queue_labels,
            capabilities=request.capabilities,
        )

        logger.info(
            f"Worker registered: {result.name} (id={result.id}, "
            f"ip={request.ip_address}, hostname={request.hostname})"
        )
        return WorkerRegistrationResponse(worker_id=result.id, token=token)
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=safe_error_message(e))
    except EntityNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=safe_error_message(e))


@router.post(
    "/{worker_id}/heartbeat",
    response_model=WorkerHeartbeatResponse,
    status_code=status.HTTP_200_OK,
    summary="Send worker heartbeat",
    description="""
    Workers send heartbeats every 60 seconds to indicate they're alive and report
    their current status (idle/busy).

    Workers that miss heartbeats for 3+ minutes are automatically considered offline
    and removed from the active workers list.

    No user authentication required.
    """,
)
async def worker_heartbeat(
    worker_id: UUID = Path(..., description="Worker ID from registration"),
    request: WorkerHeartbeatRequest = Body(...),
    service: QueueService = Depends(get_queue_service_bypass),
    session: AsyncSession = Depends(get_db_session),
    worker_repo: WorkerRepository = Depends(get_worker_repository),
) -> WorkerHeartbeatResponse:
    """Updates last_heartbeat + status, returns refreshed JWT. 400 invalid status; 404 worker missing."""
    try:
        worker_status = WorkerStatus(request.status.lower())

        # BUSY routes through set_busy so the service enforces the
        # workers.current_job_id → queued_jobs.id FK contract before SQL
        # sees the value. Non-BUSY clears current_job_id.
        if worker_status == WorkerStatus.BUSY:
            if request.current_job_id is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "current_job_id is required when status='busy'. "
                        "Pass the queued_jobs.id of the claimed job."
                    ),
                )
            is_deregistered = await service.set_busy(
                worker_id=worker_id,
                queued_job_id=request.current_job_id,
                cpu_percent=request.cpu_percent,
                memory_percent=request.memory_percent,
                memory_used_mb=request.memory_used_mb,
                memory_total_mb=request.memory_total_mb,
                disk_percent=request.disk_percent,
                gpu_percent=request.gpu_percent,
                gpu_memory_percent=request.gpu_memory_percent,
            )
        else:
            is_deregistered = await service.worker_heartbeat(
                worker_id=worker_id,
                status=worker_status,
                current_job_id=None,
                cpu_percent=request.cpu_percent,
                memory_percent=request.memory_percent,
                memory_used_mb=request.memory_used_mb,
                memory_total_mb=request.memory_total_mb,
                disk_percent=request.disk_percent,
                gpu_percent=request.gpu_percent,
                gpu_memory_percent=request.gpu_memory_percent,
            )

        token = None
        if not is_deregistered:
            worker = await worker_repo.get_by_id(worker_id)
            if worker:
                token = create_worker_token(
                    worker_id=str(worker.id),
                    queue_labels=worker.queue_labels or [],
                    capabilities=worker.capabilities or {},
                )

        # DEBUG - too noisy for INFO at heartbeat cadence
        resource_info = ""
        if request.cpu_percent is not None or request.memory_percent is not None:
            resource_info = f" cpu={request.cpu_percent}% mem={request.memory_percent}%"
        logger.debug(
            f"Worker heartbeat: {worker_id} status={request.status}" f"{resource_info}"
        )
        return WorkerHeartbeatResponse(
            status="ok", deregistered=is_deregistered, token=token
        )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid status. Must be 'idle' or 'busy'. Got: {request.status}",
        )
    except EntityNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=safe_error_message(e))
    except HTTPException:
        # Already-shaped HTTPException - skip the unexpected-exception logger below.
        raise
    except Exception:
        # Without this stack, opaque 500s in worker logs hide the real cause
        # (FK violations on current_job_id, event bus, transient DB).
        logger.exception(
            "worker_heartbeat failed unexpectedly",
            extra={
                "worker_id": str(worker_id),
                "current_job_id": (
                    str(request.current_job_id) if request.current_job_id else None
                ),
                "status": request.status,
            },
        )
        raise


@router.delete(
    "/{worker_id}",
    response_model=WorkerDeregistrationResponse,
    status_code=status.HTTP_200_OK,
    summary="Deregister a worker",
    description="""
    Worker self-deregistration endpoint. Workers call this on shutdown to cleanly
    remove themselves from the system.

    Requires the same shared secret used for registration.
    """,
)
async def deregister_worker(
    worker_id: UUID = Path(..., description="Worker ID to deregister"),
    request: WorkerDeregistrationRequest = Body(...),
    service: QueueService = Depends(get_queue_service_bypass),
) -> WorkerDeregistrationResponse:
    """400 invalid secret; 404 worker not found."""
    try:
        await service.deregister_worker(
            worker_id=worker_id,
            secret=request.secret,
        )
        return WorkerDeregistrationResponse(
            status="ok",
            message=f"Worker {worker_id} deregistered successfully",
        )
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=safe_error_message(e))
    except EntityNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=safe_error_message(e))
