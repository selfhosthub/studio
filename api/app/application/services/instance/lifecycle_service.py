# api/app/application/services/instance/lifecycle_service.py


import uuid
import logging
from typing import Any, Dict, Optional

from app.domain.instance.models import Instance, InstanceStatus
from app.domain.instance.repository import InstanceRepository
from app.domain.instance_step.models import StepExecutionStatus
from app.domain.instance_step.step_execution import StepExecution
from app.domain.instance_step.step_execution_repository import StepExecutionRepository
from app.domain.workflow.repository import WorkflowRepository
from app.domain.provider.repository import (
    ProviderRepository,
    ProviderCredentialRepository,
)
from app.domain.workflow.models import ExecutionMode
from app.domain.common.json_serialization import serialize_steps

from app.application.dtos import InstanceCreate, InstanceResponse
from app.application.interfaces import EventBus, EntityNotFoundError
from app.application.services.instance.helpers import get_instance_or_raise

logger = logging.getLogger(__name__)


class LifecycleService:
    def __init__(
        self,
        instance_repository: InstanceRepository,
        step_execution_repository: StepExecutionRepository,
        workflow_repository: WorkflowRepository,
        event_bus: EventBus,
        provider_repository: ProviderRepository,
        credential_repository: ProviderCredentialRepository,
    ):
        self.instance_repository = instance_repository
        self.step_execution_repository = step_execution_repository
        self.workflow_repository = workflow_repository
        self.event_bus = event_bus
        self.provider_repository = provider_repository
        self.credential_repository = credential_repository

    async def _get_workflow_or_raise(self, workflow_id: uuid.UUID) -> Any:
        workflow = await self.workflow_repository.get_by_id(workflow_id)
        if not workflow:
            raise EntityNotFoundError(
                entity_type="Workflow",
                entity_id=workflow_id,
                code=f"Workflow with ID {workflow_id} not found",
            )
        return workflow

    async def _get_instance_or_raise(self, instance_id: uuid.UUID) -> Instance:
        return await get_instance_or_raise(self.instance_repository, instance_id)

    async def _publish_events(self, aggregate: Instance) -> None:
        events = aggregate.clear_events()
        for event in events:
            await self.event_bus.publish(event)

    async def validate_workflow_credentials(
        self, workflow_id: uuid.UUID, organization_id: uuid.UUID
    ) -> None:
        """Verify required provider credentials exist before instance start.

        OAuth credentials only require a refresh_token to be present; the API
        auto-refreshes access tokens at fetch time.
        """
        from app.domain.provider.models import CredentialType
        from app.domain.common.value_objects import StepTriggerType

        workflow = await self._get_workflow_or_raise(workflow_id)

        # Manual-trigger steps validate credentials at start time, not here.
        # provider_id may be a UUID or an unresolved slug string.
        provider_refs: set[object] = set()
        for _step_id, step_config in workflow.steps.items():
            if step_config.trigger_type == StepTriggerType.MANUAL:
                continue
            if step_config.job and step_config.job.provider_id:
                provider_refs.add(step_config.job.provider_id)

        missing_providers = []
        expired_oauth_providers = []

        for provider_ref in provider_refs:
            if isinstance(provider_ref, uuid.UUID):
                provider = await self.provider_repository.get_by_id(provider_ref)
            else:
                provider = await self.provider_repository.get_by_slug(str(provider_ref))
            provider_id = provider.id if provider else None
            provider_name = provider.name if provider else str(provider_ref)

            # Internal and local-worker providers don't need credentials.
            if provider:
                if provider.provider_type.value == "internal":
                    continue
                if provider.config and provider.config.get("local_worker", {}).get(
                    "enabled"
                ):
                    continue

            if not provider_id:
                missing_providers.append(str(provider_ref))
                continue

            credential = await self.credential_repository.get_default_credential(
                organization_id=organization_id, provider_id=provider_id
            )

            if not credential:
                missing_providers.append(provider_name)
                continue

            if credential.credential_type == CredentialType.OAUTH2:
                refresh_token = credential.credentials.get("refresh_token")
                if not refresh_token:
                    expired_oauth_providers.append(provider_name)

        errors = []
        if missing_providers:
            providers_list = ", ".join(missing_providers)
            errors.append(f"Missing credentials for: {providers_list}")

        if expired_oauth_providers:
            providers_list = ", ".join(expired_oauth_providers)
            errors.append(
                f"OAuth re-authorization required for: {providers_list}. "
                "Please reconnect these providers in Settings → Credentials."
            )

        if errors:
            raise ValueError(f"Cannot start workflow: {' | '.join(errors)}")

    async def create_instance(self, instance_data: InstanceCreate) -> InstanceResponse:
        workflow = await self._get_workflow_or_raise(instance_data.workflow_id)

        workflow.update_instance_count()
        await self.workflow_repository.update(workflow)

        instance = workflow.create_instance(
            user_id=instance_data.user_id,
            input_data=instance_data.input_data or {},
            client_metadata=instance_data.client_metadata or {},
        )

        instance.version = workflow.instance_count

        # Snapshot the workflow definition so reruns are deterministic.
        instance.workflow_snapshot = {
            "workflow_id": str(workflow.id),
            "name": workflow.name,
            "description": workflow.description,
            "execution_mode": workflow.execution_mode.value,
            "version": workflow.version,
            "steps": serialize_steps(workflow.steps),
        }

        if workflow.execution_mode == ExecutionMode.QUEUED:
            instance.status = InstanceStatus.PENDING

        instance = await self.instance_repository.create(instance)

        for step_id, step_config in workflow.steps.items():
            # execution_mode="skip" pre-marks a step as skipped so it doesn't
            # block instance completion validation.
            exec_mode = (step_config.model_extra or {}).get("execution_mode")
            initial_status = (
                StepExecutionStatus.SKIPPED
                if exec_mode == "skip"
                else StepExecutionStatus.PENDING
            )

            step_execution = StepExecution.create(
                instance_id=instance.id,
                step_key=step_id,
                step_name=step_config.name,
                status=initial_status,
                max_retries=step_config.retry_count,
                execution_data={
                    "timeout_seconds": getattr(step_config, "timeout_seconds", None),
                    "on_failure": getattr(step_config, "on_failure", "fail_workflow"),
                    "is_required": getattr(step_config, "is_required", True),
                    "depends_on": list(getattr(step_config, "depends_on", []) or []),
                },
            )
            await self.step_execution_repository.create(step_execution)

        await self.instance_repository.update(instance)
        await self._publish_events(instance)

        return InstanceResponse.from_domain(instance)

    async def start_instance(
        self, instance_id: uuid.UUID, *, skip_validation: bool = False
    ) -> Instance:
        """Validate credentials and transition to running.

        skip_validation=True skips credential checks for paths where they
        were already performed upstream.
        """
        instance = await self._get_instance_or_raise(instance_id)

        if not skip_validation:
            await self.validate_workflow_credentials(
                instance.workflow_id, instance.organization_id
            )

        instance.start()
        instance = await self.instance_repository.update(instance)
        await self._publish_events(instance)

        return instance

    async def complete_instance(
        self, instance_id: uuid.UUID, output_data: Optional[Dict[str, Any]] = None
    ) -> InstanceResponse:
        instance = await self._get_instance_or_raise(instance_id)
        instance.complete(output_data)
        instance = await self.instance_repository.update(instance)
        await self._publish_events(instance)

        return InstanceResponse.from_domain(instance)

    async def fail_instance(
        self, instance_id: uuid.UUID, error_data: Optional[Dict[str, Any]] = None
    ) -> InstanceResponse:
        instance = await self._get_instance_or_raise(instance_id)

        error_message = (
            error_data.get("error_message", "Instance failed")
            if error_data
            else "Instance failed"
        )

        instance.fail(
            error_message=error_message,
            error_data=error_data,
        )

        instance = await self.instance_repository.update(instance)
        await self._publish_events(instance)
        return InstanceResponse.from_domain(instance)

    async def pause_instance(self, instance_id: uuid.UUID) -> InstanceResponse:
        instance = await self._get_instance_or_raise(instance_id)
        instance.pause()
        instance = await self.instance_repository.update(instance)
        await self._publish_events(instance)
        return InstanceResponse.from_domain(instance)

    async def resume_instance(self, instance_id: uuid.UUID) -> InstanceResponse:
        instance = await self._get_instance_or_raise(instance_id)
        instance.resume()
        instance = await self.instance_repository.update(instance)
        await self._publish_events(instance)
        return InstanceResponse.from_domain(instance)

    async def cancel_instance(
        self,
        instance_id: uuid.UUID,
        cancelled_job_responses: list,
    ) -> InstanceResponse:
        """Cancel an instance after its jobs have been cancelled."""
        instance = await self._get_instance_or_raise(instance_id)

        # Cancel is a circuit breaker - force ALL non-terminal steps to CANCELLED.
        # The job-cancel pass only touches PENDING/RUNNING jobs; steps whose jobs
        # are already terminal (e.g. iteration job COMPLETED while step still
        # RUNNING) would be missed if we relied solely on cancelled_job_responses.
        terminal_statuses = {
            StepExecutionStatus.COMPLETED,
            StepExecutionStatus.FAILED,
            StepExecutionStatus.CANCELLED,
        }
        all_steps = await self.step_execution_repository.list_by_instance(instance_id)
        for step_entity in all_steps:
            if step_entity.status not in terminal_statuses:
                try:
                    step_entity.cancel()
                    await self.step_execution_repository.update(step_entity)
                except ValueError:
                    pass
        instance.cancel()
        instance = await self.instance_repository.update(instance)
        await self._publish_events(instance)
        return InstanceResponse.from_domain(instance)

    def workflow_has_form_inputs(self, workflow_snapshot: Dict[str, Any]) -> bool:
        """True if any step has an input_mapping with mappingType='form'."""
        steps = workflow_snapshot.get("steps", {})
        for _step_id, step_config in steps.items():
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

            for _param_key, mapping in input_mappings.items():
                if isinstance(mapping, dict):
                    mapping_type = mapping.get("mappingType") or mapping.get(
                        "mapping_type"
                    )
                    if mapping_type == "form":
                        return True
        return False
