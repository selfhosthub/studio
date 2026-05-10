# api/app/domain/notification/models.py

import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import Field, field_validator

from app.domain.common.base_entity import AggregateRoot
from app.domain.common.events import DomainEvent
from app.domain.common.exceptions import InvalidStateTransition


class NotificationStatus(str, Enum):
    PENDING = "pending"
    SENT = "sent"


class ChannelType(str, Enum):
    EMAIL = "email"
    SMS = "sms"
    IN_APP = "in_app"
    PUSH = "push"
    SLACK = "slack"
    WEBHOOK = "webhook"


class NotificationPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ChannelStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class NotificationCreated(DomainEvent):
    event_type: str = "notification.created"
    aggregate_id: uuid.UUID
    aggregate_type: str = "notification"
    channel_type: ChannelType
    recipient_id: uuid.UUID


class NotificationSent(DomainEvent):
    event_type: str = "notification.sent"
    aggregate_id: uuid.UUID
    aggregate_type: str = "notification"


class NotificationRead(DomainEvent):
    event_type: str = "notification.read"
    aggregate_id: uuid.UUID
    aggregate_type: str = "notification"
    recipient_id: uuid.UUID


class NotificationChannelActivated(DomainEvent):
    event_type: str = "notification_channel.activated"
    aggregate_id: uuid.UUID
    aggregate_type: str = "notification_channel"
    organization_id: uuid.UUID
    channel_type: ChannelType


class NotificationChannelDeactivated(DomainEvent):
    event_type: str = "notification_channel.deactivated"
    aggregate_id: uuid.UUID
    aggregate_type: str = "notification_channel"
    organization_id: uuid.UUID
    channel_type: ChannelType


class Notification(AggregateRoot):
    """A message sent through a communication channel. Transaction log, not a state machine."""

    recipient_id: uuid.UUID
    organization_id: uuid.UUID
    created_by: uuid.UUID

    channel_type: ChannelType
    channel_id: Optional[uuid.UUID] = None

    title: Optional[str] = Field(None, max_length=255)
    message: str

    priority: NotificationPriority = NotificationPriority.MEDIUM
    status: NotificationStatus = NotificationStatus.PENDING

    sent_at: Optional[datetime] = None
    read_at: Optional[datetime] = None

    tags: List[str] = Field(default_factory=list)
    client_metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("status", mode="before")
    @classmethod
    def convert_status_to_enum(cls, v):
        if isinstance(v, str) and not isinstance(v, NotificationStatus):
            return NotificationStatus(v)
        return v

    @classmethod
    def create(
        cls,
        recipient_id: uuid.UUID,
        organization_id: uuid.UUID,
        created_by: uuid.UUID,
        channel_type: ChannelType,
        message: str,
        title: Optional[str] = None,
        priority: NotificationPriority = NotificationPriority.MEDIUM,
        tags: Optional[List[str]] = None,
        client_metadata: Optional[Dict[str, Any]] = None,
        channel_id: Optional[uuid.UUID] = None,
    ) -> "Notification":
        notification = cls(
            recipient_id=recipient_id,
            organization_id=organization_id,
            created_by=created_by,
            channel_type=channel_type,
            message=message,
            title=title,
            priority=priority,
            tags=tags or [],
            client_metadata=client_metadata or {},
            channel_id=channel_id,
        )

        notification.add_event(
            NotificationCreated(
                aggregate_id=notification.id,
                aggregate_type="notification",
                channel_type=channel_type,
                recipient_id=recipient_id,
            )
        )

        return notification

    def mark_sent(self) -> None:
        self.status = NotificationStatus.SENT
        self.sent_at = datetime.now(UTC)

        self.add_event(
            NotificationSent(
                aggregate_id=self.id,
                aggregate_type="notification",
            )
        )

    def mark_read(self) -> None:
        self.read_at = datetime.now(UTC)

        self.add_event(
            NotificationRead(
                aggregate_id=self.id,
                aggregate_type="notification",
                recipient_id=self.recipient_id,
            )
        )


class NotificationChannel(AggregateRoot):
    """A configured communication channel for sending notifications."""

    organization_id: uuid.UUID
    channel_type: ChannelType
    name: str
    configuration: Dict[str, Any] = Field(default_factory=dict)
    status: ChannelStatus = ChannelStatus.ACTIVE

    @field_validator("status", mode="before")
    @classmethod
    def convert_status_to_enum(cls, v):
        if isinstance(v, str) and not isinstance(v, ChannelStatus):
            return ChannelStatus(v)
        return v

    @classmethod
    def create(
        cls,
        organization_id: uuid.UUID,
        channel_type: ChannelType,
        name: str,
        configuration: Optional[Dict[str, Any]] = None,
    ) -> "NotificationChannel":
        return cls(
            organization_id=organization_id,
            channel_type=channel_type,
            name=name,
            configuration=configuration or {},
        )

    def activate(self) -> None:
        if self.status == ChannelStatus.ACTIVE:
            raise InvalidStateTransition(
                message="Notification channel is already active",
                code="CHANNEL_ALREADY_ACTIVE",
                context={
                    "channel_id": str(self.id),
                    "current_status": self.status.value,
                },
            )

        self.status = ChannelStatus.ACTIVE
        self.updated_at = datetime.now(UTC)

        self.add_event(
            NotificationChannelActivated(
                aggregate_id=self.id,
                aggregate_type="notification_channel",
                organization_id=self.organization_id,
                channel_type=self.channel_type,
            )
        )

    def deactivate(self) -> None:
        if self.status == ChannelStatus.INACTIVE:
            raise InvalidStateTransition(
                message="Notification channel is already inactive",
                code="CHANNEL_ALREADY_INACTIVE",
                context={
                    "channel_id": str(self.id),
                    "current_status": self.status.value,
                },
            )

        self.status = ChannelStatus.INACTIVE
        self.updated_at = datetime.now(UTC)

        self.add_event(
            NotificationChannelDeactivated(
                aggregate_id=self.id,
                aggregate_type="notification_channel",
                organization_id=self.organization_id,
                channel_type=self.channel_type,
            )
        )

    def update_configuration(self, configuration: Dict[str, Any]) -> None:
        self.configuration = configuration
