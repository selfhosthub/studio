# api/app/application/services/queue_service.py

"""Queue service for managing queues, workers, and jobs."""

from typing import Dict, List, Optional, Any
import uuid

from app.config.settings import settings

from app.application.dtos.queue_dto import (
    QueueCreate,
    QueueUpdate,
    QueueResponse,
    WorkerResponse,
    QueuedJobCreate,
    QueuedJobResponse,
)
from app.application.interfaces import (
    QueueServiceInterface,
    ValidationError,
    EventBus,
    EntityNotFoundError,
)
from app.domain.queue.models import (
    Queue,
    Worker,
    QueuedJob,
    QueueStatus,
    WorkerStatus,
    ResourceRequirements,
)
from app.domain.queue.repository import (
    QueueRepository,
    WorkerRepository,
    QueuedJobRepository,
)
from app.domain.instance_step.step_execution import StepExecutionStatus


class QueueService(QueueServiceInterface):
    """Queue service implementing pure orchestration without business logic."""

    def __init__(
        self,
        queue_repository: QueueRepository,
        worker_repository: WorkerRepository,
        step_execution_repository: QueuedJobRepository,
        event_bus: EventBus,
    ):
        self.queue_repository = queue_repository
        self.worker_repository = worker_repository
        self.step_execution_repository = step_execution_repository
        self.event_bus = event_bus

    # ==================== Queue Management ====================

    async def create_queue(
        self,
        command: QueueCreate,
    ) -> QueueResponse:
        """Create a new queue using factory method."""
        resource_requirements = None
        if command.resource_requirements:
            resource_requirements = ResourceRequirements(
                **command.resource_requirements
            )

        queue = Queue.create(
            name=command.name,
            organization_id=command.organization_id,
            created_by=command.created_by,
            queue_type=command.queue_type,
            description=command.description,
            max_concurrency=command.max_concurrency,
            max_pending_jobs=command.max_pending_jobs,
            default_timeout_seconds=command.default_timeout_seconds,
            resource_requirements=resource_requirements,
            tags=command.tags if command.tags else None,
            client_metadata=(
                command.client_metadata if command.client_metadata else None
            ),
        )

        events = queue.clear_events()

        queue = await self.queue_repository.create(queue)

        for event in events:
            await self.event_bus.publish(event)

        return QueueResponse.from_domain(queue)

    async def update_queue(
        self,
        queue_id: uuid.UUID,
        command: QueueUpdate,
    ) -> QueueResponse:
        """Update queue configuration."""
        queue = await self.queue_repository.get_by_id(queue_id)
        if not queue:
            raise EntityNotFoundError(
                entity_type="Queue",
                entity_id=queue_id,
            )

        if command.name:
            queue.name = command.name
        if command.description is not None:
            queue.description = command.description
        if command.max_concurrency is not None:
            queue.max_concurrency = command.max_concurrency
        if command.max_pending_jobs is not None:
            queue.max_pending_jobs = command.max_pending_jobs
        if command.default_timeout_seconds is not None:
            queue.default_timeout_seconds = command.default_timeout_seconds
        if command.resource_requirements is not None:
            queue.resource_requirements = ResourceRequirements(
                **command.resource_requirements
            )
        if command.tags is not None:
            queue.tags = command.tags
        if command.client_metadata is not None:
            queue.client_metadata = command.client_metadata

        queue = await self.queue_repository.update(queue)

        return QueueResponse.from_domain(queue)

    async def pause_queue(
        self,
        queue_id: uuid.UUID,
        paused_by: uuid.UUID,
    ) -> QueueResponse:
        """Pause queue processing."""
        queue = await self.queue_repository.get_by_id(queue_id)
        if not queue:
            raise EntityNotFoundError(
                entity_type="Queue",
                entity_id=queue_id,
            )

        queue.pause(paused_by=paused_by)

        events = queue.clear_events()
        queue = await self.queue_repository.update(queue)

        for event in events:
            await self.event_bus.publish(event)

        return QueueResponse.from_domain(queue)

    async def resume_queue(
        self,
        queue_id: uuid.UUID,
        resumed_by: uuid.UUID,
    ) -> QueueResponse:
        """Resume queue processing."""
        queue = await self.queue_repository.get_by_id(queue_id)
        if not queue:
            raise EntityNotFoundError(
                entity_type="Queue",
                entity_id=queue_id,
            )

        queue.resume(resumed_by=resumed_by)

        events = queue.clear_events()
        queue = await self.queue_repository.update(queue)

        for event in events:
            await self.event_bus.publish(event)

        return QueueResponse.from_domain(queue)

    async def drain_queue(
        self,
        queue_id: uuid.UUID,
        drained_by: uuid.UUID,
    ) -> QueueResponse:
        """Drain queue of pending jobs."""
        queue = await self.queue_repository.get_by_id(queue_id)
        if not queue:
            raise EntityNotFoundError(
                entity_type="Queue",
                entity_id=queue_id,
            )

        queue.drain(initiated_by=drained_by)

        events = queue.clear_events()
        queue = await self.queue_repository.update(queue)

        for event in events:
            await self.event_bus.publish(event)

        return QueueResponse.from_domain(queue)

    async def stop_queue(
        self,
        queue_id: uuid.UUID,
        stopped_by: uuid.UUID,
    ) -> QueueResponse:
        """Stop queue completely."""
        queue = await self.queue_repository.get_by_id(queue_id)
        if not queue:
            raise EntityNotFoundError(
                entity_type="Queue",
                entity_id=queue_id,
            )

        queue.stop(stopped_by=stopped_by)

        events = queue.clear_events()
        queue = await self.queue_repository.update(queue)

        for event in events:
            await self.event_bus.publish(event)

        return QueueResponse.from_domain(queue)

    async def get_queue(
        self,
        queue_id: uuid.UUID,
    ) -> Optional[QueueResponse]:
        """Get a queue by ID."""
        queue = await self.queue_repository.get_by_id(queue_id)
        if not queue:
            return None

        return QueueResponse.from_domain(queue)

    async def list_queues(
        self,
        organization_id: uuid.UUID,
        status: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[QueueResponse]:
        """List queues with optional filtering."""
        all_queues = await self.queue_repository.list_by_organization(
            organization_id=organization_id,
            skip=skip,
            limit=limit,
        )

        if status:
            status_enum = QueueStatus(status)
            all_queues = [q for q in all_queues if q.status == status_enum]

        paginated_queues = all_queues[skip : skip + limit]
        return [QueueResponse.from_domain(q) for q in paginated_queues]

    # ==================== Worker Management ====================

    async def register_worker(
        self,
        secret: str,
        name: str,
        queue_id: Optional[uuid.UUID],
        capabilities: Dict[str, Any],
        queue_labels: List[str],
        ip_address: Optional[str] = None,
        hostname: Optional[str] = None,
        cpu_percent: Optional[float] = None,
        memory_percent: Optional[float] = None,
        memory_used_mb: Optional[int] = None,
        memory_total_mb: Optional[int] = None,
        disk_percent: Optional[float] = None,
        gpu_percent: Optional[float] = None,
        gpu_memory_percent: Optional[float] = None,
    ) -> WorkerResponse:
        """Register a new worker via shared-secret self-registration.

        queue_id is optional; omit for general-purpose workers not bound to a specific queue.

        Raises:
            ValidationError: If secret is invalid
            EntityNotFoundError: If queue_id is provided but the queue doesn't exist
        """
        if secret != settings.WORKER_SHARED_SECRET:
            raise ValidationError("Invalid worker secret")

        # Only validate queue exists if queue_id is provided
        if queue_id:
            queue = await self.queue_repository.get_by_id(queue_id)
            if not queue:
                raise EntityNotFoundError(
                    entity_type="Queue",
                    entity_id=queue_id,
                )

        worker = Worker.create(
            name=name,
            queue_id=queue_id,
            capabilities=capabilities,
            queue_labels=queue_labels,
            ip_address=ip_address,
            hostname=hostname,
            cpu_percent=cpu_percent,
            memory_percent=memory_percent,
            memory_used_mb=memory_used_mb,
            memory_total_mb=memory_total_mb,
            disk_percent=disk_percent,
            gpu_percent=gpu_percent,
            gpu_memory_percent=gpu_memory_percent,
        )

        events = worker.clear_events()
        created = await self.worker_repository.create(worker)

        for event in events:
            await self.event_bus.publish(event)

        return WorkerResponse.from_domain(created)

    async def set_busy(
        self,
        worker_id: uuid.UUID,
        queued_job_id: uuid.UUID,
        cpu_percent: Optional[float] = None,
        memory_percent: Optional[float] = None,
        memory_used_mb: Optional[int] = None,
        memory_total_mb: Optional[int] = None,
        disk_percent: Optional[float] = None,
        gpu_percent: Optional[float] = None,
        gpu_memory_percent: Optional[float] = None,
    ) -> bool:
        """Mark a worker BUSY for a specific queued job.

        `queued_job_id` must reference a real row in `queued_jobs` - raises
        `EntityNotFoundError` if not found, preventing silent FK violations.

        Returns `True` if the worker is deregistered, `False` otherwise.
        """
        if not await self.step_execution_repository.exists(queued_job_id):
            raise EntityNotFoundError(
                entity_type="QueuedJob",
                entity_id=queued_job_id,
                code="QUEUED_JOB_NOT_FOUND",
            )

        worker = await self.worker_repository.get_by_id(worker_id)
        if not worker:
            raise EntityNotFoundError(
                entity_type="Worker",
                entity_id=worker_id,
            )

        worker.set_busy(
            queued_job_id=queued_job_id,
            cpu_percent=cpu_percent,
            memory_percent=memory_percent,
            memory_used_mb=memory_used_mb,
            memory_total_mb=memory_total_mb,
            disk_percent=disk_percent,
            gpu_percent=gpu_percent,
            gpu_memory_percent=gpu_memory_percent,
        )

        events = worker.clear_events()
        await self.worker_repository.update(worker)

        for event in events:
            await self.event_bus.publish(event)

        return worker.is_deregistered

    async def worker_heartbeat(
        self,
        worker_id: uuid.UUID,
        status: WorkerStatus,
        current_job_id: Optional[uuid.UUID] = None,
        cpu_percent: Optional[float] = None,
        memory_percent: Optional[float] = None,
        memory_used_mb: Optional[int] = None,
        memory_total_mb: Optional[int] = None,
        disk_percent: Optional[float] = None,
        gpu_percent: Optional[float] = None,
        gpu_memory_percent: Optional[float] = None,
    ) -> bool:
        """Record a non-BUSY heartbeat from a worker.

        Use the set_busy path for BUSY transitions - that path requires a
        non-Optional job ID and validates it against the queued_jobs table.
        This method accepts any status (typically IDLE) and never mutates
        current_job_id; passing it on a non-BUSY ping is silently ignored.

        Returns True if the worker is deregistered (caller should stop).
        """
        worker = await self.worker_repository.get_by_id(worker_id)
        if not worker:
            raise EntityNotFoundError(
                entity_type="Worker",
                entity_id=worker_id,
            )

        worker.heartbeat(
            status=status,
            current_job_id=current_job_id,
            cpu_percent=cpu_percent,
            memory_percent=memory_percent,
            memory_used_mb=memory_used_mb,
            memory_total_mb=memory_total_mb,
            disk_percent=disk_percent,
            gpu_percent=gpu_percent,
            gpu_memory_percent=gpu_memory_percent,
        )

        events = worker.clear_events()
        await self.worker_repository.update(worker)

        for event in events:
            await self.event_bus.publish(event)

        return worker.is_deregistered

    async def deregister_worker(
        self,
        worker_id: uuid.UUID,
        secret: str,
    ) -> bool:
        """Deregister a worker using the shared secret. Returns True if deleted."""
        if secret != settings.WORKER_SHARED_SECRET:
            raise ValidationError("Invalid worker secret")

        worker = await self.worker_repository.get_by_id(worker_id)
        if not worker:
            raise EntityNotFoundError(
                entity_type="Worker",
                entity_id=worker_id,
            )

        await self.worker_repository.delete(worker_id)
        return True

    async def delete_worker(
        self,
        worker_id: uuid.UUID,
    ) -> bool:
        """Delete a worker (admin operation, no secret required). Returns True if deleted."""
        worker = await self.worker_repository.get_by_id(worker_id)
        if not worker:
            raise EntityNotFoundError(
                entity_type="Worker",
                entity_id=worker_id,
            )

        await self.worker_repository.delete(worker_id)
        return True

    async def list_active_workers(
        self,
        skip: int = 0,
        limit: int = 100,
        queue_id: Optional[uuid.UUID] = None,
    ) -> List[WorkerResponse]:
        """List active workers (based on recent heartbeats)."""
        workers = await self.worker_repository.list_active_workers(
            skip=skip,
            limit=limit,
            queue_id=queue_id,
        )

        paginated_workers = workers[skip : skip + limit]

        return [WorkerResponse.from_domain(w) for w in paginated_workers]

    async def get_worker(
        self,
        worker_id: uuid.UUID,
    ) -> Optional[WorkerResponse]:
        """Return a worker by ID, or None if not found."""
        worker = await self.worker_repository.get_by_id(worker_id)
        if not worker:
            return None

        return WorkerResponse.from_domain(worker)

    async def list_workers(
        self,
        queue_id: uuid.UUID,
        status: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[WorkerResponse]:
        """List workers for a queue."""
        all_workers = await self.worker_repository.list_by_queue(
            queue_id=queue_id, skip=skip, limit=limit
        )

        if status:
            status_enum = WorkerStatus(status)
            all_workers = [w for w in all_workers if w.status == status_enum]

        paginated_workers = all_workers[skip : skip + limit]
        return [WorkerResponse.from_domain(w) for w in paginated_workers]

    # ==================== Job Management ====================

    async def enqueue_job(
        self,
        command: QueuedJobCreate,
    ) -> QueuedJobResponse:
        """Enqueue a new job."""
        resource_requirements = None
        if command.resource_requirements:
            resource_requirements = ResourceRequirements(
                **command.resource_requirements
            )

        job = QueuedJob.create(
            organization_id=command.organization_id,
            enqueued_by=command.enqueued_by,
            input_data=command.input_data,
            priority=command.priority,
            instance_id=command.workflow_id,
            resource_requirements=resource_requirements,
            timeout_seconds=command.timeout_seconds,
            max_retries=command.max_retries,
            tags=command.tags if command.tags else None,
            client_metadata=(
                command.client_metadata if command.client_metadata else None
            ),
        )

        events = job.clear_events()
        job = await self.step_execution_repository.create(job)

        for event in events:
            await self.event_bus.publish(event)

        return QueuedJobResponse.from_domain(job)

    async def get_job(
        self,
        job_id: uuid.UUID,
    ) -> Optional[QueuedJobResponse]:
        """Get a job by ID."""
        job = await self.step_execution_repository.get_by_id(job_id)
        if not job:
            return None

        return QueuedJobResponse.from_domain(job)

    async def start_job(
        self,
        job_id: uuid.UUID,
    ) -> QueuedJobResponse:
        """Start processing a queued job."""
        job = await self.step_execution_repository.get_by_id(job_id)
        if not job:
            raise EntityNotFoundError(
                entity_type="QueuedJob",
                entity_id=job_id,
            )

        job.start()

        job = await self.step_execution_repository.update(job)

        return QueuedJobResponse.from_domain(job)

    async def complete_job(
        self,
        job_id: uuid.UUID,
        result: Dict[str, Any],
    ) -> QueuedJobResponse:
        """Complete a job with output data."""
        job = await self.step_execution_repository.get_by_id(job_id)
        if not job:
            raise EntityNotFoundError(
                entity_type="QueuedJob",
                entity_id=job_id,
            )

        job.complete(output_data=result)

        job = await self.step_execution_repository.update(job)

        return QueuedJobResponse.from_domain(job)

    async def fail_job(
        self,
        job_id: uuid.UUID,
        error: str,
    ) -> QueuedJobResponse:
        """Mark a job as failed."""
        job = await self.step_execution_repository.get_by_id(job_id)
        if not job:
            raise EntityNotFoundError(
                entity_type="QueuedJob",
                entity_id=job_id,
            )

        job.fail(error_message=error)

        job = await self.step_execution_repository.update(job)

        return QueuedJobResponse.from_domain(job)

    async def list_jobs(
        self,
        queue_id: uuid.UUID,
        status: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[QueuedJobResponse]:
        """List jobs in queue."""
        if status:
            status_enum = StepExecutionStatus(status)
            all_jobs = await self.step_execution_repository.list_by_status(
                status=status_enum,
                skip=skip,
                limit=limit,
            )
        else:
            all_jobs = await self.step_execution_repository.list_by_queue(
                skip=skip,
                limit=limit,
            )

        return [QueuedJobResponse.from_domain(j) for j in all_jobs]
