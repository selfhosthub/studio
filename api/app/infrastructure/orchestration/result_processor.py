# api/app/infrastructure/orchestration/result_processor.py

"""Processes step results, drives workflow execution, manages inline-chain session state.

RLS: uses a service-account session (app.is_service_account=true) - this processor
handles results for every org and authorizes via the payload's organization_id.

Inline execution (set_fields/log/notify) runs synchronously and recurses back into
process_result(). A ContextVar shares the outer session so the orchestrator sees
every prior completion when deciding what comes next.
"""

import logging
from contextvars import ContextVar
from typing import Awaitable, Callable, Optional, Dict, Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config.settings import settings
from app.domain.instance.models import Instance
from app.infrastructure.repositories.instance_repository import (
    SQLAlchemyInstanceRepository,
)
from app.infrastructure.repositories.step_execution_repository import (
    SQLAlchemyStepExecutionRepository,
)
from app.infrastructure.repositories.org_file_repository import (
    SQLAlchemyOrgFileRepository,
)
from app.infrastructure.repositories.iteration_execution_repository import (
    SQLAlchemyIterationExecutionRepository,
)
from app.domain.instance_step.models import StepExecutionStatus
from app.infrastructure.repositories.notification_repository import (
    SQLAlchemyNotificationRepository,
)
from app.infrastructure.repositories.organization_repository import (
    SQLAlchemyUserRepository,
)
from app.infrastructure.repositories.provider_repository import (
    SQLAlchemyProviderServiceRepository,
)
from app.domain.workflow import WorkflowNavigator, apply_output_forwarding
from app.application.services.result_processing import (
    OutputExtractor,
    IterationHandler,
    ResultProcessingService,
    StepResultPayload,
    resources_to_downloaded_files,
)
from app.application.services.instance_notifier import InstanceNotifier
from app.application.services.instance import (
    WorkflowOrchestrator,
    OrchestrationAction,
)
from app.application.services.instance.status_derivation import (
    derive_instance_step_status_dict,
)
from app.application.services.instance.helpers import get_active_op_for_step
from app.infrastructure.orchestration.action_executor import (
    ActionExecutor,
    ActionContext,
)
from app.infrastructure.services import ApprovalStepFinder

logger = logging.getLogger(__name__)

_inline_session: ContextVar[Optional[AsyncSession]] = ContextVar(
    "_inline_session", default=None
)


class ResultProcessor:
    """Processes step results and manages workflow execution flow."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        broadcast_instance_update_fn: Callable[..., Awaitable[None]],
        broadcast_notification_fn: Callable[..., Awaitable[None]],
    ):
        self.session_factory = session_factory
        self.notifier = InstanceNotifier(
            broadcast_instance_update_fn=broadcast_instance_update_fn,
            notification_repo_factory=SQLAlchemyNotificationRepository,
            user_repo_factory=SQLAlchemyUserRepository,
            broadcast_notification_fn=broadcast_notification_fn,
        )
        self.orchestrator = WorkflowOrchestrator()
        self.processing_service = ResultProcessingService(
            orchestrator=self.orchestrator,
            output_extractor=OutputExtractor(),
            iteration_handler=IterationHandler(),
        )
        self.action_executor = ActionExecutor(
            notifier=self.notifier,
            get_all_step_results_fn=self._get_all_step_results,
            process_result_fn=self.process_result,
        )
        self.approval_step_finder = ApprovalStepFinder()

    async def process_result(self, payload: Dict[str, Any]) -> None:
        """Process a single step result.

        Inside an inline chain, reuses the outer session (see _inline_session).
        """
        parsed = StepResultPayload.from_dict(payload)
        if parsed is None:
            return

        existing = _inline_session.get(None)
        if existing is not None:
            await self._process_with_session(existing, payload, parsed)
            return

        try:
            async with self.session_factory() as session:
                token = _inline_session.set(session)
                try:
                    await self._process_with_session(session, payload, parsed)
                finally:
                    _inline_session.reset(token)

        except Exception as e:
            context = getattr(e, "context", None) or {}
            logger.error(
                f"Error processing step result for {parsed.instance_id}/{parsed.step_id}: {e}"
                + (f" context={context}" if context else ""),
            )

    async def _process_with_session(
        self,
        session: AsyncSession,
        payload: Dict[str, Any],
        parsed: StepResultPayload,
    ) -> None:
        instance_repo = SQLAlchemyInstanceRepository(session)
        step_execution_repo = SQLAlchemyStepExecutionRepository(session)
        provider_service_repo = SQLAlchemyProviderServiceRepository(session)
        resource_repo = SQLAlchemyOrgFileRepository(session)
        iteration_execution_repo = SQLAlchemyIterationExecutionRepository(session)

        outcome = await self.processing_service.process_step_result(
            session=session,
            payload=payload,
            instance_repo=instance_repo,
            step_execution_repo=step_execution_repo,
            provider_service_repo=provider_service_repo,
            resource_repo=resource_repo,
            iteration_execution_repo=iteration_execution_repo,
        )

        if outcome is None:
            return

        if parsed.is_queued:
            await session.commit()
            await self.notifier.announce_state_change(
                instance=outcome.instance,
                action_type="progress",
                step_id=outcome.step_id,
            )
            return

        if parsed.is_processing:
            await session.commit()
            await self.notifier.announce_state_change(
                instance=outcome.instance,
                action_type="step_started",
                step_id=outcome.step_id,
            )
            return

        # Resources must be created before action execution so downstream steps see the files.
        result_data = outcome.result_data

        # For iteration jobs we want only the current iteration's files; outcome.result_data
        # may have already aggregated all iterations on the final one.
        if parsed.is_iteration_job:
            downloaded_files = parsed.result_data.get("downloaded_files", [])
        else:
            downloaded_files = result_data.get("downloaded_files", [])

        if downloaded_files:
            if parsed.is_iteration_job and parsed.iteration_index is not None:
                for f in downloaded_files:
                    if "iteration_index" not in f:
                        f["iteration_index"] = parsed.iteration_index

            # Workers upload files before posting results - OrgFile records already exist.
            # Stamp metadata (iteration_index, index, seed, etc.) onto existing records
            # matched by virtual_path; do NOT create duplicates via OrgFileCreator.
            existing = await resource_repo.list_by_job(outcome.job.id)
            by_vpath = {r.virtual_path: r for r in existing}
            for f in downloaded_files:
                resource = by_vpath.get(f.get("virtual_path", ""))
                if resource is None:
                    continue
                meta = dict(resource.metadata or {})
                for key in (
                    "iteration_index",
                    "index",
                    "seed",
                    "thumbnail_path",
                    "original_filename",
                    "width",
                    "height",
                    "duration",
                ):
                    if key in f:
                        meta[key] = f[key]
                resource.metadata = meta
                if f.get("display_name"):
                    resource.display_name = f["display_name"]
                await resource_repo.update(resource)

            # Rebuild from live resources so deletions during regeneration are reflected.
            all_resources = await resource_repo.list_by_job(outcome.job.id)
            rebuilt_files = resources_to_downloaded_files(
                all_resources, api_base_url=settings.API_BASE_URL
            )
            result_data["downloaded_files"] = rebuilt_files

            if (
                outcome.job.extracted_outputs
                and "downloaded_files" in outcome.job.extracted_outputs
            ):
                outcome.job.extracted_outputs["downloaded_files"] = rebuilt_files
                outcome.job.extracted_outputs["image_count"] = len(rebuilt_files)
                await step_execution_repo.update(outcome.job)

        if outcome.skip_action_execution:
            await session.commit()
            await self.notifier.announce_state_change(
                instance=outcome.instance,
                action_type="progress",
                step_id=outcome.step_id,
                error=outcome.error,
                result_data={"step_result": result_data},
            )
            return

        if outcome.error:
            await self._cancel_pending_jobs_for_instance(
                step_execution_repo, outcome.instance, outcome.step_id
            )

        # Approval-step lookup is async, so the service returns approval_step_id=None
        # and we patch the action here if needed.
        action = outcome.action
        if action.action == OrchestrationAction.ENQUEUE_STEPS:
            steps = (outcome.instance.workflow_snapshot or {}).get("steps", {})
            next_steps = WorkflowNavigator.get_ready_steps(
                steps,
                set(outcome.instance.build_completed_step_ids()),
                derive_instance_step_status_dict(outcome.instance),
            )
            if next_steps:
                approval_step_id = await self.approval_step_finder.find_approval_step(
                    outcome.instance, next_steps, provider_service_repo
                )
                if approval_step_id:
                    action = self.orchestrator.determine_next_action(
                        instance=outcome.instance,
                        completed_step_id=outcome.step_id,
                        step_failed=outcome.error is not None,
                        error_message=outcome.error,
                        approval_step_id=approval_step_id,
                        is_debug_mode=outcome.instance.is_debug_mode,
                    )

        context = ActionContext(
            session=session,
            instance=outcome.instance,
            instance_id=outcome.instance.id,
            step_id=outcome.step_id,
            result_data=result_data,
            instance_repo=instance_repo,
            step_execution_repo=step_execution_repo,
            provider_service_repo=provider_service_repo,
            error=outcome.error,
        )
        if parsed.is_iteration_job:
            await self.notifier.announce_state_change(
                instance=outcome.instance,
                action_type="step_completed",
                step_id=outcome.step_id,
                result_data={"step_result": result_data},
            )

        action_handled = await self.action_executor.execute(action, context)

        op = get_active_op_for_step(outcome.instance, outcome.step_id)
        if op is not None:
            op_type_str = op.get("type", "")
            is_regen = op_type_str.startswith("regenerate_")
            staged_ids = list(op.get("staged_deletion_resource_ids") or [])
            regen_success = is_regen and outcome.error is None

            from app.domain.instance.models import OperationType

            try:
                op_type_enum = OperationType(op_type_str)
            except ValueError:
                op_type_enum = None
            isolated_success = (
                op_type_enum is not None
                and op_type_enum.is_isolated
                and outcome.error is None
            )
            # Active op was discovered via get_active_op_for_step, so the lookup is safe.
            step_for_op = outcome.instance.step_entities[outcome.step_id]
            if isolated_success:
                outcome.instance.status = step_for_op.complete_operation()
            else:
                step_for_op.complete_operation_tracking()
            await instance_repo.update(outcome.instance)

            if regen_success and staged_ids and resource_repo is not None:
                await self.processing_service._delete_staged_resources(
                    staged_ids,
                    resource_repo,
                    instance_id=outcome.instance.id,
                    step_id=outcome.step_id,
                )

            if action_handled:
                # Terminal handler already committed; commit the tracking clear.
                await session.commit()

        if action_handled:
            return

        await session.commit()
        await self.notifier.announce_state_change(
            instance=outcome.instance,
            action_type="progress",
            step_id=outcome.step_id,
            error=outcome.error,
            result_data={"step_result": result_data},
        )

    async def _cancel_pending_jobs_for_instance(
        self,
        step_execution_repo: SQLAlchemyStepExecutionRepository,
        instance: Instance,
        failed_step_id: str,
    ) -> int:
        """Cancel all pending/queued steps when one step fails."""
        jobs = await step_execution_repo.list_by_instance(
            skip=0, limit=settings.DEFAULT_FETCH_LIMIT, instance_id=instance.id
        )
        cancellable_statuses = [StepExecutionStatus.PENDING, StepExecutionStatus.QUEUED]
        cancelled_count = 0

        for job in jobs:
            if job.step_key == failed_step_id:
                continue
            if job.status not in cancellable_statuses:
                continue

            try:
                # One load, one update: a second domain object mapping to the same
                # row would cause clobbering full-row UPDATEs.
                job.cancel()
                await step_execution_repo.update(job)
                cancelled_count += 1
                logger.debug(f"Cancelled pending job {job.id} (step {job.step_key})")
            except Exception as e:
                logger.warning(f"Failed to cancel job {job.id}: {e}")

        if cancelled_count > 0:
            logger.info(
                f"Cancelled {cancelled_count} pending jobs for instance {instance.id} "
                f"after step {failed_step_id} failed"
            )

        return cancelled_count

    async def _get_all_step_results(
        self,
        step_execution_repo: SQLAlchemyStepExecutionRepository,
        resource_repo: SQLAlchemyOrgFileRepository,
        instance_id: UUID,
        workflow_snapshot: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Collect every completed step's outputs for variable resolution.

        Rebuilds downloaded_files from the live resources table so deleted files
        are not passed downstream. Honours output_forwarding when configured.
        """
        results = {}
        jobs = await step_execution_repo.list_by_instance(
            skip=0, limit=100, instance_id=instance_id
        )
        for job in jobs:
            if job.status == StepExecutionStatus.COMPLETED:
                step_result = job.get_outputs()
                logger.debug(
                    f"Building step result for '{job.step_key}': "
                    f"extracted_outputs={bool(job.extracted_outputs)}, "
                    f"result_keys={list(step_result.keys())}"
                )

                if "downloaded_files" in step_result:
                    resources = await resource_repo.list_by_job(job.id)
                    step_result["downloaded_files"] = resources_to_downloaded_files(
                        resources, api_base_url=settings.API_BASE_URL
                    )
                    step_result["image_count"] = len(resources)
                    logger.debug(
                        f"Step {job.step_key} has {len(resources)} files for iteration"
                    )

                results[job.step_key] = step_result

                if job.execution_data and "_prompt_variables" in job.execution_data:
                    prompt_vars = job.execution_data["_prompt_variables"]
                    step_result["_prompt_variables"] = prompt_vars
                    for var_name, var_value in prompt_vars.items():
                        if var_name not in step_result:
                            step_result[var_name] = var_value

        if workflow_snapshot:
            steps_config = workflow_snapshot.get("steps", {})
            for step_id, step_cfg in steps_config.items():
                fwd_cfg = (
                    step_cfg.get("output_forwarding")
                    if isinstance(step_cfg, dict)
                    else None
                )
                if fwd_cfg:
                    logger.debug(
                        f"[OUTPUT_FORWARDING_CHECK] Step '{step_id}' has output_forwarding: {fwd_cfg}, "
                        f"depends_on: {step_cfg.get('depends_on')}"
                    )
            before_summary = {
                k: list(v.keys()) if isinstance(v, dict) else type(v).__name__
                for k, v in results.items()
            }
            logger.debug(f"[OUTPUT_FORWARDING] Before: {before_summary}")
            results = apply_output_forwarding(results, steps_config)
            after_summary = {
                k: list(v.keys()) if isinstance(v, dict) else type(v).__name__
                for k, v in results.items()
            }
            logger.debug(f"[OUTPUT_FORWARDING] After: {after_summary}")

        return results
