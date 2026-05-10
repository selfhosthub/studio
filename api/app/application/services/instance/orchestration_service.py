# api/app/application/services/instance/orchestration_service.py


import uuid
import logging
from datetime import datetime, UTC
from typing import Any, Dict, List, Optional

from app.domain.common.exceptions import (
    BusinessRuleViolation,
    ConfigurationError,
    EntityNotFoundError,
    InvalidStateTransition,
    InvariantViolation,
)
from app.domain.instance.models import Instance, InstanceStatus
from app.domain.instance.events import (
    InstanceStatusChangedEvent,
    InstanceStepCompletedEvent,
)
from app.domain.instance.repository import InstanceRepository
from app.domain.instance.iteration_execution_repository import (
    IterationExecutionRepository,
)
from app.domain.instance_step.models import StepExecutionStatus
from app.domain.instance_step.step_execution import StepExecution
from app.domain.instance_step.step_execution_repository import StepExecutionRepository
from app.domain.workflow.repository import WorkflowRepository
from app.domain.org_file.repository import OrgFileRepository
from app.infrastructure.storage.workspace import cleanup_resource_files

from app.application.dtos import InstanceResponse, StepExecutionResponse
from app.application.interfaces import EventBus
from app.application.services.job_enqueue import JobEnqueueService
from app.application.services.instance.helpers import (
    get_instance_or_raise,
    assert_instance_idle,
    assert_no_active_operation,
    BUSY_STATUSES,
)
from app.domain.audit.models import (
    AuditAction,
    AuditActorType,
    AuditCategory,
    AuditSeverity,
    ResourceType,
)

logger = logging.getLogger(__name__)

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.application.services.audit_service import AuditService
    from app.application.services.instance.state_transition_service import (
        StateTransitionService,
    )


class OrchestrationService:
    def __init__(
        self,
        instance_repository: InstanceRepository,
        step_execution_repository: StepExecutionRepository,
        workflow_repository: WorkflowRepository,
        event_bus: EventBus,
        job_enqueue_service: Optional[JobEnqueueService] = None,
        resource_repository: Optional[OrgFileRepository] = None,
        audit_service: Optional["AuditService"] = None,
        state_transition_service: Optional["StateTransitionService"] = None,
        iteration_execution_repository: Optional[IterationExecutionRepository] = None,
    ):
        self.instance_repository = instance_repository
        self.step_execution_repository = step_execution_repository
        self.workflow_repository = workflow_repository
        self.event_bus = event_bus
        self.job_enqueue_service = job_enqueue_service
        self.resource_repository = resource_repository
        self.audit_service = audit_service
        self.state_transition_service = state_transition_service
        self.iteration_execution_repository = iteration_execution_repository

    async def _get_instance_or_raise(self, instance_id: uuid.UUID) -> Instance:
        return await get_instance_or_raise(self.instance_repository, instance_id)

    _BUSY_STATUSES = BUSY_STATUSES

    def _assert_instance_idle(self, instance: Instance, operation: str) -> None:
        assert_instance_idle(instance, operation)

    async def _find_job_for_step(
        self, instance_id: uuid.UUID, step_id: str
    ) -> Optional[Any]:
        jobs = await self.step_execution_repository.list_by_instance(
            skip=0, limit=100, instance_id=instance_id
        )
        for job in jobs:
            if job.step_key == step_id:
                return job
        return None

    async def _resolve_iteration_metadata_from_rows(
        self, step_execution_id: uuid.UUID
    ) -> tuple[Optional[int], Optional[str]]:
        """(iteration_count, iteration_group_id) from canonical row source.

        Both halves are None if the repository is unwired or no rows exist.
        """
        if not self.iteration_execution_repository:
            return None, None
        rows = await self.iteration_execution_repository.list_by_step_id(
            step_execution_id
        )
        if not rows:
            return None, None
        group_id = rows[0].iteration_group_id
        return len(rows), (str(group_id) if group_id else None)

    @staticmethod
    def _set_nested_value(obj: Any, path: str, value: Any) -> None:
        """Set a value via bracket/dot notation: 'messages[2].content', 'styles[0]'."""
        import re

        # "messages[2].content" → ["messages", "2", "content"]
        parts = re.split(r"\.|\[(\d+)\]", path)
        parts = [p for p in parts if p is not None and p != ""]

        if len(parts) == 1:
            obj[parts[0]] = value
            return

        current = obj
        for part in parts[:-1]:
            if part.isdigit():
                current = current[int(part)]
            else:
                current = current[part]

        last = parts[-1]
        if last.isdigit():
            current[int(last)] = value
        else:
            current[last] = value

    async def inject_form_values_into_snapshot(
        self, instance: Instance, form_values: Dict[str, Any]
    ) -> None:
        """Write form_values into the workflow_snapshot's step parameters.

        Two cases:
          mappingType='form'             → set on job.parameters
          _prompt_variable:var_name      → set on prompt mapping's variableValues
        """
        if not instance.workflow_snapshot:
            return
        steps = instance.workflow_snapshot.get("steps", {})

        for step_id, step_config in steps.items():
            if not isinstance(step_config, dict):
                continue

            input_mappings = {}
            step_mappings = step_config.get("input_mappings", {})
            if isinstance(step_mappings, dict):
                input_mappings.update(step_mappings)
            client_metadata = step_config.get("client_metadata", {})
            if isinstance(client_metadata, dict):
                cm_mappings = client_metadata.get("input_mappings", {})
                if isinstance(cm_mappings, dict):
                    input_mappings.update(cm_mappings)

            # Pass 1: standard form mappings.
            for param_key, mapping in input_mappings.items():
                if not isinstance(mapping, dict):
                    continue

                mapping_type = mapping.get("mappingType") or mapping.get("mapping_type")
                if mapping_type != "form":
                    continue

                form_key = f"{step_id}.{param_key}"
                if form_key in form_values:
                    if "job" not in step_config:
                        step_config["job"] = {}
                    if "parameters" not in step_config["job"]:
                        step_config["job"]["parameters"] = {}

                    value = form_values[form_key]
                    # Coerce string form values to match the existing typed value
                    # - HTML <select> always emits strings, providers may require ints/floats.
                    existing = step_config["job"]["parameters"].get(param_key)
                    if isinstance(value, str) and isinstance(existing, int):
                        try:
                            value = int(value)
                        except (ValueError, TypeError):
                            pass
                    elif isinstance(value, str) and isinstance(existing, float):
                        try:
                            value = float(value)
                        except (ValueError, TypeError):
                            pass

                    self._set_nested_value(
                        step_config["job"]["parameters"],
                        param_key,
                        value,
                    )
                    logger.debug(f"Injected form value for {form_key}")

            # Pass 2: prompt-variable form values.
            for form_key, form_value in form_values.items():
                if not form_key.startswith(f"{step_id}."):
                    continue
                param_path = form_key[len(step_id) + 1 :]
                if not param_path.startswith("_prompt_variable:"):
                    continue
                var_name = param_path[len("_prompt_variable:") :]

                for param_key, mapping in input_mappings.items():
                    if not isinstance(mapping, dict):
                        continue
                    if mapping.get("mappingType") != "prompt":
                        continue
                    if "variableValues" not in mapping:
                        mapping["variableValues"] = {}
                    mapping["variableValues"][var_name] = form_value
                    logger.debug(
                        f"Injected prompt variable {var_name}={form_value!r:.80} "
                        f"into {step_id}.{param_key}"
                    )

            # Pass 3: expose prompt-variable values as pseudo step results so
            # downstream steps can map to _prompt_variable:* via standard "mapped" type.
            for form_key, form_value in form_values.items():
                if f"{step_id}._prompt_variable:" in form_key:
                    tv_key = form_key.split(".", 1)[1]
                    step_config.setdefault("_resolved_prompt_vars", {})[
                        tv_key
                    ] = form_value

    async def resume_from_waiting_state(
        self,
        instance_id: uuid.UUID,
        step_id: str,
        waiting_status: InstanceStatus,
        op_type: str,
        metadata: Dict[str, Any],
        next_action_fn,
        post_resume_hook_fn=None,
    ) -> Instance:
        """Shared flow for resuming from a WAITING_FOR_* state.

        Used by approve/reject and manual-trigger paths.

        Flow: validate status → record metadata → clear pending sentinel →
        run next_action_fn (owns step+status transitions) → persist →
        publish status-changed → if step is terminal, publish step-completed →
        run optional post_resume_hook_fn (enqueue next work).

        op_type controls the output_data key mapping:
          "approval"       → metadata under "approvals",       clears "pending_approval"
          "manual_trigger" → metadata under "manual_triggers", clears "pending_trigger"
        """
        key_map = {
            "approval": ("approvals", "pending_approval"),
            "manual_trigger": ("manual_triggers", "pending_trigger"),
        }
        try:
            metadata_key, pending_key = key_map[op_type]
        except KeyError as e:
            raise ValueError(
                f"Unknown op_type for resume_from_waiting_state: {op_type!r}"
            ) from e

        instance = await self._get_instance_or_raise(instance_id)
        logger.info(
            f"Resuming from {waiting_status.value} via {op_type} on step {step_id}",
            extra={"instance_id": str(instance_id), "step_id": step_id},
        )

        if instance.status != waiting_status:
            # Wording preserved verbatim - error-handling code parses this string.
            wait_phrase = (
                "waiting for approval"
                if waiting_status == InstanceStatus.WAITING_FOR_APPROVAL
                else (
                    "waiting for manual trigger"
                    if waiting_status == InstanceStatus.WAITING_FOR_MANUAL_TRIGGER
                    else waiting_status.value
                )
            )
            raise InvalidStateTransition(
                f"Instance is not {wait_phrase}. " f"Current status: {instance.status}"
            )

        old_status = waiting_status.value

        if metadata_key not in instance.output_data:
            instance.output_data[metadata_key] = {}
        instance.output_data[metadata_key][step_id] = metadata

        if pending_key in instance.output_data:
            del instance.output_data[pending_key]

        await next_action_fn(instance)

        await self.instance_repository.update(instance)

        await self.event_bus.publish(
            InstanceStatusChangedEvent(
                aggregate_id=instance.id,
                aggregate_type="instance",
                instance_id=instance.id,
                workflow_id=instance.workflow_id,
                organization_id=instance.organization_id,
                old_status=old_status,
                new_status=instance.status,
            )
        )

        # Fire step-completion only when terminal: approve→completed, reject→failed.
        # Trigger leaves the step RUNNING, not terminal, so it skips this.
        step_terminal = (
            step_id in instance.completed_step_ids
            or step_id in instance.failed_step_ids
        )
        if step_terminal:
            step_config = (
                (instance.workflow_snapshot or {}).get("steps", {}).get(step_id, {})
            )
            step_name = (
                step_config.get("name", step_id)
                if isinstance(step_config, dict)
                else step_id
            )
            await self.event_bus.publish(
                InstanceStepCompletedEvent(
                    aggregate_id=instance.id,
                    aggregate_type="instance",
                    instance_id=instance.id,
                    workflow_id=instance.workflow_id,
                    organization_id=instance.organization_id,
                    step_id=step_id,
                    step_name=step_name,
                    completion_time=datetime.now(UTC),
                )
            )

        if post_resume_hook_fn:
            await post_resume_hook_fn(instance)

        return instance

    async def process_approval(
        self,
        instance_id: uuid.UUID,
        step_id: str,
        approved: bool,
        approved_by: Optional[uuid.UUID] = None,
        comment: Optional[str] = None,
        get_completed_step_results_fn=None,
    ) -> InstanceResponse:
        """Approve or reject a waiting step."""
        approval_result = {
            "approved": approved,
            "approved_by": str(approved_by) if approved_by else None,
            "comment": comment,
            "processed_at": datetime.now(UTC).isoformat(),
        }

        if approved:

            async def approve_action(inst: Instance) -> None:
                instance_step = (
                    await self.step_execution_repository.get_by_instance_and_key(
                        inst.id, step_id
                    )
                )
                if instance_step:
                    if instance_step.status != StepExecutionStatus.COMPLETED:
                        instance_step.complete()
                        await self.step_execution_repository.update(instance_step)
                if step_id not in inst.completed_step_ids:
                    inst.completed_step_ids.append(step_id)
                # Approval steps inherit dependency outputs as their own.
                await self._apply_approval_passthrough(inst, step_id)
                inst.status = InstanceStatus.PROCESSING

            async def approve_post_hook(inst: Instance) -> None:
                await self._enqueue_next_steps_after_approval(
                    inst, step_id, get_completed_step_results_fn
                )

            instance = await self.resume_from_waiting_state(
                instance_id=instance_id,
                step_id=step_id,
                waiting_status=InstanceStatus.WAITING_FOR_APPROVAL,
                op_type="approval",
                metadata=approval_result,
                next_action_fn=approve_action,
                post_resume_hook_fn=approve_post_hook,
            )
            logger.info(
                f"Approval step {step_id} approved for instance {instance_id}",
                extra={"instance_id": str(instance_id), "step_id": step_id},
            )
        else:
            rejection_reason = f"Approval rejected: {comment or 'No reason provided'}"

            async def reject_action(inst: Instance) -> None:
                instance_step = (
                    await self.step_execution_repository.get_by_instance_and_key(
                        inst.id, step_id
                    )
                )
                if instance_step:
                    instance_step.cancel()
                    instance_step.error_message = rejection_reason
                    await self.step_execution_repository.update(instance_step)
                if step_id not in inst.failed_step_ids:
                    inst.failed_step_ids.append(step_id)
                inst.fail(
                    error_message=rejection_reason,
                    error_data={
                        "rejected_by": str(approved_by) if approved_by else None,
                        "comment": comment,
                    },
                )

            instance = await self.resume_from_waiting_state(
                instance_id=instance_id,
                step_id=step_id,
                waiting_status=InstanceStatus.WAITING_FOR_APPROVAL,
                op_type="approval",
                metadata=approval_result,
                next_action_fn=reject_action,
            )
            logger.info(
                f"Approval step {step_id} rejected for instance {instance_id}",
                extra={"instance_id": str(instance_id), "step_id": step_id},
            )

        # Audit logging is handled by the API route, not here.
        return InstanceResponse.from_domain(instance)

    async def trigger_manual_step(
        self,
        instance_id: uuid.UUID,
        step_id: str,
        triggered_by: Optional[uuid.UUID] = None,
        get_completed_step_results_fn=None,
    ) -> InstanceResponse:
        """Manually start a step waiting on a manual trigger."""
        trigger_result = {
            "triggered_by": str(triggered_by) if triggered_by else None,
            "triggered_at": datetime.now(UTC).isoformat(),
        }

        async def trigger_action(inst: Instance) -> None:
            inst.status = InstanceStatus.PROCESSING

        async def trigger_post_hook(inst: Instance) -> None:
            await self._enqueue_step_after_trigger(
                inst, step_id, get_completed_step_results_fn
            )

        instance = await self.resume_from_waiting_state(
            instance_id=instance_id,
            step_id=step_id,
            waiting_status=InstanceStatus.WAITING_FOR_MANUAL_TRIGGER,
            op_type="manual_trigger",
            metadata=trigger_result,
            next_action_fn=trigger_action,
            post_resume_hook_fn=trigger_post_hook,
        )
        logger.info(
            f"Manual step {step_id} triggered for instance {instance_id}",
            extra={"instance_id": str(instance_id), "step_id": step_id},
        )
        # Audit logging is handled by the API route, not here.

        return InstanceResponse.from_domain(instance)

    async def resume_with_webhook_callback(
        self,
        instance_id: uuid.UUID,
        step_id: str,
        callback_payload: Dict[str, Any],
    ) -> InstanceResponse:
        """Resume a paused step using a webhook callback payload."""
        instance = await self._get_instance_or_raise(instance_id)
        logger.info(
            f"Webhook callback received for step {step_id} on instance {instance_id}",
            extra={"instance_id": str(instance_id), "step_id": step_id},
        )

        if not instance.output_data:
            instance.output_data = {}

        step_outputs = instance.output_data.get(step_id, {})
        step_outputs["callback_received"] = True
        step_outputs["callback_payload"] = callback_payload
        step_outputs["received_at"] = datetime.now(UTC).isoformat()
        instance.output_data[step_id] = step_outputs

        # Status is owned by the step entity, not output_data.
        step_entity = await self.step_execution_repository.get_by_instance_and_key(
            instance_id, step_id
        )
        if step_entity:
            step_entity.complete(output_data=step_outputs)
            await self.step_execution_repository.update(step_entity)

        instance.resume()

        instance = await self.instance_repository.update(instance)

        return InstanceResponse.from_domain(instance)

    async def run_stopped_step(
        self,
        instance_id: uuid.UUID,
        step_id: str,
        get_completed_step_results_fn=None,
    ) -> StepExecutionResponse:
        """Run a step that was previously stopped/skipped."""
        instance = await self._get_instance_or_raise(instance_id)
        logger.info(
            f"Running stopped step {step_id} on instance {instance_id}",
            extra={"instance_id": str(instance_id), "step_id": step_id},
        )

        # Block on mid-flight or concurrent operations - parity with other
        # re-execution paths.
        self._assert_instance_idle(instance, "run stopped step")
        assert_no_active_operation(
            instance,
            operation_label="run stopped step",
            error_class=BusinessRuleViolation,
            code="OPERATION_ALREADY_ACTIVE",
            requested_operation="run_stopped_step",
        )

        if not instance.workflow_snapshot:
            raise InvariantViolation("Instance has no workflow snapshot")

        steps = instance.workflow_snapshot.get("steps", {})
        if step_id not in steps:
            raise EntityNotFoundError("Step", step_id)

        step_config = steps[step_id]

        step_name = step_config.get("name", step_id)
        if isinstance(step_config, dict) and step_config.get("job"):
            step_name = step_config["job"].get("display_name", step_name)

        step_entity = instance.step_entities.get(step_id)
        current_status = step_entity.status.value if step_entity else "pending"
        if current_status in ["completed", "running"]:
            raise InvalidStateTransition(f"Step {step_id} is already {current_status}")

        if instance.status == InstanceStatus.COMPLETED:
            instance.status = InstanceStatus.PROCESSING
            instance.completed_at = None

        instance_step = await self.step_execution_repository.get_by_instance_and_key(
            instance.id, step_id
        )
        if instance_step:
            # Reset to PENDING so the consumer's first status update drives
            # the expected PENDING→QUEUED transition. Calling .start() would
            # pre-advance to RUNNING, causing the consumer's transition to fail.
            instance_step.reset_to_pending()
            await self.step_execution_repository.update(instance_step)

        # Reset the execution row so it isn't still terminal - a terminal row
        # causes the consumer to drop every subsequent worker status.
        step_job = await self._find_job_for_step(instance.id, step_id)
        if step_job:
            step_job.rerun()
            await self.step_execution_repository.update(step_job)

        if (
            isinstance(step_config, dict)
            and step_config.get("execution_mode") == "stop"
        ):
            step_config["execution_mode"] = "enabled"
            instance.workflow_snapshot["steps"][step_id] = step_config

        await self.instance_repository.update(instance)

        previous_results = {}
        if get_completed_step_results_fn:
            previous_results = await get_completed_step_results_fn(instance)

        if not self.job_enqueue_service:
            raise ConfigurationError("Job enqueue service not available")

        job_id = await self.job_enqueue_service.enqueue_step(
            instance_id=instance.id,
            step_id=step_id,
            organization_id=instance.organization_id,
            workflow_snapshot=instance.workflow_snapshot,
            instance_parameters=instance.input_data or {},
            previous_step_results=previous_results,
        )

        logger.info(
            f"Enqueued stopped step {step_id} for instance {instance_id}, job_id={job_id}",
            extra={"instance_id": str(instance_id), "step_id": step_id},
        )

        if not job_id:
            raise InvariantViolation(f"Enqueue for step {step_id} returned no job_id")

        # Return a transient QUEUED DTO so the UI renders immediately; id
        # matches the eventual persisted row once the worker's first status arrives.
        job = StepExecution(
            id=uuid.UUID(job_id),
            instance_id=instance_id,
            step_key=step_id,
            step_name=step_name,
            status=StepExecutionStatus.QUEUED,
            execution_data={},
            retry_count=0,
        )
        return StepExecutionResponse.from_domain(job)

    async def regenerate_resources(
        self,
        instance_id: uuid.UUID,
        step_id: str,
        resource_ids: List[uuid.UUID],
        parameter_overrides: Optional[Dict[str, Any]] = None,
        get_completed_step_results_fn=None,
    ) -> StepExecutionResponse:
        """Regenerate selected resources.

        With parameter_overrides on iteration resources the overrides are
        passed through as pre_resolved_parameters, bypassing resolution. Other
        cases run the normal resolution pipeline.
        """
        from app.domain.instance.models import OperationType

        if not self.resource_repository:
            raise ConfigurationError(
                "Resource repository not configured for regeneration"
            )

        instance = await self._get_instance_or_raise(instance_id)
        logger.info(
            f"Regenerating {len(resource_ids)} resources for step {step_id} "
            f"on instance {instance_id}",
            extra={
                "instance_id": str(instance_id),
                "step_id": step_id,
                "resource_count": len(resource_ids),
            },
        )

        assert_no_active_operation(
            instance,
            operation_label="regenerate",
            error_class=InvalidStateTransition,
        )

        first_resource = await self.resource_repository.get_by_id(resource_ids[0])
        if not first_resource:
            raise EntityNotFoundError(
                entity_type="OrgFile",
                entity_id=str(resource_ids[0]),
                code=f"Resource {resource_ids[0]} not found",
            )

        if not first_resource.job_execution_id:
            raise EntityNotFoundError(
                entity_type="StepExecution",
                entity_id="None",
                code=f"Resource {resource_ids[0]} has no associated job execution",
            )

        job = await self.step_execution_repository.get_by_id(
            first_resource.job_execution_id
        )
        if not job:
            raise EntityNotFoundError(
                entity_type="StepExecution",
                entity_id=str(first_resource.job_execution_id),
                code=f"Job for resource not found in instance {instance_id}",
            )

        # iteration_index is per-file (on the resource); count and group_id
        # come from the canonical iteration tracking rows.
        iteration_metadata = None
        if first_resource.metadata and "iteration_index" in first_resource.metadata:
            iter_count, iter_group = await self._resolve_iteration_metadata_from_rows(
                job.id
            )
            iteration_metadata = {
                "iteration_index": first_resource.metadata["iteration_index"],
                "iteration_count": iter_count,
                "iteration_group_id": iter_group,
            }
            logger.info(
                f"Preserving iteration metadata for regeneration: index={iteration_metadata['iteration_index']}"
            )

        # Defer deletion until enqueue succeeds.
        resources_to_delete = []
        for resource_id in resource_ids:
            resource = await self.resource_repository.get_by_id(resource_id)
            if resource:
                resources_to_delete.append(resource)

        if not resources_to_delete:
            raise BusinessRuleViolation("No valid resources found to regenerate")

        staged_ids = [str(r.id) for r in resources_to_delete]

        if self.state_transition_service:
            ctx = await self.state_transition_service.prepare_for_reexecution(
                instance=instance,
                operation=OperationType.REGENERATE_RESOURCES,
                step_ids=[step_id],
                step_executions=[job],
                operation_metadata={
                    "job_id": str(job.id),
                    "staged_deletion_resource_ids": staged_ids,
                },
            )
        else:
            job.rerun()
            await self.step_execution_repository.update(job)
            if instance.status in [InstanceStatus.COMPLETED, InstanceStatus.FAILED]:
                instance.status = InstanceStatus.PROCESSING
            await self.instance_repository.update(instance)
            ctx = None

        if self.job_enqueue_service and instance.workflow_snapshot:
            try:
                is_passthrough = bool(
                    parameter_overrides
                    and iteration_metadata is not None
                    and iteration_metadata.get("iteration_index") is not None
                )

                if is_passthrough:
                    # Frontend sent complete pre-resolved params.
                    await self.job_enqueue_service.enqueue_step(
                        instance_id=instance.id,
                        step_id=step_id,
                        organization_id=instance.organization_id,
                        workflow_snapshot=instance.workflow_snapshot,
                        pre_resolved_parameters=parameter_overrides,
                        iteration_metadata=iteration_metadata,
                    )
                else:
                    # Run normal resolution pipeline.
                    previous_results = {}
                    if get_completed_step_results_fn:
                        previous_results = await get_completed_step_results_fn(instance)
                    await self.job_enqueue_service.enqueue_step(
                        instance_id=instance.id,
                        step_id=step_id,
                        organization_id=instance.organization_id,
                        workflow_snapshot=instance.workflow_snapshot,
                        instance_parameters=instance.input_data or {},
                        previous_step_results=previous_results,
                        iteration_metadata=iteration_metadata,
                    )

                if self.state_transition_service:
                    await self.state_transition_service.commit_session()
                logger.info(
                    f"Re-enqueued step {step_id} for regeneration"
                    f" (passthrough={is_passthrough})"
                    + (
                        f", iteration_index={iteration_metadata['iteration_index']}"
                        if iteration_metadata
                        else ""
                    ),
                    extra={"instance_id": str(instance.id), "step_id": step_id},
                )
            except Exception as e:
                logger.error(
                    f"Failed to re-enqueue step {step_id} for regeneration: {e}",
                    extra={
                        "instance_id": str(instance.id),
                        "step_id": step_id,
                        "error": str(e),
                    },
                )
                if self.state_transition_service and ctx:
                    await self.state_transition_service.rollback(instance, ctx, e)
                raise
        elif self.state_transition_service:
            # No enqueue - commit prepare state so operation tracking reflects start.
            await self.state_transition_service.commit_session()

        # On the deferred path the result processor deletes staged resources on
        # success (originals survive on failure for retry). Otherwise there is
        # no worker round-trip, so delete inline.
        deferred = bool(
            self.state_transition_service
            and self.job_enqueue_service
            and instance.workflow_snapshot
        )
        if not deferred:
            for resource in resources_to_delete:
                virtual_path = resource.virtual_path
                thumbnail_path = (
                    resource.metadata.get("thumbnail_path")
                    if resource.metadata
                    else None
                )
                await self.resource_repository.delete(resource.id)
                cleanup_resource_files(
                    virtual_path=virtual_path,
                    thumbnail_path=thumbnail_path,
                )
            logger.info(
                f"Deleted {len(resources_to_delete)} resources inline "
                f"for regeneration in step {step_id}"
            )
        else:
            logger.info(
                f"Staged {len(staged_ids)} resources for deletion on success "
                f"in step {step_id}"
            )

        return StepExecutionResponse.from_domain(job)

    async def regenerate_iteration(
        self,
        instance_id: uuid.UUID,
        step_id: str,
        iteration_index: int,
        parameter_overrides: Optional[Dict[str, Any]] = None,
        get_completed_step_results_fn=None,
    ) -> StepExecutionResponse:
        """Regenerate a single iteration of a step.

        Does NOT call rerun on the job - keeping it terminal lets the result
        processor route through the subsequent-iteration handler, which
        preserves the other N-1 iterations' tracking.
        """
        from app.domain.instance.models import OperationType

        if not self.resource_repository:
            raise ConfigurationError(
                "Resource repository not configured for regeneration"
            )

        instance = await self._get_instance_or_raise(instance_id)

        step_job = await self.step_execution_repository.get_by_instance_and_key(
            instance_id=instance_id, step_key=step_id
        )
        if step_job is None:
            raise EntityNotFoundError("StepExecution", step_id)

        # iteration_count: row-derived value is canonical; step field wins when set.
        row_count, row_group_id = await self._resolve_iteration_metadata_from_rows(
            step_job.id
        )
        iteration_count = step_job.iteration_count or row_count
        if not iteration_count:
            raise BusinessRuleViolation(f"Step {step_id} is not an iteration step")
        if iteration_index >= iteration_count:
            raise BusinessRuleViolation(
                f"Iteration index {iteration_index} out of range "
                f"(step has {iteration_count} iterations)"
            )

        iteration_group_id = row_group_id or str(uuid.uuid4())
        iteration_metadata = {
            "iteration_index": iteration_index,
            "iteration_count": iteration_count,
            "iteration_group_id": iteration_group_id,
        }
        logger.info(
            f"Regenerating iteration {iteration_index} of step {step_id} "
            f"(group={iteration_group_id})"
        )

        # Stage iteration's resources for delete-on-success.
        all_resources = await self.resource_repository.list_by_job(step_job.id)
        iteration_resources = [
            r
            for r in all_resources
            if r.metadata and r.metadata.get("iteration_index") == iteration_index
        ]
        staged_ids = [str(r.id) for r in iteration_resources]

        # Empty step_ids/jobs is deliberate - skipping reset preserves other iterations' tracking.
        if self.state_transition_service:
            ctx = await self.state_transition_service.prepare_for_reexecution(
                instance=instance,
                operation=OperationType.REGENERATE_ITERATION,
                step_ids=[],
                step_executions=[],
                operation_metadata={
                    "step_id": step_id,
                    "job_id": str(step_job.id),
                    "iteration_index": iteration_index,
                    "staged_deletion_resource_ids": staged_ids,
                },
            )
        else:
            if instance.status in [InstanceStatus.COMPLETED, InstanceStatus.FAILED]:
                instance.status = InstanceStatus.PROCESSING
            ctx = None

        # Reset the iteration row to PENDING so the next result for this index is tracked cleanly.
        if self.iteration_execution_repository:
            instance_step = (
                await self.step_execution_repository.get_by_instance_and_key(
                    instance.id, step_id
                )
            )
            if instance_step:
                try:
                    group_uuid = (
                        uuid.UUID(iteration_group_id) if iteration_group_id else None
                    )
                except (ValueError, AttributeError):
                    group_uuid = None
                iteration = (
                    await self.iteration_execution_repository.get_by_step_and_index(
                        instance_step.id, iteration_index, group_uuid
                    )
                )
                if iteration:
                    iteration.reset_for_regeneration(
                        parameters=parameter_overrides or None
                    )
                    await self.iteration_execution_repository.update(
                        iteration, commit=False
                    )
                    logger.info(
                        f"Reset iteration row {iteration.id} (index={iteration_index}) "
                        f"for regeneration (step={step_id}, "
                        f"group={iteration_group_id})"
                    )
                else:
                    logger.warning(
                        f"IterationExecution row not found for regeneration: "
                        f"step={step_id} index={iteration_index} group={iteration_group_id}"
                    )

        # Flush cleanup into the same transaction as prepare so they commit or roll back together.
        if self.state_transition_service:
            await self.instance_repository.update(instance, commit=False)
        else:
            await self.instance_repository.update(instance)

        if self.job_enqueue_service and instance.workflow_snapshot:
            try:
                is_passthrough = bool(parameter_overrides)

                if is_passthrough:
                    # Frontend sent complete pre-resolved params.
                    await self.job_enqueue_service.enqueue_step(
                        instance_id=instance.id,
                        step_id=step_id,
                        organization_id=instance.organization_id,
                        workflow_snapshot=instance.workflow_snapshot,
                        pre_resolved_parameters=parameter_overrides,
                        iteration_metadata=iteration_metadata,
                    )
                else:
                    previous_results = {}
                    if get_completed_step_results_fn:
                        previous_results = await get_completed_step_results_fn(instance)
                    await self.job_enqueue_service.enqueue_step(
                        instance_id=instance.id,
                        step_id=step_id,
                        organization_id=instance.organization_id,
                        workflow_snapshot=instance.workflow_snapshot,
                        instance_parameters=instance.input_data or {},
                        previous_step_results=previous_results,
                        iteration_metadata=iteration_metadata,
                    )

                if self.state_transition_service:
                    await self.state_transition_service.commit_session()
                logger.info(
                    f"Re-enqueued step {step_id} for iteration {iteration_index} "
                    f"regeneration (passthrough={is_passthrough})",
                    extra={
                        "instance_id": str(instance.id),
                        "step_id": step_id,
                        "iteration_index": iteration_index,
                    },
                )

            except Exception as e:
                logger.error(
                    f"Failed to re-enqueue step {step_id} for iteration "
                    f"{iteration_index} regeneration: {e}",
                    extra={
                        "instance_id": str(instance.id),
                        "step_id": step_id,
                        "error": str(e),
                    },
                )
                if self.state_transition_service and ctx:
                    await self.state_transition_service.rollback(instance, ctx, e)
                raise
        elif self.state_transition_service:
            # No enqueue - commit prepare state so operation tracking reflects start.
            await self.state_transition_service.commit_session()

        # Same deferred-vs-inline deletion split as the resource regeneration path.
        deferred = bool(
            self.state_transition_service
            and self.job_enqueue_service
            and instance.workflow_snapshot
        )
        if iteration_resources and not deferred:
            for resource in iteration_resources:
                virtual_path = resource.virtual_path
                thumbnail_path = (
                    resource.metadata.get("thumbnail_path")
                    if resource.metadata
                    else None
                )
                await self.resource_repository.delete(resource.id)
                cleanup_resource_files(
                    virtual_path=virtual_path, thumbnail_path=thumbnail_path
                )
            logger.info(
                f"Deleted {len(iteration_resources)} resources inline "
                f"for iteration {iteration_index} in step {step_id}"
            )
        elif iteration_resources:
            logger.info(
                f"Staged {len(staged_ids)} resources for deletion on success "
                f"for iteration {iteration_index} in step {step_id}"
            )

        return StepExecutionResponse.from_domain(step_job)

    async def _apply_approval_passthrough(
        self,
        instance: Instance,
        approval_step_id: str,
    ) -> None:
        """Copy dependency outputs onto the approval step's output_data."""
        if not instance.workflow_snapshot:
            logger.debug("No workflow_snapshot, skipping approval passthrough")
            return

        steps = instance.workflow_snapshot.get("steps", {})
        approval_step_config = steps.get(approval_step_id, {})
        depends_on = approval_step_config.get("depends_on", []) or []

        if not depends_on:
            logger.debug(
                f"Approval step {approval_step_id} has no dependencies, nothing to pass through"
            )
            return

        passthrough_data = {}
        for dep_step_id in depends_on:
            dep_instance_step = (
                await self.step_execution_repository.get_by_instance_and_key(
                    instance.id, dep_step_id
                )
            )
            if dep_instance_step and dep_instance_step.output_data:
                passthrough_data.update(dep_instance_step.output_data)

        approval_instance_step = (
            await self.step_execution_repository.get_by_instance_and_key(
                instance.id, approval_step_id
            )
        )

        if approval_instance_step:
            if passthrough_data:
                approval_instance_step.output_data = passthrough_data
                await self.step_execution_repository.update(approval_instance_step)

                if self.audit_service:
                    step_config = steps.get(approval_step_id, {})
                    step_name = (
                        step_config.get("name", approval_step_id)
                        if isinstance(step_config, dict)
                        else approval_step_id
                    )
                    await self.audit_service.log_event(
                        actor_id=None,
                        actor_type=AuditActorType.SYSTEM,
                        action=AuditAction.BYPASS,
                        resource_type=ResourceType.INSTANCE_STEP,
                        resource_id=instance.id,
                        resource_name=step_name,
                        organization_id=instance.organization_id,
                        severity=AuditSeverity.INFO,
                        category=AuditCategory.CONFIGURATION,
                        changes={
                            "passthrough_fields": len(passthrough_data),
                            "source_dependencies": depends_on,
                        },
                        metadata={
                            "step_id": approval_step_id,
                            "instance_id": str(instance.id),
                            "workflow_id": str(instance.workflow_id),
                            "description": "Auto-passthrough of dependency data to approval step",
                        },
                    )

            logger.info(
                f"Applied passthrough to approval step {approval_step_id}: "
                f"{len(passthrough_data)} fields from {len(depends_on)} dependencies"
            )
        else:
            logger.warning(
                f"No instance_step found for approval step {approval_step_id}"
            )

    async def _enqueue_next_steps_after_approval(
        self,
        instance: Instance,
        completed_step_id: str,
        get_completed_step_results_fn=None,
    ) -> None:
        if not self.job_enqueue_service or not instance.workflow_snapshot:
            logger.warning(
                f"Cannot enqueue next steps: job_enqueue_service={bool(self.job_enqueue_service)}, "
                f"workflow_snapshot={bool(instance.workflow_snapshot)}"
            )
            return

        steps = instance.workflow_snapshot.get("steps", {})
        # Variable resolution sees COMPLETED steps only - paused steps' partial outputs are invisible.
        completed_steps = set(instance.completed_step_ids)

        ready_steps = []
        for step_id, step_config in steps.items():
            if step_id in completed_steps:
                continue
            if step_id in instance.failed_step_ids:
                continue
            step_entity = instance.step_entities.get(step_id)
            if step_entity and step_entity.status.value in [
                StepExecutionStatus.RUNNING.value,
                "running",
            ]:
                continue

            depends_on = []
            if isinstance(step_config, dict):
                depends_on = step_config.get("depends_on", []) or []

            if all(dep in completed_steps for dep in depends_on):
                ready_steps.append(step_id)

        if not ready_steps:
            logger.info(f"No ready steps found after approval of {completed_step_id}")
            all_completed = all(sid in completed_steps for sid in steps.keys())
            if all_completed:
                instance.status = InstanceStatus.COMPLETED
                instance.completed_at = datetime.now(UTC)
                await self.instance_repository.update(instance)
                logger.info(f"Instance {instance.id} completed after final approval")
            return

        previous_results = {}
        if get_completed_step_results_fn:
            previous_results = await get_completed_step_results_fn(instance)

        for next_step_id in ready_steps:
            try:
                await self.job_enqueue_service.enqueue_step(
                    instance_id=instance.id,
                    step_id=next_step_id,
                    organization_id=instance.organization_id,
                    workflow_snapshot=instance.workflow_snapshot,
                    instance_parameters=instance.input_data or {},
                    previous_step_results=previous_results,
                )
                logger.info(
                    f"Enqueued step {next_step_id} after approval of {completed_step_id}",
                    extra={
                        "instance_id": str(instance.id),
                        "step_id": next_step_id,
                    },
                )
            except Exception as e:
                logger.error(f"Failed to enqueue step {next_step_id}: {e}")

    async def _enqueue_step_after_trigger(
        self,
        instance: Instance,
        step_id: str,
        get_completed_step_results_fn=None,
    ) -> None:
        if not self.job_enqueue_service or not instance.workflow_snapshot:
            logger.warning(
                f"Cannot enqueue step: job_enqueue_service={bool(self.job_enqueue_service)}, "
                f"workflow_snapshot={bool(instance.workflow_snapshot)}"
            )
            return

        previous_results = {}
        if get_completed_step_results_fn:
            previous_results = await get_completed_step_results_fn(instance)

        try:
            await self.job_enqueue_service.enqueue_step(
                instance_id=instance.id,
                step_id=step_id,
                organization_id=instance.organization_id,
                workflow_snapshot=instance.workflow_snapshot,
                instance_parameters=instance.input_data or {},
                previous_step_results=previous_results,
            )
            logger.info(
                f"Enqueued manually triggered step {step_id} for instance {instance.id}",
                extra={"instance_id": str(instance.id), "step_id": step_id},
            )
        except Exception as e:
            logger.error(
                f"Failed to enqueue manually triggered step {step_id}: {e}",
                extra={
                    "instance_id": str(instance.id),
                    "step_id": step_id,
                    "error": str(e),
                },
            )
            raise
