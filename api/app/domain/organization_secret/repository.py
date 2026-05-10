# api/app/domain/organization_secret/repository.py

"""Repository interface for organization secrets."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from uuid import UUID

from app.domain.organization_secret.models import OrganizationSecret


class OrganizationSecretRepository(ABC):
    """Persistence operations for OrganizationSecret. Implementations encrypt secret_data at rest, enforce name immutability, and reject delete on protected secrets."""

    @abstractmethod
    async def create(self, secret: OrganizationSecret) -> OrganizationSecret:
        pass

    @abstractmethod
    async def get_by_id(
        self, secret_id: UUID, organization_id: UUID
    ) -> Optional[OrganizationSecret]:
        """organization_id is required for access control."""
        pass

    @abstractmethod
    async def get_by_name(
        self, organization_id: UUID, name: str
    ) -> Optional[OrganizationSecret]:
        pass

    @abstractmethod
    async def list_by_organization(
        self, organization_id: UUID, include_inactive: bool = False
    ) -> List[OrganizationSecret]:
        pass

    @abstractmethod
    async def update(self, secret: OrganizationSecret) -> OrganizationSecret:
        """Name is immutable and should not be updated."""
        pass

    @abstractmethod
    async def delete(self, secret_id: UUID, organization_id: UUID) -> bool:
        """Returns True if deleted. Raises ValueError if protected."""
        pass

    @abstractmethod
    async def list_metadata_only(
        self, organization_id: UUID, active_only: bool = True
    ) -> List[Dict[str, Any]]:
        """Metadata without decrypted values; safe for list endpoints."""
        pass
