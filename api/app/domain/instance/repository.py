# api/app/domain/instance/repository.py

"""Repository interface for the Instance aggregate."""
import uuid
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.domain.instance.models import InstanceStatus, Instance


class InstanceRepository(ABC):
    """Persistence operations for Instance aggregates."""

    @abstractmethod
    async def create(self, instance: Instance) -> Instance: ...

    @abstractmethod
    async def update(self, instance: Instance, *, commit: bool = True) -> Instance:
        """Pass commit=False when the caller owns the transaction across multiple repository calls."""

    @abstractmethod
    async def get_by_id(self, instance_id: uuid.UUID) -> Optional[Instance]:
        """Instance with all step executions loaded."""

    @abstractmethod
    async def get_instance_summary(self, instance_id: uuid.UUID) -> Optional[Instance]:
        """Instance without step execution details."""

    @abstractmethod
    async def find_running_instances(
        self,
        organization_id: uuid.UUID,
        skip: int,
        limit: int,
    ) -> List[Instance]: ...

    @abstractmethod
    async def find_instances_by_workflow(
        self,
        workflow_id: uuid.UUID,
        skip: int,
        limit: int,
    ) -> List[Instance]: ...

    @abstractmethod
    async def find_instances_requiring_attention(
        self,
        organization_id: uuid.UUID,
        skip: int,
        limit: int,
    ) -> List[Instance]:
        """Instances that are failed, paused, or otherwise blocked."""

    @abstractmethod
    async def list_by_workflow(
        self,
        workflow_id: uuid.UUID,
        skip: int,
        limit: int,
        status: Optional[InstanceStatus] = None,
        statuses: Optional[List[InstanceStatus]] = None,
    ) -> List[Instance]:
        """status is deprecated; prefer statuses for OR-logic filtering."""

    @abstractmethod
    async def list_by_organization(
        self,
        organization_id: uuid.UUID,
        skip: int,
        limit: int,
        status: Optional[InstanceStatus] = None,
        statuses: Optional[List[InstanceStatus]] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> List[Instance]: ...

    @abstractmethod
    async def count_by_status(
        self,
        organization_id: uuid.UUID,
        status: InstanceStatus,
    ) -> int: ...

    @abstractmethod
    async def count_by_organization(
        self,
        organization_id: uuid.UUID,
        status: Optional[InstanceStatus] = None,
        statuses: Optional[List[InstanceStatus]] = None,
    ) -> int: ...

    @abstractmethod
    async def delete(self, instance_id: uuid.UUID) -> bool: ...

    @abstractmethod
    async def exists(self, instance_id: uuid.UUID) -> bool: ...

    @abstractmethod
    async def count_running_by_workflow(self, workflow_id: uuid.UUID) -> int:
        """Enforces the single-instance-per-workflow constraint."""

    @abstractmethod
    async def get_waiting_for_webhook(
        self, workflow_id: uuid.UUID
    ) -> Optional[Instance]:
        """First WAITING_FOR_WEBHOOK instance for this workflow; used to resume on callback."""

    @abstractmethod
    async def atomic_complete_step(
        self,
        instance_id: uuid.UUID,
        step_id: str,
        step_output: Optional[Dict[str, Any]] = None,
    ) -> None:
        """FOR UPDATE + jsonb_set: in one locked tx, drop step_id from current_step_ids and stash step output."""
