# api/app/application/services/result_processing/step_result_handler.py

"""Handles status transitions for step results: QUEUED, PROCESSING, COMPLETED, FAILED."""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional

from app.domain.instance.models import Instance
from app.domain.instance_step.models import StepExecutionStatus
from app.domain.instance_step.step_execution import StepExecution
from app.domain.common.exceptions import InvalidStateTransition

logger = logging.getLogger(__name__)


class TransitionType(Enum):
    """Type of status transition."""

    QUEUED = "queued"  # Job queued, waiting for worker
    PROCESSING = "processing"  # Worker started
    COMPLETED = "completed"  # Step succeeded
    FAILED = "failed"  # Step failed


@dataclass
class TransitionResult:
    """Result of a status transition.

    should_continue=False means the caller should return early without further processing.
    needs_commit=True means the caller must commit before publishing events.
    """

    transition_type: TransitionType
    should_continue: bool = True
    needs_commit: bool = False
    step_failed: bool = False
    error_message: Optional[str] = None


class StepResultHandler:
    """Encapsulates state transition logic for jobs and instance steps based on worker-reported status."""

    def handle_queued(
        self,
        job: StepExecution,
        instance: Instance,
        instance_step: Optional[StepExecution],
        step_id: str,
        input_data: Dict[str, Any],
        request_body: Optional[Dict[str, Any]],
        prompt_variables: Optional[Dict[str, str]] = None,
    ) -> TransitionResult:
        """Handle QUEUED status - job is waiting for worker pickup.

        Persists input, request body, and prompt variables for debugging and downstream
        resolution. Prompt variables are written to execution_data["_prompt_variables"]
        - authoritative source for the API, not the worker.
        Returns should_continue=False.
        """
        logger.debug(f"Step {step_id} is QUEUED (input/request persisted)")

        # Persist debugging data
        if input_data:
            job.input_data = input_data
        if request_body:
            job.request_body = request_body

        # Persist prompt variables (API-authoritative, not from worker)
        if prompt_variables:
            job.execution_data = job.execution_data or {}
            job.execution_data["_prompt_variables"] = prompt_variables

        # Update step status via entity
        if instance_step:
            instance_step.queue()
        else:
            logger.error(
                f"StepExecution not found for {step_id} on instance "
                f"{instance.id} - cannot update step status without entity"
            )

        return TransitionResult(
            transition_type=TransitionType.QUEUED,
            should_continue=False,  # Don't proceed to completion logic
            needs_commit=True,  # Commit before publishing WebSocket
        )

    def handle_processing(
        self,
        job: StepExecution,
        instance: Instance,
        instance_step: Optional[StepExecution],
        step_id: str,
    ) -> TransitionResult:
        """Handle PROCESSING status - worker started executing. Returns should_continue=False."""
        logger.debug(f"Step {step_id} is now PROCESSING (running)")

        # Update instance step via entity (source of truth).
        # PENDING and QUEUED both transition to RUNNING via start():
        # enqueue_step calls step.queue() so the row is QUEUED by the
        # time the worker's PROCESSING publish arrives.
        if instance_step:
            if instance_step.status in (
                StepExecutionStatus.PENDING,
                StepExecutionStatus.QUEUED,
            ):
                instance_step.start()
            elif instance_step.status in (
                StepExecutionStatus.COMPLETED,
                StepExecutionStatus.FAILED,
            ):
                # Regeneration: step was already done, restart it
                instance_step.restart()

        instance.handle_step_started(step_id, job)

        return TransitionResult(
            transition_type=TransitionType.PROCESSING,
            should_continue=False,  # Don't proceed to completion logic
            needs_commit=False,  # Caller handles commit
        )

    def handle_failed(
        self,
        job: StepExecution,
        instance: Instance,
        instance_step: Optional[StepExecution],
        step_id: str,
        error: Optional[str],
        is_iteration_job: bool = False,
    ) -> TransitionResult:
        """Handle FAILED status - step execution failed.

        For iteration jobs, a single failed iteration does NOT fail the parent step
        immediately; the parent's terminal status is decided once all iterations are
        terminal, so step_failed=False is returned for iteration jobs.
        """
        error_msg = error or "Step execution failed"
        logger.debug(f"Step {step_id} FAILED: {error_msg}")

        # Guard: if step was cancelled mid-flight, skip transition
        if instance_step and instance_step.status == StepExecutionStatus.CANCELLED:
            logger.info(f"Step {step_id} cancelled, skipping fail transition")
            return TransitionResult(
                transition_type=TransitionType.FAILED,
                should_continue=False,
            )

        # Iteration jobs: parent-step status is governed by
        # _complete_iteration_step on the aggregate. step_failed=False here
        # so the orchestrator does not unwind on a single iteration failure.
        if is_iteration_job:
            return TransitionResult(
                transition_type=TransitionType.FAILED,
                should_continue=True,
                step_failed=False,
                error_message=error_msg,
            )

        job.fail(error_message=error_msg)

        # Update instance step via entity (source of truth)
        if instance_step:
            try:
                instance_step.fail(error_msg)
            except (InvalidStateTransition, ValueError) as e:
                # Step was cancelled concurrently - skip
                logger.warning(
                    f"Step {step_id} fail transition failed (likely concurrent cancel): {e}"
                )
                return TransitionResult(
                    transition_type=TransitionType.FAILED,
                    should_continue=False,
                )

        instance.handle_step_failed(step_id, job)

        return TransitionResult(
            transition_type=TransitionType.FAILED,
            should_continue=True,  # Continue to orchestrator for FAIL action
            step_failed=True,
            error_message=error_msg,
        )

    def handle_completed(
        self,
        job: StepExecution,
        instance: Instance,
        instance_step: Optional[StepExecution],
        step_id: str,
        result_data: Dict[str, Any],
        is_iteration_job: bool = False,
    ) -> TransitionResult:
        """Handle COMPLETED status - step finished successfully.

        Output extraction must be done before calling this method; job.extracted_outputs
        must already be populated.

        For iteration jobs, instance/step completion is skipped - the parent step
        transitions only when the iteration aggregate decides it is terminal.
        """
        logger.debug(f"Step {step_id} COMPLETED")

        # Guard: if step was cancelled mid-flight, skip transition
        if instance_step and instance_step.status == StepExecutionStatus.CANCELLED:
            logger.info(f"Step {step_id} cancelled, skipping completion transition")
            return TransitionResult(
                transition_type=TransitionType.COMPLETED,
                should_continue=False,
            )

        # Iteration jobs: do NOT touch the parent step's status here.
        # `job is instance_step`; calling `job.complete()` would flip
        # the parent to COMPLETED on the FIRST iteration and let
        # downstream steps proceed while later iterations are still in
        # flight. Per-iteration state lives in iteration_executions; the
        # parent transitions to COMPLETED only when
        # `_complete_iteration_step` decides based on the aggregate.
        if is_iteration_job:
            return TransitionResult(
                transition_type=TransitionType.COMPLETED,
                should_continue=True,
            )

        # Non-iteration job: complete the job (= the step row post-collapse)
        # and the instance.
        job.complete(result=result_data)
        instance.handle_step_completed(step_id, job)

        # Update instance step and store extracted outputs
        if instance_step:
            pre_transition_status = instance_step.status
            try:
                # Handle various starting states
                if instance_step.status in (
                    StepExecutionStatus.PENDING,
                    StepExecutionStatus.WAITING_FOR_MANUAL_TRIGGER,
                ):
                    instance_step.start()
                elif instance_step.status in (
                    StepExecutionStatus.COMPLETED,
                    StepExecutionStatus.FAILED,
                ):
                    # Regeneration: step was already done, restart it
                    instance_step.restart()

                # Store extracted outputs in instance_step
                instance_step.complete(output_data=job.extracted_outputs)
            except (InvalidStateTransition, ValueError) as e:
                # Invariant break: a completed job should always be able to
                # transition its step to COMPLETED. Concurrent cancel is the
                # only legitimate cause, but any other source leaves the step
                # stuck at `pre_transition_status` with no recovery path - that
                # is exactly the orphan state we are trying to prevent, so log
                # LOUDLY with full context for diagnosis.
                logger.error(
                    f"Step {step_id} transition to COMPLETED failed: {e}. "
                    f"Step is stuck at status={pre_transition_status.value}. "
                    f"Likely cause is a concurrent cancel, but investigate if "
                    f"the step has no active job.",
                    extra={
                        "instance_id": str(instance.id),
                        "step_id": step_id,
                        "job_id": str(job.id),
                        "pre_transition_status": pre_transition_status.value,
                        "attempted_status": StepExecutionStatus.COMPLETED.value,
                        "error": str(e),
                    },
                )
                return TransitionResult(
                    transition_type=TransitionType.COMPLETED,
                    should_continue=False,
                )

        return TransitionResult(
            transition_type=TransitionType.COMPLETED,
            should_continue=True,
        )
