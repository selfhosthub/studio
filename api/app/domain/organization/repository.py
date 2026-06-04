# api/app/domain/organization/repository.py

"""Repository interfaces for the organization domain."""

import uuid
from abc import ABC, abstractmethod
from typing import List, Optional

from app.domain.organization.models import Organization, User
from app.domain.common.value_objects import Role


class OrganizationRepository(ABC):
    """Persistence operations for Organization aggregates."""

    @abstractmethod
    async def create(self, organization: Organization) -> Organization: ...

    @abstractmethod
    async def update(self, organization: Organization) -> Organization: ...

    @abstractmethod
    async def get_by_id(self, organization_id: uuid.UUID) -> Optional[Organization]: ...

    @abstractmethod
    async def get_by_slug(self, slug: str) -> Optional[Organization]: ...

    @abstractmethod
    async def find_active_organizations(
        self,
        skip: int,
        limit: int,
    ) -> List[Organization]: ...

    @abstractmethod
    async def search(
        self,
        query: str,
        skip: int,
        limit: int,
    ) -> List[Organization]: ...

    @abstractmethod
    async def list_all(self) -> List[Organization]:
        """No pagination - used for admin sweeps over all orgs."""

    @abstractmethod
    async def count_workflows(self, organization_id: uuid.UUID) -> int: ...

    @abstractmethod
    async def count_active_users(self, organization_id: uuid.UUID) -> int: ...

    @abstractmethod
    async def count_blueprints(self, organization_id: uuid.UUID) -> int: ...

    @abstractmethod
    async def count_instances(self, organization_id: uuid.UUID) -> int: ...

    @abstractmethod
    async def delete(self, organization_id: uuid.UUID) -> bool: ...

    @abstractmethod
    async def exists(self, organization_id: uuid.UUID) -> bool: ...


class UserRepository(ABC):
    """Persistence operations for User entities."""

    @abstractmethod
    async def create(self, user: User) -> User: ...

    @abstractmethod
    async def update(self, user: User) -> User: ...

    @abstractmethod
    async def get_by_id(self, user_id: uuid.UUID) -> Optional[User]: ...

    @abstractmethod
    async def get_by_email(self, email: str) -> Optional[User]: ...

    @abstractmethod
    async def get_by_username(self, username: str) -> Optional[User]: ...

    @abstractmethod
    async def find_by_email(self, email: str) -> Optional[User]:
        """Alias for get_by_email; used for uniqueness checks."""

    @abstractmethod
    async def find_active_users_in_organization(
        self,
        organization_id: uuid.UUID,
        skip: int,
        limit: int,
    ) -> List[User]: ...

    @abstractmethod
    async def list(
        self,
        skip: int,
        limit: int,
        organization_id: Optional[uuid.UUID] = None,
        only_active: bool = False,
    ) -> List[User]: ...

    @abstractmethod
    async def search(
        self,
        query: str,
        skip: int,
        limit: int,
        organization_id: Optional[uuid.UUID] = None,
    ) -> List[User]:
        """Search by username, email, or full name."""

    @abstractmethod
    async def delete(self, user_id: uuid.UUID) -> bool: ...

    @abstractmethod
    async def count_by_organization_and_role(
        self, organization_id: uuid.UUID, role: Role, only_active: bool = True
    ) -> int: ...

    @abstractmethod
    async def exists(self, user_id: uuid.UUID) -> bool: ...

    @abstractmethod
    async def list_public_team(self) -> List[User]:
        """Active users with is_public=True, ordered by creation date."""
