# api/app/application/services/organization/auth_helpers.py

"""Authorization helpers for organization and user operations."""

import uuid

from app.application.interfaces import EntityNotFoundError
from app.application.interfaces.exceptions import PermissionDeniedError
from app.domain.common.value_objects import Role
from app.domain.organization.models import User
from app.domain.organization.repository import UserRepository


async def verify_admin_access(
    user_repository: UserRepository,
    user_id: uuid.UUID,
    organization_id: uuid.UUID,
) -> User:
    """Verify user is an admin in the organization, returning the actor.

    SUPER_ADMIN has unrestricted access to all organizations.
    Regular ADMIN can only access their own organization.
    """
    user = await user_repository.get_by_id(user_id)
    if not user:
        raise EntityNotFoundError(
            entity_type="User",
            entity_id=user_id,
            code="USER_NOT_FOUND",
        )

    # SUPER_ADMIN can do anything - bypass all checks
    if user.role == Role.SUPER_ADMIN:
        return user

    # Regular ADMIN must be in the same organization
    if user.organization_id != organization_id:
        raise EntityNotFoundError(
            entity_type="User",
            entity_id=user_id,
            code="USER_NOT_IN_ORGANIZATION",
        )

    if user.role != Role.ADMIN:
        raise PermissionDeniedError(
            message="Only admins can perform this action",
            code="INSUFFICIENT_PERMISSIONS",
        )

    return user


async def verify_super_admin_access(
    user_repository: UserRepository,
    user_id: uuid.UUID,
) -> None:
    """Verify user is a SUPER_ADMIN."""
    user = await user_repository.get_by_id(user_id)
    if not user:
        raise EntityNotFoundError(
            entity_type="User",
            entity_id=user_id,
            code="USER_NOT_FOUND",
        )

    if user.role != Role.SUPER_ADMIN:
        raise PermissionDeniedError(
            message="Only super admins can perform this action",
            code="SUPER_ADMIN_REQUIRED",
        )
