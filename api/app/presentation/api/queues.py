# api/app/presentation/api/queues.py

"""Queue and queued-job management API endpoints."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from app.config.settings import settings
from app.application.dtos.queue_dto import (
    QueueCreate as QueueCreateDTO,
    QueueUpdate as QueueUpdateDTO,
    QueuedJobResponse as QueuedJobResponseDTO,
)
from app.application.services.queue_service import QueueService
from app.domain.common.exceptions import EntityNotFoundError
from app.presentation.api.dependencies import (
    CurrentUser,
    get_current_user,
    get_queue_service,
    validate_organization_access,
)
from app.presentation.api.models.queue import (
    QueueCreate,
    QueueListResponse,
    QueueResponse,
    QueueStats,
    QueueUpdate,
)

router = APIRouter()


@router.post(
    "",
    response_model=QueueResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new queue",
)
async def create_queue(
    queue_data: QueueCreate,
    service: QueueService = Depends(get_queue_service),
    user: CurrentUser = Depends(get_current_user),
) -> QueueResponse:
    """User must belong to organization."""
    await validate_organization_access(str(queue_data.organization_id), user)

    command = QueueCreateDTO(
        organization_id=queue_data.organization_id,
        name=queue_data.name,
        description=queue_data.description,
        max_concurrency=queue_data.max_workers,
        max_pending_jobs=queue_data.max_jobs,
        default_timeout_seconds=queue_data.timeout,
        tags=[],
        client_metadata=queue_data.config,
        created_by=UUID(user["id"]),
    )

    result = await service.create_queue(command)

    return QueueResponse(
        id=result.id,
        organization_id=result.organization_id,
        name=result.name,
        description=result.description,
        max_workers=result.max_concurrency,
        active_workers=result.active_workers,
        max_jobs=result.max_pending_jobs,
        pending_jobs=0,
        priority=queue_data.priority,
        timeout=result.default_timeout_seconds,
        retry_limit=queue_data.retry_limit,
        config=result.client_metadata,
        metadata=result.client_metadata,
        created_at=result.created_at or datetime.now(),
        updated_at=result.updated_at or datetime.now(),
    )


@router.get(
    "",
    response_model=QueueListResponse,
    summary="List queues",
)
async def list_queues(
    organization_id: UUID = Query(..., description="Organization ID to filter by"),
    status_filter: Optional[str] = Query(
        None, alias="status", description="Status filter"
    ),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(settings.API_PAGE_LIMIT_DEFAULT, ge=1, le=1000, description="Maximum records to return"),
    service: QueueService = Depends(get_queue_service),
    user: CurrentUser = Depends(get_current_user),
) -> QueueListResponse:
    """User must belong to organization."""
    await validate_organization_access(str(organization_id), user)

    queues = await service.list_queues(
        organization_id=organization_id,
        status=status_filter,
        skip=skip,
        limit=limit,
    )

    queue_responses: list[QueueResponse] = []
    for q in queues:
        queue_responses.append(
            QueueResponse(
                id=q.id,
                organization_id=q.organization_id,
                name=q.name,
                description=q.description,
                max_workers=q.max_concurrency,
                active_workers=q.active_workers,
                max_jobs=q.max_pending_jobs,
                pending_jobs=0,
                priority=0,
                timeout=q.default_timeout_seconds,
                retry_limit=settings.JOB_RETRY_LIMIT,
                config=q.client_metadata,
                metadata=q.client_metadata,
                created_at=q.created_at or datetime.now(),
                updated_at=q.updated_at or datetime.now(),
            )
        )

    return QueueListResponse(
        queues=queue_responses,
        total=len(queue_responses),
    )


@router.get(
    "/{queue_id}",
    response_model=QueueResponse,
    summary="Get queue details",
)
async def get_queue(
    queue_id: UUID = Path(..., description="Queue ID"),
    service: QueueService = Depends(get_queue_service),
    user: CurrentUser = Depends(get_current_user),
) -> QueueResponse:
    """User must belong to queue's organization."""
    queue = await service.get_queue(queue_id)
    if not queue:
        raise EntityNotFoundError(
            entity_type="Queue",
            entity_id=queue_id,
            code=f"Queue with ID {queue_id} not found",
        )

    await validate_organization_access(str(queue.organization_id), user)

    return QueueResponse(
        id=queue.id,
        organization_id=queue.organization_id,
        name=queue.name,
        description=queue.description,
        max_workers=queue.max_concurrency,
        active_workers=queue.active_workers,
        max_jobs=queue.max_pending_jobs,
        pending_jobs=0,
        priority=0,
        timeout=queue.default_timeout_seconds,
        retry_limit=settings.JOB_RETRY_LIMIT,
        config=queue.client_metadata,
        metadata=queue.client_metadata,
        created_at=queue.created_at or datetime.now(),
        updated_at=queue.updated_at or datetime.now(),
    )


@router.get(
    "/{queue_id}/stats",
    response_model=QueueStats,
    summary="Get queue statistics",
)
async def get_queue_stats(
    queue_id: UUID = Path(..., description="Queue ID"),
    service: QueueService = Depends(get_queue_service),
    user: CurrentUser = Depends(get_current_user),
) -> QueueStats:
    """User must belong to queue's organization."""
    queue = await service.get_queue(queue_id)
    if not queue:
        raise EntityNotFoundError(
            entity_type="Queue",
            entity_id=queue_id,
            code=f"Queue with ID {queue_id} not found",
        )

    await validate_organization_access(str(queue.organization_id), user)

    jobs = await service.list_jobs(queue_id=queue_id)
    pending_count = sum(1 for j in jobs if j.status.value == "pending")

    return QueueStats(
        name=queue.name,
        length=pending_count,
        active_workers=queue.active_workers,
        max_workers=queue.max_concurrency,
        pending_jobs=pending_count,
        priority=0,
        created_at=queue.created_at or datetime.now(),
        updated_at=queue.updated_at or datetime.now(),
    )


@router.patch(
    "/{queue_id}",
    response_model=QueueResponse,
    summary="Update queue",
)
async def update_queue(
    queue_data: QueueUpdate,
    queue_id: UUID = Path(..., description="Queue ID"),
    service: QueueService = Depends(get_queue_service),
    user: CurrentUser = Depends(get_current_user),
) -> QueueResponse:
    """User must belong to queue's organization."""
    queue = await service.get_queue(queue_id)
    if not queue:
        raise EntityNotFoundError(
            entity_type="Queue",
            entity_id=queue_id,
            code=f"Queue with ID {queue_id} not found",
        )

    await validate_organization_access(str(queue.organization_id), user)

    command = QueueUpdateDTO(
        name=queue_data.name,
        description=queue_data.description,
        max_concurrency=queue_data.max_workers,
        max_pending_jobs=queue_data.max_jobs,
        default_timeout_seconds=queue_data.timeout,
        client_metadata=queue_data.config,
        updated_by=UUID(user["id"]),
    )

    result = await service.update_queue(queue_id, command)

    return QueueResponse(
        id=result.id,
        organization_id=result.organization_id,
        name=result.name,
        description=result.description,
        max_workers=result.max_concurrency,
        active_workers=result.active_workers,
        max_jobs=result.max_pending_jobs,
        pending_jobs=0,
        priority=queue_data.priority or 0,
        timeout=result.default_timeout_seconds,
        retry_limit=queue_data.retry_limit or settings.JOB_RETRY_LIMIT,
        config=result.client_metadata,
        metadata=result.client_metadata,
        created_at=result.created_at or datetime.now(),
        updated_at=result.updated_at or datetime.now(),
    )


@router.post(
    "/{queue_id}/pause",
    response_model=QueueResponse,
    summary="Pause queue",
)
async def pause_queue(
    queue_id: UUID = Path(..., description="Queue ID"),
    service: QueueService = Depends(get_queue_service),
    user: CurrentUser = Depends(get_current_user),
) -> QueueResponse:
    """Halt new job processing. User must belong to queue's org."""
    queue = await service.get_queue(queue_id)
    if not queue:
        raise EntityNotFoundError(
            entity_type="Queue",
            entity_id=queue_id,
            code=f"Queue with ID {queue_id} not found",
        )

    await validate_organization_access(str(queue.organization_id), user)

    result = await service.pause_queue(queue_id, paused_by=UUID(user["id"]))

    return QueueResponse(
        id=result.id,
        organization_id=result.organization_id,
        name=result.name,
        description=result.description,
        max_workers=result.max_concurrency,
        active_workers=result.active_workers,
        max_jobs=result.max_pending_jobs,
        pending_jobs=0,
        priority=0,
        timeout=result.default_timeout_seconds,
        retry_limit=settings.JOB_RETRY_LIMIT,
        config=result.client_metadata,
        metadata=result.client_metadata,
        created_at=result.created_at or datetime.now(),
        updated_at=result.updated_at or datetime.now(),
    )


@router.post(
    "/{queue_id}/resume",
    response_model=QueueResponse,
    summary="Resume queue",
)
async def resume_queue(
    queue_id: UUID = Path(..., description="Queue ID"),
    service: QueueService = Depends(get_queue_service),
    user: CurrentUser = Depends(get_current_user),
) -> QueueResponse:
    """User must belong to queue's organization."""
    queue = await service.get_queue(queue_id)
    if not queue:
        raise EntityNotFoundError(
            entity_type="Queue",
            entity_id=queue_id,
            code=f"Queue with ID {queue_id} not found",
        )

    await validate_organization_access(str(queue.organization_id), user)

    result = await service.resume_queue(queue_id, resumed_by=UUID(user["id"]))

    return QueueResponse(
        id=result.id,
        organization_id=result.organization_id,
        name=result.name,
        description=result.description,
        max_workers=result.max_concurrency,
        active_workers=result.active_workers,
        max_jobs=result.max_pending_jobs,
        pending_jobs=0,
        priority=0,
        timeout=result.default_timeout_seconds,
        retry_limit=settings.JOB_RETRY_LIMIT,
        config=result.client_metadata,
        metadata=result.client_metadata,
        created_at=result.created_at or datetime.now(),
        updated_at=result.updated_at or datetime.now(),
    )


@router.delete(
    "/{queue_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete queue",
)
async def delete_queue(
    queue_id: UUID = Path(..., description="Queue ID"),
    service: QueueService = Depends(get_queue_service),
    user: CurrentUser = Depends(get_current_user),
) -> None:
    """Deletes queue and all its jobs. User must belong to queue's org."""
    queue = await service.get_queue(queue_id)
    if not queue:
        raise EntityNotFoundError(
            entity_type="Queue",
            entity_id=queue_id,
            code=f"Queue with ID {queue_id} not found",
        )

    await validate_organization_access(str(queue.organization_id), user)

    try:
        success = await service.stop_queue(queue_id, stopped_by=UUID(user["id"]))
        if not success:
            raise EntityNotFoundError(
                entity_type="Queue",
                entity_id=queue_id,
                code=f"Queue with ID {queue_id} not found",
            )
    except AttributeError:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Queue deletion not yet implemented",
        )


@router.get(
    "/{queue_id}/jobs",
    response_model=list[QueuedJobResponseDTO],
    summary="List jobs in queue",
)
async def list_queue_jobs(
    queue_id: UUID = Path(..., description="Queue ID"),
    status_filter: Optional[str] = Query(
        None, alias="status", description="Status filter"
    ),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(settings.API_PAGE_LIMIT_DEFAULT, ge=1, le=1000, description="Maximum records to return"),
    service: QueueService = Depends(get_queue_service),
    user: CurrentUser = Depends(get_current_user),
) -> list[QueuedJobResponseDTO]:
    """User must belong to queue's organization."""
    queue = await service.get_queue(queue_id)
    if not queue:
        raise EntityNotFoundError(
            entity_type="Queue",
            entity_id=queue_id,
            code=f"Queue with ID {queue_id} not found",
        )

    await validate_organization_access(str(queue.organization_id), user)

    jobs = await service.list_jobs(
        queue_id=queue_id,
        status=status_filter,
        skip=skip,
        limit=limit,
    )

    return jobs
