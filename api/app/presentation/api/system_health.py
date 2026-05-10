# api/app/presentation/api/system_health.py

"""System health, storage, worker, and maintenance-mode endpoints. Super-admin only."""

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from app.config.settings import settings
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from app.application.services.system_health_service import (
    SystemHealthService,
    get_storage_stats,
)
from app.presentation.api.dependencies import (
    CurrentUser,
    get_current_user,
    get_system_health_service,
)
from app.infrastructure.maintenance import state as maintenance_state
from app.infrastructure.messaging.pg_notify import notify_global
from app.presentation.websockets.manager import manager as ws_manager

router = APIRouter(prefix="/infrastructure/health", tags=["Infrastructure"])

from app.domain.common.value_objects import Role
from app.infrastructure.auth.jwt import RoleChecker
from app.infrastructure.errors import safe_error_message

require_super_admin = RoleChecker([Role.SUPER_ADMIN])


class JobStats(BaseModel):
    total_pending: int = 0
    total_running: int = 0
    total_completed: int = 0
    total_failed: int = 0
    long_running_jobs: list[dict[str, Any]] = []  # running > 30 min
    jobs_without_worker: list[dict[str, Any]] = []  # pending > 5 min
    by_workflow: dict[str, dict[str, int]] = {}


class WebSocketStats(BaseModel):
    total_connections: int = 0
    organizations_connected: int = 0  # distinct orgs with active WS
    users_connected: int = 0  # distinct users with active WS


class StorageStats(BaseModel):
    backend: str
    total_files: int
    total_size_bytes: int
    total_size_formatted: str
    capacity_bytes: Optional[int] = None
    capacity_formatted: Optional[str] = None
    capacity_used_percent: Optional[float] = None
    workspace_path: Optional[str] = None
    by_organization: dict[str, dict[str, Any]] = {}


class WorkerStats(BaseModel):
    total_registered: int
    online: int
    offline: int
    workers: list[dict[str, Any]] = []


class PlatformStats(BaseModel):
    """Super-admin dashboard counters."""

    total_organizations: int = 0
    active_users: int = 0  # last_login within session timeout
    running_instances: int = 0


class DatabaseStats(BaseModel):
    healthy: bool = True
    status: str = "healthy"  # healthy | degraded | unhealthy

    version: Optional[str] = None
    uptime: Optional[str] = None
    uptime_seconds: Optional[int] = None

    active_connections: int = 0
    max_connections: int = 0
    connection_usage_percent: Optional[float] = None

    database_size: Optional[str] = None
    database_size_bytes: Optional[int] = None

    total_organizations: int = 0
    total_users: int = 0
    total_workflows: int = 0
    total_blueprints: int = 0
    total_instances: int = 0
    total_providers: int = 0
    total_credentials: int = 0

    slow_queries: int = 0  # > 1s in last hour
    cache_hit_ratio: Optional[float] = None


class OrganizationStorageItem(BaseModel):
    """Storage stats for one organization."""

    organization_id: str
    organization_name: str
    organization_slug: str
    files: int
    size_bytes: int
    size_formatted: str
    storage_limit_bytes: Optional[int] = None
    storage_limit_formatted: Optional[str] = None
    usage_percent: Optional[float] = None


class PaginatedStorageResponse(BaseModel):
    items: list[OrganizationStorageItem]
    total: int
    page: int
    per_page: int
    total_pages: int
    total_size_bytes: int
    total_size_formatted: str
    total_files: int


class SystemHealthResponse(BaseModel):
    timestamp: datetime
    websocket: WebSocketStats
    job_stats: Optional[JobStats] = None
    storage: StorageStats
    workers: WorkerStats
    database_connected: bool
    platform: Optional[PlatformStats] = None


def get_websocket_stats() -> WebSocketStats:
    return WebSocketStats(
        total_connections=len(ws_manager.active_connections),
        organizations_connected=len(ws_manager.org_connections),
        users_connected=len(ws_manager.user_connections),
    )


def get_queue_status_message(db_pending: int, db_running: int) -> str:
    if db_pending == 0 and db_running == 0:
        return "No active jobs"
    return f"{db_pending} pending, {db_running} running"


@router.get(
    "",
    response_model=SystemHealthResponse,
    summary="Get system health status",
    description="Get comprehensive system health including WebSocket, storage, and worker status. Super-admin only.",
)
async def get_system_health(
    user: CurrentUser = Depends(get_current_user),
    _: None = Depends(require_super_admin),
    service: SystemHealthService = Depends(get_system_health_service),
) -> SystemHealthResponse:
    """Combined snapshot: websocket, jobs, storage, workers, database, platform."""
    job_data = await service.get_job_stats()
    worker_data = await service.get_worker_stats()
    platform_data = await service.get_platform_stats()

    return SystemHealthResponse(
        timestamp=datetime.now(timezone.utc),
        websocket=get_websocket_stats(),
        job_stats=JobStats(**job_data),
        storage=StorageStats(**get_storage_stats()),
        workers=WorkerStats(**worker_data),
        database_connected=True,
        platform=PlatformStats(**platform_data),
    )


@router.get(
    "/storage",
    response_model=StorageStats,
    summary="Get storage statistics",
    description="Get storage usage statistics across organizations. Super-admin only.",
)
async def get_storage_health(
    user: CurrentUser = Depends(get_current_user),
    _: None = Depends(require_super_admin),
) -> StorageStats:
    return StorageStats(**get_storage_stats())


@router.get(
    "/workers",
    response_model=WorkerStats,
    summary="Get worker status",
    description="Get worker heartbeat status. Super-admin only.",
)
async def get_workers_health(
    user: CurrentUser = Depends(get_current_user),
    _: None = Depends(require_super_admin),
    service: SystemHealthService = Depends(get_system_health_service),
) -> WorkerStats:
    data = await service.get_worker_stats()
    return WorkerStats(**data)


@router.get(
    "/database",
    response_model=DatabaseStats,
    summary="Get database statistics",
    description="Get PostgreSQL database statistics including health metrics. Super-admin only.",
)
async def get_database_stats_endpoint(
    user: CurrentUser = Depends(get_current_user),
    _: None = Depends(require_super_admin),
    service: SystemHealthService = Depends(get_system_health_service),
) -> DatabaseStats:
    data = await service.get_database_stats()
    return DatabaseStats(**data)


@router.get(
    "/storage/organizations",
    response_model=PaginatedStorageResponse,
    summary="Get paginated organization storage",
    description="Get storage usage per organization with pagination. Super-admin only.",
)
async def get_paginated_storage(
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(settings.SYSTEM_HEALTH_DEFAULT_PAGE, ge=1, le=settings.SYSTEM_HEALTH_MAX_PAGE, description="Items per page"),
    sort_by: str = Query(
        "size_bytes",
        description="Field to sort by: name, files, size_bytes, usage_percent",
    ),
    sort_order: str = Query("desc", description="Sort order: asc or desc"),
    user: CurrentUser = Depends(get_current_user),
    _: None = Depends(require_super_admin),
    service: SystemHealthService = Depends(get_system_health_service),
) -> PaginatedStorageResponse:
    data = await service.get_paginated_org_storage(
        page=page, per_page=per_page, sort_by=sort_by, sort_order=sort_order
    )
    data["items"] = [OrganizationStorageItem(**item) for item in data["items"]]
    return PaginatedStorageResponse(**data)


class WorkerDeregisterResponse(BaseModel):
    status: str
    message: str


@router.post(
    "/workers/{worker_id}/deregister",
    response_model=WorkerDeregisterResponse,
    summary="Deregister a worker",
    description="Remove a worker from the system. Super-admin only.",
)
async def deregister_worker(
    worker_id: str,
    user: CurrentUser = Depends(get_current_user),
    _: None = Depends(require_super_admin),
    service: SystemHealthService = Depends(get_system_health_service),
) -> WorkerDeregisterResponse:
    try:
        result = await service.deregister_worker(worker_id)
        return WorkerDeregisterResponse(**result)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=safe_error_message(e)
        )
    except LookupError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=safe_error_message(e)
        )


class MaintenanceStatusResponse(BaseModel):
    """Maintenance mode status."""

    maintenance_mode: bool  # site is down
    warning_mode: bool = False  # countdown warning active
    warning_until: Optional[str] = None  # ISO timestamp when maintenance starts
    reason: Optional[str] = None
    started_at: Optional[str] = None


class MaintenanceModeRequest(BaseModel):
    reason: Optional[str] = "Scheduled maintenance"


class MaintenanceWarningRequest(BaseModel):
    minutes: int = 5
    reason: Optional[str] = "Scheduled maintenance"


async def get_maintenance_status() -> MaintenanceStatusResponse:
    result = await maintenance_state.get_maintenance_status()
    return MaintenanceStatusResponse(
        maintenance_mode=result.maintenance_mode,
        warning_mode=result.warning_mode,
        warning_until=result.warning_until,
        reason=result.reason,
        started_at=result.started_at,
    )


async def set_maintenance_mode(enabled: bool, reason: Optional[str] = None) -> bool:
    return await maintenance_state.set_maintenance_mode(enabled=enabled, reason=reason)


async def set_maintenance_warning(minutes: int, reason: Optional[str] = None) -> bool:
    return await maintenance_state.set_maintenance_warning(minutes=minutes, reason=reason)


async def broadcast_maintenance_event(
    mode: str,
    reason: Optional[str] = None,
    warning_until: Optional[str] = None,
) -> None:
    """Broadcast maintenance status change to all connected WebSocket clients via pg_notify."""
    await notify_global(
        {
            "event_type": "maintenance",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": {
                "mode": mode,
                "reason": reason,
                "warning_until": warning_until,
            },
        }
    )


@router.get(
    "/maintenance",
    response_model=MaintenanceStatusResponse,
    summary="Get maintenance mode status",
    description="Check if the system is in maintenance mode. Super-admin only.",
)
async def get_maintenance_mode_status(
    user: CurrentUser = Depends(get_current_user),
    _: None = Depends(require_super_admin),
) -> MaintenanceStatusResponse:
    return await get_maintenance_status()


@router.post(
    "/maintenance/warn",
    response_model=MaintenanceStatusResponse,
    summary="Enable maintenance warning",
    description="Start countdown to maintenance mode. Users see a warning banner. Super-admin only.",
)
async def enable_maintenance_warning(
    request: MaintenanceWarningRequest,
    user: CurrentUser = Depends(get_current_user),
    _: None = Depends(require_super_admin),
) -> MaintenanceStatusResponse:
    """Start countdown to maintenance. Users see a warning banner."""
    import logging

    logger = logging.getLogger(__name__)

    if request.minutes < 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Warning time must be at least 1 minute",
        )

    success = await set_maintenance_warning(minutes=request.minutes, reason=request.reason)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to enable maintenance warning",
        )

    logger.info(
        f"Maintenance WARNING enabled by {user.get('email')}. "
        f"Maintenance starts in {request.minutes} minutes. Reason: {request.reason}"
    )

    warning_until = (
        datetime.now(timezone.utc) + timedelta(minutes=request.minutes)
    ).isoformat()
    await broadcast_maintenance_event(
        mode="warning",
        reason=request.reason,
        warning_until=warning_until,
    )

    return await get_maintenance_status()


@router.post(
    "/maintenance/enable",
    response_model=MaintenanceStatusResponse,
    summary="Enable maintenance mode",
    description="Put the system into maintenance mode immediately. Super-admin only.",
)
async def enable_maintenance_mode(
    request: MaintenanceModeRequest,
    user: CurrentUser = Depends(get_current_user),
    _: None = Depends(require_super_admin),
) -> MaintenanceStatusResponse:
    import logging

    logger = logging.getLogger(__name__)

    success = await set_maintenance_mode(enabled=True, reason=request.reason)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to enable maintenance mode",
        )

    logger.info(
        f"Maintenance mode ENABLED by {user.get('email')}. Reason: {request.reason}"
    )

    await broadcast_maintenance_event(mode="enabled", reason=request.reason)

    return await get_maintenance_status()


@router.post(
    "/maintenance/disable",
    response_model=MaintenanceStatusResponse,
    summary="Disable maintenance mode",
    description="Take the system out of maintenance mode. Super-admin only.",
)
async def disable_maintenance_mode(
    user: CurrentUser = Depends(get_current_user),
    _: None = Depends(require_super_admin),
) -> MaintenanceStatusResponse:
    import logging

    logger = logging.getLogger(__name__)

    success = await set_maintenance_mode(enabled=False)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to disable maintenance mode",
        )

    logger.info(f"Maintenance mode DISABLED by {user.get('email')}")

    await broadcast_maintenance_event(mode="disabled")

    return await get_maintenance_status()
