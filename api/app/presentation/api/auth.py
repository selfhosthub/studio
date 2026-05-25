# api/app/presentation/api/auth.py

"""Authentication API endpoints."""

from typing import Any, Dict
import uuid
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr

from app.domain.organization.repository import (
    OrganizationRepository,
    UserRepository,
)
from app.domain.organization.models import Organization, User, Role
from app.infrastructure.auth.jwt import (
    create_access_token,
    create_refresh_token,
    verify_refresh_token,
)
from app.infrastructure.auth.password import verify_password, hash_password
from app.application.services.audit_service import AuditService
from app.domain.audit.models import (
    AuditAction,
    AuditActorType,
    AuditCategory,
    AuditSeverity,
    AuditStatus,
    ResourceType,
)
from app.application.services.public_content_service import PublicContentService
from app.presentation.api.dependencies import (
    get_audit_service,
    get_organization_repository,
    get_public_content_service,
    get_user_repository_bypass,
)
from app.infrastructure.auth.jwt import get_current_user
from app.presentation.api.public import get_allow_registration

logger = logging.getLogger(__name__)

router = APIRouter()


class RegisterRequest(BaseModel):
    first_name: str
    last_name: str
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


def generate_unique_slug(first_name: str, last_name: str) -> str:
    """URL-safe slug like 'john-doe-abc123' (random suffix ensures uniqueness)."""
    base_slug = f"{first_name.lower()}-{last_name.lower()}"
    base_slug = "".join(c if c.isalnum() or c == "-" else "" for c in base_slug)
    random_suffix = str(uuid.uuid4())[:6]
    return f"{base_slug}-{random_suffix}"


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(
    request: RegisterRequest,
    public_content_service: PublicContentService = Depends(get_public_content_service),
    user_repository: UserRepository = Depends(get_user_repository_bypass),
    organization_repository: OrganizationRepository = Depends(
        get_organization_repository
    ),
    audit_service: AuditService = Depends(get_audit_service),
) -> Dict[str, str]:
    """Public. Creates org + admin user + returns JWT. 403 if registration disabled."""
    if not await get_allow_registration(public_content_service):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Registration is currently disabled",
        )

    existing_user = await user_repository.get_by_email(request.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    org_name = f"{request.first_name} {request.last_name}'s Organization"
    org_slug = generate_unique_slug(request.first_name, request.last_name)

    organization = Organization.create(
        name=org_name,
        slug=org_slug,
        description=None,
    )

    organization = await organization_repository.create(organization)

    hashed_password = hash_password(request.password)

    # Username from email local-part, sanitized to alnum/-/_, then min length 3
    username_base = request.email.split("@")[0]
    username = "".join(
        c if c.isalnum() or c in ["-", "_"] else "" for c in username_base
    )
    if len(username) < 3:
        username = f"user_{str(uuid.uuid4())[:8]}"

    user = User.create(
        username=username,
        email=request.email,
        hashed_password=hashed_password,
        organization_id=organization.id,
        role=Role.ADMIN,
        first_name=request.first_name,
        last_name=request.last_name,
    )

    user.activate()

    user = await user_repository.create(user)

    try:
        await audit_service.log_event(
            actor_id=user.id,
            actor_type=AuditActorType(user.role.value),
            action=AuditAction.CREATE,
            resource_type=ResourceType.USER,
            resource_id=user.id,
            resource_name=user.email.email,
            organization_id=organization.id,
            severity=AuditSeverity.INFO,
            category=AuditCategory.SECURITY,
            metadata={
                "registration": True,
                "org_name": org_name,
            },
        )
    except Exception:
        pass

    token_data: Dict[str, Any] = {
        "sub": str(user.id),
        "username": user.username,
        "email": user.email.email,
        "role": user.role.value,
        "org_id": str(user.organization_id),
        "org_slug": organization.slug,
        "first_name": user.first_name,
        "last_name": user.last_name,
    }

    access_token: str = create_access_token(token_data)
    refresh_token: str = create_refresh_token(str(user.id))
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
    }


@router.post("/token")
async def login_for_access_token(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    user_repository: UserRepository = Depends(get_user_repository_bypass),
    organization_repository: OrganizationRepository = Depends(
        get_organization_repository
    ),
    audit_service: AuditService = Depends(get_audit_service),
) -> Dict[str, str]:
    """OAuth2 password grant. 401 invalid credentials, disabled user, or inactive org."""
    user = await user_repository.get_by_username(form_data.username)

    if not user:
        user = await user_repository.get_by_email(form_data.username)

    if not user or not verify_password(form_data.password, user.hashed_password):
        try:
            await audit_service.log_event(
                actor_id=None,
                actor_type=AuditActorType.ANONYMOUS,
                action=AuditAction.LOGIN_FAILED,
                resource_type=ResourceType.USER,
                severity=AuditSeverity.WARNING,
                category=AuditCategory.SECURITY,
                status=AuditStatus.FAILED,
                error_message="Invalid credentials",
                metadata={
                    "attempted_username": form_data.username,
                    "ip_address": request.client.host if request.client else None,
                    "user_agent": request.headers.get("user-agent"),
                },
            )
        except Exception:
            pass
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        try:
            await audit_service.log_event(
                actor_id=user.id,
                actor_type=AuditActorType(user.role.value),
                action=AuditAction.LOGIN_FAILED,
                resource_type=ResourceType.USER,
                resource_id=user.id,
                resource_name=user.email.email,
                organization_id=user.organization_id,
                severity=AuditSeverity.WARNING,
                category=AuditCategory.SECURITY,
                status=AuditStatus.FAILED,
                error_message="User account disabled",
                metadata={
                    "ip_address": request.client.host if request.client else None,
                    "user_agent": request.headers.get("user-agent"),
                },
            )
        except Exception:
            pass
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is disabled",
            headers={"WWW-Authenticate": "Bearer"},
        )

    org_id = user.organization_id

    org_slug = None
    if org_id:
        organization = await organization_repository.get_by_id(org_id)
        org_slug = organization.slug if organization else None

        if organization is None or not organization.is_active:
            try:
                await audit_service.log_event(
                    actor_id=user.id,
                    actor_type=AuditActorType(user.role.value),
                    action=AuditAction.LOGIN_FAILED,
                    resource_type=ResourceType.USER,
                    resource_id=user.id,
                    resource_name=user.email.email,
                    organization_id=org_id,
                    severity=AuditSeverity.WARNING,
                    category=AuditCategory.SECURITY,
                    status=AuditStatus.FAILED,
                    error_message="Organization is not active",
                    metadata={
                        "ip_address": request.client.host if request.client else None,
                        "user_agent": request.headers.get("user-agent"),
                    },
                )
            except Exception:
                pass
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect username or password",
                headers={"WWW-Authenticate": "Bearer"},
            )

    user.record_login()
    await user_repository.update(user)

    try:
        await audit_service.log_event(
            actor_id=user.id,
            actor_type=AuditActorType(user.role.value),
            action=AuditAction.LOGIN,
            resource_type=ResourceType.USER,
            resource_id=user.id,
            resource_name=user.email.email,
            organization_id=org_id,
            severity=AuditSeverity.INFO,
            category=AuditCategory.SECURITY,
            metadata={
                "username": user.username,
                "org_slug": org_slug,
                "ip_address": request.client.host if request.client else None,
                "user_agent": request.headers.get("user-agent"),
            },
        )
    except Exception:
        pass

    token_data: Dict[str, Any] = {
        "sub": str(user.id),
        "username": user.username,
        "email": user.email.email,
        "role": user.role.value,
        "org_id": str(org_id) if org_id else None,
        "org_slug": org_slug,
        "first_name": user.first_name,
        "last_name": user.last_name,
    }

    access_token: str = create_access_token(token_data)
    refresh_token: str = create_refresh_token(str(user.id))
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
    }


@router.post("/refresh")
async def refresh_access_token(
    http_request: Request,
    request: RefreshRequest,
    user_repository: UserRepository = Depends(get_user_repository_bypass),
    organization_repository: OrganizationRepository = Depends(
        get_organization_repository
    ),
    audit_service: AuditService = Depends(get_audit_service),
) -> Dict[str, str]:
    """Rotates refresh token. 401 on invalid token, missing user, or disabled user."""
    payload = verify_refresh_token(request.refresh_token)
    user_id = payload.get("sub")

    user = await user_repository.get_by_id(uuid.UUID(user_id))
    if not user:
        try:
            await audit_service.log_event(
                actor_id=None,
                actor_type=AuditActorType.ANONYMOUS,
                action=AuditAction.TOKEN_REFRESH,
                resource_type=ResourceType.USER,
                severity=AuditSeverity.WARNING,
                category=AuditCategory.SECURITY,
                status=AuditStatus.FAILED,
                error_message="User not found",
                metadata={
                    "attempted_user_id": user_id,
                    "ip_address": (
                        http_request.client.host if http_request.client else None
                    ),
                },
            )
        except Exception:
            pass
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        try:
            await audit_service.log_event(
                actor_id=user.id,
                actor_type=AuditActorType(user.role.value),
                action=AuditAction.TOKEN_REFRESH,
                resource_type=ResourceType.USER,
                resource_id=user.id,
                resource_name=user.email.email,
                organization_id=user.organization_id,
                severity=AuditSeverity.WARNING,
                category=AuditCategory.SECURITY,
                status=AuditStatus.FAILED,
                error_message="User account disabled",
                metadata={
                    "ip_address": (
                        http_request.client.host if http_request.client else None
                    ),
                },
            )
        except Exception:
            pass
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is disabled",
            headers={"WWW-Authenticate": "Bearer"},
        )

    org_id = user.organization_id
    org_slug = None
    if org_id:
        organization = await organization_repository.get_by_id(org_id)
        org_slug = organization.slug if organization else None

    token_data: Dict[str, Any] = {
        "sub": str(user.id),
        "username": user.username,
        "email": user.email.email,
        "role": user.role.value,
        "org_id": str(org_id) if org_id else None,
        "org_slug": org_slug,
        "first_name": user.first_name,
        "last_name": user.last_name,
    }

    access_token: str = create_access_token(token_data)
    new_refresh_token: str = create_refresh_token(str(user.id))

    try:
        await audit_service.log_event(
            actor_id=user.id,
            actor_type=AuditActorType(user.role.value),
            action=AuditAction.TOKEN_REFRESH,
            resource_type=ResourceType.USER,
            resource_id=user.id,
            organization_id=org_id,
            severity=AuditSeverity.INFO,
            category=AuditCategory.SECURITY,
            metadata={
                "org_slug": org_slug,
                "ip_address": http_request.client.host if http_request.client else None,
            },
        )
    except Exception:
        pass

    return {
        "access_token": access_token,
        "refresh_token": new_refresh_token,
        "token_type": "bearer",
    }


@router.post("/logout")
async def logout(
    request: Request,
    user: Dict[str, Any] = Depends(get_current_user),
    audit_service: AuditService = Depends(get_audit_service),
    user_repository: UserRepository = Depends(get_user_repository_bypass),
) -> Dict[str, str]:
    """Sets logged_out_at; JWTs with iat<logged_out_at are then rejected. Refresh tokens reject immediately; access tokens bounded by TTL."""
    user_id = user.get("id", user.get("sub", ""))
    org_id = user.get("org_id")

    try:
        user_uuid = uuid.UUID(str(user_id))
        domain_user = await user_repository.get_by_id(user_uuid)
        if domain_user is not None:
            domain_user.log_out()
            await user_repository.update(domain_user)
    except Exception as e:
        # Don't block audit/response on a stamp failure - but log: this is
        # security-relevant state we expected to update.
        logger.error(f"logout: failed to set logged_out_at for user {user_id}: {e}")

    try:
        await audit_service.log_event(
            actor_id=uuid.UUID(str(user_id)),
            actor_type=AuditActorType(user.get("role", "user")),
            action=AuditAction.LOGOUT,
            resource_type=ResourceType.USER,
            resource_id=uuid.UUID(str(user_id)),
            organization_id=uuid.UUID(org_id) if org_id else None,
            severity=AuditSeverity.INFO,
            category=AuditCategory.SECURITY,
            metadata={
                "username": user.get("username"),
                "org_slug": user.get("org_slug"),
                "ip_address": request.client.host if request.client else None,
            },
        )
    except Exception:
        pass

    return {"message": "Successfully logged out"}
