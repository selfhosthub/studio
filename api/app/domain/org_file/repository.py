# api/app/domain/org_file/repository.py

"""Repository interface for OrgFile aggregate."""

import uuid
from abc import ABC, abstractmethod
from typing import List, Optional, Tuple

from app.domain.org_file.models import (
    OrgFile,
    ResourceSource,
    ResourceStatus,
)


class OrgFileRepository(ABC):
    """Persistence operations for OrgFile."""

    @abstractmethod
    async def create(self, resource: OrgFile) -> OrgFile: ...

    @abstractmethod
    async def get_by_id(self, resource_id: uuid.UUID) -> Optional[OrgFile]: ...

    @abstractmethod
    async def list_by_job(
        self,
        job_execution_id: uuid.UUID,
    ) -> List[OrgFile]: ...

    @abstractmethod
    async def list_by_instance(
        self,
        instance_id: uuid.UUID,
        status: Optional[ResourceStatus] = None,
        source: Optional[ResourceSource] = None,
    ) -> List[OrgFile]: ...

    @abstractmethod
    async def list_by_organization(
        self,
        organization_id: uuid.UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> List[OrgFile]: ...

    @abstractmethod
    async def update(self, resource: OrgFile) -> OrgFile: ...

    @abstractmethod
    async def delete(self, resource_id: uuid.UUID) -> None:
        """Hard delete from database."""

    @abstractmethod
    async def list_by_instance_step(
        self,
        instance_step_id: uuid.UUID,
    ) -> List[OrgFile]: ...

    @abstractmethod
    async def batch_update_order(
        self,
        order_updates: List[Tuple[uuid.UUID, int]],
    ) -> List[OrgFile]:
        """order_updates: list of (resource_id, new_order). Returns resources in new display order."""
