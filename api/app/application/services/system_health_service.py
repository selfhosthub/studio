# api/app/application/services/system_health_service.py

"""
System health service - application-layer facade for infrastructure monitoring.

Absorbs raw DB queries from presentation/api/system_health.py so the
presentation layer no longer imports ORM models or calls session.execute().
"""

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import settings
from app.domain.instance_step.step_execution import StepExecutionStatus
from app.domain.instance.models import InstanceStatus
from app.infrastructure.persistence.models import (
    BlueprintModel,
    InstanceModel,
    StepExecutionModel,
    OrganizationModel,
    ProviderCredentialModel,
    ProviderModel,
    UserModel,
    WorkerModel,
    WorkflowModel,
)

logger = logging.getLogger(__name__)


def format_bytes(size_bytes: int) -> str:
    """Format bytes to human-readable string."""
    size: float = float(size_bytes)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024.0:
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} PB"


def format_uptime(seconds: int) -> str:
    """Format uptime seconds into human-readable string."""
    days, remainder = divmod(seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, _ = divmod(remainder, 60)

    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0 or not parts:
        parts.append(f"{minutes}m")
    return " ".join(parts)


def get_storage_stats() -> dict:
    """Calculate storage usage statistics from the filesystem."""
    import shutil

    storage_backend = settings.STORAGE_BACKEND
    workspace_path = settings.WORKSPACE_ROOT
    if not workspace_path:
        raise RuntimeError("WORKSPACE_ROOT environment variable is not set")
    workspace = Path(workspace_path)

    total_files = 0
    total_size = 0
    by_org: Dict[str, Dict[str, Any]] = {}

    capacity_bytes = None
    capacity_formatted = None
    capacity_used_percent = None

    try:
        if workspace.exists():
            disk_usage = shutil.disk_usage(workspace)
            capacity_bytes = disk_usage.total
            capacity_formatted = format_bytes(capacity_bytes)
            if disk_usage.total > 0:
                capacity_used_percent = round(
                    (disk_usage.used / disk_usage.total) * 100, 1
                )
    except Exception:
        pass

    orgs_dir = workspace / "orgs"
    if orgs_dir.exists():
        for org_dir in orgs_dir.iterdir():
            if org_dir.is_dir():
                org_id = org_dir.name
                org_files = 0
                org_size = 0

                resources_dir = org_dir / "resources"
                if resources_dir.exists():
                    for f in resources_dir.rglob("*"):
                        if f.is_file():
                            org_files += 1
                            org_size += f.stat().st_size

                if org_files > 0:
                    by_org[org_id] = {
                        "files": org_files,
                        "size_bytes": org_size,
                        "size_formatted": format_bytes(org_size),
                    }

                total_files += org_files
                total_size += org_size

    return {
        "backend": storage_backend,
        "total_files": total_files,
        "total_size_bytes": total_size,
        "total_size_formatted": format_bytes(total_size),
        "capacity_bytes": capacity_bytes,
        "capacity_formatted": capacity_formatted,
        "capacity_used_percent": capacity_used_percent,
        "workspace_path": str(workspace) if storage_backend == "local" else None,
        "by_organization": by_org,
    }


class SystemHealthService:
    """Application service for system health / infrastructure monitoring."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Job stats
    # ------------------------------------------------------------------

    async def get_job_stats(self) -> Dict[str, Any]:
        """Get job statistics from the database."""
        db = self._session
        stats: Dict[str, Any] = {
            "total_pending": 0,
            "total_running": 0,
            "total_completed": 0,
            "total_failed": 0,
            "long_running_jobs": [],
            "jobs_without_worker": [],
            "by_workflow": {},
        }

        try:
            # Counts by status
            status_counts = await db.execute(
                select(
                    StepExecutionModel.status, func.count(StepExecutionModel.id)
                ).group_by(StepExecutionModel.status)
            )
            for row in status_counts:
                s, count = row
                if s == StepExecutionStatus.PENDING:
                    stats["total_pending"] = count
                elif s == StepExecutionStatus.RUNNING:
                    stats["total_running"] = count
                elif s == StepExecutionStatus.COMPLETED:
                    stats["total_completed"] = count
                elif s == StepExecutionStatus.FAILED:
                    stats["total_failed"] = count

            # Long-running jobs (> 30 min)
            cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=30)
            long_running = await db.execute(
                select(
                    StepExecutionModel,
                    OrganizationModel.name,
                    OrganizationModel.slug,
                    InstanceModel.id,
                    WorkflowModel.name,
                )
                .join(
                    InstanceModel,
                    StepExecutionModel.instance_id == InstanceModel.id,
                )
                .join(WorkflowModel, InstanceModel.workflow_id == WorkflowModel.id)
                .join(
                    OrganizationModel,
                    InstanceModel.organization_id == OrganizationModel.id,
                )
                .where(
                    StepExecutionModel.status == StepExecutionStatus.RUNNING,
                    StepExecutionModel.started_at < cutoff_time,
                    StepExecutionModel.started_at.isnot(None),
                )
                .limit(20)
            )

            for row in long_running:
                job, org_name, org_slug, instance_id, workflow_name = row
                running_minutes = int(
                    (datetime.now(timezone.utc) - job.started_at).total_seconds() / 60
                )
                stats["long_running_jobs"].append(
                    {
                        "organization_name": org_name,
                        "organization_slug": org_slug,
                        "instance_id": str(instance_id),
                        "instance_name": workflow_name
                        or f"Instance {str(instance_id)[:8]}",
                        "step_id": job.step_key or "unknown",
                        "running_minutes": running_minutes,
                        "started_at": (
                            job.started_at.isoformat() if job.started_at else None
                        ),
                    }
                )

            # Stalled jobs (PENDING > 5 min)
            stall_cutoff = datetime.now(timezone.utc) - timedelta(minutes=5)
            stalled_jobs = await db.execute(
                select(
                    StepExecutionModel,
                    OrganizationModel.name,
                    OrganizationModel.slug,
                    InstanceModel.id,
                    WorkflowModel.name,
                )
                .join(
                    InstanceModel,
                    StepExecutionModel.instance_id == InstanceModel.id,
                )
                .join(WorkflowModel, InstanceModel.workflow_id == WorkflowModel.id)
                .join(
                    OrganizationModel,
                    InstanceModel.organization_id == OrganizationModel.id,
                )
                .where(
                    StepExecutionModel.status == StepExecutionStatus.PENDING,
                    StepExecutionModel.created_at < stall_cutoff,
                )
                .limit(20)
            )

            for row in stalled_jobs:
                job, org_name, org_slug, instance_id, workflow_name = row
                stats["jobs_without_worker"].append(
                    {
                        "organization_name": org_name,
                        "organization_slug": org_slug,
                        "instance_id": str(instance_id),
                        "instance_name": workflow_name
                        or f"Instance {str(instance_id)[:8]}",
                        "step_id": job.step_key or "unknown",
                        "enqueued_at": (
                            job.created_at.isoformat() if job.created_at else None
                        ),
                    }
                )

            # Jobs by workflow
            workflow_stats = await db.execute(
                select(
                    WorkflowModel.name,
                    StepExecutionModel.status,
                    func.count(StepExecutionModel.id),
                )
                .join(
                    InstanceModel,
                    StepExecutionModel.instance_id == InstanceModel.id,
                )
                .join(WorkflowModel, InstanceModel.workflow_id == WorkflowModel.id)
                .group_by(WorkflowModel.name, StepExecutionModel.status)
            )

            for row in workflow_stats:
                wf_name, s, count = row
                if wf_name not in stats["by_workflow"]:
                    stats["by_workflow"][wf_name] = {
                        "pending": 0,
                        "running": 0,
                        "completed": 0,
                        "failed": 0,
                    }
                if s == StepExecutionStatus.PENDING:
                    stats["by_workflow"][wf_name]["pending"] = count
                elif s == StepExecutionStatus.RUNNING:
                    stats["by_workflow"][wf_name]["running"] = count
                elif s == StepExecutionStatus.COMPLETED:
                    stats["by_workflow"][wf_name]["completed"] = count
                elif s == StepExecutionStatus.FAILED:
                    stats["by_workflow"][wf_name]["failed"] = count

        except Exception as e:
            logger.error(f"Error fetching job stats: {e}")

        return stats

    # ------------------------------------------------------------------
    # Worker stats
    # ------------------------------------------------------------------

    async def get_worker_stats(self) -> Dict[str, Any]:
        """Get worker heartbeat status from database."""
        db = self._session
        workers: List[Dict[str, Any]] = []
        online = 0
        offline = 0

        try:
            cutoff = datetime.now(timezone.utc) - timedelta(
                minutes=settings.WORKER_HEARTBEAT_TIMEOUT_MINUTES
            )
            result = await db.execute(select(WorkerModel))
            all_workers = result.scalars().all()

            for worker in all_workers:
                is_online = worker.last_heartbeat and worker.last_heartbeat > cutoff
                base = {
                    "worker_id": str(worker.id),
                    "name": worker.name,
                    "worker_status": (
                        worker.status.value if worker.status else "unknown"
                    ),
                    "queue_labels": worker.queue_labels or [],
                    "capabilities": worker.capabilities or {},
                    "jobs_completed": worker.jobs_completed or 0,
                    "ip_address": worker.ip_address,
                    "hostname": worker.hostname,
                    "cpu_percent": worker.cpu_percent,
                    "memory_percent": worker.memory_percent,
                    "memory_used_mb": worker.memory_used_mb,
                    "memory_total_mb": worker.memory_total_mb,
                    "disk_percent": worker.disk_percent,
                    "gpu_percent": worker.gpu_percent,
                    "gpu_memory_percent": worker.gpu_memory_percent,
                }

                if is_online and worker.last_heartbeat is not None:
                    online += 1
                    seconds_since = int(
                        (
                            datetime.now(timezone.utc) - worker.last_heartbeat
                        ).total_seconds()
                    )
                    base.update(
                        {
                            "status": "online",
                            "last_heartbeat_seconds_ago": seconds_since,
                            "current_job_id": (
                                str(worker.current_job_id)
                                if worker.current_job_id
                                else None
                            ),
                        }
                    )
                else:
                    offline += 1
                    base.update(
                        {
                            "status": "offline",
                            "last_heartbeat": (
                                worker.last_heartbeat.isoformat()
                                if worker.last_heartbeat
                                else None
                            ),
                        }
                    )

                workers.append(base)

        except Exception as e:
            logger.error(f"Error fetching worker stats: {e}")

        return {
            "total_registered": online + offline,
            "online": online,
            "offline": offline,
            "workers": workers,
        }

    # ------------------------------------------------------------------
    # Platform stats
    # ------------------------------------------------------------------

    async def get_platform_stats(self) -> Dict[str, Any]:
        """Get platform-wide statistics for super-admin dashboard."""
        db = self._session
        stats: Dict[str, Any] = {
            "total_organizations": 0,
            "active_users": 0,
            "running_instances": 0,
        }

        session_timeout_minutes = settings.ACCESS_TOKEN_EXPIRE_MINUTES

        try:
            org_count = await db.execute(
                select(func.count(OrganizationModel.id)).where(
                    OrganizationModel.slug != "system"
                )
            )
            stats["total_organizations"] = org_count.scalar() or 0

            cutoff = datetime.now(timezone.utc) - timedelta(
                minutes=session_timeout_minutes
            )
            active_users = await db.execute(
                select(func.count(UserModel.id)).where(
                    UserModel.is_active == True,
                    UserModel.last_login.isnot(None),
                    UserModel.last_login >= cutoff,
                )
            )
            stats["active_users"] = active_users.scalar() or 0

            running_instances = await db.execute(
                select(func.count(InstanceModel.id)).where(
                    InstanceModel.status.in_(
                        [InstanceStatus.PROCESSING, InstanceStatus.PENDING]
                    )
                )
            )
            stats["running_instances"] = running_instances.scalar() or 0

        except Exception as e:
            logger.error(f"Error fetching platform stats: {e}")

        return stats

    # ------------------------------------------------------------------
    # Database stats
    # ------------------------------------------------------------------

    async def get_database_stats(self) -> Dict[str, Any]:
        """Get PostgreSQL database statistics for infrastructure monitoring."""
        db = self._session
        stats: Dict[str, Any] = {
            "healthy": True,
            "status": "healthy",
            "version": None,
            "uptime": None,
            "uptime_seconds": None,
            "active_connections": 0,
            "max_connections": 0,
            "connection_usage_percent": None,
            "database_size": None,
            "database_size_bytes": None,
            "total_organizations": 0,
            "total_users": 0,
            "total_workflows": 0,
            "total_blueprints": 0,
            "total_instances": 0,
            "total_providers": 0,
            "total_credentials": 0,
            "slow_queries": 0,
            "cache_hit_ratio": None,
        }
        health_issues: List[str] = []

        try:
            # PostgreSQL version
            result = await db.execute(text("SELECT version()"))
            version_str = result.scalar()
            if version_str:
                stats["version"] = version_str.split(",")[0] if version_str else None

            # Server uptime
            uptime_result = await db.execute(
                text(
                    "SELECT EXTRACT(EPOCH FROM (now() - pg_postmaster_start_time()))::integer"
                )
            )
            uptime_seconds = uptime_result.scalar()
            if uptime_seconds:
                stats["uptime_seconds"] = uptime_seconds
                stats["uptime"] = format_uptime(uptime_seconds)

            # Connection stats
            conn_result = await db.execute(text("""
                SELECT
                    (SELECT count(*) FROM pg_stat_activity) as active,
                    (SELECT setting::int FROM pg_settings WHERE name = 'max_connections') as max_conn
            """))
            conn_row = conn_result.fetchone()
            if conn_row:
                stats["active_connections"] = conn_row[0] or 0
                stats["max_connections"] = conn_row[1] or 100
                if stats["max_connections"] > 0:
                    stats["connection_usage_percent"] = round(
                        (stats["active_connections"] / stats["max_connections"]) * 100,
                        1,
                    )
                    if stats["connection_usage_percent"] > 80:
                        health_issues.append("high_connections")

            # Database size
            size_result = await db.execute(
                text("SELECT pg_database_size(current_database())")
            )
            size_bytes = size_result.scalar()
            if size_bytes:
                stats["database_size_bytes"] = size_bytes
                stats["database_size"] = format_bytes(size_bytes)

            # Cache hit ratio
            cache_result = await db.execute(text("""
                SELECT
                    CASE
                        WHEN blks_hit + blks_read = 0 THEN 100
                        ELSE round((blks_hit::numeric / (blks_hit + blks_read)) * 100, 2)
                    END as ratio
                FROM pg_stat_database
                WHERE datname = current_database()
            """))
            cache_ratio = cache_result.scalar()
            if cache_ratio is not None:
                stats["cache_hit_ratio"] = float(cache_ratio)
                if stats["cache_hit_ratio"] < 90:
                    health_issues.append("low_cache_hit")

            # Slow queries
            try:
                slow_result = await db.execute(text("""
                    SELECT count(*)
                    FROM pg_stat_activity
                    WHERE state = 'active'
                    AND query_start < now() - interval '1 second'
                    AND query NOT LIKE '%pg_stat_activity%'
                """))
                stats["slow_queries"] = slow_result.scalar() or 0
                if stats["slow_queries"] > 5:
                    health_issues.append("slow_queries")
            except Exception:
                pass

            # Record counts
            org_count = await db.execute(
                select(func.count(OrganizationModel.id)).where(
                    OrganizationModel.slug != "system"
                )
            )
            stats["total_organizations"] = org_count.scalar() or 0

            user_count = await db.execute(select(func.count(UserModel.id)))
            stats["total_users"] = user_count.scalar() or 0

            workflow_count = await db.execute(select(func.count(WorkflowModel.id)))
            stats["total_workflows"] = workflow_count.scalar() or 0

            blueprint_count = await db.execute(select(func.count(BlueprintModel.id)))
            stats["total_blueprints"] = blueprint_count.scalar() or 0

            instance_count = await db.execute(select(func.count(InstanceModel.id)))
            stats["total_instances"] = instance_count.scalar() or 0

            provider_count = await db.execute(select(func.count(ProviderModel.id)))
            stats["total_providers"] = provider_count.scalar() or 0

            credential_count = await db.execute(
                select(func.count(ProviderCredentialModel.id))
            )
            stats["total_credentials"] = credential_count.scalar() or 0

            # Overall health
            if not health_issues:
                stats["healthy"] = True
                stats["status"] = "healthy"
            elif len(health_issues) == 1:
                stats["healthy"] = True
                stats["status"] = "degraded"
            else:
                stats["healthy"] = False
                stats["status"] = "unhealthy"

        except Exception as e:
            logger.error(f"Error fetching database stats: {e}")
            stats["healthy"] = False
            stats["status"] = "unhealthy"

        return stats

    # ------------------------------------------------------------------
    # Paginated organization storage
    # ------------------------------------------------------------------

    async def get_paginated_org_storage(
        self,
        page: int,
        per_page: int,
        sort_by: str,
        sort_order: str,
    ) -> Dict[str, Any]:
        """Get paginated storage usage per organization with limits."""
        db = self._session
        workspace_path = settings.WORKSPACE_ROOT
        if not workspace_path:
            raise RuntimeError("WORKSPACE_ROOT environment variable is not set")
        workspace = Path(workspace_path)
        orgs_dir = workspace / "orgs"

        # Get storage data from filesystem
        storage_by_org: Dict[str, Dict[str, Any]] = {}
        total_files = 0
        total_size = 0

        if orgs_dir.exists():
            for org_dir in orgs_dir.iterdir():
                if org_dir.is_dir():
                    org_id = org_dir.name
                    org_files = 0
                    org_size = 0

                    resources_dir = org_dir / "resources"
                    if resources_dir.exists():
                        for f in resources_dir.rglob("*"):
                            if f.is_file():
                                org_files += 1
                                org_size += f.stat().st_size

                    storage_by_org[org_id] = {
                        "files": org_files,
                        "size_bytes": org_size,
                    }
                    total_files += org_files
                    total_size += org_size

        # Query ALL organizations from database (excluding system org)
        result = await db.execute(
            select(OrganizationModel).where(OrganizationModel.slug != "system")
        )

        items: List[Dict[str, Any]] = []
        for org in result.scalars():
            org_id = str(org.id)
            storage = storage_by_org.get(org_id, {"files": 0, "size_bytes": 0})

            items.append(
                {
                    "organization_id": org_id,
                    "organization_name": org.name,
                    "organization_slug": org.slug,
                    "files": storage["files"],
                    "size_bytes": storage["size_bytes"],
                    "size_formatted": format_bytes(storage["size_bytes"]),
                    "storage_limit_bytes": None,
                    "storage_limit_formatted": None,
                    "usage_percent": None,
                }
            )

        # Sort
        reverse = sort_order.lower() == "desc"
        if sort_by == "name":
            items.sort(key=lambda x: x["organization_name"].lower(), reverse=reverse)
        elif sort_by == "files":
            items.sort(key=lambda x: x["files"], reverse=reverse)
        elif sort_by == "usage_percent":
            items.sort(
                key=lambda x: (
                    x["usage_percent"] is None,
                    x["usage_percent"] or 0,
                ),
                reverse=reverse,
            )
        else:
            items.sort(key=lambda x: x["size_bytes"], reverse=reverse)

        # Paginate
        total = len(items)
        total_pages = (total + per_page - 1) // per_page
        start = (page - 1) * per_page
        end = start + per_page
        paginated_items = items[start:end]

        return {
            "items": paginated_items,
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": total_pages,
            "total_size_bytes": total_size,
            "total_size_formatted": format_bytes(total_size),
            "total_files": total_files,
        }

    # ------------------------------------------------------------------
    # Worker deregistration
    # ------------------------------------------------------------------

    async def deregister_worker(self, worker_id: str) -> Dict[str, Any]:
        """Deregister a worker from the system.

        Returns dict with status and message, or raises ValueError/LookupError.
        """
        from uuid import UUID as UUIDType

        try:
            uuid_id = UUIDType(worker_id)
        except ValueError:
            raise ValueError("Invalid worker ID format")

        result = await self._session.execute(
            select(WorkerModel).where(WorkerModel.id == uuid_id)
        )
        worker = result.scalar_one_or_none()

        if not worker:
            raise LookupError(f"Worker {worker_id} not found")

        worker_name = worker.name
        logger.info(f"Deregistering worker: {worker_name} ({worker_id})")

        await self._session.delete(worker)
        await self._session.commit()

        logger.info(f"Worker {worker_name} deregistered successfully")
        return {
            "status": "ok",
            "message": f"Worker {worker_name} deregistered successfully",
        }
