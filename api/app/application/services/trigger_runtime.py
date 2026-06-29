# api/app/application/services/trigger_runtime.py

"""System-actor runtime for non-HTTP workflow triggers (schedule + event).

Both the schedule tick and the instance-completion event hook need to create
workflow instances outside any HTTP request — as a trusted system actor, spanning
all orgs (non-RLS). This module centralizes the InstanceService assembly and the
event-chaining fan-out so those two callers stay in sync.
"""

import logging
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.application.interfaces import EventBus
from app.application.services.form_field_resolver import FormFieldResolver
from app.application.services.instance_service import InstanceService
from app.application.services.job_enqueue import JobEnqueueService
from app.application.services.prompt_service import PromptService
from app.application.services.trigger_dispatcher import TriggerDispatcher
from app.infrastructure.errors import safe_error_message
from app.infrastructure.messaging.job_status_publisher import DirectJobStatusPublisher
from app.infrastructure.repositories.instance_repository import (
    SQLAlchemyInstanceRepository,
)
from app.infrastructure.repositories.iteration_execution_repository import (
    SQLAlchemyIterationExecutionRepository,
)
from app.infrastructure.repositories.organization_repository import (
    SQLAlchemyOrganizationRepository,
)
from app.infrastructure.repositories.prompt_repository import SQLAlchemyPromptRepository
from app.infrastructure.repositories.provider_repository import (
    SQLAlchemyProviderCredentialRepository,
    SQLAlchemyProviderRepository,
    SQLAlchemyProviderServiceRepository,
)
from app.infrastructure.repositories.queue_job_repository import (
    SQLAlchemyQueuedJobRepository,
)
from app.infrastructure.repositories.step_execution_repository import (
    SQLAlchemyStepExecutionRepository,
)
from app.infrastructure.repositories.workflow_repository import (
    SQLAlchemyWorkflowRepository,
)

if TYPE_CHECKING:
    from app.application.services.instance_notifier import InstanceNotifier
    from app.domain.instance.models import Instance

logger = logging.getLogger(__name__)

ProcessResultFn = Callable[[Dict[str, Any]], Awaitable[None]]

# Hard ceiling on event-trigger chain depth so an A→B→A cycle can't loop forever.
MAX_EVENT_DEPTH = 10

# action_type (from InstanceNotifier terminal announce) -> event_on values it satisfies.
_ACTION_MATCHES = {
    "completed": {"completed", "terminal"},
    "failed": {"failed", "terminal"},
}


def build_form_field_resolver(session: AsyncSession) -> FormFieldResolver:
    """Session-bound FormFieldResolver for the trigger paths (schedule/event)."""
    return FormFieldResolver(
        provider_service_repository=SQLAlchemyProviderServiceRepository(session),
        prompt_repository=SQLAlchemyPromptRepository(session),
    )


def build_system_instance_service(
    session: AsyncSession,
    event_bus: EventBus,
    process_result_fn: ProcessResultFn,
    notifier: Optional["InstanceNotifier"],
) -> InstanceService:
    """Assemble a non-RLS InstanceService bound to one session (mirrors the
    public-webhook bypass wiring; the caller is a trusted system actor)."""
    workflow_repo = SQLAlchemyWorkflowRepository(session)
    organization_repo = SQLAlchemyOrganizationRepository(session)
    provider_repo = SQLAlchemyProviderRepository(session)
    provider_service_repo = SQLAlchemyProviderServiceRepository(session)
    credential_repo = SQLAlchemyProviderCredentialRepository(session)
    queued_job_repo = SQLAlchemyQueuedJobRepository(session)
    step_execution_repo = SQLAlchemyStepExecutionRepository(session)
    iteration_execution_repo = SQLAlchemyIterationExecutionRepository(session)
    prompt_service = PromptService(repository=SQLAlchemyPromptRepository(session))
    status_publisher = DirectJobStatusPublisher(process_result_fn)
    job_enqueue_service = JobEnqueueService(
        workflow_repository=workflow_repo,
        credential_repository=credential_repo,
        provider_repository=provider_repo,
        provider_service_repository=provider_service_repo,
        organization_repository=organization_repo,
        queued_job_repository=queued_job_repo,
        prompt_service=prompt_service,
        status_publisher=status_publisher,
        iteration_execution_repository=iteration_execution_repo,
        step_execution_repository=step_execution_repo,
    )
    return InstanceService(
        instance_repository=SQLAlchemyInstanceRepository(session),
        step_execution_repository=step_execution_repo,
        workflow_repository=workflow_repo,
        organization_repository=organization_repo,
        event_bus=event_bus,
        provider_repository=provider_repo,
        credential_repository=credential_repo,
        job_enqueue_service=job_enqueue_service,
        queued_job_repository=queued_job_repo,
        iteration_execution_repository=iteration_execution_repo,
        notifier=notifier,
    )


async def fire_event_triggers(
    session: AsyncSession,
    instance: "Instance",
    action_type: str,
    *,
    event_bus: EventBus,
    process_result_fn: ProcessResultFn,
    notifier: Optional["InstanceNotifier"],
) -> None:
    """Fan out to workflows whose EVENT trigger is bound to `instance`'s workflow.

    Best-effort: a failure to fire one downstream workflow is logged and never
    propagates back into the source instance's completion path.
    """
    matches = _ACTION_MATCHES.get(action_type)
    if not matches:
        return

    source_meta = getattr(instance, "client_metadata", None) or {}
    depth = int(source_meta.get("event_depth", 0))
    if depth >= MAX_EVENT_DEPTH:
        logger.warning(
            f"Event-trigger chain hit max depth ({MAX_EVENT_DEPTH}) at instance "
            f"{instance.id}; not firing further downstream workflows."
        )
        return

    try:
        workflow_repo = SQLAlchemyWorkflowRepository(session)
        targets = await workflow_repo.list_event_triggered_by(instance.workflow_id)
    except Exception as e:
        logger.error(f"Event-trigger lookup failed: {safe_error_message(e)}")
        return

    if not targets:
        return

    payload = {
        "source_instance_id": str(instance.id),
        "source_workflow_id": str(instance.workflow_id),
        "output_data": getattr(instance, "output_data", None) or {},
    }
    dispatcher = TriggerDispatcher(
        build_system_instance_service(
            session, event_bus, process_result_fn, notifier
        ),
        build_form_field_resolver(session),
    )
    for target in targets:
        if target.id == instance.workflow_id:
            continue  # self-trigger guard (defense-in-depth; also blocked at set time)
        if getattr(target, "event_on", "completed") not in matches:
            continue
        try:
            await dispatcher.fire(
                target,
                payload=payload,
                source="event",
                extra_metadata={
                    "event_depth": depth + 1,
                    "source_instance_id": str(instance.id),
                },
            )
        except Exception as e:
            logger.error(
                f"Event trigger failed firing workflow {target.id} from instance "
                f"{instance.id}: {safe_error_message(e)}"
            )


__all__ = [
    "build_form_field_resolver",
    "build_system_instance_service",
    "fire_event_triggers",
    "MAX_EVENT_DEPTH",
]
