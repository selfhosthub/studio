# api/app/domain/common/events.py

"""Domain events: base classes and concrete event types."""

from datetime import UTC, datetime
from typing import Any, Dict, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DomainEvent(BaseModel):
    """Something that happened in the domain that domain experts care about."""

    event_type: str
    aggregate_id: UUID
    aggregate_type: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    data: Dict[str, Any] = Field(default_factory=dict)
    client_metadata: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(arbitrary_types_allowed=True)


class OrganizationEvent(DomainEvent):
    aggregate_type: str = "organization"
    organization_id: UUID


class UserEvent(DomainEvent):
    aggregate_type: str = "user"
    user_id: UUID
    organization_id: Optional[UUID] = None


class WorkflowEvent(DomainEvent):
    aggregate_type: str = "workflow"
    workflow_id: UUID
    organization_id: UUID


class BlueprintEvent(DomainEvent):
    aggregate_type: str = "blueprint"
    blueprint_id: UUID
    organization_id: UUID


class StepEvent(DomainEvent):
    aggregate_type: str = "step"
    step_id: UUID
    organization_id: UUID


class InstanceEvent(DomainEvent):
    aggregate_type: str = "instance"
    instance_id: UUID
    workflow_id: UUID
    organization_id: UUID


class JobEvent(DomainEvent):
    aggregate_type: str = "job"
    job_id: UUID
    instance_id: UUID
    organization_id: UUID


class ProviderEvent(DomainEvent):
    aggregate_type: str = "provider"
    provider_id: UUID
    organization_id: UUID


class NotificationEvent(DomainEvent):
    aggregate_type: str = "notification"
    notification_id: UUID
    organization_id: UUID
    user_id: Optional[UUID] = None


class OrganizationCreatedEvent(OrganizationEvent):
    event_type: str = "organization.created"


class OrganizationUpdatedEvent(OrganizationEvent):
    event_type: str = "organization.updated"


class OrganizationActivatedEvent(OrganizationEvent):
    event_type: str = "organization.activated"


class OrganizationDeactivatedEvent(OrganizationEvent):
    event_type: str = "organization.deactivated"


class OrganizationDeletedEvent(OrganizationEvent):
    event_type: str = "organization.deleted"


class OrganizationStatusChangedEvent(OrganizationEvent):
    event_type: str = "organization.status_changed"
    old_status: str
    new_status: str


class OrganizationSuspendedEvent(OrganizationEvent):
    event_type: str = "organization.suspended"


class UserCreatedEvent(UserEvent):
    event_type: str = "user.created"


class UserAddedToOrganizationEvent(UserEvent):
    event_type: str = "user.added_to_organization"


class UserRemovedFromOrganizationEvent(UserEvent):
    event_type: str = "user.removed_from_organization"


class UserActivatedEvent(UserEvent):
    event_type: str = "user.activated"


class UserDeactivatedEvent(UserEvent):
    event_type: str = "user.deactivated"


class UserSuspendedEvent(UserEvent):
    event_type: str = "user.suspended"


class UserEmailVerifiedEvent(UserEvent):
    event_type: str = "user.email_verified"


class UserPasswordChangedEvent(UserEvent):
    event_type: str = "user.password_changed"


class UserRoleChangedEvent(UserEvent):
    event_type: str = "user.role_changed"
    old_role: str
    new_role: str


class UserProfileUpdatedEvent(UserEvent):
    event_type: str = "user.profile_updated"


class UserLoginEvent(UserEvent):
    event_type: str = "user.login"
    login_time: datetime


class WorkflowCreatedEvent(WorkflowEvent):
    event_type: str = "workflow.created"


class WorkflowUpdatedEvent(WorkflowEvent):
    event_type: str = "workflow.updated"


class WorkflowActivatedEvent(WorkflowEvent):
    event_type: str = "workflow.activated"


class WorkflowDeactivatedEvent(WorkflowEvent):
    event_type: str = "workflow.deactivated"


class WorkflowDeletedEvent(WorkflowEvent):
    event_type: str = "workflow.deleted"


class BlueprintCreatedEvent(BlueprintEvent):
    event_type: str = "blueprint.created"


class BlueprintUpdatedEvent(BlueprintEvent):
    event_type: str = "blueprint.updated"


class BlueprintDeletedEvent(BlueprintEvent):
    event_type: str = "blueprint.deleted"


class JobCreatedEvent(JobEvent):
    event_type: str = "job.created"


class JobStartedEvent(JobEvent):
    event_type: str = "job.started"


class JobCompletedEvent(JobEvent):
    event_type: str = "job.completed"


class JobFailedEvent(JobEvent):
    event_type: str = "job.failed"


class JobCanceledEvent(JobEvent):
    event_type: str = "job.canceled"


class JobStatusChangedEvent(JobEvent):
    event_type: str = "job.status_changed"


class ProviderCreatedEvent(ProviderEvent):
    event_type: str = "provider.created"


class ProviderUpdatedEvent(ProviderEvent):
    event_type: str = "provider.updated"


class ProviderDeletedEvent(ProviderEvent):
    event_type: str = "provider.deleted"


class ProviderActivatedEvent(ProviderEvent):
    event_type: str = "provider.activated"


class ProviderDeactivatedEvent(ProviderEvent):
    event_type: str = "provider.deactivated"


class StepCreatedEvent(StepEvent):
    event_type: str = "step.created"


class StepUpdatedEvent(StepEvent):
    event_type: str = "step.updated"


class StepDeletedEvent(StepEvent):
    event_type: str = "step.deleted"


class NotificationCreatedEvent(NotificationEvent):
    event_type: str = "notification.created"


class NotificationReadEvent(NotificationEvent):
    event_type: str = "notification.read"


class NotificationDeletedEvent(NotificationEvent):
    event_type: str = "notification.deleted"
