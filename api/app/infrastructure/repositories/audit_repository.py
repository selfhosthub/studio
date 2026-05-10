# api/app/infrastructure/repositories/audit_repository.py

"""SQLAlchemy implementation of audit event repository."""

import logging
from datetime import datetime
from typing import Any, List, Optional
from uuid import UUID

from sqlalchemy import and_, desc, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.audit.models import (
    AuditAction,
    AuditActorType,
    AuditCategory,
    AuditEvent,
    AuditSeverity,
    AuditStatus,
    ResourceType,
)
from app.domain.audit.repository import AuditEventRepository as AuditEventRepositoryABC
from app.infrastructure.persistence.models import AuditEventModel

logger = logging.getLogger(__name__)


def _is_audit_org_fk_violation(exc: IntegrityError) -> bool:
    """True iff the IntegrityError was raised by the audit_events.organization_id FK.

    Unrelated FK violations (e.g. a stale actor_id referencing users.id) must still
    surface so we never mask unrelated bugs. asyncpg exposes `constraint_name` on the
    wrapped driver error; older drivers may not, so fall back to scanning the string.
    """
    orig = getattr(exc, "orig", None)
    constraint_name = getattr(orig, "constraint_name", None)
    if constraint_name is None and orig is not None:
        constraint_name = getattr(
            getattr(orig, "__cause__", None), "constraint_name", None
        )
    if constraint_name:
        return "organization_id" in constraint_name
    message = str(orig) if orig is not None else str(exc)
    return "organization_id" in message and "audit_events" in message


class AuditEventRepository(AuditEventRepositoryABC):

    def __init__(self, session: AsyncSession):
        self.session = session

    def _build_model(
        self, event: AuditEvent, organization_id: Optional[UUID]
    ) -> AuditEventModel:
        return AuditEventModel(
            id=event.id,
            organization_id=organization_id,
            actor_id=event.actor_id,
            actor_type=event.actor_type,
            action=event.action.value,
            resource_type=event.resource_type.value,
            resource_id=event.resource_id,
            resource_name=event.resource_name,
            severity=event.severity.value,
            category=event.category.value,
            changes=event.changes,
            event_metadata=event.metadata,
            status=event.status,
            error_message=event.error_message,
            created_at=event.created_at,
        )

    async def create(self, event: AuditEvent) -> AuditEvent:
        """Create a new audit event (append-only, no updates allowed).

        If the JWT-supplied organization_id references an organization that no longer
        exists, the savepoint auto-rolls back and we retry once with organization_id=None
        so the event still lands as a system-level record. Unrelated FK violations
        propagate.
        """
        model = self._build_model(event, event.organization_id)
        try:
            async with self.session.begin_nested():
                self.session.add(model)
        except IntegrityError as exc:
            if not _is_audit_org_fk_violation(exc):
                raise
            logger.warning(
                "Audit event references stale organization_id %s; storing as NULL",
                event.organization_id,
            )
            model = self._build_model(event, None)
            async with self.session.begin_nested():
                self.session.add(model)

        await self.session.commit()
        await self.session.refresh(model)

        return self._to_domain(model)

    async def get_by_id(self, event_id: UUID) -> Optional[AuditEvent]:
        stmt = select(AuditEventModel).where(AuditEventModel.id == event_id)
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()

        if not model:
            return None

        return self._to_domain(model)

    async def list_by_organization(
        self,
        organization_id: UUID,
        skip: int = 0,
        limit: int = 50,
        resource_type: Optional[str] = None,
        action: Optional[str] = None,
        severity: Optional[str] = None,
        category: Optional[str] = None,
        actor_id: Optional[UUID] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> List[AuditEvent]:
        conditions = [AuditEventModel.organization_id == organization_id]

        if resource_type:
            conditions.append(AuditEventModel.resource_type == resource_type)
        if action:
            conditions.append(AuditEventModel.action == action)
        if severity:
            conditions.append(AuditEventModel.severity == severity)
        if category:
            conditions.append(AuditEventModel.category == category)
        if actor_id:
            conditions.append(AuditEventModel.actor_id == actor_id)
        if start_date:
            conditions.append(AuditEventModel.created_at >= start_date)
        if end_date:
            conditions.append(AuditEventModel.created_at <= end_date)

        stmt = (
            select(AuditEventModel)
            .where(and_(*conditions))
            .order_by(desc(AuditEventModel.created_at))
            .offset(skip)
            .limit(limit)
        )

        result = await self.session.execute(stmt)
        models = result.scalars().all()

        return [self._to_domain(model) for model in models]

    async def list_system_events(
        self,
        skip: int = 0,
        limit: int = 50,
        resource_type: Optional[str] = None,
        action: Optional[str] = None,
        severity: Optional[str] = None,
        actor_id: Optional[UUID] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> List[AuditEvent]:
        """System-level events (organization_id IS NULL). Only visible to super_admin."""
        conditions: List[Any] = [AuditEventModel.organization_id.is_(None)]

        if resource_type:
            conditions.append(AuditEventModel.resource_type == resource_type)
        if action:
            conditions.append(AuditEventModel.action == action)
        if severity:
            conditions.append(AuditEventModel.severity == severity)
        if actor_id:
            conditions.append(AuditEventModel.actor_id == actor_id)
        if start_date:
            conditions.append(AuditEventModel.created_at >= start_date)
        if end_date:
            conditions.append(AuditEventModel.created_at <= end_date)

        stmt = (
            select(AuditEventModel)
            .where(and_(*conditions))
            .order_by(desc(AuditEventModel.created_at))
            .offset(skip)
            .limit(limit)
        )

        result = await self.session.execute(stmt)
        models = result.scalars().all()

        return [self._to_domain(model) for model in models]

    async def list_all_events(
        self,
        skip: int = 0,
        limit: int = 50,
        organization_id: Optional[UUID] = None,
        resource_type: Optional[str] = None,
        action: Optional[str] = None,
        severity: Optional[str] = None,
        category: Optional[str] = None,
        actor_id: Optional[UUID] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        include_system_events: bool = True,
    ) -> List[AuditEvent]:
        conditions = []

        if organization_id:
            conditions.append(AuditEventModel.organization_id == organization_id)
        elif not include_system_events:
            conditions.append(AuditEventModel.organization_id.isnot(None))

        if resource_type:
            conditions.append(AuditEventModel.resource_type == resource_type)
        if action:
            conditions.append(AuditEventModel.action == action)
        if severity:
            conditions.append(AuditEventModel.severity == severity)
        if category:
            conditions.append(AuditEventModel.category == category)
        if actor_id:
            conditions.append(AuditEventModel.actor_id == actor_id)
        if start_date:
            conditions.append(AuditEventModel.created_at >= start_date)
        if end_date:
            conditions.append(AuditEventModel.created_at <= end_date)

        stmt = select(AuditEventModel).order_by(desc(AuditEventModel.created_at))

        if conditions:
            stmt = stmt.where(and_(*conditions))

        stmt = stmt.offset(skip).limit(limit)

        result = await self.session.execute(stmt)
        models = result.scalars().all()

        return [self._to_domain(model) for model in models]

    async def list_by_resource(
        self,
        resource_type: str,
        resource_id: UUID,
        skip: int = 0,
        limit: int = 50,
    ) -> List[AuditEvent]:
        """Get the audit history for a specific resource."""
        stmt = (
            select(AuditEventModel)
            .where(
                and_(
                    AuditEventModel.resource_type == resource_type,
                    AuditEventModel.resource_id == resource_id,
                )
            )
            .order_by(desc(AuditEventModel.created_at))
            .offset(skip)
            .limit(limit)
        )

        result = await self.session.execute(stmt)
        models = result.scalars().all()

        return [self._to_domain(model) for model in models]

    async def list_by_actor(
        self,
        actor_id: UUID,
        skip: int = 0,
        limit: int = 50,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> List[AuditEvent]:
        conditions = [AuditEventModel.actor_id == actor_id]

        if start_date:
            conditions.append(AuditEventModel.created_at >= start_date)
        if end_date:
            conditions.append(AuditEventModel.created_at <= end_date)

        stmt = (
            select(AuditEventModel)
            .where(and_(*conditions))
            .order_by(desc(AuditEventModel.created_at))
            .offset(skip)
            .limit(limit)
        )

        result = await self.session.execute(stmt)
        models = result.scalars().all()

        return [self._to_domain(model) for model in models]

    async def count_by_organization(
        self,
        organization_id: UUID,
        resource_type: Optional[str] = None,
        severity: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> int:
        conditions = [AuditEventModel.organization_id == organization_id]

        if resource_type:
            conditions.append(AuditEventModel.resource_type == resource_type)
        if severity:
            conditions.append(AuditEventModel.severity == severity)
        if start_date:
            conditions.append(AuditEventModel.created_at >= start_date)
        if end_date:
            conditions.append(AuditEventModel.created_at <= end_date)

        stmt = (
            select(func.count()).select_from(AuditEventModel).where(and_(*conditions))
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def count_all(
        self,
        organization_id: Optional[UUID] = None,
        resource_type: Optional[str] = None,
        severity: Optional[str] = None,
        category: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> int:
        conditions = []

        if organization_id:
            conditions.append(AuditEventModel.organization_id == organization_id)
        if resource_type:
            conditions.append(AuditEventModel.resource_type == resource_type)
        if severity:
            conditions.append(AuditEventModel.severity == severity)
        if category:
            conditions.append(AuditEventModel.category == category)
        if start_date:
            conditions.append(AuditEventModel.created_at >= start_date)
        if end_date:
            conditions.append(AuditEventModel.created_at <= end_date)

        stmt = select(func.count()).select_from(AuditEventModel)

        if conditions:
            stmt = stmt.where(and_(*conditions))

        result = await self.session.execute(stmt)
        return result.scalar_one()

    def _to_domain(self, model: AuditEventModel) -> AuditEvent:
        # Safely convert enums - fallback to sensible defaults for legacy/unknown values.
        try:
            action = AuditAction(model.action)
        except (ValueError, TypeError):
            action = AuditAction.UPDATE

        try:
            resource_type = ResourceType(model.resource_type)
        except (ValueError, TypeError):
            resource_type = ResourceType.WORKFLOW

        try:
            severity = AuditSeverity(model.severity)
        except (ValueError, TypeError):
            severity = AuditSeverity.INFO

        try:
            category = AuditCategory(model.category)
        except (ValueError, TypeError):
            category = AuditCategory.CONFIGURATION

        try:
            actor_type = AuditActorType(model.actor_type)
        except (ValueError, TypeError):
            actor_type = AuditActorType.UNKNOWN

        try:
            audit_status = AuditStatus(model.status)
        except (ValueError, TypeError):
            audit_status = AuditStatus.SUCCESS

        return AuditEvent(
            id=model.id,
            organization_id=model.organization_id,
            actor_id=model.actor_id,
            actor_type=actor_type,
            action=action,
            resource_type=resource_type,
            resource_id=model.resource_id,
            resource_name=model.resource_name,
            severity=severity,
            category=category,
            changes=model.changes,
            metadata=model.event_metadata or {},
            status=audit_status,
            error_message=model.error_message,
            created_at=model.created_at,
        )
