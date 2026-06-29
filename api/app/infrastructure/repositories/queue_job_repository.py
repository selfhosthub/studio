# api/app/infrastructure/repositories/queue_job_repository.py

"""SQLAlchemy implementation of QueuedJob repository."""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Dict, List, Optional


@dataclass
class OrphanedJobResult:
    requeued: int
    failed: int
    requeued_step_ids: list[uuid.UUID] = field(default_factory=list)
    failed_step_ids: list[uuid.UUID] = field(default_factory=list)


from sqlalchemy import delete as delete_stmt, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import settings
from app.domain.common.exceptions import EntityNotFoundError
from app.domain.common.value_objects import ResourceRequirements
from app.domain.instance_step.models import StepExecutionStatus
from app.domain.queue.models import QueuedJob
from app.domain.queue.repository import QueuedJobRepository
from app.infrastructure.persistence.models import QueuedJobModel


class SQLAlchemyQueuedJobRepository(QueuedJobRepository):
    """SQLAlchemy implementation of queued job repository."""

    def __init__(self, session: AsyncSession):
        self.session = session

    def _to_domain(self, model: QueuedJobModel) -> QueuedJob:
        resource_req = None
        if model.resource_requirements:
            try:
                resource_req = ResourceRequirements(**model.resource_requirements)
            except (TypeError, ValueError):
                resource_req = None

        return QueuedJob(
            id=model.id,
            organization_id=model.organization_id,
            enqueued_by=model.enqueued_by,
            queue_name=model.queue_name,  # For worker polling
            instance_id=model.instance_id,
            priority=model.priority,
            status=model.status,
            input_data=model.payload,
            output_data=model.output_data,  # Now a proper column
            error_message=model.error_message,  # Now a proper column
            resource_requirements=resource_req,
            timeout_seconds=(
                int((model.timeout_at - model.enqueued_at).total_seconds())
                if model.timeout_at
                else None
            ),
            worker_id=model.worker_id,
            enqueued_at=model.enqueued_at,
            assigned_at=model.assigned_at,  # Now a proper column
            started_at=model.started_at,
            completed_at=model.completed_at,
            failed_at=model.failed_at,  # Now a proper column
            retry_count=model.retry_count,
            max_retries=model.max_retries,
            tags=model.tags,
            client_metadata=model.client_metadata,  # Purely user-provided data
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    async def create(self, job: QueuedJob) -> QueuedJob:
        """
        Create a new queued job.

        Args:
            job: The queued job to create

        Returns:
            The created queued job
        """
        timeout_at = None
        if job.timeout_seconds:
            timeout_at = job.enqueued_at + timedelta(seconds=job.timeout_seconds)

        db_job = QueuedJobModel(
            id=job.id,
            organization_id=job.organization_id,
            enqueued_by=job.enqueued_by,
            queue_name=job.queue_name,  # For worker polling
            job_id=None,
            instance_id=job.instance_id,
            priority=job.priority,
            status=job.status,  # type: ignore[assignment]  - domain enum assigned to SA column; SA type stubs expect Column type
            payload=job.input_data,
            resource_requirements=(
                job.resource_requirements.model_dump()
                if job.resource_requirements
                else None
            ),
            worker_id=job.worker_id,
            enqueued_at=job.enqueued_at,
            started_at=job.started_at,
            completed_at=job.completed_at,
            timeout_at=timeout_at,
            retry_count=job.retry_count,
            max_retries=job.max_retries,
            tags=job.tags,
            # Domain fields now as proper columns
            output_data=job.output_data,
            error_message=job.error_message,
            assigned_at=job.assigned_at,
            failed_at=job.failed_at,
            # User-provided metadata only
            client_metadata=job.client_metadata,
            created_at=job.created_at,
            updated_at=job.updated_at or datetime.now(UTC),  # type: ignore[assignment]  - domain datetime assigned to SA column; SA type stubs expect Column type
        )

        self.session.add(db_job)
        await self.session.commit()
        await self.session.refresh(db_job)

        return self._to_domain(db_job)

    async def update(self, job: QueuedJob) -> QueuedJob:
        """
        Update an existing queued job.

        Args:
            job: The queued job with updated fields

        Returns:
            The updated queued job

        Raises:
            EntityNotFoundError: If the job doesn't exist
        """
        result = await self.session.execute(
            select(QueuedJobModel).where(QueuedJobModel.id == job.id)
        )
        db_job = result.scalars().first()

        if not db_job:
            raise EntityNotFoundError("QueuedJob", job.id)

        db_job.status = job.status  # type: ignore[assignment]  - domain enum assigned to SA column; SA type stubs expect Column type
        db_job.priority = job.priority
        db_job.worker_id = job.worker_id
        db_job.started_at = job.started_at
        db_job.completed_at = job.completed_at
        db_job.retry_count = job.retry_count

        db_job.payload = job.input_data

        if job.timeout_seconds:
            db_job.timeout_at = job.enqueued_at + timedelta(seconds=job.timeout_seconds)

        # Domain fields now as proper columns
        db_job.output_data = job.output_data
        db_job.error_message = job.error_message
        db_job.assigned_at = job.assigned_at
        db_job.failed_at = job.failed_at

        # User-provided metadata only
        db_job.client_metadata = job.client_metadata
        db_job.updated_at = datetime.now(UTC)

        await self.session.commit()
        await self.session.refresh(db_job)

        return self._to_domain(db_job)

    async def get_by_id(self, job_id: uuid.UUID) -> Optional[QueuedJob]:
        result = await self.session.execute(
            select(QueuedJobModel).where(QueuedJobModel.id == job_id)
        )
        db_job = result.scalars().first()
        if not db_job:
            return None
        return self._to_domain(db_job)

    async def get_claimed_job_by_worker(
        self, worker_id: uuid.UUID
    ) -> Optional[QueuedJob]:
        result = await self.session.execute(
            select(QueuedJobModel).where(
                QueuedJobModel.worker_id == worker_id,
                QueuedJobModel.status == StepExecutionStatus.RUNNING,
            )
        )
        db_job = result.scalars().first()
        if not db_job:
            return None
        return self._to_domain(db_job)

    async def get_job_for_worker_upload(
        self, job_id: uuid.UUID, worker_id: uuid.UUID
    ) -> Optional[QueuedJob]:
        """Return a RUNNING job only if it is owned by the given worker. None otherwise."""
        result = await self.session.execute(
            select(QueuedJobModel).where(
                QueuedJobModel.id == job_id,
                QueuedJobModel.worker_id == worker_id,
                QueuedJobModel.status == StepExecutionStatus.RUNNING,
            )
        )
        db_job = result.scalars().first()
        if not db_job:
            return None
        return self._to_domain(db_job)

    async def list_by_queue(
        self,
        skip: int,
        limit: int,
    ) -> List[QueuedJob]:
        """
        List jobs.

        Args:
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List of jobs
        """
        stmt = (
            select(QueuedJobModel)
            .order_by(QueuedJobModel.priority.desc(), QueuedJobModel.enqueued_at.asc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        db_jobs = result.scalars().all()

        return [self._to_domain(job) for job in db_jobs]

    async def list_by_status(
        self,
        status: StepExecutionStatus,
        skip: int,
        limit: int,
    ) -> List[QueuedJob]:
        """
        List jobs filtered by status.

        Args:
            status: The job status to filter by
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List of jobs matching the status
        """
        stmt = (
            select(QueuedJobModel)
            .where(QueuedJobModel.status == status)
            .order_by(QueuedJobModel.priority.desc(), QueuedJobModel.enqueued_at.asc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        db_jobs = result.scalars().all()

        return [self._to_domain(job) for job in db_jobs]

    async def list_pending(
        self,
        skip: int,
        limit: int,
    ) -> List[QueuedJob]:
        """
        List pending jobs.

        Args:
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List of pending jobs
        """
        return await self.list_by_status(StepExecutionStatus.PENDING, skip, limit)

    async def get_next_pending(
        self,
        resource_requirements: Optional[Dict[str, float]] = None,
    ) -> Optional[QueuedJob]:
        """
        Get the next pending job.

        Args:
            resource_requirements: Optional resource requirements to match

        Returns:
            Next pending job if available
        """
        stmt = (
            select(QueuedJobModel)
            .where(
                QueuedJobModel.status == StepExecutionStatus.PENDING,
            )
            .order_by(QueuedJobModel.priority.desc(), QueuedJobModel.enqueued_at.asc())
            .limit(1)
        )

        result = await self.session.execute(stmt)
        db_job = result.scalars().first()

        if not db_job:
            return None

        return self._to_domain(db_job)

    async def get_next_pending_jobs(
        self,
        limit: int,
    ) -> List[QueuedJob]:
        """
        Get the next pending jobs in priority order.

        Args:
            limit: Maximum number of jobs to return

        Returns:
            List of pending jobs
        """
        stmt = (
            select(QueuedJobModel)
            .where(
                QueuedJobModel.status == StepExecutionStatus.PENDING,
            )
            .order_by(QueuedJobModel.priority.desc(), QueuedJobModel.enqueued_at.asc())
            .limit(limit)
        )

        result = await self.session.execute(stmt)
        db_jobs = result.scalars().all()

        return [self._to_domain(job) for job in db_jobs]

    async def count_by_status(
        self,
    ) -> Dict[StepExecutionStatus, int]:
        """
        Count jobs by status.

        Returns:
            Dictionary mapping status to count
        """
        stmt = select(QueuedJobModel.status, func.count()).group_by(
            QueuedJobModel.status
        )
        result = await self.session.execute(stmt)
        rows = result.all()

        counts: Dict[StepExecutionStatus, int] = {}
        for status, count in rows:
            counts[StepExecutionStatus(status)] = count

        return counts

    async def cleanup_expired(
        self,
        before: datetime,
    ) -> int:
        """
        Clean up expired jobs and return count of deleted jobs.

        Args:
            before: Delete jobs older than this datetime

        Returns:
            Number of jobs deleted
        """
        stmt = select(QueuedJobModel).where(
            QueuedJobModel.completed_at < before,
            QueuedJobModel.status.in_(
                [StepExecutionStatus.COMPLETED, StepExecutionStatus.FAILED]
            ),
        )
        result = await self.session.execute(stmt)
        jobs_to_delete = result.scalars().all()

        count = len(jobs_to_delete)
        for job in jobs_to_delete:
            await self.session.delete(job)

        await self.session.commit()

        return count

    async def delete(self, job_id: uuid.UUID) -> bool:
        """
        Delete a job by its ID.

        Args:
            job_id: The ID of the job to delete

        Returns:
            True if deleted, False if not found
        """
        stmt = select(QueuedJobModel).where(QueuedJobModel.id == job_id)
        result = await self.session.execute(stmt)
        job_model = result.scalars().first()

        if not job_model:
            return False

        await self.session.delete(job_model)
        await self.session.commit()

        return True

    async def delete_by_instance(self, instance_id: uuid.UUID) -> int:
        """Delete all queued jobs for a given instance."""
        stmt = delete_stmt(QueuedJobModel).where(
            QueuedJobModel.instance_id == instance_id
        )
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.rowcount

    async def exists(self, job_id: uuid.UUID) -> bool:
        """
        Check if a job exists.

        Args:
            job_id: The ID to check

        Returns:
            True if exists, False otherwise
        """
        stmt = (
            select(func.count())
            .select_from(QueuedJobModel)
            .where(QueuedJobModel.id == job_id)
        )
        result = await self.session.execute(stmt)
        count = result.scalar()

        return bool(count and count > 0)

    async def claim_next_pending_by_queue_name(
        self,
        queue_name: str,
        worker_id: str,
    ) -> Optional[QueuedJob]:
        """
        Atomically claim the next pending job from a queue by name.

        Uses SELECT FOR UPDATE SKIP LOCKED to ensure only one worker
        can claim each job, even under concurrent access.

        Args:
            queue_name: The queue name (e.g., 'step_jobs', 'video_jobs')
            worker_id: The claiming worker's identifier

        Returns:
            The claimed job if one was available, None otherwise
        """
        # Use raw SQL for FOR UPDATE SKIP LOCKED (SQLAlchemy 2.0 support varies)
        # This atomically:
        # 1. Finds the next pending job (skipping cancelled/failed instances)
        # 2. Locks it (skipping already-locked rows)
        # 3. Updates it to RUNNING status with worker_id
        claim_sql = text("""
            UPDATE queued_jobs
            SET status = 'RUNNING',
                worker_id = :worker_id,
                started_at = NOW(),
                updated_at = NOW()
            WHERE id = (
                SELECT id FROM queued_jobs
                WHERE queue_name = :queue_name
                  AND status = 'PENDING'
                  AND (instance_id IS NULL
                       OR NOT EXISTS (
                           SELECT 1 FROM instances
                           WHERE instances.id = queued_jobs.instance_id
                           AND instances.status IN ('CANCELLED', 'FAILED')
                       ))
                ORDER BY priority DESC, enqueued_at ASC
                LIMIT 1
                FOR UPDATE SKIP LOCKED
            )
            RETURNING *
        """)

        result = await self.session.execute(
            claim_sql, {"queue_name": queue_name, "worker_id": worker_id}
        )
        row = result.fetchone()

        if not row:
            return None

        # `workers.current_job_id` is the canonical "which job this worker holds"
        # signal that `requeue_orphaned_jobs` reads. Set it in the SAME
        # transaction as the claim so there is no claim->heartbeat window where a
        # live worker's freshly-claimed job looks orphaned (heartbeats only land
        # every WORKER_HEARTBEAT_TIMEOUT_MINUTES/interval seconds). The heartbeat
        # subsequently refreshes this value; it never establishes it.
        await self.session.execute(
            text(
                "UPDATE workers SET current_job_id = :job_id, updated_at = NOW() "
                "WHERE id = :worker_id"
            ),
            {"job_id": row.id, "worker_id": worker_id},
        )

        # Commit the claim
        await self.session.commit()

        # Fetch the full model to convert to domain
        db_job = await self.session.get(QueuedJobModel, row.id)
        if not db_job:
            return None

        return self._to_domain(db_job)

    async def has_active_job_for_step(self, step_id: uuid.UUID) -> bool:
        """True if the step still has a PENDING or RUNNING queue row backing it.

        ``queued_jobs.job_id`` is the ``step_executions.id`` (legacy column
        name); an iteration step fans out to several rows, any one of which
        being broker-active means work is still in flight or awaiting a worker.
        The stale-step sweep uses this as its recovery probe: an active row
        means "still working / queued", absence means "genuinely orphaned".
        """
        result = await self.session.execute(
            select(QueuedJobModel.id)
            .where(
                QueuedJobModel.job_id == step_id,
                QueuedJobModel.status.in_(
                    [StepExecutionStatus.PENDING, StepExecutionStatus.RUNNING]
                ),
            )
            .limit(1)
        )
        return result.scalars().first() is not None

    async def requeue_orphaned_jobs(self) -> "OrphanedJobResult":
        """Requeue RUNNING jobs that no live worker is actively holding.

        A RUNNING row is orphaned unless a *live* worker is on it: present in
        the workers table, not deregistered, heartbeat within the timeout, and
        ``current_job_id`` still pointing at this row. That predicate catches
        both a vanished worker (crash/OOM/eviction) and a worker that moved on
        after exhausting result-publish retries - the old "absent from the
        table" check never fired in practice because workers are deregistered
        (flagged), not deleted.
        """
        from app.infrastructure.persistence.models import WorkerModel

        cutoff = datetime.now(UTC) - timedelta(
            minutes=settings.WORKER_HEARTBEAT_TIMEOUT_MINUTES
        )
        worker_result = await self.session.execute(
            select(WorkerModel.id, WorkerModel.current_job_id).where(
                WorkerModel.is_deregistered
                == False,  # noqa: E712 - SQLAlchemy column comparison
                WorkerModel.last_heartbeat > cutoff,
            )
        )
        # Map live worker id -> the queued_jobs.id it is actively holding.
        live_worker_job: dict = {row[0]: row[1] for row in worker_result.all()}

        result = await self.session.execute(
            select(QueuedJobModel).where(
                QueuedJobModel.status == StepExecutionStatus.RUNNING,
            )
        )
        running = result.scalars().all()
        orphans = [
            job for job in running if live_worker_job.get(job.worker_id) != job.id
        ]

        requeued_step_ids: list[uuid.UUID] = []
        failed_step_ids: list[uuid.UUID] = []
        requeued = 0
        failed = 0
        now = datetime.now(UTC)

        for job in orphans:
            if job.retry_count < job.max_retries:
                job.status = StepExecutionStatus.PENDING  # type: ignore[assignment]
                job.retry_count += 1
                job.worker_id = None
                job.started_at = None
                job.assigned_at = None
                job.updated_at = now  # type: ignore[assignment]
                if job.job_id:
                    requeued_step_ids.append(job.job_id)
                requeued += 1
            else:
                job.status = StepExecutionStatus.FAILED  # type: ignore[assignment]
                job.error_message = (
                    f"Job orphaned {job.max_retries + 1} times "
                    "(worker vanished each time); giving up."
                )
                job.failed_at = now  # type: ignore[assignment]
                job.updated_at = now  # type: ignore[assignment]
                if job.job_id:
                    failed_step_ids.append(job.job_id)
                failed += 1

        if orphans:
            await self.session.commit()

        return OrphanedJobResult(
            requeued=requeued,
            failed=failed,
            requeued_step_ids=requeued_step_ids,
            failed_step_ids=failed_step_ids,
        )

    async def complete_job(
        self,
        job_id: uuid.UUID,
        output_data: Dict[str, Any],
    ) -> Optional[QueuedJob]:
        """
        Mark a job as completed with output data.

        Args:
            job_id: The job ID
            output_data: The job result/output

        Returns:
            The updated job if found
        """
        result = await self.session.execute(
            select(QueuedJobModel).where(QueuedJobModel.id == job_id)
        )
        db_job = result.scalars().first()

        if not db_job:
            return None

        db_job.status = StepExecutionStatus.COMPLETED  # type: ignore[assignment]  - domain enum assigned to SA column; SA type stubs expect Column type
        db_job.output_data = output_data
        db_job.completed_at = datetime.now(UTC)
        db_job.updated_at = datetime.now(UTC)

        await self.session.commit()
        await self.session.refresh(db_job)

        return self._to_domain(db_job)

    async def fail_job(
        self,
        job_id: uuid.UUID,
        error_message: str,
    ) -> Optional[QueuedJob]:
        """
        Mark a job as failed with an error message.

        Args:
            job_id: The job ID
            error_message: The error description

        Returns:
            The updated job if found
        """
        result = await self.session.execute(
            select(QueuedJobModel).where(QueuedJobModel.id == job_id)
        )
        db_job = result.scalars().first()

        if not db_job:
            return None

        db_job.status = StepExecutionStatus.FAILED  # type: ignore[assignment]  - domain enum assigned to SA column; SA type stubs expect Column type
        db_job.error_message = error_message
        db_job.failed_at = datetime.now(UTC)
        db_job.updated_at = datetime.now(UTC)

        await self.session.commit()
        await self.session.refresh(db_job)

        return self._to_domain(db_job)
