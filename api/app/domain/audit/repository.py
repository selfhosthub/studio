# api/app/domain/audit/repository.py

"""Repository interface for audit event persistence."""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from app.domain.audit.models import AuditEvent


class AuditEventRepository(ABC):
    """Append-only audit event repository."""

    @abstractmethod
    async def create(self, event: AuditEvent) -> AuditEvent: ...

    @abstractmethod
    async def get_by_id(self, event_id: UUID) -> Optional[AuditEvent]: ...

    @abstractmethod
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
    ) -> List[AuditEvent]: ...

    @abstractmethod
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
        """System-level events (organization_id IS NULL)."""

    @abstractmethod
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
        """All audit events (super_admin only)."""

    @abstractmethod
    async def list_by_resource(
        self,
        resource_type: str,
        resource_id: UUID,
        skip: int = 0,
        limit: int = 50,
    ) -> List[AuditEvent]: ...

    @abstractmethod
    async def list_by_actor(
        self,
        actor_id: UUID,
        skip: int = 0,
        limit: int = 50,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> List[AuditEvent]: ...

    @abstractmethod
    async def count_by_organization(
        self,
        organization_id: UUID,
        resource_type: Optional[str] = None,
        severity: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> int: ...

    @abstractmethod
    async def count_all(
        self,
        organization_id: Optional[UUID] = None,
        resource_type: Optional[str] = None,
        severity: Optional[str] = None,
        category: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> int: ...
