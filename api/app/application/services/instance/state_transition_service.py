# api/app/application/services/instance/state_transition_service.py

"""Centralized status mutations for rerun/retry/regenerate operations."""

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from app.domain.common.exceptions import BusinessRuleViolation
from app.domain.instance.models import (
    Instance,
    InstanceStatus,
    OperationType,
)
from app.domain.instance.repository import InstanceRepository
from app.domain.instance_step.models import StepExecutionStatus
from app.domain.instance_step.step_execution import StepExecution
from app.domain.instance_step.step_execution_repository import (
    StepExecutionRepository,
)
from app.infrastructure.errors import safe_error_message

if TYPE_CHECKING:
    from app.application.services.instance_notifier import InstanceNotifier

logger = logging.getLogger(__name__)


@dataclass
class TransitionContext:
    """Pre-operation snapshot used by rollback."""

    original_instance_status: InstanceStatus
    primary_step_id: str
    step_ids: List[str] = field(default_factory=list)


class StateTransitionService:
    """Owns status mutations for rerun/retry/regenerate."""

    def __init__(
        self,
        instance_repo: InstanceRepository,
        step_execution_repo: StepExecutionRepository,
        notifier: "Optional[InstanceNotifier]" = None,
    ):
        self._instance_repo = instance_repo
        self._step_execution_repo = step_execution_repo
        # Optional - rollback broadcasts a state change when present so the UI
        # reconciles without a manual reload.
        self._notifier = notifier

    async def prepare_for_reexecution(
        self,
        instance: Instance,
        operation: OperationType,
        step_ids: List[str],
        step_executions: List[StepExecution],
        *,
        is_retry: bool = False,
        skip_instance_transition: bool = False,
        operation_metadata: Optional[Dict[str, Any]] = None,
    ) -> TransitionContext:
        """Prepare an instance for re-execution.

        Flushes mutations only - caller must commit (or rollback) so prepare +
        enqueue land atomically. is_retry=True bumps retry_count; otherwise
        rerun is used. skip_instance_transition=True leaves instance.status
        unchanged (used by rerun_step_only when the parent instance is in a
        terminal state the user did not ask to change).
        """
        ctx = TransitionContext(
            original_instance_status=instance.status,
            primary_step_id=(
                step_ids[0]
                if step_ids
                else (operation_metadata or {}).get("step_id", "")
            ),
            step_ids=list(step_ids),
        )

        # Set operation context first - fails fast on concurrent operations before any step mutation.
        meta = dict(operation_metadata or {})
        meta.pop("step_id", None)
        if len(step_ids) > 1:
            meta["affected_step_ids"] = list(step_ids)

        primary_step = self._resolve_primary_step(
            instance, ctx.primary_step_id, step_executions
        )
        primary_step.begin_operation(
            op_type=operation,
            original_status=instance.status.value,
            **meta,
        )
        if not skip_instance_transition:
            instance.transition_to_processing()

        for step_execution in step_executions:
            old_status = step_execution.status.value
            if is_retry:
                step_execution.retry()
            else:
                step_execution.rerun()
            step_execution.reset_to_pending()
            await self._step_execution_repo.update(step_execution, commit=False)
            logger.debug(
                f"Reset step_execution {step_execution.id}: "
                f"{old_status} → {step_execution.status.value}",
                extra={
                    "instance_id": str(instance.id),
                    "step_execution_id": str(step_execution.id),
                    "operation": operation.value,
                },
            )

        for step_id in step_ids:
            if step_id in instance.completed_step_ids:
                instance.completed_step_ids.remove(step_id)
            if step_id in instance.failed_step_ids:
                instance.failed_step_ids.remove(step_id)

        await self._instance_repo.update(instance, commit=False)

        logger.info(
            f"Prepared instance {instance.id} for {operation.value}: "
            f"steps={step_ids}, step_executions={len(step_executions)}",
            extra={
                "instance_id": str(instance.id),
                "operation": operation.value,
                "step_ids": step_ids,
            },
        )

        return ctx

    @staticmethod
    def _resolve_primary_step(
        instance: Instance,
        primary_step_id: str,
        step_executions: List[StepExecution],
    ) -> StepExecution:
        """Locate the step that will own the new operation tracking record."""
        if primary_step_id and primary_step_id in instance.step_entities:
            return instance.step_entities[primary_step_id]
        for se in step_executions:
            if se.step_key == primary_step_id:
                return se
        raise BusinessRuleViolation(
            message=(
                f"Cannot begin operation: step '{primary_step_id}' not "
                f"in step_entities or step_executions"
            ),
            code="STEP_NOT_FOUND_FOR_OPERATION",
            context={
                "instance_id": str(instance.id),
                "primary_step_id": primary_step_id,
            },
        )

    async def rollback(
        self,
        instance: Instance,
        ctx: TransitionContext,
        error: Exception,
    ) -> None:
        """Reset state after enqueue failure, commit, then broadcast.

        Broadcast MUST follow commit - a WS-triggered UI refetch on a fresh
        session would otherwise read pre-commit data.
        """
        logger.error(
            f"Rolling back instance {instance.id} operation: {error}",
            extra={
                "instance_id": str(instance.id),
                "step_ids": ctx.step_ids,
                "error": str(error),
            },
        )

        # Primary step owns the active op; fall back to the snapshot if none found.
        primary_step = instance.step_entities.get(ctx.primary_step_id)
        if primary_step is not None and primary_step.active_operation is not None:
            instance.status = primary_step.cancel_operation()
        else:
            instance.status = ctx.original_instance_status

        for step_id in ctx.step_ids:
            step_execution = await self._step_execution_repo.get_by_instance_and_key(
                instance.id, step_id
            )
            if step_execution:
                step_execution.fail(f"Re-enqueue failed: {error}")
                await self._step_execution_repo.update(step_execution, commit=False)

        await self._instance_repo.update(instance, commit=False)

        await self.commit_session()

        if self._notifier is not None:
            try:
                await self._notifier.announce_state_change(
                    instance=instance,
                    action_type="rolled_back",
                    error=safe_error_message(error),
                )
            except Exception as broadcast_error:
                logger.warning(
                    f"Rollback broadcast failed for instance {instance.id}: {broadcast_error}"
                )

    async def complete_operation(self, instance: Instance) -> None:
        """Clear operation tracking without mutating instance status."""
        primary_step_id, primary_step = next(
            (
                (sid, se)
                for sid, se in instance.step_entities.items()
                if se.active_operation is not None
            ),
            (None, None),
        )
        if primary_step is None or primary_step.active_operation is None:
            return

        op_type = primary_step.active_operation.get("type", "")
        logger.info(
            f"Clearing operation tracking for {op_type} on instance {instance.id}",
            extra={
                "instance_id": str(instance.id),
                "operation": op_type,
                "step_id": primary_step_id,
            },
        )

        primary_step.complete_operation_tracking()
        await self._instance_repo.update(instance)

    async def cancel_active_operation(self, instance: Instance) -> Instance:
        """Cancel the in-flight rerun/retry/regenerate without cancelling the instance."""
        primary_step_id, primary_step = next(
            (
                (sid, se)
                for sid, se in instance.step_entities.items()
                if se.active_operation is not None
            ),
            (None, None),
        )
        if primary_step is None or primary_step.active_operation is None:
            return instance

        op_type = primary_step.active_operation.get("type", "")
        affected_step_ids = primary_step.active_operation.get(
            "affected_step_ids",
            [primary_step_id] if primary_step_id else [],
        )
        logger.info(
            f"Cancelling operation {op_type} on instance {instance.id}, "
            f"steps={affected_step_ids}",
            extra={
                "instance_id": str(instance.id),
                "operation": op_type,
                "step_id": primary_step_id,
            },
        )

        if affected_step_ids:
            _terminal_or_cancelled = {
                StepExecutionStatus.COMPLETED,
                StepExecutionStatus.CANCELLED,
                StepExecutionStatus.FAILED,
                StepExecutionStatus.SKIPPED,
                StepExecutionStatus.TIMEOUT,
            }
            for sid in affected_step_ids:
                step_execution = (
                    await self._step_execution_repo.get_by_instance_and_key(
                        instance.id, sid
                    )
                )
                if (
                    step_execution
                    and step_execution.status not in _terminal_or_cancelled
                ):
                    try:
                        old_status = step_execution.status.value
                        step_execution.cancel()
                        await self._step_execution_repo.update(step_execution)
                        logger.debug(
                            f"Cancelled step_execution {sid}: "
                            f"{old_status} → {step_execution.status.value}",
                            extra={
                                "instance_id": str(instance.id),
                                "step_id": sid,
                            },
                        )
                    except Exception as e:
                        logger.warning(
                            f"Failed to cancel step_execution {sid}: {e}",
                            extra={
                                "instance_id": str(instance.id),
                                "step_id": sid,
                            },
                        )

        instance.status = primary_step.cancel_operation()
        await self._instance_repo.update(instance)

        return instance

    async def commit_session(self) -> None:
        """Commit the underlying session if one is reachable."""
        session = getattr(self._step_execution_repo, "session", None)
        if session is None:
            session = getattr(self._instance_repo, "session", None)
        if session is not None:
            await session.commit()
