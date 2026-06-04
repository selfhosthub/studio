# api/app/application/services/notification_service.py

import uuid
from typing import List, Optional

from app.application.dtos.notification_dto import (
    NotificationCreate,
    NotificationResponse,
)
from app.domain.common.exceptions import EntityNotFoundError
from app.domain.notification.models import Notification
from app.domain.notification.repository import NotificationRepository
from app.infrastructure.messaging.event_bus import EventBus


class NotificationService:
    """Application service for notification management."""

    def __init__(
        self,
        notification_repository: NotificationRepository,
        event_bus: EventBus,
    ):
        self.notification_repository = notification_repository
        self.event_bus = event_bus

    async def create_notification(
        self, command: NotificationCreate
    ) -> NotificationResponse:
        notification = Notification.create(
            recipient_id=command.recipient_id,
            organization_id=command.organization_id,
            created_by=command.created_by,
            channel_type=command.channel_type,
            channel_id=command.channel_id,
            message=command.message,
            title=command.title,
            priority=command.priority,
            tags=command.tags or [],
            client_metadata=command.metadata or {},
        )

        await self._publish_events(notification)
        notification = await self.notification_repository.create(notification)

        return NotificationResponse.from_domain(notification)

    async def mark_sent(self, notification_id: uuid.UUID) -> NotificationResponse:
        notification = await self._get_notification_or_raise(notification_id)

        notification.mark_sent()

        await self._publish_events(notification)
        notification = await self.notification_repository.update(notification)

        return NotificationResponse.from_domain(notification)

    async def mark_read(self, notification_id: uuid.UUID) -> NotificationResponse:
        notification = await self._get_notification_or_raise(notification_id)

        notification.mark_read()

        await self._publish_events(notification)
        notification = await self.notification_repository.update(notification)

        return NotificationResponse.from_domain(notification)

    async def mark_all_read(self, recipient_id: uuid.UUID) -> int:
        return await self.notification_repository.mark_all_read(recipient_id)

    async def get_notification(
        self, notification_id: uuid.UUID
    ) -> Optional[NotificationResponse]:
        notification = await self.notification_repository.get_by_id(notification_id)
        if notification:
            return NotificationResponse.from_domain(notification)
        return None

    async def list_notifications_by_recipient(
        self,
        recipient_id: uuid.UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> List[NotificationResponse]:
        notifications = await self.notification_repository.list_by_recipient(
            recipient_id=recipient_id,
            skip=skip,
            limit=limit,
        )

        return [NotificationResponse.from_domain(n) for n in notifications]

    async def list_notifications_by_organization(
        self,
        organization_id: uuid.UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> List[NotificationResponse]:
        notifications = await self.notification_repository.list_by_organization(
            organization_id=organization_id,
            skip=skip,
            limit=limit,
        )

        return [NotificationResponse.from_domain(n) for n in notifications]

    async def list_pending_notifications(
        self,
        organization_id: uuid.UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> List[NotificationResponse]:
        """List pending notifications ready to send."""
        notifications = await self.notification_repository.find_pending_notifications(
            organization_id=organization_id,
            skip=skip,
            limit=limit,
        )

        return [NotificationResponse.from_domain(n) for n in notifications]

    async def _get_notification_or_raise(
        self, notification_id: uuid.UUID
    ) -> Notification:
        """Fetch the notification or raise if not found."""
        notification = await self.notification_repository.get_by_id(notification_id)

        if not notification:
            raise EntityNotFoundError(
                entity_type="Notification",
                entity_id=str(notification_id),
            )

        return notification

    async def _publish_events(self, notification: Notification) -> None:
        """Publish domain events from notification aggregate."""
        events = notification.clear_events()
        for event in events:
            await self.event_bus.publish(event)
