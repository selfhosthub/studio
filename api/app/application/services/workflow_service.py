# api/app/application/services/workflow_service.py

import secrets
import uuid
from typing import Any, Dict, List, Optional

from app.config.settings import settings
from app.application.dtos.workflow_dto import (
    WorkflowCreate,
    WorkflowUpdate,
    WorkflowResponse,
)
from app.application.interfaces.event_bus import EventBus
from app.application.interfaces import EntityNotFoundError
from app.application.interfaces.exceptions import DuplicateEntityError
from app.domain.common.exceptions import BusinessRuleViolation
from app.domain.common.value_objects import StepConfig
from app.domain.provider.repository import ProviderRepository
from app.domain.workflow.models import Workflow, WorkflowScope, WorkflowTriggerType
from app.domain.workflow.repository import WorkflowRepository


class WorkflowService:

    def __init__(
        self,
        workflow_repository: WorkflowRepository,
        event_bus: EventBus,
        provider_repository: Optional[ProviderRepository] = None,
    ):
        self.workflow_repository = workflow_repository
        self.event_bus = event_bus
        self.provider_repository = provider_repository

    async def _get_workflow_or_raise(self, workflow_id: uuid.UUID) -> Workflow:
        workflow = await self.workflow_repository.get_by_id(workflow_id)
        if not workflow:
            raise EntityNotFoundError("Workflow", workflow_id)
        return workflow

    async def _persist_and_publish(self, workflow: Workflow) -> Workflow:
        events = workflow.clear_events()
        workflow = await self.workflow_repository.update(workflow)
        for event in events:
            await self.event_bus.publish(event)
        return workflow

    async def _pin_step_versions(
        self, steps: Dict[str, Dict[str, Any]]
    ) -> Dict[str, Dict[str, Any]]:
        """Pin provider/service versions; core services (no provider_id) are skipped."""
        if not self.provider_repository:
            return steps

        version_cache: Dict[str, Optional[str]] = {}

        for step_config in steps.values():
            if not isinstance(step_config, dict):
                continue
            job = step_config.get("job")
            if not isinstance(job, dict):
                continue

            provider_id_str = step_config.get("provider_id") or job.get("provider_id")
            if not provider_id_str:
                continue

            pid_key = str(provider_id_str)
            if pid_key not in version_cache:
                try:
                    pid = uuid.UUID(pid_key)
                    provider = await self.provider_repository.get_by_id(pid)
                    version_cache[pid_key] = provider.version if provider else None
                except (ValueError, TypeError):
                    version_cache[pid_key] = None

            version = version_cache[pid_key]
            if version is not None and not job.get("provider_version"):
                job["provider_version"] = version
                job["service_version"] = version

        return steps

    async def create_workflow(self, command: WorkflowCreate) -> WorkflowResponse:
        if command.organization_id is None:
            raise ValueError("organization_id is required")

        created_by = command.created_by if command.created_by else uuid.uuid4()
        scope = (
            WorkflowScope(command.scope)
            if command.scope
            else WorkflowScope.ORGANIZATION
        )

        # Check for duplicate workflow name org-wide
        existing = await self.workflow_repository.get_by_name(
            command.organization_id,
            command.name,
        )
        if existing:
            raise DuplicateEntityError(
                entity_type="Workflow", field="name", value=command.name
            )

        # Pin provider versions and convert steps dict to StepConfig if provided
        raw_steps = command.steps
        if raw_steps:
            raw_steps = await self._pin_step_versions(raw_steps)
        steps_dict = None
        if raw_steps:
            steps_dict = {}
            for step_id, step_config_dict in raw_steps.items():
                steps_dict[step_id] = StepConfig(**step_config_dict)

        workflow = Workflow.create(
            name=command.name,
            organization_id=command.organization_id,
            created_by=created_by,
            description=command.description,
            blueprint_id=command.blueprint_id,
            steps=steps_dict,
            trigger_type=(
                command.trigger_type
                if command.trigger_type
                else WorkflowTriggerType.MANUAL
            ),
            client_metadata=command.client_metadata,
            scope=scope,
        )

        # Apply trigger_input_schema if provided (not supported in create, only update)
        if command.trigger_input_schema:
            workflow.update(trigger_input_schema=command.trigger_input_schema)

        events = workflow.clear_events()

        workflow = await self.workflow_repository.create(workflow)

        for event in events:
            await self.event_bus.publish(event)

        return WorkflowResponse.from_domain(workflow)

    async def get_workflow(self, workflow_id: uuid.UUID) -> WorkflowResponse:
        workflow = await self._get_workflow_or_raise(workflow_id)
        return WorkflowResponse.from_domain(workflow)

    async def list_workflows(
        self,
        organization_id: uuid.UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> List[WorkflowResponse]:
        workflows = await self.workflow_repository.list_by_organization(
            organization_id,
            skip=skip,
            limit=limit,
        )
        return [WorkflowResponse.from_domain(w) for w in workflows]

    async def update_workflow(
        self, workflow_id: uuid.UUID, command: WorkflowUpdate
    ) -> WorkflowResponse:
        workflow = await self._get_workflow_or_raise(workflow_id)

        # If name is being changed, check for duplicates org-wide (exclude self)
        if command.name and command.name != workflow.name:
            existing = await self.workflow_repository.get_by_name(
                workflow.organization_id,
                command.name,
                exclude_id=workflow.id,
            )
            if existing:
                raise DuplicateEntityError(
                    entity_type="Workflow", field="name", value=command.name
                )

        # Pin provider versions on steps before saving
        steps_to_save = command.steps
        if steps_to_save is not None:
            steps_to_save = await self._pin_step_versions(steps_to_save)

        # Call domain update method with all parameters, including status
        # Domain method handles version increment when status == ACTIVE
        workflow.update(
            name=command.name,
            description=command.description,
            steps=steps_to_save,
            trigger_type=command.trigger_type,
            client_metadata=command.client_metadata,
            status=command.status,
            trigger_input_schema=command.trigger_input_schema,
            webhook_method=command.webhook_method,
            webhook_auth_type=command.webhook_auth_type,
            webhook_auth_header_name=command.webhook_auth_header_name,
            webhook_auth_header_value=command.webhook_auth_header_value,
            webhook_jwt_secret=command.webhook_jwt_secret,
        )

        workflow = await self._persist_and_publish(workflow)
        return WorkflowResponse.from_domain(workflow)

    async def activate_workflow(
        self, workflow_id: uuid.UUID, activated_by: uuid.UUID
    ) -> WorkflowResponse:
        workflow = await self._get_workflow_or_raise(workflow_id)
        workflow.activate()
        workflow = await self._persist_and_publish(workflow)
        return WorkflowResponse.from_domain(workflow)

    async def deactivate_workflow(
        self, workflow_id: uuid.UUID, deactivated_by: uuid.UUID
    ) -> WorkflowResponse:
        workflow = await self._get_workflow_or_raise(workflow_id)
        workflow.deactivate()
        workflow = await self._persist_and_publish(workflow)
        return WorkflowResponse.from_domain(workflow)

    async def add_step(
        self,
        workflow_id: uuid.UUID,
        step_id: str,
        step_config: Dict[str, Any],
        added_by: uuid.UUID,
    ) -> WorkflowResponse:
        workflow = await self._get_workflow_or_raise(workflow_id)
        config = StepConfig(**step_config)
        workflow.add_step(step_id=step_id, step_config=config)
        workflow = await self._persist_and_publish(workflow)
        return WorkflowResponse.from_domain(workflow)

    async def remove_step(
        self, workflow_id: uuid.UUID, step_id: str, removed_by: uuid.UUID
    ) -> WorkflowResponse:
        workflow = await self._get_workflow_or_raise(workflow_id)
        workflow.remove_step(step_id)
        workflow = await self._persist_and_publish(workflow)
        return WorkflowResponse.from_domain(workflow)

    async def update_step(
        self,
        workflow_id: uuid.UUID,
        step_id: str,
        step_config: Dict[str, Any],
        updated_by: uuid.UUID,
    ) -> WorkflowResponse:
        workflow = await self._get_workflow_or_raise(workflow_id)
        config = StepConfig(**step_config)
        workflow.remove_step(step_id)
        workflow.add_step(step_id=step_id, step_config=config)
        workflow = await self._persist_and_publish(workflow)
        return WorkflowResponse.from_domain(workflow)

    async def delete_workflow(self, workflow_id: uuid.UUID) -> bool:
        # Workflow must be INACTIVE, ARCHIVED, or DRAFT - domain enforces this.
        workflow = await self._get_workflow_or_raise(workflow_id)
        workflow.validate_can_be_deleted()
        return await self.workflow_repository.delete(workflow_id)

    async def generate_webhook_token(self, workflow_id: uuid.UUID) -> Dict[str, str]:
        workflow = await self._get_workflow_or_raise(workflow_id)
        token, secret = workflow.generate_webhook_token()
        await self.workflow_repository.update(workflow)
        return {"token": token, "secret": secret}

    async def regenerate_webhook_token(self, workflow_id: uuid.UUID) -> Dict[str, str]:
        workflow = await self._get_workflow_or_raise(workflow_id)
        token, secret = workflow.regenerate_webhook_token()
        await self.workflow_repository.update(workflow)
        return {"token": token, "secret": secret}

    async def clear_webhook_token(self, workflow_id: uuid.UUID) -> None:
        workflow = await self._get_workflow_or_raise(workflow_id)
        workflow.clear_webhook_token()
        await self.workflow_repository.update(workflow)

    async def generate_step_webhook_token(
        self, workflow_id: uuid.UUID, step_id: str
    ) -> Dict[str, str]:
        # Token and secret stored in step.client_metadata; used by core.webhook_wait callbacks.
        workflow = await self._get_workflow_or_raise(workflow_id)

        if step_id not in workflow.steps:
            raise EntityNotFoundError("Step", step_id)

        step_config = workflow.steps[step_id]

        # Check if token already exists
        if step_config.client_metadata.get("webhook_token"):
            raise BusinessRuleViolation(
                message="Step webhook token already exists. Use regenerate to replace it.",
                code="TOKEN_EXISTS",
                context={"workflow_id": str(workflow_id), "step_id": step_id},
            )

        # Generate token and secret
        token = secrets.token_urlsafe(settings.WEBHOOK_TOKEN_LENGTH)
        secret = secrets.token_urlsafe(settings.WEBHOOK_SECRET_LENGTH)
        step_config.client_metadata["webhook_token"] = token
        step_config.client_metadata["webhook_secret"] = secret

        await self.workflow_repository.update(workflow)

        return {"token": token, "secret": secret}

    async def regenerate_step_webhook_token(
        self, workflow_id: uuid.UUID, step_id: str
    ) -> Dict[str, str]:
        workflow = await self._get_workflow_or_raise(workflow_id)

        if step_id not in workflow.steps:
            raise EntityNotFoundError("Step", step_id)

        step_config = workflow.steps[step_id]

        # Check if token exists
        if not step_config.client_metadata.get("webhook_token"):
            raise BusinessRuleViolation(
                message="No step webhook token exists. Use generate first.",
                code="NO_TOKEN",
                context={"workflow_id": str(workflow_id), "step_id": step_id},
            )

        # Generate new token and secret
        token = secrets.token_urlsafe(settings.WEBHOOK_TOKEN_LENGTH)
        secret = secrets.token_urlsafe(settings.WEBHOOK_SECRET_LENGTH)
        step_config.client_metadata["webhook_token"] = token
        step_config.client_metadata["webhook_secret"] = secret

        await self.workflow_repository.update(workflow)

        return {"token": token, "secret": secret}

    async def get_step_webhook_token(
        self, workflow_id: uuid.UUID, step_id: str
    ) -> Dict[str, str | None]:
        workflow = await self._get_workflow_or_raise(workflow_id)

        if step_id not in workflow.steps:
            raise EntityNotFoundError("Step", step_id)

        step_config = workflow.steps[step_id]
        return {
            "token": step_config.client_metadata.get("webhook_token"),
            "secret": step_config.client_metadata.get("webhook_secret"),
        }

    async def copy_workflow(
        self,
        workflow_id: uuid.UUID,
        user_id: uuid.UUID,
        organization_id: uuid.UUID,
        target_scope: str = "personal",
    ) -> WorkflowResponse:
        source = await self._get_workflow_or_raise(workflow_id)

        # Serialize steps for deep copy
        steps_dict = None
        if source.steps:
            steps_dict = {}
            for step_id, step_config in source.steps.items():
                steps_dict[step_id] = step_config.model_dump(mode="json")

        # Handle name collision
        copy_name = f"{source.name} (copy)"
        existing = await self.workflow_repository.get_by_name(
            organization_id, copy_name
        )
        if existing:
            counter = 2
            while True:
                copy_name = f"{source.name} (copy {counter})"
                existing = await self.workflow_repository.get_by_name(
                    organization_id, copy_name
                )
                if not existing:
                    break
                counter += 1

        command = WorkflowCreate(
            name=copy_name,
            description=source.description,
            organization_id=organization_id,
            created_by=user_id,
            blueprint_id=source.blueprint_id,
            steps=steps_dict,
            trigger_type=source.trigger_type,
            trigger_input_schema=source.trigger_input_schema,
            client_metadata={
                **(source.client_metadata or {}),
                "copied_from": str(source.id),
            },
            scope=target_scope,
        )
        return await self.create_workflow(command)

    async def request_publish(
        self, workflow_id: uuid.UUID, user_id: uuid.UUID
    ) -> WorkflowResponse:
        workflow = await self._get_workflow_or_raise(workflow_id)
        if workflow.created_by != user_id:
            raise BusinessRuleViolation(
                message="Only the workflow owner can request publishing",
                code="NOT_OWNER",
                context={
                    "workflow_id": str(workflow_id),
                    "created_by": str(workflow.created_by),
                    "user_id": str(user_id),
                },
            )
        workflow.request_publish()
        workflow = await self._persist_and_publish(workflow)
        return WorkflowResponse.from_domain(workflow)

    async def approve_publish(self, workflow_id: uuid.UUID) -> WorkflowResponse:
        workflow = await self._get_workflow_or_raise(workflow_id)

        # Check name won't collide with existing org workflows
        existing = await self.workflow_repository.get_by_name(
            workflow.organization_id,
            workflow.name,
            exclude_id=workflow.id,
        )
        if existing:
            raise DuplicateEntityError(
                entity_type="Workflow", field="name", value=workflow.name
            )

        workflow.approve_publish()
        workflow = await self._persist_and_publish(workflow)
        return WorkflowResponse.from_domain(workflow)

    async def reject_publish(self, workflow_id: uuid.UUID) -> WorkflowResponse:
        workflow = await self._get_workflow_or_raise(workflow_id)
        workflow.reject_publish()
        workflow = await self._persist_and_publish(workflow)
        return WorkflowResponse.from_domain(workflow)

    async def import_workflow(
        self,
        data: Dict[str, Any],
        organization_id: uuid.UUID,
        provider_repo: Any = None,  # Optional ProviderRepository for validation
        prompt_repo: Any = None,  # Optional PromptRepository for validation
    ) -> tuple[WorkflowResponse, List[str]]:
        # Validate required fields. BusinessRuleViolation is allowlisted by
        # safe_error_message, so the user-facing message is preserved.
        # ValueError would be masked to type-name-only.
        if "name" not in data:
            raise BusinessRuleViolation(
                "Workflow export must contain 'name' field"
            )
        if "steps" not in data:
            raise BusinessRuleViolation(
                "Workflow export must contain 'steps' field"
            )

        warnings: List[str] = []

        # Check provider compatibility if repo provided
        steps = data.get("steps", {})
        if provider_repo:
            for step_id, step_config in steps.items():
                if not isinstance(step_config, dict):
                    continue
                job = step_config.get("job", {})
                if not isinstance(job, dict):
                    job = {}
                # Step level takes precedence over job level.
                provider_id_str = step_config.get("provider_id") or job.get(
                    "provider_id"
                )
                if provider_id_str:
                    try:
                        provider_id = uuid.UUID(provider_id_str)
                        provider = await provider_repo.get_by_id(provider_id)
                        if not provider:
                            warnings.append(
                                f"Step '{step_id}': Provider {provider_id_str} not found"
                            )
                    except (ValueError, TypeError):
                        warnings.append(f"Step '{step_id}': Invalid provider_id format")

        # Check AI agent prompt availability if repo provided
        if prompt_repo:
            for step_id, step_config in steps.items():
                if not isinstance(step_config, dict):
                    continue
                input_mappings = step_config.get("input_mappings", {})
                if not isinstance(input_mappings, dict):
                    continue
                for _param, mapping in input_mappings.items():
                    if not isinstance(mapping, dict):
                        continue
                    if mapping.get("mappingType") != "prompt":
                        continue
                    prompt_id_str = mapping.get("promptId")
                    if not prompt_id_str:
                        warnings.append(
                            f"Step '{step_id}': No AI agent prompt selected"
                        )
                        continue
                    try:
                        prompt_id = uuid.UUID(prompt_id_str)
                        prompt = await prompt_repo.get_by_id(prompt_id)
                        if not prompt:
                            warnings.append(
                                f"Step '{step_id}': AI agent prompt {prompt_id_str} not found"
                            )
                    except (ValueError, TypeError):
                        warnings.append(
                            f"Step '{step_id}': Invalid AI agent prompt ID format"
                        )

        # Handle name collision
        workflow_name = data["name"]
        existing = await self.workflow_repository.list_by_organization(
            organization_id, skip=0, limit=settings.DEFAULT_FETCH_LIMIT
        )
        existing_names = {w.name for w in existing}
        if workflow_name in existing_names:
            workflow_name = f"{workflow_name} (imported)"
            counter = 2
            while workflow_name in existing_names:
                workflow_name = f"{data['name']} (imported {counter})"
                counter += 1

        # Parse trigger type
        trigger_type_str = data.get("trigger_type", "manual")
        try:
            trigger_type = WorkflowTriggerType(trigger_type_str.lower())
        except ValueError:
            trigger_type = WorkflowTriggerType.MANUAL

        # Create workflow
        workflow_create = WorkflowCreate(
            name=workflow_name,
            description=data.get("description"),
            organization_id=organization_id,
            trigger_type=trigger_type,
            steps=steps,
            trigger_input_schema=data.get("trigger_input_schema"),
            client_metadata=data.get("client_metadata"),
        )

        created_workflow = await self.create_workflow(workflow_create)
        return created_workflow, warnings
