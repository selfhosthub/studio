# api/app/infrastructure/repositories/worker_repository.py

"""SQLAlchemy implementation of Worker repository."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.common.exceptions import EntityNotFoundError
from app.domain.queue.models import Worker
from app.domain.queue.repository import WorkerRepository
from app.config.settings import settings
from app.infrastructure.persistence.models import WorkerModel


class SQLAlchemyWorkerRepository(WorkerRepository):
    """SQLAlchemy implementation of worker repository."""

    def __init__(self, session: AsyncSession):
        self.session = session

    def _to_domain(self, model: WorkerModel) -> Worker:
        return Worker(
            id=model.id,
            name=model.name,
            queue_id=model.queue_id,
            status=model.status,
            capabilities=model.capabilities,
            queue_labels=model.queue_labels,
            last_heartbeat=model.last_heartbeat,
            current_job_id=model.current_job_id,
            jobs_completed=model.jobs_completed,
            is_deregistered=model.is_deregistered,
            ip_address=model.ip_address,
            hostname=model.hostname,
            cpu_percent=model.cpu_percent,
            memory_percent=model.memory_percent,
            memory_used_mb=model.memory_used_mb,
            memory_total_mb=model.memory_total_mb,
            disk_percent=model.disk_percent,
            gpu_percent=model.gpu_percent,
            gpu_memory_percent=model.gpu_memory_percent,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    async def create(self, worker: Worker) -> Worker:
        db_worker = WorkerModel(
            id=worker.id,
            name=worker.name,
            queue_id=worker.queue_id,
            status=worker.status,  # type: ignore[assignment]  - domain value assigned to SA column; SA type stubs expect Column type
            capabilities=worker.capabilities,
            queue_labels=worker.queue_labels,
            last_heartbeat=worker.last_heartbeat,  # type: ignore[assignment]  - domain value assigned to SA column; SA type stubs expect Column type
            current_job_id=worker.current_job_id,  # type: ignore[assignment]  - domain value assigned to SA column; SA type stubs expect Column type
            jobs_completed=worker.jobs_completed,
            is_deregistered=worker.is_deregistered,
            ip_address=worker.ip_address,
            hostname=worker.hostname,
            cpu_percent=worker.cpu_percent,
            memory_percent=worker.memory_percent,
            memory_used_mb=worker.memory_used_mb,
            memory_total_mb=worker.memory_total_mb,
            disk_percent=worker.disk_percent,
            gpu_percent=worker.gpu_percent,
            gpu_memory_percent=worker.gpu_memory_percent,
            created_at=worker.created_at,
            updated_at=worker.updated_at,  # type: ignore[assignment]  - domain value assigned to SA column; SA type stubs expect Column type
        )

        self.session.add(db_worker)
        await self.session.commit()
        await self.session.refresh(db_worker)

        return self._to_domain(db_worker)

    async def update(self, worker: Worker) -> Worker:
        result = await self.session.execute(
            select(WorkerModel).where(WorkerModel.id == worker.id)
        )
        db_worker = result.scalars().first()

        if not db_worker:
            raise EntityNotFoundError(entity_type="Worker", entity_id=worker.id)

        db_worker.name = worker.name
        db_worker.queue_id = worker.queue_id
        db_worker.status = worker.status  # type: ignore[assignment]  - domain value assigned to SA column; SA type stubs expect Column type
        db_worker.capabilities = worker.capabilities
        db_worker.queue_labels = worker.queue_labels
        db_worker.last_heartbeat = worker.last_heartbeat  # type: ignore[assignment]  - domain value assigned to SA column; SA type stubs expect Column type
        db_worker.current_job_id = worker.current_job_id  # type: ignore[assignment]  - domain value assigned to SA column; SA type stubs expect Column type
        db_worker.jobs_completed = worker.jobs_completed
        db_worker.is_deregistered = worker.is_deregistered
        db_worker.ip_address = worker.ip_address
        db_worker.hostname = worker.hostname
        db_worker.cpu_percent = worker.cpu_percent
        db_worker.memory_percent = worker.memory_percent
        db_worker.memory_used_mb = worker.memory_used_mb
        db_worker.memory_total_mb = worker.memory_total_mb
        db_worker.disk_percent = worker.disk_percent
        db_worker.gpu_percent = worker.gpu_percent
        db_worker.gpu_memory_percent = worker.gpu_memory_percent
        db_worker.updated_at = worker.updated_at  # type: ignore[assignment]  - domain value assigned to SA column; SA type stubs expect Column type

        await self.session.commit()
        await self.session.refresh(db_worker)

        return self._to_domain(db_worker)

    async def get_by_id(self, worker_id: uuid.UUID) -> Optional[Worker]:
        result = await self.session.execute(
            select(WorkerModel).where(WorkerModel.id == worker_id)
        )
        db_worker = result.scalars().first()

        if not db_worker:
            return None

        return self._to_domain(db_worker)

    async def list_by_queue(
        self,
        queue_id: uuid.UUID,
        skip: int,
        limit: int,
    ) -> List[Worker]:
        stmt = select(WorkerModel).where(WorkerModel.queue_id == queue_id)

        stmt = stmt.offset(skip).limit(limit)

        result = await self.session.execute(stmt)
        db_workers = result.scalars().all()

        return [self._to_domain(w) for w in db_workers]

    async def list_active_workers(
        self, skip: int, limit: int, queue_id: Optional[uuid.UUID] = None
    ) -> List[Worker]:
        cutoff = datetime.now(UTC) - timedelta(minutes=settings.WORKER_HEARTBEAT_TIMEOUT_MINUTES)
        stmt = select(WorkerModel).where(WorkerModel.last_heartbeat > cutoff)

        stmt = stmt.offset(skip).limit(limit)

        if queue_id:
            stmt = stmt.where(WorkerModel.queue_id == queue_id)

        result = await self.session.execute(stmt)
        db_workers = result.scalars().all()

        return [self._to_domain(w) for w in db_workers]

    async def delete(self, worker_id: uuid.UUID) -> bool:
        result = await self.session.execute(
            select(WorkerModel).where(WorkerModel.id == worker_id)
        )
        db_worker = result.scalars().first()

        if not db_worker:
            return False

        await self.session.delete(db_worker)
        await self.session.commit()

        return True

    async def exists(self, worker_id: uuid.UUID) -> bool:
        result = await self.session.execute(
            select(WorkerModel.id).where(WorkerModel.id == worker_id)
        )
        return result.scalars().first() is not None

    async def count_active_workers_for_queue(
        self,
        queue_name: str,
        heartbeat_timeout_minutes: int = settings.WORKER_HEARTBEAT_TIMEOUT_MINUTES,
    ) -> int:
        from sqlalchemy import func

        cutoff = datetime.now(UTC) - timedelta(minutes=heartbeat_timeout_minutes)

        # PostgreSQL array contains operator
        # queue_labels @> ARRAY['video_jobs']
        stmt = (
            select(func.count(WorkerModel.id))
            .where(WorkerModel.last_heartbeat > cutoff)
            .where(WorkerModel.is_deregistered == False)  # noqa: E712 - SQLAlchemy requires == True/False for column comparison; Python equality operator is intentional
            .where(WorkerModel.queue_labels.contains([queue_name]))
        )

        result = await self.session.execute(stmt)
        count = result.scalar() or 0
        return count

    async def get_stale_workers(
        self,
        heartbeat_timeout_minutes: int = settings.WORKER_HEARTBEAT_TIMEOUT_MINUTES,
    ) -> List[Worker]:
        from sqlalchemy import or_

        cutoff = datetime.now(UTC) - timedelta(minutes=heartbeat_timeout_minutes)

        stmt = (
            select(WorkerModel)
            .where(
                or_(
                    WorkerModel.last_heartbeat < cutoff,
                    WorkerModel.last_heartbeat.is_(None),
                )
            )
            .where(WorkerModel.is_deregistered == False)  # noqa: E712 - SQLAlchemy requires == True/False for column comparison; Python equality operator is intentional
        )

        result = await self.session.execute(stmt)
        db_workers = result.scalars().all()

        return [self._to_domain(w) for w in db_workers]

    async def mark_workers_as_deregistered(
        self,
        worker_ids: List[uuid.UUID],
    ) -> int:
        from sqlalchemy import update

        if not worker_ids:
            return 0

        stmt = (
            update(WorkerModel)
            .where(WorkerModel.id.in_(worker_ids))
            .values(is_deregistered=True, updated_at=datetime.now(UTC))
        )

        result = await self.session.execute(stmt)
        await self.session.commit()

        return result.rowcount or 0
