# api/app/application/services/result_processing/iteration_handler.py

"""
Iteration Handler Service

Handles tracking and aggregation of iteration jobs for workflow steps.
When a step has iteration_count > 1, multiple jobs are created. This handler
tracks their progress (as per-iteration rows in the IterationExecution table)
and aggregates results when all complete.

Key responsibilities:
- Track progress across multiple iteration jobs via row-based persistence
- Aggregate results when all iterations complete
- Determine if step should proceed, fail, or wait for more results

Iteration progress is persisted as one `IterationExecution` row per
(instance_step, iteration_index, iteration_group_id). Row-level writes on
a dedicated table don't collide, so no FOR UPDATE lock on the parent
Instance is required.

`status_from_tracking` and `aggregate_results` remain pure
computations over a "tracking-shaped" dict. Callers materialize this
shape from the sibling IterationExecution rows.
"""

import logging
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class IterationStatus(Enum):
    """Status of iteration tracking for a step."""

    IN_PROGRESS = "in_progress"  # Still waiting for more iteration jobs
    ALL_COMPLETE = "all_complete"  # All iterations completed successfully
    HAS_FAILURES = "has_failures"  # All done but some failed


@dataclass
class IterationResult:
    """Result of tracking an iteration job."""

    status: IterationStatus
    aggregated_result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    progress: Optional[Dict[str, int]] = None  # completed, failed, total


class IterationHandler:
    """
    Handles iteration job tracking and aggregation.

    This service tracks progress across multiple iteration jobs for a step
    (backed by per-iteration rows in the IterationExecution table) and
    aggregates their results when all are complete.
    """

    async def track_iteration_via_rows(
        self,
        *,
        iteration_execution_repo,  # IterationExecutionRepository
        step_execution_repo,  # StepExecutionRepository
        instance_id: uuid.UUID,
        step_key: str,
        iteration_index: int,
        iteration_count: int,
        iteration_group_id: Optional[str],
        step_failed: bool,
        result_data: Dict[str, Any],
        error: Optional[str],
    ) -> Dict[str, Any]:
        """Transition the IterationExecution row to terminal and return a tracking-shaped dict.

        IterationExecution rows are independent - no FOR UPDATE lock on the parent Instance.
        step_key is the workflow step key string (payload["step_id"]), not instance_step.id.
        """
        logger.debug(
            f"Iteration row track: {iteration_index + 1}/{iteration_count} "
            f"step_key={step_key} status={'FAILED' if step_failed else 'COMPLETED'}, "
            f"group={iteration_group_id}"
        )

        # 1. Resolve the parent StepExecution UUID from the step_key string.
        #    Payload carries step_id as the workflow step_key, not
        #    instance_step.id. The row lookup keys on the UUID.
        instance_step = await step_execution_repo.get_by_instance_and_key(
            instance_id, step_key
        )
        if instance_step is None:
            # The result consumer already fetched instance_step earlier in
            # the pipeline; a miss here means something has gone wrong in
            # the caller chain.
            raise RuntimeError(
                f"StepExecution not found for step_key={step_key!r} "
                f"on instance={instance_id} - cannot resolve IterationExecution row"
            )

        # 2. Parse iteration_group_id: non-empty string → UUID, else None.
        #    Empty slots are legal - iteration_group_id column is nullable UUID.
        group_uuid: Optional[uuid.UUID] = None
        if iteration_group_id:
            try:
                group_uuid = uuid.UUID(iteration_group_id)
            except (ValueError, AttributeError, TypeError):
                # Legacy / malformed group IDs - fall through to None.
                # The IterationExecution column is nullable; site 9
                # persists None when the payload group is missing.
                group_uuid = None

        # 3. Resolve the iteration row.
        iteration = await iteration_execution_repo.get_by_step_and_index(
            instance_step.id, iteration_index, group_uuid
        )

        # 3a. Missing-row safety net. Enqueue creates N PENDING rows. A
        #     miss here signals an un-migrated enqueue path (or a row
        #     that was deleted mid-flight). Create a fresh terminal row
        #     so the step can still progress - and log a warning because
        #     upstream is in a bad state.
        if iteration is None:
            from app.domain.instance.iteration_execution import (
                IterationExecution,
                IterationExecutionStatus,
            )

            logger.warning(
                f"IterationExecution row missing at result time: "
                f"step_id={instance_step.id} iteration_index={iteration_index} "
                f"group_id={group_uuid}. Synthesizing terminal row - "
                f"upstream enqueue path likely did not create per-iteration rows."
            )
            iteration = IterationExecution.create(
                instance_id=instance_id,
                step_id=instance_step.id,
                iteration_index=iteration_index,
                iteration_group_id=group_uuid,
                parameters={},
                status=IterationExecutionStatus.PENDING,
            )
            # Transition straight to RUNNING then terminal - matches the
            # normal path below, letting the domain object enforce its
            # forward-lifecycle checks.
            iteration.start()
            if step_failed:
                iteration.fail(error or "iteration failed")
            else:
                iteration.complete(result_data)
            await iteration_execution_repo.create(iteration, commit=False)
        else:
            # 4. Normal path: transition PENDING/QUEUED → RUNNING if not
            #    already there, then terminal.
            from app.domain.instance.iteration_execution import (
                IterationExecutionStatus,
            )

            if iteration.status in (
                IterationExecutionStatus.PENDING,
                IterationExecutionStatus.QUEUED,
            ):
                iteration.start()

            # 5. Apply terminal transition.
            if step_failed:
                iteration.fail(error or "iteration failed")
            else:
                iteration.complete(result_data)

            # 6. Persist (caller manages the outer transaction).
            await iteration_execution_repo.update(iteration, commit=False)

        # 7. Materialize a tracking-shaped dict from sibling rows.
        from app.domain.instance.iteration_execution import (
            IterationExecutionStatus,
        )

        all_iters = await iteration_execution_repo.list_by_step_id(instance_step.id)
        # Filter by group if one was provided. list_by_step_id doesn't
        # take group_id; filter in Python. (Group is typically single
        # per step, so the list is short.)
        if group_uuid is not None:
            all_iters = [i for i in all_iters if i.iteration_group_id == group_uuid]

        completed_indices: List[int] = []
        failed_indices: List[int] = []
        results: Dict[str, Any] = {}
        for i in all_iters:
            if i.status == IterationExecutionStatus.COMPLETED:
                completed_indices.append(i.iteration_index)
                results[str(i.iteration_index)] = {
                    "status": "COMPLETED",
                    "result": i.result or {},
                }
            elif i.status == IterationExecutionStatus.FAILED:
                failed_indices.append(i.iteration_index)
                results[str(i.iteration_index)] = {
                    "status": "FAILED",
                    "error": i.error,
                }
            # PENDING / QUEUED / RUNNING / CANCELLED - not included
            # in the aggregation view (not yet terminal).

        tracking: Dict[str, Any] = {
            "completed_indices": completed_indices,
            "failed_indices": failed_indices,
            "results": results,
            "iteration_count": iteration_count,
        }

        logger.debug(
            f"Iteration row progress: completed={len(completed_indices)}, "
            f"failed={len(failed_indices)}, total={iteration_count}"
        )

        return tracking

    @staticmethod
    def status_from_tracking(
        tracking: Dict[str, Any], step_id: str
    ) -> "IterationResult":
        """
        Determine iteration status from a tracking-shaped dict returned by
        `track_iteration_via_rows`. Pure computation - no DB access.
        """
        iteration_count: int = tracking["iteration_count"]
        total_done = len(tracking["completed_indices"]) + len(
            tracking["failed_indices"]
        )
        all_done = total_done >= iteration_count

        progress = {
            "completed": len(tracking["completed_indices"]),
            "failed": len(tracking["failed_indices"]),
            "total": iteration_count,
        }

        if not all_done:
            partial_result = IterationHandler.aggregate_results(tracking, step_id)
            return IterationResult(
                status=IterationStatus.IN_PROGRESS,
                aggregated_result=partial_result,
                progress=progress,
            )

        logger.debug(
            f"All {iteration_count} iteration jobs complete for step {step_id}"
        )

        if tracking["failed_indices"]:
            failed_count = len(tracking["failed_indices"])
            error_msg = (
                f"Iteration failed: {failed_count}/{iteration_count} jobs failed"
            )
            logger.warning(error_msg)
            return IterationResult(
                status=IterationStatus.HAS_FAILURES,
                error=error_msg,
                progress=progress,
            )

        aggregated_result = IterationHandler.aggregate_results(tracking, step_id)
        return IterationResult(
            status=IterationStatus.ALL_COMPLETE,
            aggregated_result=aggregated_result,
            progress=progress,
        )

    @staticmethod
    def aggregate_results(tracking: Dict[str, Any], step_id: str) -> Dict[str, Any]:
        """
        Aggregate results from all completed iteration jobs.

        Combines downloaded_files arrays and collects per-iteration fields
        (like seed_used, prompt_id) into arrays. Results are ordered by
        iteration_index to maintain array ordering.

        Args:
            tracking: Iteration tracking dict with results for each index
            step_id: Step identifier for logging

        Returns:
            Aggregated result combining all iteration outputs
        """
        iteration_count: int = tracking["iteration_count"]
        results: Dict[str, Any] = tracking["results"]

        # Initialize aggregated result
        downloaded_files_list: List[Dict[str, Any]] = []
        aggregated: Dict[str, Any] = {
            "success": True,
            "downloaded_files": downloaded_files_list,
            "image_count": 0,
            "iteration_count": iteration_count,
        }

        # Collect values per field across iterations for aggregation
        field_values: Dict[str, List[Any]] = {}

        # Process results in order by iteration_index
        logger.debug(
            f"Aggregation for step {step_id}: iteration_count={iteration_count}, "
            f"tracking_keys={list(results.keys())}"
        )
        for i in range(iteration_count):
            result_data = results.get(str(i), {}).get("result", {})
            if not result_data:
                logger.debug(f"  Iteration {i}: NO result data (missing or empty)")
                continue
            logger.debug(f"  Iteration {i}: result_keys={list(result_data.keys())}")

            # Aggregate downloaded_files arrays
            files = result_data.get("downloaded_files", [])
            if files:
                # Add iteration_index to each file for downstream grouping
                for f in files:
                    f_with_index = dict(f)
                    f_with_index["iteration_index"] = i
                    downloaded_files_list.append(f_with_index)

            # Collect other fields for aggregation
            for key, value in result_data.items():
                if key == "downloaded_files":
                    continue  # Already handled
                elif key == "success":
                    aggregated["success"] = aggregated.get("success", True) and value
                elif key == "image_count":
                    # Will recalculate from downloaded_files
                    continue
                elif key == "request_data" and isinstance(value, dict):
                    # Add iteration_index to request_data for UI display
                    value_with_index = dict(value)
                    value_with_index["iteration_index"] = i
                    if key not in field_values:
                        field_values[key] = []
                    field_values[key].append(value_with_index)
                else:
                    # Collect all values for this field
                    if key not in field_values:
                        field_values[key] = []
                    field_values[key].append(value)

        # Aggregate collected field values
        # Fields that vary per iteration become arrays; constant fields stay scalar
        logger.debug(
            f"Aggregation field_values for step {step_id}: "
            f"{', '.join(f'{k}({len(v)})' for k, v in field_values.items())}"
        )
        for key, values in field_values.items():
            if len(values) == 1:
                # Single value - keep as scalar
                aggregated[key] = values[0]
            else:
                # Multiple values - check if all identical
                first_value = values[0]
                all_same = all(v == first_value for v in values)
                if all_same:
                    # All identical - keep as scalar
                    aggregated[key] = first_value
                else:
                    # Values differ - store as array
                    aggregated[key] = values
                    logger.debug(
                        f"  Field '{key}': {len(values)} different values → array"
                    )

        # Update image_count from aggregated files
        aggregated["image_count"] = len(downloaded_files_list)

        logger.debug(
            f"Aggregated iteration results for step {step_id}: "
            f"{aggregated['image_count']} files from {iteration_count} iterations"
        )

        return aggregated
