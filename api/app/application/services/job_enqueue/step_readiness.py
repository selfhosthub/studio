# api/app/application/services/job_enqueue/step_readiness.py

"""
Step readiness determination for workflow execution.

Determines which steps are ready to execute based on dependency resolution,
finds entry points, and handles skip/stop execution modes.
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def find_entry_step(workflow_snapshot: Dict[str, Any]) -> Optional[str]:
    """Return the entry step ID (no depends_on), or None if no steps exist."""
    steps = workflow_snapshot.get("steps", {})

    if not steps:
        return None

    # Find steps with no dependencies
    for step_id, step_config in steps.items():
        if isinstance(step_config, dict):
            depends_on = step_config.get("depends_on", [])
            if not depends_on:
                return step_id

    # Fallback: return first step if all have dependencies (shouldn't happen)
    return next(iter(steps.keys()), None)


def get_ready_steps(
    workflow_snapshot: Dict[str, Any],
    completed_step_ids: set[str],
    running_step_ids: set[str],
) -> List[str]:
    """Return steps whose dependencies are all satisfied and that are not running.

    A step is ready if it is not completed/running, all depends_on entries are in
    completed_step_ids, and its execution_mode is not skip/stop.

    Steps with execution_mode='skip' should be added to completed_step_ids before
    calling this.
    """
    steps = workflow_snapshot.get("steps", {})
    ready = []

    for step_id, step_config in steps.items():
        # Skip if already completed
        if step_id in completed_step_ids:
            continue

        # Skip if currently running
        if step_id in running_step_ids:
            continue

        # Skip if this step has skip/stop mode (should already be in completed_step_ids)
        if isinstance(step_config, dict):
            exec_mode = step_config.get("execution_mode")
            if exec_mode in ("skip", "stop"):
                continue

        # Check dependencies - all must be completed (or skipped)
        depends_on = []
        if isinstance(step_config, dict):
            depends_on = step_config.get("depends_on", []) or []

        # Steps with NO dependencies are entry points - they should only be
        # started explicitly at workflow start, not picked up here.
        # This prevents disconnected steps from auto-running.
        if not depends_on:
            continue

        all_deps_completed = all(dep_id in completed_step_ids for dep_id in depends_on)

        if all_deps_completed:
            ready.append(step_id)

    return ready
