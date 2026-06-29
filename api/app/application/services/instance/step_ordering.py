# api/app/application/services/instance/step_ordering.py

"""Topological ordering of workflow steps. Pure; cycle-safe."""

from typing import Any, Dict, List


def order_steps_topologically(workflow_snapshot: Dict[str, Any]) -> List[str]:
    """Step ids by DAG depth, then canvas Y, then insertion. Cycle-safe: cycles fall through, never crash."""
    if not workflow_snapshot:
        return []
    steps = workflow_snapshot.get("steps") or {}
    if not isinstance(steps, dict) or not steps:
        return []

    step_ids = list(steps.keys())

    def deps_of(step_id: str) -> List[str]:
        step_config = steps.get(step_id)
        raw = step_config.get("depends_on") or [] if isinstance(step_config, dict) else []
        return [dep for dep in raw if dep in steps]

    def y_of(step_id: str) -> float:
        step_config = steps.get(step_id)
        if not isinstance(step_config, dict):
            return float("inf")
        position = (step_config.get("ui_config") or {}).get("position") or {}
        y = position.get("y")
        return float(y) if isinstance(y, (int, float)) else float("inf")

    # Longest path from any root, so parallel branches rank by distance from the start.
    depth: Dict[str, int] = {}
    computing: set = set()

    def depth_of(step_id: str) -> int:
        if step_id in depth:
            return depth[step_id]
        if step_id in computing:
            return 0  # Cycle: treat as a root to break the recursion.
        computing.add(step_id)
        deps = deps_of(step_id)
        result = 1 + max((depth_of(dep) for dep in deps), default=-1)
        computing.discard(step_id)
        depth[step_id] = result
        return result

    insertion_index = {step_id: i for i, step_id in enumerate(step_ids)}
    return sorted(
        step_ids,
        key=lambda sid: (depth_of(sid), y_of(sid), insertion_index[sid]),
    )
