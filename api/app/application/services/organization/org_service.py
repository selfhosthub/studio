# api/app/application/services/organization/org_service.py

"""Application service for organization CRUD operations."""

import uuid
from typing import List, Optional

from app.application.dtos import (
    OrganizationCreate,
    OrganizationResponse,
    OrganizationUpdate,
)
from app.application.interfaces import (
    EventBus,
    EntityNotFoundError,
)
from app.application.interfaces.exceptions import PermissionDeniedError
from app.application.services.organization.auth_helpers import (
    verify_super_admin_access,
)
from app.domain.common.value_objects import Role
from app.domain.organization.models import Organization
from app.domain.organization.repository import (
    OrganizationRepository,
    UserRepository,
)


class OrgService:
    """Application service for organization-level operations."""

    def __init__(
        self,
        organization_repository: OrganizationRepository,
        user_repository: UserRepository,
        event_bus: EventBus,
    ):
        self.organization_repository = organization_repository
        self.user_repository = user_repository
        self.event_bus = event_bus

    async def create_organization(
        self, command: OrganizationCreate, current_user_id: uuid.UUID
    ) -> OrganizationResponse:
        """Create a new organization. Only SUPER_ADMIN can create organizations."""
        await verify_super_admin_access(self.user_repository, current_user_id)

        organization = Organization.create(
            name=command.name,
            slug=command.slug,
            description=command.description,
        )

        events = organization.clear_events()
        organization = await self.organization_repository.create(organization)

        for event in events:
            await self.event_bus.publish(event)

        return OrganizationResponse.from_domain(organization)

    async def activate_organization(
        self, organization_id: uuid.UUID, current_user_id: uuid.UUID
    ) -> OrganizationResponse:
        """Activate an organization. Only SUPER_ADMIN."""
        organization = await self.organization_repository.get_by_id(organization_id)
        if not organization:
            raise EntityNotFoundError(
                entity_type="Organization",
                entity_id=organization_id,
                code="ORGANIZATION_NOT_FOUND",
            )

        await verify_super_admin_access(self.user_repository, current_user_id)

        organization.activate()
        events = organization.clear_events()
        organization = await self.organization_repository.update(organization)

        for event in events:
            await self.event_bus.publish(event)

        return OrganizationResponse.from_domain(organization)

    async def deactivate_organization(
        self, organization_id: uuid.UUID, current_user_id: uuid.UUID
    ) -> OrganizationResponse:
        """Deactivate an organization. Only SUPER_ADMIN."""
        organization = await self.organization_repository.get_by_id(organization_id)
        if not organization:
            raise EntityNotFoundError(
                entity_type="Organization",
                entity_id=organization_id,
                code="ORGANIZATION_NOT_FOUND",
            )

        await verify_super_admin_access(self.user_repository, current_user_id)

        organization.deactivate()
        events = organization.clear_events()
        organization = await self.organization_repository.update(organization)

        for event in events:
            await self.event_bus.publish(event)

        return OrganizationResponse.from_domain(organization)

    async def list_organizations(
        self, skip: int = 0, limit: int = 100
    ) -> List[OrganizationResponse]:
        """List all organizations with pagination."""
        organizations = await self.organization_repository.find_active_organizations(
            skip=skip,
            limit=limit,
        )
        return [OrganizationResponse.from_domain(org) for org in organizations]

    async def get_organization(
        self, organization_id: uuid.UUID
    ) -> Optional[OrganizationResponse]:
        """Get an organization by ID."""
        organization = await self.organization_repository.get_by_id(organization_id)
        if organization:
            return OrganizationResponse.from_domain(organization)
        return None

    async def update_organization(
        self,
        organization_id: uuid.UUID,
        command: OrganizationUpdate,
        current_user_id: uuid.UUID,
    ) -> OrganizationResponse:
        """
        Update an organization.

        SUPER_ADMIN can update any organization.
        ADMIN can update their own organization's settings.
        """
        organization = await self.organization_repository.get_by_id(organization_id)
        if not organization:
            raise EntityNotFoundError(
                entity_type="Organization",
                entity_id=organization_id,
                code="ORGANIZATION_NOT_FOUND",
            )

        # Get current user to check permissions
        user = await self.user_repository.get_by_id(current_user_id)
        if not user:
            raise EntityNotFoundError(
                entity_type="User",
                entity_id=current_user_id,
                code="USER_NOT_FOUND",
            )

        # Permission check
        if user.role == Role.SUPER_ADMIN:
            pass
        elif user.role == Role.ADMIN and user.organization_id == organization_id:
            pass
        else:
            raise PermissionDeniedError(
                message="Only super admins or organization admins can update organizations",
                code="INSUFFICIENT_PERMISSIONS",
            )

        organization.update(
            name=command.name,
            description=command.description,
            settings=command.settings,
        )

        # Handle is_active changes via domain methods (super_admin only)
        if (
            command.is_active is not None
            and command.is_active != organization.is_active
        ):
            if user.role != Role.SUPER_ADMIN:
                raise PermissionDeniedError(
                    message="Only super admins can activate/deactivate organizations",
                    code="INSUFFICIENT_PERMISSIONS",
                )
            if command.is_active:
                organization.activate()
            else:
                organization.deactivate()

        events = organization.clear_events()
        organization = await self.organization_repository.update(organization)

        for event in events:
            await self.event_bus.publish(event)

        return OrganizationResponse.from_domain(organization)
