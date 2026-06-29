# api/app/infrastructure/scheduling/schedule_task.py

"""Periodic schedule-trigger tick: fire workflows whose next_run_at is due.

Runs in the single API process (the same in-process scheduler that runs cleanup),
so there is exactly one ticker — no distributed-lock needed. Each cycle opens a
fresh non-RLS session (system scheduler spans all orgs), fires every due workflow
through the shared TriggerDispatcher, then advances next_run_at from its RRULE.
A workflow that fails to fire is logged and skipped; its next_run_at still advances
so one bad run doesn't wedge the schedule.
"""

import logging
from datetime import UTC, datetime
from typing import Any, Awaitable, Callable, Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.interfaces import EventBus
from app.application.services.instance_notifier import InstanceNotifier
from app.application.services.trigger_dispatcher import TriggerDispatcher
from app.application.services.trigger_runtime import (
    build_form_field_resolver,
    build_system_instance_service,
)
from app.infrastructure.errors import safe_error_message
from app.infrastructure.repositories.workflow_repository import (
    SQLAlchemyWorkflowRepository,
)
from app.infrastructure.scheduling.rrule_schedule import (
    ScheduleError,
    compute_next_run,
)

logger = logging.getLogger(__name__)

ProcessResultFn = Callable[[Dict[str, Any]], Awaitable[None]]


def build_schedule_callback(
    session_factory: async_sessionmaker[AsyncSession],
    event_bus: EventBus,
    process_result_fn: ProcessResultFn,
    notifier: Optional[InstanceNotifier] = None,
):
    """Build a zero-arg async callback that fires all due schedule-trigger workflows."""

    async def _run_schedule_cycle() -> None:
        now = datetime.now(UTC)
        try:
            async with session_factory() as session:
                workflow_repo = SQLAlchemyWorkflowRepository(session)
                due = await workflow_repo.get_due_schedules(now)
                if not due:
                    return

                instance_service = build_system_instance_service(
                    session, event_bus, process_result_fn, notifier
                )
                dispatcher = TriggerDispatcher(
                    instance_service, build_form_field_resolver(session)
                )

                for workflow in due:
                    try:
                        instance = await dispatcher.fire(
                            workflow,
                            payload={"scheduled_at": now.isoformat()},
                            source="schedule",
                        )
                        if notifier is not None and instance is not None:
                            await notifier.announce_schedule_fired(
                                session=session,
                                organization_id=instance.organization_id,
                                instance_id=instance.id,
                                workflow_id=instance.workflow_id,
                                workflow_name=getattr(
                                    instance, "workflow_name", None
                                ),
                            )
                    except Exception as e:
                        logger.error(
                            f"Schedule fire failed for workflow {workflow.id}: "
                            f"{safe_error_message(e)}"
                        )

                    # Advance the schedule regardless of fire outcome so a single
                    # failure doesn't stall every future run.
                    workflow.schedule_last_run_at = now
                    try:
                        workflow.schedule_next_run_at = compute_next_run(
                            workflow.schedule_dtstart,
                            workflow.schedule_rrule,
                            workflow.schedule_timezone,
                            after=now,
                        )
                    except ScheduleError as e:
                        # Bad rule: disable so we stop re-selecting it every tick.
                        logger.error(
                            f"Disabling schedule for workflow {workflow.id}: {e}"
                        )
                        workflow.schedule_enabled = False
                        workflow.schedule_next_run_at = None
                    await workflow_repo.update(workflow)
        except Exception as e:
            logger.error(
                f"Schedule cycle could not open session: {safe_error_message(e)}"
            )

    return _run_schedule_cycle


__all__ = ["build_schedule_callback"]
