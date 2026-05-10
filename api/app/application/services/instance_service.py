# api/app/application/services/instance_service.py

"""Public facade for instance operations. API routes use this, not the internals."""

import uuid
import logging
from datetime import datetime, UTC
from typing import Any, Dict, List, Optional, Protocol

from app.domain.instance.models import Instance, InstanceStatus
from app.domain.instance.repository import InstanceRepository
from app.domain.instance.iteration_execution_repository import (
    IterationExecutionRepository,
)
from app.domain.instance_step.step_execution_repository import StepExecutionRepository
from app.domain.organization.repository import OrganizationRepository
from app.domain.workflow.repository import WorkflowRepository
from app.domain.provider.repository import (
    ProviderRepository,
    ProviderCredentialRepository,
)
from app.domain.org_file.repository import OrgFileRepository

from app.application.dtos import (
    InstanceCreate,
    InstanceResponse,
    StepExecutionCreate,
    StepExecutionResponse,
)
from app.application.dtos.instance_dto import PaginatedInstanceResponse

from app.application.interfaces import EventBus, EntityNotFoundError
from app.application.services.job_enqueue import JobEnqueueService

from app.application.services.instance.lifecycle_service import LifecycleService
from app.application.services.instance.job_service import JobService
from app.application.services.instance.orchestration_service import OrchestrationService
from app.application.services.instance.state_transition_service import (
    StateTransitionService,
)
from app.application.services.instance.deletion_service import (
    DeletionService,
    DeletionResult,
)
from app.application.services.instance.helpers import get_active_op_for_step
from app.domain.queue.repository import QueuedJobRepository

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.application.services.audit_service import AuditService
    from app.application.services.instance_notifier import InstanceNotifier

logger = logging.getLogger(__name__)

WEBHOOK_ENDPOINT = "/webhooks/job-status"


class WebhookConfig(Protocol):
    def get_base_url(self) -> str: ...  # pragma: no cover

    def create_token(self, job_id: uuid.UUID) -> str: ...  # pragma: no cover


class InstanceService:
    def __init__(
        self,
        instance_repository: InstanceRepository,
        workflow_repository: WorkflowRepository,
        organization_repository: OrganizationRepository,
        event_bus: EventBus,
        provider_repository: ProviderRepository,
        credential_repository: ProviderCredentialRepository,
        step_execution_repository: StepExecutionRepository,
        webhook_config: Optional[WebhookConfig] = None,
        job_enqueue_service: Optional[JobEnqueueService] = None,
        resource_repository: Optional[OrgFileRepository] = None,
        queued_job_repository: Optional[QueuedJobRepository] = None,
        audit_service: Optional["AuditService"] = None,
        notifier: Optional["InstanceNotifier"] = None,
        iteration_execution_repository: Optional[IterationExecutionRepository] = None,
    ):
        self.instance_repository = instance_repository
        self.workflow_repository = workflow_repository
        self.organization_repository = organization_repository
        self.event_bus = event_bus
        self.provider_repository = provider_repository
        self.credential_repository = credential_repository
        self.webhook_config = webhook_config
        self.job_enqueue_service = job_enqueue_service
        self.resource_repository = resource_repository
        self.step_execution_repository = step_execution_repository
        self.queued_job_repository = queued_job_repository
        self.iteration_execution_repository = iteration_execution_repository
        self._notifier = notifier

        # Shared transition service; notifier enables WS broadcast on rollback.
        self._state_transition = StateTransitionService(
            instance_repo=instance_repository,
            step_execution_repo=step_execution_repository,
            notifier=notifier,
        )

        self._lifecycle = LifecycleService(
            instance_repository=instance_repository,
            workflow_repository=workflow_repository,
            event_bus=event_bus,
            provider_repository=provider_repository,
            credential_repository=credential_repository,
            step_execution_repository=step_execution_repository,
        )

        self._job = JobService(
            instance_repository=instance_repository,
            workflow_repository=workflow_repository,
            event_bus=event_bus,
            job_enqueue_service=job_enqueue_service,
            resource_repository=resource_repository,
            step_execution_repository=step_execution_repository,
            state_transition_service=self._state_transition,
        )

        self._orchestration = OrchestrationService(
            instance_repository=instance_repository,
            workflow_repository=workflow_repository,
            event_bus=event_bus,
            job_enqueue_service=job_enqueue_service,
            resource_repository=resource_repository,
            step_execution_repository=step_execution_repository,
            audit_service=audit_service,
            state_transition_service=self._state_transition,
            iteration_execution_repository=iteration_execution_repository,
        )

    async def create_instance(self, instance_data: InstanceCreate) -> InstanceResponse:
        return await self._lifecycle.create_instance(instance_data)

    async def start_instance(self, instance_id: uuid.UUID) -> InstanceResponse:
        """Validate credentials and enqueue the first step (or wait for form input)."""
        instance = await self._lifecycle.start_instance(instance_id)

        if self.job_enqueue_service and instance.workflow_snapshot:
            has_form_inputs = self._lifecycle.workflow_has_form_inputs(
                instance.workflow_snapshot
            )
            if not has_form_inputs:
                await self._enqueue_first_step_and_handle_result(instance)
            else:
                logger.info(
                    f"Instance {instance.id} has form inputs - waiting for form submission"
                )

        return InstanceResponse.from_domain(instance)

    async def _enqueue_first_step_and_handle_result(self, instance: Instance) -> None:
        """Enqueue the first step, honoring execution_mode stop/skip semantics."""
        if not self.job_enqueue_service or not instance.workflow_snapshot:
            return

        try:
            result = await self.job_enqueue_service.enqueue_first_step(
                instance_id=instance.id,
                organization_id=instance.organization_id,
                workflow_snapshot=instance.workflow_snapshot,
                instance_parameters=instance.input_data or {},
            )

            if result == "STOP":
                instance.status = InstanceStatus.COMPLETED
                instance.completed_at = datetime.now(UTC)
                await self.instance_repository.update(instance)
                logger.info(
                    f"Instance {instance.id} completed immediately (first step has stop mode)"
                )
            elif result == "SKIP":
                workflow_snapshot = instance.workflow_snapshot
                first_step_id = self.job_enqueue_service.find_entry_step(
                    workflow_snapshot
                )
                if first_step_id:
                    first_step_entity = (
                        await self.step_execution_repository.get_by_instance_and_key(
                            instance.id, first_step_id
                        )
                    )
                    if first_step_entity:
                        first_step_entity.skip()
                        await self.step_execution_repository.update(first_step_entity)
                    await self.instance_repository.update(instance)

                    next_jobs = (
                        await self.job_enqueue_service.enqueue_ready_steps_after_skip(
                            instance_id=instance.id,
                            organization_id=instance.organization_id,
                            workflow_snapshot=workflow_snapshot,
                            skipped_step_ids={first_step_id},
                            instance_parameters=instance.input_data or {},
                        )
                    )

                    if self._notifier:
                        await self._notifier.announce_state_change(
                            instance=instance,
                            action_type="step_skipped",
                            step_id=first_step_id,
                        )

                    if next_jobs == ["STOP"]:
                        instance.status = InstanceStatus.COMPLETED
                        instance.completed_at = datetime.now(UTC)
                        await self.instance_repository.update(instance)
                        logger.info(
                            f"Instance {instance.id} completed (next step after skip has stop mode)"
                        )
                        if self._notifier:
                            await self._notifier.announce_state_change(
                                instance=instance,
                                action_type="completed",
                                session=None,
                            )
                    elif not next_jobs:
                        instance.status = InstanceStatus.COMPLETED
                        instance.completed_at = datetime.now(UTC)
                        await self.instance_repository.update(instance)
                        logger.info(
                            f"Instance {instance.id} completed (no steps after skip)"
                        )
                        if self._notifier:
                            await self._notifier.announce_state_change(
                                instance=instance,
                                action_type="completed",
                                session=None,
                            )
                    else:
                        logger.debug(
                            f"First step {first_step_id} skipped, enqueued {len(next_jobs)} next steps"
                        )
            else:
                logger.debug(f"Enqueued first step for instance {instance.id}")
        except Exception as e:
            logger.error(
                f"Failed to enqueue first step for instance {instance.id}: {e}"
            )
            raise

    async def submit_form_and_start(
        self, instance_id: uuid.UUID, form_values: Dict[str, Any]
    ) -> InstanceResponse:
        """Persist form values, inject them into the snapshot, and start the instance."""
        instance = await self.instance_repository.get_by_id(instance_id)
        if not instance:
            raise EntityNotFoundError(
                entity_type="Instance",
                entity_id=instance_id,
                code=f"Instance with ID {instance_id} not found",
            )

        current_input = instance.input_data or {}
        current_input["form_values"] = form_values
        instance.input_data = current_input

        if instance.workflow_snapshot and instance.workflow_snapshot.get("steps"):
            await self._orchestration.inject_form_values_into_snapshot(
                instance, form_values
            )

        await self._lifecycle.validate_workflow_credentials(
            instance.workflow_id, instance.organization_id
        )

        instance.start()
        # Capture events before update - repository returns a fresh object.
        events = instance.clear_events()
        instance = await self.instance_repository.update(instance)

        for event in events:
            await self.event_bus.publish(event)

        await self._enqueue_first_step_and_handle_result(instance)

        return InstanceResponse.from_domain(instance)

    async def complete_instance(
        self, instance_id: uuid.UUID, output_data: Optional[Dict[str, Any]] = None
    ) -> InstanceResponse:
        return await self._lifecycle.complete_instance(instance_id, output_data)

    async def fail_instance(
        self, instance_id: uuid.UUID, error_data: Optional[Dict[str, Any]] = None
    ) -> InstanceResponse:
        return await self._lifecycle.fail_instance(instance_id, error_data)

    async def pause_instance(self, instance_id: uuid.UUID) -> InstanceResponse:
        return await self._lifecycle.pause_instance(instance_id)

    async def resume_instance(self, instance_id: uuid.UUID) -> InstanceResponse:
        return await self._lifecycle.resume_instance(instance_id)

    async def cancel_instance(self, instance_id: uuid.UUID) -> InstanceResponse:
        """Cancel an instance and its in-flight jobs.

        If a rerun/retry/regenerate is in flight, cancel only the operation
        and restore the original status - don't cancel the whole instance.
        """
        instance = await self.instance_repository.get_by_id(instance_id)
        if not instance:
            raise EntityNotFoundError(
                entity_type="Instance",
                entity_id=instance_id,
                code=f"Instance with ID {instance_id} not found",
            )

        if instance.has_active_operation and self._state_transition:
            active_op = get_active_op_for_step(instance)
            op_type = active_op.get("type") if active_op else None
            logger.info(
                f"Cancelling active operation on instance {instance_id} "
                f"(type={op_type})"
            )
            instance = await self._state_transition.cancel_active_operation(instance)
            return InstanceResponse.from_domain(instance)

        cancelled_jobs = await self._job.cancel_all_jobs_for_instance(instance_id)
        return await self._lifecycle.cancel_instance(instance_id, cancelled_jobs)

    async def delete_instance(
        self,
        instance_id: uuid.UUID,
        organization_id: uuid.UUID,
    ) -> DeletionResult:
        """Permanently delete an instance and all associated data. Caller must
        verify terminal status."""
        if (
            not self.resource_repository
            or not self.step_execution_repository
            or not self.queued_job_repository
        ):
            raise ValueError(
                "DeletionService requires resource, step, and queued_job repositories"
            )

        deletion_service = DeletionService(
            instance_repository=self.instance_repository,
            resource_repository=self.resource_repository,
            step_execution_repository=self.step_execution_repository,
            queued_job_repository=self.queued_job_repository,
        )
        return await deletion_service.delete_instance(instance_id, organization_id)

    async def get_instance(self, instance_id: uuid.UUID) -> Optional[InstanceResponse]:
        instance = await self.instance_repository.get_by_id(instance_id)
        if not instance:
            return None
        return InstanceResponse.from_domain(instance)

    async def get_instance_with_steps(
        self, instance_id: uuid.UUID
    ) -> Optional[InstanceResponse]:
        instance = await self.instance_repository.get_by_id(instance_id)
        if not instance:
            return None
        return InstanceResponse.from_domain(instance)

    async def count_running_instances(self, workflow_id: uuid.UUID) -> int:
        return await self.instance_repository.count_running_by_workflow(workflow_id)

    async def get_waiting_for_webhook(
        self, workflow_id: uuid.UUID
    ) -> Optional[InstanceResponse]:
        instance = await self.instance_repository.get_waiting_for_webhook(workflow_id)
        if not instance:
            return None
        return InstanceResponse.from_domain(instance)

    async def list_instances(
        self,
        organization_id: uuid.UUID,
        skip: int = 0,
        limit: int = 100,
        workflow_id: Optional[uuid.UUID] = None,
        status: Optional[str] = None,
    ) -> List[InstanceResponse]:
        PROCESSING_STATUSES = [
            InstanceStatus.PROCESSING,
            InstanceStatus.WAITING_FOR_APPROVAL,
            InstanceStatus.WAITING_FOR_MANUAL_TRIGGER,
        ]

        status_enum = None
        statuses_list = None
        if status:
            if status == "processing":
                statuses_list = PROCESSING_STATUSES
            else:
                try:
                    status_enum = InstanceStatus(status)
                except ValueError:
                    pass

        if workflow_id:
            instances = await self.instance_repository.list_by_workflow(
                workflow_id=workflow_id,
                status=status_enum,
                statuses=statuses_list,
                skip=skip,
                limit=limit,
            )
        else:
            instances = await self.instance_repository.list_by_organization(
                organization_id=organization_id,
                status=status_enum,
                statuses=statuses_list,
                skip=skip,
                limit=limit,
            )

        return [InstanceResponse.from_domain(inst) for inst in instances]

    async def list_instances_paginated(
        self,
        organization_id: uuid.UUID,
        skip: int = 0,
        limit: int = 25,
        workflow_id: Optional[uuid.UUID] = None,
        status: Optional[str] = None,
    ) -> PaginatedInstanceResponse:
        PROCESSING_STATUSES = [
            InstanceStatus.PROCESSING,
            InstanceStatus.WAITING_FOR_APPROVAL,
            InstanceStatus.WAITING_FOR_MANUAL_TRIGGER,
        ]

        status_enum = None
        statuses_list = None
        if status:
            if status == "processing":
                statuses_list = PROCESSING_STATUSES
            else:
                try:
                    status_enum = InstanceStatus(status)
                except ValueError:
                    pass

        if workflow_id:
            instances = await self.instance_repository.list_by_workflow(
                workflow_id=workflow_id,
                status=status_enum,
                statuses=statuses_list,
                skip=skip,
                limit=limit,
            )
            total = len(instances) + skip
        else:
            instances = await self.instance_repository.list_by_organization(
                organization_id=organization_id,
                status=status_enum,
                statuses=statuses_list,
                skip=skip,
                limit=limit,
            )
            total = await self.instance_repository.count_by_organization(
                organization_id=organization_id,
                status=status_enum,
                statuses=statuses_list,
            )

        return PaginatedInstanceResponse(
            items=[InstanceResponse.from_domain(inst) for inst in instances],
            total=total,
            skip=skip,
            limit=limit,
        )

    async def create_job(self, job_data: StepExecutionCreate) -> StepExecutionResponse:
        return await self._job.create_job(job_data)

    async def create_job_for_instance(
        self, instance_id: uuid.UUID, job_data: StepExecutionCreate
    ) -> StepExecutionResponse:
        if str(job_data.instance_id) != str(instance_id):
            raise ValueError("Instance ID mismatch")
        return await self._job.create_job(job_data)

    async def start_job(self, job_id: uuid.UUID) -> StepExecutionResponse:
        return await self._job.start_job(job_id)

    async def complete_job(
        self, job_id: uuid.UUID, result: Dict[str, Any]
    ) -> StepExecutionResponse:
        return await self._job.complete_job(job_id, result)

    async def fail_job(
        self, job_id: uuid.UUID, error_message: str
    ) -> StepExecutionResponse:
        return await self._job.fail_job(job_id, error_message)

    async def cancel_job(self, job_id: uuid.UUID) -> StepExecutionResponse:
        return await self._job.cancel_job(job_id)

    async def cancel_all_jobs_for_instance(
        self, instance_id: uuid.UUID
    ) -> List[StepExecutionResponse]:
        return await self._job.cancel_all_jobs_for_instance(instance_id)

    async def retry_job(self, job_id: uuid.UUID) -> StepExecutionResponse:
        return await self._job.retry_job(job_id)

    async def rerun_job_only(self, job_id: uuid.UUID) -> StepExecutionResponse:
        return await self._job.rerun_job_only(job_id)

    async def rerun_and_continue(self, job_id: uuid.UUID) -> StepExecutionResponse:
        return await self._job.rerun_and_continue(job_id)

    async def rerun_step_only(
        self, instance_id: uuid.UUID, step_id: str
    ) -> StepExecutionResponse:
        return await self._job.rerun_step_only(instance_id, step_id)

    async def update_job_result(
        self, job_id: uuid.UUID, result: Dict[str, Any]
    ) -> StepExecutionResponse:
        return await self._job.update_job_result(job_id, result)

    async def get_job(self, job_id: uuid.UUID) -> Optional[StepExecutionResponse]:
        return await self._job.get_job(job_id)

    async def list_jobs_for_instance(
        self,
        instance_id: uuid.UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> List[StepExecutionResponse]:
        return await self._job.list_jobs_for_instance(instance_id, skip, limit)

    async def list_jobs_by_status(
        self,
        status: str,
        instance_id: Optional[uuid.UUID] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[StepExecutionResponse]:
        return await self._job.list_jobs_by_status(status, instance_id, skip, limit)

    async def get_instance_statistics(
        self,
        instance_id: uuid.UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> Dict[str, Any]:
        return await self._job.get_instance_statistics(instance_id, skip, limit)

    async def process_approval(
        self,
        instance_id: uuid.UUID,
        step_id: str,
        approved: bool,
        approved_by: Optional[uuid.UUID] = None,
        comment: Optional[str] = None,
    ) -> InstanceResponse:
        return await self._orchestration.process_approval(
            instance_id=instance_id,
            step_id=step_id,
            approved=approved,
            approved_by=approved_by,
            comment=comment,
            get_completed_step_results_fn=self._job.get_completed_step_results,
        )

    async def trigger_manual_step(
        self,
        instance_id: uuid.UUID,
        step_id: str,
        triggered_by: Optional[uuid.UUID] = None,
    ) -> InstanceResponse:
        return await self._orchestration.trigger_manual_step(
            instance_id=instance_id,
            step_id=step_id,
            triggered_by=triggered_by,
            get_completed_step_results_fn=self._job.get_completed_step_results,
        )

    async def resume_with_webhook_callback(
        self,
        instance_id: uuid.UUID,
        step_id: str,
        callback_payload: Dict[str, Any],
    ) -> InstanceResponse:
        return await self._orchestration.resume_with_webhook_callback(
            instance_id=instance_id,
            step_id=step_id,
            callback_payload=callback_payload,
        )

    async def run_stopped_step(
        self,
        instance_id: uuid.UUID,
        step_id: str,
    ) -> StepExecutionResponse:
        return await self._orchestration.run_stopped_step(
            instance_id=instance_id,
            step_id=step_id,
            get_completed_step_results_fn=self._job.get_completed_step_results,
        )

    async def regenerate_resources(
        self,
        instance_id: uuid.UUID,
        step_id: str,
        resource_ids: List[uuid.UUID],
        parameter_overrides: Optional[Dict[str, Any]] = None,
    ) -> StepExecutionResponse:
        return await self._orchestration.regenerate_resources(
            instance_id=instance_id,
            step_id=step_id,
            resource_ids=resource_ids,
            parameter_overrides=parameter_overrides,
            get_completed_step_results_fn=self._job.get_completed_step_results,
        )

    async def regenerate_iteration(
        self,
        instance_id: uuid.UUID,
        step_id: str,
        iteration_index: int,
        parameter_overrides: Optional[Dict[str, Any]] = None,
    ) -> StepExecutionResponse:
        return await self._orchestration.regenerate_iteration(
            instance_id=instance_id,
            step_id=step_id,
            iteration_index=iteration_index,
            parameter_overrides=parameter_overrides,
            get_completed_step_results_fn=self._job.get_completed_step_results,
        )

    async def _get_completed_step_results(
        self, instance: Instance, exclude_steps: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        return await self._job.get_completed_step_results(instance, exclude_steps)

    def _workflow_has_form_inputs(self, workflow_snapshot: Dict[str, Any]) -> bool:
        return self._lifecycle.workflow_has_form_inputs(workflow_snapshot)
