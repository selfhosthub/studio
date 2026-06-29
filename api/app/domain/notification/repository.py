# api/app/domain/notification/repository.py

import uuid
from abc import ABC, abstractmethod
from typing import List, Optional

from app.domain.notification.models import Notification


class NotificationRepository(ABC):
    """Persistence operations for Notification aggregates."""

    @abstractmethod
    async def create(self, notification: Notification) -> Notification: ...

    @abstractmethod
    async def update(self, notification: Notification) -> Notification: ...

    @abstractmethod
    async def get_by_id(self, notification_id: uuid.UUID) -> Optional[Notification]: ...

    @abstractmethod
    async def find_pending_notifications(
        self,
        organization_id: uuid.UUID,
        skip: int,
        limit: int,
    ) -> List[Notification]:
        """Pending notifications ready to send (delivery-processing query)."""

    @abstractmethod
    async def list_by_recipient(
        self,
        recipient_id: uuid.UUID,
        skip: int,
        limit: int,
    ) -> List[Notification]: ...

    @abstractmethod
    async def list_by_organization(
        self,
        organization_id: uuid.UUID,
        skip: int,
        limit: int,
    ) -> List[Notification]: ...

    @abstractmethod
    async def mark_all_read(self, recipient_id: uuid.UUID) -> int:
        """Returns number marked as read."""

    @abstractmethod
    async def delete_by_id(self, notification_id: uuid.UUID) -> bool:
        """Returns True if deleted, False if not found."""
