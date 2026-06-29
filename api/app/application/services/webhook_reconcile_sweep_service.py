# api/app/application/services/webhook_reconcile_sweep_service.py

"""WAITING_FOR_WEBHOOK notify sweep (no timer ever fails a step - I-13).

A step parked in WAITING_FOR_WEBHOOK waits indefinitely for a provider callback;
no wall-clock timer fails it and no timer auto-polls the provider (that would be
a fail-open bypass of the callback-auth control). This sweep's only job is to
nudge the operator: once a parked step has waited past its notify window, fire a
single "still awaiting provider callback" notification so a genuinely stuck run
surfaces without silently completing via an unauthenticated poll.

Fire-once per step entry: the flag lives in step.execution_data.webhook_notified_at
and is cleared on each WAITING_FOR_WEBHOOK entry (StepExecution.wait_for_webhook),
so a rerun that re-parks the step can notify again. Not iteration-level - one
notification per step, regardless of how many iterations are pending.

The notify window is per-provider (client_metadata.webhook_completion.notify_minutes),
falling back to settings.WEBHOOK_NOTIFY_MINUTES. User-initiated recovery (the
"Check Status" button) is a separate, explicit path - this service never polls.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import settings
from app.infrastructure.errors import safe_error_message
from app.domain.instance_step.step_execution import StepExecution

if TYPE_CHECKING:
    from app.application.services.instance_notifier import InstanceNotifier
    from app.domain.instance.repository import InstanceRepository
    from app.domain.instance_step.step_execution_repository import (
        StepExecutionRepository,
    )

logger = logging.getLogger(__name__)

_NOTIFIED_FLAG = "webhook_notified_at"


@dataclass
class WebhookReconcileResult:
    """Summary of a single notify-sweep cycle."""

    steps_examined: int
    steps_notified: int
    timestamp: str
    threshold_minutes: int


class WebhookReconcileSweepService:
    """Fires the once-per-step "still awaiting callback" notification for overdue WFW steps."""

    def __init__(
        self,
        step_execution_repository: "StepExecutionRepository",
        instance_repository: "InstanceRepository",
        notifier: Optional["InstanceNotifier"] = None,
        session: Optional[AsyncSession] = None,
    ):
        self.step_execution_repository = step_execution_repository
        self.instance_repository = instance_repository
        self.notifier = notifier
        # The bell notification commits on this session (the cleanup-cycle
        # session the repos share). None in tests with notifier=None.
        self.session = session

    async def reconcile_webhook_steps(
        self,
        timeout_minutes: Optional[int] = None,
    ) -> WebhookReconcileResult:
        """Find overdue WFW steps and fire the still-waiting notification once each."""
        threshold = (
            timeout_minutes
            if timeout_minutes is not None
            else settings.WEBHOOK_NOTIFY_MINUTES
        )

        steps = (
            await self.step_execution_repository.list_webhook_steps_awaiting_reconcile(
                timeout_minutes=threshold
            )
        )

        steps_notified = 0
        for step in steps:
            try:
                if await self._notify_step(step):
                    steps_notified += 1
            except Exception as e:
                logger.error(
                    f"Webhook notify failed for step {step.id} "
                    f"(instance={step.instance_id}, key={step.step_key}): {safe_error_message(e)}"
                )

        if steps:
            logger.info(
                f"Webhook notify sweep: examined {len(steps)} parked steps, "
                f"notified {steps_notified} (threshold {threshold} min)"
            )

        return WebhookReconcileResult(
            steps_examined=len(steps),
            steps_notified=steps_notified,
            timestamp=datetime.now(UTC).isoformat(),
            threshold_minutes=threshold,
        )

    async def _notify_step(self, step: StepExecution) -> bool:
        """Fire the still-waiting notification once for one parked step.

        Returns True if a notification fired (first time past the window), False
        if already notified this WFW entry or the instance is gone.
        """
        if step.execution_data.get(_NOTIFIED_FLAG):
            return False

        instance = await self.instance_repository.get_by_id(step.instance_id)
        if instance is None:
            return False

        # Stamp the flag first and persist, so a notifier failure cannot cause a
        # re-fire next cycle (the notification is best-effort; the nudge is not
        # worth re-spamming the operator if the WS/bell write hiccups).
        step.execution_data[_NOTIFIED_FLAG] = datetime.now(UTC).isoformat()
        await self.step_execution_repository.update(step)

        if self.notifier is not None:
            display = instance.workflow_name or "Workflow"
            await self.notifier.announce_state_change(
                instance=instance,
                action_type="waiting_webhook_reminder",
                step_id=step.step_key,
                session=self.session,
                title_override="Still Awaiting Provider Callback",
                message_override=(
                    f"{display} has been waiting for the provider callback on "
                    f"step '{step.step_key}' longer than expected. The run is "
                    "parked, not failed - use Check Status to poll the provider, "
                    "or verify the webhook is configured."
                ),
            )
        return True


__all__ = ["WebhookReconcileSweepService", "WebhookReconcileResult"]
