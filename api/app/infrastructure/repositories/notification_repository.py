# api/app/infrastructure/repositories/notification_repository.py

"""SQLAlchemy implementation of notification repository."""

from datetime import UTC, datetime
from typing import List, Optional
from uuid import UUID

from sqlalchemy import and_, delete, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.notification.models import (
    ChannelType,
    Notification,
    NotificationStatus,
)
from app.domain.notification.repository import NotificationRepository
from app.infrastructure.persistence.models import NotificationModel


class SQLAlchemyNotificationRepository(NotificationRepository):
    """SQLAlchemy implementation of notification repository."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, notification: Notification) -> Notification:
        model = NotificationModel(
            id=notification.id,
            organization_id=notification.organization_id,
            recipient_id=notification.recipient_id,
            title=notification.title,
            message=notification.message,
            channel_type=notification.channel_type.value,
            channel_id=notification.channel_id,
            priority=notification.priority,
            status=notification.status,
            sent_at=notification.sent_at,
            created_by=notification.created_by,
            client_metadata=notification.client_metadata,
            created_at=notification.created_at,
            updated_at=notification.updated_at or datetime.now(UTC),
        )

        self.session.add(model)
        await self.session.commit()
        await self.session.refresh(model)

        return self._to_domain(model)

    async def update(self, notification: Notification) -> Notification:
        stmt = select(NotificationModel).where(NotificationModel.id == notification.id)
        result = await self.session.execute(stmt)
        existing = result.scalar_one()

        existing.status = notification.status
        existing.sent_at = notification.sent_at
        existing.read_at = notification.read_at
        existing.client_metadata = notification.client_metadata
        existing.updated_at = datetime.now(UTC)

        await self.session.commit()
        await self.session.refresh(existing)

        return self._to_domain(existing)

    async def get_by_id(self, notification_id: UUID) -> Optional[Notification]:
        stmt = select(NotificationModel).where(NotificationModel.id == notification_id)
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()

        if not model:
            return None

        return self._to_domain(model)

    async def list_by_recipient(
        self,
        recipient_id: UUID,
        skip: int,
        limit: int,
    ) -> List[Notification]:
        stmt = (
            select(NotificationModel)
            .where(NotificationModel.recipient_id == recipient_id)
            .order_by(desc(NotificationModel.created_at))
        )

        stmt = stmt.offset(skip).limit(limit)

        result = await self.session.execute(stmt)
        models = result.scalars().all()

        return [self._to_domain(model) for model in models]

    async def list_by_organization(
        self,
        organization_id: UUID,
        skip: int,
        limit: int,
    ) -> List[Notification]:
        stmt = (
            select(NotificationModel)
            .where(NotificationModel.organization_id == organization_id)
            .order_by(desc(NotificationModel.created_at))
        )

        stmt = stmt.offset(skip).limit(limit)

        result = await self.session.execute(stmt)
        models = result.scalars().all()

        return [self._to_domain(model) for model in models]

    async def find_pending_notifications(
        self, organization_id: UUID, skip: int, limit: int
    ) -> List[Notification]:
        stmt = (
            select(NotificationModel)
            .where(
                and_(
                    NotificationModel.organization_id == organization_id,
                    NotificationModel.status == NotificationStatus.PENDING,
                )
            )
            .order_by(NotificationModel.created_at)
        )

        stmt = stmt.offset(skip).limit(limit)

        result = await self.session.execute(stmt)
        models = result.scalars().all()

        return [self._to_domain(model) for model in models]

    async def mark_all_read(self, recipient_id: UUID) -> int:
        stmt = select(NotificationModel).where(
            and_(
                NotificationModel.recipient_id == recipient_id,
                NotificationModel.read_at.is_(None),
            )
        )

        result = await self.session.execute(stmt)
        notifications = result.scalars().all()

        for notification in notifications:
            notification.read_at = datetime.now(UTC)

        await self.session.commit()

        return len(notifications)

    async def delete_by_id(self, notification_id: UUID) -> bool:
        stmt = select(NotificationModel).where(NotificationModel.id == notification_id)
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()

        if not model:
            return False

        await self.session.delete(model)
        await self.session.commit()

        return True

    async def count_by_status(
        self, organization_id: UUID, status: NotificationStatus
    ) -> int:
        stmt = select(func.count()).where(
            and_(
                NotificationModel.organization_id == organization_id,
                NotificationModel.status == status,
            )
        )

        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def cleanup_old_notifications(
        self, before: datetime, status: Optional[NotificationStatus] = None
    ) -> int:
        conditions = [NotificationModel.created_at < before]

        if status:
            conditions.append(NotificationModel.status == status)
        else:
            conditions.append(NotificationModel.status.in_([NotificationStatus.SENT]))

        stmt = delete(NotificationModel).where(and_(*conditions))

        result = await self.session.execute(stmt)
        await self.session.commit()

        return result.rowcount or 0

    def _to_domain(self, model: NotificationModel) -> Notification:
        try:
            channel_type = ChannelType(model.channel_type)
        except (ValueError, TypeError):
            channel_type = ChannelType.IN_APP

        return Notification(
            id=model.id,
            organization_id=model.organization_id,
            recipient_id=model.recipient_id,
            created_by=model.created_by,
            channel_type=channel_type,
            channel_id=model.channel_id,
            title=model.title,
            message=model.message,
            priority=model.priority,
            status=model.status,
            sent_at=model.sent_at,
            read_at=model.read_at,
            tags=[],
            client_metadata=model.client_metadata,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
