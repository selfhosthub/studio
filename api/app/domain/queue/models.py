# api/app/domain/queue/models.py

"""Domain models for queues, workers, and queued jobs."""

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import Field, field_validator

from app.config.settings import settings
from app.domain.common.base_entity import AggregateRoot
from app.domain.common.events import DomainEvent
from app.domain.common.exceptions import InvalidStateTransition
from app.domain.common.value_objects import ResourceRequirements
from app.domain.instance_step.models import StepExecutionStatus


class QueueType(str, Enum):
    DEFAULT = "default"
    PRIORITY = "priority"


class QueueStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    DRAINING = "draining"
    STOPPED = "stopped"


class WorkerStatus(str, Enum):
    IDLE = "idle"
    BUSY = "busy"
    OFFLINE = "offline"


class QueueCreatedEvent(DomainEvent):
    event_type: str = "queue.created"
    aggregate_id: uuid.UUID
    aggregate_type: str = "queue"
    queue_id: uuid.UUID
    organization_id: uuid.UUID
    created_by: uuid.UUID


class QueuePausedEvent(DomainEvent):
    event_type: str = "queue.paused"
    aggregate_id: uuid.UUID
    aggregate_type: str = "queue"
    queue_id: uuid.UUID
    organization_id: uuid.UUID
    paused_by: uuid.UUID
    reason: Optional[str] = None


class QueueResumedEvent(DomainEvent):
    event_type: str = "queue.resumed"
    aggregate_id: uuid.UUID
    aggregate_type: str = "queue"
    queue_id: uuid.UUID
    organization_id: uuid.UUID
    resumed_by: uuid.UUID


class QueueDrainingEvent(DomainEvent):
    event_type: str = "queue.draining"
    aggregate_id: uuid.UUID
    aggregate_type: str = "queue"
    queue_id: uuid.UUID
    organization_id: uuid.UUID
    initiated_by: uuid.UUID
    reason: Optional[str] = None


class QueueStoppedEvent(DomainEvent):
    event_type: str = "queue.stopped"
    aggregate_id: uuid.UUID
    aggregate_type: str = "queue"
    queue_id: uuid.UUID
    organization_id: uuid.UUID
    stopped_by: uuid.UUID
    force_stopped: bool = False


class WorkerRegisteredEvent(DomainEvent):
    event_type: str = "worker.registered"
    aggregate_id: uuid.UUID
    aggregate_type: str = "worker"
    worker_id: uuid.UUID
    queue_id: Optional[uuid.UUID] = None


class WorkerHeartbeatEvent(DomainEvent):
    event_type: str = "worker.heartbeat"
    aggregate_id: uuid.UUID
    aggregate_type: str = "worker"
    worker_id: uuid.UUID
    queue_id: Optional[uuid.UUID] = None
    status: str


class WorkerJobCompletedEvent(DomainEvent):
    event_type: str = "worker.job_completed"
    aggregate_id: uuid.UUID
    aggregate_type: str = "worker"
    worker_id: uuid.UUID
    job_id: uuid.UUID
    success: bool


class JobEnqueuedEvent(DomainEvent):
    event_type: str = "job.enqueued"
    aggregate_id: uuid.UUID
    aggregate_type: str = "job"
    job_id: uuid.UUID
    organization_id: uuid.UUID
    priority: int


class JobAssignedEvent(DomainEvent):
    event_type: str = "job.assigned"
    aggregate_id: uuid.UUID
    aggregate_type: str = "job"
    job_id: uuid.UUID
    worker_id: uuid.UUID


class Queue(AggregateRoot):
    """Aggregate root for a job queue: prioritization and scheduling across workers."""

    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=1000)
    organization_id: uuid.UUID
    queue_type: QueueType = QueueType.DEFAULT

    status: QueueStatus = QueueStatus.ACTIVE
    max_concurrency: int = Field(
        default=settings.QUEUE_DEFAULT_MAX_CONCURRENCY, ge=1, le=1000
    )
    max_pending_jobs: int = Field(
        default=settings.QUEUE_DEFAULT_MAX_PENDING, ge=1, le=100000
    )
    default_timeout_seconds: int = Field(
        default=settings.QUEUE_DEFAULT_TIMEOUT, ge=1, le=86400
    )

    resource_requirements: Optional[ResourceRequirements] = None
    scaling_policy: Dict[str, Any] = Field(default_factory=dict)

    total_jobs_processed: int = 0
    failed_jobs_count: int = 0
    average_processing_time: Optional[float] = None

    registered_workers: List[str] = Field(default_factory=list)
    active_workers: int = 0

    created_by: uuid.UUID
    paused_at: Optional[datetime] = None
    paused_by: Optional[uuid.UUID] = None
    stopped_at: Optional[datetime] = None
    stopped_by: Optional[uuid.UUID] = None

    tags: List[str] = Field(default_factory=list)
    client_metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("status", mode="before")
    @classmethod
    def convert_status_to_enum(cls, v):
        if isinstance(v, str) and not isinstance(v, QueueStatus):
            return QueueStatus(v)
        return v

    @classmethod
    def create(
        cls,
        name: str,
        organization_id: uuid.UUID,
        created_by: uuid.UUID,
        queue_type: QueueType = QueueType.DEFAULT,
        description: Optional[str] = None,
        max_concurrency: int = settings.QUEUE_DEFAULT_MAX_CONCURRENCY,
        max_pending_jobs: int = settings.QUEUE_DEFAULT_MAX_PENDING,
        default_timeout_seconds: int = settings.QUEUE_DEFAULT_TIMEOUT,
        resource_requirements: Optional[ResourceRequirements] = None,
        tags: Optional[List[str]] = None,
        client_metadata: Optional[Dict[str, Any]] = None,
    ) -> "Queue":
        queue = cls(
            id=uuid.uuid4(),
            name=name,
            organization_id=organization_id,
            created_by=created_by,
            queue_type=queue_type,
            description=description,
            max_concurrency=max_concurrency,
            max_pending_jobs=max_pending_jobs,
            default_timeout_seconds=default_timeout_seconds,
            resource_requirements=resource_requirements,
            tags=tags or [],
            client_metadata=client_metadata or {},
            created_at=datetime.now(),
        )

        queue.add_domain_event(
            QueueCreatedEvent(
                aggregate_id=queue.id,
                aggregate_type="queue",
                queue_id=queue.id,
                organization_id=organization_id,
                created_by=created_by,
            )
        )

        return queue

    def add_domain_event(self, event: DomainEvent) -> None:
        if not hasattr(self, "_events"):
            self._events = []
        self._events.append(event)

    def clear_events(self) -> List[DomainEvent]:
        if not hasattr(self, "_events"):
            self._events = []
        events = self._events.copy()
        self._events.clear()
        return events

    def pause(self, paused_by: uuid.UUID, reason: Optional[str] = None) -> None:
        if self.status != QueueStatus.ACTIVE:
            raise InvalidStateTransition(
                message=f"Queue must be active to pause, current status: {self.status.value}",
                code="INVALID_QUEUE_PAUSE",
                context={
                    "entity_type": "Queue",
                    "entity_id": str(self.id),
                    "current_state": self.status.value,
                    "attempted_state": QueueStatus.PAUSED.value,
                },
            )

        self.status = QueueStatus.PAUSED
        self.paused_at = datetime.now()
        self.paused_by = paused_by
        self.updated_at = datetime.now()

        self.add_domain_event(
            QueuePausedEvent(
                aggregate_id=self.id,
                aggregate_type="queue",
                queue_id=self.id,
                organization_id=self.organization_id,
                paused_by=paused_by,
                reason=reason,
            )
        )

    def resume(self, resumed_by: uuid.UUID) -> None:
        if self.status != QueueStatus.PAUSED:
            raise InvalidStateTransition(
                message=f"Queue must be paused to resume, current status: {self.status.value}",
                code="INVALID_QUEUE_RESUME",
                context={
                    "entity_type": "Queue",
                    "entity_id": str(self.id),
                    "current_state": self.status.value,
                    "attempted_state": QueueStatus.ACTIVE.value,
                },
            )

        self.status = QueueStatus.ACTIVE
        self.paused_at = None
        self.paused_by = None
        self.updated_at = datetime.now()

        self.add_domain_event(
            QueueResumedEvent(
                aggregate_id=self.id,
                aggregate_type="queue",
                queue_id=self.id,
                organization_id=self.organization_id,
                resumed_by=resumed_by,
            )
        )

    def drain(self, initiated_by: uuid.UUID, reason: Optional[str] = None) -> None:
        if self.status not in [QueueStatus.ACTIVE, QueueStatus.PAUSED]:
            raise InvalidStateTransition(
                message=f"Queue must be active or paused to drain, current status: {self.status.value}",
                code="INVALID_QUEUE_DRAIN",
                context={
                    "entity_type": "Queue",
                    "entity_id": str(self.id),
                    "current_state": self.status.value,
                    "attempted_state": QueueStatus.DRAINING.value,
                },
            )

        self.status = QueueStatus.DRAINING
        self.updated_at = datetime.now()

        self.add_domain_event(
            QueueDrainingEvent(
                aggregate_id=self.id,
                aggregate_type="queue",
                queue_id=self.id,
                organization_id=self.organization_id,
                initiated_by=initiated_by,
                reason=reason,
            )
        )

    def stop(self, stopped_by: uuid.UUID, force: bool = False) -> None:
        if not force and self.status == QueueStatus.STOPPED:
            raise InvalidStateTransition(
                message="Queue is already stopped",
                code="INVALID_QUEUE_STOP",
                context={
                    "entity_type": "Queue",
                    "entity_id": str(self.id),
                    "current_state": self.status.value,
                    "attempted_state": QueueStatus.STOPPED.value,
                },
            )

        self.status = QueueStatus.STOPPED
        self.stopped_at = datetime.now()
        self.stopped_by = stopped_by
        self.updated_at = datetime.now()

        self.add_domain_event(
            QueueStoppedEvent(
                aggregate_id=self.id,
                aggregate_type="queue",
                queue_id=self.id,
                organization_id=self.organization_id,
                stopped_by=stopped_by,
                force_stopped=force,
            )
        )

    @staticmethod
    def validate_status_transition(current: QueueStatus, target: QueueStatus) -> bool:
        valid_transitions: Dict[QueueStatus, List[QueueStatus]] = {
            QueueStatus.ACTIVE: [
                QueueStatus.PAUSED,
                QueueStatus.DRAINING,
                QueueStatus.STOPPED,
            ],
            QueueStatus.PAUSED: [QueueStatus.ACTIVE, QueueStatus.STOPPED],
            QueueStatus.DRAINING: [QueueStatus.STOPPED],
            QueueStatus.STOPPED: [],
        }
        return target in valid_transitions.get(current, [])

    @staticmethod
    def from_string(status: str) -> QueueStatus:
        try:
            return QueueStatus(status.lower())
        except ValueError:
            return QueueStatus.ACTIVE


class Worker(AggregateRoot):
    """Ephemeral job-processing node. Self-registering; not organization-owned."""

    name: str = Field(..., min_length=1, max_length=255)
    queue_id: Optional[uuid.UUID] = None  # Optional for general-purpose workers

    capabilities: Dict[str, Any] = Field(default_factory=dict)
    queue_labels: List[str] = Field(default_factory=list)

    status: WorkerStatus = WorkerStatus.OFFLINE
    last_heartbeat: Optional[datetime] = None
    current_job_id: Optional[uuid.UUID] = None

    jobs_completed: int = 0
    is_deregistered: bool = False

    # Network info
    ip_address: Optional[str] = None
    hostname: Optional[str] = None

    # Resource metrics (updated with each heartbeat)
    cpu_percent: Optional[float] = None
    memory_percent: Optional[float] = None
    memory_used_mb: Optional[int] = None
    memory_total_mb: Optional[int] = None
    disk_percent: Optional[float] = None
    gpu_percent: Optional[float] = None
    gpu_memory_percent: Optional[float] = None

    @field_validator("status", mode="before")
    @classmethod
    def convert_status_to_enum(cls, v):
        if isinstance(v, str) and not isinstance(v, WorkerStatus):
            return WorkerStatus(v)
        return v

    @classmethod
    def create(
        cls,
        name: str,
        queue_id: Optional[uuid.UUID] = None,
        capabilities: Optional[Dict[str, Any]] = None,
        queue_labels: Optional[List[str]] = None,
        ip_address: Optional[str] = None,
        hostname: Optional[str] = None,
        cpu_percent: Optional[float] = None,
        memory_percent: Optional[float] = None,
        memory_used_mb: Optional[int] = None,
        memory_total_mb: Optional[int] = None,
        disk_percent: Optional[float] = None,
        gpu_percent: Optional[float] = None,
        gpu_memory_percent: Optional[float] = None,
    ) -> "Worker":
        worker = cls(
            id=uuid.uuid4(),
            name=name,
            queue_id=queue_id,
            capabilities=capabilities or {},
            queue_labels=queue_labels or [],
            status=WorkerStatus.OFFLINE,
            jobs_completed=0,
            ip_address=ip_address,
            hostname=hostname,
            cpu_percent=cpu_percent,
            memory_percent=memory_percent,
            memory_used_mb=memory_used_mb,
            memory_total_mb=memory_total_mb,
            disk_percent=disk_percent,
            gpu_percent=gpu_percent,
            gpu_memory_percent=gpu_memory_percent,
            last_heartbeat=datetime.now(),
            created_at=datetime.now(),
        )

        worker.add_domain_event(
            WorkerRegisteredEvent(
                aggregate_id=worker.id,
                aggregate_type="worker",
                worker_id=worker.id,
                queue_id=queue_id,
            )
        )

        return worker

    def add_domain_event(self, event: DomainEvent) -> None:
        if not hasattr(self, "_events"):
            self._events = []
        self._events.append(event)

    def clear_events(self) -> List[DomainEvent]:
        if not hasattr(self, "_events"):
            self._events = []
        events = self._events.copy()
        self._events.clear()
        return events

    def set_busy(
        self,
        queued_job_id: uuid.UUID,
        cpu_percent: Optional[float] = None,
        memory_percent: Optional[float] = None,
        memory_used_mb: Optional[int] = None,
        memory_total_mb: Optional[int] = None,
        disk_percent: Optional[float] = None,
        gpu_percent: Optional[float] = None,
        gpu_memory_percent: Optional[float] = None,
    ) -> None:
        """Set worker BUSY for a specific queued job.

        queued_job_id must be a queued_jobs.id value - the FK workers.current_job_id → queued_jobs.id
        makes any other UUID class a guaranteed FK violation on commit.
        """
        self.status = WorkerStatus.BUSY
        self.current_job_id = queued_job_id
        self.last_heartbeat = datetime.now()
        self.updated_at = datetime.now()

        if cpu_percent is not None:
            self.cpu_percent = cpu_percent
        if memory_percent is not None:
            self.memory_percent = memory_percent
        if memory_used_mb is not None:
            self.memory_used_mb = memory_used_mb
        if memory_total_mb is not None:
            self.memory_total_mb = memory_total_mb
        if disk_percent is not None:
            self.disk_percent = disk_percent
        if gpu_percent is not None:
            self.gpu_percent = gpu_percent
        if gpu_memory_percent is not None:
            self.gpu_memory_percent = gpu_memory_percent

        self.add_domain_event(
            WorkerHeartbeatEvent(
                aggregate_id=self.id,
                aggregate_type="worker",
                worker_id=self.id,
                queue_id=self.queue_id,
                status=WorkerStatus.BUSY.value,
            )
        )

    def heartbeat(
        self,
        status: WorkerStatus,
        current_job_id: Optional[uuid.UUID] = None,
        cpu_percent: Optional[float] = None,
        memory_percent: Optional[float] = None,
        memory_used_mb: Optional[int] = None,
        memory_total_mb: Optional[int] = None,
        disk_percent: Optional[float] = None,
        gpu_percent: Optional[float] = None,
        gpu_memory_percent: Optional[float] = None,
    ) -> None:
        """Record a heartbeat. For BUSY transitions prefer set_busy - it rejects None at the type layer."""
        self.status = status
        self.current_job_id = current_job_id
        self.last_heartbeat = datetime.now()
        self.updated_at = datetime.now()

        if cpu_percent is not None:
            self.cpu_percent = cpu_percent
        if memory_percent is not None:
            self.memory_percent = memory_percent
        if memory_used_mb is not None:
            self.memory_used_mb = memory_used_mb
        if memory_total_mb is not None:
            self.memory_total_mb = memory_total_mb
        if disk_percent is not None:
            self.disk_percent = disk_percent
        if gpu_percent is not None:
            self.gpu_percent = gpu_percent
        if gpu_memory_percent is not None:
            self.gpu_memory_percent = gpu_memory_percent

        self.add_domain_event(
            WorkerHeartbeatEvent(
                aggregate_id=self.id,
                aggregate_type="worker",
                worker_id=self.id,
                queue_id=self.queue_id,
                status=status.value,
            )
        )

    def complete_job(self, job_id: uuid.UUID, success: bool = True) -> None:
        if success:
            self.jobs_completed += 1

        self.current_job_id = None
        self.status = WorkerStatus.IDLE
        self.updated_at = datetime.now()

        self.add_domain_event(
            WorkerJobCompletedEvent(
                aggregate_id=self.id,
                aggregate_type="worker",
                worker_id=self.id,
                job_id=job_id,
                success=success,
            )
        )


class QueuedJob(AggregateRoot):
    """Work unit submitted by callers and processed by workers."""

    queue_name: Optional[str] = (
        None  # Queue name for worker polling (e.g., 'step_jobs')
    )
    organization_id: uuid.UUID
    instance_id: Optional[uuid.UUID] = None

    status: StepExecutionStatus = StepExecutionStatus.PENDING
    priority: int = Field(default=0, ge=-100, le=100)

    input_data: Dict[str, Any] = Field(default_factory=dict)
    output_data: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None

    resource_requirements: Optional[ResourceRequirements] = None
    timeout_seconds: Optional[int] = None

    worker_id: Optional[uuid.UUID] = None
    assigned_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    failed_at: Optional[datetime] = None

    enqueued_at: datetime
    enqueued_by: uuid.UUID

    retry_count: int = 0
    max_retries: int = settings.DEFAULT_MAX_RETRIES

    tags: List[str] = Field(default_factory=list)
    client_metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("status", mode="before")
    @classmethod
    def convert_status_to_enum(cls, v):
        if isinstance(v, str) and not isinstance(v, StepExecutionStatus):
            return StepExecutionStatus(v)
        return v

    @classmethod
    def create(
        cls,
        organization_id: uuid.UUID,
        enqueued_by: uuid.UUID,
        input_data: Dict[str, Any],
        priority: int = 0,
        instance_id: Optional[uuid.UUID] = None,
        resource_requirements: Optional[ResourceRequirements] = None,
        timeout_seconds: Optional[int] = None,
        max_retries: int = settings.DEFAULT_MAX_RETRIES,
        tags: Optional[List[str]] = None,
        client_metadata: Optional[Dict[str, Any]] = None,
    ) -> "QueuedJob":
        job = cls(
            id=uuid.uuid4(),
            organization_id=organization_id,
            enqueued_by=enqueued_by,
            input_data=input_data,
            priority=priority,
            instance_id=instance_id,
            resource_requirements=resource_requirements,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            tags=tags or [],
            client_metadata=client_metadata or {},
            enqueued_at=datetime.now(),
            created_at=datetime.now(),
        )

        job.add_domain_event(
            JobEnqueuedEvent(
                aggregate_id=job.id,
                aggregate_type="job",
                job_id=job.id,
                organization_id=organization_id,
                priority=priority,
            )
        )

        return job

    def add_domain_event(self, event: DomainEvent) -> None:
        if not hasattr(self, "_events"):
            self._events = []
        self._events.append(event)

    def clear_events(self) -> List[DomainEvent]:
        if not hasattr(self, "_events"):
            self._events = []
        events = self._events.copy()
        self._events.clear()
        return events

    def assign_to_worker(self, worker_id: uuid.UUID) -> None:
        if self.status != StepExecutionStatus.PENDING:
            raise InvalidStateTransition(
                message=f"Can only assign pending jobs, current status: {self.status.value}",
                code="INVALID_JOB_ASSIGN",
                context={
                    "entity_type": "QueuedJob",
                    "entity_id": str(self.id),
                    "current_state": self.status.value,
                    "attempted_state": StepExecutionStatus.RUNNING.value,
                },
            )

        self.worker_id = worker_id
        self.status = StepExecutionStatus.RUNNING
        self.assigned_at = datetime.now()
        self.updated_at = datetime.now()

        self.add_domain_event(
            JobAssignedEvent(
                aggregate_id=self.id,
                aggregate_type="job",
                job_id=self.id,
                worker_id=worker_id,
            )
        )

    def start(self) -> None:
        if self.status != StepExecutionStatus.RUNNING:
            raise InvalidStateTransition(
                message=f"Can only start assigned/running jobs, current status: {self.status.value}",
                code="INVALID_JOB_START",
                context={
                    "entity_type": "QueuedJob",
                    "entity_id": str(self.id),
                    "current_state": self.status.value,
                    "attempted_state": StepExecutionStatus.RUNNING.value,
                },
            )

        self.status = StepExecutionStatus.RUNNING
        self.started_at = datetime.now()
        self.updated_at = datetime.now()

    def complete(self, output_data: Dict[str, Any]) -> None:
        if self.status != StepExecutionStatus.RUNNING:
            raise InvalidStateTransition(
                message=f"Can only complete running jobs, current status: {self.status.value}",
                code="INVALID_JOB_COMPLETE",
                context={
                    "entity_type": "QueuedJob",
                    "entity_id": str(self.id),
                    "current_state": self.status.value,
                    "attempted_state": StepExecutionStatus.COMPLETED.value,
                },
            )

        self.status = StepExecutionStatus.COMPLETED
        self.output_data = output_data
        self.completed_at = datetime.now()
        self.updated_at = datetime.now()

    def fail(self, error_message: str) -> None:
        if self.status not in [
            StepExecutionStatus.RUNNING,
            StepExecutionStatus.PENDING,
        ]:
            raise InvalidStateTransition(
                message=f"Can only fail pending or running jobs, current status: {self.status.value}",
                code="INVALID_JOB_FAIL",
                context={
                    "entity_type": "QueuedJob",
                    "entity_id": str(self.id),
                    "current_state": self.status.value,
                    "attempted_state": StepExecutionStatus.FAILED.value,
                },
            )

        self.status = StepExecutionStatus.FAILED
        self.error_message = error_message
        self.failed_at = datetime.now()
        self.updated_at = datetime.now()

    def can_retry(self) -> bool:
        return (
            self.retry_count < self.max_retries
            and self.status == StepExecutionStatus.FAILED
        )

    def retry(self) -> None:
        if not self.can_retry():
            raise InvalidStateTransition(
                message=f"Job cannot be retried (status: {self.status.value}, retries: {self.retry_count}/{self.max_retries})",
                code="INVALID_JOB_RETRY",
                context={
                    "entity_type": "QueuedJob",
                    "entity_id": str(self.id),
                    "current_state": self.status.value,
                    "attempted_state": StepExecutionStatus.PENDING.value,
                },
            )

        self.retry_count += 1
        self.status = StepExecutionStatus.PENDING
        self.worker_id = None
        self.assigned_at = None
        self.started_at = None
        self.error_message = None
        self.updated_at = datetime.now()
