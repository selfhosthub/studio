# api/app/application/services/instance/status_derivation.py

"""Canonical per-step status derivation. Pure; no side effects."""

from typing import Dict, Optional

from app.domain.instance.models import Instance
from app.domain.instance_step.models import StepExecutionStatus
from app.domain.instance_step.step_execution import StepExecution


def derive_step_status(
    instance: Instance, step_id: str
) -> Optional[StepExecutionStatus]:
    """Status for a single step, or None if no entity exists yet."""
    entity: Optional[StepExecution] = instance.step_entities.get(step_id)
    if entity is None:
        return None
    return entity.status


def derive_instance_step_status_dict(instance: Instance) -> Dict[str, str]:
    """Status map for every step that has an entity. Missing steps are omitted."""
    if not instance.step_entities:
        return {}
    return {
        step_id: entity.status.value
        for step_id, entity in instance.step_entities.items()
        if entity is not None
    }
