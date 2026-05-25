# api/app/presentation/api/organizations.py

"""Organization and user management API endpoints."""
import logging
from datetime import datetime
from pathlib import Path as FilePath
from typing import Any, Dict, List, Optional
from uuid import UUID

from app.config.settings import settings
from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel

from app.application.dtos.organization_dto import (
    OrganizationCreate as OrganizationCreateDTO,
    OrganizationResponse,
    OrganizationUpdate as OrganizationUpdateDTO,
    UserCreate as UserCreateDTO,
    UserResponse,
    UserUpdate as UserUpdateDTO,
)
from app.application.interfaces.exceptions import PermissionDeniedError, ValidationError
from app.application.services.organization import OrganizationService
from app.application.services.provider_service import ProviderService
from app.domain.common.exceptions import EntityNotFoundError
from app.domain.common.exceptions import InvalidStateTransition
from app.domain.common.value_objects import Role
from app.domain.organization.repository import OrganizationRepository, UserRepository
from app.domain.workflow.repository import WorkflowRepository
from app.presentation.api.dependencies import (
    get_audit_service,
    get_current_user,
    get_organization_repository,
    get_organization_service,
    get_provider_service,
    get_user_repository,
    get_user_repository_bypass,
    get_workflow_repository,
    require_admin,
    require_super_admin,
    verify_org_access,
    verify_org_access_strict,
)
from app.presentation.api.models.organization import (
    AdminUserUpdateRequest,
    OrganizationCreate as OrganizationCreateRequest,
    OrganizationUpdate as OrganizationUpdateRequest,
    PasswordChangeRequest,
    UserCreate as UserCreateRequest,
    UserResponse as UserResponseModel,
    UserUpdateRequest,
)
from app.application.services.audit_service import AuditService
from app.domain.audit.models import AuditAction, AuditActorType, AuditSeverity, AuditCategory, ResourceType
from app.infrastructure.errors import safe_error_message

logger = logging.getLogger(__name__)


# =============================================================================
# Response Models for Organization Stats
# =============================================================================


class OrganizationStorageStats(BaseModel):
    files: int = 0
    size_bytes: int = 0
    size_formatted: str = "0 B"


class OrganizationStats(BaseModel):
    id: UUID
    name: str
    slug: str
    description: Optional[str] = None
    is_active: bool
    status: str = "active"  # pending_approval, active, suspended
    is_system: bool = False  # System org (super-admin's org)
    created_at: Optional[datetime] = None
    activated_at: Optional[datetime] = None
    # Stats
    member_count: int = 0
    workflow_count: int = 0
    storage: OrganizationStorageStats = OrganizationStorageStats()


class OrganizationStatsListResponse(BaseModel):
    organizations: List[OrganizationStats]
    total: int
    skip: int
    limit: int


router = APIRouter()


@router.post(
    "/", response_model=OrganizationResponse, status_code=status.HTTP_201_CREATED
)
async def create_organization(
    organization: OrganizationCreateRequest,
    user: Dict[str, Any] = Depends(require_admin),
    service: OrganizationService = Depends(get_organization_service),
):
    """Requires SUPER_ADMIN privileges."""
    try:
        dto = OrganizationCreateDTO(
            name=organization.name,
            slug=organization.slug,
            description=organization.description,
            settings=organization.settings,
        )
        return await service.create_organization(dto, user["id"])
    except PermissionDeniedError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=safe_error_message(e))
    except (ValueError, ValidationError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=safe_error_message(e))


@router.get("/", response_model=List[OrganizationResponse])
async def list_organizations(
    skip: int = Query(0, ge=0),
    limit: int = Query(settings.API_PAGE_LIMIT_DEFAULT, ge=1, le=settings.API_PAGE_MAX),
    user: Dict[str, Any] = Depends(require_admin),
    service: OrganizationService = Depends(get_organization_service),
):
    """Requires admin privileges."""
    return await service.list_organizations()


def _format_bytes(size_bytes: int) -> str:
    size: float = float(size_bytes)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024.0:
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} PB"


def _get_org_storage_stats(org_id: str) -> OrganizationStorageStats:
    workspace_path = settings.WORKSPACE_ROOT
    if not workspace_path:
        raise RuntimeError("WORKSPACE_ROOT environment variable is not set")
    workspace = FilePath(workspace_path)
    org_base = workspace / "orgs" / org_id

    files = 0
    size_bytes = 0

    # Count files in both instances/ and uploads/ directories
    for subdir in ["instances", "uploads"]:
        dir_path = org_base / subdir
        if dir_path.exists():
            for f in dir_path.rglob("*"):
                if f.is_file():
                    files += 1
                    try:
                        size_bytes += f.stat().st_size
                    except (OSError, IOError):
                        pass

    return OrganizationStorageStats(
        files=files,
        size_bytes=size_bytes,
        size_formatted=_format_bytes(size_bytes),
    )


@router.get("/stats", response_model=OrganizationStatsListResponse)
async def list_organization_stats(
    skip: int = Query(0, ge=0),
    limit: int = Query(settings.API_PAGE_LIMIT_SMALL, ge=1, le=settings.API_PAGE_MAX),
    filter: Optional[str] = Query(
        None,
        description="Filter: 'all', 'active', 'inactive'",
        pattern="^(all|active|inactive)$",
    ),
    sort_by: Optional[str] = Query(
        None,
        description="Sort by: 'name', 'created_at', 'member_count', 'workflow_count', 'storage'",
    ),
    sort_order: Optional[str] = Query(
        "asc",
        description="Sort order: 'asc' or 'desc'",
        pattern="^(asc|desc)$",
    ),
    user: Dict[str, Any] = Depends(require_super_admin),
    org_repo: OrganizationRepository = Depends(get_organization_repository),
    user_repo: UserRepository = Depends(get_user_repository),
    workflow_repo: WorkflowRepository = Depends(get_workflow_repository),
):
    """List organizations with member/workflow/storage stats. Requires SUPER_ADMIN."""
    all_orgs = await org_repo.list_all()

    org_stats_list: List[OrganizationStats] = []

    for org in all_orgs:
        if filter == "active" and not org.is_active:
            continue
        if filter == "inactive" and org.is_active:
            continue

        member_count = 0
        try:
            members = await user_repo.find_active_users_in_organization(
                org.id, skip=0, limit=10000
            )
            member_count = len(members)
        except Exception as e:
            import logging

            logging.error(
                f"Failed to get members for org {org.id}: {type(e).__name__}: {e}"
            )

        workflow_count = 0
        try:
            workflows = await workflow_repo.list_by_organization(
                org.id, skip=0, limit=10000
            )
            workflow_count = len(workflows)
        except Exception as e:
            import logging

            logging.error(
                f"Failed to get workflows for org {org.id}: {type(e).__name__}: {e}"
            )

        storage = _get_org_storage_stats(str(org.id))
        is_system = org.settings.get("is_system", False) if org.settings else False

        org_stats_list.append(
            OrganizationStats(
                id=org.id,
                name=org.name,
                slug=org.slug,
                description=org.description,
                is_active=org.is_active,
                status=(
                    org.status.value
                    if hasattr(org, "status") and org.status
                    else "active"
                ),
                is_system=is_system,
                created_at=org.created_at,
                activated_at=org.activated_at if hasattr(org, "activated_at") else None,
                member_count=member_count,
                workflow_count=workflow_count,
                storage=storage,
            )
        )

    # System org is always pinned at top of results
    system_org: Optional[OrganizationStats] = None
    other_orgs: List[OrganizationStats] = []
    for org_stat in org_stats_list:
        if org_stat.is_system:
            system_org = org_stat
        else:
            other_orgs.append(org_stat)

    if sort_by:
        reverse = sort_order == "desc"
        if sort_by == "name":
            other_orgs.sort(key=lambda x: x.name.lower(), reverse=reverse)
        elif sort_by == "created_at":
            other_orgs.sort(key=lambda x: x.created_at or datetime.min, reverse=reverse)
        elif sort_by == "member_count":
            other_orgs.sort(key=lambda x: x.member_count, reverse=reverse)
        elif sort_by == "workflow_count":
            other_orgs.sort(key=lambda x: x.workflow_count, reverse=reverse)
        elif sort_by == "storage":
            other_orgs.sort(key=lambda x: x.storage.size_bytes, reverse=reverse)

    org_stats_list = ([system_org] if system_org else []) + other_orgs
    total = len(org_stats_list)
    paginated = org_stats_list[skip : skip + limit]

    return OrganizationStatsListResponse(
        organizations=paginated,
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/{organization_id}", response_model=OrganizationResponse)
async def get_organization(
    organization_id: UUID = Path(...),
    verified_org_id: UUID = Depends(verify_org_access),
    service: OrganizationService = Depends(get_organization_service),
):
    """Users can only view their own org; super_admin has read-only access to any org."""
    organization = await service.get_organization(organization_id)
    if not organization:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found",
        )

    return organization


@router.patch("/{organization_id}", response_model=OrganizationResponse)
async def update_organization(
    organization_id: UUID,
    update_data: OrganizationUpdateRequest,
    user: Dict[str, Any] = Depends(require_admin),
    service: OrganizationService = Depends(get_organization_service),
    audit_service: AuditService = Depends(get_audit_service),
):
    """Requires admin privileges. Branding changes require super_admin."""
    current_user_id = UUID(user["id"])

    # Branding settings can only be modified by super-admins
    if update_data.settings and "branding" in update_data.settings:
        if user.get("role") != "super_admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only super-admins can modify branding settings",
            )

    try:
        existing_org = await service.get_organization(organization_id)

        dto = OrganizationUpdateDTO(
            name=update_data.name,
            description=update_data.description,
            settings=update_data.settings,
            is_active=update_data.is_active,
            updated_by=current_user_id,
        )
        updated_org = await service.update_organization(organization_id, dto, current_user_id)

        # Track what changed for audit log
        changes = {}
        if existing_org:
            if update_data.name and update_data.name != existing_org.name:
                changes["name"] = {"old": existing_org.name, "new": update_data.name}
            if update_data.description is not None and update_data.description != existing_org.description:
                changes["description"] = {"changed": True}
            if update_data.settings is not None:
                # Check for branding changes
                old_settings = existing_org.settings or {}
                new_settings = update_data.settings or {}
                old_branding = old_settings.get("branding", {})
                new_branding = new_settings.get("branding", {})
                if old_branding != new_branding:
                    changes["branding"] = {"changed": True}
                # Check for other settings changes
                if {k: v for k, v in old_settings.items() if k != "branding"} != {k: v for k, v in new_settings.items() if k != "branding"}:
                    changes["settings"] = {"changed": True}
            if update_data.is_active is not None and update_data.is_active != existing_org.is_active:
                changes["is_active"] = {"old": existing_org.is_active, "new": update_data.is_active}

        # Determine severity based on what changed
        severity = AuditSeverity.INFO
        if "is_active" in changes:
            severity = AuditSeverity.WARNING

        # Audit log the organization update
        await audit_service.log_event(
            actor_id=current_user_id,
            actor_type=AuditActorType(user.get("role", "admin")),
            action=AuditAction.UPDATE,
            resource_type=ResourceType.ORGANIZATION,
            resource_id=organization_id,
            resource_name=updated_org.name,
            organization_id=organization_id,
            severity=severity,
            category=AuditCategory.CONFIGURATION,
            changes=changes if changes else {"updated": True},
        )

        return updated_org
    except PermissionDeniedError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=safe_error_message(e))
    except EntityNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found",
        )
    except (ValueError, ValidationError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=safe_error_message(e))


@router.get("/{organization_id}/members", response_model=List[UserResponseModel])
async def get_organization_members(
    organization_id: UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(settings.API_PAGE_LIMIT_DEFAULT, ge=1, le=settings.API_PAGE_MAX),
    verified_org_id: UUID = Depends(verify_org_access),
    user: Dict[str, Any] = Depends(get_current_user),
    service: OrganizationService = Depends(get_organization_service),
):
    """
    List organization members.

    Users can only view members of their own organization.
    Super admin can view members of any organization (read-only support access).
    """
    user_role = user.get("role", "user")

    # Regular users need admin role to view member list
    if user_role == Role.USER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required to view member list",
        )

    users = await service.list_users(organization_id, skip=skip, limit=limit)
    return [
        UserResponseModel(
            id=u.id,
            username=u.username,
            email=u.email,
            first_name=u.first_name,
            last_name=u.last_name,
            organization_id=organization_id,
            role=u.role,
            is_active=u.is_active,
            created_at=u.created_at,
            updated_at=u.updated_at,
        )
        for u in users
    ]


@router.post(
    "/{organization_id}/members",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_organization_member(
    organization_id: UUID,
    user_request: UserCreateRequest,
    user: Dict[str, Any] = Depends(require_admin),
    service: OrganizationService = Depends(get_organization_service),
):
    """
    Add a new member to organization.

    Requires admin privileges.
    """
    current_user_id = UUID(user["id"])

    try:
        dto = UserCreateDTO(
            username=user_request.username,
            email=user_request.email,
            password=user_request.password,
            organization_id=organization_id,
            role=user_request.role,
            first_name=user_request.first_name,
            last_name=user_request.last_name,
            auto_activate=True,  # Users created via admin invite are auto-activated
        )
        return await service.create_user(dto, current_user_id=current_user_id)
    except (ValueError, ValidationError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=safe_error_message(e))


@router.delete(
    "/{organization_id}/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_organization_member(
    organization_id: UUID,
    user_id: UUID,
    user: Dict[str, Any] = Depends(require_admin),
    service: OrganizationService = Depends(get_organization_service),
):
    """
    Remove a member from organization.

    Requires admin privileges.
    """
    current_user_id = UUID(user["id"])

    try:
        await service.deactivate_user(user_id=user_id, current_user_id=current_user_id)
    except EntityNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found in organization",
        )


@router.get("/users/me", response_model=UserResponse)
async def get_current_user_profile(
    user: Dict[str, Any] = Depends(get_current_user),
    service: OrganizationService = Depends(get_organization_service),
):
    """Get current user profile."""
    user_id = UUID(user["id"])
    user_response = await service.get_user(user_id)

    if not user_response:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    return user_response


@router.patch("/users/me", response_model=UserResponse)
async def update_current_user_profile(
    update_data: UserUpdateRequest,
    user: Dict[str, Any] = Depends(get_current_user),
    service: OrganizationService = Depends(get_organization_service),
):
    """Update current user profile."""
    user_id = UUID(user["id"])

    try:
        dto = UserUpdateDTO(
            email=update_data.email,
            first_name=update_data.first_name,
            last_name=update_data.last_name,
        )
        return await service.update_user(user_id, dto, current_user_id=user_id)
    except EntityNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    except (ValueError, ValidationError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=safe_error_message(e))


@router.post("/users/me/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    password_data: PasswordChangeRequest,
    user: Dict[str, Any] = Depends(get_current_user),
    service: OrganizationService = Depends(get_organization_service),
    audit_service: AuditService = Depends(get_audit_service),
):
    """Change current user password."""
    user_id = UUID(user["id"])
    organization_id = UUID(user.get("org_id")) if user.get("org_id") else None

    try:
        await service.change_user_password(
            user_id=user_id,
            current_password=password_data.current_password,
            new_password=password_data.new_password,
        )

        # Audit log the password change (WARNING severity - security event)
        await audit_service.log_event(
            actor_id=user_id,
            actor_type=AuditActorType(user.get("role", "user")),
            action=AuditAction.UPDATE,
            resource_type=ResourceType.USER,
            resource_id=user_id,
            resource_name=user.get("email") or user.get("username"),
            organization_id=organization_id,
            severity=AuditSeverity.WARNING,
            category=AuditCategory.SECURITY,
            changes={"password": {"changed": True}},  # Never log actual password
            metadata={"reason": "user_initiated"},
        )
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_message(e),
        )
    except EntityNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_message(e),
        )


@router.patch("/users/{user_id}", response_model=UserResponseModel)
async def update_user_as_admin(
    user_id: UUID,
    update_data: AdminUserUpdateRequest,
    user: Dict[str, Any] = Depends(require_admin),
    service: OrganizationService = Depends(get_organization_service),
    audit_service: AuditService = Depends(get_audit_service),
):
    """
    Update a user (admin only).

    Admins can update username, email, role, first_name, and last_name.
    Business rules:
    - Cannot demote the last admin in an organization (even super_admin cannot do this)
    - Can deactivate the last admin (for billing/suspension purposes)
    - Username and email must be unique across all users
    """
    current_user_id = UUID(user["id"])
    organization_id = UUID(user.get("org_id")) if user.get("org_id") else None

    try:
        # Get the user before update to track changes
        existing_user = await service.get_user(user_id)

        dto = UserUpdateDTO(
            username=update_data.username,
            email=update_data.email,
            first_name=update_data.first_name,
            last_name=update_data.last_name,
            role=update_data.role,
            is_active=update_data.is_active,
        )
        updated_user = await service.update_user_as_admin(user_id, dto, current_user_id)

        # Track what changed for audit log
        changes = {}
        if existing_user:
            if update_data.username and update_data.username != existing_user.username:
                changes["username"] = {"old": existing_user.username, "new": update_data.username}
            if update_data.email and update_data.email != existing_user.email:
                changes["email"] = {"old": existing_user.email, "new": update_data.email}
            if update_data.role and update_data.role != existing_user.role:
                changes["role"] = {"old": existing_user.role, "new": update_data.role}
            if update_data.is_active is not None and update_data.is_active != existing_user.is_active:
                changes["is_active"] = {"old": existing_user.is_active, "new": update_data.is_active}

        # Determine severity based on what changed
        severity = AuditSeverity.INFO
        if "role" in changes or "is_active" in changes:
            severity = AuditSeverity.WARNING

        # Audit log the user update
        await audit_service.log_event(
            actor_id=current_user_id,
            actor_type=AuditActorType(user.get("role", "admin")),
            action=AuditAction.UPDATE,
            resource_type=ResourceType.USER,
            resource_id=user_id,
            resource_name=updated_user.email or updated_user.username,
            organization_id=organization_id,
            severity=severity,
            category=AuditCategory.SECURITY,
            changes=changes if changes else {"updated": True},
        )

        return updated_user
    except EntityNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=safe_error_message(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=safe_error_message(e))


@router.get("/{organization_id}/credentials", response_model=List[Dict[str, Any]])
async def list_organization_credentials(
    organization_id: UUID,
    provider_id: Optional[UUID] = Query(None, description="Filter by provider"),
    credential_type: Optional[str] = Query(
        None, description="Filter by credential type"
    ),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    search: Optional[str] = Query(None, description="Search by name"),
    skip: int = Query(0, ge=0),
    limit: int = Query(settings.API_PAGE_LIMIT_DEFAULT, ge=1, le=settings.API_PAGE_MAX),
    verified_org_id: UUID = Depends(verify_org_access_strict),
    provider_service: ProviderService = Depends(get_provider_service),
):
    """
    List all credentials for an organization (Secrets Vault).

    Multi-tenant security:
    - Users can only list credentials for their own organization
    - Even super_admin cannot view other org's credentials (security boundary)
    - All users see masked secrets (no actual secret values)
    """
    try:
        # Call application service (which handles credential_type conversion)
        credentials = await provider_service.list_credentials_by_organization(
            organization_id=organization_id,
            skip=skip,
            limit=limit,
            provider_id=provider_id,
            credential_type=credential_type,
            is_active=is_active,
            search=search,
        )

        # Application service returns DTOs with masked secrets
        return [c.model_dump() for c in credentials]

    except Exception:
        logger.exception("Failed to fetch credentials for organization %s", organization_id)  # nosemgrep: python-logger-credential-disclosure
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch credentials",
        )


# =============================================================================
# Super Admin Organization Management
# =============================================================================


@router.post("/{organization_id}/activate", response_model=OrganizationResponse)
async def activate_organization_legacy(
    organization_id: UUID = Path(...),
    user: Dict[str, Any] = Depends(require_super_admin),
    organization_repo: OrganizationRepository = Depends(get_organization_repository),
    service: OrganizationService = Depends(get_organization_service),
):
    """
    Activate an organization (legacy).

    Requires SUPER_ADMIN privileges.
    This allows the organization's users to create/update resources.
    """
    try:
        organization = await organization_repo.get_by_id(organization_id)
        if not organization:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Organization not found",
            )

        organization.activate()
        organization = await organization_repo.update(organization)

        # Convert to response format
        return await service.get_organization(organization_id)

    except InvalidStateTransition as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_message(e),
        )
    except EntityNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found",
        )


@router.post("/{organization_id}/deactivate", response_model=OrganizationResponse)
async def deactivate_organization(
    organization_id: UUID = Path(...),
    user: Dict[str, Any] = Depends(require_super_admin),
    organization_repo: OrganizationRepository = Depends(get_organization_repository),
    service: OrganizationService = Depends(get_organization_service),
):
    """
    Deactivate an organization.

    Requires SUPER_ADMIN privileges.
    This prevents the organization's users from creating/updating resources.
    """
    try:
        organization = await organization_repo.get_by_id(organization_id)
        if not organization:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Organization not found",
            )

        organization.deactivate()
        organization = await organization_repo.update(organization)

        # Convert to response format
        return await service.get_organization(organization_id)

    except InvalidStateTransition as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_message(e),
        )
    except EntityNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found",
        )


# =============================================================================
# Super Admin: Organization Admin Management
# =============================================================================


class OrgAdminResponse(BaseModel):
    """Minimal admin user info for super admin view."""

    id: UUID
    username: str
    email: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    role: str
    is_active: bool
    created_at: Optional[datetime] = None


@router.get("/{organization_id}/admins", response_model=List[OrgAdminResponse])
async def get_organization_admins(
    organization_id: UUID = Path(...),
    user: Dict[str, Any] = Depends(require_super_admin),
    org_repo: OrganizationRepository = Depends(get_organization_repository),
    user_repo: UserRepository = Depends(get_user_repository_bypass),
):
    """
    List admin users for an organization.

    Requires SUPER_ADMIN privileges.
    Returns only users with 'admin' role (not regular users).
    Used for support/escalation to identify org contacts.
    """
    # Verify org exists
    org = await org_repo.get_by_id(organization_id)
    if not org:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found",
        )

    # Get all users for this org (using bypass to access cross-org)
    users = await user_repo.list(
        skip=0,
        limit=100,
        organization_id=organization_id,
    )

    # Filter to admins only
    admins = [u for u in users if u.role.value == "admin"]

    return [
        OrgAdminResponse(
            id=u.id,
            username=u.username,
            email=u.email.email,
            first_name=u.first_name,
            last_name=u.last_name,
            role=u.role.value,
            is_active=u.is_active,
            created_at=u.created_at,
        )
        for u in admins
    ]


class AdminStatusUpdateRequest(BaseModel):
    """Request to update admin user status."""

    is_active: bool


@router.patch("/{organization_id}/admins/{admin_id}/status")
async def update_organization_admin_status(
    organization_id: UUID = Path(...),
    admin_id: UUID = Path(...),
    request: AdminStatusUpdateRequest = Body(...),
    user: Dict[str, Any] = Depends(require_super_admin),
    org_repo: OrganizationRepository = Depends(get_organization_repository),
    user_repo: UserRepository = Depends(get_user_repository_bypass),
):
    """
    Activate or deactivate an organization admin.

    Requires SUPER_ADMIN privileges.
    Used for security incidents where an admin account needs to be disabled.
    """
    # Verify org exists
    org = await org_repo.get_by_id(organization_id)
    if not org:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found",
        )

    # Get the admin user
    admin_user = await user_repo.get_by_id(admin_id)
    if not admin_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # Verify user belongs to the specified org
    if admin_user.organization_id != organization_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found in this organization",
        )

    # Verify user is an admin (not regular user)
    if admin_user.role.value not in ("admin", "super_admin"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is not an admin",
        )

    # Update status
    if request.is_active:
        admin_user.activate()
    else:
        admin_user.deactivate()

    await user_repo.update(admin_user)

    return {
        "id": admin_user.id,
        "username": admin_user.username,
        "is_active": admin_user.is_active,
        "message": f"Admin {'activated' if request.is_active else 'deactivated'} successfully",
    }


# =============================================================================
# Organization Status Management (Super Admin Only)
# =============================================================================


class OrganizationActivateRequest(BaseModel):
    """Request to activate an organization."""

    pass  # Activation method is always MANUAL for this endpoint


class OrganizationSuspendRequest(BaseModel):
    """Request to suspend an organization."""

    reason: Optional[str] = None


class OrganizationStatusResponse(BaseModel):
    """Response for organization status operations."""

    id: UUID
    name: str
    status: str
    is_active: bool
    activated_at: Optional[datetime] = None
    message: str


@router.post(
    "/{organization_id}/activate",
    response_model=OrganizationStatusResponse,
)
async def activate_organization(
    organization_id: UUID = Path(...),
    user: Dict[str, Any] = Depends(require_super_admin),
    org_repo: OrganizationRepository = Depends(get_organization_repository),
):
    """
    Activate a pending or suspended organization.

    Changes organization status to 'active', enabling full access.

    Requires SUPER_ADMIN privileges.
    """
    org = await org_repo.get_by_id(organization_id)
    if not org:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found",
        )

    try:
        from app.domain.common.value_objects import ActivationMethod

        org.activate(
            activated_by=UUID(user["id"]),
            method=ActivationMethod.MANUAL,
        )
        await org_repo.update(org)

        return OrganizationStatusResponse(
            id=org.id,
            name=org.name,
            status=org.status.value,
            is_active=org.is_active,
            activated_at=org.activated_at,
            message=f"Organization '{org.name}' has been activated",
        )
    except InvalidStateTransition as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_message(e),
        )


@router.post(
    "/{organization_id}/suspend",
    response_model=OrganizationStatusResponse,
)
async def suspend_organization(
    organization_id: UUID = Path(...),
    request: Optional[OrganizationSuspendRequest] = Body(default=None),
    user: Dict[str, Any] = Depends(require_super_admin),
    org_repo: OrganizationRepository = Depends(get_organization_repository),
):
    """
    Suspend an organization.

    Changes organization status to 'suspended', making it read-only.

    Requires SUPER_ADMIN privileges.
    """
    org = await org_repo.get_by_id(organization_id)
    if not org:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found",
        )

    # Prevent suspending the system organization
    is_system = org.settings.get("is_system", False) if org.settings else False
    if is_system:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot suspend the system organization",
        )

    try:
        reason = request.reason if request else None
        org.suspend(reason=reason)
        await org_repo.update(org)

        return OrganizationStatusResponse(
            id=org.id,
            name=org.name,
            status=org.status.value,
            is_active=org.is_active,
            activated_at=org.activated_at,
            message=f"Organization '{org.name}' has been suspended",
        )
    except InvalidStateTransition as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_message(e),
        )


@router.post(
    "/{organization_id}/set-pending",
    response_model=OrganizationStatusResponse,
)
async def set_organization_pending(
    organization_id: UUID = Path(...),
    user: Dict[str, Any] = Depends(require_super_admin),
    org_repo: OrganizationRepository = Depends(get_organization_repository),
):
    """
    Set an organization to pending approval status.

    Changes organization status to 'pending_approval', allowing limited access
    (can build but not execute workflows).

    Requires SUPER_ADMIN privileges.
    """
    org = await org_repo.get_by_id(organization_id)
    if not org:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found",
        )

    # Prevent changing the system organization
    is_system = org.settings.get("is_system", False) if org.settings else False
    if is_system:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot change status of the system organization",
        )

    try:
        org.set_pending_approval()
        await org_repo.update(org)

        return OrganizationStatusResponse(
            id=org.id,
            name=org.name,
            status=org.status.value,
            is_active=org.is_active,
            activated_at=org.activated_at,
            message=f"Organization '{org.name}' is now pending approval",
        )
    except InvalidStateTransition as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_message(e),
        )
