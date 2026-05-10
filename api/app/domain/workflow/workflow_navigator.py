# api/app/domain/workflow/workflow_navigator.py

"""Pure graph navigation utilities for workflow snapshots and step-status dicts."""

import logging
from typing import Any, Dict, List, Optional, Set

from app.domain.instance_step.models import StepExecutionStatus

logger = logging.getLogger(__name__)


class WorkflowNavigator:
    """Static graph navigation helpers; no I/O or domain-object dependencies."""

    @staticmethod
    def get_reachable_steps(steps: Dict[str, Any]) -> Set[str]:
        """BFS from zero-dependency entry points; disconnected steps are excluded."""
        entry_points: Set[str] = set()
        for step_id, step_config in steps.items():
            if isinstance(step_config, dict):
                depends_on = step_config.get("depends_on", []) or []
                if not depends_on:
                    entry_points.add(step_id)

        reachable = set(entry_points)
        to_check = list(entry_points)

        while to_check:
            current = to_check.pop(0)
            for step_id, step_config in steps.items():
                if step_id in reachable:
                    continue
                if isinstance(step_config, dict):
                    depends_on = step_config.get("depends_on", []) or []
                    if current in depends_on:
                        reachable.add(step_id)
                        to_check.append(step_id)

        return reachable

    @staticmethod
    def get_ready_steps(
        steps: Dict[str, Any],
        completed_step_ids: Set[str],
        step_status: Dict[str, str],
    ) -> List[str]:
        """Steps whose deps are all complete, excluding entry points, skip/stop modes, and in-flight/terminal steps."""
        ready: List[str] = []

        all_completed = set(completed_step_ids)

        # Also include steps that completed since completed_step_ids was last persisted (handles race conditions).
        for sid, status in step_status.items():
            if status in [StepExecutionStatus.COMPLETED.value, "completed", "skipped"]:
                all_completed.add(sid)

        # 'skip' mode steps count as completed for dependency resolution.
        for step_id, step_config in steps.items():
            if isinstance(step_config, dict):
                exec_mode = step_config.get("execution_mode")
                if exec_mode == "skip":
                    all_completed.add(step_id)

        for step_id, step_config in steps.items():
            if step_id in all_completed:
                continue

            # Exclude in-flight and terminal-non-complete steps. Terminal-non-complete
            # steps can't be claimed (claim_for_enqueue requires PENDING), so returning
            # them would stall the instance in PROCESSING with no progress.
            current_status = step_status.get(step_id)
            if current_status in [
                StepExecutionStatus.QUEUED.value,
                StepExecutionStatus.RUNNING.value,
                StepExecutionStatus.CANCELLED.value,
                StepExecutionStatus.FAILED.value,
                "queued",
                "running",
                "cancelled",
                "failed",
            ]:
                continue

            # Stop-mode steps are excluded; they halt the workflow and are checked independently.
            if isinstance(step_config, dict):
                exec_mode = step_config.get("execution_mode")
                if exec_mode == "stop":
                    continue

            depends_on: List[str] = []
            if isinstance(step_config, dict):
                depends_on = step_config.get("depends_on", []) or []

            # Entry points (no deps) are started explicitly at workflow start, not picked up here.
            if not depends_on:
                continue

            all_deps_completed = all(dep_id in all_completed for dep_id in depends_on)

            if all_deps_completed:
                ready.append(step_id)

        return ready

    @staticmethod
    def is_workflow_complete(
        steps: Dict[str, Any],
        completed_step_ids: Set[str],
        step_status: Dict[str, str],
    ) -> bool:
        """True when all reachable steps are completed, skipped, or waiting_for_manual_trigger."""
        all_completed = set(completed_step_ids)
        for sid, status in step_status.items():
            if status in [
                StepExecutionStatus.COMPLETED.value,
                "completed",
                "skipped",
                "waiting_for_manual_trigger",
            ]:
                all_completed.add(sid)

        # 'skip' mode steps count as completed for dependency resolution.
        for step_id, step_config in steps.items():
            if isinstance(step_config, dict):
                exec_mode = step_config.get("execution_mode")
                if exec_mode == "skip":
                    all_completed.add(step_id)

        # Disconnected steps don't need to complete for workflow completion.
        reachable_steps = WorkflowNavigator.get_reachable_steps(steps)

        return all(step_id in all_completed for step_id in reachable_steps)

    @staticmethod
    def find_manual_trigger_step(
        steps: Dict[str, Any],
        ready_step_ids: List[str],
    ) -> Optional[str]:
        """First ready step with trigger_type='manual', or None."""
        for step_id in ready_step_ids:
            step_config = steps.get(step_id)
            if not step_config or not isinstance(step_config, dict):
                continue

            trigger_type = step_config.get("trigger_type", "auto")
            logger.debug(f"Step {step_id}: trigger_type={trigger_type}")
            if trigger_type == "manual":
                return step_id

        return None

    @staticmethod
    def partition_by_trigger(
        steps: Dict[str, Any],
        ready_step_ids: List[str],
    ) -> tuple:
        """Split ready steps into (auto_step_ids, manual_step_ids)."""
        auto: List[str] = []
        manual: List[str] = []
        for step_id in ready_step_ids:
            step_config = steps.get(step_id)
            if not step_config or not isinstance(step_config, dict):
                auto.append(step_id)
                continue
            trigger_type = step_config.get("trigger_type", "auto")
            if trigger_type == "manual":
                manual.append(step_id)
            else:
                auto.append(step_id)
        return auto, manual

    @staticmethod
    def find_stop_step(
        steps: Dict[str, Any],
        ready_step_ids: List[str],
        completed_step_ids: Optional[Set[str]] = None,
        step_status: Optional[Dict[str, str]] = None,
    ) -> Optional[str]:
        """First stop-mode step whose deps are all completed, or None. Stop steps are excluded from get_ready_steps so this checks them independently."""
        all_completed: Set[str] = set()
        if completed_step_ids:
            all_completed = set(completed_step_ids)
        if step_status:
            for sid, status in step_status.items():
                if status in [StepExecutionStatus.COMPLETED.value, "completed", "skipped"]:
                    all_completed.add(sid)

        # 'skip' mode steps count as completed for dependency resolution.
        for step_id, step_config in steps.items():
            if isinstance(step_config, dict):
                exec_mode = step_config.get("execution_mode")
                if exec_mode == "skip":
                    all_completed.add(step_id)

        for step_id, step_config in steps.items():
            if not step_config or not isinstance(step_config, dict):
                continue

            exec_mode = step_config.get("execution_mode")
            if exec_mode != "stop":
                continue

            depends_on = step_config.get("depends_on", []) or []
            if not depends_on:
                return step_id

            if all(dep_id in all_completed for dep_id in depends_on):
                return step_id

        return None

    @staticmethod
    def find_entry_step(steps: Dict[str, Any]) -> Optional[str]:
        """First step with no dependencies, or None if steps is empty."""
        if not steps:
            return None

        for step_id, step_config in steps.items():
            if isinstance(step_config, dict):
                depends_on = step_config.get("depends_on", [])
                if not depends_on:
                    return step_id

        # Fallback: shouldn't happen in a valid workflow, but return first step defensively.
        return next(iter(steps.keys()), None)
