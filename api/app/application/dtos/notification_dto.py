# api/app/application/dtos/notification_dto.py

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel

from app.domain.notification.models import (
    ChannelType,
    Notification,
    NotificationPriority,
    NotificationStatus,
)


class NotificationBase(BaseModel):
    recipient_id: UUID
    organization_id: UUID


class NotificationCreate(NotificationBase):
    created_by: UUID
    channel_type: ChannelType = ChannelType.IN_APP
    channel_id: Optional[UUID] = None
    message: str
    title: Optional[str] = None
    priority: NotificationPriority = NotificationPriority.MEDIUM
    tags: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None


class NotificationUpdate(BaseModel):
    status: Optional[NotificationStatus] = None
    client_metadata: Optional[Dict[str, Any]] = None


class NotificationResponse(BaseModel):
    id: UUID
    organization_id: UUID
    recipient_id: UUID
    created_by: UUID
    channel_type: ChannelType
    channel_id: Optional[UUID] = None
    title: Optional[str] = None
    message: str
    priority: NotificationPriority
    status: NotificationStatus
    sent_at: Optional[datetime] = None
    read_at: Optional[datetime] = None
    tags: List[str]
    client_metadata: Dict[str, Any]
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @classmethod
    def from_domain(cls, notification: Notification) -> "NotificationResponse":
        return cls(
            id=notification.id,
            organization_id=notification.organization_id,
            recipient_id=notification.recipient_id,
            created_by=notification.created_by,
            channel_type=notification.channel_type,
            channel_id=notification.channel_id,
            title=notification.title,
            message=notification.message,
            priority=notification.priority,
            status=notification.status,
            sent_at=notification.sent_at,
            read_at=notification.read_at,
            tags=notification.tags,
            client_metadata=notification.client_metadata,
            created_at=notification.created_at,
            updated_at=notification.updated_at,
        )
