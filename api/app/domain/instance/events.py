# api/app/domain/instance/events.py

"""Domain events for the instance context."""
from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID

from app.domain.common.events import DomainEvent


class InstanceEvent(DomainEvent):
    instance_id: UUID
    workflow_id: UUID
    organization_id: UUID


class InstanceCreatedEvent(InstanceEvent):
    event_type: str = "instance.created"
    input_data: Optional[Dict[str, Any]] = None
    created_by: Optional[UUID] = None


class InstanceStartedEvent(InstanceEvent):
    event_type: str = "instance.started"
    started_by: Optional[UUID] = None
    start_time: datetime


class InstanceCompletedEvent(InstanceEvent):
    event_type: str = "instance.completed"
    completion_time: datetime
    output_data: Optional[Dict[str, Any]] = None


class InstanceFailedEvent(InstanceEvent):
    event_type: str = "instance.failed"
    failure_time: datetime
    error_message: str
    error_data: Optional[Dict[str, Any]] = None


class InstancePausedEvent(InstanceEvent):
    event_type: str = "instance.paused"
    paused_by: Optional[UUID] = None
    pause_time: datetime


class InstanceResumedEvent(InstanceEvent):
    event_type: str = "instance.resumed"
    resumed_by: Optional[UUID] = None
    resume_time: datetime


class InstanceCancelledEvent(InstanceEvent):
    event_type: str = "instance.cancelled"
    cancelled_by: Optional[UUID] = None
    cancellation_time: datetime
    reason: Optional[str] = None


class InstanceStatusChangedEvent(InstanceEvent):
    event_type: str = "instance.status_changed"
    old_status: str
    new_status: str


class InstanceStepStartedEvent(InstanceEvent):
    event_type: str = "instance.step_started"
    step_id: str
    step_name: str
    start_time: datetime


class InstanceStepCompletedEvent(InstanceEvent):
    event_type: str = "instance.step_completed"
    step_id: str
    step_name: str
    completion_time: datetime
    output_data: Optional[Dict[str, Any]] = None


class InstanceStepFailedEvent(InstanceEvent):
    event_type: str = "instance.step_failed"
    step_id: str
    step_name: str
    failure_time: datetime
    error_message: Optional[str] = None
    error_data: Optional[Dict[str, Any]] = None


class InstanceStepRetriedEvent(InstanceEvent):
    event_type: str = "instance.step_retried"
    step_id: str
    step_name: str
    retry_count: int
    retry_time: datetime


class JobExecutionEvent(DomainEvent):
    instance_id: UUID
    job_id: UUID
    step_id: str
    step_name: str


class JobExecutionCreatedEvent(JobExecutionEvent):
    event_type: str = "job.created"


class JobExecutionStartedEvent(JobExecutionEvent):
    event_type: str = "job.started"
    started_at: datetime


class JobExecutionCompletedEvent(JobExecutionEvent):
    event_type: str = "job.completed"
    completed_at: datetime
    result: Optional[Dict[str, Any]] = None


class JobExecutionFailedEvent(JobExecutionEvent):
    event_type: str = "job.failed"
    failed_at: datetime
    error_message: str
    error_data: Optional[Dict[str, Any]] = None


class JobExecutionRetriedEvent(JobExecutionEvent):
    event_type: str = "job.retried"
    retry_count: int
    retried_at: datetime


class JobExecutionCancelledEvent(JobExecutionEvent):
    event_type: str = "job.cancelled"
    cancelled_at: datetime
    reason: Optional[str] = None


class JobStatusChangedEvent(DomainEvent):
    event_type: str = "job.status_changed"
    job_id: UUID
    instance_id: UUID
    organization_id: UUID
    old_status: Optional[str] = None
    new_status: str
