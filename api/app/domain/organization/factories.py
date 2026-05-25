# api/app/domain/organization/factories.py

"""Factory classes for the organization domain."""
import uuid
from typing import Optional

from app.domain.common import Role
from app.domain.organization.models import (
    Organization,
    User,
)
from app.domain.common.exceptions import (
    ValidationError as DomainValidationError,
)


class UserFactory:
    """Creates users with proper initialization."""

    @staticmethod
    def create_and_invite(
        organization: Organization,
        username: str,
        email: str,
        temporary_password_hash: str,
        role: Role,
        invited_by_id: Optional[uuid.UUID] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        auto_activate: bool = False,
        current_user_count: Optional[int] = None,
        existing_emails: Optional[list[str]] = None,
        existing_usernames: Optional[list[str]] = None,
    ) -> User:
        """Create a user and add them to an organization. existing_emails/usernames pre-filter for uniqueness."""
        if existing_emails is not None and email in existing_emails:
            raise DomainValidationError(
                message=f"User with email {email} already exists",
                code="EMAIL_ALREADY_EXISTS",
                context={
                    "email": email,
                    "organization_id": str(organization.id),
                },
            )

        if existing_usernames is not None and username in existing_usernames:
            raise DomainValidationError(
                message=f"User with username {username} already exists",
                code="USERNAME_ALREADY_EXISTS",
                context={
                    "username": username,
                    "organization_id": str(organization.id),
                },
            )

        user = User.create(
            username=username,
            email=email,
            hashed_password=temporary_password_hash,
            organization_id=organization.id,
            role=role,
            first_name=first_name,
            last_name=last_name,
        )

        if auto_activate:
            user.verify_email()

        return user
