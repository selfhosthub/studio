# api/app/domain/organization/models.py

"""Domain models for the organization context: tenants, users, and relationships."""

import uuid
from datetime import UTC, datetime
from typing import Any, Dict, Optional

from pydantic import Field, field_validator

from app.domain.common import (
    ActivationMethod,
    AggregateRoot,
    Email,
    OrganizationCreatedEvent,
    OrganizationUpdatedEvent,
    OrganizationActivatedEvent,
    OrganizationDeactivatedEvent,
    OrganizationStatus,
    OrganizationStatusChangedEvent,
    OrganizationSuspendedEvent,
    Role,
    UserCreatedEvent,
    UserActivatedEvent,
    UserDeactivatedEvent,
    UserEmailVerifiedEvent,
    UserPasswordChangedEvent,
    UserProfileUpdatedEvent,
    UserLoginEvent,
)
from app.domain.common.exceptions import (
    InvalidStateTransition,
    ValidationError,
)


class User(AggregateRoot):
    """System user. Usernames and emails are globally unique so auth and password reset don't need org context."""

    username: str
    email: Email
    hashed_password: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    avatar_url: Optional[str] = None
    bio: Optional[str] = None
    is_public: bool = False
    role: Role = Role.USER
    is_active: bool = False
    last_login: Optional[datetime] = None
    organization_id: uuid.UUID
    # Token-invalidation markers: any JWT with iat older than the relevant timestamp is rejected.
    password_changed_at: Optional[datetime] = None
    role_changed_at: Optional[datetime] = None
    logged_out_at: Optional[datetime] = None

    @field_validator("username", mode="before")
    def username_must_be_valid(cls, v: str) -> str:
        v = v.strip().lower()
        if len(v) < 3:
            raise ValidationError(
                message="Username must be at least 3 characters",
                code="INVALID_USERNAME",
            )
        if not all(c.isalnum() or c in ["-", "_"] for c in v):
            raise ValidationError(
                message="Username must contain only letters, numbers, hyphens, and underscores",
                code="INVALID_USERNAME",
            )
        return v

    @classmethod
    def create(
        cls,
        username: str,
        email: str,
        hashed_password: str,
        organization_id: uuid.UUID,
        role: Role = Role.USER,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
    ) -> "User":
        user = cls(
            username=username,
            email=Email(email=email),
            hashed_password=hashed_password,
            organization_id=organization_id,
            role=role,
            first_name=first_name,
            last_name=last_name,
            is_active=False,
        )

        user.add_event(
            UserCreatedEvent(
                aggregate_id=user.id,
                aggregate_type="user",
                user_id=user.id,
                organization_id=organization_id,
                data={
                    "username": username,
                    "email": email,
                    "role": role.value,
                    "organization_id": str(organization_id),
                },
            )
        )

        return user

    def activate(self) -> None:
        if self.is_active:
            raise InvalidStateTransition(
                message="User is already active",
                code="USER_ALREADY_ACTIVE",
                context={
                    "user_id": str(self.id),
                },
            )

        self.is_active = True
        self.updated_at = datetime.now(UTC)

        self.add_event(
            UserActivatedEvent(
                aggregate_id=self.id,
                aggregate_type="user",
                user_id=self.id,
                organization_id=self.organization_id,
                data={
                    "activated_at": self.updated_at.isoformat(),
                },
            )
        )

    def deactivate(self) -> None:
        if not self.is_active:
            raise InvalidStateTransition(
                message="User is already inactive",
                code="USER_ALREADY_INACTIVE",
                context={
                    "user_id": str(self.id),
                },
            )

        self.is_active = False
        self.updated_at = datetime.now(UTC)

        self.add_event(
            UserDeactivatedEvent(
                aggregate_id=self.id,
                aggregate_type="user",
                user_id=self.id,
                organization_id=self.organization_id,
                data={
                    "deactivated_at": self.updated_at.isoformat(),
                },
            )
        )

    def record_login(self) -> None:
        self.last_login = datetime.now(UTC)

    def verify_email(self) -> None:
        """Mark email verified and activate the account."""
        if self.is_active:
            raise InvalidStateTransition(
                message="User is already active",
                code="USER_ALREADY_ACTIVE",
                context={
                    "user_id": str(self.id),
                    "email": self.email.email,
                },
            )

        self.is_active = True
        self.updated_at = datetime.now(UTC)

        self.add_event(
            UserEmailVerifiedEvent(
                aggregate_id=self.id,
                aggregate_type="user",
                user_id=self.id,
                organization_id=self.organization_id,
                data={
                    "email": self.email.email,
                    "verified_at": self.updated_at.isoformat(),
                },
            )
        )

    def update_login_time(self) -> None:
        self.last_login = datetime.now(UTC)
        self.updated_at = datetime.now(UTC)

        self.add_event(
            UserLoginEvent(
                aggregate_id=self.id,
                aggregate_type="user",
                user_id=self.id,
                organization_id=self.organization_id,
                login_time=self.last_login,
                data={
                    "login_time": self.last_login.isoformat(),
                },
            )
        )

    def update_profile(
        self,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        avatar_url: Optional[str] = None,
    ) -> None:
        """avatar_url: pass empty string to clear."""
        if first_name is not None:
            self.first_name = first_name
        if last_name is not None:
            self.last_name = last_name
        if avatar_url is not None:
            self.avatar_url = avatar_url if avatar_url else None

        self.updated_at = datetime.now(UTC)

        self.add_event(
            UserProfileUpdatedEvent(
                aggregate_id=self.id,
                aggregate_type="user",
                user_id=self.id,
                organization_id=self.organization_id,
                data={
                    "first_name": self.first_name,
                    "last_name": self.last_name,
                    "avatar_url": self.avatar_url,
                    "updated_at": self.updated_at.isoformat(),
                },
            )
        )

    def change_password(self, new_hashed_password: str) -> None:
        now = datetime.now(UTC)
        self.hashed_password = new_hashed_password
        self.updated_at = now
        # JWTs issued before this are stale.
        self.password_changed_at = now

        self.add_event(
            UserPasswordChangedEvent(
                aggregate_id=self.id,
                aggregate_type="user",
                user_id=self.id,
                organization_id=self.organization_id,
                data={
                    "changed_at": self.updated_at.isoformat(),
                },
            )
        )

    def update_admin_fields(
        self,
        username: Optional[str] = None,
        email: Optional[str] = None,
        role: Optional[Role] = None,
    ) -> None:
        """Admin-initiated update. Format-only validation here; uniqueness is the service layer's responsibility."""
        changed_fields = {}

        if username is not None:
            username = username.strip().lower()
            if username != self.username:
                if len(username) < 3:
                    raise ValidationError(
                        message="Username must be at least 3 characters",
                        code="INVALID_USERNAME",
                    )
                if not all(c.isalnum() or c in ["-", "_"] for c in username):
                    raise ValidationError(
                        message="Username must contain only letters, numbers, hyphens, and underscores",
                        code="INVALID_USERNAME",
                    )
                self.username = username
                changed_fields["username"] = username

        if email is not None and email != self.email.email:
            self.email = Email(email=email)
            changed_fields["email"] = email

        if role is not None and role != self.role:
            self.role = role
            changed_fields["role"] = role.value
            # Stale JWTs carry the old role claim.
            self.role_changed_at = datetime.now(UTC)

        if changed_fields:
            self.updated_at = datetime.now(UTC)

            self.add_event(
                UserProfileUpdatedEvent(
                    aggregate_id=self.id,
                    aggregate_type="user",
                    user_id=self.id,
                    organization_id=self.organization_id,
                    data={
                        **changed_fields,
                        "updated_at": self.updated_at.isoformat(),
                    },
                )
            )

    def log_out(self) -> None:
        """Mark logged out. JWTs issued before this are rejected; revocation lever for stolen tokens."""
        self.logged_out_at = datetime.now(UTC)
        self.updated_at = self.logged_out_at


class Organization(AggregateRoot):
    """Aggregate root for the primary tenant boundary."""

    name: str
    slug: str
    description: Optional[str] = None
    is_active: bool = True  # Deprecated; use status.
    status: OrganizationStatus = OrganizationStatus.ACTIVE
    max_users: Optional[int] = None
    max_workflows: Optional[int] = None
    settings: Dict[str, Any] = Field(default_factory=dict)

    activated_at: Optional[datetime] = None
    activated_by: Optional[uuid.UUID] = None
    activation_method: Optional[ActivationMethod] = None

    @field_validator("status", mode="before")
    @classmethod
    def convert_status_to_enum(cls, v):
        if isinstance(v, str) and not isinstance(v, OrganizationStatus):
            return OrganizationStatus(v)
        return v

    @field_validator("slug", mode="before")
    def slug_must_be_valid(cls, v: str) -> str:
        if len(v) < 3:
            raise ValidationError(
                message="Slug must be at least 3 characters",
                code="INVALID_SLUG",
            )
        if not all(c.isalnum() or c in ["-", "_"] for c in v):
            raise ValidationError(
                message="Slug must contain only lowercase letters, numbers, hyphens, and underscores",
                code="INVALID_SLUG",
            )
        if not v.islower():
            raise ValidationError(
                message="Slug must be lowercase",
                code="INVALID_SLUG",
            )
        return v

    @classmethod
    def create(
        cls,
        name: str,
        slug: str,
        description: Optional[str] = None,
        max_users: Optional[int] = None,
        max_workflows: Optional[int] = None,
        status: OrganizationStatus = OrganizationStatus.ACTIVE,
        auto_activate: bool = True,
    ) -> "Organization":
        """status defaults ACTIVE for backwards compat. auto_activate sets activation tracking when initially active."""
        now = datetime.now(UTC)
        is_active = status == OrganizationStatus.ACTIVE

        org = cls(
            name=name,
            slug=slug,
            description=description,
            is_active=is_active,
            status=status,
            max_users=max_users,
            max_workflows=max_workflows,
            activated_at=now if is_active and auto_activate else None,
            activation_method=(
                ActivationMethod.AUTO if is_active and auto_activate else None
            ),
        )

        org.add_event(
            OrganizationCreatedEvent(
                aggregate_id=org.id,
                aggregate_type="organization",
                organization_id=org.id,
                data={
                    "name": name,
                    "slug": slug,
                    "status": status.value,
                },
            )
        )

        return org

    def update(
        self,
        name: Optional[str] = None,
        description: Optional[str] = None,
        max_users: Optional[int] = None,
        max_workflows: Optional[int] = None,
        settings: Optional[Dict[str, Any]] = None,
    ) -> None:
        if name is not None:
            self.name = name
        if description is not None:
            self.description = description
        if max_users is not None:
            self.max_users = max_users
        if max_workflows is not None:
            self.max_workflows = max_workflows
        if settings is not None:
            self.settings = settings

        self.updated_at = datetime.now(UTC)

        self.add_event(
            OrganizationUpdatedEvent(
                aggregate_id=self.id,
                aggregate_type="organization",
                organization_id=self.id,
                data={
                    "name": self.name,
                    "slug": self.slug,
                    "description": self.description,
                    "max_users": self.max_users,
                    "max_workflows": self.max_workflows,
                    "settings": self.settings,
                    "updated_at": self.updated_at.isoformat(),
                },
            )
        )

    def activate(
        self,
        activated_by: Optional[uuid.UUID] = None,
        method: ActivationMethod = ActivationMethod.MANUAL,
    ) -> None:
        if self.status == OrganizationStatus.ACTIVE:
            raise InvalidStateTransition(
                message="Organization is already active",
                code="ORG_ALREADY_ACTIVE",
                context={
                    "organization_id": str(self.id),
                },
            )

        old_status = self.status
        self.status = OrganizationStatus.ACTIVE
        self.is_active = True
        self.activated_at = datetime.now(UTC)
        self.activated_by = activated_by
        self.activation_method = method
        self.updated_at = datetime.now(UTC)

        self.add_event(
            OrganizationActivatedEvent(
                aggregate_id=self.id,
                aggregate_type="organization",
                organization_id=self.id,
                data={
                    "activated_at": self.activated_at.isoformat(),
                    "activated_by": str(activated_by) if activated_by else None,
                    "activation_method": method.value,
                    "previous_status": old_status.value,
                },
            )
        )

    def deactivate(self) -> None:
        """Set to SUSPENDED. Typical use: billing issues or policy violations."""
        if self.status == OrganizationStatus.SUSPENDED:
            raise InvalidStateTransition(
                message="Organization is already suspended",
                code="ORG_ALREADY_SUSPENDED",
                context={
                    "organization_id": str(self.id),
                },
            )

        old_status = self.status
        self.status = OrganizationStatus.SUSPENDED
        self.is_active = False
        self.updated_at = datetime.now(UTC)

        self.add_event(
            OrganizationDeactivatedEvent(
                aggregate_id=self.id,
                aggregate_type="organization",
                organization_id=self.id,
                data={
                    "deactivated_at": self.updated_at.isoformat(),
                    "previous_status": old_status.value,
                },
            )
        )

    def suspend(self, reason: Optional[str] = None) -> None:
        if self.status == OrganizationStatus.SUSPENDED:
            raise InvalidStateTransition(
                message="Organization is already suspended",
                code="ORG_ALREADY_SUSPENDED",
                context={
                    "organization_id": str(self.id),
                },
            )

        old_status = self.status
        self.status = OrganizationStatus.SUSPENDED
        self.is_active = False
        self.updated_at = datetime.now(UTC)

        self.add_event(
            OrganizationSuspendedEvent(
                aggregate_id=self.id,
                aggregate_type="organization",
                organization_id=self.id,
                data={
                    "suspended_at": self.updated_at.isoformat(),
                    "previous_status": old_status.value,
                    "reason": reason,
                },
            )
        )

    def set_pending_approval(self) -> None:
        if self.status == OrganizationStatus.PENDING_APPROVAL:
            raise InvalidStateTransition(
                message="Organization is already pending approval",
                code="ORG_ALREADY_PENDING",
                context={
                    "organization_id": str(self.id),
                },
            )

        old_status = self.status
        self.status = OrganizationStatus.PENDING_APPROVAL
        self.is_active = False
        self.updated_at = datetime.now(UTC)

        self.add_event(
            OrganizationStatusChangedEvent(
                aggregate_id=self.id,
                aggregate_type="organization",
                organization_id=self.id,
                old_status=old_status.value,
                new_status=OrganizationStatus.PENDING_APPROVAL.value,
                data={
                    "changed_at": self.updated_at.isoformat(),
                },
            )
        )

    def can_execute_workflows(self) -> bool:
        return self.status == OrganizationStatus.ACTIVE

    def can_build_resources(self) -> bool:
        return self.status in (
            OrganizationStatus.ACTIVE,
            OrganizationStatus.PENDING_APPROVAL,
        )

    def is_read_only(self) -> bool:
        return self.status == OrganizationStatus.SUSPENDED
