# api/app/application/services/organization/__init__.py

"""Organization service facade.

Composes org and user sub-services behind a single API so existing importers
work unchanged.
"""

import uuid
from typing import List, Optional

from app.application.dtos import (
    OrganizationCreate,
    OrganizationResponse,
    OrganizationUpdate,
    UserCreate,
    UserResponse,
    UserUpdate,
)
from app.application.interfaces import EventBus
from app.application.interfaces.password_service import PasswordServiceInterface
from app.domain.organization.repository import (
    OrganizationRepository,
    UserRepository,
)

from .org_service import OrgService
from .user_service import UserService


class OrganizationService:
    """Facade that preserves the original public API."""

    def __init__(
        self,
        organization_repository: OrganizationRepository,
        user_repository: UserRepository,
        event_bus: EventBus,
        password_service: PasswordServiceInterface,
    ):
        self._org_service = OrgService(
            organization_repository=organization_repository,
            user_repository=user_repository,
            event_bus=event_bus,
        )
        self._user_service = UserService(
            organization_repository=organization_repository,
            user_repository=user_repository,
            event_bus=event_bus,
            password_service=password_service,
        )

    # -- Organization operations --

    async def create_organization(
        self, command: OrganizationCreate, current_user_id: uuid.UUID
    ) -> OrganizationResponse:
        return await self._org_service.create_organization(command, current_user_id)

    async def activate_organization(
        self, organization_id: uuid.UUID, current_user_id: uuid.UUID
    ) -> OrganizationResponse:
        return await self._org_service.activate_organization(
            organization_id, current_user_id
        )

    async def deactivate_organization(
        self, organization_id: uuid.UUID, current_user_id: uuid.UUID
    ) -> OrganizationResponse:
        return await self._org_service.deactivate_organization(
            organization_id, current_user_id
        )

    async def list_organizations(
        self, skip: int = 0, limit: int = 100
    ) -> List[OrganizationResponse]:
        return await self._org_service.list_organizations(skip=skip, limit=limit)

    async def get_organization(
        self, organization_id: uuid.UUID
    ) -> Optional[OrganizationResponse]:
        return await self._org_service.get_organization(organization_id)

    async def update_organization(
        self,
        organization_id: uuid.UUID,
        command: OrganizationUpdate,
        current_user_id: uuid.UUID,
    ) -> OrganizationResponse:
        return await self._org_service.update_organization(
            organization_id, command, current_user_id
        )

    # -- User operations --

    async def create_user(
        self,
        command: UserCreate,
        current_user_id: Optional[uuid.UUID] = None,
    ) -> UserResponse:
        return await self._user_service.create_user(command, current_user_id)

    async def activate_user(
        self, user_id: uuid.UUID, current_user_id: uuid.UUID
    ) -> UserResponse:
        return await self._user_service.activate_user(user_id, current_user_id)

    async def deactivate_user(
        self, user_id: uuid.UUID, current_user_id: uuid.UUID
    ) -> UserResponse:
        return await self._user_service.deactivate_user(user_id, current_user_id)

    async def change_user_password(
        self, user_id: uuid.UUID, current_password: str, new_password: str
    ) -> None:
        return await self._user_service.change_user_password(
            user_id, current_password, new_password
        )

    async def list_users(
        self,
        organization_id: uuid.UUID,
        skip: int = 0,
        limit: int = 100,
        only_active: bool = False,
    ) -> List[UserResponse]:
        return await self._user_service.list_users(
            organization_id, skip=skip, limit=limit, only_active=only_active
        )

    async def get_user(self, user_id: uuid.UUID) -> Optional[UserResponse]:
        return await self._user_service.get_user(user_id)

    async def update_user(
        self,
        user_id: uuid.UUID,
        command: UserUpdate,
        current_user_id: uuid.UUID,
    ) -> UserResponse:
        return await self._user_service.update_user(user_id, command, current_user_id)

    async def update_user_as_admin(
        self,
        user_id: uuid.UUID,
        command: UserUpdate,
        current_user_id: uuid.UUID,
    ) -> UserResponse:
        return await self._user_service.update_user_as_admin(
            user_id, command, current_user_id
        )
