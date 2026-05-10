# api/app/application/services/instance/job_service.py


import uuid
import logging
from datetime import datetime, UTC
from typing import Any, Dict, List, Optional

import jsonpath_ng

from app.config.settings import settings
from app.domain.instance_step.models import StepExecutionStatus
from app.domain.instance_step.step_execution import StepExecution
from app.domain.instance.models import (
    Instance,
    InstanceStatus,
    OperationType,
)
from app.domain.instance.repository import InstanceRepository
from app.domain.instance_step.step_execution_repository import StepExecutionRepository
from app.domain.workflow.repository import WorkflowRepository
from app.domain.org_file.repository import OrgFileRepository
from app.infrastructure.storage.workspace import cleanup_resource_files

from app.application.dtos import StepExecutionCreate, StepExecutionResponse
from app.application.interfaces import EventBus, EntityNotFoundError
from app.domain.common.exceptions import BusinessRuleViolation
from app.application.services.mapping_resolver import MappingResolver
from app.application.services.job_enqueue import JobEnqueueService
from app.application.services.instance.helpers import (
    get_instance_or_raise,
    assert_instance_idle,
    BUSY_STATUSES,
)
from app.domain.workflow import apply_output_forwarding

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.application.services.instance.state_transition_service import (
        StateTransitionService,
    )

logger = logging.getLogger(__name__)


class JobService:
    def __init__(
        self,
        instance_repository: InstanceRepository,
        step_execution_repository: StepExecutionRepository,
        workflow_repository: WorkflowRepository,
        event_bus: EventBus,
        job_enqueue_service: Optional[JobEnqueueService] = None,
        resource_repository: Optional[OrgFileRepository] = None,
        state_transition_service: Optional["StateTransitionService"] = None,
    ):
        self.instance_repository = instance_repository
        self.step_execution_repository = step_execution_repository
        self.workflow_repository = workflow_repository
        self.event_bus = event_bus
        self.job_enqueue_service = job_enqueue_service
        self.resource_repository = resource_repository
        self.state_transition_service = state_transition_service
        self.mapping_resolver = MappingResolver()

    async def _get_instance_or_raise(self, instance_id: uuid.UUID) -> Instance:
        return await get_instance_or_raise(self.instance_repository, instance_id)

    async def _get_job_or_raise(self, job_id: uuid.UUID) -> StepExecution:
        job = await self.step_execution_repository.get_by_id(job_id)
        if not job:
            raise EntityNotFoundError(
                entity_type="StepExecution",
                entity_id=job_id,
                code=f"StepExecution with ID {job_id} not found",
            )
        return job

    _BUSY_STATUSES = BUSY_STATUSES

    def _assert_instance_idle(self, instance: Instance, operation: str) -> None:
        assert_instance_idle(instance, operation)

    async def _publish_events(self, aggregate: Instance) -> None:
        events = aggregate.clear_events()
        for event in events:
            await self.event_bus.publish(event)

    async def resolve_input_mappings(
        self, instance: Instance, workflow_id: uuid.UUID, step_id: str
    ) -> Dict[str, Any]:
        """Resolve a step's input_mappings against the execution context."""
        workflow = await self.workflow_repository.get_by_id(workflow_id)
        if not workflow:
            logger.warning(
                f"Workflow {workflow_id} not found for input mapping resolution"
            )
            return {}

        step_config = workflow.steps.get(step_id)
        if not step_config:
            logger.warning(f"Step {step_id} not found in workflow")
            return {}

        # Mappings can live on client_metadata or as step-level extras.
        input_mappings = {}

        if step_config.client_metadata:
            cm_mappings = step_config.client_metadata.get("input_mappings", {})
            if isinstance(cm_mappings, dict):
                input_mappings.update(cm_mappings)

        step_dict = (
            step_config.model_dump() if hasattr(step_config, "model_dump") else {}
        )
        step_mappings = step_dict.get("input_mappings", {})
        if isinstance(step_mappings, dict):
            input_mappings.update(step_mappings)

        if not input_mappings:
            logger.debug(f"No input_mappings configured for step {step_id}")
            return (step_config.job.parameters if step_config.job else None) or {}

        all_jobs = await self.step_execution_repository.list_by_instance(
            skip=0, limit=settings.DEFAULT_FETCH_LIMIT, instance_id=instance.id
        )
        completed_steps = [
            {"step_id": job.step_key, "extracted_outputs": job.extracted_outputs}
            for job in all_jobs
            if job.status == StepExecutionStatus.COMPLETED and job.extracted_outputs
        ]

        execution_context = self.mapping_resolver.build_execution_context(
            trigger_data=instance.input_data, completed_steps=completed_steps
        )

        resolved_params = self.mapping_resolver.resolve_mappings(
            input_mappings=input_mappings, execution_context=execution_context
        )

        static_params = (step_config.job.parameters if step_config.job else None) or {}
        final_params = {**static_params, **resolved_params}

        logger.info(
            f"Resolved {len(resolved_params)} input mappings for step {step_id}. "
            f"Final parameters: {len(final_params)} fields"
        )

        return final_params

    async def extract_outputs(
        self, job: StepExecution, workflow_id: uuid.UUID, step_id: str
    ) -> None:
        """Extract outputs from a job result via the step's JSONPath output config."""
        workflow = await self.workflow_repository.get_by_id(workflow_id)
        if not workflow:
            logger.warning(f"Workflow {workflow_id} not found for output extraction")
            return

        step_config = workflow.steps.get(step_id)
        if not step_config or not step_config.outputs:
            logger.debug(f"No outputs configured for step {step_id}")
            return

        if not job.result:
            logger.warning(f"Job {job.id} has no result to extract from")
            return

        for output_name, output_config in step_config.outputs.items():
            path = output_config.get("path")
            if not path:
                logger.warning(f"Output '{output_name}' missing 'path' configuration")
                continue

            try:
                expr = jsonpath_ng.parse(path)
                matches = expr.find(job.result)

                if matches:
                    values = [m.value for m in matches]
                    extracted_value = values[0] if len(values) == 1 else values
                    job.extracted_outputs[output_name] = extracted_value
                    logger.debug(
                        f"Extracted '{output_name}' from step {step_id}: {extracted_value}"
                    )
                else:
                    logger.warning(
                        f"JSONPath '{path}' found no matches in job result for output '{output_name}'"
                    )

            except Exception as e:
                logger.error(
                    f"Failed to extract output '{output_name}' from step {step_id}: {e}"
                )

        if job.extracted_outputs:
            await self.step_execution_repository.update(job)
            logger.info(
                f"Extracted {len(job.extracted_outputs)} outputs from step {step_id}"
            )

    async def create_job(self, job_data: StepExecutionCreate) -> StepExecutionResponse:
        """Create a job for a step, resolving input mappings before persistence."""
        instance = await self._get_instance_or_raise(job_data.instance_id)

        step_name: Optional[str] = getattr(job_data, "step_name", None)
        step_config: Optional[Dict[str, Any]] = getattr(job_data, "step_config", None)

        if not step_name:
            step_name = f"Step {job_data.step_key}"
        if not step_config:
            step_config = {}

        resolved_params = await self.resolve_input_mappings(
            instance=instance,
            workflow_id=instance.workflow_id,
            step_id=job_data.step_key,
        )

        if resolved_params:
            step_config = {**step_config, "parameters": resolved_params}
            logger.info(
                f"Job for step {job_data.step_key}: resolved {len(resolved_params)} parameters"
            )

        # Per-step config travels on execution_data.
        job = StepExecution.create(
            instance_id=instance.id,
            step_key=job_data.step_key,
            step_name=step_name,
            execution_data={
                "timeout_seconds": step_config.get("timeout_seconds"),
                "on_failure": step_config.get("on_failure", "fail_workflow"),
                "is_required": step_config.get("is_required", True),
                "depends_on": step_config.get("depends_on", []),
                "parameters": step_config.get("parameters", {}),
            },
            parameters=step_config.get("parameters", {}),
        )

        job = await self.step_execution_repository.create(job)
        return StepExecutionResponse.from_domain(job)

    async def start_job(self, job_id: uuid.UUID) -> StepExecutionResponse:
        job = await self._get_job_or_raise(job_id)
        job.start()
        job = await self.step_execution_repository.update(job)
        logger.info(
            f"Job {job_id} started for step {job.step_key}",
            extra={
                "job_id": str(job_id),
                "instance_id": str(job.instance_id),
                "step_id": job.step_key,
            },
        )

        instance = await self.instance_repository.get_by_id(job.instance_id)
        if instance:
            instance.handle_step_started(job.step_key, job)
            await self.instance_repository.update(instance)
            await self._publish_events(instance)

        return StepExecutionResponse.from_domain(job)

    async def complete_job(
        self, job_id: uuid.UUID, result: Dict[str, Any]
    ) -> StepExecutionResponse:
        job = await self._get_job_or_raise(job_id)
        job.complete(result)
        job = await self.step_execution_repository.update(job)
        logger.info(
            f"Job {job_id} completed for step {job.step_key}",
            extra={
                "job_id": str(job_id),
                "instance_id": str(job.instance_id),
                "step_id": job.step_key,
            },
        )

        instance = await self.instance_repository.get_by_id(job.instance_id)
        if instance:
            await self.extract_outputs(job, instance.workflow_id, job.step_key)
            instance.handle_step_completed(job.step_key, job)
            await self.instance_repository.update(instance)
            await self._publish_events(instance)

        return StepExecutionResponse.from_domain(job)

    async def fail_job(
        self, job_id: uuid.UUID, error_message: str
    ) -> StepExecutionResponse:
        job = await self._get_job_or_raise(job_id)
        job.fail(error_message)
        job = await self.step_execution_repository.update(job)
        logger.info(
            f"Job {job_id} failed for step {job.step_key}: {error_message}",
            extra={
                "job_id": str(job_id),
                "instance_id": str(job.instance_id),
                "step_id": job.step_key,
                "error": error_message,
            },
        )

        instance = await self.instance_repository.get_by_id(job.instance_id)
        if instance:
            instance.handle_step_failed(job.step_key, job)
            await self.instance_repository.update(instance)
            await self._publish_events(instance)

        return StepExecutionResponse.from_domain(job)

    async def cancel_job(self, job_id: uuid.UUID) -> StepExecutionResponse:
        job = await self._get_job_or_raise(job_id)
        job.cancel()
        job = await self.step_execution_repository.update(job)
        logger.info(
            f"Job {job_id} cancelled for step {job.step_key}",
            extra={
                "job_id": str(job_id),
                "instance_id": str(job.instance_id),
                "step_id": job.step_key,
            },
        )
        return StepExecutionResponse.from_domain(job)

    async def cancel_all_jobs_for_instance(
        self, instance_id: uuid.UUID
    ) -> List[StepExecutionResponse]:
        """Cancel all pending/queued/running jobs for an instance."""
        jobs = await self.step_execution_repository.list_by_instance(
            instance_id=instance_id,
            skip=0,
            limit=settings.DEFAULT_FETCH_LIMIT,
        )

        cancellable_statuses = [
            StepExecutionStatus.PENDING,
            StepExecutionStatus.QUEUED,
            StepExecutionStatus.RUNNING,
        ]
        jobs_to_cancel = [job for job in jobs if job.status in cancellable_statuses]

        cancelled_jobs = []
        for job in jobs_to_cancel:
            try:
                job.cancel()
                updated_job = await self.step_execution_repository.update(job)
                cancelled_jobs.append(StepExecutionResponse.from_domain(updated_job))
            except Exception as e:
                logger.warning(
                    f"Failed to cancel job {job.id}: {e}",
                    extra={"instance_id": str(instance_id), "job_id": str(job.id)},
                )

        logger.info(
            f"Cancelled {len(cancelled_jobs)} jobs for instance {instance_id}",
            extra={"instance_id": str(instance_id)},
        )

        return cancelled_jobs

    async def retry_job(self, job_id: uuid.UUID) -> StepExecutionResponse:
        job = await self._get_job_or_raise(job_id)

        instance = await self.instance_repository.get_by_id(job.instance_id)
        if instance:
            self._assert_instance_idle(instance, "retry job")

        if instance and self.state_transition_service:
            ctx = await self.state_transition_service.prepare_for_reexecution(
                instance=instance,
                operation=OperationType.RETRY_JOB,
                step_ids=[job.step_key],
                step_executions=[job],
                is_retry=True,
                operation_metadata={"job_id": str(job.id)},
            )

            if self.job_enqueue_service and instance.workflow_snapshot:
                try:
                    previous_results = await self.get_completed_step_results(instance)
                    await self.job_enqueue_service.enqueue_step(
                        instance_id=instance.id,
                        step_id=job.step_key,
                        organization_id=instance.organization_id,
                        workflow_snapshot=instance.workflow_snapshot,
                        instance_parameters=instance.input_data or {},
                        previous_step_results=previous_results,
                    )
                    await self.state_transition_service.commit_session()
                    logger.info(
                        f"Re-enqueued step {job.step_key} for instance {instance.id} retry",
                        extra={
                            "instance_id": str(instance.id),
                            "step_id": job.step_key,
                            "job_id": str(job.id),
                        },
                    )
                except Exception as e:
                    logger.error(
                        f"Failed to re-enqueue step {job.step_key} for retry",
                        extra={
                            "instance_id": str(instance.id),
                            "job_id": str(job.id),
                            "error": str(e),
                        },
                    )
                    # rollback() flushes + commits + publishes WS atomically.
                    await self.state_transition_service.rollback(instance, ctx, e)
                    raise
            else:
                await self.state_transition_service.commit_session()
        else:
            job.retry()
            job = await self.step_execution_repository.update(job)
            if instance and instance.status == InstanceStatus.FAILED:
                instance.status = InstanceStatus.PROCESSING
                await self.instance_repository.update(instance)

        return StepExecutionResponse.from_domain(job)

    async def rerun_job_only(self, job_id: uuid.UUID) -> StepExecutionResponse:
        """Rerun a single job. Old resources are deleted only after enqueue succeeds."""
        job = await self._get_job_or_raise(job_id)

        instance = await self.instance_repository.get_by_id(job.instance_id)
        if instance:
            self._assert_instance_idle(instance, "rerun job")

        # Skipped steps require all predecessors to be completed.
        step_entity = instance.step_entities.get(job.step_key) if instance else None
        if instance and step_entity and step_entity.status.value == "skipped":
            workflow = await self.workflow_repository.get_by_id(instance.workflow_id)
            if workflow:
                await self._assert_predecessors_completed(
                    instance, job.step_key, workflow.steps
                )

        # Defer resource deletion until enqueue succeeds - avoids orphans on failure.
        resources_to_delete = []
        if self.resource_repository:
            resources_to_delete = await self.resource_repository.list_by_job(job_id)

        if instance and self.state_transition_service:
            ctx = await self.state_transition_service.prepare_for_reexecution(
                instance=instance,
                operation=OperationType.RERUN_JOB,
                step_ids=[job.step_key],
                step_executions=[job],
                operation_metadata={"job_id": str(job.id)},
            )

            if self.job_enqueue_service and instance.workflow_snapshot:
                try:
                    previous_results = await self.get_completed_step_results(instance)
                    await self.job_enqueue_service.enqueue_step(
                        instance_id=instance.id,
                        step_id=job.step_key,
                        organization_id=instance.organization_id,
                        workflow_snapshot=instance.workflow_snapshot,
                        instance_parameters=instance.input_data or {},
                        previous_step_results=previous_results,
                    )
                    await self.state_transition_service.commit_session()
                    logger.info(
                        f"Re-enqueued step {job.step_key} for single-step rerun",
                        extra={
                            "instance_id": str(instance.id),
                            "step_id": job.step_key,
                            "job_id": str(job.id),
                        },
                    )
                except Exception as e:
                    logger.error(
                        f"Failed to re-enqueue step {job.step_key} for rerun",
                        extra={
                            "instance_id": str(instance.id),
                            "job_id": str(job.id),
                            "error": str(e),
                        },
                    )
                    await self.state_transition_service.rollback(instance, ctx, e)
                    raise
            else:
                await self.state_transition_service.commit_session()
        else:
            job.rerun()
            job = await self.step_execution_repository.update(job)
            if instance and instance.status in [
                InstanceStatus.COMPLETED,
                InstanceStatus.FAILED,
            ]:
                instance.status = InstanceStatus.PROCESSING
                await self.instance_repository.update(instance)

        if self.resource_repository and resources_to_delete:
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
                f"Deleted {len(resources_to_delete)} resources for job {job_id} after rerun enqueue",
                extra={"job_id": str(job_id), "instance_id": str(job.instance_id)},
            )

        return StepExecutionResponse.from_domain(job)

    async def rerun_and_continue(self, job_id: uuid.UUID) -> StepExecutionResponse:
        """Rerun a job and every downstream dependent step."""
        job = await self._get_job_or_raise(job_id)
        instance = await self.instance_repository.get_by_id(job.instance_id)

        if not instance:
            raise EntityNotFoundError(
                entity_type="Instance",
                entity_id=job.instance_id,
                code=f"Instance not found for job {job_id}",
            )
        self._assert_instance_idle(instance, "rerun and continue")

        workflow = await self.workflow_repository.get_by_id(instance.workflow_id)
        if not workflow:
            raise EntityNotFoundError(
                entity_type="Workflow",
                entity_id=instance.workflow_id,
                code="Workflow not found for instance",
            )

        downstream_steps = self._get_downstream_steps(job.step_key, workflow.steps)
        steps_to_execute = [job.step_key] + downstream_steps

        jobs_to_reset = []
        resources_to_delete = []
        for step_id in steps_to_execute:
            step_job = await self._find_job_by_step(instance.id, step_id)
            if step_job:
                jobs_to_reset.append(step_job)
                if self.resource_repository:
                    resources = await self.resource_repository.list_by_job(step_job.id)
                    resources_to_delete.extend(resources)

        if self.state_transition_service:
            ctx = await self.state_transition_service.prepare_for_reexecution(
                instance=instance,
                operation=OperationType.RERUN_AND_CONTINUE,
                step_ids=steps_to_execute,
                step_executions=jobs_to_reset,
                operation_metadata={"job_id": str(job.id)},
            )

            logger.info(
                f"Prepared {len(steps_to_execute)} steps for rerun_and_continue",
                extra={
                    "instance_id": str(instance.id),
                    "step_id": job.step_key,
                    "step_ids": steps_to_execute,
                },
            )

            if self.job_enqueue_service and instance.workflow_snapshot:
                try:
                    previous_results = await self.get_completed_step_results(
                        instance, exclude_steps=steps_to_execute
                    )
                    await self.job_enqueue_service.enqueue_step(
                        instance_id=instance.id,
                        step_id=job.step_key,
                        organization_id=instance.organization_id,
                        workflow_snapshot=instance.workflow_snapshot,
                        instance_parameters=instance.input_data or {},
                        previous_step_results=previous_results,
                    )
                    await self.state_transition_service.commit_session()
                    logger.info(
                        f"Re-enqueued step {job.step_key} for continue rerun, "
                        f"{len(steps_to_execute)} steps will be re-executed",
                        extra={
                            "instance_id": str(instance.id),
                            "step_id": job.step_key,
                            "job_id": str(job.id),
                        },
                    )
                except Exception as e:
                    logger.error(
                        f"Failed to re-enqueue step {job.step_key} for rerun_and_continue",
                        extra={
                            "instance_id": str(instance.id),
                            "job_id": str(job.id),
                            "error": str(e),
                        },
                    )
                    await self.state_transition_service.rollback(instance, ctx, e)
                    raise
            else:
                await self.state_transition_service.commit_session()
        else:
            for step_job in jobs_to_reset:
                step_job.rerun()
                await self.step_execution_repository.update(step_job)
            if instance.status in [InstanceStatus.COMPLETED, InstanceStatus.FAILED]:
                instance.status = InstanceStatus.PROCESSING
            await self.instance_repository.update(instance)

        if self.resource_repository and resources_to_delete:
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
                f"Deleted {len(resources_to_delete)} resources for rerun_and_continue after enqueue",
                extra={"instance_id": str(instance.id), "job_id": str(job.id)},
            )

        return StepExecutionResponse.from_domain(job)

    async def rerun_step_only(
        self, instance_id: uuid.UUID, step_id: str
    ) -> StepExecutionResponse:
        """Rerun every job for a step without re-running dependents.

        Used when re-executing with modified inputs but the user does not want
        downstream steps automatically retriggered.
        """
        instance = await self.instance_repository.get_by_id(instance_id)
        if not instance:
            raise EntityNotFoundError(
                entity_type="Instance",
                entity_id=instance_id,
                code="Instance not found",
            )
        self._assert_instance_idle(instance, "rerun step")

        # Skipped steps require all predecessors completed.
        step_entity = instance.step_entities.get(step_id)
        if step_entity and step_entity.status.value == "skipped":
            workflow = await self.workflow_repository.get_by_id(instance.workflow_id)
            if workflow:
                await self._assert_predecessors_completed(
                    instance, step_id, workflow.steps
                )

        all_jobs = await self.step_execution_repository.list_by_instance(
            skip=0, limit=settings.DEFAULT_FETCH_LIMIT, instance_id=instance_id
        )
        step_jobs = [j for j in all_jobs if j.step_key == step_id]

        if not step_jobs:
            raise EntityNotFoundError(
                entity_type="StepExecution",
                entity_id=f"{instance_id}/{step_id}",
                code=f"No jobs found for step {step_id}",
            )

        first_job = step_jobs[0]

        # Defer resource deletion until enqueue succeeds.
        resources_to_delete = []
        if self.resource_repository:
            for job in step_jobs:
                resources = await self.resource_repository.list_by_job(job.id)
                resources_to_delete.extend(resources)

        if self.state_transition_service:
            ctx = await self.state_transition_service.prepare_for_reexecution(
                instance=instance,
                operation=OperationType.RERUN_STEP,
                step_ids=[step_id],
                step_executions=step_jobs,
                skip_instance_transition=True,
                operation_metadata={"job_id": str(first_job.id)},
            )

            if self.job_enqueue_service and instance.workflow_snapshot:
                try:
                    previous_results = await self.get_completed_step_results(instance)
                    await self.job_enqueue_service.enqueue_step(
                        instance_id=instance.id,
                        step_id=step_id,
                        organization_id=instance.organization_id,
                        workflow_snapshot=instance.workflow_snapshot,
                        instance_parameters=instance.input_data or {},
                        previous_step_results=previous_results,
                    )
                    await self.state_transition_service.commit_session()
                    logger.info(
                        f"Re-enqueued step {step_id} for step-only rerun",
                        extra={"instance_id": str(instance_id), "step_id": step_id},
                    )
                except Exception as e:
                    logger.error(
                        f"Failed to re-enqueue step {step_id} for step-only rerun",
                        extra={
                            "instance_id": str(instance_id),
                            "step_id": step_id,
                            "error": str(e),
                        },
                    )
                    await self.state_transition_service.rollback(instance, ctx, e)
                    raise
            else:
                await self.state_transition_service.commit_session()
        else:
            for job in step_jobs:
                job.rerun()
                await self.step_execution_repository.update(job)
            if instance.status in [InstanceStatus.COMPLETED, InstanceStatus.FAILED]:
                instance.status = InstanceStatus.PROCESSING
            await self.instance_repository.update(instance)

        if self.resource_repository and resources_to_delete:
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
                f"Deleted {len(resources_to_delete)} resources for step {step_id} "
                f"({len(step_jobs)} jobs) after rerun enqueue",
                extra={"instance_id": str(instance_id), "step_id": step_id},
            )

        return StepExecutionResponse.from_domain(first_job)

    def _get_predecessor_step_ids(
        self, step_id: str, steps: Dict[str, Any]
    ) -> List[str]:
        step_config = steps.get(step_id)
        if step_config is None:
            return []
        if hasattr(step_config, "depends_on"):
            return list(step_config.depends_on or [])
        elif isinstance(step_config, dict):
            return list(step_config.get("depends_on", []) or [])
        return []

    async def _assert_predecessors_completed(
        self,
        instance: Instance,
        step_id: str,
        steps: Dict[str, Any],
    ) -> None:
        """Block direct rerun of a skipped step until all predecessors are completed."""
        predecessor_ids = self._get_predecessor_step_ids(step_id, steps)
        if not predecessor_ids:
            return

        incomplete = []
        for pred_id in predecessor_ids:
            pred_entity = instance.step_entities.get(pred_id)
            status = pred_entity.status.value if pred_entity else None
            if status != "completed":
                incomplete.append(f"{pred_id} ({status or 'unknown'})")

        if incomplete:
            raise BusinessRuleViolation(
                message=(
                    f"Cannot rerun skipped step '{step_id}': "
                    f"predecessor steps not completed: {', '.join(incomplete)}. "
                    f"Use 'Rerun' on the failed predecessor to re-execute "
                    f"it and all downstream steps."
                ),
                code="PREDECESSORS_NOT_COMPLETED",
                context={
                    "step_id": step_id,
                    "incomplete_predecessors": incomplete,
                },
            )

    def _get_downstream_steps(self, step_id: str, steps: Dict[str, Any]) -> List[str]:
        """Steps that transitively depend on step_id (BFS)."""
        downstream = []
        queue = [step_id]
        visited = {step_id}

        while queue:
            current = queue.pop(0)
            for sid, step_config in steps.items():
                if sid in visited:
                    continue
                depends_on = []
                if hasattr(step_config, "depends_on"):
                    depends_on = step_config.depends_on or []
                elif isinstance(step_config, dict):
                    depends_on = step_config.get("depends_on", []) or []

                if current in depends_on:
                    visited.add(sid)
                    downstream.append(sid)
                    queue.append(sid)

        return downstream

    async def _find_job_by_step(
        self, instance_id: uuid.UUID, step_id: str
    ) -> Optional[StepExecution]:
        jobs = await self.step_execution_repository.list_by_instance(
            skip=0, limit=settings.DEFAULT_FETCH_LIMIT, instance_id=instance_id
        )
        for job in jobs:
            if job.step_key == step_id:
                return job
        return None

    async def get_completed_step_results(
        self, instance: Instance, exclude_steps: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Results from completed steps for use in re-execution input resolution.

        Mirrors normal orchestration: extracted_outputs > raw result; downloaded_files
        rebuilt from live resources; iteration-aggregated results backfilled from
        instance storage; output forwarding and prompt-variable merging applied.
        """
        from app.application.services.result_processing import (
            resources_to_downloaded_files,
        )

        exclude_steps = exclude_steps or []
        results: Dict[str, Any] = {}
        processed_steps: set[str] = set()

        jobs = await self.step_execution_repository.list_by_instance(
            skip=0, limit=settings.DEFAULT_FETCH_LIMIT, instance_id=instance.id
        )

        for job in jobs:
            if job.step_key in exclude_steps:
                continue
            if job.status != StepExecutionStatus.COMPLETED:
                continue
            if not (job.extracted_outputs or job.result):
                continue
            # Iteration steps emit many jobs - first job wins.
            if job.step_key in processed_steps:
                continue

            step_result = job.get_outputs()

            # Rebuild downloaded_files from live resources. Both FK columns on
            # org_files target step_executions.id.
            if "downloaded_files" in step_result and self.resource_repository:
                resources = await self.resource_repository.list_by_instance_step(job.id)
                if not resources:
                    resources = await self.resource_repository.list_by_job(job.id)
                step_result["downloaded_files"] = resources_to_downloaded_files(
                    resources, api_base_url=settings.API_BASE_URL
                )
                step_result["image_count"] = len(resources)

            if job.execution_data and "_prompt_variables" in job.execution_data:
                prompt_vars = job.execution_data["_prompt_variables"]
                step_result["_prompt_variables"] = prompt_vars
                for var_name, var_value in prompt_vars.items():
                    if var_name not in step_result:
                        step_result[var_name] = var_value

            results[job.step_key] = step_result
            processed_steps.add(job.step_key)

        # output_data["steps"] holds aggregated iteration results - backfill any
        # step not already covered above.
        stored_steps = instance.output_data.get("steps", {})
        for step_id, step_data in stored_steps.items():
            if step_id in exclude_steps or not isinstance(step_data, dict):
                continue
            if step_id in processed_steps:
                continue
            results[step_id] = dict(step_data)

        # Surface prompt-variable form values as pseudo step results.
        if instance.input_data:
            for form_key, form_value in instance.input_data.items():
                if "._prompt_variable:" in form_key:
                    step_id, suffix = form_key.split(".", 1)
                    var_name = suffix.split(":", 1)[1]
                    if step_id not in results:
                        results[step_id] = {}
                    results[step_id][var_name] = form_value

        if instance.workflow_snapshot:
            steps_config = instance.workflow_snapshot.get("steps", {})
            results = apply_output_forwarding(results, steps_config)

        return results

    async def get_job(self, job_id: uuid.UUID) -> Optional[StepExecutionResponse]:
        job = await self.step_execution_repository.get_by_id(job_id)
        if not job:
            return None
        return StepExecutionResponse.from_domain(job)

    async def list_jobs_for_instance(
        self,
        instance_id: uuid.UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> List[StepExecutionResponse]:
        jobs = await self.step_execution_repository.list_by_instance(
            instance_id=instance_id,
            skip=skip,
            limit=limit,
        )
        return [StepExecutionResponse.from_domain(job) for job in jobs]

    async def list_jobs_by_status(
        self,
        status: str,
        instance_id: Optional[uuid.UUID] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[StepExecutionResponse]:
        try:
            status_enum = StepExecutionStatus(status)
        except ValueError:
            return []

        if instance_id:
            jobs = await self.step_execution_repository.list_by_instance(
                instance_id=instance_id,
                status=status_enum,
                skip=skip,
                limit=limit,
            )
        else:
            jobs = []

        return [StepExecutionResponse.from_domain(job) for job in jobs]

    async def get_instance_statistics(
        self,
        instance_id: uuid.UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> Dict[str, Any]:
        instance = await self._get_instance_or_raise(instance_id)
        jobs = await self.step_execution_repository.list_by_instance(
            instance_id=instance_id,
            skip=skip,
            limit=limit,
        )

        stats: Dict[str, Any] = {
            "instance_id": str(instance_id),
            "status": instance.status,
            "total_jobs": len(jobs),
            "pending_jobs": sum(
                1 for j in jobs if j.status == StepExecutionStatus.PENDING
            ),
            "running_jobs": sum(
                1 for j in jobs if j.status == StepExecutionStatus.RUNNING
            ),
            "completed_jobs": sum(
                1 for j in jobs if j.status == StepExecutionStatus.COMPLETED
            ),
            "failed_jobs": sum(
                1 for j in jobs if j.status == StepExecutionStatus.FAILED
            ),
            "cancelled_jobs": sum(
                1 for j in jobs if j.status == StepExecutionStatus.CANCELLED
            ),
            "started_at": (
                instance.started_at.isoformat() if instance.started_at else None
            ),
            "completed_at": (
                instance.completed_at.isoformat() if instance.completed_at else None
            ),
            "duration_seconds": None,
        }

        if instance.started_at and instance.completed_at:
            duration = instance.completed_at - instance.started_at
            stats["duration_seconds"] = duration.total_seconds()

        return stats

    async def update_job_result(
        self, job_id: uuid.UUID, result: Dict[str, Any]
    ) -> StepExecutionResponse:
        """Edit a completed job's result so downstream reruns see the new values."""
        job = await self._get_job_or_raise(job_id)

        if job.status != StepExecutionStatus.COMPLETED:
            raise ValueError(
                f"Cannot update result for job in {job.status.value} status. "
                "Only completed jobs can have their results edited."
            )

        job.result = result
        job.updated_at = datetime.now(UTC)

        job = await self.step_execution_repository.update(job)

        logger.info(f"Updated result for job {job_id}")

        return StepExecutionResponse.from_domain(job)
