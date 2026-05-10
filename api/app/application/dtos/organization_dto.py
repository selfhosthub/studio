# api/app/application/dtos/organization_dto.py

"""DTOs for organization operations."""
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, EmailStr

from app.domain.common.value_objects import ActivationMethod, OrganizationStatus, Role
from app.domain.organization.models import Organization, User


class OrganizationBase(BaseModel):
    name: str
    slug: str
    description: Optional[str] = None
    settings: Optional[Dict[str, Any]] = None


class OrganizationCreate(OrganizationBase):
    pass


class OrganizationUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    settings: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None
    updated_by: uuid.UUID


class OrganizationResponse(OrganizationBase):
    id: uuid.UUID
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    is_active: bool
    status: OrganizationStatus = OrganizationStatus.ACTIVE
    activated_at: Optional[datetime] = None
    activated_by: Optional[uuid.UUID] = None
    activation_method: Optional[ActivationMethod] = None

    @classmethod
    def from_domain(cls, org: Organization) -> "OrganizationResponse":
        return cls(
            id=org.id,
            name=org.name,
            slug=org.slug,
            description=org.description,
            settings=org.settings,
            created_at=org.created_at,
            updated_at=org.updated_at,
            is_active=org.is_active,
            status=org.status,
            activated_at=org.activated_at,
            activated_by=org.activated_by,
            activation_method=org.activation_method,
        )


class OrganizationActivation(BaseModel):
    method: ActivationMethod = ActivationMethod.MANUAL
    activated_by: uuid.UUID


class OrganizationSuspend(BaseModel):
    reason: Optional[str] = None
    suspended_by: uuid.UUID


class UserBase(BaseModel):
    username: str
    email: EmailStr
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    role: Role = Role.USER


class UserCreate(UserBase):
    password: str
    organization_id: uuid.UUID
    auto_activate: bool = False


class UserUpdate(BaseModel):
    username: Optional[str] = None
    email: Optional[EmailStr] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    role: Optional[Role] = None
    is_active: Optional[bool] = None
    password: Optional[str] = None
    avatar_url: Optional[str] = None


class UserActivation(BaseModel):
    is_active: bool


class UserResponse(UserBase):
    id: uuid.UUID
    avatar_url: Optional[str] = None
    organization_id: uuid.UUID
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    is_active: bool

    @classmethod
    def from_domain(cls, user: User) -> "UserResponse":
        return cls(
            id=user.id,
            username=user.username,
            email=user.email.email,
            first_name=user.first_name,
            last_name=user.last_name,
            avatar_url=user.avatar_url,
            organization_id=user.organization_id,
            role=user.role,
            created_at=user.created_at,
            updated_at=user.updated_at,
            is_active=user.is_active,
        )
