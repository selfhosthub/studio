# api/app/domain/instance/models.py

"""Workflow instance aggregate root and instance-level status/operation types."""

import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from pydantic import ConfigDict, Field, field_validator

from app.domain.common.base_entity import AggregateRoot
from app.domain.common.exceptions import (
    BusinessRuleViolation,
    InvalidStateTransition,
)
from app.domain.instance.events import (
    InstanceStartedEvent,
    InstanceCompletedEvent,
    InstanceFailedEvent,
    InstancePausedEvent,
    InstanceResumedEvent,
    InstanceCancelledEvent,
    InstanceStatusChangedEvent,
    InstanceStepStartedEvent,
    InstanceStepCompletedEvent,
    InstanceStepFailedEvent,
)
from app.domain.instance_step.models import StepExecutionStatus

if TYPE_CHECKING:
    from app.domain.instance_step.step_execution import StepExecution


class InstanceStatus(str, Enum):
    """Workflow instance status. Instances don't wait for workers; jobs do."""

    PENDING = "pending"  # Queued for start (scheduled/queued workflows)
    PROCESSING = "processing"
    WAITING_FOR_WEBHOOK = "waiting_for_webhook"
    WAITING_FOR_APPROVAL = "waiting_for_approval"
    WAITING_FOR_MANUAL_TRIGGER = "waiting_for_manual_trigger"
    DEBUG_PAUSED = "debug_paused"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

    # Deprecated; do not use.
    INACTIVE = "inactive"
    ACTIVE = "active"


class OperationType(str, Enum):
    """Active re-execution operation on an instance. is_isolated controls whether the workflow advances after the target completes."""

    REGENERATE_RESOURCES = "regenerate_resources"
    REGENERATE_ITERATION = "regenerate_iteration"
    RETRY_JOB = "retry_job"
    RERUN_JOB = "rerun_job"
    RERUN_STEP = "rerun_step"
    RERUN_AND_CONTINUE = "rerun_and_continue"

    @property
    def is_isolated(self) -> bool:
        """True for in-place operations: completion ends the operation with no downstream enqueue.

        RETRY_JOB and RERUN_AND_CONTINUE are not isolated - they intentionally advance after success.
        """
        return self in (
            OperationType.REGENERATE_RESOURCES,
            OperationType.REGENERATE_ITERATION,
            OperationType.RERUN_JOB,
            OperationType.RERUN_STEP,
        )


class Instance(AggregateRoot):
    """Aggregate root for a workflow execution. Step state lives on step_entities."""

    workflow_id: uuid.UUID
    organization_id: uuid.UUID
    user_id: Optional[uuid.UUID] = None

    # Populated from JOIN, not persisted.
    workflow_name: Optional[str] = None

    status: InstanceStatus = InstanceStatus.INACTIVE
    version: int = 1
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    paused_at: Optional[datetime] = None

    input_data: Dict[str, Any] = Field(default_factory=dict)
    output_data: Dict[str, Any] = Field(default_factory=dict)

    current_step_ids: List[str] = Field(default_factory=list)
    completed_step_ids: List[str] = Field(default_factory=list)

    # Source of truth for step state. Forward ref; TYPE_CHECKING import gives the narrowed type for pyright.
    step_entities: "Dict[str, StepExecution]" = Field(
        default_factory=dict, exclude=True
    )
    failed_step_ids: List[str] = Field(default_factory=list)

    # Snapshot of workflow definition at creation time; insulates execution from later workflow edits.
    workflow_snapshot: Optional[Dict[str, Any]] = None

    error_data: Optional[Dict[str, Any]] = None

    client_metadata: Dict[str, Any] = Field(default_factory=dict)

    # Inherited from workflow's DEBUG status. When True, instance pauses after each step.
    is_debug_mode: bool = False

    model_config = ConfigDict(arbitrary_types_allowed=True)

    @field_validator("status", mode="before")
    @classmethod
    def convert_status_to_enum(cls, v):
        if isinstance(v, str) and not isinstance(v, InstanceStatus):
            return InstanceStatus(v)
        return v

    def build_step_status_dict(self) -> Dict[str, str]:
        if not self.step_entities:
            return {}
        return {
            key: (
                entity.status.value
                if hasattr(entity.status, "value")
                else str(entity.status)
            )
            for key, entity in self.step_entities.items()
        }

    def build_completed_step_ids(self) -> List[str]:
        if not self.step_entities:
            return []
        return [
            key
            for key, entity in self.step_entities.items()
            if hasattr(entity, "allows_dependency_start")
            and entity.allows_dependency_start()
        ]

    @classmethod
    def create(
        cls,
        workflow_id: uuid.UUID,
        organization_id: uuid.UUID,
        user_id: Optional[uuid.UUID] = None,
        input_data: Optional[Dict[str, Any]] = None,
        client_metadata: Optional[Dict[str, Any]] = None,
        is_debug_mode: bool = False,
    ) -> "Instance":
        return cls(
            workflow_id=workflow_id,
            organization_id=organization_id,
            user_id=user_id,
            status=InstanceStatus.INACTIVE,
            input_data=input_data or {},
            client_metadata=client_metadata or {},
            is_debug_mode=is_debug_mode,
        )

    def start(self, started_by: Optional[uuid.UUID] = None) -> None:
        """Start. Allowed from INACTIVE (default) or PENDING (queued workflows)."""
        if self.status not in [InstanceStatus.INACTIVE, InstanceStatus.PENDING]:
            raise InvalidStateTransition(
                message=f"Cannot start instance with status {self.status}",
                code="INVALID_INSTANCE_START",
                context={
                    "instance_id": str(self.id),
                    "current_status": self.status,
                },
            )

        self.status = InstanceStatus.PROCESSING
        self.started_at = datetime.now(UTC)
        self.updated_at = datetime.now(UTC)

        self.add_event(
            InstanceStartedEvent(
                aggregate_id=self.id,
                aggregate_type="instance",
                instance_id=self.id,
                workflow_id=self.workflow_id,
                organization_id=self.organization_id,
                started_by=started_by or self.user_id,
                start_time=self.started_at,
                data={
                    "step_count": len(self.step_entities),
                },
            )
        )

    def pause(self, paused_by: Optional[uuid.UUID] = None) -> None:
        if self.status != InstanceStatus.PROCESSING:
            raise InvalidStateTransition(
                message=f"Cannot pause instance with status {self.status}",
                code="INVALID_INSTANCE_PAUSE",
                context={
                    "instance_id": str(self.id),
                    "current_status": self.status,
                },
            )

        self.status = InstanceStatus.PAUSED
        self.paused_at = datetime.now(UTC)
        self.updated_at = datetime.now(UTC)

        self.add_event(
            InstancePausedEvent(
                aggregate_id=self.id,
                aggregate_type="instance",
                instance_id=self.id,
                workflow_id=self.workflow_id,
                organization_id=self.organization_id,
                paused_by=paused_by or self.user_id,
                pause_time=self.paused_at,
                data={},
            )
        )

    def resume(self, resumed_by: Optional[uuid.UUID] = None) -> None:
        if self.status != InstanceStatus.PAUSED:
            raise InvalidStateTransition(
                message=f"Cannot resume instance with status {self.status}",
                code="INVALID_INSTANCE_RESUME",
                context={
                    "instance_id": str(self.id),
                    "current_status": self.status,
                },
            )

        self.status = InstanceStatus.PROCESSING
        self.paused_at = None
        self.updated_at = datetime.now(UTC)

        self.add_event(
            InstanceResumedEvent(
                aggregate_id=self.id,
                aggregate_type="instance",
                instance_id=self.id,
                workflow_id=self.workflow_id,
                organization_id=self.organization_id,
                resumed_by=resumed_by or self.user_id,
                resume_time=datetime.now(UTC),
                data={},
            )
        )

    def wait_for_approval(self, step_id: str) -> None:
        """Transition to WAITING_FOR_APPROVAL. Idempotent so handlers can re-enter the target state."""
        if self.status == InstanceStatus.WAITING_FOR_APPROVAL:
            return
        if self.status != InstanceStatus.PROCESSING:
            raise InvalidStateTransition(
                message=f"Cannot wait for approval from status {self.status}",
                code="INVALID_WAIT_FOR_APPROVAL",
                context={
                    "instance_id": str(self.id),
                    "current_status": self.status,
                    "step_id": step_id,
                },
            )

        old_status = self.status
        self.status = InstanceStatus.WAITING_FOR_APPROVAL
        self.updated_at = datetime.now(UTC)

        self.add_event(
            InstanceStatusChangedEvent(
                aggregate_id=self.id,
                aggregate_type="instance",
                instance_id=self.id,
                workflow_id=self.workflow_id,
                organization_id=self.organization_id,
                old_status=old_status.value,
                new_status=self.status.value,
                data={"waiting_step_id": step_id},
            )
        )

    def wait_for_manual_trigger(self, step_id: str) -> None:
        """Transition to WAITING_FOR_MANUAL_TRIGGER. Idempotent for the same reason as wait_for_approval."""
        if self.status == InstanceStatus.WAITING_FOR_MANUAL_TRIGGER:
            return
        if self.status != InstanceStatus.PROCESSING:
            raise InvalidStateTransition(
                message=f"Cannot wait for manual trigger from status {self.status}",
                code="INVALID_WAIT_FOR_MANUAL_TRIGGER",
                context={
                    "instance_id": str(self.id),
                    "current_status": self.status,
                    "step_id": step_id,
                },
            )

        old_status = self.status
        self.status = InstanceStatus.WAITING_FOR_MANUAL_TRIGGER
        self.updated_at = datetime.now(UTC)

        self.add_event(
            InstanceStatusChangedEvent(
                aggregate_id=self.id,
                aggregate_type="instance",
                instance_id=self.id,
                workflow_id=self.workflow_id,
                organization_id=self.organization_id,
                old_status=old_status.value,
                new_status=self.status.value,
                data={"waiting_step_id": step_id},
            )
        )

    def cancel(
        self, cancelled_by: Optional[uuid.UUID] = None, reason: Optional[str] = None
    ) -> None:
        if self.status in [
            InstanceStatus.COMPLETED,
            InstanceStatus.FAILED,
            InstanceStatus.CANCELLED,
        ]:
            raise InvalidStateTransition(
                message=f"Cannot cancel instance with status {self.status}",
                code="INVALID_INSTANCE_CANCEL",
                context={
                    "instance_id": str(self.id),
                    "current_status": self.status,
                },
            )

        self.status = InstanceStatus.CANCELLED
        self.completed_at = datetime.now(UTC)
        self.updated_at = datetime.now(UTC)

        self.add_event(
            InstanceCancelledEvent(
                aggregate_id=self.id,
                aggregate_type="instance",
                instance_id=self.id,
                workflow_id=self.workflow_id,
                organization_id=self.organization_id,
                cancelled_by=cancelled_by or self.user_id,
                cancellation_time=self.completed_at,
                reason=reason,
                data={},
            )
        )

    @property
    def has_active_operation(self) -> bool:
        """True if any step entity carries an active operation; False when step_entities is empty."""
        return any(
            se.active_operation is not None for se in self.step_entities.values()
        )

    def transition_to_processing(self) -> None:
        """Move to PROCESSING. Idempotent; not gated by terminal status - rerun-from-terminal flows depend on this."""
        if self.status == InstanceStatus.PROCESSING:
            return
        self.status = InstanceStatus.PROCESSING
        self.updated_at = datetime.now(UTC)

    def complete(
        self,
        output_data: Optional[Dict[str, Any]] = None,
        force: bool = False,
    ) -> None:
        """Mark completed. Idempotent. force=True skips the all-steps-complete guard (for stop-step early completion)."""
        if self.status == InstanceStatus.COMPLETED:
            if output_data:
                self.output_data.update(output_data)
            return

        allowed_statuses = [
            InstanceStatus.PROCESSING,
            InstanceStatus.WAITING_FOR_APPROVAL,
            InstanceStatus.WAITING_FOR_MANUAL_TRIGGER,
        ]
        if self.status not in allowed_statuses:
            raise InvalidStateTransition(
                message=f"Cannot complete instance with status {self.status}",
                code="INVALID_INSTANCE_COMPLETE",
                context={
                    "instance_id": str(self.id),
                    "current_status": self.status,
                },
            )

        if not force:
            step_status_dict = self.build_step_status_dict()
            incomplete_steps = [
                step_id
                for step_id, status in step_status_dict.items()
                if status
                not in [
                    StepExecutionStatus.COMPLETED.value,
                    StepExecutionStatus.SKIPPED.value,
                    StepExecutionStatus.STOPPED.value,
                    StepExecutionStatus.WAITING_FOR_MANUAL_TRIGGER.value,
                ]
            ]
            if incomplete_steps:
                raise BusinessRuleViolation(
                    message="Cannot complete instance with incomplete steps",
                    code="INCOMPLETE_STEPS",
                    context={
                        "instance_id": str(self.id),
                        "incomplete_steps": incomplete_steps,
                    },
                )

        self.status = InstanceStatus.COMPLETED
        self.completed_at = datetime.now(UTC)
        if output_data:
            self.output_data.update(output_data)
        self.updated_at = datetime.now(UTC)

        self.add_event(
            InstanceCompletedEvent(
                aggregate_id=self.id,
                aggregate_type="instance",
                instance_id=self.id,
                workflow_id=self.workflow_id,
                organization_id=self.organization_id,
                completion_time=self.completed_at,
                output_data=self.output_data,
                data={
                    "duration_seconds": (
                        (self.completed_at - self.started_at).total_seconds()
                        if self.started_at
                        else None
                    ),
                    "completed_steps": len(self.completed_step_ids),
                },
            )
        )

    def fail(
        self,
        error_message: str,
        error_data: Optional[Dict[str, Any]] = None,
    ) -> None:
        if self.status in [
            InstanceStatus.COMPLETED,
            InstanceStatus.FAILED,
            InstanceStatus.CANCELLED,
        ]:
            raise InvalidStateTransition(
                message=f"Cannot fail instance with status {self.status}",
                code="INVALID_INSTANCE_FAIL",
                context={
                    "instance_id": str(self.id),
                    "current_status": self.status,
                },
            )

        self.status = InstanceStatus.FAILED
        self.completed_at = datetime.now(UTC)
        self.error_data = error_data or {"error": error_message}
        self.updated_at = datetime.now(UTC)

        self.add_event(
            InstanceFailedEvent(
                aggregate_id=self.id,
                aggregate_type="instance",
                instance_id=self.id,
                workflow_id=self.workflow_id,
                organization_id=self.organization_id,
                failure_time=self.completed_at,
                error_message=error_message,
                error_data=self.error_data,
                data={
                    "completed_steps": len(self.completed_step_ids),
                    "failed_steps": len(self.failed_step_ids),
                },
            )
        )

    def handle_step_started(
        self, step_id: str, step_execution: "StepExecution"
    ) -> None:
        """Update current_step_ids and emit event."""
        if step_id not in self.current_step_ids:
            self.current_step_ids.append(step_id)
        self.updated_at = datetime.now(UTC)

        self.add_event(
            InstanceStepStartedEvent(
                aggregate_id=self.id,
                aggregate_type="instance",
                instance_id=self.id,
                workflow_id=self.workflow_id,
                organization_id=self.organization_id,
                step_id=step_id,
                step_name=step_execution.step_name,
                start_time=step_execution.started_at or datetime.now(UTC),
                data={},
            )
        )

    def handle_step_completed(
        self, step_id: str, step_execution: "StepExecution"
    ) -> None:
        """Update current/completed step lists and emit event."""
        if step_id in self.current_step_ids:
            self.current_step_ids.remove(step_id)
        if step_id not in self.completed_step_ids:
            self.completed_step_ids.append(step_id)
        self.updated_at = datetime.now(UTC)

        self.add_event(
            InstanceStepCompletedEvent(
                aggregate_id=self.id,
                aggregate_type="instance",
                instance_id=self.id,
                workflow_id=self.workflow_id,
                organization_id=self.organization_id,
                step_id=step_id,
                step_name=step_execution.step_name,
                completion_time=step_execution.completed_at or datetime.now(UTC),
                output_data=step_execution.result,
                data={},
            )
        )

    def handle_step_failed(self, step_id: str, step_execution: "StepExecution") -> None:
        """Update current/failed step lists and emit event."""
        if step_id in self.current_step_ids:
            self.current_step_ids.remove(step_id)
        if step_id not in self.failed_step_ids:
            self.failed_step_ids.append(step_id)
        self.updated_at = datetime.now(UTC)

        self.add_event(
            InstanceStepFailedEvent(
                aggregate_id=self.id,
                aggregate_type="instance",
                instance_id=self.id,
                workflow_id=self.workflow_id,
                organization_id=self.organization_id,
                step_id=step_id,
                step_name=step_execution.step_name,
                failure_time=step_execution.completed_at or datetime.now(UTC),
                error_message=step_execution.error_message,
                error_data=None,
                data={},
            )
        )

    def can_step_start(
        self,
        step_id: str,
        depends_on: List[str],
        step_entities: "Optional[Dict[str, StepExecution]]" = None,
    ) -> bool:
        """True if all dependencies are satisfied. Prefers live entity status; falls back to completed_step_ids list."""
        if not depends_on:
            return True

        for dep_step_id in depends_on:
            if step_entities and dep_step_id in step_entities:
                dep_entity = step_entities[dep_step_id]
                if not dep_entity.allows_dependency_start():
                    return False
            else:
                if dep_step_id not in self.completed_step_ids:
                    return False

        return True
