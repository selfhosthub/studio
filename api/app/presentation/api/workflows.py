# api/app/presentation/api/workflows.py

"""Workflow management API endpoints."""

import logging
import json
from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from app.config.settings import settings
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
from fastapi.responses import Response
from pydantic import BaseModel

from app.application.dtos.workflow_dto import (
    WorkflowCreate,
    WorkflowFormSchemaResponse,
    WorkflowResponse,
    WorkflowUpdate,
)
from app.application.interfaces.exceptions import DuplicateEntityError
from app.domain.common.exceptions import BusinessRuleViolation, EntityNotFoundError
from app.application.services.form_field_resolver import FormFieldResolver
from app.application.services.workflow_credential_service import (
    CredentialCheckResult as CredentialCheckResponse,
    WorkflowCredentialService,
)
from app.application.services.audit_service import AuditService
from app.application.services.workflow_service import (
    TRIGGER_SECRET_TYPES,
    WorkflowService,
)
from app.domain.audit.models import (
    AuditAction,
    AuditActorType,
    AuditCategory,
    ResourceType,
)
from app.domain.common.value_objects import Role, Visibility
from app.domain.workflow.models import WorkflowScope
from app.infrastructure.messaging.pg_notify import notify_global
from app.domain.prompt.repository import PromptRepository
from app.domain.provider.repository import (
    ProviderCredentialRepository,
    ProviderRepository,
    ProviderServiceRepository,
)
from app.presentation.api.dependencies import (
    CurrentUser,
    get_current_user,
    get_prompt_repository,
    get_provider_credential_repository,
    get_provider_repository,
    get_audit_service,
    get_provider_service_repository,
    get_workflow_service,
    require_admin,
    require_super_admin,
    require_user,
    validate_organization_access,
)
from app.infrastructure.errors import safe_error_message

logger = logging.getLogger(__name__)

router = APIRouter()

# Catalog-visibility values that mean a workflow is (or was) in some org's
# marketplace listing - a transition touching these changes other orgs' catalog.
_CATALOG_VISIBLE = {Visibility.STAGING.value, Visibility.PUBLIC.value}


async def _broadcast_catalog_changed() -> None:
    """Push a global 'catalog changed' signal so active clients can refetch the
    marketplace (no server cache to bust - reads are always live; this is the
    live-refresh nudge). Best-effort: a delivery failure must not fail the
    request that triggered it."""
    try:
        await notify_global(
            {
                "event_type": "catalog_changed",
                "data": {"type": "workflow"},
            }
        )
    except Exception:
        logger.exception("Failed to broadcast catalog_changed")


@router.post("/", response_model=WorkflowResponse, status_code=status.HTTP_201_CREATED)
async def create_workflow(
    workflow: WorkflowCreate,
    user: CurrentUser = Depends(get_current_user),
    service: WorkflowService = Depends(get_workflow_service),
):
    """
    Create a new workflow.

    The workflow is always created in the caller's own organization (resolved
    from the DB); any client-supplied organization_id in the body is ignored.
    """
    # Org is the caller's own (DB-sourced).
    effective_org_id = user["org_id"]

    # Update workflow with the effective organization_id and creator
    workflow.organization_id = UUID(effective_org_id)
    workflow.created_by = UUID(user["id"])

    try:
        return await service.create_workflow(workflow)
    except DuplicateEntityError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=safe_error_message(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=safe_error_message(e))


@router.get("/", response_model=List[WorkflowResponse])
async def list_workflows(
    scope: Optional[str] = Query(
        None,
        description="Filter by scope: 'personal' or 'organization'",
    ),
    skip: int = Query(0, ge=0),
    limit: int = Query(settings.API_PAGE_LIMIT_DEFAULT, ge=1, le=settings.API_PAGE_MAX),
    user: CurrentUser = Depends(get_current_user),
    service: WorkflowService = Depends(get_workflow_service),
):
    """
    List workflows for an organization with pagination.

    Use scope=personal to list only the current user's personal workflows.
    Use scope=organization to list only organization-level workflows.
    Omit scope to list all workflows (backward compatible).
    """
    # Always the caller's own org (DB-sourced).
    org_uuid = UUID(user["org_id"])

    if scope == "personal":
        workflows = await service.workflow_repository.list_personal_workflows(
            org_uuid, UUID(user["id"]), skip=skip, limit=limit
        )
    elif scope == "organization":
        workflows = await service.workflow_repository.list_organization_workflows(
            org_uuid, skip=skip, limit=limit
        )
    else:
        workflows = await service.workflow_repository.list_by_organization(
            org_uuid, skip=skip, limit=limit
        )
    return await service.to_responses(workflows)


@router.get("/by-blueprint/{blueprint_id}", response_model=List[WorkflowResponse])
async def list_workflows_by_blueprint(
    blueprint_id: UUID = Path(...),
    skip: int = Query(0, ge=0),
    limit: int = Query(settings.API_PAGE_LIMIT_DEFAULT, ge=1, le=settings.API_PAGE_MAX),
    user: CurrentUser = Depends(get_current_user),
    service: WorkflowService = Depends(get_workflow_service),
):
    """
    List workflows derived from a blueprint with pagination.

    Users can only list workflows for blueprints they have access to.
    Super-admins can access all workflows.
    """
    workflows = await service.workflow_repository.list_by_blueprint(
        blueprint_id, skip=skip, limit=limit
    )

    if workflows and len(workflows) > 0:
        first_workflow = workflows[0]
        await validate_organization_access(str(first_workflow.organization_id), user)

    return await service.to_responses(workflows)


@router.get("/pending-publish", response_model=List[WorkflowResponse])
async def list_pending_publish(
    skip: int = Query(0, ge=0),
    limit: int = Query(settings.API_PAGE_LIMIT_DEFAULT, ge=1, le=settings.API_PAGE_MAX),
    user: CurrentUser = Depends(require_admin),
    service: WorkflowService = Depends(get_workflow_service),
):
    """List workflows pending publish approval (admin only)."""
    # Always the caller's own org (DB-sourced).
    workflows = await service.workflow_repository.list_pending_publish(
        UUID(user["org_id"]), skip=skip, limit=limit
    )
    return await service.to_responses(workflows)


@router.post("/{workflow_id}/copy", response_model=WorkflowResponse)
async def copy_workflow(
    workflow_id: UUID = Path(...),
    user: CurrentUser = Depends(get_current_user),
    service: WorkflowService = Depends(get_workflow_service),
):
    """Copy a workflow to the current user's personal scope."""
    effective_org_id = user["org_id"]
    try:
        return await service.copy_workflow(
            workflow_id=workflow_id,
            user_id=UUID(user["id"]),
            organization_id=UUID(effective_org_id),
            target_scope="personal",
        )
    except EntityNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow {workflow_id} not found",
        )
    except DuplicateEntityError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=safe_error_message(e))


@router.post("/{workflow_id}/request-publish", response_model=WorkflowResponse)
async def request_publish(
    workflow_id: UUID = Path(...),
    user: CurrentUser = Depends(get_current_user),
    service: WorkflowService = Depends(get_workflow_service),
):
    """Request publishing a personal workflow to the organization."""
    try:
        return await service.request_publish(workflow_id, UUID(user["id"]))
    except EntityNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow {workflow_id} not found",
        )
    except BusinessRuleViolation as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=safe_error_message(e))


@router.post("/{workflow_id}/approve-publish", response_model=WorkflowResponse)
async def approve_publish(
    workflow_id: UUID = Path(...),
    user: CurrentUser = Depends(require_admin),
    service: WorkflowService = Depends(get_workflow_service),
):
    """Admin approves a pending publish request."""
    try:
        return await service.approve_publish(workflow_id)
    except EntityNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow {workflow_id} not found",
        )
    except BusinessRuleViolation as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=safe_error_message(e))


@router.post("/{workflow_id}/reject-publish", response_model=WorkflowResponse)
async def reject_publish(
    workflow_id: UUID = Path(...),
    user: CurrentUser = Depends(require_admin),
    service: WorkflowService = Depends(get_workflow_service),
):
    """Admin rejects a pending publish request."""
    try:
        return await service.reject_publish(workflow_id)
    except EntityNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow {workflow_id} not found",
        )
    except BusinessRuleViolation as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=safe_error_message(e))


class WorkflowVisibilityUpdate(BaseModel):
    visibility: Visibility


@router.post("/{workflow_id}/visibility", response_model=WorkflowResponse)
async def set_workflow_visibility(
    payload: WorkflowVisibilityUpdate,
    workflow_id: UUID = Path(...),
    user: CurrentUser = Depends(require_super_admin),
    service: WorkflowService = Depends(get_workflow_service),
    audit_service: AuditService = Depends(get_audit_service),
):
    """super_admin-only: set a workflow's cross-org marketplace visibility
    (private | staging | public). The transition is audit-logged with old/new."""
    try:
        old_visibility, updated = await service.set_visibility(
            workflow_id, payload.visibility
        )
    except EntityNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow {workflow_id} not found",
        )

    await audit_service.log_event(
        actor_id=UUID(str(user.get("id"))),
        actor_type=AuditActorType(user.get("role") or "user"),
        action=AuditAction.UPDATE,
        resource_type=ResourceType.WORKFLOW,
        resource_id=workflow_id,
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

    # Notify other orgs' open marketplace views if this entered or left a catalog.
    if {old_visibility.value, payload.visibility.value} & _CATALOG_VISIBLE:
        await _broadcast_catalog_changed()

    return updated


@router.get("/{workflow_id}", response_model=WorkflowResponse)
async def get_workflow(
    workflow_id: UUID = Path(...),
    user: CurrentUser = Depends(get_current_user),
    service: WorkflowService = Depends(get_workflow_service),
):
    """
    Get a workflow by ID.

    Users can only access workflows for organizations they belong to.
    Super-admins can access all workflows.
    """
    workflow = await service.get_workflow(workflow_id)

    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow with ID {workflow_id} not found",
        )

    await validate_organization_access(str(workflow.organization_id), user)
    return workflow


@router.patch("/{workflow_id}", response_model=WorkflowResponse)
async def update_workflow(
    workflow_id: UUID,
    workflow_update: WorkflowUpdate,
    user: CurrentUser = Depends(get_current_user),
    service: WorkflowService = Depends(get_workflow_service),
):
    """
    Update a workflow.

    Users can only update workflows for organizations they belong to.
    Super-admins can update any workflow.
    """
    workflow = await service.get_workflow(workflow_id)

    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow with ID {workflow_id} not found",
        )

    await validate_organization_access(str(workflow.organization_id), user)

    # Trigger configuration is admin-only, mirroring the webhook/api-key secret
    # endpoints (all require_admin). A regular org user may edit a workflow's
    # name/status/steps but must not change how it is triggered.
    _TRIGGER_CONFIG_FIELDS = (
        "trigger_type",
        "webhook_method",
        "webhook_auth_type",
        "webhook_auth_header_name",
        "webhook_auth_header_value",
        "webhook_jwt_secret",
    )
    touches_trigger_config = any(
        getattr(workflow_update, f) is not None for f in _TRIGGER_CONFIG_FIELDS
    )
    if touches_trigger_config and user.get("role") not in ("admin", "super_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can change a workflow's trigger configuration.",
        )

    try:
        return await service.update_workflow(
            workflow_id, workflow_update, actor_id=UUID(str(user.get("id")))
        )
    except DuplicateEntityError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=safe_error_message(e))
    except BusinessRuleViolation as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=safe_error_message(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=safe_error_message(e))


@router.delete("/{workflow_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workflow(
    workflow_id: UUID = Path(...),
    user: CurrentUser = Depends(require_user),
    service: WorkflowService = Depends(get_workflow_service),
    audit_service: AuditService = Depends(get_audit_service),
):
    """
    Delete a workflow.

    Business Rule: Workflow must be deactivated before deletion.
    Active workflows cannot be deleted.

    Admins can delete any workflow in their org.
    Regular users can only delete workflows they created (created_by matches).
    Super-admins can delete any workflow.

    Raises:
        404: Workflow not found
        403: User doesn't have access to organization, or doesn't own the workflow
        409: Workflow is ACTIVE (must deactivate first)
    """
    workflow = await service.get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow with ID {workflow_id} not found",
        )

    await validate_organization_access(str(workflow.organization_id), user)

    user_role = user.get("role", "")
    if user_role not in ("admin", "super_admin"):
        user_id = user.get("id", "")
        if str(workflow.created_by) != str(user_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only delete workflows you created",
            )

    try:
        await service.delete_workflow(workflow_id, actor_id=UUID(str(user.get("id"))))
    except BusinessRuleViolation as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=safe_error_message(e),
        )

    # Audit the delete - a managed-package delete is a catalog transition the
    # marketplace cache-bust keys off (visibility recorded for that reason).
    await audit_service.log_event(
        actor_id=UUID(str(user.get("id"))),
        actor_type=AuditActorType(user.get("role") or "user"),
        action=AuditAction.DELETE,
        resource_type=ResourceType.WORKFLOW,
        resource_id=workflow_id,
        resource_name=workflow.name,
        organization_id=workflow.organization_id,
        category=AuditCategory.CONFIGURATION,
        metadata={"visibility": getattr(workflow, "visibility", None)},
    )

    # If a published (catalog-visible) workflow was deleted, nudge catalogs.
    if getattr(workflow, "visibility", None) in _CATALOG_VISIBLE:
        await _broadcast_catalog_changed()


@router.get("/{workflow_id}/credentials/check", response_model=CredentialCheckResponse)
async def check_workflow_credentials(
    workflow_id: UUID = Path(...),
    user: CurrentUser = Depends(get_current_user),
    service: WorkflowService = Depends(get_workflow_service),
    credential_repo: ProviderCredentialRepository = Depends(
        get_provider_credential_repository
    ),
    provider_repo: ProviderRepository = Depends(get_provider_repository),
    service_repo: ProviderServiceRepository = Depends(get_provider_service_repository),
    prompt_repo: PromptRepository = Depends(get_prompt_repository),
):
    """
    Check if all required credentials are ready for workflow execution.

    Returns:
        - ready: true if workflow can run without credential issues
        - issues: list of problems that need to be resolved before running

    Use this endpoint on workflow detail page load to show warnings
    before the user clicks "Run".
    """
    workflow = await service.get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow with ID {workflow_id} not found",
        )

    await validate_organization_access(str(workflow.organization_id), user)

    credential_service = WorkflowCredentialService()
    return await credential_service.check_workflow_credentials(
        workflow_id=workflow_id,
        organization_id=UUID(str(workflow.organization_id)),
        steps=workflow.steps,
        provider_repo=provider_repo,
        credential_repo=credential_repo,
        service_repo=service_repo,
        prompt_repo=prompt_repo,
    )


@router.get("/{workflow_id}/form-schema", response_model=WorkflowFormSchemaResponse)
async def get_workflow_form_schema(
    workflow_id: UUID = Path(...),
    user: CurrentUser = Depends(get_current_user),
    service: WorkflowService = Depends(get_workflow_service),
    service_repo: ProviderServiceRepository = Depends(get_provider_service_repository),
    prompt_repo: PromptRepository = Depends(get_prompt_repository),
):
    """
    Get the form schema for a workflow.

    Returns a form schema containing all parameters marked as 'form' type
    in the workflow's step input mappings. This schema is used to generate
    the form shown to end-users when creating a new instance.

    Form field configuration is derived automatically from the parameter's
    JSON Schema definition (type, description, enum, etc.), so no manual
    form configuration is required when setting mappingType to 'form'.

    Fields are ordered by step sequence in the workflow.
    """
    workflow = await service.get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow with ID {workflow_id} not found",
        )

    await validate_organization_access(str(workflow.organization_id), user)

    resolver = FormFieldResolver(
        provider_service_repository=service_repo,
        prompt_repository=prompt_repo,
    )
    form_fields = await resolver.resolve_fields(workflow)

    return WorkflowFormSchemaResponse(
        workflow_id=workflow_id,
        workflow_name=workflow.name,
        has_form_fields=len(form_fields) > 0,
        fields=form_fields,
    )


# Response model for webhook token
class WebhookTokenResponse(BaseModel):
    """Response for webhook token operations."""

    webhook_token: str
    webhook_secret: str
    webhook_url: str


@router.post(
    "/{workflow_id}/webhook-token",
    response_model=WebhookTokenResponse,
    status_code=status.HTTP_201_CREATED,
)
async def generate_webhook_token(
    workflow_id: UUID = Path(...),
    user: CurrentUser = Depends(require_admin),
    service: WorkflowService = Depends(get_workflow_service),
):
    """
    Generate a secure webhook token for triggering this workflow.

    This creates a unique, unguessable URL that external systems can call
    to start new workflow instances.

    Requires ADMIN or SUPER_ADMIN role.

    Returns:
        - webhook_token: The generated token
        - webhook_url: The full URL to call

    Raises:
        404: Workflow not found
        409: Token already exists (use regenerate instead)
    """
    workflow = await service.get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow with ID {workflow_id} not found",
        )

    await validate_organization_access(str(workflow.organization_id), user)

    try:
        result = await service.generate_webhook_token(workflow_id)
        webhook_url = f"{settings.API_BASE_URL}/api/v1/webhooks/incoming/{result['token']}"
        return WebhookTokenResponse(
            webhook_token=result["token"],
            webhook_secret=result["secret"],
            webhook_url=webhook_url,
        )
    except BusinessRuleViolation as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=safe_error_message(e),
        )


@router.post(
    "/{workflow_id}/webhook-token/regenerate", response_model=WebhookTokenResponse
)
async def regenerate_webhook_token(
    workflow_id: UUID = Path(...),
    user: CurrentUser = Depends(require_admin),
    service: WorkflowService = Depends(get_workflow_service),
):
    """
    Regenerate the webhook token for this workflow.

    WARNING: This will invalidate the previous webhook URL.
    Any external systems using the old URL will need to be updated.

    Requires ADMIN or SUPER_ADMIN role.

    Returns:
        - webhook_token: The new token
        - webhook_url: The new URL to call

    Raises:
        404: Workflow not found or no token exists
    """
    workflow = await service.get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow with ID {workflow_id} not found",
        )

    await validate_organization_access(str(workflow.organization_id), user)

    try:
        result = await service.regenerate_webhook_token(workflow_id)
        webhook_url = f"{settings.API_BASE_URL}/api/v1/webhooks/incoming/{result['token']}"
        return WebhookTokenResponse(
            webhook_token=result["token"],
            webhook_secret=result["secret"],
            webhook_url=webhook_url,
        )
    except BusinessRuleViolation as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=safe_error_message(e),
        )


@router.delete("/{workflow_id}/webhook-token", status_code=status.HTTP_204_NO_CONTENT)
async def delete_webhook_token(
    workflow_id: UUID = Path(...),
    user: CurrentUser = Depends(require_admin),
    service: WorkflowService = Depends(get_workflow_service),
):
    """
    Remove the webhook token from this workflow.

    This disables webhook triggering for this workflow.

    Requires ADMIN or SUPER_ADMIN role.

    Raises:
        404: Workflow not found
    """
    workflow = await service.get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow with ID {workflow_id} not found",
        )

    await validate_organization_access(str(workflow.organization_id), user)
    await service.clear_webhook_token(workflow_id)


# =============================================================================
# Schedule / API-key / Event Trigger Endpoints
# =============================================================================


class ScheduleConfigRequest(BaseModel):
    """Request body for configuring a workflow schedule trigger."""

    dtstart: Optional[datetime] = None
    rrule: Optional[str] = None
    timezone: str = "UTC"
    enabled: bool = False


class ScheduleConfigResponse(BaseModel):
    """Response for schedule trigger configuration."""

    enabled: bool
    next_run_at: Optional[str] = None


class ApiKeyResponse(BaseModel):
    """Response for API-key trigger operations."""

    api_key: str
    trigger_url: str
    # How many workflows share this key's trigger secret (incl. this one). >1 →
    # the UI hides in-workflow Regenerate and points to the Secrets page instead.
    shared_by_count: int = 1


class RotateTriggerSecretKeyResponse(BaseModel):
    """Result of regenerating a shared `workflow_trigger` secret on the Secrets page."""

    api_key: str
    shared_by_count: int


class TriggerSecretOption(BaseModel):
    """A reusable workflow_trigger OrganizationSecret an admin can share."""

    id: str
    name: str
    shared_by_count: int


class SetTriggerSecretRequest(BaseModel):
    """Point a workflow at an existing trigger secret (share it)."""

    secret_id: UUID


class EventConfigRequest(BaseModel):
    """Request body for configuring a workflow event trigger."""

    source_workflow_id: UUID
    on: str = "completed"


@router.put(
    "/{workflow_id}/schedule",
    response_model=ScheduleConfigResponse,
)
async def set_workflow_schedule(
    body: ScheduleConfigRequest,
    workflow_id: UUID = Path(...),
    user: CurrentUser = Depends(require_admin),
    service: WorkflowService = Depends(get_workflow_service),
):
    """
    Configure the schedule (SCHEDULE trigger) for this workflow.

    Requires ADMIN or SUPER_ADMIN role.

    Raises:
        404: Workflow not found
        400: Invalid schedule rule
    """
    workflow = await service.get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow with ID {workflow_id} not found",
        )

    await validate_organization_access(str(workflow.organization_id), user)

    try:
        return await service.set_schedule(
            workflow_id,
            dtstart=body.dtstart,
            rrule=body.rrule,
            timezone=body.timezone,
            enabled=body.enabled,
        )
    except BusinessRuleViolation as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_message(e),
        )


@router.delete("/{workflow_id}/schedule", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workflow_schedule(
    workflow_id: UUID = Path(...),
    user: CurrentUser = Depends(require_admin),
    service: WorkflowService = Depends(get_workflow_service),
):
    """
    Remove the schedule trigger from this workflow.

    Requires ADMIN or SUPER_ADMIN role.

    Raises:
        404: Workflow not found
    """
    workflow = await service.get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow with ID {workflow_id} not found",
        )

    await validate_organization_access(str(workflow.organization_id), user)
    await service.clear_schedule(workflow_id)


@router.get("/{workflow_id}/api-key", response_model=ApiKeyResponse)
async def recall_workflow_api_key(
    workflow_id: UUID = Path(...),
    user: CurrentUser = Depends(require_admin),
    service: WorkflowService = Depends(get_workflow_service),
):
    """
    Recall the existing API key for this workflow (admin only).

    The key is stored encrypted-at-rest in an OrganizationSecret, so an admin
    can retrieve it to hand to integrations instead of regenerating. Regular
    users cannot view it.

    Raises:
        404: Workflow not found, or no API key is configured.
    """
    workflow = await service.get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow with ID {workflow_id} not found",
        )

    await validate_organization_access(str(workflow.organization_id), user)

    api_key = await service.recall_api_key(workflow_id)
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No API key is configured for this workflow",
        )
    trigger_url = f"{settings.API_BASE_URL}/api/v1/webhooks/trigger/{workflow_id}"
    shared_by_count = await service.trigger_secret_share_count(workflow_id)
    return ApiKeyResponse(
        api_key=api_key, trigger_url=trigger_url, shared_by_count=shared_by_count
    )


@router.get(
    "/{workflow_id}/trigger-secret/options",
    response_model=List[TriggerSecretOption],
)
async def list_workflow_trigger_secret_options(
    workflow_id: UUID = Path(...),
    secret_type: str = Query(
        ...,
        description=(
            "Trigger-secret type to list: 'api_key', 'webhook_hmac', "
            "'webhook_header', or 'webhook_jwt'. Each credential lives in its own "
            "typed secret, so the picker filters on this column directly."
        ),
    ),
    user: CurrentUser = Depends(require_admin),
    service: WorkflowService = Depends(get_workflow_service),
):
    """List the org's reusable trigger secrets of one TYPE (admin only) so this
    workflow can **share** an existing one instead of minting a new one. Each
    option carries a shared-by-N count.

    Raises:
        404: Workflow not found.
        400: `secret_type` is not a trigger-secret type.
    """
    if secret_type not in TRIGGER_SECRET_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"secret_type must be one of {sorted(TRIGGER_SECRET_TYPES)}",
        )
    workflow = await service.get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow with ID {workflow_id} not found",
        )
    await validate_organization_access(str(workflow.organization_id), user)
    options = await service.list_trigger_secrets(
        workflow.organization_id, secret_type
    )
    return [TriggerSecretOption(**o) for o in options]


@router.put("/{workflow_id}/trigger-secret", response_model=WorkflowResponse)
async def set_workflow_trigger_secret(
    body: SetTriggerSecretRequest,
    workflow_id: UUID = Path(...),
    user: CurrentUser = Depends(require_admin),
    service: WorkflowService = Depends(get_workflow_service),
):
    """Point this workflow at an existing `workflow_trigger` secret (share it).
    Admin only. The secret must exist and belong to this org.

    Raises:
        404: Workflow not found.
        400: The secret doesn't exist / isn't a trigger secret in this org.
    """
    workflow = await service.get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow with ID {workflow_id} not found",
        )
    await validate_organization_access(str(workflow.organization_id), user)
    try:
        return await service.set_trigger_secret(workflow_id, body.secret_id)
    except BusinessRuleViolation as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_message(e),
        )


@router.post(
    "/trigger-secrets/{secret_id}/regenerate-key",
    response_model=RotateTriggerSecretKeyResponse,
)
async def regenerate_trigger_secret_key(
    secret_id: UUID = Path(...),
    user: CurrentUser = Depends(require_admin),
    service: WorkflowService = Depends(get_workflow_service),
):
    """Deliberately rotate a `workflow_trigger` secret's API key from the Secrets
    page (admin only). Every workflow sharing the secret immediately uses the new
    key; the response reports how many that is. This is where rotation of a
    *shared* secret lives — the in-workflow Regenerate refuses when shared.

    Raises:
        400: The secret doesn't exist / isn't a trigger secret in this org.
    """
    org_id = user.get("org_id") or user.get("organization_id")
    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User does not belong to an organization",
        )
    try:
        result = await service.regenerate_trigger_secret_key(
            secret_id, UUID(str(org_id))
        )
        return RotateTriggerSecretKeyResponse(**result)
    except BusinessRuleViolation as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_message(e),
        )


@router.post(
    "/{workflow_id}/api-key",
    response_model=ApiKeyResponse,
    status_code=status.HTTP_201_CREATED,
)
async def generate_workflow_api_key(
    workflow_id: UUID = Path(...),
    user: CurrentUser = Depends(require_admin),
    service: WorkflowService = Depends(get_workflow_service),
):
    """
    Generate an API key (API trigger) for this workflow.

    Requires ADMIN or SUPER_ADMIN role.

    Raises:
        404: Workflow not found
        409: API key already exists (use regenerate instead)
    """
    workflow = await service.get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow with ID {workflow_id} not found",
        )

    await validate_organization_access(str(workflow.organization_id), user)

    try:
        api_key = await service.generate_api_key(workflow_id)
        trigger_url = (
            f"{settings.API_BASE_URL}/api/v1/webhooks/trigger/{workflow_id}"
        )
        shared_by_count = await service.trigger_secret_share_count(workflow_id)
        return ApiKeyResponse(
            api_key=api_key,
            trigger_url=trigger_url,
            shared_by_count=shared_by_count,
        )
    except BusinessRuleViolation as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=safe_error_message(e),
        )


@router.post("/{workflow_id}/api-key/regenerate", response_model=ApiKeyResponse)
async def regenerate_workflow_api_key(
    workflow_id: UUID = Path(...),
    user: CurrentUser = Depends(require_admin),
    service: WorkflowService = Depends(get_workflow_service),
):
    """
    Regenerate the API key for this workflow.

    WARNING: This invalidates the previous API key.

    Requires ADMIN or SUPER_ADMIN role.

    Raises:
        404: Workflow not found or no API key exists
    """
    workflow = await service.get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow with ID {workflow_id} not found",
        )

    await validate_organization_access(str(workflow.organization_id), user)

    try:
        api_key = await service.regenerate_api_key(workflow_id)
        trigger_url = (
            f"{settings.API_BASE_URL}/api/v1/webhooks/trigger/{workflow_id}"
        )
        shared_by_count = await service.trigger_secret_share_count(workflow_id)
        return ApiKeyResponse(
            api_key=api_key,
            trigger_url=trigger_url,
            shared_by_count=shared_by_count,
        )
    except BusinessRuleViolation as e:
        # A shared secret must be rotated on the Secrets page (409), not here;
        # "no key exists" stays a 404.
        code = status.HTTP_409_CONFLICT if e.code == "TRIGGER_SECRET_SHARED" else status.HTTP_404_NOT_FOUND
        raise HTTPException(status_code=code, detail=safe_error_message(e))


@router.delete("/{workflow_id}/api-key", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workflow_api_key(
    workflow_id: UUID = Path(...),
    user: CurrentUser = Depends(require_admin),
    service: WorkflowService = Depends(get_workflow_service),
):
    """
    Remove the API key from this workflow.

    Requires ADMIN or SUPER_ADMIN role.

    Raises:
        404: Workflow not found
    """
    workflow = await service.get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow with ID {workflow_id} not found",
        )

    await validate_organization_access(str(workflow.organization_id), user)
    await service.clear_api_key(workflow_id)


@router.put("/{workflow_id}/event", status_code=status.HTTP_204_NO_CONTENT)
async def set_workflow_event_trigger(
    body: EventConfigRequest,
    workflow_id: UUID = Path(...),
    user: CurrentUser = Depends(require_admin),
    service: WorkflowService = Depends(get_workflow_service),
):
    """
    Configure the event trigger (EVENT trigger) for this workflow.

    Requires ADMIN or SUPER_ADMIN role.

    Raises:
        404: Workflow not found
        400: Invalid event configuration (self-trigger, cross-org, invalid on)
    """
    workflow = await service.get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow with ID {workflow_id} not found",
        )

    await validate_organization_access(str(workflow.organization_id), user)

    try:
        await service.set_event_trigger(
            workflow_id,
            body.source_workflow_id,
            body.on,
        )
    except BusinessRuleViolation as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_message(e),
        )


@router.delete("/{workflow_id}/event", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workflow_event_trigger(
    workflow_id: UUID = Path(...),
    user: CurrentUser = Depends(require_admin),
    service: WorkflowService = Depends(get_workflow_service),
):
    """
    Remove the event trigger from this workflow.

    Requires ADMIN or SUPER_ADMIN role.

    Raises:
        404: Workflow not found
    """
    workflow = await service.get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow with ID {workflow_id} not found",
        )

    await validate_organization_access(str(workflow.organization_id), user)
    await service.clear_event_trigger(workflow_id)


# =============================================================================
# Step Webhook Token Endpoints (for core.webhook_wait steps)
# =============================================================================


class StepWebhookTokenResponse(BaseModel):
    """Response for step webhook token operations."""

    step_id: str
    webhook_token: str
    webhook_secret: str
    webhook_url: str


@router.post(
    "/{workflow_id}/steps/{step_id}/webhook-token",
    response_model=StepWebhookTokenResponse,
    status_code=status.HTTP_201_CREATED,
)
async def generate_step_webhook_token(
    workflow_id: UUID = Path(...),
    step_id: str = Path(...),
    user: CurrentUser = Depends(require_admin),
    service: WorkflowService = Depends(get_workflow_service),
):
    """
    Generate a secure webhook token for a workflow step.

    Used for core.webhook_wait steps that pause the workflow and wait
    for an external callback.

    Requires ADMIN or SUPER_ADMIN role.

    Returns:
        - step_id: The step ID
        - webhook_token: The generated token
        - webhook_url: The full URL for callbacks

    Raises:
        404: Workflow or step not found
        409: Token already exists (use regenerate instead)
    """
    workflow = await service.get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow with ID {workflow_id} not found",
        )

    await validate_organization_access(str(workflow.organization_id), user)

    try:
        result = await service.generate_step_webhook_token(workflow_id, step_id)
        webhook_url = f"/api/v1/webhooks/incoming/{result['token']}"
        return StepWebhookTokenResponse(
            step_id=step_id,
            webhook_token=result["token"],
            webhook_secret=result["secret"],
            webhook_url=webhook_url,
        )
    except EntityNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=safe_error_message(e),
        )
    except BusinessRuleViolation as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=safe_error_message(e),
        )


@router.post(
    "/{workflow_id}/steps/{step_id}/webhook-token/regenerate",
    response_model=StepWebhookTokenResponse,
)
async def regenerate_step_webhook_token(
    workflow_id: UUID = Path(...),
    step_id: str = Path(...),
    user: CurrentUser = Depends(require_admin),
    service: WorkflowService = Depends(get_workflow_service),
):
    """
    Regenerate the webhook token for a workflow step.

    WARNING: This will invalidate the previous callback URL.
    Any external systems using the old URL will need to be updated.

    Requires ADMIN or SUPER_ADMIN role.

    Returns:
        - step_id: The step ID
        - webhook_token: The new token
        - webhook_url: The new URL for callbacks

    Raises:
        404: Workflow, step, or token not found
    """
    workflow = await service.get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow with ID {workflow_id} not found",
        )

    await validate_organization_access(str(workflow.organization_id), user)

    try:
        result = await service.regenerate_step_webhook_token(workflow_id, step_id)
        webhook_url = f"/api/v1/webhooks/incoming/{result['token']}"
        return StepWebhookTokenResponse(
            step_id=step_id,
            webhook_token=result["token"],
            webhook_secret=result["secret"],
            webhook_url=webhook_url,
        )
    except EntityNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=safe_error_message(e),
        )
    except BusinessRuleViolation as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=safe_error_message(e),
        )


@router.get(
    "/{workflow_id}/steps/{step_id}/webhook-token",
    response_model=StepWebhookTokenResponse,
)
async def get_step_webhook_token(
    workflow_id: UUID = Path(...),
    step_id: str = Path(...),
    user: CurrentUser = Depends(require_admin),
    service: WorkflowService = Depends(get_workflow_service),
):
    """
    Get the webhook token for a workflow step.

    Requires ADMIN or SUPER_ADMIN role.

    Returns:
        - step_id: The step ID
        - webhook_token: The token
        - webhook_url: The callback URL

    Raises:
        404: Workflow, step, or token not found
    """
    workflow = await service.get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow with ID {workflow_id} not found",
        )

    await validate_organization_access(str(workflow.organization_id), user)

    try:
        result = await service.get_step_webhook_token(workflow_id, step_id)
        if not result["token"]:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No webhook token found for step {step_id}",
            )
        webhook_url = f"/api/v1/webhooks/incoming/{result['token']}"
        return StepWebhookTokenResponse(
            step_id=step_id,
            webhook_token=result["token"],
            webhook_secret=result["secret"] or "",
            webhook_url=webhook_url,
        )
    except EntityNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=safe_error_message(e),
        )


# =============================================================================
# Workflow Export/Import Endpoints
# =============================================================================


class WorkflowImportResponse(BaseModel):
    """Response for workflow import."""

    workflow: WorkflowResponse
    warnings: List[str] = []


@router.get("/{workflow_id}/export")
async def export_workflow(
    workflow_id: UUID = Path(...),
    user: CurrentUser = Depends(get_current_user),
    service: WorkflowService = Depends(get_workflow_service),
):
    """
    Export a workflow as a JSON file.

    The exported file contains the workflow definition without organization-specific
    IDs, making it portable for import into other organizations.

    Returns a downloadable JSON file.
    """
    workflow = await service.get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow with ID {workflow_id} not found",
        )

    await validate_organization_access(str(workflow.organization_id), user)

    # Build export data - exclude org-specific fields
    export_data = {
        "export_version": 1,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "name": workflow.name,
        "description": workflow.description,
        "trigger_type": (
            workflow.trigger_type.value
            if hasattr(workflow.trigger_type, "value")
            else workflow.trigger_type
        ),
        "steps": workflow.steps,
        "trigger_input_schema": workflow.trigger_input_schema,
        "client_metadata": workflow.client_metadata,
    }

    # Sanitize filename
    safe_name = "".join(c if c.isalnum() or c in "._- " else "_" for c in workflow.name)
    filename = f"{safe_name}.json"

    return Response(
        content=json.dumps(export_data, indent=2, default=str),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post(
    "/import",
    response_model=WorkflowImportResponse,
    status_code=status.HTTP_201_CREATED,
)
async def import_workflow(
    file: UploadFile = File(..., description="Workflow JSON file to import"),
    user: CurrentUser = Depends(require_user),
    service: WorkflowService = Depends(get_workflow_service),
    provider_repo: ProviderRepository = Depends(get_provider_repository),
    prompt_repo: PromptRepository = Depends(get_prompt_repository),
):
    """
    Import a workflow from a JSON file.

    Creates a new workflow in the target organization from an exported workflow file.
    The workflow name will have "(imported)" appended if a workflow with the same
    name already exists.

    Returns the created workflow and any warnings (e.g., missing providers).
    """
    # Validate file type (presentation layer concern)
    if not file.filename or not file.filename.endswith(".json"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be a .json file",
        )

    # Read and parse JSON (presentation layer concern - file handling)
    try:
        content = await file.read()
        data = json.loads(content.decode("utf-8"))
    except json.JSONDecodeError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Uploaded file is not valid JSON (line {e.lineno}, column {e.colno}).",
        )
    except Exception:
        logger.exception("Failed to read uploaded workflow file")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to read file",
        )

    # Target organization is always the caller's own (DB-sourced).
    effective_org_id = user["org_id"]

    # Delegate business logic to service
    try:
        # Mirror manual create: super_admins author org-level workflows;
        # everyone else imports a personal workflow that only they can see and
        # must request publish approval to promote to organization scope.
        import_scope = (
            WorkflowScope.ORGANIZATION
            if user.get("role") == Role.SUPER_ADMIN.value
            else WorkflowScope.PERSONAL
        )
        created_workflow, warnings = await service.import_workflow(
            data=data,
            organization_id=UUID(effective_org_id),
            created_by=UUID(user["id"]),
            provider_repo=provider_repo,
            prompt_repo=prompt_repo,
            scope=import_scope,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=safe_error_message(e))
    except DuplicateEntityError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=safe_error_message(e))

    return WorkflowImportResponse(
        workflow=created_workflow,
        warnings=warnings,
    )
