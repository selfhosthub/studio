# api/app/domain/workflow/models.py

"""Domain models for the workflow context."""
import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from pydantic import ConfigDict, Field, field_validator

from app.config.settings import settings
from app.domain.common.base_entity import AggregateRoot
from app.domain.common.exceptions import (
    InvalidStateTransition,
    BusinessRuleViolation,
    ValidationError as DomainValidationError,
)
from app.domain.common.value_objects import JobConfig, StepConfig, StepType
from app.domain.workflow.events import (
    WorkflowActivatedEvent,
    WorkflowCreatedEvent,
    WorkflowDeactivatedEvent,
    WorkflowStepAddedEvent,
    WorkflowStepRemovedEvent,
    WorkflowUpdatedEvent,
)


class PublishStatus(str, Enum):
    """Workflow publish status."""

    PENDING = "pending"
    REJECTED = "rejected"


class WorkflowScope(str, Enum):
    """Visibility scope of a workflow."""

    PERSONAL = "personal"
    ORGANIZATION = "organization"


class WorkflowStatus(str, Enum):
    """Status of a workflow."""

    DRAFT = "draft"
    ACTIVE = "active"
    INACTIVE = "inactive"
    ARCHIVED = "archived"
    DEBUG = "debug"  # Instances auto-pause after each step for debugging


class WorkflowTriggerType(str, Enum):
    """How a workflow is triggered."""

    MANUAL = "manual"
    SCHEDULE = "schedule"
    WEBHOOK = "webhook"
    EVENT = "event"
    API = "api"


class WorkflowPriority(str, Enum):
    """Workflow execution priority."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


class ExecutionMode(str, Enum):
    """Workflow execution mode."""

    IMMEDIATE = "immediate"  # Execute synchronously, return result immediately
    QUEUED = "queued"  # Queue for async worker processing (default)


class Workflow(AggregateRoot):
    """Aggregate root for a configured workflow definition. Instantiated from blueprints; executable multiple times."""

    name: str
    description: Optional[str] = None
    organization_id: uuid.UUID
    blueprint_id: Optional[uuid.UUID] = None
    blueprint_name: Optional[str] = None
    blueprint_version: Optional[int] = None
    status: WorkflowStatus = WorkflowStatus.DRAFT
    steps: Dict[str, StepConfig] = Field(default_factory=dict)
    trigger_type: WorkflowTriggerType = WorkflowTriggerType.MANUAL
    priority: WorkflowPriority = WorkflowPriority.NORMAL
    execution_mode: ExecutionMode = ExecutionMode.QUEUED
    client_metadata: Dict[str, Any] = Field(default_factory=dict)
    tags: List[str] = Field(default_factory=list)
    version: int = 1
    instance_count: int = 0
    last_instance_at: Optional[datetime] = None
    created_by: uuid.UUID
    scope: WorkflowScope = WorkflowScope.ORGANIZATION
    publish_status: Optional[PublishStatus] = None
    max_concurrent_instances: Optional[int] = None
    webhook_token: Optional[str] = None  # Secure token for webhook trigger URL
    webhook_secret: Optional[str] = None  # HMAC signing secret for webhook verification
    webhook_method: str = "POST"  # HTTP method for webhook trigger (POST or GET)
    webhook_auth_type: str = "none"  # Auth type: "none", "header", "jwt", "hmac"
    webhook_auth_header_name: Optional[str] = (
        None  # Header name for header auth (e.g., "X-API-Key")
    )
    webhook_auth_header_value: Optional[str] = (
        None  # Header value for header auth (encrypted)
    )
    webhook_jwt_secret: Optional[str] = None  # JWT signing secret for jwt auth (HS256)
    trigger_input_schema: Optional[Dict[str, Any]] = (
        None  # Schema for expected trigger payload fields
    )

    model_config = ConfigDict(arbitrary_types_allowed=True)

    @field_validator("status", mode="before")
    @classmethod
    def convert_status_to_enum(cls, v):
        if isinstance(v, str) and not isinstance(v, WorkflowStatus):
            return WorkflowStatus(v)
        return v

    @field_validator("scope", mode="before")
    @classmethod
    def convert_scope_to_enum(cls, v):
        if isinstance(v, str) and not isinstance(v, WorkflowScope):
            return WorkflowScope(v)
        return v

    @classmethod
    def create(
        cls,
        name: str,
        organization_id: uuid.UUID,
        created_by: uuid.UUID,
        description: Optional[str] = None,
        blueprint_id: Optional[uuid.UUID] = None,
        blueprint_version: Optional[int] = None,
        steps: Optional[Dict[str, StepConfig]] = None,
        trigger_type: WorkflowTriggerType = WorkflowTriggerType.MANUAL,
        priority: WorkflowPriority = WorkflowPriority.NORMAL,
        execution_mode: ExecutionMode = ExecutionMode.QUEUED,
        client_metadata: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None,
        scope: WorkflowScope = WorkflowScope.ORGANIZATION,
    ) -> "Workflow":
        workflow = cls(
            name=name,
            description=description,
            organization_id=organization_id,
            blueprint_id=blueprint_id,
            blueprint_version=blueprint_version,
            steps=steps or {},
            trigger_type=trigger_type,
            priority=priority,
            execution_mode=execution_mode,
            client_metadata=client_metadata or {},
            tags=tags or [],
            created_by=created_by,
            scope=scope,
            status=WorkflowStatus.DRAFT,
        )

        workflow.add_event(
            WorkflowCreatedEvent(
                aggregate_id=workflow.id,
                aggregate_type="workflow",
                workflow_id=workflow.id,
                organization_id=organization_id,
                name=name,
                description=description,
                created_by=created_by,
                data={
                    "blueprint_id": str(blueprint_id) if blueprint_id else None,
                    "trigger_type": trigger_type.value,
                },
            )
        )

        return workflow

    def update(
        self,
        name: Optional[str] = None,
        description: Optional[str] = None,
        steps: Optional[Dict[str, Dict[str, Any]]] = None,
        trigger_type: Optional[WorkflowTriggerType] = None,
        priority: Optional[WorkflowPriority] = None,
        execution_mode: Optional[ExecutionMode] = None,
        client_metadata: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None,
        status: Optional[WorkflowStatus] = None,
        trigger_input_schema: Optional[Dict[str, Any]] = None,
        webhook_method: Optional[str] = None,
        webhook_auth_type: Optional[str] = None,
        webhook_auth_header_name: Optional[str] = None,
        webhook_auth_header_value: Optional[str] = None,
        webhook_jwt_secret: Optional[str] = None,
    ) -> None:
        """Update workflow properties. Rejects ARCHIVED workflows; requires steps when activating."""
        if self.status == WorkflowStatus.ARCHIVED:
            raise InvalidStateTransition(
                message="Cannot update an archived workflow",
                code="CANNOT_UPDATE_ARCHIVED",
                context={
                    "workflow_id": str(self.id),
                },
            )

        # If transitioning to ACTIVE, validate business rules
        if status == WorkflowStatus.ACTIVE:
            if not self.steps:
                raise BusinessRuleViolation(
                    message="Cannot activate workflow without steps",
                    code="NO_STEPS",
                    context={
                        "workflow_id": str(self.id),
                    },
                )
            if not self._validate_step_dependencies():
                raise BusinessRuleViolation(
                    message="Workflow has invalid step dependencies",
                    code="INVALID_DEPENDENCIES",
                    context={
                        "workflow_id": str(self.id),
                    },
                )

        if name is not None:
            self.name = name
        if description is not None:
            self.description = description
        if steps is not None:
            # Deserialize steps from dictionary to StepConfig objects
            from app.domain.common.json_serialization import deserialize_steps

            self.steps = deserialize_steps(steps)
        if trigger_type is not None:
            self.trigger_type = trigger_type
        if priority is not None:
            self.priority = priority
        if execution_mode is not None:
            self.execution_mode = execution_mode
        if client_metadata is not None:
            self.client_metadata.update(client_metadata)
        if tags is not None:
            self.tags = tags
        if trigger_input_schema is not None:
            self.trigger_input_schema = trigger_input_schema
        if webhook_method is not None:
            self.webhook_method = webhook_method
        if webhook_auth_type is not None:
            self.webhook_auth_type = webhook_auth_type
        if webhook_auth_header_name is not None:
            self.webhook_auth_header_name = webhook_auth_header_name
        if webhook_auth_header_value is not None:
            self.webhook_auth_header_value = webhook_auth_header_value
        if webhook_jwt_secret is not None:
            self.webhook_jwt_secret = webhook_jwt_secret

        # Increment version when status becomes/remains ACTIVE
        # This creates an audit trail for active releases
        if status and status == WorkflowStatus.ACTIVE:
            self.version += 1

        if status is not None:
            self.status = status

        self.updated_at = datetime.now(UTC)

        self.add_event(
            WorkflowUpdatedEvent(
                aggregate_id=self.id,
                aggregate_type="workflow",
                workflow_id=self.id,
                organization_id=self.organization_id,
                name=self.name,
                description=self.description,
            )
        )

    def add_step(self, step_id: str, step_config: StepConfig) -> None:
        """Add a step. Rejects active workflows, duplicate step IDs, missing deps, and cycles."""
        if self.status == WorkflowStatus.ACTIVE:
            raise InvalidStateTransition(
                message="Cannot add step to active workflow",
                code="WORKFLOW_ACTIVE",
                context={
                    "workflow_id": str(self.id),
                    "current_status": self.status.value,
                },
            )

        if step_id in self.steps:
            raise DomainValidationError(
                message=f"Step {step_id} already exists in workflow",
                code="STEP_ALREADY_EXISTS",
                context={
                    "workflow_id": str(self.id),
                    "step_id": step_id,
                },
            )

        for dep_id in step_config.depends_on:
            if dep_id not in self.steps:
                raise DomainValidationError(
                    message=f"Dependency {dep_id} does not exist",
                    code="DEPENDENCY_NOT_FOUND",
                    context={
                        "workflow_id": str(self.id),
                        "step_id": step_id,
                        "missing_dependency": dep_id,
                    },
                )

        if self._would_create_cycle(step_id, step_config.depends_on):
            raise DomainValidationError(
                message="Adding step would create a dependency cycle",
                code="CIRCULAR_DEPENDENCY",
                context={
                    "workflow_id": str(self.id),
                    "step_id": step_id,
                    "dependencies": step_config.depends_on,
                },
            )

        self.steps[step_id] = step_config
        self.updated_at = datetime.now(UTC)

        step_type_value = step_config.step_type.value if step_config.step_type else None
        self.add_event(
            WorkflowStepAddedEvent(
                aggregate_id=self.id,
                aggregate_type="workflow",
                workflow_id=self.id,
                organization_id=self.organization_id,
                step_id=step_id,
                step_name=step_config.name,
                step_type=step_type_value,
                data={
                    "step_id": step_id,
                    "step_name": step_config.name,
                    "step_type": step_type_value,
                },
            )
        )

    def add_step_from_dict(
        self, step_id: str, step_config_dict: Dict[str, Any]
    ) -> None:
        from app.domain.common.converters import dict_to_step_config

        step_config = dict_to_step_config(step_config_dict)
        self.add_step(step_id, step_config)

    def remove_step(self, step_id: str) -> None:
        """Remove a step. Rejects active workflows, missing step IDs, and steps with dependents."""
        if self.status == WorkflowStatus.ACTIVE:
            raise InvalidStateTransition(
                message="Cannot remove step from active workflow",
                code="WORKFLOW_ACTIVE",
                context={
                    "workflow_id": str(self.id),
                    "current_status": self.status.value,
                },
            )

        if step_id not in self.steps:
            raise DomainValidationError(
                message=f"Step {step_id} does not exist in workflow",
                code="STEP_NOT_FOUND",
                context={
                    "workflow_id": str(self.id),
                    "step_id": step_id,
                },
            )

        dependent_steps = self.get_dependent_steps(step_id)
        if dependent_steps:
            raise DomainValidationError(
                message=f"Cannot remove step {step_id}: other steps depend on it",
                code="STEP_HAS_DEPENDENTS",
                context={
                    "workflow_id": str(self.id),
                    "step_id": step_id,
                    "dependent_steps": dependent_steps,
                },
            )

        del self.steps[step_id]
        self.updated_at = datetime.now(UTC)

        self.add_event(
            WorkflowStepRemovedEvent(
                aggregate_id=self.id,
                aggregate_type="workflow",
                workflow_id=self.id,
                organization_id=self.organization_id,
                step_id=step_id,
                data={
                    "step_id": step_id,
                },
            )
        )

    def activate(self) -> None:
        """Activate. Rejects already-active, archived, stepless, or invalid-dependency workflows."""
        if self.status == WorkflowStatus.ACTIVE:
            raise InvalidStateTransition(
                message="Workflow is already active",
                code="WORKFLOW_ALREADY_ACTIVE",
                context={
                    "workflow_id": str(self.id),
                    "current_status": self.status.value,
                },
            )

        if not self.steps:
            raise BusinessRuleViolation(
                message="Cannot activate workflow without steps",
                code="NO_STEPS",
                context={
                    "workflow_id": str(self.id),
                },
            )

        if self.status == WorkflowStatus.ARCHIVED:
            raise InvalidStateTransition(
                message="Cannot activate archived workflow",
                code="WORKFLOW_ARCHIVED",
                context={
                    "workflow_id": str(self.id),
                    "current_status": self.status.value,
                },
            )

        if not self._validate_step_dependencies():
            raise BusinessRuleViolation(
                message="Workflow has invalid step dependencies",
                code="INVALID_DEPENDENCIES",
                context={
                    "workflow_id": str(self.id),
                },
            )

        self.status = WorkflowStatus.ACTIVE
        self.updated_at = datetime.now(UTC)

        self.add_event(
            WorkflowActivatedEvent(
                aggregate_id=self.id,
                aggregate_type="workflow",
                workflow_id=self.id,
                organization_id=self.organization_id,
                activated_by=self.created_by,
                data={
                    "step_count": len(self.steps),
                },
            )
        )

    def deactivate(self) -> None:
        """Deactivate. Rejects already-inactive workflows."""
        if self.status == WorkflowStatus.INACTIVE:
            raise InvalidStateTransition(
                message="Workflow is already inactive",
                code="WORKFLOW_ALREADY_INACTIVE",
                context={
                    "workflow_id": str(self.id),
                    "current_status": self.status.value,
                },
            )

        self.status = WorkflowStatus.INACTIVE
        self.updated_at = datetime.now(UTC)

        self.add_event(
            WorkflowDeactivatedEvent(
                aggregate_id=self.id,
                aggregate_type="workflow",
                workflow_id=self.id,
                organization_id=self.organization_id,
                deactivated_by=self.created_by,
            )
        )

    def archive(self) -> None:
        """Archive the workflow."""
        self.status = WorkflowStatus.ARCHIVED
        self.updated_at = datetime.now(UTC)

    def generate_webhook_token(self) -> tuple[str, str]:
        """Generate token + HMAC secret. Raises if a token already exists; use regenerate to replace."""
        if self.webhook_token:
            raise BusinessRuleViolation(
                message="Webhook token already exists. Use regenerate_webhook_token() to replace it.",
                code="TOKEN_EXISTS",
                context={"workflow_id": str(self.id)},
            )

        import secrets

        self.webhook_token = secrets.token_urlsafe(24)  # 32 characters
        self.webhook_secret = secrets.token_urlsafe(32)  # 43 characters for HMAC
        self.trigger_type = WorkflowTriggerType.WEBHOOK
        self.updated_at = datetime.now(UTC)
        return (self.webhook_token, self.webhook_secret)

    def regenerate_webhook_token(self) -> tuple[str, str]:
        """Rotate token + HMAC secret. Raises if no token exists yet; use generate first."""
        if not self.webhook_token:
            raise BusinessRuleViolation(
                message="No webhook token exists. Use generate_webhook_token() first.",
                code="NO_TOKEN",
                context={"workflow_id": str(self.id)},
            )

        import secrets

        self.webhook_token = secrets.token_urlsafe(24)  # 32 characters
        self.webhook_secret = secrets.token_urlsafe(32)  # 43 characters for HMAC
        self.updated_at = datetime.now(UTC)
        return (self.webhook_token, self.webhook_secret)

    def clear_webhook_token(self) -> None:
        """Remove the webhook token and secret from this workflow."""
        self.webhook_token = None
        self.webhook_secret = None
        if self.trigger_type == WorkflowTriggerType.WEBHOOK:
            self.trigger_type = WorkflowTriggerType.MANUAL
        self.updated_at = datetime.now(UTC)

    def request_publish(self) -> None:
        """Request publishing a personal workflow to the organization.

        Raises:
            BusinessRuleViolation: If not personal scope or already pending.
        """
        if self.scope != WorkflowScope.PERSONAL:
            raise BusinessRuleViolation(
                message="Only personal workflows can be published to the organization",
                code="NOT_PERSONAL_SCOPE",
                context={"workflow_id": str(self.id), "scope": self.scope.value},
            )
        if self.publish_status == PublishStatus.PENDING:
            raise BusinessRuleViolation(
                message="Workflow is already pending publish approval",
                code="ALREADY_PENDING",
                context={"workflow_id": str(self.id)},
            )
        self.publish_status = PublishStatus.PENDING
        self.updated_at = datetime.now(UTC)

    def approve_publish(self) -> None:
        """Admin approves publishing. Scope flips to organization.

        Raises:
            BusinessRuleViolation: If not pending approval.
        """
        if self.publish_status != PublishStatus.PENDING:
            raise BusinessRuleViolation(
                message="Workflow is not pending publish approval",
                code="NOT_PENDING",
                context={
                    "workflow_id": str(self.id),
                    "publish_status": self.publish_status,
                },
            )
        self.scope = WorkflowScope.ORGANIZATION
        self.publish_status = None
        self.updated_at = datetime.now(UTC)

    def reject_publish(self) -> None:
        """Admin rejects publishing. Stays personal, status set to rejected.

        Raises:
            BusinessRuleViolation: If not pending approval.
        """
        if self.publish_status != PublishStatus.PENDING:
            raise BusinessRuleViolation(
                message="Workflow is not pending publish approval",
                code="NOT_PENDING",
                context={
                    "workflow_id": str(self.id),
                    "publish_status": self.publish_status,
                },
            )
        self.publish_status = PublishStatus.REJECTED
        self.updated_at = datetime.now(UTC)

    def can_be_deleted(self) -> bool:
        """True when status is INACTIVE, ARCHIVED, or DRAFT (ACTIVE blocks deletion)."""
        return self.status in (
            WorkflowStatus.INACTIVE,
            WorkflowStatus.ARCHIVED,
            WorkflowStatus.DRAFT,
        )

    def validate_can_be_deleted(self) -> None:
        """Raises if status is ACTIVE."""
        if self.status == WorkflowStatus.ACTIVE:
            raise BusinessRuleViolation(
                message="Cannot delete active workflow. Deactivate it first.",
                code="WORKFLOW_ACTIVE",
                context={
                    "workflow_id": str(self.id),
                    "current_status": self.status.value,
                },
            )

    def create_instance(
        self,
        user_id: Optional[uuid.UUID] = None,
        input_data: Optional[Dict[str, Any]] = None,
        client_metadata: Optional[Dict[str, Any]] = None,
    ):
        """Factory method for instances. ACTIVE and DEBUG are allowed; all other statuses raise."""
        # Allow ACTIVE and DEBUG workflows to create instances
        if self.status not in (WorkflowStatus.ACTIVE, WorkflowStatus.DEBUG):
            raise BusinessRuleViolation(
                message=f"Cannot create instance from {self.status.value} workflow",
                code="WORKFLOW_NOT_ACTIVE",
                context={
                    "workflow_id": str(self.id),
                    "current_status": self.status.value,
                },
            )

        from app.domain.instance.models import Instance

        return Instance.create(
            workflow_id=self.id,
            organization_id=self.organization_id,
            user_id=user_id,
            input_data=input_data,
            client_metadata=client_metadata,
            is_debug_mode=(self.status == WorkflowStatus.DEBUG),
        )

    def update_instance_count(self) -> None:
        """Increment the instance count and update last instance time."""
        self.instance_count += 1
        self.last_instance_at = datetime.now(UTC)
        self.updated_at = datetime.now(UTC)

    def get_step_dependencies(self, step_id: str) -> List[str]:
        if step_id not in self.steps:
            return []
        return self.steps[step_id].depends_on

    def get_dependent_steps(self, step_id: str) -> List[str]:
        dependents: List[str] = []
        for sid in self.steps:
            step = self.steps[sid]
            if step_id in step.depends_on:
                dependents.append(sid)
        return dependents

    def validate_dependencies(self) -> bool:
        return self._validate_step_dependencies()

    def can_execute(self) -> bool:
        return (
            self.status == WorkflowStatus.ACTIVE
            and len(self.steps) > 0
            and self.validate_dependencies()
        )

    def _validate_step_dependencies(self) -> bool:
        """True when all deps resolve and the dependency graph is acyclic."""
        for step_id, step_config in self.steps.items():
            for dep_id in step_config.depends_on:
                if dep_id == "__instance_form__":
                    continue  # virtual step, not a real dependency
                if dep_id not in self.steps:
                    return False

        visited: Set[str] = set()
        path: Set[str] = set()

        def has_cycle(node: str) -> bool:
            if node in path:
                return True
            if node in visited:
                return False

            visited.add(node)
            path.add(node)

            if node in self.steps:
                for dep in self.steps[node].depends_on:
                    if has_cycle(dep):
                        return True

            path.remove(node)
            return False

        for step_id in self.steps:
            if has_cycle(step_id):
                return False

        return True

    def _would_create_cycle(self, step_id: str, new_dependencies: List[str]) -> bool:
        """True if applying new_dependencies to step_id would introduce a cycle."""
        temp_deps = dict(self.steps)
        temp_config = self.steps.get(step_id)
        if temp_config:
            temp_deps[step_id] = StepConfig(
                name=temp_config.name,
                description=temp_config.description,
                step_type=temp_config.step_type,
                job=temp_config.job,
                depends_on=new_dependencies,
                timeout_seconds=temp_config.timeout_seconds,
                retry_count=temp_config.retry_count,
                retry_delay_seconds=temp_config.retry_delay_seconds,
                is_required=temp_config.is_required,
                on_failure=temp_config.on_failure,
                condition=temp_config.condition,
                client_metadata=temp_config.client_metadata,
            )
        else:
            temp_deps[step_id] = StepConfig(
                name="temp",
                description=None,
                step_type=StepType.TASK,
                job=None,
                depends_on=new_dependencies,
                timeout_seconds=None,
                retry_count=settings.STEP_DEFAULT_RETRY_COUNT,
                retry_delay_seconds=settings.STEP_DEFAULT_RETRY_DELAY,
                is_required=True,
                on_failure="fail_workflow",
                condition=None,
                client_metadata={},
            )

        visited: Set[str] = set()
        path: Set[str] = set()

        def has_cycle(node: str) -> bool:
            if node in path:
                return True
            if node in visited:
                return False

            visited.add(node)
            path.add(node)

            step = temp_deps[node]
            for dep in step.depends_on:
                if dep in temp_deps and has_cycle(dep):
                    return True

            path.remove(node)
            return False

        for step in temp_deps:
            if has_cycle(step):
                return True

        return False

    @staticmethod
    def _parse_status(status: str) -> WorkflowStatus:
        """Parse string to WorkflowStatus enum."""
        return WorkflowStatus(status)


class WorkflowBuilder:
    """Builder for constructing workflows with fluent API."""

    def __init__(
        self,
        name: str,
        organization_id: uuid.UUID,
        created_by: uuid.UUID,
    ):
        self.workflow = Workflow.create(
            name=name,
            organization_id=organization_id,
            created_by=created_by,
        )
        self.last_step_id: Optional[str] = None

    def with_description(self, description: str) -> "WorkflowBuilder":
        self.workflow.description = description
        return self

    def with_blueprint(
        self, blueprint_id: uuid.UUID, blueprint_version: int
    ) -> "WorkflowBuilder":
        self.workflow.blueprint_id = blueprint_id
        self.workflow.blueprint_version = blueprint_version
        return self

    def with_trigger(self, trigger_type: WorkflowTriggerType) -> "WorkflowBuilder":
        self.workflow.trigger_type = trigger_type
        return self

    def with_priority(self, priority: WorkflowPriority) -> "WorkflowBuilder":
        self.workflow.priority = priority
        return self

    def add_step(
        self,
        step_id: str,
        name: str,
        provider_id: uuid.UUID,
        service_id: str,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> "WorkflowBuilder":
        dependencies = [self.last_step_id] if self.last_step_id else []

        job_config = JobConfig(
            provider_id=provider_id,
            service_id=service_id,
            parameters=parameters or {},
        )

        step_config = StepConfig(
            name=name,
            step_type=StepType.TASK,
            job=job_config,
            depends_on=dependencies,
            is_required=True,
            on_failure="fail_workflow",
        )

        self.workflow.add_step(step_id, step_config)
        self.last_step_id = step_id

        return self

    def add_parallel_step(
        self,
        step_id: str,
        name: str,
        provider_id: uuid.UUID,
        service_id: str,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> "WorkflowBuilder":
        dependencies = getattr(self, "_last_parallel_steps", [])

        job_config = JobConfig(
            provider_id=provider_id,
            service_id=service_id,
            parameters=parameters or {},
        )

        step_config = StepConfig(
            name=name,
            step_type=StepType.TASK,
            job=job_config,
            depends_on=dependencies,
            is_required=True,
            on_failure="fail_workflow",
        )

        self.workflow.add_step(step_id, step_config)
        self.last_step_id = step_id

        return self

    def from_blueprint(
        self,
        blueprint: Any,
        provider_mappings: Dict[str, tuple[uuid.UUID, str]],
    ) -> "WorkflowBuilder":
        self.workflow.blueprint_id = blueprint.id
        self.workflow.blueprint_version = blueprint.version
        self.workflow.steps = dict(blueprint.steps)

        for step_id, (provider_id, service_id) in provider_mappings.items():
            if step_id in self.workflow.steps:
                step = self.workflow.steps[step_id]
                if step.job:
                    step.job.provider_id = provider_id
                    step.job.service_id = service_id

        return self

    def build(self) -> Workflow:
        return self.workflow
