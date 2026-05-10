# api/app/application/services/stale_step_sweep_service.py

"""
Stale Step Sweep Service

Detects and recovers from workflow instances stuck in non-terminal states
beyond a configurable timeout. This is the safety net that makes the system
self-healing across ALL failure modes:

- Worker crash / OOM mid-job (heartbeat lost, no result ever published)
- Result publish exhausted retries (API was returning 5xx during worker's
  3-attempt window, worker logged CRITICAL and moved on, step orphaned)
- Network partition (worker delivered result but API never received it)
- Worker process killed before publishing (OS signal, container eviction)

For each stale step:
  1. Mark the step FAILED with a descriptive error
  2. Mark the parent instance FAILED
  3. Create an operator notification (via InstanceNotifier)
  4. Broadcast the instance update via WebSocket (via InstanceNotifier)

Threshold is configured via settings.STALE_STEP_TIMEOUT_MINUTES (default 15).
Raise it if you have legitimately long-running workers.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import settings
from app.domain.common.exceptions import InvalidStateTransition
from app.domain.instance.models import Instance, InstanceStatus
from app.domain.instance_step.step_execution import StepExecution

if TYPE_CHECKING:
    from app.application.services.instance_notifier import InstanceNotifier
    from app.domain.instance.repository import InstanceRepository
    from app.domain.instance_step.step_execution_repository import (
        StepExecutionRepository,
    )

logger = logging.getLogger(__name__)


@dataclass
class StaleSweepResult:
    """Summary of a single sweep cycle."""

    steps_failed: int
    instances_failed: int
    timestamp: str
    threshold_minutes: int


class StaleStepSweepService:
    """
    Fails steps (and their parent instances) stuck in active states too long.

    Pulls stale steps from the repository, converts them + their parent
    instances to FAILED state, and surfaces the failure via notifications
    and WebSocket updates so operators see "something went wrong" rather
    than a spinner that never resolves.
    """

    def __init__(
        self,
        session: AsyncSession,
        step_execution_repository: "StepExecutionRepository",
        instance_repository: "InstanceRepository",
        notifier: Optional["InstanceNotifier"] = None,
    ):
        """notifier=None updates the DB but skips WS broadcast and in-app notifications (useful for tests)."""
        self.session = session
        self.step_execution_repository = step_execution_repository
        self.instance_repository = instance_repository
        self.notifier = notifier

    async def sweep_stale_steps(
        self,
        timeout_minutes: Optional[int] = None,
    ) -> StaleSweepResult:
        """Find stale steps and fail them along with their parent instances."""
        threshold = (
            timeout_minutes
            if timeout_minutes is not None
            else settings.STALE_STEP_TIMEOUT_MINUTES
        )

        stale_steps = await self.step_execution_repository.list_stale_steps(
            timeout_minutes=threshold
        )

        if not stale_steps:
            logger.debug(f"No stale steps found (threshold {threshold} min)")
            return StaleSweepResult(
                steps_failed=0,
                instances_failed=0,
                timestamp=datetime.now(UTC).isoformat(),
                threshold_minutes=threshold,
            )

        logger.info(
            f"Found {len(stale_steps)} stale steps "
            f"(threshold {threshold} min) - sweeping"
        )

        # Group by instance so we only fail each instance once even if
        # multiple of its steps are stale
        instance_ids_to_fail: set = set()
        steps_failed = 0

        for step in stale_steps:
            try:
                await self._fail_stale_step(step, threshold)
                steps_failed += 1
                instance_ids_to_fail.add(step.instance_id)
            except Exception as e:
                logger.error(
                    f"Failed to fail stale step {step.id} "
                    f"(instance={step.instance_id}, key={step.step_key}): {e}"
                )

        instances_failed = 0
        for instance_id in instance_ids_to_fail:
            try:
                if await self._fail_instance(instance_id, threshold):
                    instances_failed += 1
            except Exception as e:
                logger.error(f"Failed to fail stale instance {instance_id}: {e}")

        logger.info(
            f"Stale sweep complete: {steps_failed} steps failed, "
            f"{instances_failed} instances failed"
        )

        return StaleSweepResult(
            steps_failed=steps_failed,
            instances_failed=instances_failed,
            timestamp=datetime.now(UTC).isoformat(),
            threshold_minutes=threshold,
        )

    async def _fail_stale_step(
        self,
        step: StepExecution,
        threshold_minutes: int,
    ) -> None:
        """Mark a single stale step as FAILED with a descriptive error."""
        # updated_at is Optional but sweep candidates always have it set - it's the filter field.
        last_activity = step.updated_at or step.started_at or step.created_at
        if last_activity is not None:
            # Ensure tz-aware for subtraction
            if last_activity.tzinfo is None:
                last_activity = last_activity.replace(tzinfo=UTC)
            age_seconds = int((datetime.now(UTC) - last_activity).total_seconds())
        else:
            age_seconds = threshold_minutes * 60
        error_msg = (
            f"Step stalled in {step.status.value} for "
            f"{age_seconds // 60} min (threshold: {threshold_minutes} min). "
            "Worker may have crashed, result delivery may have failed, "
            "or the API was unavailable when the worker tried to report."
        )
        logger.warning(
            f"Failing stale step {step.step_key} "
            f"(instance={step.instance_id}, id={step.id}, "
            f"status={step.status.value}, age={age_seconds}s)"
        )
        step.fail(error_msg)
        await self.step_execution_repository.update(step)

    async def _fail_instance(
        self,
        instance_id: UUID,
        threshold_minutes: int,
    ) -> bool:
        """
        Mark an instance as FAILED if it isn't already terminal, and
        notify operators via WebSocket + in-app notification.

        Returns True if the instance was transitioned, False if it was
        already in a terminal state (race with manual cancel, etc.).
        """
        instance = await self.instance_repository.get_by_id(instance_id)
        if instance is None:
            logger.warning(
                f"Stale step sweep: instance {instance_id} not found "
                "(deleted mid-sweep?)"
            )
            return False

        if _is_terminal(instance):
            logger.debug(
                f"Stale step sweep: instance {instance_id} already "
                f"terminal ({instance.status}), skipping"
            )
            return False

        error_msg = (
            f"Instance stalled beyond {threshold_minutes}-minute threshold. "
            "One or more steps were marked failed by the stale-step sweep. "
            "Review step errors and rerun if the underlying issue is fixed."
        )
        try:
            instance.fail(error_msg)
        except InvalidStateTransition as e:
            logger.warning(
                f"Stale step sweep: cannot fail instance {instance_id} "
                f"from {instance.status}: {e}"
            )
            return False

        await self.instance_repository.update(instance)

        # Operator notification - DB notification for admins + WS broadcast
        if self.notifier is not None:
            try:
                await self.notifier.announce_state_change(
                    instance=instance,
                    action_type="failed",
                    error=error_msg,
                    session=self.session,
                )
            except Exception as e:
                logger.warning(
                    f"Stale step sweep: announce_state_change failed for "
                    f"instance {instance_id}: {e}"
                )

        return True


def _is_terminal(instance: Instance) -> bool:
    """Check if an instance is in a terminal status."""
    return instance.status in (
        InstanceStatus.COMPLETED,
        InstanceStatus.FAILED,
        InstanceStatus.CANCELLED,
    )


__all__ = ["StaleStepSweepService", "StaleSweepResult"]
