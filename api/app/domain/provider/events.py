# api/app/domain/provider/events.py

"""Domain events for the provider context."""
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, Optional
from uuid import UUID

from app.domain.common.events import DomainEvent


class ProviderEvent(DomainEvent):
    provider_id: UUID


class ProviderCreatedEvent(ProviderEvent):
    event_type: str = "provider.created"
    name: str
    provider_type: str


class ProviderUpdatedEvent(ProviderEvent):
    event_type: str = "provider.updated"
    changes: Dict[str, Any]


class ProviderDeletedEvent(ProviderEvent):
    event_type: str = "provider.deleted"


class ProviderActivatedEvent(ProviderEvent):
    event_type: str = "provider.activated"


class ProviderDeactivatedEvent(ProviderEvent):
    event_type: str = "provider.deactivated"


class ProviderSuspendedEvent(ProviderEvent):
    event_type: str = "provider.suspended"


class ProviderErrorEvent(ProviderEvent):
    event_type: str = "provider.error"
    error: str


class ServiceEvent(DomainEvent):
    provider_id: UUID
    service_id: UUID


class ServiceCreatedEvent(ServiceEvent):
    event_type: str = "provider.service.created"
    service_name: str
    service_type: str


class ServiceRegisteredEvent(ServiceEvent):
    event_type: str = "provider.service.registered"
    service_name: str
    service_type: str
    registered_by: UUID


class ServiceUpdatedEvent(ServiceEvent):
    event_type: str = "provider.service.updated"
    changes: Dict[str, Any]


class ServiceDeletedEvent(ServiceEvent):
    event_type: str = "provider.service.deleted"


class CredentialEvent(DomainEvent):
    provider_id: UUID
    credential_id: UUID
    organization_id: UUID


class CredentialAddedEvent(CredentialEvent):
    event_type: str = "provider.credential.added"
    credential_name: str
    credential_type: str
    added_by: UUID


class CredentialUpdatedEvent(CredentialEvent):
    event_type: str = "provider.credential.updated"
    updated_by: UUID


class CredentialRotatedEvent(CredentialEvent):
    event_type: str = "provider.credential.rotated"
    rotated_by: UUID


class CredentialValidatedEvent(CredentialEvent):
    event_type: str = "provider.credential.validated"
    is_valid: bool
    validated_by: UUID


class CredentialExpiredEvent(CredentialEvent):
    event_type: str = "provider.credential.expired"
    expired_at: datetime


class CredentialDeletedEvent(CredentialEvent):
    event_type: str = "provider.credential.deleted"
    deleted_by: UUID


class ResourceEvent(DomainEvent):
    provider_id: UUID
    resource_id: UUID
    organization_id: UUID
    resource_type: str


class ResourceRegisteredEvent(ResourceEvent):
    event_type: str = "provider.resource.registered"
    created_by: UUID
    job_id: Optional[UUID] = None


class ResourceDeactivatedEvent(ResourceEvent):
    event_type: str = "provider.resource.deactivated"
    deactivated_by: UUID
    reason: Optional[str] = None


class ResourceProvisionedEvent(ResourceEvent):
    event_type: str = "provider.resource.provisioned"
    external_id: str
    external_url: Optional[str] = None
    actual_specs: Dict[str, Any]


class ResourceStartedEvent(ResourceEvent):
    event_type: str = "provider.resource.started"
    started_by: UUID


class ResourceStoppedEvent(ResourceEvent):
    event_type: str = "provider.resource.stopped"
    stopped_by: UUID
    reason: Optional[str] = None


class ResourceTerminatingEvent(ResourceEvent):
    event_type: str = "provider.resource.terminating"
    reason: str
    terminated_by: Optional[UUID] = None


class ResourceTerminatedEvent(ResourceEvent):
    event_type: str = "provider.resource.terminated"
    reason: str
    total_cost: Decimal
    runtime_hours: float


class ResourceFailedEvent(ResourceEvent):
    event_type: str = "provider.resource.failed"
    error: str
    failure_count: int


class ResourceExpiredEvent(ResourceEvent):
    event_type: str = "provider.resource.expired"
    expired_at: datetime


class ResourceHealthEvent(ResourceEvent):
    event_type: str = "provider.resource.health_updated"
    health_status: str
    cpu_utilization: Optional[float] = None
    memory_utilization: Optional[float] = None
    gpu_utilization: Optional[float] = None


class ResourceCostEvent(ResourceEvent):
    event_type: str = "provider.resource.cost_updated"
    hourly_cost: Decimal
    total_cost: Decimal
    hours_billed: float
    billing_period: str


class ResourceQuotaExceededEvent(ProviderEvent):
    event_type: str = "provider.resource.quota_exceeded"
    resource_type: str
    requested: int
    quota: int
    current_usage: int
