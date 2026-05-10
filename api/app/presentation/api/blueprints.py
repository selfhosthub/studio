# api/app/presentation/api/blueprints.py

"""Blueprint management API endpoints."""
from typing import List, Optional
from uuid import UUID

from app.config.settings import settings
from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from app.application.dtos.blueprint_dto import (
    BlueprintCreate,
    BlueprintResponse,
    BlueprintUpdate,
)
from app.application.interfaces import EntityNotFoundError
from app.application.services.blueprint_service import BlueprintService
from sqlalchemy.ext.asyncio import AsyncSession

from app.presentation.api.dependencies import (
    CurrentUser,
    get_audit_service,
    get_current_user,
    get_db_session,
    get_effective_org_id,
    get_blueprint_service,
    require_admin,
    validate_organization_access,
)
from app.application.services.audit_service import AuditService
from app.domain.audit.models import AuditAction, AuditActorType, AuditSeverity, AuditCategory, ResourceType
from app.domain.provider.models import PackageType
from app.infrastructure.services.package_version_service import PackageVersionService
from app.infrastructure.errors import safe_error_message

router = APIRouter()


@router.post("/", response_model=BlueprintResponse, status_code=status.HTTP_201_CREATED)
async def create_blueprint(
    blueprint: BlueprintCreate,
    user: CurrentUser = Depends(get_current_user),
    service: BlueprintService = Depends(get_blueprint_service),
    audit_service: AuditService = Depends(get_audit_service),
):
    effective_org_id = get_effective_org_id(
        str(blueprint.organization_id) if blueprint.organization_id else None, user
    )

    blueprint.organization_id = UUID(effective_org_id)
    blueprint.created_by = UUID(user["id"])

    try:
        created = await service.create_blueprint(blueprint)

        await audit_service.log_event(
            actor_id=UUID(user["id"]),
            actor_type=AuditActorType(user.get("role") or "user"),
            action=AuditAction.CREATE,
            resource_type=ResourceType.BLUEPRINT,
            resource_id=created.id,
            resource_name=created.name,
            organization_id=UUID(effective_org_id),
            severity=AuditSeverity.INFO,
            category=AuditCategory.CONFIGURATION,
            metadata={
                "category": created.category,
            },
        )

        return created
    except EntityNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=safe_error_message(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=safe_error_message(e))


@router.get("/", response_model=List[BlueprintResponse])
async def list_blueprints(
    organization_id: Optional[UUID] = Query(
        None,
        description="Organization ID to filter by (optional, derived from user token if not provided)",
    ),
    category: Optional[str] = Query(None, description="Filter by category"),
    status_filter: Optional[str] = Query(
        None, alias="status", description="Filter by status"
    ),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(settings.API_PAGE_LIMIT_DEFAULT, ge=1, le=settings.API_PAGE_MAX, description="Maximum records to return"),
    user: CurrentUser = Depends(get_current_user),
    service: BlueprintService = Depends(get_blueprint_service),
):
    effective_org_id = get_effective_org_id(
        str(organization_id) if organization_id else None, user
    )

    return await service.list_blueprints(
        organization_id=UUID(effective_org_id),
        category=category,
        status=status_filter,
        skip=skip,
        limit=limit,
    )


@router.get("/{blueprint_id}", response_model=BlueprintResponse)
async def get_blueprint(
    blueprint_id: UUID = Path(..., description="Blueprint unique identifier"),
    user: CurrentUser = Depends(get_current_user),
    service: BlueprintService = Depends(get_blueprint_service),
):
    """User must belong to the blueprint's org, or be super_admin."""
    blueprint = await service.get_blueprint(blueprint_id)
    if not blueprint:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Blueprint with ID {blueprint_id} not found",
        )

    await validate_organization_access(str(blueprint.organization_id), user)

    return blueprint


@router.put("/{blueprint_id}", response_model=BlueprintResponse)
async def update_blueprint(
    blueprint_update: BlueprintUpdate,
    blueprint_id: UUID = Path(..., description="Blueprint unique identifier"),
    user: CurrentUser = Depends(get_current_user),
    service: BlueprintService = Depends(get_blueprint_service),
    audit_service: AuditService = Depends(get_audit_service),
):
    """User must belong to the blueprint's org, or be super_admin."""
    blueprint = await service.get_blueprint(blueprint_id)
    if not blueprint:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Blueprint with ID {blueprint_id} not found",
        )

    await validate_organization_access(str(blueprint.organization_id), user)

    try:
        updated = await service.update_blueprint(blueprint_id, blueprint_update)

        changes = {}
        if blueprint_update.name and blueprint_update.name != blueprint.name:
            changes["name"] = {"old": blueprint.name, "new": blueprint_update.name}
        if blueprint_update.description is not None and blueprint_update.description != blueprint.description:
            changes["description"] = {"old": blueprint.description, "new": blueprint_update.description}
        if blueprint_update.steps is not None:
            changes["steps"] = {"changed": True}

        await audit_service.log_event(
            actor_id=UUID(user["id"]),
            actor_type=AuditActorType(user.get("role") or "user"),
            action=AuditAction.UPDATE,
            resource_type=ResourceType.BLUEPRINT,
            resource_id=blueprint_id,
            resource_name=updated.name,
            organization_id=blueprint.organization_id,
            severity=AuditSeverity.INFO,
            category=AuditCategory.CONFIGURATION,
            changes=changes if changes else {"updated": True},
        )

        return updated
    except EntityNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=safe_error_message(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=safe_error_message(e))


@router.post("/{blueprint_id}/archive", response_model=BlueprintResponse)
async def archive_blueprint(
    blueprint_id: UUID = Path(..., description="Blueprint unique identifier"),
    user: CurrentUser = Depends(get_current_user),
    service: BlueprintService = Depends(get_blueprint_service),
    audit_service: AuditService = Depends(get_audit_service),
):
    """Archive removes from active use while preserving for audit. User must belong to org or be super_admin."""
    blueprint = await service.get_blueprint(blueprint_id)
    if not blueprint:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Blueprint with ID {blueprint_id} not found",
        )

    await validate_organization_access(str(blueprint.organization_id), user)

    try:
        archived = await service.archive_blueprint(blueprint_id, archived_by=UUID(user["id"]))

        await audit_service.log_event(
            actor_id=UUID(user["id"]),
            actor_type=AuditActorType(user.get("role") or "user"),
            action=AuditAction.DEACTIVATE,
            resource_type=ResourceType.BLUEPRINT,
            resource_id=blueprint_id,
            resource_name=blueprint.name,
            organization_id=blueprint.organization_id,
            severity=AuditSeverity.WARNING,
            category=AuditCategory.CONFIGURATION,
            changes={"status": {"old": blueprint.status, "new": "inactive"}},
        )

        return archived
    except EntityNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=safe_error_message(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=safe_error_message(e))


@router.delete("/{blueprint_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_blueprint(
    blueprint_id: UUID = Path(..., description="Blueprint ID"),
    user: CurrentUser = Depends(require_admin),
    service: BlueprintService = Depends(get_blueprint_service),
    audit_service: AuditService = Depends(get_audit_service),
    db: AsyncSession = Depends(get_db_session),
):
    """Admin/super_admin only. Blueprint must be archived first; super_admin force-deletes for marketplace uninstall.

    409 if not inactive/archived. 403 outside org (super_admin bypasses).
    """
    from app.domain.common.exceptions import BusinessRuleViolation

    blueprint = await service.get_blueprint(blueprint_id)
    if not blueprint:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Blueprint with ID {blueprint_id} not found",
        )

    await validate_organization_access(str(blueprint.organization_id), user)

    # Capture before deletion for audit
    blueprint_name = blueprint.name
    organization_id = blueprint.organization_id

    try:
        force = user.get("role") == "super_admin"
        await service.delete_blueprint(blueprint_id, force=force)

        marketplace_id = (blueprint.client_metadata or {}).get("marketplace_id")
        if marketplace_id:
            await PackageVersionService.soft_delete(db, PackageType.BLUEPRINT, marketplace_id)

        await audit_service.log_event(
            actor_id=UUID(user["id"]),
            actor_type=AuditActorType(user.get("role") or "admin"),
            action=AuditAction.DELETE,
            resource_type=ResourceType.BLUEPRINT,
            resource_id=blueprint_id,
            resource_name=blueprint_name,
            organization_id=organization_id,
            severity=AuditSeverity.WARNING,
            category=AuditCategory.CONFIGURATION,
        )
    except EntityNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=safe_error_message(e))
    except BusinessRuleViolation as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=safe_error_message(e))
