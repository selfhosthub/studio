# api/app/application/services/instance/step_ordering.py

"""Topological ordering of workflow steps. Pure; cycle-safe."""

from typing import Any, Dict, List


def order_steps_topologically(workflow_snapshot: Dict[str, Any]) -> List[str]:
    """Step ids in dependency order. Cycle-safe: cycles fall through, never crash."""
    if not workflow_snapshot:
        return []
    steps = workflow_snapshot.get("steps") or {}
    if not isinstance(steps, dict) or not steps:
        return []

    step_ids = list(steps.keys())
    sorted_ids: List[str] = []
    visited: set = set()
    visiting: set = set()

    def visit(step_id: str) -> None:
        if step_id in visited:
            return
        if step_id in visiting:
            # Cycle: bail. The outer frame appends once when it finishes -
            # appending here would double-emit.
            return

        visiting.add(step_id)
        step_config = steps.get(step_id)
        if isinstance(step_config, dict):
            depends_on = step_config.get("depends_on") or []
        else:
            depends_on = []
        for dep in depends_on:
            if dep in steps:
                visit(dep)
        visiting.discard(step_id)
        visited.add(step_id)
        sorted_ids.append(step_id)

    for step_id in step_ids:
        visit(step_id)

    return sorted_ids
