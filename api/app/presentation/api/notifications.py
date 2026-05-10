# api/app/presentation/api/notifications.py

"""Notification API endpoints."""

from typing import List
from uuid import UUID

from app.config.settings import settings
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.application.dtos.notification_dto import (
    NotificationCreate,
    NotificationResponse,
)
from app.application.services.notification_service import NotificationService
from app.domain.common.value_objects import Role
from app.presentation.api.dependencies import (
    CurrentUser,
    get_current_user,
    get_notification_service,
)

router = APIRouter()


@router.post("/notifications/", response_model=NotificationResponse)
async def create_notification(
    request: NotificationCreate,
    user: CurrentUser = Depends(get_current_user),
    service: NotificationService = Depends(get_notification_service),
) -> NotificationResponse:
    """Create a new notification."""
    raw_org_id = user.get("org_id")
    if not raw_org_id or request.organization_id != UUID(raw_org_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Access denied to this organization"
        )

    return await service.create_notification(request)


@router.get("/notifications/{notification_id}", response_model=NotificationResponse)
async def get_notification(
    notification_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    service: NotificationService = Depends(get_notification_service),
) -> NotificationResponse:
    """Get a notification by ID."""
    notification = await service.get_notification(notification_id)

    if not notification:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")

    user_id = UUID(user["id"])
    user_role = user.get("role", "user")

    if user_role not in ["super_admin"] and notification.organization_id != UUID(
        user.get("org_id", "")
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Access denied to this organization"
        )

    if user_role == Role.USER and notification.recipient_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    return notification


@router.get(
    "/notifications/recipient/{recipient_id}", response_model=List[NotificationResponse]
)
async def list_notifications_by_recipient(
    recipient_id: UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(settings.API_PAGE_LIMIT_DEFAULT, ge=1, le=settings.API_PAGE_MAX),
    user: CurrentUser = Depends(get_current_user),
    service: NotificationService = Depends(get_notification_service),
) -> List[NotificationResponse]:
    """List notifications for a recipient."""
    user_id = UUID(user["id"])
    user_role = user.get("role", "user")

    if user_role == Role.USER and recipient_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    return await service.list_notifications_by_recipient(
        recipient_id=recipient_id,
        skip=skip,
        limit=limit,
    )


@router.patch(
    "/notifications/{notification_id}/read", response_model=NotificationResponse
)
async def mark_notification_as_read(
    notification_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    service: NotificationService = Depends(get_notification_service),
) -> NotificationResponse:
    """Mark a notification as read."""
    notification = await service.get_notification(notification_id)

    if not notification:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")

    user_id = UUID(user["id"])
    user_role = user.get("role", "user")

    if user_role == Role.USER and notification.recipient_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    return await service.mark_read(notification_id)


@router.patch("/notifications/recipient/{recipient_id}/read-all")
async def mark_all_notifications_as_read(
    recipient_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    service: NotificationService = Depends(get_notification_service),
) -> dict:
    """Mark all notifications as read for a recipient."""
    user_id = UUID(user["id"])
    user_role = user.get("role", "user")

    if user_role == Role.USER and recipient_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    count = await service.mark_all_read(recipient_id)
    return {"count": count}
