# api/app/application/dtos/provider_dto.py

"""DTOs for provider operations."""
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.domain.provider.models import (
    Provider,
    ProviderCredential,
    ProviderService,
    ProviderType,
    ServiceType,
    CredentialType,
)


class ProviderBase(BaseModel):
    name: str
    slug: str
    provider_type: ProviderType
    # Keyed by (slug, version); version must match MAJOR.MINOR.PATCH.
    version: str
    description: Optional[str] = None
    endpoint_url: Optional[str] = None
    config: Dict[str, Any] = Field(default_factory=dict)
    capabilities: Dict[str, Any] = Field(default_factory=dict)
    client_metadata: Dict[str, Any] = Field(default_factory=dict)


class ProviderCreate(ProviderBase):
    created_by: Optional[uuid.UUID] = None


class ProviderUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    endpoint_url: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    capabilities: Optional[Dict[str, Any]] = None
    client_metadata: Optional[Dict[str, Any]] = None
    status: Optional[str] = None


class ProviderResponse(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    provider_type: ProviderType
    description: Optional[str]
    endpoint_url: Optional[str]
    status: str
    config: Dict[str, Any]
    capabilities: Dict[str, Any]
    client_metadata: Dict[str, Any]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    version: Optional[str] = None
    services: List["ProviderServiceResponse"] = Field(default_factory=list)
    service_types: List[ServiceType] = Field(
        default_factory=list,
        description="Aggregated list of service types supported by this provider",
    )

    @classmethod
    def from_domain(
        cls,
        provider: Provider,
        services: Optional[List["ProviderServiceResponse"]] = None,
    ) -> "ProviderResponse":
        services_list = services or []

        all_cats: set[ServiceType] = set()
        for s in services_list:
            if s.categories:
                for c in s.categories:
                    try:
                        all_cats.add(ServiceType(c))
                    except ValueError:
                        pass
            else:
                all_cats.add(s.service_type)
        service_types = list(all_cats)

        return cls(
            id=provider.id,
            name=provider.name,
            slug=provider.slug,
            provider_type=provider.provider_type,
            description=provider.description,
            endpoint_url=provider.endpoint_url,
            status=provider.status.value,
            config=provider.config,
            capabilities=provider.capabilities,
            client_metadata=provider.client_metadata,
            version=provider.version,
            created_at=provider.created_at,
            updated_at=provider.updated_at,
            services=services_list,
            service_types=service_types,
        )


class ProviderServiceBase(BaseModel):
    provider_id: uuid.UUID
    service_id: str
    display_name: str
    service_type: ServiceType
    categories: List[str] = Field(default_factory=list)
    description: Optional[str] = None
    endpoint: Optional[str] = None
    parameter_schema: Dict[str, Any] = Field(default_factory=dict)
    result_schema: Dict[str, Any] = Field(default_factory=dict)
    example_parameters: Dict[str, Any] = Field(default_factory=dict)
    client_metadata: Dict[str, Any] = Field(default_factory=dict)


class ProviderServiceCreate(ProviderServiceBase):
    created_by: Optional[uuid.UUID] = None


class ProviderServiceUpdate(BaseModel):
    display_name: Optional[str] = None
    description: Optional[str] = None
    endpoint: Optional[str] = None
    parameter_schema: Optional[Dict[str, Any]] = None
    result_schema: Optional[Dict[str, Any]] = None
    example_parameters: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None
    client_metadata: Optional[Dict[str, Any]] = None


class ProviderServiceResponse(BaseModel):
    id: uuid.UUID
    provider_id: uuid.UUID
    service_id: str
    display_name: str
    service_type: ServiceType
    categories: List[str] = Field(default_factory=list)
    description: Optional[str]
    endpoint: Optional[str]
    parameter_schema: Dict[str, Any]
    result_schema: Dict[str, Any]
    example_parameters: Dict[str, Any]
    is_active: bool
    client_metadata: Dict[str, Any]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    @classmethod
    def from_domain(cls, service: ProviderService) -> "ProviderServiceResponse":
        return cls(
            id=service.id,
            provider_id=service.provider_id,
            service_id=service.service_id,
            display_name=service.display_name,
            service_type=service.service_type,
            categories=service.categories,
            description=service.description,
            endpoint=service.endpoint,
            parameter_schema=service.parameter_schema,
            result_schema=service.result_schema,
            example_parameters=service.example_parameters,
            is_active=service.is_active,
            client_metadata=service.client_metadata,
            created_at=service.created_at,
            updated_at=service.updated_at,
        )


class ProviderCredentialBase(BaseModel):
    provider_id: uuid.UUID
    organization_id: uuid.UUID
    credential_type: CredentialType
    name: str
    description: Optional[str] = None
    expires_at: Optional[datetime] = None
    client_metadata: Dict[str, Any] = Field(default_factory=dict)


class ProviderCredentialCreate(ProviderCredentialBase):
    credentials: Dict[str, Any]
    created_by: uuid.UUID
    # If True, secret can only be viewed at creation.
    is_token_type: bool = False


class ProviderCredentialUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    credentials: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None
    expires_at: Optional[datetime] = None
    client_metadata: Optional[Dict[str, Any]] = None


class ProviderCredentialResponse(BaseModel):
    id: uuid.UUID
    provider_id: uuid.UUID
    organization_id: uuid.UUID
    credential_type: CredentialType
    name: str
    description: Optional[str]
    is_active: bool
    # If True, secret can only be viewed at creation.
    is_token_type: bool = False
    # client_id + client_secret present (org-managed OAuth).
    has_client_credentials: bool = False
    # access_token present (OAuth authorization completed).
    has_access_token: bool = False
    expires_at: Optional[datetime]
    created_by: uuid.UUID
    client_metadata: Dict[str, Any]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    @classmethod
    def from_domain(
        cls, credential: ProviderCredential
    ) -> "ProviderCredentialResponse":
        creds = credential.credentials or {}
        return cls(
            id=credential.id,
            provider_id=credential.provider_id,
            organization_id=credential.organization_id,
            credential_type=credential.credential_type,
            name=credential.name,
            description=credential.description,
            is_active=credential.is_active,
            is_token_type=getattr(credential, "is_token_type", False),
            has_client_credentials=bool(
                creds.get("client_id") and creds.get("client_secret")
            ),
            has_access_token=bool(creds.get("access_token")),
            expires_at=credential.expires_at,
            created_by=credential.created_by,
            client_metadata=credential.client_metadata,
            created_at=credential.created_at,
            updated_at=credential.updated_at,
        )


class ProviderCredentialWithSecretResponse(ProviderCredentialResponse):
    """Credential response including the decrypted secret (reveal endpoint only)."""

    credentials: Dict[str, Any]

    @classmethod
    def from_domain(
        cls, credential: ProviderCredential
    ) -> "ProviderCredentialWithSecretResponse":
        return cls(
            id=credential.id,
            provider_id=credential.provider_id,
            organization_id=credential.organization_id,
            credential_type=credential.credential_type,
            name=credential.name,
            description=credential.description,
            is_active=credential.is_active,
            is_token_type=getattr(credential, "is_token_type", False),
            expires_at=credential.expires_at,
            created_by=credential.created_by,
            client_metadata=credential.client_metadata,
            created_at=credential.created_at,
            updated_at=credential.updated_at,
            credentials=credential.credentials,
        )


class ProviderTestConnection(BaseModel):
    provider_id: uuid.UUID
    test_type: Optional[str] = "basic"
    parameters: Dict[str, Any] = Field(default_factory=dict)


class ProviderTestResult(BaseModel):
    provider_id: uuid.UUID
    is_connected: bool
    response_time_ms: Optional[float] = None
    error_message: Optional[str] = None
    test_timestamp: datetime
    additional_info: Dict[str, Any] = Field(default_factory=dict)


class ProviderMetrics(BaseModel):
    provider_id: uuid.UUID
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    average_response_time_ms: float = 0.0
    active_resources: int = 0
    total_resources_allocated: int = 0
    last_request_at: Optional[datetime] = None
    uptime_percentage: float = 0.0
    metrics_period_start: datetime
    metrics_period_end: datetime
