# api/app/application/services/result_processing/result_processing_service.py

"""Application layer service that orchestrates step result processing."""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.instance.models import Instance, InstanceStatus
from app.domain.instance_step.step_execution import StepExecution
from app.domain.instance_step.models import StepExecutionStatus
from app.application.services.instance import (
    WorkflowOrchestrator,
    NextAction,
    OrchestrationAction,
)
from app.application.services.instance.helpers import get_active_op_for_step
from app.application.services.result_processing.output_extractor import OutputExtractor
from app.application.services.result_processing.iteration_handler import (
    IterationHandler,
    IterationStatus,
    IterationResult,
)
from app.application.services.result_processing.step_result_handler import (
    StepResultHandler,
)

logger = logging.getLogger(__name__)


@dataclass
class StepResultPayload:
    """
    Parsed step result payload from worker HTTP submission.

    Provides strongly-typed access to payload fields with defaults.
    """

    instance_id: UUID
    step_id: str
    status: str  # QUEUED, PROCESSING, COMPLETED, FAILED
    result_data: Dict[str, Any]
    error: Optional[str]
    input_data: Dict[str, Any]
    request_body: Optional[Dict[str, Any]]
    # Iteration metadata
    iteration_index: Optional[int]
    iteration_count: Optional[int]
    iteration_group_id: Optional[str]
    # Per-iteration request params (set at enqueue time for immediate UI visibility)
    iteration_requests: Optional[List[Dict[str, Any]]] = None
    # Prompt variables (API-authoritative, set at enqueue time)
    prompt_variables: Optional[Dict[str, str]] = None

    @property
    def is_iteration_job(self) -> bool:
        """Check if this is an iteration job (has iteration metadata)."""
        return self.iteration_index is not None and self.iteration_count is not None

    @property
    def is_failed(self) -> bool:
        """Check if the step failed."""
        return self.status.upper() == "FAILED"

    @property
    def is_queued(self) -> bool:
        """Check if the step is queued."""
        return self.status.upper() == "QUEUED"

    @property
    def is_processing(self) -> bool:
        """Check if the step is processing."""
        return self.status.upper() == "PROCESSING"

    @property
    def is_completed(self) -> bool:
        """Check if the step completed (or any non-special status)."""
        return not (self.is_failed or self.is_queued or self.is_processing)

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> Optional["StepResultPayload"]:
        """
        Parse payload dict into StepResultPayload.

        Returns None if required fields are missing.
        """
        instance_id_str = payload.get("instance_id")
        step_id = payload.get("step_id")

        if not step_id:
            logger.error(f"Step result missing step_id: {payload}")
            return None

        if not instance_id_str:
            logger.error(f"Step result missing instance_id: {payload}")
            return None

        try:
            instance_id = UUID(instance_id_str)
        except (ValueError, TypeError) as e:
            logger.error(f"Invalid instance_id '{instance_id_str}': {e}")
            return None

        return cls(
            instance_id=instance_id,
            step_id=step_id,
            status=payload.get("status", "COMPLETED"),
            result_data=payload.get("result", {}),
            error=payload.get("error"),
            input_data=payload.get("input_data", {}),
            request_body=payload.get("request_body"),
            iteration_index=payload.get("iteration_index"),
            iteration_count=payload.get("iteration_count"),
            iteration_group_id=payload.get("iteration_group_id"),
            iteration_requests=payload.get("iteration_requests"),
            prompt_variables=payload.get("_prompt_variables"),
        )


@dataclass
class ProcessingOutcome:
    """
    Result of processing a step result.

    This value object is returned by ResultProcessingService.process_step_result()
    and tells the caller (ResultConsumer) what action to take.

    Fields:
        action: The next action determined by WorkflowOrchestrator
        instance: The workflow instance (after domain logic applied)
        job: The job execution (after domain logic applied)
        step_id: The step ID that was processed
        result_data: The step's result data
        error: Error message if step failed
        skip_action_execution: If True, caller should not execute the action
            (e.g., iteration in progress, QUEUED/PROCESSING status)
    """

    action: NextAction
    instance: Instance
    job: StepExecution
    step_id: str
    result_data: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    skip_action_execution: bool = False

    def __repr__(self) -> str:
        return (
            f"ProcessingOutcome(action={self.action}, step={self.step_id}, "
            f"skip={self.skip_action_execution}, error={self.error})"
        )


class ResultProcessingService:
    """Orchestrates step result processing; session lifecycle and side effects stay in the caller."""

    def __init__(
        self,
        orchestrator: WorkflowOrchestrator,
        output_extractor: OutputExtractor,
        iteration_handler: IterationHandler,
        step_result_handler: Optional[StepResultHandler] = None,
    ):
        self.orchestrator = orchestrator
        self.output_extractor = output_extractor
        self.iteration_handler = iteration_handler
        self.step_result_handler = step_result_handler or StepResultHandler()

    async def process_step_result(
        self,
        session: AsyncSession,
        payload: Dict[str, Any],
        instance_repo: Any,  # InstanceRepository
        step_execution_repo: Optional[Any] = None,  # StepExecutionRepository
        provider_service_repo: Optional[Any] = None,  # ProviderServiceRepository
        resource_repo: Optional[Any] = None,  # OrgFileRepository
        iteration_execution_repo: Optional[Any] = None,  # IterationExecutionRepository
        *,
        # Accepts legacy job_repo / instance_step_repo kwargs; folds into step_execution_repo.
        job_repo: Optional[Any] = None,
        instance_step_repo: Optional[Any] = None,
    ) -> Optional[ProcessingOutcome]:
        """Process a single step result. Does not commit - caller is responsible."""
        if step_execution_repo is None:
            step_execution_repo = job_repo or instance_step_repo
        if step_execution_repo is None:
            raise TypeError(
                "process_step_result requires step_execution_repo "
                "(or legacy job_repo / instance_step_repo)"
            )

        # 1. Parse and validate payload
        parsed = StepResultPayload.from_dict(payload)
        if parsed is None:
            return None  # Invalid payload, logged in from_dict

        logger.debug(
            f"Processing step result: instance={parsed.instance_id}, "
            f"step={parsed.step_id}, status={parsed.status}",
            extra={
                "instance_id": str(parsed.instance_id),
                "step_id": parsed.step_id,
            },
        )

        # 2. Fetch instance
        instance = await instance_repo.get_by_id(parsed.instance_id)
        if not instance:
            logger.error(f"Instance {parsed.instance_id} not found")
            return None

        # 3. Guard: Skip if instance is cancelled
        if instance.status == InstanceStatus.CANCELLED:
            # DEBUG, not INFO: cancelling mid-flight doesn't stop the worker
            # from finishing its current operation, so every subsequent status
            # the worker publishes for this job hits this guard. Normal and
            # expected - logging at INFO drowns the log wall with tens of
            # copies during rerun-after-cancel flows.
            logger.debug(
                f"Skipping result processing: instance {parsed.instance_id} is cancelled "
                f"(step={parsed.step_id})"
            )
            return None

        # 4. Fetch the StepExecution row. One row is both the "instance
        # step" (lifecycle state) and the "job" (worker dispatch state);
        # `job` and `instance_step` MUST therefore alias the same
        # Python object. Loading them via two separate queries
        # produces two domain objects mapping to the same row, and the
        # subsequent dual `repo.update(...)` writes clobber each other -
        # the second write overwrites the first because both are full-row
        # UPDATEs (incident: `output_data` populated but `result`/
        # `extracted_outputs` wiped on a COMPLETED step, which broke
        # downstream prompt-variable resolution for `story_text`).
        instance_step = await step_execution_repo.get_by_instance_and_key(
            parsed.instance_id, parsed.step_id
        )
        if instance_step is None:
            logger.error(
                f"StepExecution not found for step {parsed.step_id} "
                f"in instance {parsed.instance_id}"
            )
            return None
        job = instance_step

        # 4b. Guard: Skip if step is cancelled (cancel may have raced with result delivery)

        if instance_step.status == StepExecutionStatus.CANCELLED:
            # DEBUG, not INFO - same reasoning as the instance-cancelled
            # guard above. Workers keep publishing until their current
            # operation finishes; the guard fires dozens of times per
            # cancelled step and swamps the log at INFO level.
            logger.debug(
                f"Skipping result processing: step {parsed.step_id} is cancelled "
                f"(instance={parsed.instance_id})"
            )
            return None

        # 6. Guard: Skip if job is in terminal state (duplicate message)
        # Exception: iteration jobs can have multiple results for the same job
        if job.status in (
            StepExecutionStatus.COMPLETED,
            StepExecutionStatus.FAILED,
            StepExecutionStatus.CANCELLED,
        ):
            if not parsed.is_iteration_job:
                # DEBUG, not WARNING: duplicate publishes are routine.
                # Workers retry on transient 5xx / WS drops and replay the
                # last terminal status; by the time the replay arrives the
                # job is already terminal. Same reasoning as the cancelled
                # guards above - logging at WARNING drowns the log wall
                # during normal retry storms without signalling any bug.
                logger.debug(
                    f"Skipping result for already-terminal job {job.id} "
                    f"(status={job.status}) step={parsed.step_id} "
                    f"instance={parsed.instance_id}"
                )
                return None
            # Only track terminal results (COMPLETED/FAILED) for iteration aggregation.
            # Non-terminal statuses (PROCESSING, QUEUED) arrive with empty result_data
            # and must not be tracked - they would fill completed_indices prematurely
            # and trigger ALL_COMPLETE before actual results arrive.
            if not (parsed.is_completed or parsed.is_failed):
                logger.debug(
                    f"Ignoring non-terminal {parsed.status} for iteration job "
                    f"(step={parsed.step_id}, iteration={parsed.iteration_index}/"
                    f"{parsed.iteration_count}, group={parsed.iteration_group_id})"
                )
                return None
            # Iteration job with terminal job status - subsequent iteration result
            # Track iteration and return outcome for caller to handle resources
            return await self._handle_subsequent_iteration(
                parsed=parsed,
                instance=instance,
                instance_step=instance_step,
                job=job,
                instance_repo=instance_repo,
                step_execution_repo=step_execution_repo,
                resource_repo=resource_repo,
                iteration_execution_repo=iteration_execution_repo,
            )

        # 7. Start job if pending (transition PENDING -> RUNNING).
        # Skip for QUEUED publishes - the QUEUED handler transitions
        # PENDING → QUEUED via `step.queue()`, and the job and step
        # share one row, so a stale `start()` here would leave the
        # row at RUNNING and reject the subsequent `queue()`.
        if job.status == StepExecutionStatus.PENDING and not parsed.is_queued:
            job.start()
            await step_execution_repo.update(job)

        # 8. Update debugging data from worker
        if parsed.input_data:
            job.input_data = parsed.input_data
        if parsed.request_body:
            job.request_body = parsed.request_body

        # 9. Store iteration_requests on job for immediate UI visibility
        # This is set at enqueue time so UI can show request data before workers respond
        if parsed.iteration_requests:
            job.iteration_requests = parsed.iteration_requests
            logger.debug(
                f"Stored {len(parsed.iteration_requests)} iteration_requests on job {job.id}"
            )

        # 10. Handle status transitions using StepResultHandler
        if parsed.is_queued:
            transition = self.step_result_handler.handle_queued(
                job=job,
                instance=instance,
                instance_step=instance_step,
                step_id=parsed.step_id,
                input_data=parsed.input_data,
                request_body=parsed.request_body,
                prompt_variables=parsed.prompt_variables,
            )
            # QUEUED: Update repos and return None (caller handles commit + notify).
            # `job is instance_step` (single StepExecution row); one update writes both.
            await step_execution_repo.update(job)
            await instance_repo.update(instance)
            # Return outcome with skip flag for caller to handle commit/notify
            return ProcessingOutcome(
                action=NextAction(action=OrchestrationAction.COMPLETE),  # Placeholder
                instance=instance,
                job=job,
                step_id=parsed.step_id,
                result_data={"step_status": "queued", "input_data": parsed.input_data},
                skip_action_execution=True,  # Don't execute orchestrator action
            )

        if parsed.is_processing:
            transition = self.step_result_handler.handle_processing(
                job=job,
                instance=instance,
                instance_step=instance_step,
                step_id=parsed.step_id,
            )
            # PROCESSING: Update repos and return outcome with skip flag.
            # `job is instance_step` (single StepExecution row); one update writes both.
            await step_execution_repo.update(job)
            await instance_repo.update(instance)
            return ProcessingOutcome(
                action=NextAction(action=OrchestrationAction.COMPLETE),  # Placeholder
                instance=instance,
                job=job,
                step_id=parsed.step_id,
                result_data={"step_status": "processing"},
                skip_action_execution=True,
            )

        if parsed.is_failed:
            transition = self.step_result_handler.handle_failed(
                job=job,
                instance=instance,
                instance_step=instance_step,
                step_id=parsed.step_id,
                error=parsed.error,
                is_iteration_job=parsed.is_iteration_job,
            )
            if not transition.should_continue:
                return None  # Step was cancelled mid-flight
            # FAILED: Single update - `job is instance_step`.
            await step_execution_repo.update(job)
            instance.step_entities[parsed.step_id] = instance_step
            # For iteration jobs, the parent step's terminal status is
            # decided by _complete_iteration_step on the aggregate. A
            # single iteration's failure must not fail the parent here,
            # otherwise sibling iterations still in flight would be
            # abandoned and downstream steps would unwind prematurely.
            step_failed = not parsed.is_iteration_job
            error_message = transition.error_message
        else:
            # COMPLETED: Extract outputs first, then handle completion
            # Store result on job BEFORE extraction so OutputExtractor can read it.
            # job.complete() will set this again later, which is fine.
            job.result = parsed.result_data

            snapshot_steps = (instance.workflow_snapshot or {}).get("steps", {})
            step_config = snapshot_steps.get(parsed.step_id, {})
            logger.debug(
                f"OutputExtractor lookup: step_id='{parsed.step_id}', "
                f"snapshot_step_keys={list(snapshot_steps.keys())}, "
                f"step_config_found={bool(step_config)}, "
                f"has_outputs={'outputs' in step_config if step_config else False}"
            )
            try:
                await self.output_extractor.extract_outputs(
                    job, step_config, provider_service_repo
                )
                logger.debug(
                    f"OutputExtractor result for step {parsed.step_id}: "
                    f"extracted_outputs={bool(job.extracted_outputs)}, "
                    f"keys={list(job.extracted_outputs.keys()) if isinstance(job.extracted_outputs, dict) else 'N/A'}"
                )
            except Exception as extract_err:
                logger.error(
                    f"OutputExtractor CRASHED for step {parsed.step_id}: "
                    f"{type(extract_err).__name__}: {extract_err}",
                    exc_info=True,
                )

            transition = self.step_result_handler.handle_completed(
                job=job,
                instance=instance,
                instance_step=instance_step,
                step_id=parsed.step_id,
                result_data=parsed.result_data,
                is_iteration_job=parsed.is_iteration_job,
            )
            if not transition.should_continue:
                return None  # Step was cancelled mid-flight
            # COMPLETED: Single update - `job is instance_step`. Writes
            # `status`, `result`, `extracted_outputs`, and `output_data`
            # in one row UPDATE so no column gets clobbered by a sibling write.
            await step_execution_repo.update(job)
            instance.step_entities[parsed.step_id] = instance_step
            step_failed = False
            error_message = None

        # Iteration jobs skip the instance-level update to avoid clobbering sibling iteration writes.
        if not parsed.is_iteration_job:
            await instance_repo.update(instance)

        # 11. Handle iteration jobs - track and aggregate
        if parsed.is_iteration_job:
            return await self._handle_first_iteration(
                parsed=parsed,
                instance=instance,
                instance_step=instance_step,
                job=job,
                step_failed=step_failed,
                error_message=error_message,
                instance_repo=instance_repo,
                step_execution_repo=step_execution_repo,
                resource_repo=resource_repo,
                iteration_execution_repo=iteration_execution_repo,
            )

        # 12. Store result in instance output_data (non-iteration only)
        if parsed.result_data and not step_failed:
            if "steps" not in instance.output_data:
                instance.output_data["steps"] = {}
            instance.output_data["steps"][parsed.step_id] = parsed.result_data
            await instance_repo.update(instance)

        # 12b. Handle step-level bookkeeping for re-execution operations.
        # NOTE: active_operation is NOT cleared here. It's cleared in
        # result_processor.py step 15, AFTER the action handler runs, so
        # that the handler transitions from PROCESSING (not from the
        # restored original_status, which could be a WAITING_* state the
        # handler rejects). Staged-resource deletion also moves to step 15
        # so it's atomic with the tracking clear and the handler's commit.
        # See lifecycle.md §6.10 (V1 reorder).
        active_op = get_active_op_for_step(instance, parsed.step_id)
        if active_op is not None:
            op_type = active_op.get("type", "")
            is_regen = op_type.startswith("regenerate_")

            if step_failed and is_regen:
                # Regen failed. Preserve originals and restore step to
                # COMPLETED so downstream workflow stays consistent.
                if instance_step and instance_step.status == StepExecutionStatus.FAILED:
                    try:
                        instance_step.restart()  # FAILED -> RUNNING
                        instance_step.complete(
                            output_data=instance_step.output_data or {}
                        )
                        instance_step.error_message = None
                        await step_execution_repo.update(instance_step)
                    except Exception as e:
                        # exc_info=True so the next reproduction surfaces
                        # the actual traceback. Mirrors the iteration-path
                        # restore swallow at lines 919, 948.
                        logger.warning(
                            f"Failed to restore step {parsed.step_id} after failed regen: {e}",
                            exc_info=True,
                        )
                if parsed.step_id in instance.failed_step_ids:
                    instance.failed_step_ids.remove(parsed.step_id)
                if parsed.step_id not in instance.completed_step_ids:
                    instance.completed_step_ids.append(parsed.step_id)
                await instance_repo.update(instance)
                logger.info(
                    f"Regen failed for step {parsed.step_id}; originals preserved "
                    f"(active_operation kept for step-15 cleanup)"
                )
                # Suppress orchestrator FAIL for regen-only failures so the
                # workflow doesn't unwind on a preserved-state regeneration.
                step_failed = False
                error_message = None

        # 13. Determine next action using orchestrator
        # (approval_step lookup will be handled by caller for now)
        action = self.orchestrator.determine_next_action(
            instance=instance,
            completed_step_id=parsed.step_id,
            step_failed=step_failed,
            error_message=error_message,
            approval_step_id=None,  # Caller handles async lookup
            is_debug_mode=instance.is_debug_mode,
        )

        logger.info(
            f"Step {'failed' if step_failed else 'completed'}: step={parsed.step_id} next={action.action.value}",
            extra={
                "instance_id": str(parsed.instance_id),
                "step_id": parsed.step_id,
            },
        )

        return ProcessingOutcome(
            action=action,
            instance=instance,
            job=job,
            step_id=parsed.step_id,
            result_data=parsed.result_data,
            error=error_message,
            skip_action_execution=False,
        )

    async def _handle_subsequent_iteration(
        self,
        parsed: StepResultPayload,
        instance: Instance,
        instance_step: Any,
        job: StepExecution,
        instance_repo: Any,
        step_execution_repo: Any,
        resource_repo: Optional[Any] = None,
        iteration_execution_repo: Optional[Any] = None,
    ) -> Optional[ProcessingOutcome]:
        """
        Handle subsequent iteration results (job already in terminal state).

        When the first iteration job completes, it updates the job to COMPLETED.
        Subsequent iteration results for the same step still need to be tracked
        for aggregation purposes. This method handles that case.

        Returns:
            ProcessingOutcome with iteration tracking info, or None if still in progress
        """
        # Operation bypass: any active operation on this step means only 1 result
        # is expected. Bypass N-iteration aggregation which would expect
        # iteration_count results and leave the step stuck at RUNNING.
        if get_active_op_for_step(instance, parsed.step_id) is not None:
            return await self._complete_operation_iteration(
                parsed,
                instance,
                instance_step,
                job,
                instance_repo,
                step_execution_repo,
                resource_repo=resource_repo,
            )

        step_failed = parsed.is_failed

        # Row-based tracking: IterationExecution table holds per-iteration
        # state. Row-level writes don't collide, so no FOR UPDATE on the
        # parent Instance is required.
        tracking = await self.iteration_handler.track_iteration_via_rows(
            iteration_execution_repo=iteration_execution_repo,
            step_execution_repo=step_execution_repo,
            instance_id=instance.id,
            step_key=parsed.step_id,
            iteration_index=parsed.iteration_index or 0,
            iteration_count=parsed.iteration_count or 0,
            iteration_group_id=parsed.iteration_group_id,
            step_failed=step_failed,
            result_data=parsed.result_data,
            error=parsed.error,
        )

        # Determine status from the atomically-updated tracking
        iteration_result = IterationHandler.status_from_tracking(
            tracking, parsed.step_id
        )

        if iteration_result.status == IterationStatus.IN_PROGRESS:
            partial = iteration_result.aggregated_result or {}
            # Filter partial aggregation to declared outputs only
            snapshot_steps = (instance.workflow_snapshot or {}).get("steps", {})
            step_outputs_config = snapshot_steps.get(parsed.step_id, {}).get("outputs")
            if step_outputs_config:
                partial = self.output_extractor.extract_from_data(
                    partial, step_outputs_config
                )
            job.extracted_outputs = partial
            await step_execution_repo.update(job)

            return ProcessingOutcome(
                action=NextAction(action=OrchestrationAction.COMPLETE),
                instance=instance,
                job=job,
                step_id=parsed.step_id,
                result_data={
                    "iteration_progress": iteration_result.progress,
                    "downloaded_files": parsed.result_data.get("downloaded_files", []),
                },
                skip_action_execution=True,
            )

        # All iterations complete - determine final outcome
        return await self._complete_iteration_step(
            parsed=parsed,
            instance=instance,
            instance_step=instance_step,
            job=job,
            iteration_result=iteration_result,
            instance_repo=instance_repo,
            step_execution_repo=step_execution_repo,
        )

    async def _handle_first_iteration(
        self,
        parsed: StepResultPayload,
        instance: Instance,
        instance_step: Any,
        job: StepExecution,
        step_failed: bool,
        error_message: Optional[str],
        instance_repo: Any,
        step_execution_repo: Any,
        resource_repo: Optional[Any] = None,
        iteration_execution_repo: Optional[Any] = None,
    ) -> Optional[ProcessingOutcome]:
        """
        Handle first iteration job result (job transitions to COMPLETED/FAILED).

        This is called when the first iteration job completes. It tracks the
        iteration and determines if we need to wait for more or proceed.

        Returns:
            ProcessingOutcome with iteration tracking info, or None if still in progress
        """
        # Operation bypass: any active operation on this step means only 1 result
        # is expected. Bypass N-iteration aggregation.
        if get_active_op_for_step(instance, parsed.step_id) is not None:
            return await self._complete_operation_iteration(
                parsed,
                instance,
                instance_step,
                job,
                instance_repo,
                step_execution_repo,
                resource_repo=resource_repo,
            )

        # Row-based tracking: IterationExecution table holds per-iteration
        # state. Row-level writes don't collide, so no FOR UPDATE on the
        # parent Instance is required.
        try:
            tracking = await self.iteration_handler.track_iteration_via_rows(
                iteration_execution_repo=iteration_execution_repo,
                step_execution_repo=step_execution_repo,
                instance_id=instance.id,
                step_key=parsed.step_id,
                iteration_index=parsed.iteration_index or 0,
                iteration_count=parsed.iteration_count or 0,
                iteration_group_id=parsed.iteration_group_id,
                step_failed=step_failed,
                result_data=parsed.result_data,
                error=error_message,
            )
        except Exception as agg_err:
            logger.error(
                f"IterationExecution row tracking failed for step {parsed.step_id} "
                f"iteration {parsed.iteration_index}: {agg_err}",
                exc_info=True,
            )
            # Fail the step explicitly instead of leaving it stuck at RUNNING.
            # `instance_step` is guaranteed non-None at this point
            # (early return at step 4 if the row was missing).
            instance_step.fail(f"Iteration tracking error: {agg_err}")
            await step_execution_repo.update(instance_step)
            await instance_repo.update(instance)

            return ProcessingOutcome(
                action=NextAction(
                    action=OrchestrationAction.FAIL,
                    error_message=f"Iteration tracking error: {agg_err}",
                ),
                instance=instance,
                job=job,
                step_id=parsed.step_id,
                result_data=parsed.result_data,
                error=f"Iteration tracking error: {agg_err}",
            )

        # Determine status from the atomically-updated tracking
        iteration_result = IterationHandler.status_from_tracking(
            tracking, parsed.step_id
        )

        if iteration_result.status == IterationStatus.IN_PROGRESS:
            partial = iteration_result.aggregated_result or {}
            # Filter partial aggregation to declared outputs only
            snapshot_steps = (instance.workflow_snapshot or {}).get("steps", {})
            step_outputs_config = snapshot_steps.get(parsed.step_id, {}).get("outputs")
            if step_outputs_config:
                partial = self.output_extractor.extract_from_data(
                    partial, step_outputs_config
                )
            job.extracted_outputs = partial
            await step_execution_repo.update(job)

            return ProcessingOutcome(
                action=NextAction(action=OrchestrationAction.COMPLETE),
                instance=instance,
                job=job,
                step_id=parsed.step_id,
                result_data={
                    "iteration_progress": iteration_result.progress,
                    "downloaded_files": parsed.result_data.get("downloaded_files", []),
                },
                skip_action_execution=True,
            )

        # All iterations complete - determine final outcome
        return await self._complete_iteration_step(
            parsed=parsed,
            instance=instance,
            instance_step=instance_step,
            job=job,
            iteration_result=iteration_result,
            instance_repo=instance_repo,
            step_execution_repo=step_execution_repo,
        )

    async def _complete_operation_iteration(
        self,
        parsed: StepResultPayload,
        instance: Instance,
        instance_step: Any,
        job: StepExecution,
        instance_repo: Any,
        step_execution_repo: Any,
        resource_repo: Optional[Any] = None,
    ) -> ProcessingOutcome:
        """
        Handle a single iteration result for an active operation.

        Bypasses N-iteration aggregation because only 1 result is expected
        (the operation re-enqueued a single iteration, not the full batch).

        Regeneration operations skip the orchestrator (step was already
        complete, downstream already ran). Rerun/retry operations run the
        orchestrator so pending downstream steps get picked up naturally.

        On regen failure, preserves original resources (staged for deletion
        but never deleted) and restores the step to COMPLETED so downstream
        workflow state stays consistent.
        """
        step_id = parsed.step_id
        # Caller guarantees the step carries an active op.
        active_op = instance.step_entities[step_id].active_operation
        assert active_op is not None  # narrowing for pyright
        op_type = active_op.get("type", "unknown")
        is_regeneration = op_type.startswith("regenerate_")
        is_failed = parsed.is_failed
        staged_ids: List[str] = list(
            active_op.get("staged_deletion_resource_ids") or []
        )

        logger.info(
            f"Completing operation {op_type} iteration for step {step_id} "
            f"on instance {instance.id} (failed={is_failed})",
            extra={
                "instance_id": str(instance.id),
                "step_id": step_id,
                "operation": op_type,
                "failed": is_failed,
                "staged_resource_count": len(staged_ids),
            },
        )

        if is_failed and is_regeneration:
            # Regen failed. Staged resources survive (deferred deletion).
            # Restore step to COMPLETED so downstream stays consistent with
            # the unchanged original outputs.
            if instance_step and instance_step.status != StepExecutionStatus.COMPLETED:
                try:
                    if instance_step.status == StepExecutionStatus.FAILED:
                        instance_step.restart()
                    if instance_step.status == StepExecutionStatus.PENDING:
                        instance_step.start()
                    instance_step.complete(output_data=instance_step.output_data or {})
                    instance_step.error_message = None
                    await step_execution_repo.update(instance_step)
                except Exception as e:
                    # exc_info=True so the next reproduction surfaces the
                    # actual traceback. Without it, the f-string repr of `e`
                    # can render empty for some exception classes and hides
                    # the underlying cause. See lifecycle.md §6 - auto-commit
                    # drift between repo writes is a candidate trigger.
                    logger.warning(
                        f"Failed to restore step {step_id} after failed regen: {e}",
                        exc_info=True,
                    )

            if step_id in instance.failed_step_ids:
                instance.failed_step_ids.remove(step_id)
            if step_id not in instance.completed_step_ids:
                instance.completed_step_ids.append(step_id)

            logger.info(
                f"Regen failed for step {step_id}; preserved "
                f"{len(staged_ids)} original resources"
            )
        else:
            # Success (or rerun/retry). Complete step with new result_data.
            if instance_step and instance_step.status != StepExecutionStatus.COMPLETED:
                try:
                    if instance_step.status == StepExecutionStatus.PENDING:
                        instance_step.start()
                    instance_step.complete(output_data=parsed.result_data)
                    await step_execution_repo.update(instance_step)
                except Exception as e:
                    # exc_info=True so the next reproduction surfaces the
                    # actual traceback. Production "stuck RUNNING after
                    # regen" symptom landed here without a logged cause -
                    # the bare `{e}` repr hid whatever raised. See
                    # lifecycle.md §6 - auto-commit drift between repo
                    # writes is a candidate trigger.
                    logger.warning(
                        f"Failed to restore step {step_id} to COMPLETED: {e}",
                        exc_info=True,
                    )

            # Delete staged resources now that new ones have landed
            if is_regeneration and staged_ids and resource_repo is not None:
                await self._delete_staged_resources(
                    staged_ids,
                    resource_repo,
                    instance_id=instance.id,
                    step_id=step_id,
                )

        # For rerun/retry, update tracking lists so orchestrator sees the step
        # as completed. Regeneration steps are already in completed_step_ids.
        if not is_regeneration:
            instance.handle_step_completed(step_id, job)

            # Store result in instance output_data for downstream input resolution
            if parsed.result_data:
                if "steps" not in instance.output_data:
                    instance.output_data["steps"] = {}
                instance.output_data["steps"][step_id] = parsed.result_data

        # Regeneration iteration skips the action executor, so clear the
        # operation tracking here to keep result_processor.py's step 15
        # guard simple (runs only for action-executor-participating paths).
        # Rerun/retry iteration runs the action executor and is cleared at
        # step 15. See lifecycle.md §6.10.
        # Tracking-clear is step-scoped. The regen path always operates
        # on a known step (parsed.step_id from the worker payload) so
        # the step_entities lookup is unconditional - if the step is
        # missing, that's a real bug to surface, not silently skip.
        if is_regeneration:
            instance.step_entities[step_id].complete_operation_tracking()
            await instance_repo.update(instance)
            return ProcessingOutcome(
                action=NextAction(action=OrchestrationAction.COMPLETE),
                instance=instance,
                job=job,
                step_id=step_id,
                result_data=parsed.result_data,
                skip_action_execution=True,
            )

        # Rerun/retry: leave active_operation set so result_processor.py
        # step 15 clears it AFTER the action handler runs.
        await instance_repo.update(instance)

        action = self.orchestrator.determine_next_action(
            instance=instance,
            completed_step_id=step_id,
            step_failed=parsed.is_failed,
            error_message=parsed.error if parsed.is_failed else None,
            approval_step_id=None,
            is_debug_mode=instance.is_debug_mode,
        )

        return ProcessingOutcome(
            action=action,
            instance=instance,
            job=job,
            step_id=step_id,
            result_data=parsed.result_data,
            skip_action_execution=False,
        )

    async def _delete_staged_resources(
        self,
        staged_ids: List[str],
        resource_repo: Any,
        instance_id: UUID,
        step_id: str,
    ) -> None:
        """Delete resources that were staged by a regeneration operation."""
        if not staged_ids:
            return
        from uuid import UUID as _UUID
        from app.infrastructure.storage.workspace import cleanup_resource_files

        deleted = 0
        for rid_str in staged_ids:
            try:
                resource = await resource_repo.get_by_id(_UUID(rid_str))
                if resource is None:
                    continue  # Already gone; no-op
                virtual_path = resource.virtual_path
                thumbnail_path = (
                    resource.metadata.get("thumbnail_path")
                    if resource.metadata
                    else None
                )
                await resource_repo.delete(resource.id)
                cleanup_resource_files(
                    virtual_path=virtual_path,
                    thumbnail_path=thumbnail_path,
                )
                deleted += 1
            except Exception as e:
                logger.warning(
                    f"Failed to delete staged resource {rid_str}: {e}",
                    extra={
                        "instance_id": str(instance_id),
                        "step_id": step_id,
                    },
                )
        logger.info(
            f"Deleted {deleted}/{len(staged_ids)} staged resources after "
            f"successful regen for step {step_id}",
            extra={"instance_id": str(instance_id), "step_id": step_id},
        )

    async def _complete_iteration_step(
        self,
        parsed: StepResultPayload,
        instance: Instance,
        instance_step: Any,
        job: StepExecution,
        iteration_result: IterationResult,
        instance_repo: Any,
        step_execution_repo: Any,
    ) -> ProcessingOutcome:
        """
        Complete an iteration step after all iteration jobs are done.

        This aggregates results and determines the next action.

        Returns:
            ProcessingOutcome with aggregated results and next action
        """

        logger.debug(
            f"All {parsed.iteration_count} iterations completed for step {parsed.step_id} "
            f"(status={iteration_result.status.value})",
            extra={
                "instance_id": str(parsed.instance_id),
                "step_id": parsed.step_id,
                "iteration_count": parsed.iteration_count,
            },
        )

        # Determine if step failed
        if iteration_result.status == IterationStatus.HAS_FAILURES:
            step_failed = True
            error_message = iteration_result.error
            result_data = parsed.result_data
        else:
            step_failed = False
            error_message = None
            result_data = iteration_result.aggregated_result or {}

            # Apply output extraction to filter aggregated result to declared outputs only.
            # Without this, downstream steps receive all worker metadata (poll_attempts,
            # elapsed_seconds, etc.) instead of just the declared outputs.
            snapshot_steps = (instance.workflow_snapshot or {}).get("steps", {})
            step_outputs_config = snapshot_steps.get(parsed.step_id, {}).get("outputs")
            if step_outputs_config:
                result_data = self.output_extractor.extract_from_data(
                    result_data, step_outputs_config
                )

            # Update job with aggregated extracted_outputs
            job.extracted_outputs = result_data
            await step_execution_repo.update(job)

        # Complete the instance step entity (separate table, no race)
        if instance_step:
            if instance_step.status == StepExecutionStatus.PENDING:
                instance_step.start()
            if (
                not step_failed
                and instance_step.status != StepExecutionStatus.COMPLETED
            ):
                instance_step.complete(output_data=result_data)
            elif step_failed:
                instance_step.fail(error_message or "Iteration failed")
            await step_execution_repo.update(instance_step)

        # Atomically mark step completed on the instance row.
        # Uses FOR UPDATE to prevent concurrent step completions from
        # clobbering each other's step_status/current_step_ids changes.
        # No cleanup_tracking_key needed - iteration state lives in the
        # IterationExecution table, not in Instance.output_data.
        if not step_failed:
            await instance_repo.atomic_complete_step(
                instance_id=instance.id,
                step_id=parsed.step_id,
                step_output=result_data,
            )

        # Re-read instance from DB so orchestrator sees the atomic changes
        instance = await instance_repo.get_by_id(instance.id)

        # Determine next action using orchestrator
        action = self.orchestrator.determine_next_action(
            instance=instance,
            completed_step_id=parsed.step_id,
            step_failed=step_failed,
            error_message=error_message,
            approval_step_id=None,  # Caller handles async lookup
            is_debug_mode=instance.is_debug_mode,
        )

        return ProcessingOutcome(
            action=action,
            instance=instance,
            job=job,
            step_id=parsed.step_id,
            result_data=result_data,
            error=error_message,
            skip_action_execution=False,
        )
