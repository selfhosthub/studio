# api/app/domain/workflow/models.py

"""Domain models for the workflow context."""
import re
import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from pydantic import ConfigDict, Field, field_validator, model_validator

from app.config.settings import get_settings
from app.domain.common.base_entity import AggregateRoot
from app.domain.common.exceptions import (
    InvalidStateTransition,
    BusinessRuleViolation,
    ValidationError as DomainValidationError,
)
from app.domain.common.value_objects import (
    JobConfig,
    StepConfig,
    StepType,
    Visibility,
)
from app.domain.workflow.events import (
    WorkflowActivatedEvent,
    WorkflowCreatedEvent,
    WorkflowDeactivatedEvent,
    WorkflowStepAddedEvent,
    WorkflowStepRemovedEvent,
    WorkflowUpdatedEvent,
)


_SLUG_BASENAME_RE = re.compile(r"[^a-z0-9]+")


def _derive_default_slug(name: str) -> str:
    """Best-effort namespaced slug from a workflow name. Callers in production should set slug explicitly via the org's namespace."""
    basename = _SLUG_BASENAME_RE.sub("-", name.lower()).strip("-") or "workflow"
    if not basename[0].isalpha():
        basename = f"w-{basename}"
    return f"local/{basename}"


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
    """Aggregate root for a configured workflow definition. Executable multiple times."""

    name: str
    slug: str = ""
    description: Optional[str] = None
    organization_id: uuid.UUID
    status: WorkflowStatus = WorkflowStatus.DRAFT
    steps: Dict[str, StepConfig] = Field(default_factory=dict)
    trigger_type: WorkflowTriggerType = WorkflowTriggerType.MANUAL
    priority: WorkflowPriority = WorkflowPriority.NORMAL
    execution_mode: ExecutionMode = ExecutionMode.QUEUED
    client_metadata: Dict[str, Any] = Field(default_factory=dict)
    tags: List[str] = Field(default_factory=list)
    version: int = 1
    has_unresolved_refs: bool = False
    instance_count: int = 0
    # Live count of existing instance rows, set by the repository on read.
    # instance_count is a monotonic version counter and never decrements on
    # instance deletion, so deletability must use this instead. None when the
    # repository did not load it.
    live_instance_count: Optional[int] = None
    last_instance_at: Optional[datetime] = None
    created_by: uuid.UUID
    scope: WorkflowScope = WorkflowScope.ORGANIZATION
    publish_status: Optional[PublishStatus] = None
    # Cross-org marketplace visibility (super_admin-controlled). Orthogonal to
    # scope/status/publish_status. Default private.
    visibility: Visibility = Visibility.PRIVATE
    max_concurrent_instances: Optional[int] = None
    webhook_token: Optional[str] = None  # Secure token for webhook trigger URL
    webhook_method: str = "POST"  # HTTP method for webhook trigger (POST or GET)
    webhook_auth_type: str = "none"  # Auth type: "none", "header", "jwt", "hmac"
    webhook_auth_header_name: Optional[str] = (
        None  # Header name for header auth (e.g., "X-API-Key")
    )
    trigger_input_schema: Optional[Dict[str, Any]] = (
        None  # Schema for expected trigger payload fields
    )
    # --- Schedule trigger (RRULE / RFC 5545) ---
    schedule_dtstart: Optional[datetime] = None  # Anchor / one-off run time (tz-aware)
    schedule_rrule: Optional[str] = None  # iCal RRULE; None = run once at dtstart
    schedule_timezone: str = "UTC"  # IANA tz name the rule is evaluated in
    schedule_enabled: bool = False  # Master on/off for the schedule tick
    schedule_next_run_at: Optional[datetime] = None  # Next fire time (UTC), computed
    schedule_last_run_at: Optional[datetime] = None  # Last fire time (UTC)
    # --- API trigger ---
    # Plaintext bearer key, present ONLY transiently right after generate/regenerate
    # so the API layer can return it once. Never loaded from the DB; the recoverable
    # copy lives in the referenced OrganizationSecret (trigger_secret_id).
    api_key: Optional[str] = None
    # --- Trigger credential store (org_secrets single store) ---
    # Reference to the OrganizationSecret holding this workflow's trigger creds
    # ({api_key, webhook_secret, webhook_auth_value, webhook_jwt_secret}), encrypted
    # and admin-recoverable. Non-unique: multiple workflows may share one secret
    # (admin's choice). The workflow only points at it - no secret values on the row.
    trigger_secret_id: Optional[uuid.UUID] = None
    # --- Event trigger (workflow-completion chaining) ---
    event_source_workflow_id: Optional[uuid.UUID] = (
        None  # Fire when an instance of this workflow finishes
    )
    event_on: str = "completed"  # "completed" | "failed" | "terminal"

    model_config = ConfigDict(arbitrary_types_allowed=True)

    @model_validator(mode="after")
    def _ensure_slug(self) -> "Workflow":
        if not self.slug:
            self.slug = _derive_default_slug(self.name)
        return self

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

    @field_validator("visibility", mode="before")
    @classmethod
    def convert_visibility_to_enum(cls, v):
        if isinstance(v, str) and not isinstance(v, Visibility):
            return Visibility(v)
        return v

    @classmethod
    def create(
        cls,
        name: str,
        organization_id: uuid.UUID,
        created_by: uuid.UUID,
        slug: str = "",
        description: Optional[str] = None,
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
            slug=slug,
            description=description,
            organization_id=organization_id,
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
    ) -> None:
        """Update workflow properties. Archived workflows accept only the status
        change that un-archives them; requires steps when activating."""
        if self.status == WorkflowStatus.ARCHIVED and (
            status is None or status == WorkflowStatus.ARCHIVED
        ):
            raise InvalidStateTransition(
                message="Cannot update an archived workflow. Change its status first.",
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

    def validate_can_be_archived(self, actor_id: Optional[uuid.UUID] = None) -> None:
        """Raises if the workflow is pending publish approval and the actor is
        not its creator (only the owner may archive a pending submission)."""
        if self.publish_status == PublishStatus.PENDING and actor_id != self.created_by:
            raise BusinessRuleViolation(
                message="Cannot archive a workflow pending publish approval. Reject it first.",
                code="WORKFLOW_PENDING_APPROVAL",
                context={"workflow_id": str(self.id)},
            )

    def archive(self) -> None:
        """Archive the workflow."""
        self.status = WorkflowStatus.ARCHIVED
        self.updated_at = datetime.now(UTC)

    def set_visibility(self, new_visibility: Visibility) -> Visibility:
        """Transition cross-org marketplace visibility. Returns the previous
        value (for audit). Authorization (super_admin-only) is enforced at the
        API boundary; this only mutates state."""
        old_visibility = self.visibility
        self.visibility = new_visibility
        self.updated_at = datetime.now(UTC)
        return old_visibility

    def generate_webhook_token(self) -> tuple[str, str]:
        """Generate token + HMAC secret. Raises if a token already exists; use regenerate to replace.

        Returns (token, secret). The token is the capability identifier and stays
        on the workflow; the secret is recoverable and the service stores it in the
        referenced OrganizationSecret, never on the workflow row.
        """
        if self.webhook_token:
            raise BusinessRuleViolation(
                message="Webhook token already exists. Use regenerate_webhook_token() to replace it.",
                code="TOKEN_EXISTS",
                context={"workflow_id": str(self.id)},
            )

        import secrets

        self.webhook_token = secrets.token_urlsafe(24)  # 32 characters
        secret = secrets.token_urlsafe(32)  # 43 characters for HMAC
        self.trigger_type = WorkflowTriggerType.WEBHOOK
        self.updated_at = datetime.now(UTC)
        return (self.webhook_token, secret)

    def regenerate_webhook_token(self) -> tuple[str, str]:
        """Rotate token + HMAC secret. Raises if no token exists yet; use generate first.

        Returns (token, secret); the secret is stored by the service in the
        referenced OrganizationSecret (see generate_webhook_token)."""
        if not self.webhook_token:
            raise BusinessRuleViolation(
                message="No webhook token exists. Use generate_webhook_token() first.",
                code="NO_TOKEN",
                context={"workflow_id": str(self.id)},
            )

        import secrets

        self.webhook_token = secrets.token_urlsafe(24)  # 32 characters
        secret = secrets.token_urlsafe(32)  # 43 characters for HMAC
        self.updated_at = datetime.now(UTC)
        return (self.webhook_token, secret)

    def clear_webhook_token(self) -> None:
        """Remove the webhook token from this workflow. The signing secret lives in
        the referenced OrganizationSecret; the service drops it there."""
        self.webhook_token = None
        if self.trigger_type == WorkflowTriggerType.WEBHOOK:
            self.trigger_type = WorkflowTriggerType.MANUAL
        self.updated_at = datetime.now(UTC)

    @staticmethod
    def new_api_key() -> str:
        """Mint a fresh API trigger key string (format `wfk_<token>`). The sole
        source of the key format - service-side rotation (e.g. of a shared trigger
        secret on the Secrets page) uses this too, so the format never drifts."""
        import secrets

        return f"wfk_{secrets.token_urlsafe(32)}"

    def generate_api_key(self) -> str:
        """Mint a fresh API trigger key and switch to the API trigger type.

        Returns the plaintext key. The recoverable copy is stored by the service
        in the referenced OrganizationSecret; nothing about the key is persisted on
        the workflow row. The "already exists / doesn't exist" gating for
        generate-vs-regenerate lives in the service (it reads the secret)."""
        self.api_key = Workflow.new_api_key()
        self.trigger_type = WorkflowTriggerType.API
        self.updated_at = datetime.now(UTC)
        return self.api_key

    def clear_api_key(self) -> None:
        """Remove the API trigger key from this workflow. The recoverable copy lives
        in the referenced OrganizationSecret; the service drops it there."""
        self.api_key = None
        if self.trigger_type == WorkflowTriggerType.API:
            self.trigger_type = WorkflowTriggerType.MANUAL
        self.updated_at = datetime.now(UTC)

    def detach_trigger_secret(self) -> None:
        """The referenced OrganizationSecret was deleted out from under this
        workflow: drop the link and fall back to manual. Covers both api_key and
        webhook secrets (the per-workflow webhook token is meaningless without its
        signing secret), so the workflow never sits in a 'triggered but no
        credential' limbo."""
        self.trigger_secret_id = None
        self.api_key = None
        self.webhook_token = None
        if self.trigger_type in (
            WorkflowTriggerType.API,
            WorkflowTriggerType.WEBHOOK,
        ):
            self.trigger_type = WorkflowTriggerType.MANUAL
        self.updated_at = datetime.now(UTC)

    def set_schedule(
        self,
        *,
        dtstart: Optional[datetime],
        rrule: Optional[str],
        timezone: str,
        enabled: bool,
        next_run_at: Optional[datetime],
    ) -> None:
        """Configure the schedule trigger. Validation of dtstart/rrule and the
        computation of next_run_at happen at the service boundary (needs dateutil);
        this only mutates state and flips trigger_type."""
        self.schedule_dtstart = dtstart
        self.schedule_rrule = rrule
        self.schedule_timezone = timezone
        self.schedule_enabled = enabled
        self.schedule_next_run_at = next_run_at
        self.trigger_type = WorkflowTriggerType.SCHEDULE
        self.updated_at = datetime.now(UTC)

    def clear_schedule(self) -> None:
        """Disable and wipe schedule configuration."""
        self.schedule_dtstart = None
        self.schedule_rrule = None
        self.schedule_enabled = False
        self.schedule_next_run_at = None
        if self.trigger_type == WorkflowTriggerType.SCHEDULE:
            self.trigger_type = WorkflowTriggerType.MANUAL
        self.updated_at = datetime.now(UTC)

    def set_event_trigger(self, source_workflow_id: uuid.UUID, on: str) -> None:
        """Bind this workflow to fire when an instance of source_workflow_id finishes."""
        if source_workflow_id == self.id:
            raise BusinessRuleViolation(
                message="A workflow cannot trigger itself via an event.",
                code="EVENT_SELF_TRIGGER",
                context={"workflow_id": str(self.id)},
            )
        if on not in ("completed", "failed", "terminal"):
            raise BusinessRuleViolation(
                message="event_on must be one of: completed, failed, terminal.",
                code="INVALID_EVENT_ON",
                context={"event_on": on},
            )
        self.event_source_workflow_id = source_workflow_id
        self.event_on = on
        self.trigger_type = WorkflowTriggerType.EVENT
        self.updated_at = datetime.now(UTC)

    def clear_event_trigger(self) -> None:
        """Remove the event-trigger binding."""
        self.event_source_workflow_id = None
        if self.trigger_type == WorkflowTriggerType.EVENT:
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

    def _has_blocking_instances(self) -> bool:
        """True if existing instances block deletion. Prefers the live count;
        falls back to the monotonic instance_count when it wasn't loaded."""
        count = (
            self.live_instance_count
            if self.live_instance_count is not None
            else self.instance_count
        )
        return count > 0

    def can_be_deleted(self) -> bool:
        """True when no instances exist and status is INACTIVE, ARCHIVED, or DRAFT."""
        if self._has_blocking_instances():
            return False
        return self.status in (
            WorkflowStatus.INACTIVE,
            WorkflowStatus.ARCHIVED,
            WorkflowStatus.DRAFT,
        )

    def validate_can_be_deleted(self, actor_id: Optional[uuid.UUID] = None) -> None:
        """Raises if ACTIVE, if it has ever executed, or if pending approval and
        the actor is not its creator."""
        if self.status == WorkflowStatus.ACTIVE:
            raise BusinessRuleViolation(
                message="Cannot delete active workflow. Deactivate it first.",
                code="WORKFLOW_ACTIVE",
                context={
                    "workflow_id": str(self.id),
                    "current_status": self.status.value,
                },
            )
        if self._has_blocking_instances():
            raise BusinessRuleViolation(
                message="Cannot delete a workflow with existing instances. Delete its instances first.",
                code="WORKFLOW_HAS_INSTANCES",
                context={
                    "workflow_id": str(self.id),
                    "instance_count": self.instance_count,
                },
            )
        if self.publish_status == PublishStatus.PENDING and actor_id != self.created_by:
            raise BusinessRuleViolation(
                message="Cannot delete a workflow pending publish approval. Reject it first.",
                code="WORKFLOW_PENDING_APPROVAL",
                context={"workflow_id": str(self.id)},
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
                retry_count=get_settings().STEP_DEFAULT_RETRY_COUNT,
                retry_delay_seconds=get_settings().STEP_DEFAULT_RETRY_DELAY,
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

    def build(self) -> Workflow:
        return self.workflow
