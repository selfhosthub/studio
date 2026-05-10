# api/app/presentation/api/models/provider.py

"""Pydantic models for provider API endpoints."""
from datetime import datetime
from typing import Any, Dict, List, Optional, cast

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.provider.models import ProviderStatus, ProviderType, ServiceType


class ProviderBase(BaseModel):
    """Base model for provider data."""

    name: str = Field(..., description="Provider name")
    description: Optional[str] = Field(default=None, description="Provider description")
    provider_type: ProviderType = Field(..., description="Provider type")
    endpoint_url: Optional[str] = Field(
        default=None, description="Provider endpoint URL"
    )
    config: Dict[str, Any] = Field(
        default_factory=dict, description="Provider configuration"
    )
    capabilities: Dict[str, Any] = Field(
        default_factory=dict, description="Provider capabilities"
    )


class ProviderCreate(ProviderBase):
    pass


class ProviderUpdate(BaseModel):
    name: Optional[str] = Field(default=None, description="Provider name")
    description: Optional[str] = Field(default=None, description="Provider description")
    endpoint_url: Optional[str] = Field(
        default=None, description="Provider endpoint URL"
    )
    config: Optional[Dict[str, Any]] = Field(
        default=None, description="Provider configuration"
    )
    capabilities: Optional[Dict[str, Any]] = Field(
        None, description="Provider capabilities"
    )


class ProviderRead(ProviderBase):
    """Provider response model."""

    id: UUID
    slug: str = Field(..., description="Unique provider slug (e.g. 'openai')")
    status: ProviderStatus
    client_metadata: Dict[str, Any]
    created_at: datetime
    updated_at: datetime
    services: List["ProviderServiceRead"] = Field(
        default_factory=list, description="Provider services"
    )
    service_types: List[ServiceType] = Field(
        default_factory=list,
        description="Aggregated list of service types supported by this provider",
    )

    tier: Optional[str] = Field(
        default=None, description="Provider tier: 'built-in', 'basic', or 'premium'"
    )
    system: Optional[bool] = Field(
        default=None,
        description="Whether this is a system/dev provider (e.g., httpbin, mock-service)",
    )
    credential_provider: Optional[str] = Field(
        default=None,
        description="Slug of provider to use for credentials (for credential sharing)",
    )
    requires: Optional[List[str]] = Field(
        default=None, description="List of provider slugs this provider depends on"
    )
    version: Optional[str] = Field(
        default=None, description="Installed package version"
    )

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_orm_with_metadata(cls, obj: Any) -> "ProviderRead":
        """ORM build that lifts marketplace fields out of client_metadata."""
        client_metadata: Dict[str, Any] = obj.client_metadata or {}
        services: List["ProviderServiceRead"] = (
            obj.services if hasattr(obj, "services") else []
        )
        service_types: List[ServiceType] = (
            obj.service_types if hasattr(obj, "service_types") else []
        )

        return cls(
            id=obj.id,
            name=obj.name,
            slug=obj.slug,
            description=obj.description,
            provider_type=obj.provider_type,
            endpoint_url=obj.endpoint_url,
            config=obj.config or {},
            capabilities=obj.capabilities or {},
            status=obj.status,
            client_metadata=client_metadata,
            created_at=obj.created_at,
            updated_at=obj.updated_at,
            services=services,
            service_types=service_types,
            tier=cast(Optional[str], client_metadata.get("tier")),
            system=cast(Optional[bool], client_metadata.get("system")),
            credential_provider=cast(
                Optional[str], client_metadata.get("credential_provider")
            ),
            requires=cast(Optional[List[str]], client_metadata.get("requires")),
            version=getattr(obj, "version", None),
        )


class CredentialBase(BaseModel):
    """Base model for credential data."""

    name: str = Field(..., description="Credential name")
    credential_type: str = Field(..., description="Credential type")
    secret_data: Dict[str, Any] = Field(..., description="Secret data to store")
    expires_at: Optional[datetime] = Field(default=None, description="Expiration date")


class CredentialCreate(CredentialBase):
    is_token_type: bool = Field(
        default=False,
        description="For 'custom' type: if True, secret can only be viewed at creation time (like OAuth tokens)",
    )


class CredentialUpdate(BaseModel):
    name: Optional[str] = Field(default=None, description="New credential name")
    credential_type: Optional[str] = Field(
        default=None, description="New credential type"
    )
    secret_data: Optional[Dict[str, Any]] = Field(
        default=None, description="New secret data"
    )
    is_active: Optional[bool] = Field(default=None, description="Set active status")
    expires_at: Optional[datetime] = Field(
        default=None, description="New expiration date"
    )


class CredentialRead(BaseModel):
    """Credential response model."""

    id: UUID
    provider_id: UUID
    name: str
    credential_type: str
    is_active: bool
    is_token_type: bool = Field(
        default=False,
        description="If True, this credential type cannot be revealed after creation",
    )
    has_client_credentials: bool = Field(
        default=False,
        description="True if credential has client_id + client_secret (org-managed OAuth)",
    )
    has_access_token: bool = Field(
        default=False,
        description="True if credential has an access_token (OAuth completed)",
    )
    expires_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CredentialReadWithSecret(CredentialRead):
    """Credential response model with secret data (for creation response or admin reveal)."""

    secret_data: Dict[str, Any] = Field(
        ..., description="The secret data (only shown once for token types)"
    )


class CredentialRevealResponse(BaseModel):
    """Response for revealing a credential's secret."""

    secret_data: Dict[str, Any] = Field(..., description="The revealed secret data")
    revealed_at: datetime = Field(
        ..., description="Timestamp when the secret was revealed"
    )
    credential_id: UUID = Field(..., description="The credential ID")
    credential_type: str = Field(..., description="The credential type")


class CredentialRevealError(BaseModel):
    """Error response when credential cannot be revealed."""

    error: str = Field(..., description="Error code")
    reason: str = Field(..., description="Human-readable reason")
    credential_type: str = Field(
        ..., description="The credential type that was requested"
    )


class ProviderServiceBase(BaseModel):
    """Base model for provider service data."""

    service_id: str = Field(
        ...,
        description="Unique identifier for the service (e.g., 'myprovider.my_service')",
    )
    display_name: str = Field(..., description="Display name for the service")
    description: Optional[str] = Field(default=None, description="Service description")
    service_type: ServiceType = Field(
        ...,
        description="Primary service type category (AI, STORAGE, COMMUNICATION, etc.)",
    )
    categories: List[str] = Field(
        default_factory=list,
        description="All categories this service belongs to (e.g., ['core', 'flow'])",
    )
    endpoint: Optional[str] = Field(default=None, description="Service endpoint URL")
    parameter_schema: Dict[str, Any] = Field(
        default_factory=dict, description="JSON Schema for parameters"
    )
    result_schema: Dict[str, Any] = Field(
        default_factory=dict, description="JSON Schema for results"
    )
    example_parameters: Dict[str, Any] = Field(
        default_factory=dict, description="Example parameters"
    )
    is_active: bool = Field(True, description="Whether the service is active")
    client_metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata"
    )


class ProviderServiceCreate(ProviderServiceBase):
    pass


class ProviderServiceUpdate(BaseModel):
    display_name: Optional[str] = Field(
        None, description="Display name for the service"
    )
    description: Optional[str] = Field(default=None, description="Service description")
    service_type: Optional[ServiceType] = Field(
        None,
        description="Service type category (AI, STORAGE, COMMUNICATION, etc.)",
    )
    endpoint: Optional[str] = Field(default=None, description="Service endpoint URL")
    parameter_schema: Optional[Dict[str, Any]] = Field(
        None, description="JSON Schema for parameters"
    )
    result_schema: Optional[Dict[str, Any]] = Field(
        None, description="JSON Schema for results"
    )
    example_parameters: Optional[Dict[str, Any]] = Field(
        None, description="Example parameters"
    )
    is_active: Optional[bool] = Field(
        default=None, description="Whether the service is active"
    )
    client_metadata: Optional[Dict[str, Any]] = Field(
        None, description="Additional metadata"
    )


class ProviderServiceRead(ProviderServiceBase):
    """Provider service response model."""

    id: UUID
    provider_id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ConnectionTestResult(BaseModel):
    """Connection test result."""

    success: bool
    timestamp: str
    provider_type: str
    has_credentials: bool
    message: str
