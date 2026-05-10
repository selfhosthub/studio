# api/app/presentation/api/audit.py

"""Audit log API.

Visibility: super_admin → all events (org + system); admin → own org only; user → no access.
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from app.config.settings import settings
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.application.services.audit_service import AuditService
from app.domain.audit.models import AuditActorType, AuditEvent
from app.domain.common.value_objects import Role
from app.presentation.api.dependencies import (
    CurrentUser,
    get_audit_service,
    require_admin,
    require_super_admin,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Audit Logs"])


class AuditEventResponse(BaseModel):
    id: str
    organization_id: Optional[str] = None
    actor_id: str
    actor_type: str
    action: str
    resource_type: str
    resource_id: Optional[str] = None
    resource_name: Optional[str] = None
    severity: str
    category: str
    changes: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = {}
    status: str
    error_message: Optional[str] = None
    created_at: str

    @classmethod
    def from_domain(cls, event: AuditEvent) -> "AuditEventResponse":
        return cls(
            id=str(event.id),
            organization_id=(
                str(event.organization_id) if event.organization_id else None
            ),
            actor_id=str(event.actor_id),
            actor_type=(
                event.actor_type.value
                if hasattr(event.actor_type, "value")
                else str(event.actor_type)
            ),
            action=(
                event.action.value
                if hasattr(event.action, "value")
                else str(event.action)
            ),
            resource_type=(
                event.resource_type.value
                if hasattr(event.resource_type, "value")
                else str(event.resource_type)
            ),
            resource_id=str(event.resource_id) if event.resource_id else None,
            resource_name=event.resource_name,
            severity=(
                event.severity.value
                if hasattr(event.severity, "value")
                else str(event.severity)
            ),
            category=(
                event.category.value
                if hasattr(event.category, "value")
                else str(event.category)
            ),
            changes=event.changes,
            metadata=event.metadata or {},
            status=(
                event.status.value
                if hasattr(event.status, "value")
                else str(event.status)
            ),
            error_message=event.error_message,
            created_at=event.created_at.isoformat(),
        )


class AuditEventListResponse(BaseModel):
    items: List[AuditEventResponse]
    total: int
    skip: int
    limit: int


@router.get(
    "/",
    response_model=AuditEventListResponse,
    summary="List audit events",
    description="List audit events with filters. Admins see their org's events, super_admins see all.",
)
async def list_audit_events(
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(
        settings.API_PAGE_LIMIT_MEDIUM,
        ge=1,
        le=settings.API_PAGE_MAX,
        description="Maximum records to return",
    ),
    organization_id: Optional[str] = Query(
        None, description="Filter by organization (super_admin only)"
    ),
    resource_type: Optional[str] = Query(None, description="Filter by resource type"),
    action: Optional[str] = Query(None, description="Filter by action"),
    severity: Optional[str] = Query(
        None, description="Filter by severity (info, warning, critical)"
    ),
    category: Optional[str] = Query(
        None, description="Filter by category (security, configuration, access, audit)"
    ),
    actor_id: Optional[str] = Query(None, description="Filter by actor ID"),
    start_date: Optional[str] = Query(
        None, description="Filter by start date (ISO8601)"
    ),
    end_date: Optional[str] = Query(None, description="Filter by end date (ISO8601)"),
    include_system_events: bool = Query(
        True, description="Include system-level events (super_admin only)"
    ),
    current_user: CurrentUser = Depends(require_admin),
    audit_service: AuditService = Depends(get_audit_service),
) -> AuditEventListResponse:
    """admin → own org only; super_admin → all + system events."""
    user_role = current_user.get("role", "user")
    user_org_id = current_user.get("org_id")
    is_super_admin = user_role == Role.SUPER_ADMIN

    parsed_start_date = None
    parsed_end_date = None
    if start_date:
        try:
            parsed_start_date = datetime.fromisoformat(
                start_date.replace("Z", "+00:00")
            )
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid start_date format. Use ISO8601.",
            )
    if end_date:
        try:
            parsed_end_date = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid end_date format. Use ISO8601.",
            )

    parsed_actor_id = None
    if actor_id:
        try:
            parsed_actor_id = UUID(actor_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid actor_id format.",
            )

    if is_super_admin:
        parsed_org_id = None
        if organization_id:
            try:
                parsed_org_id = UUID(organization_id)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid organization_id format.",
                )

        events = await audit_service.list_all_events(
            skip=skip,
            limit=limit,
            organization_id=parsed_org_id,
            resource_type=resource_type,
            action=action,
            severity=severity,
            category=category,
            actor_id=parsed_actor_id,
            start_date=parsed_start_date,
            end_date=parsed_end_date,
            include_system_events=include_system_events,
        )

        total = await audit_service.count_events(
            organization_id=parsed_org_id,
            resource_type=resource_type,
            severity=severity,
            category=category,
            start_date=parsed_start_date,
            end_date=parsed_end_date,
        )

    else:
        if not user_org_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User does not belong to an organization.",
            )

        org_uuid = UUID(user_org_id)

        events = await audit_service.list_organization_events(
            organization_id=org_uuid,
            skip=skip,
            limit=limit,
            resource_type=resource_type,
            action=action,
            severity=severity,
            category=category,
            actor_id=parsed_actor_id,
            start_date=parsed_start_date,
            end_date=parsed_end_date,
        )

        total = await audit_service.count_events(
            organization_id=org_uuid,
            resource_type=resource_type,
            severity=severity,
            category=category,
            start_date=parsed_start_date,
            end_date=parsed_end_date,
        )

    return AuditEventListResponse(
        items=[AuditEventResponse.from_domain(e) for e in events],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/system",
    response_model=AuditEventListResponse,
    summary="List system-level audit events",
    description="List system-level audit events (providers, services, packages). Super admin only.",
)
async def list_system_events(
    skip: int = Query(0, ge=0),
    limit: int = Query(settings.API_PAGE_LIMIT_MEDIUM, ge=1, le=settings.API_PAGE_MAX),
    resource_type: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    actor_id: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    current_user: CurrentUser = Depends(require_super_admin),
    audit_service: AuditService = Depends(get_audit_service),
) -> AuditEventListResponse:
    """super_admin only. organization_id IS NULL events."""
    parsed_start_date = None
    parsed_end_date = None
    if start_date:
        try:
            parsed_start_date = datetime.fromisoformat(
                start_date.replace("Z", "+00:00")
            )
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid start_date format")
    if end_date:
        try:
            parsed_end_date = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid end_date format")

    parsed_actor_id = UUID(actor_id) if actor_id else None

    events = await audit_service.list_system_events(
        skip=skip,
        limit=limit,
        resource_type=resource_type,
        action=action,
        severity=severity,
        actor_id=parsed_actor_id,
        start_date=parsed_start_date,
        end_date=parsed_end_date,
    )

    # No specialized count method yet - approximate from page size
    total = len(events) if len(events) < limit else limit + skip + 1

    return AuditEventListResponse(
        items=[AuditEventResponse.from_domain(e) for e in events],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/resource/{resource_type}/{resource_id}",
    response_model=AuditEventListResponse,
    summary="Get resource history",
    description="Get audit history for a specific resource.",
)
async def get_resource_history(
    resource_type: str,
    resource_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(settings.API_PAGE_LIMIT_MEDIUM, ge=1, le=settings.API_PAGE_MAX),
    current_user: CurrentUser = Depends(require_admin),
    audit_service: AuditService = Depends(get_audit_service),
) -> AuditEventListResponse:
    """Audit history for a single resource."""
    try:
        parsed_resource_id = UUID(resource_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid resource_id format")

    user_role = current_user.get("role", "user")
    is_super_admin = user_role == Role.SUPER_ADMIN

    events = await audit_service.get_resource_history(
        resource_type=resource_type,
        resource_id=parsed_resource_id,
        skip=skip,
        limit=limit,
    )

    if not is_super_admin:
        user_org_id = current_user.get("org_id")
        if user_org_id:
            org_uuid = UUID(user_org_id)
            events = [
                e
                for e in events
                if e.organization_id == org_uuid or e.organization_id is None
            ]

    return AuditEventListResponse(
        items=[AuditEventResponse.from_domain(e) for e in events],
        total=len(events),
        skip=skip,
        limit=limit,
    )


@router.get(
    "/actor/{actor_id}",
    response_model=AuditEventListResponse,
    summary="Get actor history",
    description="Get all actions performed by a specific user.",
)
async def get_actor_history(
    actor_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(settings.API_PAGE_LIMIT_MEDIUM, ge=1, le=settings.API_PAGE_MAX),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    current_user: CurrentUser = Depends(require_admin),
    audit_service: AuditService = Depends(get_audit_service),
) -> AuditEventListResponse:
    """admin → actors in own org only; super_admin → any actor."""
    try:
        parsed_actor_id = UUID(actor_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid actor_id format")

    parsed_start_date = None
    parsed_end_date = None
    if start_date:
        try:
            parsed_start_date = datetime.fromisoformat(
                start_date.replace("Z", "+00:00")
            )
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid start_date format")
    if end_date:
        try:
            parsed_end_date = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid end_date format")

    user_role = current_user.get("role", "user")
    is_super_admin = user_role == Role.SUPER_ADMIN

    events = await audit_service.get_actor_history(
        actor_id=parsed_actor_id,
        skip=skip,
        limit=limit,
        start_date=parsed_start_date,
        end_date=parsed_end_date,
    )

    if not is_super_admin:
        user_org_id = current_user.get("org_id")
        if user_org_id:
            org_uuid = UUID(user_org_id)
            events = [
                e
                for e in events
                if e.organization_id == org_uuid or e.organization_id is None
            ]

    return AuditEventListResponse(
        items=[AuditEventResponse.from_domain(e) for e in events],
        total=len(events),
        skip=skip,
        limit=limit,
    )


def _event_to_siem_dict(event: AuditEvent) -> Dict[str, Any]:
    """Flat SIEM-compatible dict for one event."""
    return {
        "id": str(event.id),
        "timestamp": event.created_at.isoformat(),
        "organization_id": (
            str(event.organization_id) if event.organization_id else None
        ),
        "actor_id": str(event.actor_id),
        "actor_type": (
            event.actor_type.value
            if hasattr(event.actor_type, "value")
            else str(event.actor_type)
        ),
        "action": (
            event.action.value if hasattr(event.action, "value") else str(event.action)
        ),
        "resource_type": (
            event.resource_type.value
            if hasattr(event.resource_type, "value")
            else str(event.resource_type)
        ),
        "resource_id": str(event.resource_id) if event.resource_id else None,
        "resource_name": event.resource_name,
        "severity": (
            event.severity.value
            if hasattr(event.severity, "value")
            else str(event.severity)
        ),
        "category": (
            event.category.value
            if hasattr(event.category, "value")
            else str(event.category)
        ),
        "status": (
            event.status.value if hasattr(event.status, "value") else str(event.status)
        ),
        "error_message": event.error_message,
        "changes": event.changes,
        "metadata": event.metadata or {},
    }


@router.get(
    "/export",
    summary="Export audit events (SIEM)",
    description="Export audit events as JSONL for SIEM ingestion. Super admin only. Max 10,000 events per request.",
)
async def export_audit_events(
    start_date: Optional[str] = Query(None, description="Start date (ISO8601)"),
    end_date: Optional[str] = Query(None, description="End date (ISO8601)"),
    organization_id: Optional[str] = Query(None, description="Filter by organization"),
    resource_type: Optional[str] = Query(None, description="Filter by resource type"),
    action: Optional[str] = Query(None, description="Filter by action"),
    severity: Optional[str] = Query(None, description="Filter by severity"),
    category: Optional[str] = Query(None, description="Filter by category"),
    limit: int = Query(10000, ge=1, le=10000, description="Max events to export"),
    current_user: CurrentUser = Depends(require_super_admin),
    audit_service: AuditService = Depends(get_audit_service),
) -> StreamingResponse:
    """super_admin only. JSONL stream up to 10k events. Use start_date/end_date for incremental exports."""
    parsed_start_date = None
    parsed_end_date = None
    if start_date:
        try:
            parsed_start_date = datetime.fromisoformat(
                start_date.replace("Z", "+00:00")
            )
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid start_date format")
    if end_date:
        try:
            parsed_end_date = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid end_date format")

    parsed_org_id = None
    if organization_id:
        try:
            parsed_org_id = UUID(organization_id)
        except ValueError:
            raise HTTPException(
                status_code=400, detail="Invalid organization_id format"
            )

    events = await audit_service.list_all_events(
        skip=0,
        limit=limit,
        organization_id=parsed_org_id,
        resource_type=resource_type,
        action=action,
        severity=severity,
        category=category,
        start_date=parsed_start_date,
        end_date=parsed_end_date,
        include_system_events=True,
    )

    try:
        await audit_service.log_audit_log_viewed(
            actor_id=UUID(current_user["id"]),
            actor_type=AuditActorType.SUPER_ADMIN,
            organization_id=None,
            metadata={
                "export": True,
                "event_count": len(events),
                "filters": {
                    "start_date": start_date,
                    "end_date": end_date,
                    "organization_id": organization_id,
                },
            },
        )
    except Exception as e:
        logger.warning(f"Failed to log audit export: {e}")

    def generate_jsonl():
        for event in events:
            yield json.dumps(_event_to_siem_dict(event)) + "\n"

    return StreamingResponse(
        generate_jsonl(),
        media_type="application/x-ndjson",
        headers={
            "Content-Disposition": f"attachment; filename=audit_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl",
        },
    )
