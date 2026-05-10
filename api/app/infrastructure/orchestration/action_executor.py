# api/app/infrastructure/orchestration/action_executor.py

"""Executes orchestration actions: instance state transitions, enqueueing, notifications."""

import logging
from dataclasses import dataclass
from datetime import datetime, UTC
from typing import Any, Dict, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.instance.models import InstanceStatus, Instance
from app.domain.instance.repository import InstanceRepository
from app.domain.instance_step.models import StepExecutionStatus
from app.domain.instance_step.step_execution_repository import (
    StepExecutionRepository,
)
from app.domain.provider.repository import ProviderServiceRepository
from app.infrastructure.repositories.workflow_repository import (
    SQLAlchemyWorkflowRepository,
)
from app.infrastructure.repositories.provider_repository import (
    SQLAlchemyProviderRepository,
    SQLAlchemyProviderCredentialRepository,
)
from app.infrastructure.repositories.queue_job_repository import (
    SQLAlchemyQueuedJobRepository,
)
from app.infrastructure.repositories.iteration_execution_repository import (
    SQLAlchemyIterationExecutionRepository,
)
from app.infrastructure.repositories.org_file_repository import (
    SQLAlchemyOrgFileRepository,
)
from app.application.services.job_enqueue import (
    EmptyIterationSourceError,
    JobEnqueueService,
    ProviderInactiveError,
    ServiceInactiveError,
)
from app.application.services.prompt_service import PromptService
from app.infrastructure.repositories.prompt_repository import (
    SQLAlchemyPromptRepository,
)
from app.application.services.instance_notifier import InstanceNotifier
from app.application.services.instance import (
    NextAction,
    OrchestrationAction,
)

logger = logging.getLogger(__name__)


@dataclass
class ActionContext:
    session: AsyncSession
    instance: Instance
    instance_id: UUID
    step_id: str
    result_data: Dict[str, Any]
    instance_repo: InstanceRepository
    step_execution_repo: StepExecutionRepository
    provider_service_repo: ProviderServiceRepository
    error: Optional[str] = None

    @property
    def instance_step_repo(self) -> StepExecutionRepository:
        # Legacy alias.
        return self.step_execution_repo

    @property
    def job_repo(self) -> StepExecutionRepository:
        # Legacy alias.
        return self.step_execution_repo


class ActionExecutor:
    """Applies side effects (DB commits, notifications, enqueue) for orchestration actions.

    Domain entities own the state transitions; this class wires them to infrastructure.
    """

    def __init__(
        self,
        notifier: InstanceNotifier,
        get_all_step_results_fn,
        process_result_fn=None,
    ):
        self.notifier = notifier
        self._get_all_step_results = get_all_step_results_fn
        self._process_result_fn = process_result_fn

    async def execute(
        self,
        action: NextAction,
        context: ActionContext,
    ) -> bool:
        """Execute an orchestration action. Returns True if processing should stop."""
        match action.action:
            case OrchestrationAction.FAIL:
                return await self._handle_fail(action, context)
            case OrchestrationAction.STOP:
                return await self._handle_stop(action, context)
            case OrchestrationAction.COMPLETE:
                return await self._handle_complete(action, context)
            case OrchestrationAction.WAIT_APPROVAL:
                return await self._handle_wait_approval(action, context)
            case OrchestrationAction.WAIT_MANUAL:
                return await self._handle_wait_manual(action, context)
            case OrchestrationAction.WAIT_DEBUG:
                return await self._handle_wait_debug(action, context)
            case OrchestrationAction.ENQUEUE_STEPS:
                return await self._handle_enqueue_steps(action, context)

        return False

    async def _cancel_remaining_non_terminal_steps(
        self, ctx: ActionContext
    ) -> None:
        """Mark every non-terminal step CANCELLED so the UI can flip from Cancel to Run Again.

        Without this, steps that were PENDING at instance creation but never enqueued
        (because the failure short-circuited orchestration) stay PENDING forever.
        """
        terminal = {
            StepExecutionStatus.COMPLETED,
            StepExecutionStatus.FAILED,
            StepExecutionStatus.SKIPPED,
            StepExecutionStatus.CANCELLED,
        }
        try:
            all_steps = await ctx.step_execution_repo.list_by_instance(
                ctx.instance_id
            )
        except Exception as exc:
            logger.warning(
                f"Failed to list step_executions for instance {ctx.instance_id} "
                f"during fail sweep: {exc}"
            )
            return
        for step in all_steps:
            if step.status in terminal:
                continue
            try:
                step.cancel()
                await ctx.step_execution_repo.update(step)
            except Exception as exc:
                # One stuck step shouldn't block the broader fail flow.
                logger.warning(
                    f"Failed to cancel step {step.step_key} during instance "
                    f"{ctx.instance_id} fail sweep: {exc}"
                )

    async def _handle_fail(
        self,
        action: NextAction,
        ctx: ActionContext,
    ) -> bool:
        error_msg = action.error_message or ctx.error or "Step failed"

        ctx.instance.fail(
            error_message=error_msg,
            error_data={"error": error_msg, "step_id": ctx.step_id},
        )
        await ctx.instance_repo.update(ctx.instance)
        await self._cancel_remaining_non_terminal_steps(ctx)

        await self.notifier.announce_state_change(
            instance=ctx.instance,
            action_type="failed",
            step_id=ctx.step_id,
            error=error_msg,
            result_data={"step_result": ctx.result_data},
            session=ctx.session,
        )

        return True

    async def _handle_stop(
        self,
        action: NextAction,
        ctx: ActionContext,
    ) -> bool:
        stop_step_id = action.waiting_step_id
        assert stop_step_id is not None, "STOP action requires waiting_step_id"

        stop_step_entity = await ctx.step_execution_repo.get_by_instance_and_key(
            ctx.instance_id, stop_step_id
        )
        if stop_step_entity:
            stop_step_entity.stop()
            await ctx.step_execution_repo.update(stop_step_entity)

        ctx.instance.complete(force=True)
        await ctx.instance_repo.update(ctx.instance)

        logger.info(f"Instance completed early: step={stop_step_id}")

        await self.notifier.announce_state_change(
            instance=ctx.instance,
            action_type="completed",
            step_id=ctx.step_id,
            result_data={
                "step_result": ctx.result_data,
                "stopped_at": stop_step_id,
            },
            session=ctx.session,
        )

        return True

    async def _handle_complete(
        self,
        action: NextAction,
        ctx: ActionContext,
    ) -> bool:
        ctx.instance.complete()
        await ctx.instance_repo.update(ctx.instance)

        logger.info(f"Instance completed: step={ctx.step_id}")

        await self.notifier.announce_state_change(
            instance=ctx.instance,
            action_type="completed",
            step_id=ctx.step_id,
            result_data={"step_result": ctx.result_data},
            session=ctx.session,
        )

        return True

    async def _handle_wait_approval(
        self,
        action: NextAction,
        ctx: ActionContext,
    ) -> bool:
        approval_step_id = action.waiting_step_id
        assert (
            approval_step_id is not None
        ), "WAIT_APPROVAL action requires waiting_step_id"

        ctx.instance.wait_for_approval(approval_step_id)

        if "pending_approval" not in ctx.instance.output_data:
            ctx.instance.output_data["pending_approval"] = {}
        ctx.instance.output_data["pending_approval"] = {
            "step_id": approval_step_id,
            "waiting_since": datetime.now(UTC).isoformat(),
        }

        approval_step_entity = await ctx.step_execution_repo.get_by_instance_and_key(
            ctx.instance_id, approval_step_id
        )
        if approval_step_entity:
            approval_step_entity.wait_for_approval()
            await ctx.step_execution_repo.update(approval_step_entity)
        else:
            logger.error(
                f"StepExecution entity not found for approval step "
                f"{approval_step_id} on instance {ctx.instance_id}"
            )

        await ctx.instance_repo.update(ctx.instance)

        logger.info(f"Waiting for approval: step={approval_step_id}")

        await self.notifier.announce_state_change(
            instance=ctx.instance,
            action_type="waiting_approval",
            step_id=approval_step_id,
            result_data={"waiting_for_approval": True},
            session=ctx.session,
        )

        return True

    async def _handle_wait_manual(
        self,
        action: NextAction,
        ctx: ActionContext,
    ) -> bool:
        manual_step_id = action.waiting_step_id
        assert manual_step_id is not None, "WAIT_MANUAL action requires waiting_step_id"

        ctx.instance.wait_for_manual_trigger(manual_step_id)

        if "pending_trigger" not in ctx.instance.output_data:
            ctx.instance.output_data["pending_trigger"] = {}
        ctx.instance.output_data["pending_trigger"] = {
            "step_id": manual_step_id,
            "waiting_since": datetime.now(UTC).isoformat(),
        }

        manual_step_entity = await ctx.step_execution_repo.get_by_instance_and_key(
            ctx.instance_id, manual_step_id
        )
        if manual_step_entity:
            manual_step_entity.wait_for_manual_trigger()
            await ctx.step_execution_repo.update(manual_step_entity)
        else:
            logger.error(
                f"StepExecution entity not found for manual step "
                f"{manual_step_id} on instance {ctx.instance_id}"
            )

        await ctx.instance_repo.update(ctx.instance)

        logger.info(f"Waiting for manual trigger: step={manual_step_id}")

        await self.notifier.announce_state_change(
            instance=ctx.instance,
            action_type="waiting_manual_trigger",
            step_id=manual_step_id,
            result_data={"waiting_for_trigger": True},
            session=ctx.session,
        )

        return True

    async def _handle_wait_debug(
        self,
        action: NextAction,
        ctx: ActionContext,
    ) -> bool:
        completed_step_id = action.waiting_step_id
        pending_steps = action.step_ids or []

        ctx.instance.status = InstanceStatus.DEBUG_PAUSED
        ctx.instance.output_data["debug_paused"] = {
            "completed_step_id": completed_step_id,
            "pending_step_ids": pending_steps,
            "paused_at": datetime.now(UTC).isoformat(),
        }

        await ctx.instance_repo.update(ctx.instance)
        await ctx.session.commit()

        logger.info(f"Debug paused after step={completed_step_id} pending={pending_steps}")

        await self.notifier.announce_state_change(
            instance=ctx.instance,
            action_type="debug_paused",
            result_data={
                "completed_step_id": completed_step_id,
                "pending_step_ids": pending_steps,
                "debug_mode": True,
            },
        )

        return True

    async def _handle_enqueue_steps(
        self,
        action: NextAction,
        ctx: ActionContext,
    ) -> bool:
        workflow_repo = SQLAlchemyWorkflowRepository(ctx.session)
        credential_repo = SQLAlchemyProviderCredentialRepository(ctx.session)
        provider_repo = SQLAlchemyProviderRepository(ctx.session)
        queued_job_repo = SQLAlchemyQueuedJobRepository(ctx.session)
        resource_repo = SQLAlchemyOrgFileRepository(ctx.session)

        pt_repo = SQLAlchemyPromptRepository(ctx.session)
        pt_service = PromptService(repository=pt_repo)

        if self._process_result_fn:
            from app.infrastructure.messaging.job_status_publisher import (
                DirectJobStatusPublisher,
            )
            status_publisher = DirectJobStatusPublisher(self._process_result_fn)
        else:
            from app.infrastructure.messaging.job_status_publisher import (
                NullJobStatusPublisher,
            )
            status_publisher = NullJobStatusPublisher()

        iteration_execution_repo = SQLAlchemyIterationExecutionRepository(ctx.session)
        job_enqueue_service = JobEnqueueService(
            workflow_repository=workflow_repo,
            credential_repository=credential_repo,
            provider_repository=provider_repo,
            provider_service_repository=ctx.provider_service_repo,
            queued_job_repository=queued_job_repo,
            prompt_service=pt_service,
            status_publisher=status_publisher,
            iteration_execution_repository=iteration_execution_repo,
            step_execution_repository=ctx.step_execution_repo,
        )

        previous_results = await self._get_all_step_results(
            ctx.step_execution_repo,
            resource_repo,
            ctx.instance_id,
            ctx.instance.workflow_snapshot,
        )

        # Atomic claim guards against double-dispatch when parallel steps complete
        # simultaneously and both try to enqueue the same downstream step.
        enqueue_step_id: Optional[str] = None
        try:
            for next_step_id in action.step_ids:
                enqueue_step_id = next_step_id
                claimed = await ctx.step_execution_repo.claim_for_enqueue(
                    ctx.instance_id, next_step_id
                )
                if not claimed:
                    logger.debug(
                        f"Step {next_step_id} already claimed for instance "
                        f"{ctx.instance_id}, skipping enqueue"
                    )
                    continue

                await job_enqueue_service.enqueue_step(
                    instance_id=ctx.instance_id,
                    step_id=next_step_id,
                    organization_id=ctx.instance.organization_id,
                    workflow_snapshot=ctx.instance.workflow_snapshot or {},
                    instance_parameters=ctx.instance.input_data or {},
                    previous_step_results=previous_results,
                )
                logger.info(f"Step enqueued: step={next_step_id}")
        except (
            ProviderInactiveError,
            ServiceInactiveError,
            EmptyIterationSourceError,
        ) as e:
            error_msg = str(e)
            logger.error(
                f"Cannot enqueue step for instance {ctx.instance_id}: {error_msg}"
            )
            # PENDING → FAILED is reserved for enqueue-time contract violations (I-13)
            # so the UI surfaces the precise step that broke.
            if isinstance(e, EmptyIterationSourceError) and enqueue_step_id:
                step = await ctx.step_execution_repo.get_by_instance_and_key(
                    ctx.instance_id, enqueue_step_id
                )
                if step is not None:
                    step.fail(error_message=error_msg)
                    await ctx.step_execution_repo.update(step)
            ctx.instance.fail(
                error_message=error_msg,
                error_data={"error": error_msg, "step_id": enqueue_step_id},
            )
            await ctx.instance_repo.update(ctx.instance)
            await self._cancel_remaining_non_terminal_steps(ctx)

            await self.notifier.announce_state_change(
                instance=ctx.instance,
                action_type="failed",
                step_id=ctx.step_id,
                error=error_msg,
                result_data={"step_result": ctx.result_data},
                session=ctx.session,
            )
            return True

        # Refresh: inline execution chains create separate domain objects, and
        # without re-reading the outer call's stale Instance overwrites their updates.
        refreshed = await ctx.instance_repo.get_by_id(ctx.instance_id)
        if refreshed:
            ctx.instance = refreshed
        await ctx.instance_repo.update(ctx.instance)
        return False
