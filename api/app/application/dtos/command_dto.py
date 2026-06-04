# api/app/application/dtos/command_dto.py

"""Command DTOs carrying user context for audit and authorization."""
import uuid
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

from app.application.defaults import NOTIFICATION_CHANNELS_DEFAULT


class CommandBase(BaseModel):
    user_id: uuid.UUID
    organization_id: uuid.UUID
    correlation_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    client_metadata: Dict[str, Any] = Field(default_factory=dict)


class CreateCommand(CommandBase):
    pass


class UpdateCommand(CommandBase):
    entity_id: uuid.UUID


class DeleteCommand(CommandBase):
    entity_id: uuid.UUID
    force: bool = False


class StateTransitionCommand(CommandBase):
    entity_id: uuid.UUID
    reason: Optional[str] = None


class BulkCommand(CommandBase):
    entity_ids: list[uuid.UUID]


class CreateWorkflowCommand(CreateCommand):
    name: str
    description: Optional[str] = None
    blueprint_id: Optional[uuid.UUID] = None
    client_metadata: Dict[str, Any] = Field(default_factory=dict)


class ActivateWorkflowCommand(StateTransitionCommand):
    pass


class DeactivateWorkflowCommand(StateTransitionCommand):
    pass


class CreateInstanceCommand(CreateCommand):
    workflow_id: uuid.UUID
    input_data: Dict[str, Any] = Field(default_factory=dict)
    client_metadata: Dict[str, Any] = Field(default_factory=dict)


class StartInstanceCommand(StateTransitionCommand):
    pass


class PauseInstanceCommand(StateTransitionCommand):
    pass


class ResumeInstanceCommand(StateTransitionCommand):
    pass


class CancelInstanceCommand(StateTransitionCommand):
    pass


class CreateQueueCommand(CreateCommand):
    name: str
    queue_type: str
    description: Optional[str] = None
    max_concurrency: int = 10
    max_pending_jobs: int = 1000
    default_timeout_seconds: int = 3600
    resource_requirements: Optional[Dict[str, Any]] = None
    client_metadata: Dict[str, Any] = Field(default_factory=dict)


class PauseQueueCommand(StateTransitionCommand):
    pass


class ResumeQueueCommand(StateTransitionCommand):
    pass


class DrainQueueCommand(StateTransitionCommand):
    pass


class StopQueueCommand(StateTransitionCommand):
    force: bool = False


class RegisterProviderCommand(CreateCommand):
    name: str
    provider_type: str
    display_name: Optional[str] = None
    description: Optional[str] = None
    base_url: Optional[str] = None
    capabilities: Dict[str, Any] = Field(default_factory=dict)
    client_metadata: Dict[str, Any] = Field(default_factory=dict)


class ActivateProviderCommand(StateTransitionCommand):
    pass


class DeactivateProviderCommand(StateTransitionCommand):
    pass


class CreateBlueprintCommand(CreateCommand):
    name: str
    description: Optional[str] = None
    category: str = "GENERAL"
    steps: Dict[str, Any] = Field(default_factory=dict)
    client_metadata: Dict[str, Any] = Field(default_factory=dict)


class PublishBlueprintCommand(StateTransitionCommand):
    pass


class ArchiveBlueprintCommand(StateTransitionCommand):
    pass


class CreateOrganizationCommand(CreateCommand):
    name: str
    slug: str
    description: Optional[str] = None
    settings: Dict[str, Any] = Field(default_factory=dict)


class AddUserToOrganizationCommand(CommandBase):
    target_user_id: uuid.UUID
    role: str = "USER"


class RemoveUserFromOrganizationCommand(CommandBase):
    target_user_id: uuid.UUID


class SendNotificationCommand(CreateCommand):
    recipient_id: uuid.UUID
    title: str
    content: str
    category: str = "SYSTEM"
    priority: str = "MEDIUM"
    channels: list[str] = Field(default_factory=lambda: list(NOTIFICATION_CHANNELS_DEFAULT))
    client_metadata: Dict[str, Any] = Field(default_factory=dict)


class MarkNotificationReadCommand(StateTransitionCommand):
    pass


class RegisterWebhookCommand(CreateCommand):
    name: str
    url: str
    events: list[str]
    auth_type: str = "NONE"
    auth_value: Optional[str] = None
    headers: Dict[str, str] = Field(default_factory=dict)
    client_metadata: Dict[str, Any] = Field(default_factory=dict)


class TriggerWebhookCommand(CommandBase):
    webhook_id: uuid.UUID
    event_type: str
    payload: Dict[str, Any]
