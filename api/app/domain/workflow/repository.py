# api/app/domain/workflow/repository.py

"""Repository interfaces for the workflow domain."""
import uuid
from abc import ABC, abstractmethod
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
    async def find_workflows_using_blueprint(
        self,
        blueprint_id: uuid.UUID,
        skip: int,
        limit: int,
    ) -> List[Workflow]: ...

    @abstractmethod
    async def has_workflows_for_blueprint(self, blueprint_id: uuid.UUID) -> bool: ...

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
    async def list_by_blueprint(
        self,
        blueprint_id: uuid.UUID,
        skip: int,
        limit: int,
        status: Optional[WorkflowStatus] = None,
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
    async def count_by_blueprint(
        self,
        blueprint_id: uuid.UUID,
        skip: int,
        limit: int,
    ) -> int: ...

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
