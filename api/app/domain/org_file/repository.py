# api/app/domain/org_file/repository.py

"""Repository interface for OrgFile aggregate."""

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Tuple

from app.domain.org_file.models import (
    OrgFile,
    ResourceSource,
    ResourceStatus,
)


class OrgFileKind(str, Enum):
    """File type families the library filters by."""

    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    DOCUMENT = "document"
    OTHER = "other"


class OrgFileSort(str, Enum):
    """Fields the library list orders by."""

    NAME = "name"
    DATE = "date"
    SIZE = "size"
    TYPE = "type"
    SOURCE = "source"
    THUMB = "thumb"
    STATUS = "status"


@dataclass(frozen=True)
class OrgFileQuery:
    """Filters and order for an organization's file list."""

    search: Optional[str] = None
    kind: Optional[OrgFileKind] = None
    source: Optional[ResourceSource] = None
    sort: OrgFileSort = OrgFileSort.DATE
    descending: bool = True


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
        query: Optional[OrgFileQuery] = None,
    ) -> List[OrgFile]: ...

    @abstractmethod
    async def count_by_organization(
        self, organization_id: uuid.UUID, query: Optional[OrgFileQuery] = None
    ) -> int:
        """Rows list_by_organization pages over for the same query."""

    @abstractmethod
    async def count_live_by_organization(self) -> Dict[uuid.UUID, int]:
        """Unfiltered count_by_organization for every organization that has files."""

    @abstractmethod
    async def update(self, resource: OrgFile) -> OrgFile: ...

    @abstractmethod
    async def delete(self, resource_id: uuid.UUID) -> None:
        """Hard delete from database."""

    @abstractmethod
    async def count_referencing_path(self, path: str) -> int:
        """Rows whose file or thumbnail is stored at path."""

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
