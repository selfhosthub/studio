# api/app/application/services/provider_service.py

"""
Provider application service.
"""
import secrets
import uuid
from datetime import UTC, datetime
from typing import List, Optional

from app.application.dtos.provider_dto import (
    ProviderCreate,
    ProviderCredentialCreate,
    ProviderCredentialResponse,
    ProviderCredentialUpdate,
    ProviderResponse,
    ProviderServiceCreate,
    ProviderServiceResponse,
    ProviderServiceUpdate,
    ProviderUpdate,
)
from app.application.interfaces import EntityNotFoundError, EventBus
from app.config.settings import settings
from app.domain.common.exceptions import ConfigurationError
from app.domain.common.value_objects import OperationalStatus, Visibility
from app.domain.provider.models import (
    Provider,
    ProviderCredential,
    ProviderService as ProviderServiceModel,
    ProviderType,
    ServiceType,
)
from app.domain.provider.repository import (
    ProviderCredentialRepository,
    ProviderRepository,
    ProviderServiceRepository,
)


class ProviderService:
    """
    Application service for provider operations.

    Pure orchestrator - delegates business logic to domain.
    """

    def __init__(
        self,
        provider_repo: ProviderRepository,
        credential_repo: ProviderCredentialRepository,
        event_bus: EventBus,
        provider_service_repo: Optional[ProviderServiceRepository] = None,
    ):
        self.provider_repo = provider_repo
        self.credential_repo = credential_repo
        self.event_bus = event_bus
        self.provider_service_repo = provider_service_repo

    async def create_provider(self, command: ProviderCreate) -> ProviderResponse:
        """Create a new provider."""
        provider = Provider.create(
            name=command.name,
            slug=command.slug,
            provider_type=command.provider_type,
            version=command.version,
            description=command.description,
            endpoint_url=command.endpoint_url,
            config=command.config,
            capabilities=command.capabilities,
            client_metadata=command.client_metadata,
            created_by=command.created_by,
        )

        events = provider.clear_events()

        created = await self.provider_repo.create(provider)

        for event in events:
            await self.event_bus.publish(event)

        return ProviderResponse.from_domain(created)

    async def update_provider(
        self, provider_id: uuid.UUID, command: ProviderUpdate
    ) -> ProviderResponse:
        """Update an existing provider."""
        provider = await self.provider_repo.get_by_id(provider_id)
        if not provider:
            raise EntityNotFoundError(
                entity_type="Provider",
                entity_id=provider_id,
                code=f"Provider with ID {provider_id} not found",
            )

        if command.name is not None:
            provider.name = command.name
        if command.description is not None:
            provider.description = command.description
        if command.endpoint_url is not None:
            provider.endpoint_url = command.endpoint_url
        if command.config is not None:
            provider.config = command.config
        if command.capabilities is not None:
            provider.capabilities = command.capabilities
        if command.client_metadata is not None:
            provider.client_metadata = command.client_metadata
        if command.status is not None:
            # `status` on the update command is the operational axis (active/inactive).
            provider.operational_status = OperationalStatus(command.status)
        if command.visibility is not None:
            provider.visibility = command.visibility

        provider.updated_at = datetime.now(UTC)

        updated = await self.provider_repo.update(provider)

        return ProviderResponse.from_domain(updated)

    async def get_provider(self, provider_id: uuid.UUID) -> Optional[ProviderResponse]:
        """Get a provider by ID."""
        provider = await self.provider_repo.get_by_id(provider_id)
        if provider:
            return ProviderResponse.from_domain(provider)
        return None

    async def get_provider_by_slug(self, slug: str) -> Optional[ProviderResponse]:
        """Get the current provider row for a slug."""
        provider = await self.provider_repo.get_by_slug(slug)
        if provider:
            return ProviderResponse.from_domain(provider)
        return None

    async def list_providers(
        self,
        skip: int = 0,
        limit: int = 100,
        operational_status: Optional[OperationalStatus] = None,
        provider_type: Optional[ProviderType] = None,
        visibilities: Optional[List[Visibility]] = None,
    ) -> List[ProviderResponse]:
        """List providers with their services.

        ``visibilities``, when set, restricts results to those visibility
        labels; None returns every visibility (super-org management view).
        """
        providers = await self.provider_repo.list_all(
            operational_status=operational_status,
            provider_type=provider_type,
            visibilities=visibilities,
            skip=skip,
            limit=limit,
        )

        # Fetch services for each provider
        result = []
        for p in providers:
            if self.provider_service_repo:
                services = await self.provider_service_repo.list_by_provider(
                    p.id, skip=0, limit=100
                )
                service_responses = [
                    ProviderServiceResponse.from_domain(s) for s in services
                ]
                result.append(
                    ProviderResponse.from_domain(p, services=service_responses)
                )
            else:
                result.append(ProviderResponse.from_domain(p, services=[]))

        return result

    async def list_providers_slim(
        self,
        operational_status: Optional[OperationalStatus] = None,
        visibilities: Optional[List[Visibility]] = None,
    ) -> List[Provider]:
        """List providers without hydrating services.

        Returns the full set (no pagination) of lightweight domain providers
        for identity-only callers. The {id, slug} rows are tiny, so returning
        every provider is both safe and necessary for completeness (a
        readiness check must see all installed providers, not one page).
        """
        return await self.provider_repo.list_all(
            operational_status=operational_status,
            visibilities=visibilities,
            skip=0,
            limit=settings.API_PAGE_MAX,
        )

    async def delete_provider(self, provider_id: uuid.UUID) -> bool:
        """Delete a provider by ID."""
        provider = await self.provider_repo.get_by_id(provider_id)
        if not provider:
            return False

        return await self.provider_repo.delete(provider_id)

    @staticmethod
    def _mint_callback_token_if_needed(credential: ProviderCredential) -> Optional[str]:
        """Lazily mint this credential's inbound-callback routing token the first
        time it carries a ``webhook_callback_api_key``. Immortal once set (a
        credential's callback URL must be stable for its life - changing it means
        a new Leonardo key, i.e. a new credential). Poll-only credentials (no
        callback key) never get a token."""
        if credential.webhook_callback_token:
            return credential.webhook_callback_token
        if (credential.credentials or {}).get("webhook_callback_api_key"):
            return secrets.token_urlsafe(settings.WEBHOOK_TOKEN_LENGTH)
        return None

    async def create_credential(
        self, command: ProviderCredentialCreate
    ) -> ProviderCredentialResponse:
        """Create credentials for a provider."""
        provider = await self.provider_repo.get_by_id(command.provider_id)
        if not provider:
            raise EntityNotFoundError(
                entity_type="Provider",
                entity_id=command.provider_id,
                code=f"Provider with ID {command.provider_id} not found",
            )

        credential = ProviderCredential(
            provider_slug=provider.slug,
            organization_id=command.organization_id,
            credential_type=command.credential_type,
            name=command.name,
            description=command.description,
            credentials=command.credentials,
            is_token_type=getattr(command, "is_token_type", False),
            created_by=command.created_by,
            expires_at=command.expires_at,
            client_metadata=command.client_metadata,
            # Client-supplied token (user-generated in the form) persists as-is;
            # else lazy-mint below if a webhook_callback_api_key is present.
            webhook_callback_token=getattr(command, "webhook_callback_token", None),
        )
        credential.webhook_callback_token = self._mint_callback_token_if_needed(
            credential
        )

        created = await self.credential_repo.create(credential)

        return await self._credential_response(created)

    async def _current_provider_id(self, slug: str) -> uuid.UUID:
        """Id of the current provider row for a slug; credentials key on the slug."""
        provider = await self.provider_repo.get_by_slug(slug)
        if not provider:
            raise EntityNotFoundError(
                entity_type="Provider",
                entity_id=slug,
                code=f"Provider {slug} not found",
            )
        return provider.id

    async def _credential_response(
        self, credential: ProviderCredential
    ) -> ProviderCredentialResponse:
        return ProviderCredentialResponse.from_domain(
            credential, await self._current_provider_id(credential.provider_slug)
        )

    async def _credential_responses(
        self, credentials: List[ProviderCredential]
    ) -> List[ProviderCredentialResponse]:
        ids = {
            slug: await self._current_provider_id(slug)
            for slug in {c.provider_slug for c in credentials}
        }
        return [
            ProviderCredentialResponse.from_domain(c, ids[c.provider_slug])
            for c in credentials
        ]

    async def update_credential(
        self, credential_id: uuid.UUID, command: ProviderCredentialUpdate
    ) -> ProviderCredentialResponse:
        """Update provider credentials."""
        credential = await self.credential_repo.get_by_id(credential_id)
        if not credential:
            raise EntityNotFoundError(
                entity_type="ProviderCredential",
                entity_id=credential_id,
                code=f"Credential with ID {credential_id} not found",
            )

        if command.name is not None:
            credential.name = command.name
        if command.description is not None:
            credential.description = command.description
        if command.credentials is not None:
            # Drop blank values so a cleared field is removed, not stored as "".
            credential.credentials = {
                k: v for k, v in command.credentials.items() if v != ""
            }
        if command.is_active is not None:
            credential.is_active = command.is_active
        if command.expires_at is not None:
            credential.expires_at = command.expires_at
        if command.client_metadata is not None:
            credential.client_metadata = command.client_metadata
        # A client-supplied token is a user-driven regenerate of the callback URL.
        # Clearing the webhook_callback_api_key clears the routing token too; with
        # the key still set, an absent token lazy-mints on first webhook save.
        client_token = getattr(command, "webhook_callback_token", None)
        if client_token:
            credential.webhook_callback_token = client_token
        elif not (credential.credentials or {}).get("webhook_callback_api_key"):
            credential.webhook_callback_token = None
        else:
            credential.webhook_callback_token = self._mint_callback_token_if_needed(
                credential
            )

        updated = await self.credential_repo.update(credential)

        return await self._credential_response(updated)

    async def get_credential(
        self, credential_id: uuid.UUID
    ) -> Optional[ProviderCredentialResponse]:
        """Get a credential by ID (without secret data)."""
        credential = await self.credential_repo.get_by_id(credential_id)
        if credential:
            return await self._credential_response(credential)
        return None

    async def get_credential_with_secret(
        self, credential_id: uuid.UUID
    ) -> Optional[ProviderCredential]:
        """
        Get a credential by ID including decrypted secret data.

        Used by the reveal endpoint. Returns the domain entity directly
        to allow access to the credentials field.
        """
        return await self.credential_repo.get_by_id(credential_id)

    async def list_credentials_by_provider(
        self, provider_id: uuid.UUID, skip: int = 0, limit: int = 100
    ) -> List[ProviderCredentialResponse]:
        """List credentials for a provider."""
        provider = await self.provider_repo.get_by_id(provider_id)
        if not provider:
            return []
        credentials = await self.credential_repo.list_by_provider(
            provider_slug=provider.slug, skip=skip, limit=limit
        )
        return await self._credential_responses(credentials)

    async def list_credentials_by_organization(
        self,
        organization_id: uuid.UUID,
        skip: int = 0,
        limit: int = 100,
        provider_id: Optional[uuid.UUID] = None,
        credential_type: Optional[str] = None,
        is_active: Optional[bool] = None,
        search: Optional[str] = None,
    ) -> List[ProviderCredentialResponse]:
        """List all credentials for an organization (secrets vault)."""
        from app.domain.provider.models import CredentialType

        cred_type_enum = None
        if credential_type:
            try:
                cred_type_enum = CredentialType(credential_type)
            except ValueError:
                pass  # Invalid type, ignore filter

        provider_slug = None
        if provider_id is not None:
            provider = await self.provider_repo.get_by_id(provider_id)
            if not provider:
                return []
            provider_slug = provider.slug

        credentials = await self.credential_repo.list_by_organization(
            organization_id=organization_id,
            skip=skip,
            limit=limit,
            provider_slug=provider_slug,
            credential_type=cred_type_enum,
            is_active=is_active,
            search=search,
        )
        return await self._credential_responses(credentials)

    async def delete_credential(self, credential_id: uuid.UUID) -> bool:
        """Delete a credential by ID."""
        credential = await self.credential_repo.get_by_id(credential_id)
        if not credential:
            return False

        return await self.credential_repo.delete(credential_id)

    async def create_provider_service(
        self, command: ProviderServiceCreate
    ) -> ProviderServiceResponse:
        """Create a new provider service."""
        if not self.provider_service_repo:
            raise ConfigurationError("Provider service repository is not available")

        provider = await self.provider_repo.get_by_id(command.provider_id)
        if not provider:
            raise EntityNotFoundError(
                entity_type="Provider",
                entity_id=command.provider_id,
                code=f"Provider with ID {command.provider_id} not found",
            )

        service = ProviderServiceModel(
            provider_id=command.provider_id,
            service_id=command.service_id,
            display_name=command.display_name,
            service_type=command.service_type,
            description=command.description,
            endpoint=command.endpoint,
            parameter_schema=command.parameter_schema,
            result_schema=command.result_schema,
            example_parameters=command.example_parameters,
            client_metadata=command.client_metadata,
            created_by=command.created_by,
        )

        created = await self.provider_service_repo.create(service)

        return ProviderServiceResponse.from_domain(created)

    async def update_provider_service(
        self, service_id: uuid.UUID, command: ProviderServiceUpdate
    ) -> ProviderServiceResponse:
        """Update a provider service."""
        if not self.provider_service_repo:
            raise ConfigurationError("Provider service repository is not available")

        service = await self.provider_service_repo.get_by_id(service_id)
        if not service:
            raise EntityNotFoundError(
                entity_type="ProviderService",
                entity_id=service_id,
                code=f"Provider service with ID {service_id} not found",
            )

        if command.display_name is not None:
            service.display_name = command.display_name
        if command.description is not None:
            service.description = command.description
        if command.endpoint is not None:
            service.endpoint = command.endpoint
        if command.parameter_schema is not None:
            service.parameter_schema = command.parameter_schema
        if command.result_schema is not None:
            service.result_schema = command.result_schema
        if command.example_parameters is not None:
            service.example_parameters = command.example_parameters
        if command.is_active is not None:
            service.is_active = command.is_active
        if command.client_metadata is not None:
            service.client_metadata = command.client_metadata

        updated = await self.provider_service_repo.update(service)

        return ProviderServiceResponse.from_domain(updated)

    async def get_provider_service(
        self, service_id: uuid.UUID
    ) -> ProviderServiceResponse:
        """Get a provider service by ID."""
        if not self.provider_service_repo:
            raise ConfigurationError("Provider service repository is not available")

        service = await self.provider_service_repo.get_by_id(service_id)
        if not service:
            raise EntityNotFoundError(
                entity_type="ProviderService",
                entity_id=service_id,
                code=f"Provider service with ID {service_id} not found",
            )

        return ProviderServiceResponse.from_domain(service)

    async def get_provider_service_by_service_id(
        self, provider_id: uuid.UUID, service_id_str: str
    ) -> Optional[ProviderServiceResponse]:
        """
        Get a provider service by its service_id string (e.g., 'myprovider.my_service').

        Args:
            provider_id: UUID of the provider
            service_id_str: The service_id string identifier

        Returns:
            ProviderServiceResponse or None if not found
        """
        if not self.provider_service_repo:
            raise ConfigurationError("Provider service repository is not available")

        # Use existing method - it returns first match
        service = await self.provider_service_repo.get_by_service_id(
            service_id_str, skip=0, limit=1
        )

        # Verify it belongs to the expected provider
        if service and service.provider_id == provider_id:
            return ProviderServiceResponse.from_domain(service)

        return None

    async def list_provider_services(
        self,
        skip: int = 0,
        limit: int = 100,
        provider_id: Optional[uuid.UUID] = None,
        service_type: Optional[ServiceType] = None,
        is_active: Optional[bool] = None,
    ) -> List[ProviderServiceResponse]:
        """List provider services."""
        if not self.provider_service_repo:
            raise ConfigurationError("Provider service repository is not available")

        if provider_id:
            services = await self.provider_service_repo.list_by_provider(
                provider_id=provider_id,
                service_type=service_type,
                is_active=is_active,
                skip=skip,
                limit=limit,
            )
        elif service_type:
            services = await self.provider_service_repo.list_by_type(
                service_type=service_type,
                is_active=is_active,
                skip=skip,
                limit=limit,
            )
        else:
            services = []

        return [ProviderServiceResponse.from_domain(s) for s in services]

    async def delete_provider_service(self, service_id: uuid.UUID) -> bool:
        """Delete a provider service by ID."""
        if not self.provider_service_repo:
            raise ConfigurationError("Provider service repository is not available")

        service = await self.provider_service_repo.get_by_id(service_id)
        if not service:
            return False

        return await self.provider_service_repo.delete(service_id)
