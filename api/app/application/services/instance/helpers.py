# api/app/application/services/instance/helpers.py

"""Shared instance-service helpers. Stateless - dependencies passed in, not via self."""

import uuid
from typing import Any, Dict, Optional, Type

from app.domain.instance.models import Instance, InstanceStatus
from app.domain.instance.repository import InstanceRepository
from app.domain.common.exceptions import (
    BusinessRuleViolation,
    InvalidStateTransition,
)
from app.application.interfaces import EntityNotFoundError

# Statuses that block rerun/retry/regeneration.
BUSY_STATUSES = frozenset([InstanceStatus.PENDING, InstanceStatus.PROCESSING])


def get_active_op_for_step(
    instance: Instance,
    step_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Active-operation dict for the given step, or None.

    With step_id=None this is the "is anything active anywhere?" query -
    returns the first non-None active_operation found across step_entities.
    """
    if step_id is not None:
        step = instance.step_entities.get(step_id)
        if step is None or step.active_operation is None:
            return None
        return step.active_operation
    for se in instance.step_entities.values():
        if se.active_operation is not None:
            return se.active_operation
    return None


async def get_instance_or_raise(
    instance_repository: InstanceRepository, instance_id: uuid.UUID
) -> Instance:
    instance = await instance_repository.get_by_id(instance_id)
    if not instance:
        raise EntityNotFoundError(
            entity_type="Instance",
            entity_id=instance_id,
            code=f"Instance with ID {instance_id} not found",
        )
    return instance


def assert_instance_idle(instance: Instance, operation: str) -> None:
    if instance.status in BUSY_STATUSES:
        raise ValueError(
            f"Cannot {operation} while instance is {instance.status.value}. "
            f"Wait for processing to complete or cancel the instance first."
        )


def assert_no_active_operation(
    instance: Instance,
    *,
    operation_label: str,
    error_class: Type[Exception] = BusinessRuleViolation,
    code: Optional[str] = None,
    requested_operation: Optional[str] = None,
    step_id: Optional[str] = None,
) -> None:
    """Reject when an operation is already in flight on this instance (or step).

    error_class is configurable: some callers raise with a code so the UI can
    disambiguate operation collisions; others raise a state-transition error.

    step_id=None rejects on ANY active operation; a real step_id scopes
    the rejection to that step only.
    """
    op = get_active_op_for_step(instance, step_id)
    if op is None:
        return
    op_type = op.get("type", "unknown")
    message = f"Cannot {operation_label}: instance has active operation ({op_type})"
    if error_class is BusinessRuleViolation:
        raise BusinessRuleViolation(
            message=message,
            code=code,
            context={
                "instance_id": str(instance.id),
                "active_operation": op,
                "requested_operation": requested_operation,
            },
        )
    if error_class is InvalidStateTransition:
        raise InvalidStateTransition(message)
    raise error_class(message)
