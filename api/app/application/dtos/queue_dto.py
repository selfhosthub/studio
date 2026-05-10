# api/app/application/dtos/queue_dto.py

"""DTOs for queue operations."""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.domain.instance_step.step_execution import StepExecutionStatus
from app.domain.queue.models import (
    Queue,
    QueueStatus,
    QueueType,
    Worker,
    WorkerStatus,
    QueuedJob,
)
from app.infrastructure.security.redaction import redact_sensitive_data


class QueueBase(BaseModel):
    name: str
    organization_id: uuid.UUID
    queue_type: QueueType = QueueType.DEFAULT
    description: Optional[str] = None
    max_concurrency: int = 10
    max_pending_jobs: int = 1000
    default_timeout_seconds: int = 3600
    resource_requirements: Optional[Dict[str, Any]] = None
    scaling_policy: Dict[str, Any] = Field(default_factory=dict)
    tags: List[str] = Field(default_factory=list)
    client_metadata: Dict[str, Any] = Field(default_factory=dict)


class QueueCreate(QueueBase):
    created_by: uuid.UUID


class QueueUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    max_concurrency: Optional[int] = None
    max_pending_jobs: Optional[int] = None
    default_timeout_seconds: Optional[int] = None
    resource_requirements: Optional[Dict[str, Any]] = None
    scaling_policy: Optional[Dict[str, Any]] = None
    tags: Optional[List[str]] = None
    client_metadata: Optional[Dict[str, Any]] = None
    updated_by: uuid.UUID


class QueueResponse(QueueBase):
    id: uuid.UUID
    status: QueueStatus
    total_jobs_processed: int
    failed_jobs_count: int
    active_workers: int
    created_by: uuid.UUID
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    paused_at: Optional[datetime] = None
    paused_by: Optional[uuid.UUID] = None

    @classmethod
    def from_domain(cls, queue: Queue) -> "QueueResponse":
        resource_req = None
        if queue.resource_requirements:
            resource_req = queue.resource_requirements.model_dump()

        return cls(
            id=queue.id,
            name=queue.name,
            organization_id=queue.organization_id,
            queue_type=queue.queue_type,
            description=queue.description,
            status=queue.status,
            max_concurrency=queue.max_concurrency,
            max_pending_jobs=queue.max_pending_jobs,
            default_timeout_seconds=queue.default_timeout_seconds,
            resource_requirements=resource_req,
            scaling_policy=queue.scaling_policy,
            total_jobs_processed=queue.total_jobs_processed,
            failed_jobs_count=queue.failed_jobs_count,
            active_workers=queue.active_workers,
            tags=queue.tags,
            client_metadata=queue.client_metadata,
            created_by=queue.created_by,
            created_at=queue.created_at,
            updated_at=queue.updated_at,
            paused_at=queue.paused_at,
            paused_by=queue.paused_by,
        )


class QueuePause(BaseModel):
    paused_by: uuid.UUID
    reason: Optional[str] = None


class QueueResume(BaseModel):
    resumed_by: uuid.UUID


class QueueDrain(BaseModel):
    drained_by: uuid.UUID


class QueueStop(BaseModel):
    stopped_by: uuid.UUID
    force: bool = False


class WorkerRegistration(BaseModel):
    secret: str
    name: str
    queue_id: Optional[uuid.UUID] = None  # Optional for general-purpose workers
    capabilities: Dict[str, Any] = Field(default_factory=dict)
    queue_labels: List[str] = Field(default_factory=list)


class WorkerHeartbeat(BaseModel):
    status: WorkerStatus
    current_job_id: Optional[uuid.UUID] = None


class WorkerResponse(BaseModel):
    id: uuid.UUID
    name: str
    queue_id: Optional[uuid.UUID] = None  # Optional for general-purpose workers
    status: WorkerStatus
    last_heartbeat: Optional[datetime] = None
    current_job_id: Optional[uuid.UUID] = None

    @classmethod
    def from_domain(cls, worker: Worker) -> "WorkerResponse":
        return cls(
            id=worker.id,
            name=worker.name,
            queue_id=worker.queue_id,
            status=worker.status,
            last_heartbeat=worker.last_heartbeat,
            current_job_id=worker.current_job_id,
        )


class QueuedJobBase(BaseModel):
    organization_id: uuid.UUID
    priority: int = 0
    input_data: Dict[str, Any] = Field(default_factory=dict)
    resource_requirements: Optional[Dict[str, Any]] = None
    timeout_seconds: Optional[int] = None
    max_retries: int = 3
    tags: List[str] = Field(default_factory=list)
    client_metadata: Dict[str, Any] = Field(default_factory=dict)


class QueuedJobCreate(QueuedJobBase):
    enqueued_by: uuid.UUID
    blueprint_id: Optional[uuid.UUID] = None
    workflow_id: Optional[uuid.UUID] = None


class QueuedJobUpdate(BaseModel):
    status: Optional[StepExecutionStatus] = None
    worker_id: Optional[uuid.UUID] = None
    output_data: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    retry_count: Optional[int] = None
    client_metadata: Optional[Dict[str, Any]] = None


class QueuedJobResponse(QueuedJobBase):
    id: uuid.UUID
    status: StepExecutionStatus
    blueprint_id: Optional[uuid.UUID] = None
    workflow_id: Optional[uuid.UUID] = None
    worker_id: Optional[uuid.UUID] = None
    output_data: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    retry_count: int = 0
    enqueued_at: datetime
    enqueued_by: uuid.UUID
    assigned_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    failed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @classmethod
    def from_domain(cls, job: QueuedJob) -> "QueuedJobResponse":
        resource_req = None
        if job.resource_requirements:
            resource_req = job.resource_requirements.model_dump()

        return cls(
            id=job.id,
            organization_id=job.organization_id,
            blueprint_id=getattr(job, "blueprint_id", None),
            workflow_id=getattr(job, "workflow_id", None),
            status=job.status,
            priority=job.priority,
            worker_id=job.worker_id,
            input_data=redact_sensitive_data(job.input_data, include_pii=False) or {},
            output_data=job.output_data,
            error_message=job.error_message,
            resource_requirements=resource_req,
            timeout_seconds=job.timeout_seconds,
            retry_count=job.retry_count,
            max_retries=job.max_retries,
            enqueued_at=job.enqueued_at,
            enqueued_by=job.enqueued_by,
            assigned_at=job.assigned_at,
            started_at=job.started_at,
            completed_at=job.completed_at,
            failed_at=job.failed_at,
            tags=job.tags,
            client_metadata=job.client_metadata,
            created_at=job.created_at,
            updated_at=job.updated_at,
        )


class QueueStats(BaseModel):
    queue_id: uuid.UUID
    pending_jobs: int
    running_jobs: int
    completed_jobs: int
    failed_jobs: int
    active_workers: int
    idle_workers: int
    average_wait_time_seconds: float
    average_execution_time_seconds: float
