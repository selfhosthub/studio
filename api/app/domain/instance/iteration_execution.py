# api/app/domain/instance/iteration_execution.py

"""Per-iteration execution entity. One row per (instance, step, iteration_index).

parameters is the middle layer of the three-layer parameter model: step-level inputs above, wire payload below.
"""

import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import ConfigDict, Field, field_validator

from app.domain.common.base_entity import Entity
from app.domain.common.exceptions import InvalidStateTransition


class IterationExecutionStatus(str, Enum):
    """Lifecycle status for a single iteration. PENDING = row only; QUEUED = broker row exists - the distinction pause semantics pivot on."""

    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# Forward-lifecycle transitions. Terminal states have no outgoing edges; regeneration resets via reset_for_regeneration.
VALID_TRANSITIONS: dict[IterationExecutionStatus, set[IterationExecutionStatus]] = {
    IterationExecutionStatus.PENDING: {
        IterationExecutionStatus.QUEUED,
        IterationExecutionStatus.RUNNING,  # inline dispatch (no broker row)
        IterationExecutionStatus.CANCELLED,
    },
    IterationExecutionStatus.QUEUED: {
        IterationExecutionStatus.RUNNING,
        IterationExecutionStatus.CANCELLED,
        # Worker may fail a claim before reaching RUNNING.
        IterationExecutionStatus.FAILED,
    },
    IterationExecutionStatus.RUNNING: {
        IterationExecutionStatus.COMPLETED,
        IterationExecutionStatus.FAILED,
        IterationExecutionStatus.CANCELLED,
    },
    IterationExecutionStatus.COMPLETED: set(),
    IterationExecutionStatus.FAILED: set(),
    IterationExecutionStatus.CANCELLED: set(),
}


# Resetting these would race a worker holding the claim or a live broker row. Cancel first.
_CANNOT_RESET_MID_FLIGHT: frozenset[IterationExecutionStatus] = frozenset(
    {
        IterationExecutionStatus.RUNNING,
        IterationExecutionStatus.QUEUED,
    }
)


class IterationExecution(Entity):
    """Per-iteration execution record. One row per (instance_id, step_id, iteration_index)."""

    instance_id: uuid.UUID
    step_id: uuid.UUID
    iteration_index: int
    iteration_group_id: Optional[uuid.UUID] = None

    @property
    def job_id(self) -> uuid.UUID:
        """Legacy alias for step_id."""
        return self.step_id

    status: IterationExecutionStatus = IterationExecutionStatus.PENDING

    @field_validator("status", mode="before")
    @classmethod
    def convert_status_to_enum(cls, v):
        if isinstance(v, str) and not isinstance(v, IterationExecutionStatus):
            return IterationExecutionStatus(v)
        return v

    # Middle layer of the three-layer parameter model: post-expansion per-iteration inputs.
    parameters: Dict[str, Any] = Field(default_factory=dict)

    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    model_config = ConfigDict(arbitrary_types_allowed=True)

    @classmethod
    def create(
        cls,
        instance_id: uuid.UUID,
        step_id: uuid.UUID,
        iteration_index: int,
        iteration_group_id: Optional[uuid.UUID] = None,
        parameters: Optional[Dict[str, Any]] = None,
        status: IterationExecutionStatus = IterationExecutionStatus.PENDING,
    ) -> "IterationExecution":
        return cls(
            instance_id=instance_id,
            step_id=step_id,
            iteration_index=iteration_index,
            iteration_group_id=iteration_group_id,
            parameters=parameters or {},
            status=status,
        )

    def _validate_transition(self, target: IterationExecutionStatus) -> None:
        valid_targets = VALID_TRANSITIONS.get(self.status, set())
        if target not in valid_targets:
            raise InvalidStateTransition(
                message=f"Cannot transition from {self.status.value} to {target.value}",
                code="INVALID_ITERATION_TRANSITION",
                context={
                    "entity_type": "IterationExecution",
                    "entity_id": str(self.id),
                    "current_state": self.status.value,
                    "attempted_state": target.value,
                },
            )

    def queue(self) -> None:
        """Mark enqueued. Idempotent: result-consumer replay can re-arrive."""
        if self.status == IterationExecutionStatus.QUEUED:
            return
        self._validate_transition(IterationExecutionStatus.QUEUED)
        self.status = IterationExecutionStatus.QUEUED

    def start(self) -> None:
        """Mark running. Idempotent for worker heartbeat / WS reconnect replay."""
        if self.status == IterationExecutionStatus.RUNNING:
            return
        self._validate_transition(IterationExecutionStatus.RUNNING)
        self.status = IterationExecutionStatus.RUNNING
        self.started_at = datetime.now(UTC)
        self.error = None

    def complete(self, result: Optional[Dict[str, Any]] = None) -> None:
        if self.status == IterationExecutionStatus.COMPLETED:
            if result is not None:
                self.result = result
            return
        self._validate_transition(IterationExecutionStatus.COMPLETED)
        self.status = IterationExecutionStatus.COMPLETED
        self.completed_at = datetime.now(UTC)
        if result is not None:
            self.result = result

    def fail(self, error: str) -> None:
        if self.status == IterationExecutionStatus.FAILED:
            self.error = error
            return
        self._validate_transition(IterationExecutionStatus.FAILED)
        self.status = IterationExecutionStatus.FAILED
        self.error = error
        self.completed_at = datetime.now(UTC)

    def cancel(self) -> None:
        """Cancel. Idempotent: the instance/step cancel sweep can re-touch already-cancelled rows."""
        if self.status == IterationExecutionStatus.CANCELLED:
            return
        self._validate_transition(IterationExecutionStatus.CANCELLED)
        self.status = IterationExecutionStatus.CANCELLED
        self.completed_at = datetime.now(UTC)

    def reset_for_regeneration(
        self, parameters: Optional[Dict[str, Any]] = None
    ) -> None:
        """Reset a terminal iteration to PENDING. Mid-flight rows must be cancelled first to avoid racing the worker."""
        if self.status in _CANNOT_RESET_MID_FLIGHT:
            raise InvalidStateTransition(
                message=(
                    f"Cannot reset iteration in {self.status.value} - "
                    f"cancel it first"
                ),
                code="ITERATION_RESET_MID_FLIGHT",
                context={
                    "entity_type": "IterationExecution",
                    "entity_id": str(self.id),
                    "current_state": self.status.value,
                    "attempted_state": IterationExecutionStatus.PENDING.value,
                },
            )
        self.status = IterationExecutionStatus.PENDING
        self.result = None
        self.error = None
        self.started_at = None
        self.completed_at = None
        if parameters is not None:
            self.parameters = parameters

    def is_terminal(self) -> bool:
        return self.status in {
            IterationExecutionStatus.COMPLETED,
            IterationExecutionStatus.FAILED,
            IterationExecutionStatus.CANCELLED,
        }
