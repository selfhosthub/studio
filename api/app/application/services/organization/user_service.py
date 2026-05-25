# api/app/application/services/organization/user_service.py

"""Application service for user CRUD operations within organizations."""

import uuid
from typing import List, Optional

from app.application.dtos import (
    UserCreate,
    UserResponse,
    UserUpdate,
)
from app.application.interfaces import (
    EventBus,
    ValidationError,
    EntityNotFoundError,
)
from app.application.interfaces.password_service import PasswordServiceInterface
from app.application.services.organization.auth_helpers import (
    verify_admin_access,
)
from app.domain.common.value_objects import Role
from app.domain.organization.factories import UserFactory
from app.domain.organization.repository import (
    OrganizationRepository,
    UserRepository,
)


class UserService:
    """Application service for user management operations."""

    def __init__(
        self,
        organization_repository: OrganizationRepository,
        user_repository: UserRepository,
        event_bus: EventBus,
        password_service: PasswordServiceInterface,
    ):
        self.organization_repository = organization_repository
        self.user_repository = user_repository
        self.event_bus = event_bus
        self.password_service = password_service

    async def create_user(
        self,
        command: UserCreate,
        current_user_id: Optional[uuid.UUID] = None,
    ) -> UserResponse:
        """Create a new user in an organization. current_user_id=None skips the admin check (bootstrap path)."""
        organization = await self.organization_repository.get_by_id(
            command.organization_id
        )
        if not organization:
            raise EntityNotFoundError(
                entity_type="Organization",
                entity_id=command.organization_id,
                code="ORGANIZATION_NOT_FOUND",
            )

        # Verify admin access if not bootstrap
        if current_user_id is not None:
            await verify_admin_access(
                self.user_repository, current_user_id, command.organization_id
            )

        # Check email uniqueness
        existing_user = await self.user_repository.get_by_email(command.email)
        if existing_user:
            raise ValidationError(f"User with email {command.email} already exists")

        hashed_password = self.password_service.hash_password(command.password)

        user = UserFactory.create_and_invite(
            organization=organization,
            username=command.username,
            email=command.email,
            temporary_password_hash=hashed_password,
            role=Role(command.role),
            invited_by_id=current_user_id,
            first_name=getattr(command, "first_name", None),
            last_name=getattr(command, "last_name", None),
            auto_activate=getattr(command, "auto_activate", False),
        )

        events = user.clear_events()
        user = await self.user_repository.create(user)

        for event in events:
            await self.event_bus.publish(event)

        return UserResponse.from_domain(user)

    async def activate_user(
        self, user_id: uuid.UUID, current_user_id: uuid.UUID
    ) -> UserResponse:
        """Activate a user."""
        user = await self.user_repository.get_by_id(user_id)
        if not user:
            raise EntityNotFoundError(
                entity_type="User",
                entity_id=user_id,
                code="USER_NOT_FOUND",
            )

        await verify_admin_access(
            self.user_repository, current_user_id, user.organization_id
        )

        user.activate()
        events = user.clear_events()
        user = await self.user_repository.update(user)

        for event in events:
            await self.event_bus.publish(event)

        return UserResponse.from_domain(user)

    async def deactivate_user(
        self, user_id: uuid.UUID, current_user_id: uuid.UUID
    ) -> UserResponse:
        """Deactivate a user."""
        user = await self.user_repository.get_by_id(user_id)
        if not user:
            raise EntityNotFoundError(
                entity_type="User",
                entity_id=user_id,
                code="USER_NOT_FOUND",
            )

        actor = await verify_admin_access(
            self.user_repository, current_user_id, user.organization_id
        )

        # SUPER_ADMIN bypasses last-X guards (platform operator can always intervene).
        if actor.role != Role.SUPER_ADMIN:
            if user.role == Role.SUPER_ADMIN:
                active_super_admin_count = (
                    await self.user_repository.count_by_organization_and_role(
                        organization_id=user.organization_id,
                        role=Role.SUPER_ADMIN,
                        only_active=True,
                    )
                )
                if active_super_admin_count <= 1:
                    raise ValidationError("Cannot deactivate the last super admin")

            if user.role == Role.ADMIN:
                active_admin_count = (
                    await self.user_repository.count_by_organization_and_role(
                        organization_id=user.organization_id,
                        role=Role.ADMIN,
                        only_active=True,
                    )
                )
                if active_admin_count <= 1:
                    raise ValidationError("Cannot deactivate the last organization admin")

        user.deactivate()
        events = user.clear_events()
        user = await self.user_repository.update(user)

        for event in events:
            await self.event_bus.publish(event)

        return UserResponse.from_domain(user)

    async def change_user_password(
        self, user_id: uuid.UUID, current_password: str, new_password: str
    ) -> None:
        """Change a user's password."""
        user = await self.user_repository.get_by_id(user_id)
        if not user:
            raise EntityNotFoundError(
                entity_type="User",
                entity_id=user_id,
                code="USER_NOT_FOUND",
            )

        if not self.password_service.verify_password(
            current_password, user.hashed_password
        ):
            raise ValidationError("Current password is incorrect")

        new_hashed_password = self.password_service.hash_password(new_password)
        user.change_password(new_hashed_password)

        await self.user_repository.update(user)

    async def list_users(
        self,
        organization_id: uuid.UUID,
        skip: int = 0,
        limit: int = 100,
        only_active: bool = False,
    ) -> List[UserResponse]:
        """List all users in an organization with pagination."""
        users = await self.user_repository.list(
            skip=skip,
            limit=limit,
            organization_id=organization_id,
            only_active=only_active,
        )
        return [UserResponse.from_domain(user) for user in users]

    async def get_user(self, user_id: uuid.UUID) -> Optional[UserResponse]:
        """Get a user by ID."""
        user = await self.user_repository.get_by_id(user_id)
        if user:
            return UserResponse.from_domain(user)
        return None

    async def update_user(
        self,
        user_id: uuid.UUID,
        command: UserUpdate,
        current_user_id: uuid.UUID,
    ) -> UserResponse:
        """Update a user. Users can update self; admins can update anyone in org."""
        user = await self.user_repository.get_by_id(user_id)
        if not user:
            raise EntityNotFoundError(
                entity_type="User",
                entity_id=user_id,
                code="USER_NOT_FOUND",
            )

        # Allow user to update self, or admin to update anyone in org
        if current_user_id != user_id:
            await verify_admin_access(
                self.user_repository, current_user_id, user.organization_id
            )

        user.update_profile(
            first_name=getattr(command, "first_name", None),
            last_name=getattr(command, "last_name", None),
            avatar_url=getattr(command, "avatar_url", None),
        )

        events = user.clear_events()
        user = await self.user_repository.update(user)

        for event in events:
            await self.event_bus.publish(event)

        return UserResponse.from_domain(user)

    async def update_user_as_admin(
        self,
        user_id: uuid.UUID,
        command: UserUpdate,
        current_user_id: uuid.UUID,
    ) -> UserResponse:
        """Update a user as an admin (supports changing username, email, role)."""
        user = await self.user_repository.get_by_id(user_id)
        if not user:
            raise EntityNotFoundError(
                entity_type="User",
                entity_id=user_id,
                code="USER_NOT_FOUND",
            )

        # Verify admin access to the user's organization
        actor = await verify_admin_access(
            self.user_repository, current_user_id, user.organization_id
        )

        # Guard clause: Prevent demoting last admin or super_admin (SUPER_ADMIN actors bypass).
        if actor.role != Role.SUPER_ADMIN and command.role is not None and command.role != user.role:
            if user.role == Role.SUPER_ADMIN and command.role != Role.SUPER_ADMIN:
                active_super_admin_count = (
                    await self.user_repository.count_by_organization_and_role(
                        organization_id=user.organization_id,
                        role=Role.SUPER_ADMIN,
                        only_active=True,
                    )
                )
                if active_super_admin_count <= 1:
                    raise ValidationError(
                        "Cannot demote the last super admin",
                    )
            elif user.role == Role.ADMIN and command.role != Role.ADMIN:
                active_admin_count = (
                    await self.user_repository.count_by_organization_and_role(
                        organization_id=user.organization_id,
                        role=Role.ADMIN,
                        only_active=True,
                    )
                )
                if active_admin_count <= 1:
                    raise ValidationError(
                        "Cannot demote the last organization admin",
                    )

        # Check uniqueness constraints
        if command.username is not None and command.username != user.username:
            existing = await self.user_repository.get_by_username(command.username)
            if existing:
                raise ValidationError(
                    f"Username '{command.username}' already exists",
                )

        if command.email is not None and command.email != user.email.email:
            existing = await self.user_repository.get_by_email(command.email)
            if existing:
                raise ValidationError(
                    f"Email '{command.email}' already exists",
                )

        # Update admin fields (username, email, role) via domain method
        user.update_admin_fields(
            username=command.username,
            email=command.email,
            role=command.role,
        )

        # Update profile fields
        user.update_profile(
            first_name=command.first_name,
            last_name=command.last_name,
        )

        # Handle is_active changes via domain methods
        if command.is_active is not None and command.is_active != user.is_active:
            if command.is_active:
                user.activate()
            else:
                # SUPER_ADMIN bypasses last-X guards.
                if actor.role != Role.SUPER_ADMIN:
                    if user.role == Role.SUPER_ADMIN:
                        active_super_admin_count = (
                            await self.user_repository.count_by_organization_and_role(
                                organization_id=user.organization_id,
                                role=Role.SUPER_ADMIN,
                                only_active=True,
                            )
                        )
                        if active_super_admin_count <= 1:
                            raise ValidationError(
                                message="Cannot deactivate the last super admin",
                                code="LAST_SUPER_ADMIN",
                                context={"field": "is_active"},
                            )
                    elif user.role == Role.ADMIN:
                        active_admin_count = (
                            await self.user_repository.count_by_organization_and_role(
                                organization_id=user.organization_id,
                                role=Role.ADMIN,
                                only_active=True,
                            )
                        )
                        if active_admin_count <= 1:
                            raise ValidationError(
                                message="Cannot deactivate the last organization admin",
                                code="LAST_ADMIN",
                                context={"field": "is_active"},
                            )
                user.deactivate()

        # Persist, publish events, return response
        events = user.clear_events()
        user = await self.user_repository.update(user)

        for event in events:
            await self.event_bus.publish(event)

        return UserResponse.from_domain(user)
