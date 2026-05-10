# api/app/application/services/instance/workflow_orchestrator.py

"""Pure decision logic for "what happens after a step completes?". No I/O -
the caller owns DB, notifications, WS, and enqueue."""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

logger = logging.getLogger(__name__)

from app.application.services.instance.helpers import get_active_op_for_step
from app.application.services.instance.status_derivation import (
    derive_instance_step_status_dict,
)
from app.domain.instance.models import Instance
from app.domain.workflow import WorkflowNavigator


class OrchestrationAction(Enum):
    ENQUEUE_STEPS = "enqueue_steps"
    WAIT_APPROVAL = "wait_approval"
    WAIT_MANUAL = "wait_manual"
    WAIT_DEBUG = "wait_debug"
    STOP = "stop"
    COMPLETE = "complete"
    FAIL = "fail"
    NOOP = "noop"  # Waiting on parallel siblings.


@dataclass
class NextAction:
    action: OrchestrationAction
    step_ids: List[str] = field(default_factory=list)  # For ENQUEUE_STEPS.
    waiting_step_id: Optional[str] = None  # For WAIT_*, STOP.
    error_message: Optional[str] = None  # For FAIL.

    def __repr__(self) -> str:
        if self.action == OrchestrationAction.ENQUEUE_STEPS:
            return f"NextAction(ENQUEUE_STEPS, steps={self.step_ids})"
        elif self.action in (
            OrchestrationAction.WAIT_APPROVAL,
            OrchestrationAction.WAIT_MANUAL,
            OrchestrationAction.WAIT_DEBUG,
            OrchestrationAction.STOP,
        ):
            return f"NextAction({self.action.name}, step={self.waiting_step_id})"
        elif self.action == OrchestrationAction.FAIL:
            return f"NextAction(FAIL, error={self.error_message})"
        return f"NextAction({self.action.name})"


class WorkflowOrchestrator:
    """Pure decision logic: given current state, returns the next action.

    No I/O - the caller executes side effects.
    """

    def determine_next_action(
        self,
        instance: Instance,
        completed_step_id: str,
        step_failed: bool = False,
        error_message: Optional[str] = None,
        approval_step_id: Optional[str] = None,
        is_debug_mode: bool = False,
    ) -> NextAction:
        if step_failed:
            return NextAction(
                action=OrchestrationAction.FAIL,
                error_message=error_message or f"Step {completed_step_id} failed",
            )

        # Isolated re-execution overrides the dead-end FAIL branch - debugging one
        # step shouldn't fail the instance due to unrelated tail steps.
        from app.domain.instance.models import OperationType

        active_op = get_active_op_for_step(instance, completed_step_id)
        isolated_op_on_this_step = False
        if active_op is not None:
            op_type_str = active_op.get("type", "")
            try:
                isolated_op_on_this_step = OperationType(op_type_str).is_isolated
            except ValueError:
                isolated_op_on_this_step = False

        steps = (instance.workflow_snapshot or {}).get("steps", {})
        completed = set(instance.completed_step_ids)

        # Stop step takes priority - ready-step enumeration filters them out.
        stop_step = WorkflowNavigator.find_stop_step(
            steps, [], completed, derive_instance_step_status_dict(instance)
        )
        if stop_step:
            return NextAction(
                action=OrchestrationAction.STOP,
                waiting_step_id=stop_step,
            )

        next_steps = WorkflowNavigator.get_ready_steps(
            steps, completed, derive_instance_step_status_dict(instance)
        )

        if not next_steps:
            if WorkflowNavigator.is_workflow_complete(
                steps, completed, derive_instance_step_status_dict(instance)
            ):
                return NextAction(action=OrchestrationAction.COMPLETE)

            # Dead-end: every reachable-and-not-complete step is terminal.
            # Without this branch the instance stays in PROCESSING forever.
            # Transition to FAILED so the user can recover.
            step_status_dict = derive_instance_step_status_dict(instance)
            reachable = WorkflowNavigator.get_reachable_steps(steps)
            all_completed_for_check = set(completed)
            for sid, status in step_status_dict.items():
                if status in ("completed", "skipped"):
                    all_completed_for_check.add(sid)
            for sid, cfg in steps.items():
                if isinstance(cfg, dict) and cfg.get("execution_mode") == "skip":
                    all_completed_for_check.add(sid)

            TERMINAL_INCOMPLETE = {"cancelled", "failed"}
            dead_ended = True
            for sid in reachable:
                if sid in all_completed_for_check:
                    continue
                status = step_status_dict.get(sid)
                # None means never-started - progressable, not dead.
                if status not in TERMINAL_INCOMPLETE:
                    dead_ended = False
                    break

            if dead_ended:
                if isolated_op_on_this_step:
                    # Isolated rerun/regenerate - NOOP lets the result processor
                    # restore the pre-operation status without failing the instance.
                    logger.info(
                        f"Dead-end after isolated operation on "
                        f"{completed_step_id} - suppressing FAIL, restoring "
                        f"pre-op status. step_status={step_status_dict}"
                    )
                    return NextAction(action=OrchestrationAction.NOOP)
                logger.warning(
                    f"Workflow dead-ended after {completed_step_id}: all "
                    f"reachable non-complete steps are CANCELLED/FAILED. "
                    f"Failing instance so user can recover. "
                    f"step_status={step_status_dict}"
                )
                return NextAction(
                    action=OrchestrationAction.FAIL,
                    error_message=(
                        "Workflow cannot continue: remaining steps are "
                        "cancelled or failed. Rerun the affected steps to "
                        "resume."
                    ),
                )

            # Parallel branches: one finished, others still running.
            logger.debug(
                f"No ready steps after {completed_step_id}, but workflow not complete. "
                f"Waiting for parallel steps. completed={list(completed)}"
            )
            return NextAction(action=OrchestrationAction.NOOP)

        if approval_step_id and approval_step_id in next_steps:
            return NextAction(
                action=OrchestrationAction.WAIT_APPROVAL,
                waiting_step_id=approval_step_id,
            )

        auto_steps, manual_steps = WorkflowNavigator.partition_by_trigger(
            steps, next_steps
        )

        if not auto_steps and manual_steps:
            return NextAction(
                action=OrchestrationAction.WAIT_MANUAL,
                waiting_step_id=manual_steps[0],
            )

        if is_debug_mode and auto_steps:
            return NextAction(
                action=OrchestrationAction.WAIT_DEBUG,
                step_ids=auto_steps,
                waiting_step_id=completed_step_id,
            )

        if auto_steps:
            return NextAction(
                action=OrchestrationAction.ENQUEUE_STEPS,
                step_ids=auto_steps,
            )

        return NextAction(action=OrchestrationAction.NOOP)

    def is_workflow_complete(
        self,
        instance: Instance,
    ) -> bool:
        steps = (instance.workflow_snapshot or {}).get("steps", {})
        return WorkflowNavigator.is_workflow_complete(
            steps,
            set(instance.build_completed_step_ids()),
            derive_instance_step_status_dict(instance),
        )
