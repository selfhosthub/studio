# api/app/infrastructure/persistence/models.py

"""SQLAlchemy 2.0 database models."""

import uuid
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    ARRAY,
    JSON,
    Boolean,
    CheckConstraint,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    TIMESTAMP,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY as PG_ARRAY, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.config.settings import settings
from app.domain.notification.models import (
    NotificationPriority,
    NotificationStatus,
)
from app.domain.provider.models import (
    CatalogType,
    PackageSource,
    PackageType,
    ProviderStatus,
    ProviderType,
    ServiceType,
)
from app.domain.queue.models import QueueStatus, QueueType, WorkerStatus
from app.domain.blueprint.models import BlueprintCategory, BlueprintStatus
from app.domain.workflow.models import (
    ExecutionMode,
    PublishStatus,
    WorkflowPriority,
    WorkflowScope,
    WorkflowStatus,
    WorkflowTriggerType,
)
from app.domain.instance.models import InstanceStatus
from app.domain.instance.iteration_execution import IterationExecutionStatus
from app.domain.instance_step.models import StepExecutionStatus
from app.domain.org_file.models import ResourceSource, ResourceStatus
from app.domain.audit.models import (
    AuditAction,
    AuditActorType,
    AuditCategory,
    AuditSeverity,
    AuditStatus,
    ResourceType,
)
from app.domain.common.value_objects import (
    ActivationMethod,
    OrganizationStatus,
    PromptPublishStatus,
    PromptScope,
    PromptSource,
)


class Base(DeclarativeBase):
    pass


class OrganizationModel(Base):
    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[OrganizationStatus] = mapped_column(
        Enum(
            OrganizationStatus,
            name="organization_status",
            create_constraint=True,
            native_enum=True,
            values_callable=lambda x: [e.value for e in x],  # type: ignore[misc]  - SQLAlchemy Enum values_callable lambda; SA type stubs don't type the callable parameter
        ),
        default=OrganizationStatus.ACTIVE,
        index=True,
    )
    slug: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    settings: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    updated_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    activated_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    activated_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", use_alter=True, name="fk_organizations_activated_by_users"),
        nullable=True,
    )
    activation_method: Mapped[Optional[ActivationMethod]] = mapped_column(
        Enum(
            ActivationMethod,
            name="activationmethod",
            create_constraint=True,
            native_enum=True,
        ),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    members: Mapped[List["UserModel"]] = relationship(
        foreign_keys="UserModel.organization_id",
        back_populates="organization",
    )
    blueprints: Mapped[List["BlueprintModel"]] = relationship(
        back_populates="organization"
    )
    workflows: Mapped[List["WorkflowModel"]] = relationship(
        back_populates="organization"
    )
    instances: Mapped[List["InstanceModel"]] = relationship(
        back_populates="organization"
    )
    prompts: Mapped[List["PromptModel"]] = relationship(back_populates="organization")


class UserModel(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    username: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(50), default="user")
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    first_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    avatar_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    bio: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_public: Mapped[bool] = mapped_column(Boolean, default=False)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
    last_login: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    # Token-invalidation timestamps. NULL = no invalidation event yet.
    # Tokens with iat < max(these timestamps) are rejected.
    password_changed_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    role_changed_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    logged_out_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )

    organization: Mapped["OrganizationModel"] = relationship(
        foreign_keys=[organization_id], back_populates="members"
    )


class BlueprintModel(Base):
    __tablename__ = "blueprints"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id")
    )
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[BlueprintStatus] = mapped_column(
        Enum(
            BlueprintStatus,
            name="blueprintstatus",
            create_constraint=True,
            native_enum=True,
        ),
        default=BlueprintStatus.DRAFT,
    )
    category: Mapped[BlueprintCategory] = mapped_column(
        Enum(
            BlueprintCategory,
            name="blueprintcategory",
            create_constraint=True,
            native_enum=True,
        ),
        default=BlueprintCategory.GENERAL,
    )
    steps: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    tags: Mapped[List[str]] = mapped_column(ARRAY(String), default=list)
    client_metadata: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    organization: Mapped["OrganizationModel"] = relationship(
        back_populates="blueprints"
    )
    workflows: Mapped[List["WorkflowModel"]] = relationship(back_populates="blueprint")

    __table_args__ = (
        UniqueConstraint(
            "name", "organization_id", "version", name="uix_blueprint_name_org_version"
        ),
        Index("ix_blueprints_organization_status", "organization_id", "status"),
    )


class WorkflowModel(Base):
    __tablename__ = "workflows"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255))
    slug: Mapped[str] = mapped_column(String(255))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id")
    )
    blueprint_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("blueprints.id"), nullable=True
    )
    status: Mapped[WorkflowStatus] = mapped_column(
        Enum(
            WorkflowStatus,
            name="workflowstatus",
            create_constraint=True,
            native_enum=True,
        ),
        default=WorkflowStatus.DRAFT,
    )
    trigger_type: Mapped[WorkflowTriggerType] = mapped_column(
        Enum(
            WorkflowTriggerType,
            name="workflowtriggertype",
            create_constraint=True,
            native_enum=True,
        ),
        default=WorkflowTriggerType.MANUAL,
    )
    priority: Mapped[WorkflowPriority] = mapped_column(
        Enum(
            WorkflowPriority,
            name="workflowpriority",
            create_constraint=True,
            native_enum=True,
        ),
        default=WorkflowPriority.NORMAL,
    )
    execution_mode: Mapped[ExecutionMode] = mapped_column(
        Enum(
            ExecutionMode,
            name="executionmode",
            create_constraint=True,
            native_enum=True,
        ),
        default=ExecutionMode.QUEUED,
    )
    has_unresolved_refs: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    max_concurrent_instances: Mapped[int] = mapped_column(Integer, default=1)
    instance_count: Mapped[int] = mapped_column(Integer, default=0)
    last_instance_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    webhook_token: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, unique=True, index=True
    )
    # Encrypted at rest. ~43 plaintext → ~160 after encryption; 256 leaves
    # room for Fernet version bumps without a migration.
    webhook_secret: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    webhook_method: Mapped[str] = mapped_column(String(10), default="POST")
    webhook_auth_type: Mapped[str] = mapped_column(String(20), default="none")
    webhook_auth_header_name: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True
    )
    webhook_auth_header_value: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True  # Encrypted; 500 fits Fernet ciphertext.
    )
    webhook_jwt_secret: Mapped[Optional[str]] = mapped_column(
        String(256), nullable=True  # Encrypted; 256 fits Fernet ciphertext.
    )
    tags: Mapped[List[str]] = mapped_column(ARRAY(String), default=list)
    client_metadata: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    scope: Mapped[WorkflowScope] = mapped_column(
        Enum(
            WorkflowScope,
            name="workflowscope",
            create_constraint=True,
            native_enum=True,
        ),
        default=WorkflowScope.ORGANIZATION,
    )
    publish_status: Mapped[Optional[PublishStatus]] = mapped_column(
        Enum(
            PublishStatus,
            name="publishstatus",
            create_constraint=True,
            native_enum=True,
        ),
        nullable=True,
        default=None,
    )
    updated_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )

    organization: Mapped["OrganizationModel"] = relationship(back_populates="workflows")
    blueprint: Mapped[Optional["BlueprintModel"]] = relationship(
        back_populates="workflows"
    )
    instances: Mapped[List["InstanceModel"]] = relationship(back_populates="workflow")
    versions: Mapped[List["WorkflowVersionModel"]] = relationship(
        back_populates="workflow", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("organization_id", "slug", name="uix_workflow_org_slug"),
        CheckConstraint(
            "slug LIKE '%/%' AND slug NOT LIKE '/%' AND slug NOT LIKE '%/'",
            name="ck_workflow_slug_namespaced",
        ),
        Index("ix_workflows_organization_status", "organization_id", "status"),
        Index("ix_workflows_organization_scope", "organization_id", "scope"),
        Index("ix_workflows_created_by_scope", "created_by", "scope"),
        Index("ix_workflows_blueprint", "blueprint_id"),
        Index(
            "ix_workflows_has_unresolved_refs",
            "organization_id",
            postgresql_where=text("has_unresolved_refs = TRUE"),
        ),
        Index(
            "ix_workflows_slug_pattern",
            text("slug text_pattern_ops"),
        ),
    )


class WorkflowVersionModel(Base):
    """Immutable snapshot of a workflow's steps + trigger schema. One row per save (deduped on structural_hash)."""

    __tablename__ = "workflow_versions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflows.id", ondelete="CASCADE"),
        nullable=False,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    steps: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False)
    trigger_input_schema: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSONB, nullable=True
    )
    structural_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    label: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    workflow: Mapped["WorkflowModel"] = relationship(back_populates="versions")

    __table_args__ = (
        UniqueConstraint("workflow_id", "version", name="uix_workflow_version_unique"),
        Index("ix_workflow_versions_workflow_created", "workflow_id", "created_at"),
        Index("ix_workflow_versions_workflow_hash", "workflow_id", "structural_hash"),
    )


class InstanceModel(Base):
    __tablename__ = "instances"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workflows.id")
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id")
    )
    status: Mapped[InstanceStatus] = mapped_column(
        Enum(
            InstanceStatus,
            name="instancestatus",
            create_constraint=True,
            native_enum=True,
        ),
        default=InstanceStatus.INACTIVE,
    )
    version: Mapped[int] = mapped_column(Integer, default=1)
    input_data: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict)
    output_data: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict)
    client_metadata: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict)
    workflow_snapshot: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSONB, nullable=True, default=None
    )
    current_step_ids: Mapped[List[str]] = mapped_column(ARRAY(String), default=list)
    failed_step_ids: Mapped[List[str]] = mapped_column(ARRAY(String), default=list)
    error_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    is_debug_mode: Mapped[bool] = mapped_column(Boolean, default=False)
    started_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    workflow: Mapped["WorkflowModel"] = relationship(back_populates="instances")
    organization: Mapped["OrganizationModel"] = relationship(back_populates="instances")

    step_executions: Mapped[List["StepExecutionModel"]] = relationship(
        back_populates="instance", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_instances_workflow_status", "workflow_id", "status"),
        Index("ix_instances_organization_status", "organization_id", "status"),
        Index("ix_instances_status_created", "status", "created_at"),
    )


class StepExecutionModel(Base):
    """One row per step per instance - lifecycle and worker-attempt state merged.

    `parameters` is the top layer of the three-layer parameter model
    (middle: iteration_executions.parameters; bottom: queued_jobs.payload).
    """

    __tablename__ = "step_executions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    instance_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("instances.id", ondelete="CASCADE"),
        index=True,
    )

    step_key: Mapped[str] = mapped_column(String(255), index=True)
    # Default empty: fixtures care only about step_key. DTO layer falls
    # back to step_config.name.
    step_name: Mapped[str] = mapped_column(String(255), default="", server_default="")

    status: Mapped[StepExecutionStatus] = mapped_column(
        Enum(
            StepExecutionStatus,
            name="stepexecutionstatus",
            create_constraint=True,
            native_enum=True,
        ),
        default=StepExecutionStatus.PENDING,
        index=True,
    )

    # output_data: non-file outputs (files live in org_files).
    # result: raw provider response. extracted_outputs: extracted values passed to downstream steps.
    output_data: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict)
    result: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    extracted_outputs: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict)

    # Error tracking
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Retry state (JobExecution heritage)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    max_retries: Mapped[int] = mapped_column(
        Integer, default=settings.DEFAULT_MAX_RETRIES
    )

    # Execution metadata + debugging (JobExecution heritage)
    execution_data: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict)
    input_data: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict)
    request_body: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)

    # Iteration summary (per-iteration state is in iteration_executions)
    iteration_requests: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(
        JSONB, nullable=True
    )

    # Top layer of the three-layer parameter model.
    parameters: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict)

    active_operation: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSONB, nullable=True
    )

    started_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    instance: Mapped["InstanceModel"] = relationship(back_populates="step_executions")
    iterations: Mapped[List["IterationExecutionModel"]] = relationship(
        back_populates="step_execution", cascade="all, delete-orphan"
    )
    # OrgFileModel has two FKs to step_executions; pin foreign_keys
    # so the relationship is unambiguous.
    output_resources: Mapped[List["OrgFileModel"]] = relationship(
        back_populates="step_execution",
        foreign_keys="OrgFileModel.instance_step_id",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint(
            "instance_id", "step_key", name="uq_step_execution_instance_step_key"
        ),
        Index("ix_step_executions_instance_status", "instance_id", "status"),
    )


class IterationExecutionModel(Base):
    """Per-iteration row, child of StepExecutionModel.

    `parameters` is the middle layer of the three-layer parameter model.
    """

    __tablename__ = "iteration_executions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    instance_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("instances.id", ondelete="CASCADE"),
        index=True,
    )
    step_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("step_executions.id", ondelete="CASCADE"),
        index=True,
    )
    iteration_index: Mapped[int] = mapped_column(Integer)
    iteration_group_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )

    status: Mapped[IterationExecutionStatus] = mapped_column(
        Enum(
            IterationExecutionStatus,
            name="iterationexecutionstatus",
            create_constraint=True,
            native_enum=True,
        ),
        default=IterationExecutionStatus.PENDING,
        index=True,
    )

    parameters: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict)

    result: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    started_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    step_execution: Mapped["StepExecutionModel"] = relationship(
        back_populates="iterations"
    )

    __table_args__ = (
        # iteration_group_id is included so multi-fanout steps don't collide.
        UniqueConstraint(
            "step_id",
            "iteration_group_id",
            "iteration_index",
            name="uq_iteration_execution_key",
        ),
        Index(
            "ix_iteration_executions_instance_step_index",
            "instance_id",
            "step_id",
            "iteration_index",
        ),
    )


class ProviderModel(Base):
    """Keyed by (slug, version). Each install of a new version creates a sibling row.

    Deterministic UUID: uuid5(NAMESPACE_DNS, f"provider.{slug}@{version}").
    Slug and name are not unique across rows.
    """

    __tablename__ = "providers"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), index=True)
    slug: Mapped[str] = mapped_column(String(255), index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    provider_type: Mapped[ProviderType] = mapped_column(
        Enum(
            ProviderType, name="providertype", create_constraint=True, native_enum=True
        )
    )
    endpoint_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    status: Mapped[ProviderStatus] = mapped_column(
        Enum(
            ProviderStatus,
            name="providerstatus",
            create_constraint=True,
            native_enum=True,
        ),
        default=ProviderStatus.ACTIVE,
    )
    config: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    capabilities: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    client_metadata: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    source_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    credentials: Mapped[List["ProviderCredentialModel"]] = relationship(
        back_populates="provider"
    )
    services: Mapped[List["ProviderServiceModel"]] = relationship(
        back_populates="provider"
    )

    __table_args__ = (
        UniqueConstraint("slug", "version", name="uix_provider_slug_version"),
        CheckConstraint(
            "slug LIKE '%/%' AND slug NOT LIKE '/%' AND slug NOT LIKE '%/'",
            name="ck_provider_slug_namespaced",
        ),
        Index(
            "ix_providers_slug_pattern",
            text("slug text_pattern_ops"),
        ),
    )


class ProviderServiceModel(Base):
    __tablename__ = "provider_services"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    provider_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("providers.id")
    )
    service_id: Mapped[str] = mapped_column(String(255), index=True)
    display_name: Mapped[str] = mapped_column(String(255))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    service_type: Mapped[ServiceType] = mapped_column(
        Enum(
            ServiceType,
            name="servicetype",
            create_constraint=True,
            native_enum=True,
            values_callable=lambda x: [e.value for e in x],  # type: ignore[misc]  - SQLAlchemy Enum values_callable lambda; SA type stubs don't type the callable parameter
        ),
        default=ServiceType.CORE,
        server_default="core",
        nullable=False,
    )
    categories: Mapped[List[str]] = mapped_column(JSON, default=list)
    endpoint: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    parameter_schema: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    result_schema: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    example_parameters: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    client_metadata: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    # Denormalized from the parent provider; service-level queries skip the join.
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    provider: Mapped["ProviderModel"] = relationship(back_populates="services")

    __table_args__ = (
        # provider_id already encodes (slug, version), so per-provider uniqueness suffices.
        UniqueConstraint("provider_id", "service_id", name="uix_provider_service_id"),
        Index("ix_provider_services_service_type_active", "service_type", "is_active"),
    )


class ComfyUIWorkflowModel(Base):
    """Catalog row for ComfyUI workflow packages, keyed by (slug, version).

    Mirrors ProviderModel: deterministic UUID, sibling rows per version.
    """

    __tablename__ = "comfyui_workflows"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    slug: Mapped[str] = mapped_column(String(255), index=True)
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    author: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    # Full package content: Studio metadata at top level + ComfyUI graph
    # under `graph`. Workers extract graph; UI/marketplace query metadata.
    json_content: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict)
    source_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    __table_args__ = (
        UniqueConstraint("slug", "version", name="uix_comfyui_workflow_slug_version"),
        CheckConstraint(
            "slug LIKE '%/%' AND slug NOT LIKE '/%' AND slug NOT LIKE '%/'",
            name="ck_comfyui_workflow_slug_namespaced",
        ),
        Index("ix_comfyui_workflows_slug_active", "slug", "is_active"),
        Index(
            "ix_comfyui_workflows_slug_pattern",
            text("slug text_pattern_ops"),
        ),
    )


class ProviderCredentialModel(Base):
    """Provider credential database model."""

    __tablename__ = "provider_credentials"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    provider_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("providers.id")
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id")
    )
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    credential_type: Mapped[str] = mapped_column(String(50))
    secret_data: Mapped[Dict[str, Any]] = mapped_column(JSON)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_token_type: Mapped[bool] = mapped_column(Boolean, default=False)
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    provider: Mapped["ProviderModel"] = relationship(back_populates="credentials")
    organization: Mapped["OrganizationModel"] = relationship()

    __table_args__ = (
        Index("ix_provider_credentials_provider_org", "provider_id", "organization_id"),
    )


class PackageVersionModel(Base):
    """Per-install snapshot of full package JSON content. Enables version pinning + rollback."""

    __tablename__ = "package_versions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    package_type: Mapped[PackageType] = mapped_column(
        Enum(
            PackageType,
            name="packagetype",
            create_constraint=True,
            native_enum=True,
        )
    )
    slug: Mapped[str] = mapped_column(String(255), index=True)
    version: Mapped[str] = mapped_column(String(50))
    json_content: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict)
    source_hash: Mapped[str] = mapped_column(String(64))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    source: Mapped[PackageSource] = mapped_column(
        Enum(
            PackageSource,
            name="packagesource",
            create_constraint=True,
            native_enum=True,
        ),
        default=PackageSource.LOCAL,
    )
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), default=lambda: datetime.now(UTC)
    )

    __table_args__ = (
        UniqueConstraint(
            "slug", "package_type", "version", name="uix_package_versions_slug_type_version"
        ),
        CheckConstraint(
            "slug LIKE '%/%' AND slug NOT LIKE '/%' AND slug NOT LIKE '%/'",
            name="ck_package_versions_slug_namespaced",
        ),
        Index("ix_package_versions_active", "slug", "package_type", "is_active"),
        Index(
            "ix_package_versions_slug_pattern",
            text("slug text_pattern_ops"),
        ),
    )


class QueueModel(Base):
    __tablename__ = "queues"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255))
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id")
    )
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    queue_type: Mapped[QueueType] = mapped_column(
        Enum(QueueType, name="queuetype", create_constraint=True, native_enum=True),
        default=QueueType.DEFAULT,
    )
    status: Mapped[QueueStatus] = mapped_column(
        Enum(QueueStatus, name="queuestatus", create_constraint=True, native_enum=True),
        default=QueueStatus.ACTIVE,
    )
    max_concurrency: Mapped[int] = mapped_column(Integer, default=10)
    max_pending_jobs: Mapped[int] = mapped_column(Integer, default=1000)
    default_timeout_seconds: Mapped[int] = mapped_column(Integer, default=3600)
    resource_requirements: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON, nullable=True
    )
    tags: Mapped[List[str]] = mapped_column(ARRAY(String), default=list)
    client_metadata: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    organization: Mapped["OrganizationModel"] = relationship()

    __table_args__ = (
        UniqueConstraint("name", "organization_id", name="uix_queue_name_org"),
        Index("ix_queues_organization_status", "organization_id", "status"),
    )


class WorkerModel(Base):
    __tablename__ = "workers"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255))
    queue_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("queues.id"), nullable=True
    )
    status: Mapped[WorkerStatus] = mapped_column(
        Enum(
            WorkerStatus, name="workerstatus", create_constraint=True, native_enum=True
        ),
        default=WorkerStatus.OFFLINE,
    )
    capabilities: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    queue_labels: Mapped[List[str]] = mapped_column(PG_ARRAY(String), default=list)
    last_heartbeat: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    current_job_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("queued_jobs.id", ondelete="SET NULL"),
        nullable=True,
    )
    jobs_completed: Mapped[int] = mapped_column(Integer, default=0)
    is_deregistered: Mapped[bool] = mapped_column(Boolean, default=False)

    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    hostname: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Resource metrics - refreshed on each heartbeat.
    cpu_percent: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    memory_percent: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    memory_used_mb: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    memory_total_mb: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    disk_percent: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    gpu_percent: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    gpu_memory_percent: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    queue: Mapped["QueueModel"] = relationship()

    __table_args__ = (
        Index("ix_workers_queue_status", "queue_id", "status"),
        Index("ix_workers_heartbeat", "last_heartbeat"),
    )


class QueuedJobModel(Base):
    __tablename__ = "queued_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    enqueued_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)

    # Legacy column name `job_id`; value is a step_executions.id.
    job_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("step_executions.id"),
        nullable=True,
        index=True,
    )

    instance_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("instances.id"),
        nullable=True,
        index=True,
    )
    queue_name: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, index=True
    )
    priority: Mapped[int] = mapped_column(Integer, default=0, index=True)
    # Broker-facing claim state. Valid values are a subset of StepExecutionStatus,
    # so the unified enum fits without losing a state.
    status: Mapped[StepExecutionStatus] = mapped_column(
        Enum(
            StepExecutionStatus,
            name="stepexecutionstatus",
            create_constraint=True,
            native_enum=True,
        ),
        default=StepExecutionStatus.PENDING,
        index=True,
    )
    payload: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    resource_requirements: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON, nullable=True
    )
    worker_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )
    enqueued_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), default=lambda: datetime.now(UTC), index=True
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    timeout_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True, index=True
    )
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    max_retries: Mapped[int] = mapped_column(
        Integer, default=settings.DEFAULT_MAX_RETRIES
    )
    tags: Mapped[List[str]] = mapped_column(ARRAY(String), default=list)

    output_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    assigned_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    failed_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )

    # User-provided metadata only - never use for system fields.
    client_metadata: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class NotificationModel(Base):
    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id")
    )
    recipient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    message: Mapped[str] = mapped_column(Text)
    status: Mapped[NotificationStatus] = mapped_column(
        Enum(
            NotificationStatus,
            name="notificationstatus",
            create_constraint=True,
            native_enum=True,
        ),
        default=NotificationStatus.SENT,
    )
    priority: Mapped[NotificationPriority] = mapped_column(
        Enum(
            NotificationPriority,
            name="notificationpriority",
            create_constraint=True,
            native_enum=True,
        ),
        default=NotificationPriority.MEDIUM,
    )
    channel_type: Mapped[str] = mapped_column(String(50))
    channel_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("notification_channels.id"), nullable=True
    )
    category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    action_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    read_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    sent_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    client_metadata: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    organization: Mapped["OrganizationModel"] = relationship()
    recipient: Mapped["UserModel"] = relationship(foreign_keys=[recipient_id])
    creator: Mapped["UserModel"] = relationship(foreign_keys=[created_by])
    channel: Mapped[Optional["NotificationChannelModel"]] = relationship()

    __table_args__ = (
        Index("ix_notifications_recipient_status", "recipient_id", "status"),
        Index("ix_notifications_organization_status", "organization_id", "status"),
        Index("ix_notifications_channel_type", "channel_type"),
    )


class NotificationChannelModel(Base):
    __tablename__ = "notification_channels"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id")
    )
    channel_type: Mapped[str] = mapped_column(String(50))
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    channel_config: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    preferences: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    user: Mapped["UserModel"] = relationship()
    organization: Mapped["OrganizationModel"] = relationship()

    __table_args__ = (
        UniqueConstraint("user_id", "channel_type", name="uix_user_channel_type"),
        Index("ix_notification_channels_user", "user_id"),
    )


class OrgFileModel(Base):
    __tablename__ = "org_files"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # job_execution_id + instance_step_id both target step_executions.
    # Legacy column name `job_execution_id` is kept for DTO wire compatibility.
    job_execution_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("step_executions.id", ondelete="CASCADE"),
        nullable=True,
    )
    instance_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("instances.id", ondelete="CASCADE"),
        nullable=True,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE")
    )
    instance_step_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("step_executions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    file_extension: Mapped[str] = mapped_column(String(50))
    file_size: Mapped[int] = mapped_column(Integer)
    mime_type: Mapped[str] = mapped_column(String(100))
    checksum: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    virtual_path: Mapped[str] = mapped_column(String(1024))
    display_name: Mapped[str] = mapped_column(String(255))

    source: Mapped[ResourceSource] = mapped_column(
        Enum(
            ResourceSource,
            name="resourcesource",
            create_constraint=True,
            native_enum=True,
        )
    )

    provider_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("providers.id"), nullable=True
    )
    provider_resource_id: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True
    )
    provider_url: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    download_timestamp: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )

    status: Mapped[ResourceStatus] = mapped_column(
        Enum(
            ResourceStatus,
            name="resourcestatus",
            create_constraint=True,
            native_enum=True,
        ),
        default=ResourceStatus.PENDING,
    )
    resource_metadata: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    has_thumbnail: Mapped[bool] = mapped_column(Boolean, default=False)

    # Display ordering (user-customizable)
    display_order: Mapped[int] = mapped_column(Integer, default=0)

    # Worker that produced this resource (set when remote workers upload files)
    worker_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    # `step_execution` is the canonical relationship; `instance_step` and
    # `job_execution` are aliases on the same FK columns for existing eager-load paths.
    step_execution: Mapped[Optional["StepExecutionModel"]] = relationship(
        back_populates="output_resources",
        foreign_keys="OrgFileModel.instance_step_id",
        overlaps="job_execution",
    )
    job_execution: Mapped[Optional["StepExecutionModel"]] = relationship(
        foreign_keys="OrgFileModel.job_execution_id",
        overlaps="step_execution",
    )
    instance: Mapped[Optional["InstanceModel"]] = relationship()
    organization: Mapped["OrganizationModel"] = relationship()
    provider: Mapped[Optional["ProviderModel"]] = relationship()

    __table_args__ = (
        Index("ix_org_files_job_id", "job_execution_id"),
        Index("ix_org_files_instance_id", "instance_id"),
        Index("ix_org_files_org_id", "organization_id"),
        Index("ix_org_files_status", "status"),
        Index("ix_org_files_source", "source"),
    )


class OrganizationSecretModel(Base):
    """Organization secret database model.

    Provider-agnostic secrets for webhook authentication, internal APIs,
    and expression variables. Secret names are immutable after creation.
    """

    __tablename__ = "organization_secrets"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    name: Mapped[str] = mapped_column(String(255))
    secret_type: Mapped[str] = mapped_column(String(50))
    secret_data: Mapped[Dict[str, Any]] = mapped_column(JSON)
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_protected: Mapped[bool] = mapped_column(
        Boolean, default=False
    )  # Protected secrets cannot be deleted
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    organization: Mapped["OrganizationModel"] = relationship()

    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="uix_org_secret_name"),
        Index("ix_org_secrets_org_active", "organization_id", "is_active"),
    )


# ============================================================================
class SiteContentModel(Base):
    """Site content database model.

    Stores configurable public page content (testimonials, terms, privacy, etc.).
    Content is stored as JSON to allow flexible structure per page.
    System-wide content (not per-org) - tied to the system organization.
    """

    __tablename__ = "site_content"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Page identifier: 'home', 'about', 'terms', 'privacy', 'contact', etc.
    page_id: Mapped[str] = mapped_column(String(100), unique=True, index=True)

    # JSON content structure varies by page:
    # - home: { testimonials: [...], features: [...] }
    # - terms: { content: "markdown text", last_updated: "date" }
    # - privacy: { content: "markdown text", last_updated: "date" }
    # - about: { story: "markdown text" }
    # - contact: { email: "...", phone: "...", address: "..." }
    content: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)

    # Audit fields
    updated_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


# ============================================================================
# Marketplace Catalog Models
# ============================================================================


class MarketplaceCatalogModel(Base):
    """Marketplace catalog database model.

    Stores provider and blueprint catalogs fetched from remote sources (GitHub)
    or uploaded manually. Only one active catalog per type.
    """

    __tablename__ = "marketplace_catalogs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Catalog type: 'providers' or 'blueprints'
    catalog_type: Mapped[CatalogType] = mapped_column(
        Enum(
            CatalogType,
            name="catalogtype",
            create_constraint=True,
            native_enum=True,
        )
    )

    # Source info
    source_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_tag: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # The actual catalog content (JSON)
    catalog_data: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)

    # Version from the catalog JSON
    version: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Status tracking
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    fetch_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Timestamps
    fetched_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    __table_args__ = (
        Index("ix_marketplace_catalogs_type_active", "catalog_type", "is_active"),
        Index("ix_marketplace_catalogs_fetched", "fetched_at"),
    )


class AuditEventModel(Base):
    """Audit event log for tracking admin actions and security events.

    This table stores all auditable events for compliance and security monitoring.
    IMPORTANT: Never store sensitive values (secrets, credentials, passwords) in this table.
    For secret/credential changes, only log that a change occurred, not the actual values.
    """

    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Organization scope - NULL for system-wide events (providers, services, packages)
    # System events are only visible to super_admin
    organization_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=True, index=True
    )

    # Who performed the action - NULL for anonymous actions (e.g. failed login)
    actor_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True
    )
    actor_type: Mapped[AuditActorType] = mapped_column(
        Enum(
            AuditActorType,
            name="auditactortype",
            create_constraint=True,
            native_enum=True,
        ),
        default=AuditActorType.USER,
    )

    # What happened
    action: Mapped[AuditAction] = mapped_column(
        Enum(
            AuditAction,
            name="auditaction",
            create_constraint=True,
            native_enum=True,
        ),
        index=True,
    )

    # What was affected
    resource_type: Mapped[ResourceType] = mapped_column(
        Enum(
            ResourceType,
            name="resourcetype",
            create_constraint=True,
            native_enum=True,
        ),
        index=True,
    )
    resource_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True  # ID of the affected resource
    )
    resource_name: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True  # Human-readable name (preserved after deletion)
    )

    # Event classification for filtering and alerting
    severity: Mapped[AuditSeverity] = mapped_column(
        Enum(
            AuditSeverity,
            name="auditseverity",
            create_constraint=True,
            native_enum=True,
        ),
        default=AuditSeverity.INFO,
        index=True,
    )
    category: Mapped[AuditCategory] = mapped_column(
        Enum(
            AuditCategory,
            name="auditcategory",
            create_constraint=True,
            native_enum=True,
        ),
        default=AuditCategory.CONFIGURATION,
    )

    # What changed - NEVER store secret/credential values here
    # Format: {"field": {"old": "value", "new": "value"}} or {"changed": true} for secrets
    changes: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)

    # Additional context (ip_address, user_agent, session_id, reason, etc.)
    # Note: Named 'event_metadata' to avoid conflict with SQLAlchemy's reserved 'metadata' attribute
    event_metadata: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)

    # Result of the action
    status: Mapped[AuditStatus] = mapped_column(
        Enum(
            AuditStatus,
            name="auditstatus",
            create_constraint=True,
            native_enum=True,
        ),
        default=AuditStatus.SUCCESS,
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Timestamp - immutable, no updated_at since audit logs are append-only
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), default=lambda: datetime.now(UTC), index=True
    )

    # Relationships for easy querying
    organization: Mapped[Optional["OrganizationModel"]] = relationship(
        foreign_keys=[organization_id]
    )
    actor: Mapped[Optional["UserModel"]] = relationship(foreign_keys=[actor_id])

    __table_args__ = (
        # Primary query patterns
        Index("ix_audit_events_org_created", "organization_id", "created_at"),
        Index("ix_audit_events_actor_created", "actor_id", "created_at"),
        Index("ix_audit_events_resource", "resource_type", "resource_id"),
        Index("ix_audit_events_severity_created", "severity", "created_at"),
        Index("ix_audit_events_category_created", "category", "created_at"),
    )


# ============================================================================
# Prompt Models
# ============================================================================


class PromptModel(Base):
    """Prompt database model.

    Stores reusable, configurable text blocks for LLM steps.
    Chunks and variables are stored as JSON (value objects of the aggregate).
    """

    __tablename__ = "prompts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(String(100), default="general")
    chunks: Mapped[List[Dict[str, Any]]] = mapped_column(JSON, default=list)
    variables: Mapped[List[Dict[str, Any]]] = mapped_column(JSON, default=list)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    source: Mapped[PromptSource] = mapped_column(
        Enum(
            PromptSource,
            name="promptsource",
            create_constraint=True,
            native_enum=True,
        ),
        default=PromptSource.CUSTOM,
    )
    marketplace_slug: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    scope: Mapped[PromptScope] = mapped_column(
        Enum(
            PromptScope,
            name="promptscope",
            create_constraint=True,
            native_enum=True,
        ),
        default=PromptScope.ORGANIZATION,
    )
    publish_status: Mapped[Optional[PromptPublishStatus]] = mapped_column(
        Enum(
            PromptPublishStatus,
            name="promptpublishstatus",
            create_constraint=True,
            native_enum=True,
        ),
        nullable=True,
        default=None,
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    organization: Mapped["OrganizationModel"] = relationship(back_populates="prompts")

    __table_args__ = (
        Index("ix_prompts_org_enabled", "organization_id", "is_enabled"),
        Index("ix_prompts_org_category", "organization_id", "category"),
        Index("ix_prompts_org_scope", "organization_id", "scope"),
        Index("ix_prompts_created_by", "created_by"),
        Index(
            "uix_prompt_org_marketplace_slug",
            "organization_id",
            "marketplace_slug",
            unique=True,
            postgresql_where=text("marketplace_slug IS NOT NULL"),
        ),
        CheckConstraint(
            "marketplace_slug IS NULL OR (marketplace_slug LIKE '%/%' AND marketplace_slug NOT LIKE '/%' AND marketplace_slug NOT LIKE '%/')",
            name="ck_prompt_marketplace_slug_namespaced",
        ),
        Index(
            "ix_prompts_marketplace_slug_pattern",
            text("marketplace_slug text_pattern_ops"),
            postgresql_where=text("marketplace_slug IS NOT NULL"),
        ),
    )


class OAuthStateModel(Base):
    """Short-lived OAuth CSRF state. Replaces the in-process dict so any API instance can validate callbacks."""

    __tablename__ = "oauth_states"

    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    data: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )

    __table_args__ = (
        Index("ix_oauth_states_expires_at", "expires_at"),
    )


class SystemSettingModel(Base):
    """Key/value store for system-level flags shared across all API instances."""

    __tablename__ = "system_settings"

    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    value: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
