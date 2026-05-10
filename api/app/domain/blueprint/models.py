# api/app/domain/blueprint/models.py

"""Blueprint domain models."""
import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import ConfigDict, Field, field_validator

from app.config.settings import settings
from app.domain.common.base_entity import AggregateRoot
from app.domain.common.exceptions import (
    BusinessRuleViolation,
    InvalidStateTransition,
    ValidationError,
)
from app.domain.common.events import DomainEvent
from app.domain.common.value_objects import StepConfig


class BlueprintCategory(str, Enum):
    GENERAL = "general"
    DATA_PROCESSING = "data_processing"
    INTEGRATION = "integration"
    AUTOMATION = "automation"
    ANALYTICS = "analytics"
    CUSTOM = "custom"


class BlueprintStatus(str, Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"


class BlueprintCreatedEvent(DomainEvent):
    event_type: str = "blueprint.created"
    blueprint_id: uuid.UUID
    organization_id: uuid.UUID
    data: Dict[str, Any] = Field(default_factory=dict)


class BlueprintUpdatedEvent(DomainEvent):
    event_type: str = "blueprint.updated"
    blueprint_id: uuid.UUID
    organization_id: uuid.UUID
    data: Dict[str, Any] = Field(default_factory=dict)


class Blueprint(AggregateRoot):
    """Aggregate root for a reusable workflow definition."""

    name: str = Field(..., min_length=1)
    description: Optional[str] = None
    organization_id: uuid.UUID
    category: BlueprintCategory = BlueprintCategory.GENERAL
    status: BlueprintStatus = BlueprintStatus.DRAFT
    version: int = 1
    steps: Dict[str, StepConfig] = Field(default_factory=dict)
    tags: List[str] = Field(default_factory=list)
    icon: Optional[str] = None
    color: Optional[str] = None
    client_metadata: Dict[str, Any] = Field(default_factory=dict)

    max_execution_time_seconds: Optional[int] = None
    max_retries: int = settings.DEFAULT_MAX_RETRIES
    allow_parallel_execution: bool = True
    requires_approval: bool = False

    created_by: Optional[uuid.UUID] = None

    model_config = ConfigDict(arbitrary_types_allowed=True)

    @field_validator("status", mode="before")
    @classmethod
    def convert_status_to_enum(cls, v):
        if isinstance(v, str) and not isinstance(v, BlueprintStatus):
            return BlueprintStatus(v)
        return v

    @classmethod
    def create(
        cls,
        name: str,
        organization_id: uuid.UUID,
        created_by: Optional[uuid.UUID] = None,
        description: Optional[str] = None,
        category: BlueprintCategory = BlueprintCategory.GENERAL,
        tags: Optional[List[str]] = None,
        icon: Optional[str] = None,
        color: Optional[str] = None,
        max_execution_time_seconds: Optional[int] = None,
        max_retries: int = 3,
        allow_parallel_execution: bool = True,
        requires_approval: bool = False,
        client_metadata: Optional[Dict[str, Any]] = None,
        steps: Optional[Dict[str, StepConfig]] = None,
    ) -> "Blueprint":
        blueprint = cls(
            name=name,
            description=description,
            organization_id=organization_id,
            category=category,
            status=BlueprintStatus.DRAFT,
            version=1,
            steps=steps or {},
            tags=tags or [],
            icon=icon,
            color=color,
            client_metadata=client_metadata or {},
            max_execution_time_seconds=max_execution_time_seconds,
            max_retries=max_retries,
            allow_parallel_execution=allow_parallel_execution,
            requires_approval=requires_approval,
            created_by=created_by,
        )

        blueprint.add_event(
            BlueprintCreatedEvent(
                aggregate_id=blueprint.id,
                aggregate_type="blueprint",
                blueprint_id=blueprint.id,
                organization_id=organization_id,
                data={
                    "name": name,
                    "category": category.value,
                },
            )
        )

        return blueprint

    @classmethod
    def create_with_steps_dict(
        cls,
        name: str,
        organization_id: uuid.UUID,
        created_by: uuid.UUID,
        description: Optional[str] = None,
        category: BlueprintCategory = BlueprintCategory.GENERAL,
        tags: Optional[List[str]] = None,
        icon: Optional[str] = None,
        color: Optional[str] = None,
        max_execution_time_seconds: Optional[int] = None,
        max_retries: int = 3,
        allow_parallel_execution: bool = True,
        requires_approval: bool = False,
        client_metadata: Optional[Dict[str, Any]] = None,
        steps_dict: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> "Blueprint":
        """Create a blueprint, parsing steps from raw dicts."""
        steps = {}
        if steps_dict:
            for step_id, step_config_dict in steps_dict.items():
                steps[step_id] = StepConfig(**step_config_dict)

        return cls.create(
            name=name,
            organization_id=organization_id,
            created_by=created_by,
            description=description,
            category=category,
            tags=tags,
            icon=icon,
            color=color,
            max_execution_time_seconds=max_execution_time_seconds,
            max_retries=max_retries,
            allow_parallel_execution=allow_parallel_execution,
            requires_approval=requires_approval,
            client_metadata=client_metadata,
            steps=steps,
        )

    def publish(self) -> None:
        """Publish the blueprint. Requires DRAFT status, at least one step, and a valid dependency graph."""
        if self.status != BlueprintStatus.DRAFT:
            raise InvalidStateTransition(
                message=f"Cannot publish blueprint with status {self.status.value}",
                code="INVALID_PUBLISH_STATUS",
                context={
                    "blueprint_id": str(self.id),
                    "current_status": self.status.value,
                },
            )

        if not self.steps:
            raise BusinessRuleViolation(
                message="Cannot publish blueprint without steps",
                code="NO_STEPS",
                context={
                    "blueprint_id": str(self.id),
                },
            )

        self.validate_steps()

        self.status = BlueprintStatus.PUBLISHED
        self.updated_at = datetime.now(UTC)

        self.add_event(
            BlueprintUpdatedEvent(
                aggregate_id=self.id,
                aggregate_type="blueprint",
                blueprint_id=self.id,
                organization_id=self.organization_id,
                data={
                    "name": self.name,
                    "status": "published",
                },
            )
        )

    def deprecate(self) -> None:
        """Mark a published blueprint as deprecated."""
        if self.status != BlueprintStatus.PUBLISHED:
            raise InvalidStateTransition(
                message=f"Cannot deprecate blueprint with status {self.status.value}",
                code="INVALID_DEPRECATE_STATUS",
                context={
                    "blueprint_id": str(self.id),
                    "current_status": self.status.value,
                },
            )

        self.status = BlueprintStatus.DEPRECATED
        self.updated_at = datetime.now(UTC)

        self.add_event(
            BlueprintUpdatedEvent(
                aggregate_id=self.id,
                aggregate_type="blueprint",
                blueprint_id=self.id,
                organization_id=self.organization_id,
                data={
                    "name": self.name,
                    "status": "deprecated",
                },
            )
        )

    def archive(self) -> None:
        if self.status == BlueprintStatus.ARCHIVED:
            raise InvalidStateTransition(
                message="Blueprint is already archived",
                code="ALREADY_ARCHIVED",
                context={
                    "blueprint_id": str(self.id),
                },
            )

        old_status = self.status
        self.status = BlueprintStatus.ARCHIVED
        self.updated_at = datetime.now(UTC)

        self.add_event(
            BlueprintUpdatedEvent(
                aggregate_id=self.id,
                aggregate_type="blueprint",
                blueprint_id=self.id,
                organization_id=self.organization_id,
                data={
                    "name": self.name,
                    "old_status": old_status.value,
                    "new_status": self.status.value,
                },
            )
        )

    def revert_to_draft(self) -> None:
        """Revert to DRAFT for editing. Bumps version. Archived blueprints cannot revert."""
        if self.status == BlueprintStatus.DRAFT:
            raise InvalidStateTransition(
                message="Blueprint is already in draft status",
                code="ALREADY_DRAFT",
                context={
                    "blueprint_id": str(self.id),
                },
            )

        if self.status == BlueprintStatus.ARCHIVED:
            raise InvalidStateTransition(
                message="Cannot revert archived blueprint to draft",
                code="CANNOT_REVERT_ARCHIVED",
                context={
                    "blueprint_id": str(self.id),
                },
            )

        old_status = self.status
        self.status = BlueprintStatus.DRAFT
        self.version += 1
        self.updated_at = datetime.now(UTC)

        self.add_event(
            BlueprintUpdatedEvent(
                aggregate_id=self.id,
                aggregate_type="blueprint",
                blueprint_id=self.id,
                organization_id=self.organization_id,
                data={
                    "name": self.name,
                    "old_status": old_status.value,
                    "new_status": self.status.value,
                    "version": self.version,
                },
            )
        )

    def update(
        self,
        name: Optional[str] = None,
        description: Optional[str] = None,
        category: Optional[BlueprintCategory] = None,
        tags: Optional[List[str]] = None,
        icon: Optional[str] = None,
        color: Optional[str] = None,
        max_execution_time_seconds: Optional[int] = None,
        max_retries: Optional[int] = None,
        allow_parallel_execution: Optional[bool] = None,
        requires_approval: Optional[bool] = None,
        client_metadata: Optional[Dict[str, Any]] = None,
        status: Optional[BlueprintStatus] = None,
    ) -> None:
        """Update fields. Cannot update an archived blueprint. Publishing requires steps + valid graph."""
        if self.status == BlueprintStatus.ARCHIVED:
            raise InvalidStateTransition(
                message="Cannot update an archived blueprint",
                code="CANNOT_UPDATE_ARCHIVED",
                context={
                    "blueprint_id": str(self.id),
                },
            )

        if status == BlueprintStatus.PUBLISHED:
            if not self.steps:
                raise BusinessRuleViolation(
                    message="Cannot publish blueprint without steps",
                    code="NO_STEPS",
                    context={
                        "blueprint_id": str(self.id),
                    },
                )
            self.validate_steps()

        if name is not None:
            self.name = name
        if description is not None:
            self.description = description
        if category is not None:
            self.category = category
        if tags is not None:
            self.tags = tags
        if icon is not None:
            self.icon = icon
        if color is not None:
            self.color = color
        if max_execution_time_seconds is not None:
            self.max_execution_time_seconds = max_execution_time_seconds
        if max_retries is not None:
            self.max_retries = max_retries
        if allow_parallel_execution is not None:
            self.allow_parallel_execution = allow_parallel_execution
        if requires_approval is not None:
            self.requires_approval = requires_approval
        if client_metadata is not None:
            self.client_metadata.update(client_metadata)

        # Bump version on each publish for the released-version audit trail.
        if status and status == BlueprintStatus.PUBLISHED:
            self.version += 1

        if status is not None:
            self.status = status

        self.updated_at = datetime.now(UTC)

        self.add_event(
            BlueprintUpdatedEvent(
                aggregate_id=self.id,
                aggregate_type="blueprint",
                blueprint_id=self.id,
                organization_id=self.organization_id,
                data={
                    "name": self.name,
                    "version": self.version,
                    "status": self.status.value,
                },
            )
        )

    def add_step(self, step_id: str, config: StepConfig) -> None:
        """Add a step. Published/archived blueprints reject step changes; revert to draft first."""
        if self.status == BlueprintStatus.PUBLISHED:
            raise InvalidStateTransition(
                message="Cannot modify steps in a published blueprint. Revert to draft first.",
                code="CANNOT_MODIFY_PUBLISHED",
                context={
                    "blueprint_id": str(self.id),
                },
            )

        if self.status == BlueprintStatus.ARCHIVED:
            raise InvalidStateTransition(
                message="Cannot modify steps in an archived blueprint",
                code="CANNOT_MODIFY_ARCHIVED",
                context={
                    "blueprint_id": str(self.id),
                },
            )

        if step_id in self.steps:
            raise ValidationError(
                message=f"Step with ID '{step_id}' already exists",
                code="DUPLICATE_STEP_ID",
                context={
                    "blueprint_id": str(self.id),
                    "step_id": step_id,
                },
            )

        self.steps[step_id] = config
        self.version += 1
        self.updated_at = datetime.now(UTC)

    def remove_step(self, step_id: str) -> None:
        """Remove a step. Rejects if any other step depends on it."""
        if self.status == BlueprintStatus.PUBLISHED:
            raise InvalidStateTransition(
                message="Cannot modify steps in a published blueprint. Revert to draft first.",
                code="CANNOT_MODIFY_PUBLISHED",
                context={
                    "blueprint_id": str(self.id),
                },
            )

        if self.status == BlueprintStatus.ARCHIVED:
            raise InvalidStateTransition(
                message="Cannot modify steps in an archived blueprint",
                code="CANNOT_MODIFY_ARCHIVED",
                context={
                    "blueprint_id": str(self.id),
                },
            )

        if step_id not in self.steps:
            raise ValidationError(
                message=f"Step '{step_id}' does not exist",
                code="STEP_NOT_FOUND",
                context={
                    "blueprint_id": str(self.id),
                    "step_id": step_id,
                },
            )

        for other_step_id, other_step in self.steps.items():
            if step_id in other_step.depends_on:
                raise BusinessRuleViolation(
                    message=f"Cannot remove step '{step_id}' because step '{other_step_id}' depends on it",
                    code="STEP_HAS_DEPENDENTS",
                    context={
                        "blueprint_id": str(self.id),
                        "step_id": step_id,
                        "dependent_step_id": other_step_id,
                    },
                )

        del self.steps[step_id]
        self.version += 1
        self.updated_at = datetime.now(UTC)

    def add_step_from_dict(
        self, step_id: str, step_config_dict: Dict[str, Any]
    ) -> None:
        step_config = StepConfig(**step_config_dict)
        self.add_step(step_id, step_config)

    def update_step(self, step_id: str, config: StepConfig) -> None:
        if self.status == BlueprintStatus.PUBLISHED:
            raise InvalidStateTransition(
                message="Cannot modify steps in a published blueprint. Revert to draft first.",
                code="CANNOT_MODIFY_PUBLISHED",
                context={
                    "blueprint_id": str(self.id),
                },
            )

        if self.status == BlueprintStatus.ARCHIVED:
            raise InvalidStateTransition(
                message="Cannot modify steps in an archived blueprint",
                code="CANNOT_MODIFY_ARCHIVED",
                context={
                    "blueprint_id": str(self.id),
                },
            )

        if step_id not in self.steps:
            raise ValidationError(
                message=f"Step '{step_id}' does not exist",
                code="STEP_NOT_FOUND",
                context={
                    "blueprint_id": str(self.id),
                    "step_id": step_id,
                },
            )

        self.steps[step_id] = config
        self.version += 1
        self.updated_at = datetime.now(UTC)

    def validate_steps(self) -> None:
        """Require non-empty steps, all dependencies present, and no cycles."""
        if not self.steps:
            raise BusinessRuleViolation(
                message="Blueprint must have at least one step",
                code="NO_STEPS",
                context={
                    "blueprint_id": str(self.id),
                },
            )

        step_ids = set(self.steps.keys())

        for step_id, step_config in self.steps.items():
            for dep_id in step_config.depends_on:
                if dep_id not in step_ids:
                    raise BusinessRuleViolation(
                        message=f"Step '{step_id}' depends on non-existent step '{dep_id}'",
                        code="INVALID_DEPENDENCY",
                        context={
                            "blueprint_id": str(self.id),
                            "step_id": step_id,
                            "missing_dependency": dep_id,
                        },
                    )

        if self._has_circular_dependencies():
            raise BusinessRuleViolation(
                message="Blueprint has circular dependencies",
                code="CIRCULAR_DEPENDENCIES",
                context={
                    "blueprint_id": str(self.id),
                },
            )

    def _has_circular_dependencies(self) -> bool:
        visited: set[str] = set()
        rec_stack: set[str] = set()

        def visit(step_id: str) -> bool:
            if step_id in rec_stack:
                return True
            if step_id in visited:
                return False

            visited.add(step_id)
            rec_stack.add(step_id)

            step_config = self.steps.get(step_id)
            if step_config:
                for dep_id in step_config.depends_on:
                    if visit(dep_id):
                        return True

            rec_stack.remove(step_id)
            return False

        for step_id in self.steps.keys():
            if visit(step_id):
                return True

        return False

    def create_workflow(
        self,
        name: str,
        organization_id: uuid.UUID,
        created_by: uuid.UUID,
        description: Optional[str] = None,
    ):
        """Materialize a workflow from this blueprint. Blueprint must be PUBLISHED."""
        if self.status != BlueprintStatus.PUBLISHED:
            raise BusinessRuleViolation(
                message=f"Cannot create workflow from {self.status.value} blueprint",
                code="BLUEPRINT_NOT_PUBLISHED",
                context={
                    "blueprint_id": str(self.id),
                    "current_status": self.status.value,
                },
            )

        from app.domain.workflow.models import Workflow

        return Workflow.create(
            name=name,
            organization_id=organization_id,
            created_by=created_by,
            description=description or self.description,
            blueprint_id=self.id,
            blueprint_version=self.version,
            steps=self.steps.copy(),
        )
