# api/app/presentation/api/prompts.py

"""Prompt management API endpoints."""

import json
import logging
from typing import List, Optional
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Path,
    Query,
    UploadFile,
    status,
)
from pydantic import BaseModel

from app.application.dtos.prompt_dto import (
    AssembleRequestDTO,
    PromptCreateDTO,
    PromptResponseDTO,
    PromptUpdateDTO,
)
from app.application.services.audit_service import AuditService
from app.application.services.prompt_service import PromptService
from app.config.settings import settings
from app.domain.audit.models import (
    AuditAction,
    AuditActorType,
    AuditCategory,
    ResourceType,
)
from app.domain.common.exceptions import BusinessRuleViolation, EntityNotFoundError, PermissionDeniedError
from app.domain.common.value_objects import PromptScope, Role, Visibility
from app.domain.prompt.models import PromptSource
from app.presentation.api.dependencies import (
    CurrentUser,
    get_audit_service,
    get_current_user,
    get_prompt_service,
    require_admin,
    require_super_admin,
    require_user,
)
from app.infrastructure.errors import safe_error_message

router = APIRouter()
logger = logging.getLogger(__name__)


class PromptImportResponse(BaseModel):
    """Result of importing a prompt from a JSON file."""

    prompt: PromptResponseDTO
    warnings: List[str] = []


def _default_scope_for(user: CurrentUser) -> PromptScope:
    """Per-role default scope: super_admin authors org-level content directly;
    everyone else (admin, user) creates personal content needing publish approval.
    Mirrors the workflow import/create rule."""
    return (
        PromptScope.ORGANIZATION
        if user.get("role") == Role.SUPER_ADMIN.value
        else PromptScope.PERSONAL
    )


@router.get("/personal", response_model=List[PromptResponseDTO])
async def list_personal_prompts(
    skip: int = Query(0, ge=0),
    limit: int = Query(settings.API_PAGE_LIMIT_DEFAULT, ge=1, le=settings.API_PAGE_MAX),
    user: CurrentUser = Depends(get_current_user),
    service: PromptService = Depends(get_prompt_service),
):
    """List prompts the current user created personally (scope=personal)."""
    org_id = user["org_id"]
    prompts = await service.repository.list_personal_prompts(
        organization_id=UUID(org_id),
        created_by=UUID(user["id"]),
        skip=skip,
        limit=limit,
    )
    return [service._to_response(p) for p in prompts]


@router.get("/pending-publish", response_model=List[PromptResponseDTO])
async def list_pending_publish(
    skip: int = Query(0, ge=0),
    limit: int = Query(settings.API_PAGE_LIMIT_DEFAULT, ge=1, le=settings.API_PAGE_MAX),
    user: CurrentUser = Depends(require_admin),
    service: PromptService = Depends(get_prompt_service),
):
    """List prompts pending publish approval (admin only)."""
    org_id = user["org_id"]
    prompts = await service.repository.list_pending_publish(
        organization_id=UUID(org_id),
        skip=skip,
        limit=limit,
    )
    return [service._to_response(p) for p in prompts]


@router.get("/", response_model=List[PromptResponseDTO])
async def list_prompts(
    category: Optional[str] = Query(None, description="Filter by category"),
    scope: Optional[str] = Query(
        None,
        description="Filter by scope: 'organization' lists only org-scoped "
        "prompts. Omit to list all scopes (backward compatible).",
    ),
    user: CurrentUser = Depends(get_current_user),
    service: PromptService = Depends(get_prompt_service),
):
    """List prompts for the organization, optionally filtered by scope."""
    org_id = user["org_id"]
    scope_filter = PromptScope(scope) if scope else None
    return await service.list_prompts(
        organization_id=UUID(org_id),
        category=category,
        scope=scope_filter,
    )


@router.get("/{prompt_id}", response_model=PromptResponseDTO)
async def get_prompt(
    prompt_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    service: PromptService = Depends(get_prompt_service),
):
    org_id = user["org_id"]
    try:
        return await service.get_prompt(
            prompt_id=prompt_id,
            organization_id=UUID(org_id),
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=safe_error_message(e))


@router.post(
    "/",
    response_model=PromptResponseDTO,
    status_code=status.HTTP_201_CREATED,
)
async def create_prompt(
    dto: PromptCreateDTO,
    user: CurrentUser = Depends(get_current_user),
    service: PromptService = Depends(get_prompt_service),
):
    """Create a new prompt."""
    org_id = user["org_id"]
    source = PromptSource.SUPER_ADMIN if user.get("role") == "super_admin" else PromptSource.CUSTOM
    # Role→scope rule (mirrors workflows): super_admin authors org-level content
    # directly; everyone else creates personal content needing publish approval.
    # An explicit dto.scope (e.g. a future "publish on create") overrides.
    scope = (
        PromptScope(dto.scope)
        if dto.scope
        else _default_scope_for(user)
    )
    return await service.create_prompt(
        dto=dto,
        organization_id=UUID(org_id),
        org_slug=str(user.get("org_slug") or "org"),
        source=source,
        created_by=UUID(user["id"]),
        scope=scope,
    )


@router.post(
    "/import",
    response_model=PromptImportResponse,
    status_code=status.HTTP_201_CREATED,
)
async def import_prompt(
    file: UploadFile = File(..., description="Prompt JSON file to import"),
    user: CurrentUser = Depends(require_user),
    service: PromptService = Depends(get_prompt_service),
):
    """Import a prompt from an exported JSON file.

    Gated to any org member (require_user). Role→scope rule mirrors workflows:
    super_admin imports at organization scope; everyone else imports a personal,
    unpublished prompt that needs the publish-approval flow to reach org scope.
    Sets created_by to the uploader so ownership-based publish requests work.
    """
    if not file.filename or not file.filename.endswith(".json"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be a .json file",
        )

    try:
        content = await file.read()
        data = json.loads(content.decode("utf-8"))
    except json.JSONDecodeError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Uploaded file is not valid JSON (line {e.lineno}, column {e.colno}).",
        )
    except Exception:
        logger.exception("Failed to read uploaded prompt file")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to read file",
        )

    org_id = user["org_id"]
    try:
        prompt, warnings = await service.import_prompt(
            data=data,
            organization_id=UUID(org_id),
            org_slug=str(user.get("org_slug") or "org"),
            created_by=UUID(user["id"]),
            scope=_default_scope_for(user),
        )
    except BusinessRuleViolation as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=safe_error_message(e)
        )

    return PromptImportResponse(prompt=prompt, warnings=warnings)


@router.put("/{prompt_id}", response_model=PromptResponseDTO)
async def update_prompt(
    prompt_id: UUID,
    dto: PromptUpdateDTO,
    user: CurrentUser = Depends(get_current_user),
    service: PromptService = Depends(get_prompt_service),
):
    """Update a prompt."""
    org_id = user["org_id"]
    try:
        return await service.update_prompt(
            prompt_id=prompt_id,
            dto=dto,
            organization_id=UUID(org_id),
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=safe_error_message(e))


@router.delete("/{prompt_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_prompt(
    prompt_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    service: PromptService = Depends(get_prompt_service),
):
    """Delete a prompt."""
    org_id = user["org_id"]
    try:
        await service.delete_prompt(
            prompt_id=prompt_id,
            organization_id=UUID(org_id),
            actor_id=UUID(user["id"]),
        )
    except BusinessRuleViolation as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=safe_error_message(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=safe_error_message(e))


@router.post(
    "/{prompt_id}/copy",
    response_model=PromptResponseDTO,
    status_code=status.HTTP_201_CREATED,
)
async def copy_prompt(
    prompt_id: UUID = Path(...),
    user: CurrentUser = Depends(get_current_user),
    service: PromptService = Depends(get_prompt_service),
):
    """Copy a prompt into the caller's personal scope."""
    org_id = user["org_id"]
    try:
        return await service.copy_prompt(
            prompt_id=prompt_id,
            organization_id=UUID(org_id),
            org_slug=str(user.get("org_slug") or "org"),
            created_by=UUID(user["id"]),
        )
    except EntityNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=safe_error_message(e))


@router.post("/{prompt_id}/request-publish", response_model=PromptResponseDTO)
async def request_publish(
    prompt_id: UUID = Path(...),
    user: CurrentUser = Depends(get_current_user),
    service: PromptService = Depends(get_prompt_service),
):
    """Request publishing a personal prompt to the organization."""
    try:
        return await service.request_publish(prompt_id, UUID(user["id"]))
    except EntityNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=safe_error_message(e))
    except PermissionDeniedError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=safe_error_message(e))
    except BusinessRuleViolation as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=safe_error_message(e))


@router.post("/{prompt_id}/approve-publish", response_model=PromptResponseDTO)
async def approve_publish(
    prompt_id: UUID = Path(...),
    user: CurrentUser = Depends(require_admin),
    service: PromptService = Depends(get_prompt_service),
):
    """Admin approves a pending publish request."""
    try:
        return await service.approve_publish(prompt_id)
    except EntityNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=safe_error_message(e))
    except BusinessRuleViolation as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=safe_error_message(e))


@router.post("/{prompt_id}/reject-publish", response_model=PromptResponseDTO)
async def reject_publish(
    prompt_id: UUID = Path(...),
    user: CurrentUser = Depends(require_admin),
    service: PromptService = Depends(get_prompt_service),
):
    """Admin rejects a pending publish request."""
    try:
        return await service.reject_publish(prompt_id)
    except EntityNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=safe_error_message(e))
    except BusinessRuleViolation as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=safe_error_message(e))


class PromptVisibilityUpdate(BaseModel):
    visibility: Visibility


@router.post("/{prompt_id}/visibility", response_model=PromptResponseDTO)
async def set_prompt_visibility(
    payload: PromptVisibilityUpdate,
    prompt_id: UUID = Path(...),
    user: CurrentUser = Depends(require_super_admin),
    service: PromptService = Depends(get_prompt_service),
    audit_service: AuditService = Depends(get_audit_service),
):
    """super_admin-only: set a prompt's cross-org marketplace visibility
    (private | staging | public). The transition is audit-logged with old/new."""
    try:
        old_visibility, updated = await service.set_visibility(
            prompt_id, payload.visibility
        )
    except EntityNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Prompt {prompt_id} not found",
        )

    await audit_service.log_event(
        actor_id=UUID(str(user.get("id"))),
        actor_type=AuditActorType(user.get("role") or "user"),
        action=AuditAction.UPDATE,
        resource_type=ResourceType.PACKAGE,  # prompts are catalog packages; no PROMPT enum value
        resource_id=prompt_id,
        resource_name=updated.name,
        organization_id=updated.organization_id,
        category=AuditCategory.CONFIGURATION,
        changes={
            "visibility": {
                "old": old_visibility.value,
                "new": payload.visibility.value,
            }
        },
    )
    return updated


@router.post("/{prompt_id}/assemble")
async def assemble_prompt(
    prompt_id: UUID,
    dto: AssembleRequestDTO,
    user: CurrentUser = Depends(get_current_user),
    service: PromptService = Depends(get_prompt_service),
):
    """Assemble a prompt with variable values. For live preview."""
    org_id = user["org_id"]
    try:
        result = await service.assemble_prompt(
            prompt_id=prompt_id,
            variable_values=dto.variable_values,
            organization_id=UUID(org_id),
        )
        return {"messages": result}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=safe_error_message(e))
