# api/app/application/interfaces/service_interfaces.py

"""Application service interface contracts."""

import uuid
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.config.settings import settings
from app.application.dtos import (
    # Instance DTOs
    InstanceResponse,
    InstanceCreate,
    StepExecutionResponse,
    StepExecutionCreate,
    # Notification DTOs
    NotificationResponse,
    NotificationCreate,
    # Organization DTOs
    OrganizationResponse,
    OrganizationCreate,
    OrganizationUpdate,
    UserCreate,
    UserUpdate,
    UserActivation,
    UserResponse,
    # Provider DTOs
    ProviderResponse,
    ProviderCreate,
    ProviderUpdate,
    ProviderServiceResponse,
    ProviderServiceCreate,
    ProviderCredentialResponse,
    ProviderCredentialCreate,
    # Queue DTOs
    QueueResponse,
    QueueCreate,
    QueueUpdate,
    WorkerResponse,
    QueuedJobResponse,
    QueuedJobCreate,
    # Blueprint DTOs
    BlueprintResponse,
    BlueprintCreate,
    BlueprintUpdate,
    # Webhook DTOs
    WebhookResponse,
    CreateWebhookRequest,
    UpdateWebhookRequest,
    ListWebhooksResponse,
    # Workflow DTOs
    WorkflowResponse,
    WorkflowCreate,
    WorkflowUpdate,
)


class InstanceServiceInterface(ABC):
    @abstractmethod
    async def create_instance(self, command: InstanceCreate) -> InstanceResponse:
        pass

    @abstractmethod
    async def get_instance(self, instance_id: uuid.UUID) -> Optional[InstanceResponse]:
        pass

    @abstractmethod
    async def start_instance(
        self, instance_id: uuid.UUID, user_id: uuid.UUID
    ) -> InstanceResponse:
        pass

    @abstractmethod
    async def pause_instance(
        self, instance_id: uuid.UUID, user_id: uuid.UUID
    ) -> InstanceResponse:
        pass

    @abstractmethod
    async def resume_instance(
        self, instance_id: uuid.UUID, user_id: uuid.UUID
    ) -> InstanceResponse:
        pass

    @abstractmethod
    async def cancel_instance(
        self, instance_id: uuid.UUID, user_id: uuid.UUID, reason: str
    ) -> InstanceResponse:
        pass

    @abstractmethod
    async def list_instances(
        self,
        organization_id: uuid.UUID,
        workflow_id: Optional[uuid.UUID] = None,
        status: Optional[str] = None,
        skip: int = 0,
        limit: int = settings.API_PAGE_LIMIT_DEFAULT,
    ) -> List[InstanceResponse]:
        pass

    @abstractmethod
    async def create_job_execution(
        self, command: StepExecutionCreate
    ) -> StepExecutionResponse:
        pass

    @abstractmethod
    async def update_job_status(
        self,
        job_id: uuid.UUID,
        status: str,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> StepExecutionResponse:
        pass


class NotificationServiceInterface(ABC):
    @abstractmethod
    async def create_notification(
        self, command: NotificationCreate
    ) -> NotificationResponse:
        pass

    @abstractmethod
    async def send_notification(
        self, notification_id: uuid.UUID
    ) -> NotificationResponse:
        pass

    @abstractmethod
    async def deliver_notification(
        self, notification_id: uuid.UUID, delivered_at: datetime
    ) -> NotificationResponse:
        pass

    @abstractmethod
    async def fail_notification(
        self, notification_id: uuid.UUID, error: str
    ) -> NotificationResponse:
        pass

    @abstractmethod
    async def retry_notification(
        self, notification_id: uuid.UUID
    ) -> NotificationResponse:
        pass

    @abstractmethod
    async def list_notifications(
        self,
        organization_id: uuid.UUID,
        recipient_id: Optional[uuid.UUID] = None,
        channel: Optional[str] = None,
        status: Optional[str] = None,
        skip: int = 0,
        limit: int = settings.API_PAGE_LIMIT_DEFAULT,
    ) -> List[NotificationResponse]:
        pass


class OrganizationServiceInterface(ABC):
    @abstractmethod
    async def create_organization(
        self, command: OrganizationCreate
    ) -> OrganizationResponse:
        pass

    @abstractmethod
    async def update_organization(
        self, organization_id: uuid.UUID, command: OrganizationUpdate
    ) -> OrganizationResponse:
        pass

    @abstractmethod
    async def activate_organization(
        self, organization_id: uuid.UUID, activated_by: uuid.UUID
    ) -> OrganizationResponse:
        pass

    @abstractmethod
    async def deactivate_organization(
        self, organization_id: uuid.UUID, deactivated_by: uuid.UUID
    ) -> OrganizationResponse:
        pass

    @abstractmethod
    async def create_user(self, command: UserCreate) -> UserResponse:
        pass

    @abstractmethod
    async def get_user(self, user_id: uuid.UUID) -> Optional[UserResponse]:
        pass

    @abstractmethod
    async def update_user(
        self, user_id: uuid.UUID, command: UserUpdate, current_user_id: uuid.UUID
    ) -> UserResponse:
        pass

    @abstractmethod
    async def activate_user(
        self, user_id: uuid.UUID, activated_by: uuid.UUID
    ) -> UserResponse:
        pass

    @abstractmethod
    async def deactivate_user(
        self, user_id: uuid.UUID, deactivated_by: uuid.UUID
    ) -> UserResponse:
        pass

    @abstractmethod
    async def add_user_to_organization(
        self,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        role: str,
        added_by: uuid.UUID,
    ) -> UserResponse:
        pass

    @abstractmethod
    async def remove_user_from_organization(
        self,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        removed_by: uuid.UUID,
    ) -> bool:
        pass

    @abstractmethod
    async def list_organization_users(
        self,
        organization_id: uuid.UUID,
        role: Optional[str] = None,
        skip: int = 0,
        limit: int = settings.API_PAGE_LIMIT_DEFAULT,
    ) -> List[UserResponse]:
        pass

    @abstractmethod
    async def activate_user_with_command(
        self, user_id: uuid.UUID, command: UserActivation
    ) -> UserResponse:
        pass


class ProviderServiceInterface(ABC):
    @abstractmethod
    async def create_provider(self, command: ProviderCreate) -> ProviderResponse:
        pass

    @abstractmethod
    async def update_provider(
        self, provider_id: uuid.UUID, command: ProviderUpdate
    ) -> ProviderResponse:
        pass

    @abstractmethod
    async def activate_provider(
        self, provider_id: uuid.UUID, activated_by: uuid.UUID
    ) -> ProviderResponse:
        pass

    @abstractmethod
    async def deactivate_provider(
        self, provider_id: uuid.UUID, deactivated_by: uuid.UUID
    ) -> ProviderResponse:
        pass

    @abstractmethod
    async def create_provider_service(
        self, command: ProviderServiceCreate
    ) -> ProviderServiceResponse:
        pass

    @abstractmethod
    async def update_provider_service(
        self, service_id: uuid.UUID, updates: Dict[str, Any]
    ) -> ProviderServiceResponse:
        pass

    @abstractmethod
    async def create_credential(
        self, command: ProviderCredentialCreate
    ) -> ProviderCredentialResponse:
        pass

    @abstractmethod
    async def update_credential(
        self, credential_id: uuid.UUID, credentials: Dict[str, Any]
    ) -> ProviderCredentialResponse:
        pass

    @abstractmethod
    async def provider_connection_test(self, provider_id: uuid.UUID) -> bool:
        pass

    @abstractmethod
    async def list_providers(
        self,
        organization_id: uuid.UUID,
        provider_type: Optional[str] = None,
        status: Optional[str] = None,
        skip: int = 0,
        limit: int = settings.API_PAGE_LIMIT_DEFAULT,
    ) -> List[ProviderResponse]:
        pass

    @abstractmethod
    async def list_provider_services(
        self,
        provider_id: uuid.UUID,
        service_type: Optional[str] = None,
        skip: int = 0,
        limit: int = settings.API_PAGE_LIMIT_DEFAULT,
    ) -> List[ProviderServiceResponse]:
        pass


class QueueServiceInterface(ABC):
    @abstractmethod
    async def create_queue(self, command: QueueCreate) -> QueueResponse:
        pass

    @abstractmethod
    async def update_queue(
        self, queue_id: uuid.UUID, command: QueueUpdate
    ) -> QueueResponse:
        pass

    @abstractmethod
    async def pause_queue(
        self, queue_id: uuid.UUID, paused_by: uuid.UUID
    ) -> QueueResponse:
        pass

    @abstractmethod
    async def resume_queue(
        self, queue_id: uuid.UUID, resumed_by: uuid.UUID
    ) -> QueueResponse:
        pass

    @abstractmethod
    async def drain_queue(
        self, queue_id: uuid.UUID, drained_by: uuid.UUID
    ) -> QueueResponse:
        pass

    @abstractmethod
    async def stop_queue(
        self, queue_id: uuid.UUID, stopped_by: uuid.UUID
    ) -> QueueResponse:
        pass

    @abstractmethod
    async def enqueue_job(self, command: QueuedJobCreate) -> QueuedJobResponse:
        pass

    @abstractmethod
    async def complete_job(
        self, job_id: uuid.UUID, result: Dict[str, Any]
    ) -> QueuedJobResponse:
        pass

    @abstractmethod
    async def fail_job(self, job_id: uuid.UUID, error: str) -> QueuedJobResponse:
        pass

    @abstractmethod
    async def list_queues(
        self,
        organization_id: uuid.UUID,
        status: Optional[str] = None,
        skip: int = 0,
        limit: int = settings.API_PAGE_LIMIT_DEFAULT,
    ) -> List[QueueResponse]:
        pass

    @abstractmethod
    async def list_workers(
        self,
        queue_id: uuid.UUID,
        status: Optional[str] = None,
        skip: int = 0,
        limit: int = settings.API_PAGE_LIMIT_DEFAULT,
    ) -> List[WorkerResponse]:
        pass

    @abstractmethod
    async def list_jobs(
        self,
        queue_id: uuid.UUID,
        status: Optional[str] = None,
        skip: int = 0,
        limit: int = settings.API_PAGE_LIMIT_DEFAULT,
    ) -> List[QueuedJobResponse]:
        pass


class BlueprintServiceInterface(ABC):
    @abstractmethod
    async def create_blueprint(self, command: BlueprintCreate) -> BlueprintResponse:
        pass

    @abstractmethod
    async def update_blueprint(
        self, blueprint_id: uuid.UUID, command: BlueprintUpdate
    ) -> BlueprintResponse:
        pass

    @abstractmethod
    async def publish_blueprint(
        self,
        blueprint_id: uuid.UUID,
    ) -> BlueprintResponse:
        pass

    @abstractmethod
    async def archive_blueprint(
        self, blueprint_id: uuid.UUID, archived_by: uuid.UUID
    ) -> BlueprintResponse:
        pass

    @abstractmethod
    async def add_step(
        self,
        blueprint_id: uuid.UUID,
        step_id: str,
        step_config: Dict[str, Any],
        added_by: uuid.UUID,
    ) -> BlueprintResponse:
        pass

    @abstractmethod
    async def remove_step(
        self, blueprint_id: uuid.UUID, step_id: str, removed_by: uuid.UUID
    ) -> BlueprintResponse:
        pass

    @abstractmethod
    async def update_step(
        self,
        blueprint_id: uuid.UUID,
        step_id: str,
        step_config: Dict[str, Any],
        updated_by: uuid.UUID,
    ) -> BlueprintResponse:
        pass

    @abstractmethod
    async def validate_blueprint(self, blueprint_id: uuid.UUID) -> Dict[str, Any]:
        pass

    @abstractmethod
    async def create_workflow_from_blueprint(
        self,
        blueprint_id: uuid.UUID,
        workflow_name: str,
        created_by: uuid.UUID,
    ) -> WorkflowResponse:
        pass

    @abstractmethod
    async def list_blueprints(
        self,
        organization_id: uuid.UUID,
        status: Optional[str] = None,
        skip: int = 0,
        limit: int = settings.API_PAGE_LIMIT_DEFAULT,
    ) -> List[BlueprintResponse]:
        pass


class WebhookServiceInterface(ABC):
    """Inbound-only webhooks: external HTTP calls trigger workflow runs."""

    @abstractmethod
    async def create_webhook(
        self,
        request: CreateWebhookRequest,
        organization_id: uuid.UUID,
        created_by: uuid.UUID,
        organization_slug: str,
    ) -> WebhookResponse:
        pass

    @abstractmethod
    async def update_webhook(
        self,
        webhook_id: uuid.UUID,
        request: UpdateWebhookRequest,
        updated_by: uuid.UUID,
        organization_id: uuid.UUID,
        organization_slug: str,
    ) -> WebhookResponse:
        pass

    @abstractmethod
    async def get_webhook(
        self,
        webhook_id: uuid.UUID,
        organization_id: uuid.UUID,
        organization_slug: str,
    ) -> WebhookResponse:
        pass

    @abstractmethod
    async def list_webhooks(
        self,
        organization_id: uuid.UUID,
        organization_slug: str,
        skip: int = 0,
        limit: int = settings.API_PAGE_LIMIT_DEFAULT,
    ) -> ListWebhooksResponse:
        pass

    @abstractmethod
    async def delete_webhook(
        self,
        webhook_id: uuid.UUID,
        organization_id: uuid.UUID,
    ) -> bool:
        pass

    @abstractmethod
    async def handle_incoming_webhook(
        self,
        organization_slug: str,
        webhook_slug: str,
        payload: Dict[str, Any],
        headers: Dict[str, str],
    ) -> Dict[str, Any]:
        pass


class WorkflowServiceInterface(ABC):
    @abstractmethod
    async def create_workflow(self, command: WorkflowCreate) -> WorkflowResponse:
        pass

    @abstractmethod
    async def update_workflow(
        self, workflow_id: uuid.UUID, command: WorkflowUpdate
    ) -> WorkflowResponse:
        pass

    @abstractmethod
    async def activate_workflow(
        self, workflow_id: uuid.UUID, activated_by: uuid.UUID
    ) -> WorkflowResponse:
        pass

    @abstractmethod
    async def deactivate_workflow(
        self, workflow_id: uuid.UUID, deactivated_by: uuid.UUID
    ) -> WorkflowResponse:
        pass

    @abstractmethod
    async def add_step(
        self,
        workflow_id: uuid.UUID,
        step_id: str,
        step_config: Dict[str, Any],
        added_by: uuid.UUID,
    ) -> WorkflowResponse:
        pass

    @abstractmethod
    async def remove_step(
        self, workflow_id: uuid.UUID, step_id: str, removed_by: uuid.UUID
    ) -> WorkflowResponse:
        pass

    @abstractmethod
    async def update_step(
        self,
        workflow_id: uuid.UUID,
        step_id: str,
        step_config: Dict[str, Any],
        updated_by: uuid.UUID,
    ) -> WorkflowResponse:
        pass

    @abstractmethod
    async def validate_workflow(self, workflow_id: uuid.UUID) -> Dict[str, Any]:
        pass

    @abstractmethod
    async def create_instance(
        self,
        workflow_id: uuid.UUID,
        input_data: Dict[str, Any],
        created_by: uuid.UUID,
    ) -> InstanceResponse:
        pass

    @abstractmethod
    async def list_workflows(
        self,
        organization_id: uuid.UUID,
        blueprint_id: Optional[uuid.UUID] = None,
        status: Optional[str] = None,
        skip: int = 0,
        limit: int = settings.API_PAGE_LIMIT_DEFAULT,
    ) -> List[WorkflowResponse]:
        pass

    @abstractmethod
    async def get_instances(
        self,
        workflow_id: uuid.UUID,
        status: Optional[str] = None,
        skip: int = 0,
        limit: int = settings.API_PAGE_LIMIT_DEFAULT,
    ) -> List[InstanceResponse]:
        pass
