# api/app/domain/instance_step/models.py

"""Step execution status enum and forward-lifecycle transition table."""

from enum import Enum


class StepExecutionStatus(str, Enum):
    """Status of a workflow step execution. TIMEOUT/BLOCKED are first-class to avoid two-set drift with worker-attempt state.

    PAUSED is reserved for the edit-params flow; has no forward transitions. A reachability-exemption test pins this contract.
    """

    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    STOPPED = "stopped"  # resumable
    WAITING_APPROVAL = "waiting_for_approval"
    WAITING_FOR_MANUAL_TRIGGER = "waiting_for_manual_trigger"
    WAITING_FOR_WEBHOOK = "waiting_for_webhook"  # awaiting provider callback
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"
    BLOCKED = "blocked"  # resource/rate-limit; resumable
    PAUSED = "paused"


# Forward-lifecycle transitions only - does NOT describe reset/rerun.
# Reset-to-PENDING has one invariant: mid-flight steps (RUNNING or QUEUED) must be cancelled first
# to avoid racing the worker or leaving orphan queue entries. Kept separate from forward transitions
# so adding a new status doesn't require editing every cascade-rerun path.
VALID_TRANSITIONS: dict[StepExecutionStatus, set[StepExecutionStatus]] = {
    StepExecutionStatus.PENDING: {
        StepExecutionStatus.QUEUED,
        StepExecutionStatus.RUNNING,
        StepExecutionStatus.SKIPPED,
        StepExecutionStatus.STOPPED,
        StepExecutionStatus.WAITING_APPROVAL,
        StepExecutionStatus.WAITING_FOR_MANUAL_TRIGGER,
        StepExecutionStatus.CANCELLED,
        # API-side enqueue-time contract violations (e.g. empty iteration source); API-only edge.
        StepExecutionStatus.FAILED,
    },
    StepExecutionStatus.QUEUED: {
        StepExecutionStatus.RUNNING,
        StepExecutionStatus.COMPLETED,
        StepExecutionStatus.FAILED,
        StepExecutionStatus.CANCELLED,
        StepExecutionStatus.BLOCKED,
        StepExecutionStatus.STOPPED,  # stop can land before worker claims
    },
    StepExecutionStatus.RUNNING: {
        StepExecutionStatus.COMPLETED,
        StepExecutionStatus.FAILED,
        StepExecutionStatus.WAITING_APPROVAL,
        StepExecutionStatus.WAITING_FOR_WEBHOOK,
        StepExecutionStatus.CANCELLED,
        StepExecutionStatus.TIMEOUT,
        StepExecutionStatus.BLOCKED,
        StepExecutionStatus.STOPPED,
    },
    StepExecutionStatus.WAITING_APPROVAL: {
        StepExecutionStatus.COMPLETED,
        StepExecutionStatus.FAILED,
        StepExecutionStatus.CANCELLED,
    },
    StepExecutionStatus.WAITING_FOR_WEBHOOK: {
        StepExecutionStatus.COMPLETED,
        StepExecutionStatus.FAILED,
        StepExecutionStatus.CANCELLED,
    },
    StepExecutionStatus.WAITING_FOR_MANUAL_TRIGGER: {
        StepExecutionStatus.RUNNING,
        StepExecutionStatus.QUEUED,
        StepExecutionStatus.CANCELLED,
    },
    StepExecutionStatus.STOPPED: {
        StepExecutionStatus.RUNNING,
        StepExecutionStatus.QUEUED,
        StepExecutionStatus.CANCELLED,
    },
    StepExecutionStatus.BLOCKED: {
        # Resumable; CANCELLED is the universal escape hatch.
        StepExecutionStatus.QUEUED,
        StepExecutionStatus.RUNNING,
        StepExecutionStatus.CANCELLED,
    },
    # Terminal - rerun/regeneration uses reset_to_pending, not this table.
    StepExecutionStatus.COMPLETED: set(),
    StepExecutionStatus.FAILED: set(),
    StepExecutionStatus.SKIPPED: set(),
    StepExecutionStatus.CANCELLED: set(),
    StepExecutionStatus.TIMEOUT: set(),
    # PAUSED is intentionally empty until pause-on-demand ships;
    # the reachability test exempts it from the producer-and-reader rule.
}


# Resetting from these would race a worker or leave orphan queue rows.
# reset_to_pending rejects and forces the caller to cancel first.
_CANNOT_RESET_MID_FLIGHT: frozenset[StepExecutionStatus] = frozenset(
    {
        StepExecutionStatus.RUNNING,
        StepExecutionStatus.QUEUED,
    }
)


# Long-lived parked states: a run waits here indefinitely for a human or an
# external callback. No wall-clock timer ever fails a step (I-13) - parked or
# active, a run waits indefinitely and visibly; only a real signal (worker
# error, provider error, explicit user action) moves it to FAILED. This set is
# the canonical list of states the UI treats as "parked, awaiting input."
INDEFINITE_WAIT_STATUSES: frozenset[StepExecutionStatus] = frozenset(
    {
        StepExecutionStatus.WAITING_APPROVAL,
        StepExecutionStatus.WAITING_FOR_MANUAL_TRIGGER,
        StepExecutionStatus.WAITING_FOR_WEBHOOK,
    }
)
