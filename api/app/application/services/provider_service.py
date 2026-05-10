# api/app/application/services/provider_service.py

"""
Provider application service.
"""
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
from app.domain.common.exceptions import ConfigurationError
from app.domain.provider.models import (
    Provider,
    ProviderCredential,
    ProviderService as ProviderServiceModel,
    ProviderStatus,
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
            provider.status = ProviderStatus(command.status)

        provider.updated_at = datetime.now(UTC)

        updated = await self.provider_repo.update(provider)

        return ProviderResponse.from_domain(updated)

    async def get_provider(self, provider_id: uuid.UUID) -> Optional[ProviderResponse]:
        """Get a provider by ID."""
        provider = await self.provider_repo.get_by_id(provider_id)
        if provider:
            return ProviderResponse.from_domain(provider)
        return None

    async def list_providers(
        self,
        skip: int = 0,
        limit: int = 100,
        status: Optional[ProviderStatus] = None,
        provider_type: Optional[ProviderType] = None,
    ) -> List[ProviderResponse]:
        """List providers with their services."""
        providers = await self.provider_repo.list_all(
            status=status,
            provider_type=provider_type,
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

    async def delete_provider(self, provider_id: uuid.UUID) -> bool:
        """Delete a provider by ID."""
        provider = await self.provider_repo.get_by_id(provider_id)
        if not provider:
            return False

        return await self.provider_repo.delete(provider_id)

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
            provider_id=command.provider_id,
            organization_id=command.organization_id,
            credential_type=command.credential_type,
            name=command.name,
            description=command.description,
            credentials=command.credentials,
            is_token_type=getattr(command, "is_token_type", False),
            created_by=command.created_by,
            expires_at=command.expires_at,
            client_metadata=command.client_metadata,
        )

        created = await self.credential_repo.create(credential)

        return ProviderCredentialResponse.from_domain(created)

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
            credential.credentials = command.credentials
        if command.is_active is not None:
            credential.is_active = command.is_active
        if command.expires_at is not None:
            credential.expires_at = command.expires_at
        if command.client_metadata is not None:
            credential.client_metadata = command.client_metadata

        updated = await self.credential_repo.update(credential)

        return ProviderCredentialResponse.from_domain(updated)

    async def get_credential(
        self, credential_id: uuid.UUID
    ) -> Optional[ProviderCredentialResponse]:
        """Get a credential by ID (without secret data)."""
        credential = await self.credential_repo.get_by_id(credential_id)
        if credential:
            return ProviderCredentialResponse.from_domain(credential)
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
        credentials = await self.credential_repo.list_by_provider(
            provider_id=provider_id, skip=skip, limit=limit
        )
        return [ProviderCredentialResponse.from_domain(c) for c in credentials]

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

        credentials = await self.credential_repo.list_by_organization(
            organization_id=organization_id,
            skip=skip,
            limit=limit,
            provider_id=provider_id,
            credential_type=cred_type_enum,
            is_active=is_active,
            search=search,
        )
        return [ProviderCredentialResponse.from_domain(c) for c in credentials]

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
