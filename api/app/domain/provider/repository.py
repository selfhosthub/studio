# api/app/domain/provider/repository.py

"""Repository interfaces for the provider domain."""
import uuid
from abc import ABC, abstractmethod
from typing import List, Optional

from app.domain.provider.models import (
    CredentialType,
    Provider,
    ProviderCredential,
    ProviderService,
    ProviderStatus,
    ProviderType,
    ServiceType,
)


class ProviderRepository(ABC):
    """Persistence operations for system-wide Provider aggregates."""

    @abstractmethod
    async def create(self, provider: Provider) -> Provider: ...

    @abstractmethod
    async def update(self, provider: Provider) -> Provider: ...

    @abstractmethod
    async def get_by_id(self, provider_id: uuid.UUID) -> Optional[Provider]: ...

    @abstractmethod
    async def get_by_name(self, name: str) -> Optional[Provider]:
        """Providers are system-wide; no organization scope needed."""

    @abstractmethod
    async def get_by_slug(self, slug: str) -> Optional[Provider]: ...

    @abstractmethod
    async def find_active_providers(
        self,
        skip: int,
        limit: int,
    ) -> List[Provider]: ...

    @abstractmethod
    async def find_providers_by_type(
        self,
        provider_type: ProviderType,
        skip: int,
        limit: int,
    ) -> List[Provider]: ...

    @abstractmethod
    async def find_global_providers(
        self,
        skip: int,
        limit: int,
    ) -> List[Provider]: ...

    @abstractmethod
    async def list_all(
        self,
        skip: int,
        limit: int,
        status: Optional[ProviderStatus] = None,
        provider_type: Optional[ProviderType] = None,
    ) -> List[Provider]: ...

    @abstractmethod
    async def count(
        self,
        status: Optional[ProviderStatus] = None,
    ) -> int: ...

    @abstractmethod
    async def delete(self, provider_id: uuid.UUID) -> bool: ...

    @abstractmethod
    async def exists(self, provider_id: uuid.UUID) -> bool: ...


class ProviderServiceRepository(ABC):
    """Persistence operations for ProviderService entities."""

    @abstractmethod
    async def create(self, service: ProviderService) -> ProviderService: ...

    @abstractmethod
    async def update(self, service: ProviderService) -> ProviderService: ...

    @abstractmethod
    async def get_by_id(self, service_id: uuid.UUID) -> Optional[ProviderService]: ...

    @abstractmethod
    async def get_by_service_id(
        self,
        service_id: str,
        skip: int,
        limit: int,
    ) -> Optional[ProviderService]:
        """Lookup by the string service_id."""

    @abstractmethod
    async def list_by_provider(
        self,
        provider_id: uuid.UUID,
        skip: int,
        limit: int,
        service_type: Optional[ServiceType] = None,
        is_active: Optional[bool] = None,
        supports_gpu: Optional[bool] = None,
    ) -> List[ProviderService]: ...

    @abstractmethod
    async def list_by_type(
        self,
        service_type: ServiceType,
        skip: int,
        limit: int,
        is_active: Optional[bool] = None,
    ) -> List[ProviderService]: ...

    @abstractmethod
    async def search(
        self,
        query: str,
        skip: int,
        limit: int,
    ) -> List[ProviderService]: ...

    @abstractmethod
    async def delete(self, service_id: uuid.UUID) -> bool: ...

    @abstractmethod
    async def exists(self, service_id: uuid.UUID) -> bool: ...


class ProviderCredentialRepository(ABC):
    """Persistence for ProviderCredential. Credentials ARE organization-specific."""

    @abstractmethod
    async def create(self, credential: ProviderCredential) -> ProviderCredential: ...

    @abstractmethod
    async def update(self, credential: ProviderCredential) -> ProviderCredential: ...

    @abstractmethod
    async def get_by_id(self, credential_id: uuid.UUID) -> Optional[ProviderCredential]: ...

    @abstractmethod
    async def get_default_credential(
        self,
        provider_id: uuid.UUID,
        organization_id: uuid.UUID,
    ) -> Optional[ProviderCredential]: ...

    @abstractmethod
    async def list_by_provider(
        self,
        provider_id: uuid.UUID,
        skip: int,
        limit: int,
        credential_type: Optional[CredentialType] = None,
        is_active: Optional[bool] = None,
    ) -> List[ProviderCredential]: ...

    @abstractmethod
    async def list_by_organization(
        self,
        organization_id: uuid.UUID,
        skip: int,
        limit: int,
        provider_id: Optional[uuid.UUID] = None,
        credential_type: Optional[CredentialType] = None,
        is_active: Optional[bool] = None,
        search: Optional[str] = None,
    ) -> List[ProviderCredential]:
        """Secrets Vault view: an organization's provider credentials with filters."""

    @abstractmethod
    async def delete(self, credential_id: uuid.UUID) -> bool: ...

    @abstractmethod
    async def exists(self, credential_id: uuid.UUID) -> bool: ...
