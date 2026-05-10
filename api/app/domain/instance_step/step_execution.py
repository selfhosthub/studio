# api/app/domain/instance_step/step_execution.py

"""StepExecution domain entity: unified lifecycle + worker-attempt state for a workflow step.

parameters is the top layer of the three-layer parameter model (iteration row middle, worker payload bottom).
active_operation is the sole store for active rerun/retry/regenerate; instance derives has_active_operation from it.
Forward transitions use the VALID_TRANSITIONS table; reset-to-PENDING bypasses it by design - see reset_to_pending.
"""

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from pydantic import ConfigDict, Field, field_validator

from app.config.settings import settings
from app.domain.common.base_entity import AggregateRoot
from app.domain.common.exceptions import (
    BusinessRuleViolation,
    InvalidStateTransition,
)
from app.domain.instance.iteration_execution import IterationExecution
from app.domain.instance_step.models import (
    VALID_TRANSITIONS,
    StepExecutionStatus,
    _CANNOT_RESET_MID_FLIGHT,
)

if TYPE_CHECKING:
    from app.domain.instance.models import InstanceStatus, OperationType


# Terminal statuses - single source of truth for is_terminal().
_TERMINAL_STATUSES: frozenset[StepExecutionStatus] = frozenset(
    {
        StepExecutionStatus.COMPLETED,
        StepExecutionStatus.FAILED,
        StepExecutionStatus.SKIPPED,
        StepExecutionStatus.CANCELLED,
        StepExecutionStatus.TIMEOUT,
    }
)

# Statuses from which rerun() (JobExecution-style, no retry_count bump)
# may restart work.
_RERUNNABLE_STATUSES: frozenset[StepExecutionStatus] = frozenset(
    {
        StepExecutionStatus.COMPLETED,
        StepExecutionStatus.FAILED,
        StepExecutionStatus.CANCELLED,
        StepExecutionStatus.SKIPPED,
        StepExecutionStatus.TIMEOUT,
    }
)


class StepExecution(AggregateRoot):
    """Aggregate root for a step's execution. One row per step per instance; iterations are aggregate children."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    instance_id: uuid.UUID
    step_key: str
    # Display name; defaults to empty. DTOs fall back to step_config.name / step_key when blank.
    step_name: str = ""

    @property
    def instance_step_id(self) -> uuid.UUID:
        """Legacy alias for id."""
        return self.id

    @instance_step_id.setter
    def instance_step_id(self, value: Optional[uuid.UUID]) -> None:
        if value is not None:
            self.id = value

    status: StepExecutionStatus = StepExecutionStatus.PENDING

    @field_validator("status", mode="before")
    @classmethod
    def convert_status_to_enum(cls, v):
        if isinstance(v, str) and not isinstance(v, StepExecutionStatus):
            return StepExecutionStatus(v)
        return v

    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    # Non-file outputs. File outputs live in org_files keyed on this row.
    output_data: Dict[str, Any] = Field(default_factory=dict)

    # Raw provider response.
    result: Optional[Dict[str, Any]] = None

    # Output-extractor projections for downstream steps.
    extracted_outputs: Dict[str, Any] = Field(default_factory=dict)

    error_message: Optional[str] = None

    retry_count: int = 0
    max_retries: int = Field(default_factory=lambda: settings.DEFAULT_MAX_RETRIES)

    # Free-form: timeouts, failure-policy flags, prompt-variables cache, etc.
    execution_data: Dict[str, Any] = Field(default_factory=dict)

    # Worker-reported debug data: what the provider was told.
    input_data: Dict[str, Any] = Field(default_factory=dict)
    request_body: Optional[Dict[str, Any]] = None

    # Iteration summary; per-iteration state lives in `iterations`.
    iteration_count: Optional[int] = None
    iteration_source: Optional[Dict[str, Any]] = None
    iteration_requests: Optional[List[Dict[str, Any]]] = None

    iterations: List[IterationExecution] = Field(default_factory=list)

    # Top layer of the three-layer parameter model.
    parameters: Dict[str, Any] = Field(default_factory=dict)

    # Sole storage for active rerun/retry/regenerate.
    active_operation: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(arbitrary_types_allowed=True)

    @classmethod
    def create(
        cls,
        instance_id: uuid.UUID,
        step_key: Optional[str] = None,
        step_name: Optional[str] = None,
        status: StepExecutionStatus = StepExecutionStatus.PENDING,
        max_retries: Optional[int] = None,
        execution_data: Optional[Dict[str, Any]] = None,
        parameters: Optional[Dict[str, Any]] = None,
        *,
        step_id: Optional[str] = None,
        # Legacy: accepted and ignored so old call sites keep working.
        job_config: Any = None,
    ) -> "StepExecution":
        """Build a new step execution. step_id is a legacy alias for step_key; one of them is required."""
        resolved_key = step_key if step_key is not None else step_id
        if resolved_key is None:
            raise TypeError("StepExecution.create requires either step_key or step_id")
        return cls(
            instance_id=instance_id,
            step_key=resolved_key,
            step_name=step_name if step_name is not None else resolved_key,
            status=status,
            max_retries=(
                max_retries if max_retries is not None else settings.DEFAULT_MAX_RETRIES
            ),
            execution_data=execution_data or {},
            parameters=parameters or {},
        )

    def _validate_transition(self, target: StepExecutionStatus) -> None:
        """Forward-lifecycle gate. Reset-to-PENDING bypasses this - see reset_to_pending."""
        valid_targets = VALID_TRANSITIONS.get(self.status, set())
        if target not in valid_targets:
            raise InvalidStateTransition(
                message=(
                    f"Cannot transition from {self.status.value} to " f"{target.value}"
                ),
                code="INVALID_STEP_EXECUTION_TRANSITION",
                context={
                    "entity_type": "StepExecution",
                    "entity_id": str(self.id),
                    "current_state": self.status.value,
                    "attempted_state": target.value,
                },
            )

    def queue(self) -> None:
        """Mark queued. Idempotent: result-consumer / WS reconnect can replay a QUEUED publish."""
        if self.status == StepExecutionStatus.QUEUED:
            return
        self._validate_transition(StepExecutionStatus.QUEUED)
        self.status = StepExecutionStatus.QUEUED
        self.updated_at = datetime.now(UTC)

    def start(self) -> None:
        """Mark running. Idempotent: duplicate PROCESSING events from heartbeat/replay must not abort the result pipeline."""
        if self.status == StepExecutionStatus.RUNNING:
            return
        self._validate_transition(StepExecutionStatus.RUNNING)
        self.status = StepExecutionStatus.RUNNING
        self.started_at = datetime.now(UTC)
        self.error_message = None
        self.updated_at = datetime.now(UTC)

    def restart(self) -> None:
        """Fallback COMPLETED/FAILED → RUNNING when the caller didn't reset first. Prefer reset_to_pending()."""
        if self.status not in (
            StepExecutionStatus.COMPLETED,
            StepExecutionStatus.FAILED,
        ):
            raise InvalidStateTransition(
                message=f"Cannot restart step with status {self.status.value}",
                code="INVALID_STEP_EXECUTION_RESTART",
                context={
                    "entity_type": "StepExecution",
                    "entity_id": str(self.id),
                    "current_state": self.status.value,
                    "attempted_state": StepExecutionStatus.RUNNING.value,
                },
            )
        self.status = StepExecutionStatus.RUNNING
        self.started_at = datetime.now(UTC)
        self.completed_at = None
        self.error_message = None
        self.updated_at = datetime.now(UTC)

    def complete(
        self,
        output_data: Optional[Dict[str, Any]] = None,
        result: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Mark COMPLETED. Idempotent: a repeat call with new output_data overwrites."""
        if self.status == StepExecutionStatus.COMPLETED:
            if output_data:
                self.output_data = output_data
            if result is not None:
                self.result = result
            return
        self._validate_transition(StepExecutionStatus.COMPLETED)
        self.status = StepExecutionStatus.COMPLETED
        self.completed_at = datetime.now(UTC)
        if output_data:
            self.output_data = output_data
        if result is not None:
            self.result = result
        self.updated_at = datetime.now(UTC)

    def fail(self, error_message: str) -> None:
        """Mark FAILED. Permissive - does NOT validate the source state; failures can land from any non-terminal state."""
        self.status = StepExecutionStatus.FAILED
        self.error_message = error_message
        self.completed_at = datetime.now(UTC)
        self.updated_at = datetime.now(UTC)

    def skip(self) -> None:
        """Mark SKIPPED. Idempotent: a cascaded rerun can revisit an already-skipped step."""
        if self.status == StepExecutionStatus.SKIPPED:
            return
        self._validate_transition(StepExecutionStatus.SKIPPED)
        self.status = StepExecutionStatus.SKIPPED
        self.completed_at = datetime.now(UTC)
        self.updated_at = datetime.now(UTC)

    def stop(self) -> None:
        """Mark STOPPED (resumable). PENDING source is normal - stop fires from upstream completion before queueing."""
        if self.status == StepExecutionStatus.STOPPED:
            return
        if self.status not in (
            StepExecutionStatus.PENDING,
            StepExecutionStatus.RUNNING,
            StepExecutionStatus.QUEUED,
        ):
            raise InvalidStateTransition(
                message=f"Cannot stop step with status {self.status.value}",
                code="INVALID_STEP_EXECUTION_STOP",
                context={
                    "entity_type": "StepExecution",
                    "entity_id": str(self.id),
                    "current_state": self.status.value,
                    "attempted_state": StepExecutionStatus.STOPPED.value,
                },
            )
        self.status = StepExecutionStatus.STOPPED
        self.updated_at = datetime.now(UTC)

    def wait_for_approval(self) -> None:
        if self.status == StepExecutionStatus.WAITING_APPROVAL:
            return
        self._validate_transition(StepExecutionStatus.WAITING_APPROVAL)
        self.status = StepExecutionStatus.WAITING_APPROVAL
        self.updated_at = datetime.now(UTC)

    def wait_for_manual_trigger(self) -> None:
        if self.status == StepExecutionStatus.WAITING_FOR_MANUAL_TRIGGER:
            return
        self._validate_transition(StepExecutionStatus.WAITING_FOR_MANUAL_TRIGGER)
        self.status = StepExecutionStatus.WAITING_FOR_MANUAL_TRIGGER
        self.updated_at = datetime.now(UTC)

    def cancel(self) -> None:
        """Mark CANCELLED. Idempotent: instance-cancel sweeps every non-terminal step, may re-touch already-cancelled rows."""
        if self.status == StepExecutionStatus.CANCELLED:
            return
        self._validate_transition(StepExecutionStatus.CANCELLED)
        self.status = StepExecutionStatus.CANCELLED
        self.completed_at = datetime.now(UTC)
        self.updated_at = datetime.now(UTC)

    def timeout(self, error_message: Optional[str] = None) -> None:
        """Mark TIMEOUT (worker deadline exceeded). Error message optional; worker record may already carry one."""
        self._validate_transition(StepExecutionStatus.TIMEOUT)
        self.status = StepExecutionStatus.TIMEOUT
        self.completed_at = datetime.now(UTC)
        if error_message is not None:
            self.error_message = error_message
        self.updated_at = datetime.now(UTC)

    def block(self, reason: Optional[str] = None) -> None:
        """Mark BLOCKED (resumable: rate-limit, resource). Reason is stored on error_message so surfaces don't need a second field."""
        self._validate_transition(StepExecutionStatus.BLOCKED)
        self.status = StepExecutionStatus.BLOCKED
        if reason is not None:
            self.error_message = reason
        self.updated_at = datetime.now(UTC)

    def unblock(self) -> None:
        """Exit BLOCKED → QUEUED. Goes through the queue (not straight to RUNNING) so worker re-claim keeps the same handoff."""
        self._validate_transition(StepExecutionStatus.QUEUED)
        self.status = StepExecutionStatus.QUEUED
        self.error_message = None
        self.updated_at = datetime.now(UTC)

    def reset_to_pending(self) -> None:
        """Wipe back to PENDING for rerun/regeneration. Mid-flight (RUNNING/QUEUED) must be cancelled first to avoid racing the broker.

        Bypasses VALID_TRANSITIONS by design: rerun cascades hit steps in any
        state and must uniformly reach PENDING. `iterations` is NOT reset here -
        rerun/regenerate services own per-iteration policy. `output_data` is
        preserved; the caller's result processor decides what to do with it.
        """
        if self.status in _CANNOT_RESET_MID_FLIGHT:
            raise InvalidStateTransition(
                message=(
                    f"Cannot reset step in {self.status.value} - " f"cancel it first"
                ),
                code="RESET_MID_FLIGHT",
                context={
                    "entity_type": "StepExecution",
                    "entity_id": str(self.id),
                    "current_state": self.status.value,
                    "attempted_state": StepExecutionStatus.PENDING.value,
                },
            )
        self.status = StepExecutionStatus.PENDING
        self.started_at = None
        self.completed_at = None
        self.error_message = None
        self.updated_at = datetime.now(UTC)

    def retry(self) -> None:
        """Bump retry_count and return to PENDING. Caller must first check can_retry()."""
        if not self.can_retry():
            raise BusinessRuleViolation(
                message="Step cannot be retried",
                code="MAX_RETRIES_EXCEEDED",
                context={
                    "step_execution_id": str(self.id),
                    "retry_count": self.retry_count,
                    "max_retries": self.max_retries,
                },
            )
        self.retry_count += 1
        self.status = StepExecutionStatus.PENDING
        self.error_message = None
        self.started_at = None
        self.completed_at = None
        self.updated_at = datetime.now(UTC)

    def rerun(self) -> None:
        """Operator-initiated rerun without counting against retries. PENDING is a no-op."""
        if self.status == StepExecutionStatus.PENDING:
            return
        if self.status not in _RERUNNABLE_STATUSES:
            raise InvalidStateTransition(
                message=f"Cannot rerun step with status {self.status.value}",
                code="INVALID_STEP_EXECUTION_RERUN",
                context={
                    "entity_type": "StepExecution",
                    "entity_id": str(self.id),
                    "current_state": self.status.value,
                },
            )
        self.status = StepExecutionStatus.PENDING
        self.result = None
        self.error_message = None
        self.started_at = None
        self.completed_at = None
        self.updated_at = datetime.now(UTC)

    def begin_operation(
        self,
        op_type: "OperationType",
        *,
        original_status: str,
        **metadata: Any,
    ) -> None:
        """Begin a re-execution operation. Rejects if another is already active; only writes the tracking dict."""
        if self.active_operation is not None:
            raise BusinessRuleViolation(
                message="Cannot begin operation while another is active",
                code="OPERATION_ALREADY_ACTIVE",
                context={
                    "step_execution_id": str(self.id),
                    "step_key": self.step_key,
                    "active_operation": self.active_operation,
                    "requested_operation": op_type.value,
                },
            )

        self.active_operation = {
            "type": op_type.value,
            "original_status": original_status,
            "started_at": datetime.now(UTC).isoformat(),
            **metadata,
        }
        self.updated_at = datetime.now(UTC)

    def complete_operation_tracking(self) -> None:
        """Clear active_operation. Idempotent."""
        if self.active_operation is None:
            return
        self.active_operation = None
        self.updated_at = datetime.now(UTC)

    def cancel_operation(self) -> "InstanceStatus":
        """Cancel and return the instance status to restore. Service applies the result."""
        # Local import: avoids the cycle through Instance.
        from app.domain.instance.models import InstanceStatus

        if self.active_operation is None:
            raise BusinessRuleViolation(
                message="No active operation to cancel",
                code="NO_ACTIVE_OPERATION",
                context={
                    "step_execution_id": str(self.id),
                    "step_key": self.step_key,
                },
            )

        original = InstanceStatus(self.active_operation["original_status"])
        self.active_operation = None
        self.updated_at = datetime.now(UTC)
        return original

    def complete_operation(self) -> "InstanceStatus":
        """Complete and return the instance status to restore. FAILED → COMPLETED on success."""
        # Local import: avoids the cycle through Instance.
        from app.domain.instance.models import InstanceStatus

        if self.active_operation is None:
            raise BusinessRuleViolation(
                message="No active operation to complete",
                code="NO_ACTIVE_OPERATION",
                context={
                    "step_execution_id": str(self.id),
                    "step_key": self.step_key,
                },
            )

        original = InstanceStatus(self.active_operation["original_status"])
        self.active_operation = None
        self.updated_at = datetime.now(UTC)

        if original == InstanceStatus.FAILED:
            return InstanceStatus.COMPLETED
        return original

    def can_retry(self) -> bool:
        """True iff FAILED and within retry budget."""
        return (
            self.status == StepExecutionStatus.FAILED
            and self.retry_count < self.max_retries
        )

    def is_iterating(self) -> bool:
        return self.iteration_count is not None and self.iteration_count > 0

    def is_terminal(self) -> bool:
        """True for terminal states. TIMEOUT counts; BLOCKED does not (resumable)."""
        return self.status in _TERMINAL_STATUSES

    def can_proceed(self) -> bool:
        """True iff this step succeeded enough that downstream work may run."""
        return self.status in (
            StepExecutionStatus.COMPLETED,
            StepExecutionStatus.SKIPPED,
        )

    def allows_dependency_start(self) -> bool:
        """True iff dependents may run. Semantically distinct from can_proceed - kept separate so callers convey intent."""
        return self.status in (
            StepExecutionStatus.COMPLETED,
            StepExecutionStatus.SKIPPED,
        )

    def get_outputs(self) -> Dict[str, Any]:
        """Prefers extracted_outputs over raw result. Always use this instead of reading result directly."""
        return dict(self.extracted_outputs or self.result or {})


# Resolve the Instance.step_entities forward ref at module load; direct import would create a circular dependency.
def _finalize_instance_model_references() -> None:
    from app.domain.instance.models import Instance

    Instance.model_rebuild(_types_namespace={"StepExecution": StepExecution})


_finalize_instance_model_references()
