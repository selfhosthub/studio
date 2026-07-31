# api/app/domain/workflow/repository.py

"""Repository interfaces for the workflow domain."""
import uuid
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, Any, List, Optional

from app.domain.workflow.models import Workflow, WorkflowStatus, WorkflowTriggerType


class WorkflowRepository(ABC):
    """Persistence operations for Workflow aggregates."""

    @abstractmethod
    async def create(self, workflow: Workflow) -> Workflow: ...

    @abstractmethod
    async def update(self, workflow: Workflow) -> Workflow: ...

    @abstractmethod
    async def get_by_id(self, workflow_id: uuid.UUID) -> Optional[Workflow]: ...

    @abstractmethod
    async def get_by_id_and_version(
        self, workflow_id: uuid.UUID, version: int
    ) -> Optional[Workflow]: ...

    @abstractmethod
    async def get_by_name(
        self,
        organization_id: uuid.UUID,
        name: str,
        exclude_id: Optional[uuid.UUID] = None,
    ) -> Optional[Workflow]: ...

    @abstractmethod
    async def find_active_workflows_for_organization(
        self,
        organization_id: uuid.UUID,
        skip: int,
        limit: int,
    ) -> List[Workflow]: ...

    @abstractmethod
    async def find_workflows_ready_for_execution(
        self,
        organization_id: uuid.UUID,
        skip: int,
        limit: int,
    ) -> List[Workflow]: ...

    @abstractmethod
    async def list_by_organization(
        self,
        organization_id: uuid.UUID,
        skip: int,
        limit: int,
        status: Optional[WorkflowStatus] = None,
        trigger_type: Optional[WorkflowTriggerType] = None,
    ) -> List[Workflow]: ...

    @abstractmethod
    async def list_active_scheduled(
        self,
        skip: int,
        limit: int,
        organization_id: Optional[uuid.UUID] = None,
    ) -> List[Workflow]: ...

    @abstractmethod
    async def search(
        self,
        query: str,
        skip: int,
        limit: int,
        organization_id: Optional[uuid.UUID] = None,
    ) -> List[Workflow]: ...

    @abstractmethod
    async def delete(self, workflow_id: uuid.UUID) -> bool:
        """Returns True if deleted, False if not found."""

    @abstractmethod
    async def count_by_organization(
        self,
        organization_id: uuid.UUID,
        skip: int,
        limit: int,
        status: Optional[WorkflowStatus] = None,
    ) -> int: ...

    @abstractmethod
    async def count_by_trigger_secret_id(self, secret_id: uuid.UUID) -> int:
        """How many workflows reference this trigger OrganizationSecret (sharing)."""
        ...

    @abstractmethod
    async def list_by_trigger_secret_id(
        self, secret_id: uuid.UUID
    ) -> List[Dict[str, Any]]:
        """Lightweight [{"id", "name"}] for every workflow referencing this trigger
        secret - for the in-use warning before deletion and the reset that follows."""
        ...

    @abstractmethod
    async def get_execution_stats(self, workflow_id: uuid.UUID) -> Dict[str, Any]: ...

    @abstractmethod
    async def exists(self, workflow_id: uuid.UUID) -> bool: ...

    @abstractmethod
    async def list_personal_workflows(
        self,
        organization_id: uuid.UUID,
        created_by: uuid.UUID,
        skip: int,
        limit: int,
        status: Optional[WorkflowStatus] = None,
    ) -> List[Workflow]: ...

    @abstractmethod
    async def list_organization_workflows(
        self,
        organization_id: uuid.UUID,
        skip: int,
        limit: int,
        status: Optional[WorkflowStatus] = None,
    ) -> List[Workflow]: ...

    @abstractmethod
    async def list_pending_publish(
        self,
        organization_id: uuid.UUID,
        skip: int,
        limit: int,
    ) -> List[Workflow]: ...

    @abstractmethod
    async def get_by_webhook_token(self, token: str) -> Optional[Workflow]: ...

    @abstractmethod
    async def get_by_step_webhook_token(
        self, token: str
    ) -> Optional[tuple[Workflow, str]]:
        """Returns (workflow, step_id) tuple or None if token not found."""

    @abstractmethod
    async def get_due_schedules(self, now: datetime) -> List[Workflow]:
        """Active, enabled schedule-trigger workflows whose next_run_at is due."""

    @abstractmethod
    async def list_event_triggered_by(
        self, source_workflow_id: uuid.UUID
    ) -> List[Workflow]:
        """Active event-trigger workflows bound to fire when source finishes."""
