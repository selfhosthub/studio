# api/app/presentation/api/workers.py

"""Worker self-registration / heartbeat / deregistration. JWT issued on register, refreshed on heartbeat."""

import hmac
import logging
from typing import Union
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Path, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.services.comfyui_catalog_hash import cached_catalog_hash
from app.application.services.queue_service import QueueService
from app.application.interfaces import EntityNotFoundError, ValidationError
from app.domain.queue.models import WorkerStatus
from app.config.queues import allowed_queues
from app.config.settings import settings
from app.infrastructure.security.worker_bootstrap import bootstrap_token_matches
from app.infrastructure.security.worker_enrollment import looks_like_credential
from app.infrastructure.security.worker_enrollment_store import (
    consume_join_token,
    create_enrollment,
    create_enrollment_request,
    enrollment_is_live,
    poll_enrollment_request,
    resolve_enrollment,
    touch_enrollment,
)
from app.infrastructure.auth.worker_jwt import create_worker_token
from app.domain.queue.repository import WorkerRepository
from app.infrastructure.persistence.database import get_db_session
from app.presentation.api.dependencies import (
    get_queue_service_bypass,
    get_worker_repository,
)
from app.presentation.api.worker_auth import WorkerIdentity, worker_token_claims
from app.presentation.api.models.worker import (
    EnrollmentRequestPollRequest,
    EnrollmentRequestPollResponse,
    WorkerEnrollmentPendingResponse,
    WorkerDeregistrationResponse,
    WorkerEnrollRequest,
    WorkerEnrollResponse,
    WorkerHeartbeatRequest,
    WorkerHeartbeatResponse,
    WorkerRegistrationRequest,
    WorkerRegistrationResponse,
)
from app.infrastructure.errors import safe_error_message

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/enroll",
    response_model=WorkerEnrollResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Exchange a join token for a worker credential",
    description="""
    One-time enrollment. A super admin mints a join token and hands it to the
    worker's operator; the worker exchanges it here for a long-lived, revocable
    credential scoped to the token's queues.

    The credential is returned once and never again: only its hash is stored.
    """,
)
async def enroll_worker(request: WorkerEnrollRequest) -> WorkerEnrollResponse:
    """401 if the token is unknown, already used, or expired."""
    scope = await consume_join_token(request.join_token)
    if scope is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Join token is unknown, already used, or expired.",
        )

    created = await create_enrollment(
        label=request.label or scope["label"],
        queues=scope["queues"],
        join_token_id=scope["id"],
    )
    logger.info(
        f"Worker enrolled: {request.label or scope['label']} "
        f"(enrollment={created['id']}, queues={sorted(scope['queues'])})"
    )
    return WorkerEnrollResponse(credential=created["credential"], queues=scope["queues"])


@router.post(
    "/enroll/requests/{request_id}",
    response_model=EnrollmentRequestPollResponse,
    summary="Poll a pending enrollment request",
    description="""
    A worker whose registration is waiting for a super admin polls here with the
    token it received. An approved request returns the worker's credential once.
    """,
)
async def poll_enrollment(
    request_id: UUID, request: EnrollmentRequestPollRequest
) -> EnrollmentRequestPollResponse:
    """404 unknown request or token; 410 credential already collected."""
    result = await poll_enrollment_request(request_id, request.poll_token)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Enrollment request not found.",
        )
    if result["status"] == "claimed":
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="This request's credential was already collected.",
        )
    return EnrollmentRequestPollResponse(**result)


@router.post(
    "/register",
    response_model=WorkerRegistrationResponse,
    status_code=status.HTTP_201_CREATED,
    responses={202: {"model": WorkerEnrollmentPendingResponse}},
    summary="Register a new worker",
    description="""
    Worker self-registration endpoint. Workers call this on startup with the
    shared secret or their enrollment credential.

    A shared-secret worker that also presents the workspace bootstrap token is
    inside the deployment and registers at once. Any other shared-secret worker
    gets 202 and a pending enrollment request a super admin approves.
    """,
)
async def register_worker(
    request: WorkerRegistrationRequest,
    service: QueueService = Depends(get_queue_service_bypass),
) -> Union[WorkerRegistrationResponse, JSONResponse]:
    """400 invalid secret/validation or out-of-set queue; 401 dead credential; 404 queue not found; 429 too many pending requests."""
    # secret carries either the fleet shared secret or an enrollment credential,
    # told apart by the credential's prefix. A credential narrows the allowed set
    # to its recorded scope; it can never widen it.
    operator_allowed = allowed_queues()
    enrollment = None
    if looks_like_credential(request.secret):
        enrollment = await resolve_enrollment(request.secret)
        if enrollment is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Worker credential is unknown or revoked.",
            )
        await touch_enrollment(enrollment["id"])
        allowed = operator_allowed & frozenset(enrollment["queues"])
    else:
        allowed = operator_allowed

    # Queues actually served: the explicit field is enforced by name against
    # the allowlist (compiled defaults union SHS_ALLOWED_QUEUES; ruling
    # 2026-08-03). Legacy workers send labels only; infer served queues as
    # the labels that are allowed queues, so capability tags never refuse.
    if request.queues:
        refused = [q for q in request.queues if q not in allowed]
        if refused:
            scope_note = (
                "This credential is scoped to: "
                f"{', '.join(sorted(enrollment['queues'])) or 'no queues'}."
                if enrollment
                else "The operator can widen it via SHS_ALLOWED_QUEUES."
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Queue(s) not in the allowed set: {', '.join(sorted(refused))}. "
                + scope_note,
            )
        served_queues = request.queues
    else:
        served_queues = [q for q in request.queue_labels if q in allowed]
    if enrollment is None and not bootstrap_token_matches(request.bootstrap_token):
        if not hmac.compare_digest(request.secret, settings.WORKER_SHARED_SECRET):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid worker secret",
            )
        try:
            service.check_worker_version(request.name, request.worker_version)
        except ValidationError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=safe_error_message(e)
            )
        pending = await create_enrollment_request(
            name=request.name,
            hostname=request.hostname,
            ip_address=request.ip_address,
            queues=list(served_queues),
        )
        if pending is None:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many enrollment requests are waiting for approval.",
            )
        logger.info(
            f"Worker enrollment requested: {request.name} "
            f"(request={pending['id']}, hostname={request.hostname})"
        )
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content=WorkerEnrollmentPendingResponse(
                request_id=pending["id"], poll_token=pending["poll_token"]
            ).model_dump(mode="json"),
        )
    # An enrolled worker keeps only the labels that are not queue names, so a
    # self-declared queue cannot re-widen what the credential granted.
    if enrollment is not None:
        tags = [q for q in request.queue_labels if q not in operator_allowed]
        labels = sorted(set(served_queues) | set(tags))
    else:
        labels = sorted(set(request.queue_labels) | set(served_queues))
    try:
        result = await service.register_worker(
            secret=request.secret,
            name=request.name,
            worker_version=request.worker_version,
            queue_id=request.queue_id,
            capabilities={**request.capabilities, "queues": served_queues},
            queue_labels=labels,
            ip_address=request.ip_address,
            hostname=request.hostname,
            cpu_percent=request.cpu_percent,
            memory_percent=request.memory_percent,
            memory_used_mb=request.memory_used_mb,
            memory_total_mb=request.memory_total_mb,
            disk_percent=request.disk_percent,
            gpu_percent=request.gpu_percent,
            gpu_memory_percent=request.gpu_memory_percent,
            storage_mode=request.storage_mode,
            enrollment_id=enrollment["id"] if enrollment else None,
        )
        token = create_worker_token(
            worker_id=str(result.id),
            queue_labels=labels,
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

    Requires the worker's own JWT. A worker whose enrollment was revoked is
    deregistered and receives no token.
    """,
)
async def worker_heartbeat(
    worker_id: UUID = Path(..., description="Worker ID from registration"),
    request: WorkerHeartbeatRequest = Body(...),
    identity: WorkerIdentity = Depends(worker_token_claims),
    service: QueueService = Depends(get_queue_service_bypass),
    session: AsyncSession = Depends(get_db_session),
    worker_repo: WorkerRepository = Depends(get_worker_repository),
) -> WorkerHeartbeatResponse:
    """Updates last_heartbeat + status, returns refreshed JWT. 400 invalid status; 403 another worker's token; 404 worker missing."""
    if identity.worker_id != worker_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Token does not belong to this worker",
        )
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
                storage_mode=request.storage_mode,
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
                storage_mode=request.storage_mode,
            )

        token = None
        comfyui_catalog_hash = None
        if not is_deregistered:
            worker = await worker_repo.get_by_id(worker_id)
            if worker and worker.enrollment_id and not await enrollment_is_live(
                worker.enrollment_id
            ):
                await worker_repo.mark_workers_as_deregistered([worker.id])
                is_deregistered = True
                worker = None
            if worker:
                # Refresh tokens keep the served queues claim-authorized, same
                # union as registration.
                served = (worker.capabilities or {}).get("queues") or []
                queue_labels = sorted(set(worker.queue_labels or []) | set(served))
                token = create_worker_token(
                    worker_id=str(worker.id),
                    queue_labels=queue_labels,
                    capabilities=worker.capabilities or {},
                )
                # comfyui workers get the catalog hash so they can flag a resync.
                if any(label.startswith("comfyui") for label in queue_labels):
                    comfyui_catalog_hash = await cached_catalog_hash(session)

        return WorkerHeartbeatResponse(
            status="ok",
            deregistered=is_deregistered,
            token=token,
            comfyui_catalog_hash=comfyui_catalog_hash,
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

    Requires the worker's own JWT.
    """,
)
async def deregister_worker(
    worker_id: UUID = Path(..., description="Worker ID to deregister"),
    identity: WorkerIdentity = Depends(worker_token_claims),
    service: QueueService = Depends(get_queue_service_bypass),
) -> WorkerDeregistrationResponse:
    """403 another worker's token; 404 worker not found."""
    if identity.worker_id != worker_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Token does not belong to this worker",
        )
    try:
        await service.deregister_worker(worker_id=worker_id)
        return WorkerDeregistrationResponse(
            status="ok",
            message=f"Worker {worker_id} deregistered successfully",
        )
    except EntityNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=safe_error_message(e))
