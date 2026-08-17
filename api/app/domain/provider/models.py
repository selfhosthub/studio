# api/app/domain/provider/models.py

"""Provider domain models."""
import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import ConfigDict, Field, field_validator

from app.domain.common.base_entity import AggregateRoot, Entity
from app.domain.common.exceptions import InvalidStateTransition
from app.domain.common.value_objects import OperationalStatus, Visibility


class ProviderType(str, Enum):
    API = "api"
    INFRASTRUCTURE = "infrastructure"
    HYBRID = "hybrid"
    INTERNAL = "internal"
    CUSTOM = "custom"


class CredentialType(str, Enum):
    API_KEY = "api_key"
    ACCESS_KEY = "access_key"
    OAUTH = "oauth"  # legacy alias
    OAUTH2 = "oauth2"
    BEARER = "bearer"
    JWT = "jwt"
    BASIC = "basic"  # legacy
    BASIC_AUTH = "basic_auth"
    CUSTOM = "custom"


class CatalogType(str, Enum):
    PROVIDERS = "providers"
    BLUEPRINTS = "blueprints"
    WORKFLOWS = "workflows"
    COMFYUI = "comfyui"
    PROMPTS = "prompts"
    DOCS = "docs"


class PackageType(str, Enum):
    PROVIDER = "provider"
    WORKFLOW = "workflow"
    BLUEPRINT = "blueprint"
    COMFYUI = "comfyui"
    PROMPT = "prompt"


class ServiceType(str, Enum):
    """Service classification for step-picker categories."""

    CORE = "core"
    FLOW = "flow"
    AI = "ai"
    PRODUCTIVITY = "productivity"
    COMMUNICATION = "communication"
    STORAGE = "storage"
    SOCIAL_MEDIA = "social_media"
    HUMAN_IN_THE_LOOP = "human_in_the_loop"
    TRANSFORM = "transform"
    NETWORK = "network"


class Provider(AggregateRoot):
    """System-wide external service provider. Shared across organizations; orgs configure their own credentials."""

    name: str
    slug: str
    provider_type: ProviderType
    description: Optional[str] = None
    endpoint_url: Optional[str] = None
    # Two orthogonal axes (split out of the former overloaded ProviderStatus in
    # Phase 8). visibility = who sees it in the marketplace; operational_status =
    # whether it can be installed/used. See docs/contributing/invariants.md and
    # the catalog-visibility plan.
    visibility: Visibility = Visibility.PUBLIC
    operational_status: OperationalStatus = OperationalStatus.ACTIVE
    config: Dict[str, Any] = Field(default_factory=dict)
    capabilities: Dict[str, Any] = Field(default_factory=dict)
    client_metadata: Dict[str, Any] = Field(default_factory=dict)
    # Mandatory: providers are keyed by (slug, version) in the catalog table.
    version: str
    source_hash: Optional[str] = None
    created_by: Optional[uuid.UUID] = None

    model_config = ConfigDict(arbitrary_types_allowed=True)

    @field_validator("visibility", mode="before")
    @classmethod
    def _coerce_visibility(cls, v):
        if isinstance(v, str) and not isinstance(v, Visibility):
            return Visibility(v)
        return v

    @field_validator("operational_status", mode="before")
    @classmethod
    def _coerce_operational_status(cls, v):
        if isinstance(v, str) and not isinstance(v, OperationalStatus):
            return OperationalStatus(v)
        return v

    @classmethod
    def create(
        cls,
        name: str,
        slug: str,
        provider_type: ProviderType,
        version: str,
        description: Optional[str] = None,
        endpoint_url: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
        capabilities: Optional[Dict[str, Any]] = None,
        client_metadata: Optional[Dict[str, Any]] = None,
        created_by: Optional[uuid.UUID] = None,
    ) -> "Provider":
        """version is required (semver MAJOR.MINOR.PATCH); providers are keyed by (slug, version)."""
        from app.domain.provider.events import ProviderCreatedEvent

        provider = cls(
            name=name,
            slug=slug,
            provider_type=provider_type,
            version=version,
            description=description,
            endpoint_url=endpoint_url,
            config=config or {},
            capabilities=capabilities or {},
            client_metadata=client_metadata or {},
            visibility=Visibility.PUBLIC,
            operational_status=OperationalStatus.ACTIVE,
            created_by=created_by,
        )

        provider.add_event(
            ProviderCreatedEvent(
                aggregate_id=provider.id,
                aggregate_type="provider",
                provider_id=provider.id,
                name=name,
                provider_type=provider_type.value,
            )
        )

        return provider

    def activate(self) -> None:
        from app.domain.provider.events import ProviderActivatedEvent
        from datetime import datetime, UTC

        if self.operational_status == OperationalStatus.ACTIVE:
            raise InvalidStateTransition(
                message="Provider is already active",
                code="PROVIDER_ALREADY_ACTIVE",
                context={
                    "provider_id": str(self.id),
                    "current_status": self.operational_status.value,
                },
            )

        self.operational_status = OperationalStatus.ACTIVE
        self.updated_at = datetime.now(UTC)

        self.add_event(
            ProviderActivatedEvent(
                aggregate_id=self.id,
                aggregate_type="provider",
                provider_id=self.id,
            )
        )

    def deactivate(self) -> None:
        from app.domain.provider.events import ProviderDeactivatedEvent
        from datetime import datetime, UTC

        if self.operational_status == OperationalStatus.INACTIVE:
            raise InvalidStateTransition(
                message="Provider is already inactive",
                code="PROVIDER_ALREADY_INACTIVE",
                context={
                    "provider_id": str(self.id),
                    "current_status": self.operational_status.value,
                },
            )

        self.operational_status = OperationalStatus.INACTIVE
        self.updated_at = datetime.now(UTC)

        self.add_event(
            ProviderDeactivatedEvent(
                aggregate_id=self.id,
                aggregate_type="provider",
                provider_id=self.id,
            )
        )


class ProviderService(Entity):
    """A specific capability offered by a provider; available to all organizations."""

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
    is_active: bool = True
    # Render a custom editor instead of the generic parameter form.
    custom_ui: bool = False
    # Service manages its own output; UI hides the output schema section.
    custom_output: bool = False
    # Custom parameter-section title; UI falls back to "Service Parameters".
    parameter_title: Optional[str] = None
    client_metadata: Dict[str, Any] = Field(default_factory=dict)
    created_by: Optional[uuid.UUID] = None

    model_config = ConfigDict(arbitrary_types_allowed=True)


class ProviderCredential(Entity):
    """Org-specific credentials for system-wide providers."""

    # Keyed on the provider slug so a credential survives a version upgrade.
    provider_slug: str
    organization_id: uuid.UUID
    credential_type: CredentialType
    name: str
    description: Optional[str] = None
    credentials: Dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True
    # Token-type credentials are reveal-once: viewable only at creation.
    is_token_type: bool = False
    expires_at: Optional[datetime] = None
    created_by: uuid.UUID
    client_metadata: Dict[str, Any] = Field(default_factory=dict)
    # Opaque routing key for this credential's inbound provider-callback URL.
    # Lazily minted on first save of a webhook_callback_api_key; None for
    # poll-only credentials. Not auth material (the bearer secret lives in
    # `credentials`); a plaintext capability, like a workflow webhook token.
    webhook_callback_token: Optional[str] = None

    model_config = ConfigDict(arbitrary_types_allowed=True)
