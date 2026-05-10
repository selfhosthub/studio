# api/app/presentation/api/instances.py

"""Workflow instance management API endpoints."""

import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from app.config.settings import settings
from fastapi import (
    APIRouter,
    Body,
    Depends,
    File,
    HTTPException,
    Path,
    Query,
    UploadFile,
    status,
)
from pydantic import BaseModel, Field

from app.application.dtos.instance_dto import (
    InstanceCreate,
    InstanceResponse,
    StepExecutionCreate,
    StepExecutionResponse,
    PaginatedInstanceResponse,
)
from app.application.dtos.org_file_dto import OrgFileResponse
from app.application.services.audit_service import AuditService
from app.application.services.instance_service import InstanceService
from app.application.services.org_file import OrgFileService
from app.domain.audit.models import (
    AuditAction,
    AuditActorType,
    AuditCategory,
    AuditSeverity,
    ResourceType,
)
from app.domain.instance_step.step_execution_repository import StepExecutionRepository
from app.presentation.api.dependencies import (
    CurrentUser,
    get_audit_service,
    get_current_user,
    get_db_session,
    get_effective_org_id,
    get_instance_service,
    get_step_execution_repository,
    get_org_file_service,
    get_notifier,
    require_tenant,
    validate_organization_access,
)
from app.infrastructure.errors import safe_error_message
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

router = APIRouter()


async def _audit_instance_action(
    audit_service: AuditService,
    user: CurrentUser,
    action: AuditAction,
    instance: InstanceResponse,
    metadata: Optional[Dict[str, Any]] = None,
    resource_type: ResourceType = ResourceType.INSTANCE,
    resource_id: Optional[UUID] = None,
    resource_name: Optional[str] = None,
    severity: AuditSeverity = AuditSeverity.INFO,
) -> None:
    """Log an audit event for a user-initiated instance action."""
    base_metadata = {
        "workflow_id": str(instance.workflow_id),
        "workflow_name": instance.workflow_name,
        "instance_status": instance.status,
    }
    if metadata:
        base_metadata.update(metadata)

    await audit_service.log_event(
        actor_id=UUID(str(user.get("id"))),
        actor_type=AuditActorType(user.get("role") or "user"),
        action=action,
        resource_type=resource_type,
        resource_id=resource_id or instance.id,
        resource_name=resource_name or instance.name,
        organization_id=instance.organization_id,
        severity=severity,
        category=AuditCategory.CONFIGURATION,
        metadata=base_metadata,
    )


@router.post("/", response_model=InstanceResponse, status_code=status.HTTP_201_CREATED)
async def create_instance(
    instance: InstanceCreate,
    user: CurrentUser = Depends(require_tenant),
    service: InstanceService = Depends(get_instance_service),
):
    logger.info(
        f"Instance created for workflow {instance.workflow_id} "
        f"by user {user.get('id')} via API"
    )
    try:
        return await service.create_instance(instance)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=safe_error_message(e))


@router.get("/by-workflow/{workflow_id}", response_model=List[InstanceResponse])
async def list_instances_by_workflow(
    workflow_id: UUID = Path(...),
    status_filter: Optional[str] = Query(None, alias="status"),
    skip: int = Query(0, ge=0),
    limit: int = Query(settings.API_PAGE_LIMIT_DEFAULT, ge=1, le=settings.API_PAGE_MAX),
    user: CurrentUser = Depends(get_current_user),
    service: InstanceService = Depends(get_instance_service),
):
    user_org_id = UUID(user["org_id"]) if user.get("org_id") else None
    if not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User organization not found",
        )

    instances = await service.list_instances(
        organization_id=user_org_id,
        workflow_id=workflow_id,
        status=status_filter,
        skip=skip,
        limit=limit,
    )

    if instances:
        await validate_organization_access(str(instances[0].organization_id), user)

    return instances


@router.get("/", response_model=PaginatedInstanceResponse)
async def list_instances(
    organization_id: Optional[UUID] = Query(
        None,
        description="Organization ID to filter by (optional, derived from user token if not provided)",
    ),
    status_filter: Optional[str] = Query(None, alias="status"),
    skip: int = Query(0, ge=0),
    limit: int = Query(settings.API_PAGE_LIMIT_SMALL, ge=1, le=settings.API_PAGE_MAX),
    user: CurrentUser = Depends(get_current_user),
    service: InstanceService = Depends(get_instance_service),
):
    effective_org_id = get_effective_org_id(
        str(organization_id) if organization_id else None, user
    )

    return await service.list_instances_paginated(
        organization_id=UUID(effective_org_id),
        status=status_filter,
        skip=skip,
        limit=limit,
    )


@router.get("/by-organization/{organization_id}", response_model=List[InstanceResponse])
async def list_instances_by_organization(
    organization_id: UUID = Path(...),
    status_filter: Optional[str] = Query(None, alias="status"),
    skip: int = Query(0, ge=0),
    limit: int = Query(settings.API_PAGE_LIMIT_DEFAULT, ge=1, le=settings.API_PAGE_MAX),
    user: CurrentUser = Depends(get_current_user),
    service: InstanceService = Depends(get_instance_service),
):
    """Deprecated: use GET /instances?organization_id=... instead."""
    await validate_organization_access(str(organization_id), user)

    return await service.list_instances(
        organization_id=organization_id,
        status=status_filter,
        skip=skip,
        limit=limit,
    )


@router.get("/{instance_id}", response_model=InstanceResponse)
async def get_instance(
    instance_id: UUID = Path(...),
    user: CurrentUser = Depends(get_current_user),
    service: InstanceService = Depends(get_instance_service),
):
    instance = await service.get_instance_with_steps(instance_id)
    if not instance:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Instance with ID {instance_id} not found",
        )

    await validate_organization_access(str(instance.organization_id), user)
    return instance


@router.post("/{instance_id}/start", response_model=InstanceResponse)
async def start_instance(
    instance_id: UUID = Path(...),
    user: CurrentUser = Depends(require_tenant),
    service: InstanceService = Depends(get_instance_service),
    notifier=Depends(get_notifier),
    session: AsyncSession = Depends(get_db_session),
):
    """Start a workflow instance."""
    instance = await service.get_instance(instance_id)
    if not instance:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Instance with ID {instance_id} not found",
        )

    await validate_organization_access(str(instance.organization_id), user)

    logger.info(f"Instance {instance_id} started by user {user.get('id')} via API")

    try:
        result = await service.start_instance(instance_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=safe_error_message(e))

    await notifier.announce_state_change(
        instance=instance,
        action_type="processing_started",
        session=session,
    )

    return result


class FormSubmitRequest(BaseModel):
    """Request body for submitting form values and starting an instance."""

    form_values: Dict[str, Any]


@router.post("/{instance_id}/submit-form", response_model=InstanceResponse)
async def submit_form_and_start(
    instance_id: UUID = Path(...),
    request: FormSubmitRequest = Body(...),
    user: CurrentUser = Depends(require_tenant),
    service: InstanceService = Depends(get_instance_service),
    notifier=Depends(get_notifier),
    session: AsyncSession = Depends(get_db_session),
):
    """Submit form values and start a workflow instance. form_values keyed by '{step_id}.{parameter_key}'."""
    instance = await service.get_instance(instance_id)
    if not instance:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Instance with ID {instance_id} not found",
        )

    await validate_organization_access(str(instance.organization_id), user)

    logger.info(
        f"Instance {instance_id} form submitted and started "
        f"by user {user.get('id')} via API"
    )

    try:
        result = await service.submit_form_and_start(instance_id, request.form_values)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=safe_error_message(e))

    await notifier.announce_state_change(
        instance=instance,
        action_type="processing_started",
        session=session,
    )

    return result


@router.post("/{instance_id}/complete", response_model=InstanceResponse)
async def complete_instance(
    instance_id: UUID = Path(...),
    output_data: Optional[Dict[str, Any]] = None,
    user: CurrentUser = Depends(require_tenant),
    service: InstanceService = Depends(get_instance_service),
):
    """Complete a workflow instance."""
    instance = await service.get_instance(instance_id)
    if not instance:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Instance with ID {instance_id} not found",
        )

    await validate_organization_access(str(instance.organization_id), user)

    logger.info(f"Instance {instance_id} completed by user {user.get('id')} via API")

    try:
        return await service.complete_instance(instance_id, output_data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=safe_error_message(e))


@router.post("/{instance_id}/fail", response_model=InstanceResponse)
async def fail_instance(
    instance_id: UUID = Path(...),
    error_data: Optional[Dict[str, Any]] = None,
    user: CurrentUser = Depends(require_tenant),
    service: InstanceService = Depends(get_instance_service),
):
    """Mark a workflow instance as failed."""
    instance = await service.get_instance(instance_id)
    if not instance:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Instance with ID {instance_id} not found",
        )

    await validate_organization_access(str(instance.organization_id), user)

    logger.info(
        f"Instance {instance_id} marked failed by user {user.get('id')} via API"
    )

    try:
        return await service.fail_instance(instance_id, error_data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=safe_error_message(e))


@router.post("/{instance_id}/pause", response_model=InstanceResponse)
async def pause_instance(
    instance_id: UUID = Path(...),
    user: CurrentUser = Depends(require_tenant),
    service: InstanceService = Depends(get_instance_service),
):
    """Pause a workflow instance."""
    instance = await service.get_instance(instance_id)
    if not instance:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Instance with ID {instance_id} not found",
        )

    await validate_organization_access(str(instance.organization_id), user)

    logger.info(f"Instance {instance_id} paused by user {user.get('id')} via API")

    try:
        return await service.pause_instance(instance_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=safe_error_message(e))


@router.post("/{instance_id}/resume", response_model=InstanceResponse)
async def resume_instance(
    instance_id: UUID = Path(...),
    user: CurrentUser = Depends(require_tenant),
    service: InstanceService = Depends(get_instance_service),
):
    """Resume a paused workflow instance."""
    instance = await service.get_instance(instance_id)
    if not instance:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Instance with ID {instance_id} not found",
        )

    await validate_organization_access(str(instance.organization_id), user)

    logger.info(f"Instance {instance_id} resumed by user {user.get('id')} via API")

    try:
        return await service.resume_instance(instance_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=safe_error_message(e))


@router.post("/{instance_id}/cancel", response_model=InstanceResponse)
async def cancel_instance(
    instance_id: UUID = Path(...),
    user: CurrentUser = Depends(require_tenant),
    service: InstanceService = Depends(get_instance_service),
    audit_service: AuditService = Depends(get_audit_service),
    notifier=Depends(get_notifier),
    session: AsyncSession = Depends(get_db_session),
):
    """Cancel a workflow instance."""
    instance = await service.get_instance(instance_id)
    if not instance:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Instance with ID {instance_id} not found",
        )

    await validate_organization_access(str(instance.organization_id), user)

    await _audit_instance_action(
        audit_service,
        user,
        AuditAction.CANCEL,
        instance,
        severity=AuditSeverity.WARNING,
    )

    logger.info(
        f"Instance {instance_id} cancelled by user {user.get('id')} "
        f"(email={user.get('email')}) via API"
    )

    try:
        result = await service.cancel_instance(instance_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=safe_error_message(e))

    await notifier.announce_state_change(
        instance=instance,
        action_type="cancelled",
        session=session,
    )

    return result


TERMINAL_STATUSES = {"completed", "failed", "cancelled"}


@router.delete("/{instance_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_instance(
    instance_id: UUID = Path(...),
    user: CurrentUser = Depends(require_tenant),
    service: InstanceService = Depends(get_instance_service),
    audit_service: AuditService = Depends(get_audit_service),
):
    """Permanently delete an instance. Only terminal statuses allowed. Admins may delete any; users only their own."""
    instance = await service.get_instance(instance_id)
    if not instance:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Instance with ID {instance_id} not found",
        )

    await validate_organization_access(str(instance.organization_id), user)

    # Users can only delete instances they created; admins can delete any in their org
    user_role = user.get("role", "user")
    if user_role == "user" and str(instance.user_id) != str(user.get("id")):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Users can only delete their own instances",
        )

    if instance.status not in TERMINAL_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot delete instance with status '{instance.status}'. "
            f"Only completed, failed, or cancelled instances can be deleted.",
        )

    await _audit_instance_action(
        audit_service,
        user,
        AuditAction.DELETE,
        instance,
        metadata={"created_by": str(instance.user_id) if instance.user_id else None},
        severity=AuditSeverity.WARNING,
    )

    logger.info(
        f"Instance {instance_id} deleted by user {user.get('id')} "
        f"(role={user_role}) via API"
    )

    try:
        await service.delete_instance(instance_id, instance.organization_id)
    except Exception as e:
        logger.exception(f"Failed to delete instance {instance_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete instance",
        )


@router.post(
    "/{instance_id}/step_executions",
    response_model=StepExecutionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_job(
    job: StepExecutionCreate,
    instance_id: UUID = Path(...),
    user: CurrentUser = Depends(require_tenant),
    service: InstanceService = Depends(get_instance_service),
):
    if str(job.instance_id) != str(instance_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Instance ID in the path must match the one in the request message",
        )

    instance = await service.get_instance(instance_id)
    if not instance:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Instance with ID {instance_id} not found",
        )

    await validate_organization_access(str(instance.organization_id), user)

    try:
        return await service.create_job_for_instance(instance_id, job)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=safe_error_message(e))


@router.get("/step_executions/{job_id}", response_model=StepExecutionResponse)
async def get_job(
    job_id: UUID = Path(...),
    user: CurrentUser = Depends(get_current_user),
    service: InstanceService = Depends(get_instance_service),
):
    job = await service.get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job with ID {job_id} not found",
        )

    instance = await service.get_instance(job.instance_id)
    if not instance:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Instance with ID {job.instance_id} not found",
        )

    await validate_organization_access(str(instance.organization_id), user)
    return job


# Note: Job state transitions (start/complete/fail) should come from:
# - Queue consumers (workers reporting results via queue)
# - Webhook callbacks (external providers reporting status)
# - Internal workflow engine (orchestrating job execution)
#
# The following endpoints are for manual user intervention only:


@router.post("/step_executions/{job_id}/cancel", response_model=StepExecutionResponse)
async def cancel_job(
    job_id: UUID = Path(...),
    user: CurrentUser = Depends(require_tenant),
    service: InstanceService = Depends(get_instance_service),
    audit_service: AuditService = Depends(get_audit_service),
):
    """Cancel a job execution."""
    job = await service.get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job with ID {job_id} not found",
        )

    instance = await service.get_instance(job.instance_id)
    if not instance:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Instance with ID {job.instance_id} not found",
        )

    await validate_organization_access(str(instance.organization_id), user)

    await _audit_instance_action(
        audit_service,
        user,
        AuditAction.CANCEL,
        instance,
        resource_type=ResourceType.INSTANCE_STEP,
        metadata={"step_id": job.step_id, "job_id": str(job_id), "scope": "job"},
        severity=AuditSeverity.WARNING,
    )

    logger.info(
        f"Job {job_id} (step={job.step_id}, instance={job.instance_id}) "
        f"cancelled by user {user.get('id')} via API"
    )

    try:
        return await service.cancel_job(job_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=safe_error_message(e))


@router.post(
    "/{instance_id}/cancel-step-executions", response_model=List[StepExecutionResponse]
)
async def cancel_all_jobs(
    instance_id: UUID = Path(...),
    user: CurrentUser = Depends(require_tenant),
    service: InstanceService = Depends(get_instance_service),
    audit_service: AuditService = Depends(get_audit_service),
):
    """Cancel all pending/running jobs for an instance.

    This is useful when an instance fails and the user wants to clear out
    any remaining pending jobs before deciding to retry or abandon the workflow.
    Works on instances in any state (including failed).
    """
    instance = await service.get_instance(instance_id)
    if not instance:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Instance with ID {instance_id} not found",
        )

    await validate_organization_access(str(instance.organization_id), user)

    await _audit_instance_action(
        audit_service,
        user,
        AuditAction.CANCEL,
        instance,
        metadata={"scope": "all_jobs"},
        severity=AuditSeverity.WARNING,
    )

    logger.info(
        f"All jobs for instance {instance_id} cancelled "
        f"by user {user.get('id')} via API"
    )

    return await service.cancel_all_jobs_for_instance(instance_id)


class ApprovalRequest(BaseModel):
    """Request body for approving or rejecting a step."""

    approved: bool = True
    comment: Optional[str] = None


class ApprovalResponse(BaseModel):
    """Response after approving or rejecting a step."""

    instance_id: UUID
    step_id: str
    approved: bool
    status: str
    message: str


class TriggerResponse(BaseModel):
    """Response after triggering a manual step."""

    instance_id: UUID
    step_id: str
    status: str
    message: str


@router.post("/{instance_id}/approve", response_model=ApprovalResponse)
async def approve_step(
    instance_id: UUID = Path(...),
    request: ApprovalRequest = ApprovalRequest(),
    user: CurrentUser = Depends(require_tenant),
    service: InstanceService = Depends(get_instance_service),
    audit_service: AuditService = Depends(get_audit_service),
    notifier=Depends(get_notifier),
    session: AsyncSession = Depends(get_db_session),
):
    """Approve or reject a step waiting for approval. Approved continues the workflow; rejected fails it."""
    instance = await service.get_instance(instance_id)
    if not instance:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Instance with ID {instance_id} not found",
        )

    await validate_organization_access(str(instance.organization_id), user)

    if instance.status != "waiting_for_approval":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Instance is not waiting for approval. Current status: {instance.status}",
        )

    pending_approval = instance.output_data.get("pending_approval", {})
    step_id = pending_approval.get("step_id")
    if not step_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No pending approval step found",
        )

    action = AuditAction.APPROVE if request.approved else AuditAction.REJECT
    await _audit_instance_action(
        audit_service,
        user,
        action,
        instance,
        resource_type=ResourceType.INSTANCE_STEP,
        metadata={"step_id": step_id, "comment": request.comment},
    )

    logger.info(
        f"Instance {instance_id} step {step_id} "
        f"{'approved' if request.approved else 'rejected'} "
        f"by user {user.get('id')} via API"
    )

    try:
        result = await service.process_approval(
            instance_id=instance_id,
            step_id=step_id,
            approved=request.approved,
            approved_by=UUID(user.get("id")) if user.get("id") else None,
            comment=request.comment,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=safe_error_message(e))

    # Refresh instance so announce uses the post-transition status.
    refreshed = await service.get_instance(instance_id)
    announce_instance = refreshed or instance
    # Reject transitions to FAILED; approve resumes → PROCESSING.
    action_type = "failed" if not request.approved else "processing_started"
    await notifier.announce_state_change(
        instance=announce_instance,
        action_type=action_type,
        step_id=step_id,
        session=session,
    )

    return ApprovalResponse(
        instance_id=instance_id,
        step_id=step_id,
        approved=request.approved,
        status=result.status if hasattr(result, "status") else "processed",
        message="Approved" if request.approved else "Rejected",
    )


@router.post(
    "/{instance_id}/step_executions/{step_id}/trigger", response_model=TriggerResponse
)
async def trigger_step(
    instance_id: UUID = Path(...),
    step_id: str = Path(..., description="Step ID to trigger"),
    user: CurrentUser = Depends(require_tenant),
    service: InstanceService = Depends(get_instance_service),
    audit_service: AuditService = Depends(get_audit_service),
    notifier=Depends(get_notifier),
    session: AsyncSession = Depends(get_db_session),
):
    """Trigger a step waiting for manual trigger, resuming execution."""
    instance = await service.get_instance(instance_id)
    if not instance:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Instance with ID {instance_id} not found",
        )

    await validate_organization_access(str(instance.organization_id), user)

    if instance.status != "waiting_for_manual_trigger":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Instance is not waiting for manual trigger. Current status: {instance.status}",
        )

    pending_trigger = instance.output_data.get("pending_trigger", {})
    pending_step_id = pending_trigger.get("step_id")
    if not pending_step_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No pending trigger step found",
        )

    if pending_step_id != step_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Step {step_id} is not the pending trigger step (expected {pending_step_id})",
        )

    await _audit_instance_action(
        audit_service,
        user,
        AuditAction.TRIGGER,
        instance,
        resource_type=ResourceType.INSTANCE_STEP,
        metadata={"step_id": step_id},
    )

    logger.info(
        f"Instance {instance_id} step {step_id} manually triggered "
        f"by user {user.get('id')} via API"
    )

    try:
        result = await service.trigger_manual_step(
            instance_id=instance_id,
            step_id=step_id,
            triggered_by=UUID(user.get("id")) if user.get("id") else None,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=safe_error_message(e))

    refreshed = await service.get_instance(instance_id)
    announce_instance = refreshed or instance
    await notifier.announce_state_change(
        instance=announce_instance,
        action_type="processing_started",
        step_id=step_id,
        session=session,
    )

    return TriggerResponse(
        instance_id=instance_id,
        step_id=step_id,
        status=result.status if hasattr(result, "status") else "triggered",
        message="Step triggered successfully",
    )


@router.post("/step_executions/{job_id}/retry", response_model=StepExecutionResponse)
async def retry_job(
    job_id: UUID = Path(...),
    user: CurrentUser = Depends(require_tenant),
    service: InstanceService = Depends(get_instance_service),
    audit_service: AuditService = Depends(get_audit_service),
):
    """Retry a failed job execution."""
    job = await service.get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job with ID {job_id} not found",
        )

    instance = await service.get_instance(job.instance_id)
    if not instance:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Instance with ID {job.instance_id} not found",
        )

    await validate_organization_access(str(instance.organization_id), user)

    await _audit_instance_action(
        audit_service,
        user,
        AuditAction.RETRY,
        instance,
        resource_type=ResourceType.INSTANCE_STEP,
        metadata={"step_id": job.step_id, "job_id": str(job_id)},
    )

    logger.info(
        f"Job {job_id} (step={job.step_id}, instance={job.instance_id}) "
        f"retried by user {user.get('id')} via API"
    )

    try:
        return await service.retry_job(job_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=safe_error_message(e))


@router.post(
    "/step_executions/{job_id}/rerun-only", response_model=StepExecutionResponse
)
async def rerun_job_only(
    job_id: UUID = Path(...),
    user: CurrentUser = Depends(require_tenant),
    service: InstanceService = Depends(get_instance_service),
    audit_service: AuditService = Depends(get_audit_service),
):
    """Rerun a single job without clearing downstream step results."""
    job = await service.get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job with ID {job_id} not found",
        )

    instance = await service.get_instance(job.instance_id)
    if not instance:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Instance with ID {job.instance_id} not found",
        )

    await validate_organization_access(str(instance.organization_id), user)

    await _audit_instance_action(
        audit_service,
        user,
        AuditAction.RERUN,
        instance,
        resource_type=ResourceType.INSTANCE_STEP,
        metadata={"step_id": job.step_id, "job_id": str(job_id), "mode": "rerun_only"},
    )

    logger.info(
        f"Job {job_id} (step={job.step_id}, instance={job.instance_id}) "
        f"rerun-only by user {user.get('id')} via API"
    )

    try:
        return await service.rerun_job_only(job_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=safe_error_message(e))


@router.post(
    "/step_executions/{job_id}/rerun-and-continue", response_model=StepExecutionResponse
)
async def rerun_and_continue(
    job_id: UUID = Path(...),
    user: CurrentUser = Depends(require_tenant),
    service: InstanceService = Depends(get_instance_service),
    audit_service: AuditService = Depends(get_audit_service),
):
    """Rerun a job and all downstream dependent steps; upstream steps use cached results."""
    job = await service.get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job with ID {job_id} not found",
        )

    instance = await service.get_instance(job.instance_id)
    if not instance:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Instance with ID {job.instance_id} not found",
        )

    await validate_organization_access(str(instance.organization_id), user)

    await _audit_instance_action(
        audit_service,
        user,
        AuditAction.RERUN,
        instance,
        resource_type=ResourceType.INSTANCE_STEP,
        metadata={
            "step_id": job.step_id,
            "job_id": str(job_id),
            "mode": "rerun_and_continue",
        },
    )

    logger.info(
        f"Job {job_id} (step={job.step_id}, instance={job.instance_id}) "
        f"rerun-and-continue by user {user.get('id')} via API"
    )

    try:
        return await service.rerun_and_continue(job_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=safe_error_message(e))


@router.post(
    "/{instance_id}/step_executions/{step_id}/rerun",
    response_model=StepExecutionResponse,
)
async def rerun_step_only(
    instance_id: UUID = Path(...),
    step_id: str = Path(...),
    user: CurrentUser = Depends(require_tenant),
    service: InstanceService = Depends(get_instance_service),
    audit_service: AuditService = Depends(get_audit_service),
):
    """Rerun all jobs for a step without triggering downstream steps (useful for iteration steps)."""
    instance = await service.get_instance(instance_id)
    if not instance:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Instance with ID {instance_id} not found",
        )

    await validate_organization_access(str(instance.organization_id), user)

    await _audit_instance_action(
        audit_service,
        user,
        AuditAction.RERUN,
        instance,
        resource_type=ResourceType.INSTANCE_STEP,
        metadata={"step_id": step_id, "mode": "rerun_step_only"},
    )

    logger.info(
        f"Step {step_id} for instance {instance_id} "
        f"rerun-step-only by user {user.get('id')} via API"
    )

    try:
        return await service.rerun_step_only(instance_id, step_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=safe_error_message(e))


class UpdateJobResultRequest(BaseModel):
    """Request body for updating a job's result data."""

    result: Dict[str, Any]


@router.patch("/step_executions/{job_id}/result", response_model=StepExecutionResponse)
async def update_job_result(
    job_id: UUID = Path(...),
    request: UpdateJobResultRequest = Body(...),
    user: CurrentUser = Depends(require_tenant),
    service: InstanceService = Depends(get_instance_service),
    audit_service: AuditService = Depends(get_audit_service),
):
    job = await service.get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job with ID {job_id} not found",
        )

    instance = await service.get_instance(job.instance_id)
    if not instance:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Instance with ID {job.instance_id} not found",
        )

    await validate_organization_access(str(instance.organization_id), user)

    await _audit_instance_action(
        audit_service,
        user,
        AuditAction.UPDATE,
        instance,
        resource_type=ResourceType.INSTANCE_STEP,
        metadata={
            "step_id": job.step_id,
            "job_id": str(job_id),
            "action": "edit_result",
        },
    )

    logger.info(
        f"Job {job_id} (step={job.step_id}, instance={job.instance_id}) "
        f"result updated by user {user.get('id')} via API"
    )

    try:
        return await service.update_job_result(job_id, request.result)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=safe_error_message(e))


@router.get(
    "/{instance_id}/step_executions", response_model=List[StepExecutionResponse]
)
async def list_jobs_for_instance(
    instance_id: UUID = Path(...),
    user: CurrentUser = Depends(get_current_user),
    service: InstanceService = Depends(get_instance_service),
):
    instance = await service.get_instance(instance_id)
    if not instance:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Instance with ID {instance_id} not found",
        )

    await validate_organization_access(str(instance.organization_id), user)
    return await service.list_jobs_for_instance(instance_id)


@router.post("/{instance_id}/run-step/{step_id}", response_model=StepExecutionResponse)
async def run_stopped_step(
    instance_id: UUID = Path(...),
    step_id: str = Path(..., description="Step ID to run"),
    user: CurrentUser = Depends(require_tenant),
    service: InstanceService = Depends(get_instance_service),
    audit_service: AuditService = Depends(get_audit_service),
    notifier=Depends(get_notifier),
    session: AsyncSession = Depends(get_db_session),
):
    """Run a stopped or pending step, using results from previously completed steps."""
    instance = await service.get_instance(instance_id)
    if not instance:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Instance with ID {instance_id} not found",
        )

    await validate_organization_access(str(instance.organization_id), user)

    await _audit_instance_action(
        audit_service,
        user,
        AuditAction.TRIGGER,
        instance,
        resource_type=ResourceType.INSTANCE_STEP,
        metadata={"step_id": step_id, "mode": "run_stopped_step"},
    )

    logger.info(
        f"Stopped step {step_id} for instance {instance_id} "
        f"run by user {user.get('id')} via API"
    )

    try:
        result = await service.run_stopped_step(instance_id, step_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=safe_error_message(e))

    refreshed = await service.get_instance(instance_id)
    announce_instance = refreshed or instance
    await notifier.announce_state_change(
        instance=announce_instance,
        action_type="processing_started",
        step_id=step_id,
        session=session,
    )

    return result


@router.get("/{instance_id}/statistics", response_model=Dict[str, Any])
async def get_instance_statistics(
    instance_id: UUID = Path(...),
    user: CurrentUser = Depends(get_current_user),
    service: InstanceService = Depends(get_instance_service),
):
    instance = await service.get_instance(instance_id)
    if not instance:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Instance with ID {instance_id} not found",
        )

    await validate_organization_access(str(instance.organization_id), user)
    return await service.get_instance_statistics(instance_id)


class RegenerateResourcesRequest(BaseModel):
    """Request body for regenerating selected resources."""

    resource_ids: List[UUID]
    parameter_overrides: Dict[str, Any] = {}


@router.post(
    "/{instance_id}/step_executions/{step_id}/regenerate",
    response_model=StepExecutionResponse,
)
async def regenerate_resources(
    instance_id: UUID = Path(...),
    step_id: str = Path(..., description="Step ID containing resources to regenerate"),
    request: RegenerateResourcesRequest = Body(...),
    user: CurrentUser = Depends(require_tenant),
    service: InstanceService = Depends(get_instance_service),
    audit_service: AuditService = Depends(get_audit_service),
):
    """
    Regenerate selected resources from a step with new seeds.

    Deletes the selected resources and re-queues the step. When parameter_overrides
    include iteration context, params are passed directly to the worker (passthrough);
    otherwise the normal resolution pipeline runs.
    """
    instance = await service.get_instance(instance_id)
    if not instance:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Instance with ID {instance_id} not found",
        )

    await validate_organization_access(str(instance.organization_id), user)

    if not request.resource_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No resource IDs provided for regeneration",
        )

    await _audit_instance_action(
        audit_service,
        user,
        AuditAction.REGENERATE,
        instance,
        resource_type=ResourceType.INSTANCE_STEP,
        metadata={
            "step_id": step_id,
            "resource_count": len(request.resource_ids),
            "resource_ids": [str(r) for r in request.resource_ids],
        },
    )

    logger.info(
        f"Regenerating {len(request.resource_ids)} resources for step {step_id} "
        f"instance {instance_id} by user {user.get('id')} via API"
    )

    try:
        return await service.regenerate_resources(
            instance_id=instance_id,
            step_id=step_id,
            resource_ids=request.resource_ids,
            parameter_overrides=request.parameter_overrides or None,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=safe_error_message(e))


class RegenerateIterationRequest(BaseModel):
    """Request body for regenerating a single iteration."""

    iteration_index: int = Field(
        ..., ge=0, description="0-based iteration index to regenerate"
    )
    parameter_overrides: Dict[str, Any] = {}


@router.post(
    "/{instance_id}/step_executions/{step_id}/regenerate-iteration",
    response_model=StepExecutionResponse,
)
async def regenerate_iteration(
    instance_id: UUID = Path(...),
    step_id: str = Path(
        ..., description="Step ID containing the iteration to regenerate"
    ),
    request: RegenerateIterationRequest = Body(...),
    user: CurrentUser = Depends(require_tenant),
    service: InstanceService = Depends(get_instance_service),
    audit_service: AuditService = Depends(get_audit_service),
):
    """Regenerate a single iteration. Handles crash (0 files) and redo (replace existing) cases."""
    instance = await service.get_instance(instance_id)
    if not instance:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Instance with ID {instance_id} not found",
        )

    await validate_organization_access(str(instance.organization_id), user)

    await _audit_instance_action(
        audit_service,
        user,
        AuditAction.REGENERATE,
        instance,
        resource_type=ResourceType.INSTANCE_STEP,
        metadata={"step_id": step_id, "iteration_index": request.iteration_index},
    )

    logger.info(
        f"Regenerating iteration {request.iteration_index} for step {step_id} "
        f"instance {instance_id} by user {user.get('id')} via API"
    )

    try:
        return await service.regenerate_iteration(
            instance_id=instance_id,
            step_id=step_id,
            iteration_index=request.iteration_index,
            parameter_overrides=request.parameter_overrides or None,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=safe_error_message(e))


@router.post(
    "/{instance_id}/step_executions/{step_id}/upload",
    response_model=List[OrgFileResponse],
)
async def upload_files_to_step(
    instance_id: UUID = Path(..., description="Instance ID"),
    step_id: str = Path(..., description="Step ID (workflow step key)"),
    files: List[UploadFile] = File(..., description="Files to upload"),
    user: CurrentUser = Depends(require_tenant),
    service: InstanceService = Depends(get_instance_service),
    resource_service: OrgFileService = Depends(
        get_org_file_service
    ),
    step_execution_repo: StepExecutionRepository = Depends(
        get_step_execution_repository
    ),
    audit_service: AuditService = Depends(get_audit_service),
):
    """Upload files to a step's resource collection. Image thumbnails are generated automatically."""
    import mimetypes

    if not files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No files provided",
        )

    if len(files) > 10:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Maximum 10 files per upload",
        )

    org_id = user.get("org_id")
    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Organization ID not found in user token",
        )

    instance = await service.get_instance(instance_id)
    if not instance:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Instance {instance_id} not found",
        )

    if str(instance.organization_id) != org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this instance",
        )

    instance_step = await step_execution_repo.get_by_instance_and_key(
        instance_id, step_id
    )
    if not instance_step:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Step '{step_id}' not found for instance {instance_id}",
        )

    await _audit_instance_action(
        audit_service,
        user,
        AuditAction.UPLOAD,
        instance,
        resource_type=ResourceType.INSTANCE_STEP,
        metadata={
            "step_id": step_id,
            "file_count": len(files),
            "filenames": [f.filename for f in files if f.filename],
        },
    )

    created_resources = []
    for file in files:
        if not file or not file.filename:
            continue

        file_extension = ""
        ext_index = file.filename.rfind(".")
        if ext_index != -1:
            file_extension = file.filename[ext_index:]

        mime_type = file.content_type
        if not mime_type or mime_type == "application/octet-stream":
            guessed_type, _ = mimetypes.guess_type(file.filename or "")
            mime_type = guessed_type or "application/octet-stream"

        content = await file.read()
        file_size = len(content)

        from io import BytesIO

        file_stream = BytesIO(content)

        try:
            resource = await resource_service.upload_file_to_step(
                instance_id=instance_id,
                step_key=step_id,
                organization_id=UUID(org_id),
                file_content=file_stream,
                file_size=file_size,
                mime_type=mime_type,
                file_extension=file_extension,
                display_name=file.filename or "uploaded_file",
                job_execution_id=None,  # User uploads don't need job association
                instance_step_id=instance_step.id,
            )
            created_resources.append(resource)

            logger.info(
                f"File uploaded to step: name={file.filename}, size={file_size}, "
                f"instance={instance_id}, step={step_id}, user={user.get('id')}"
            )
        except Exception as e:
            logger.exception(f"Failed to upload file {file.filename}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to upload file",
            )

    if not created_resources:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No files were successfully uploaded",
        )

    # Empty API_BASE_URL produces relative URLs - works behind a reverse proxy
    api_base_url = settings.API_BASE_URL
    return [
        OrgFileResponse.from_domain(resource, api_base_url)
        for resource in created_resources
    ]


class AddFilesFromLibraryRequest(BaseModel):
    """Request body for adding library files to a step."""

    resource_ids: List[UUID]


@router.post(
    "/{instance_id}/step_executions/{step_id}/add-from-library",
    response_model=List[OrgFileResponse],
)
async def add_files_from_library(
    instance_id: UUID = Path(..., description="Instance ID"),
    step_id: str = Path(..., description="Step ID (workflow step key)"),
    request: AddFilesFromLibraryRequest = Body(...),
    user: CurrentUser = Depends(require_tenant),
    service: InstanceService = Depends(get_instance_service),
    resource_service: OrgFileService = Depends(
        get_org_file_service
    ),
    step_execution_repo: StepExecutionRepository = Depends(
        get_step_execution_repository
    ),
    audit_service: AuditService = Depends(get_audit_service),
):
    """Associate existing library files with a step. Files are not duplicated on disk."""
    if not request.resource_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No resource IDs provided",
        )

    if len(request.resource_ids) > 10:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Maximum 10 files per request",
        )

    org_id = user.get("org_id")
    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Organization ID not found in user token",
        )

    instance = await service.get_instance(instance_id)
    if not instance:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Instance {instance_id} not found",
        )

    if str(instance.organization_id) != org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this instance",
        )

    instance_step = await step_execution_repo.get_by_instance_and_key(
        instance_id, step_id
    )
    if not instance_step:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Step '{step_id}' not found for instance {instance_id}",
        )

    await _audit_instance_action(
        audit_service,
        user,
        AuditAction.UPLOAD,
        instance,
        resource_type=ResourceType.INSTANCE_STEP,
        metadata={
            "step_id": step_id,
            "source": "library",
            "resource_count": len(request.resource_ids),
            "resource_ids": [str(r) for r in request.resource_ids],
        },
    )

    created_resources = []
    for resource_id in request.resource_ids:
        try:
            resource = await resource_service.add_library_file_to_step(
                source_resource_id=resource_id,
                instance_id=instance_id,
                instance_step_id=instance_step.id,
                organization_id=UUID(org_id),
            )
            created_resources.append(resource)

            logger.info(
                f"Library file added to step: resource_id={resource_id}, "
                f"instance={instance_id}, step={step_id}, user={user.get('id')}"
            )
        except Exception as e:
            logger.exception(f"Failed to add library file {resource_id}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to add library file",
            )

    if not created_resources:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No files were successfully added",
        )

    # Empty API_BASE_URL produces relative URLs - works behind a reverse proxy
    api_base_url = settings.API_BASE_URL
    return [
        OrgFileResponse.from_domain(resource, api_base_url)
        for resource in created_resources
    ]
