# api/app/presentation/api/prompts.py

"""Prompt management API endpoints."""

from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from app.application.dtos.prompt_dto import (
    AssembleRequestDTO,
    PromptCreateDTO,
    PromptResponseDTO,
    PromptUpdateDTO,
)
from app.application.services.prompt_service import PromptService
from app.config.settings import settings
from app.domain.common.exceptions import BusinessRuleViolation, EntityNotFoundError, PermissionDeniedError
from app.domain.prompt.models import PromptSource
from app.presentation.api.dependencies import (
    CurrentUser,
    get_current_user,
    get_effective_org_id,
    get_prompt_service,
    require_admin,
)
from app.infrastructure.errors import safe_error_message

router = APIRouter()


@router.get("/personal", response_model=List[PromptResponseDTO])
async def list_personal_prompts(
    skip: int = Query(0, ge=0),
    limit: int = Query(settings.API_PAGE_LIMIT_DEFAULT, ge=1, le=settings.API_PAGE_MAX),
    user: CurrentUser = Depends(get_current_user),
    service: PromptService = Depends(get_prompt_service),
):
    """List prompts the current user created personally (scope=personal)."""
    org_id = get_effective_org_id(None, user)
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
    org_id = get_effective_org_id(None, user)
    prompts = await service.repository.list_pending_publish(
        organization_id=UUID(org_id),
        skip=skip,
        limit=limit,
    )
    return [service._to_response(p) for p in prompts]


@router.get("/", response_model=List[PromptResponseDTO])
async def list_prompts(
    category: Optional[str] = Query(None, description="Filter by category"),
    user: CurrentUser = Depends(get_current_user),
    service: PromptService = Depends(get_prompt_service),
):
    """List organization-scoped prompts."""
    org_id = get_effective_org_id(None, user)
    return await service.list_prompts(
        organization_id=UUID(org_id),
        category=category,
    )


@router.get("/{prompt_id}", response_model=PromptResponseDTO)
async def get_prompt(
    prompt_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    service: PromptService = Depends(get_prompt_service),
):
    org_id = get_effective_org_id(None, user)
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
    org_id = get_effective_org_id(None, user)
    source = PromptSource.SUPER_ADMIN if user.get("role") == "super_admin" else PromptSource.CUSTOM
    return await service.create_prompt(
        dto=dto,
        organization_id=UUID(org_id),
        source=source,
    )


@router.put("/{prompt_id}", response_model=PromptResponseDTO)
async def update_prompt(
    prompt_id: UUID,
    dto: PromptUpdateDTO,
    user: CurrentUser = Depends(get_current_user),
    service: PromptService = Depends(get_prompt_service),
):
    """Update a prompt."""
    org_id = get_effective_org_id(None, user)
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
    org_id = get_effective_org_id(None, user)
    try:
        await service.delete_prompt(
            prompt_id=prompt_id,
            organization_id=UUID(org_id),
        )
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
    org_id = get_effective_org_id(None, user)
    try:
        return await service.copy_prompt(
            prompt_id=prompt_id,
            organization_id=UUID(org_id),
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


@router.post("/{prompt_id}/assemble")
async def assemble_prompt(
    prompt_id: UUID,
    dto: AssembleRequestDTO,
    user: CurrentUser = Depends(get_current_user),
    service: PromptService = Depends(get_prompt_service),
):
    """Assemble a prompt with variable values. For live preview."""
    org_id = get_effective_org_id(None, user)
    try:
        result = await service.assemble_prompt(
            prompt_id=prompt_id,
            variable_values=dto.variable_values,
            organization_id=UUID(org_id),
        )
        return {"messages": result}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=safe_error_message(e))
