# api/app/application/services/org_file/__init__.py

"""Job output resource service facade.

Composes read/query and upload services behind a single API so existing
importers work unchanged.
"""

import uuid
from typing import Any, BinaryIO, List, Optional, Tuple
from pathlib import Path

from app.application.interfaces.event_bus import EventBus
from app.domain.org_file.models import (
    OrgFile,
    ResourceSource,
    ResourceStatus,
)
from app.domain.org_file.repository import OrgFileRepository
from app.domain.instance.repository import InstanceRepository
from app.domain.workflow.repository import WorkflowRepository

from .resource_service import ResourceService
from .resource_upload_service import ResourceUploadService


class OrgFileService:
    """Facade that preserves the original public API for this service."""

    def __init__(
        self,
        resource_repository: OrgFileRepository,
        instance_repository: InstanceRepository,
        workflow_repository: WorkflowRepository,
        event_bus: EventBus,
    ):
        self._resource_service = ResourceService(
            resource_repository=resource_repository,
            instance_repository=instance_repository,
            workflow_repository=workflow_repository,
            event_bus=event_bus,
        )
        self._upload_service = ResourceUploadService(
            resource_repository=resource_repository,
            event_bus=event_bus,
        )

    # -- Resource CRUD / query operations --

    async def register_resource(
        self,
        job_execution_id: uuid.UUID,
        display_name: str,
        file_size: int,
        mime_type: str,
        file_extension: str,
        source: ResourceSource,
        checksum: Optional[str] = None,
        provider_id: Optional[uuid.UUID] = None,
        provider_resource_id: Optional[str] = None,
        provider_url: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> OrgFile:
        return await self._resource_service.register_resource(
            job_execution_id=job_execution_id,
            display_name=display_name,
            file_size=file_size,
            mime_type=mime_type,
            file_extension=file_extension,
            source=source,
            checksum=checksum,
            provider_id=provider_id,
            provider_resource_id=provider_resource_id,
            provider_url=provider_url,
            metadata=metadata,
        )

    async def get_resource(self, resource_id: uuid.UUID) -> Optional[OrgFile]:
        return await self._resource_service.get_resource(resource_id)

    async def get_resources_for_instance(
        self,
        instance_id: uuid.UUID,
        status: Optional[ResourceStatus] = None,
        source: Optional[ResourceSource] = None,
    ) -> List[OrgFile]:
        return await self._resource_service.get_resources_for_instance(
            instance_id, status=status, source=source
        )

    async def get_resources_for_job(
        self, job_execution_id: uuid.UUID
    ) -> List[OrgFile]:
        return await self._resource_service.get_resources_for_job(job_execution_id)

    async def get_resources_for_organization(
        self, organization_id: uuid.UUID, skip: int = 0, limit: int = 20
    ) -> List[OrgFile]:
        return await self._resource_service.get_resources_for_organization(
            organization_id, skip=skip, limit=limit
        )

    async def get_resource_file_path(self, resource_id: uuid.UUID) -> Tuple[Path, str]:
        return await self._resource_service.get_resource_file_path(resource_id)

    async def get_resource_thumbnail_path(
        self, resource_id: uuid.UUID
    ) -> Optional[Path]:
        return await self._resource_service.get_resource_thumbnail_path(resource_id)

    async def delete_resource(self, resource_id: uuid.UUID) -> None:
        return await self._resource_service.delete_resource(resource_id)

    async def reorder_resources(
        self,
        job_execution_id: uuid.UUID,
        resource_ids: List[uuid.UUID],
    ) -> List[OrgFile]:
        return await self._resource_service.reorder_resources(
            job_execution_id, resource_ids
        )

    async def reorder_step_resources(
        self,
        instance_step_id: uuid.UUID,
        resource_ids: List[uuid.UUID],
    ) -> List[OrgFile]:
        return await self._resource_service.reorder_step_resources(
            instance_step_id, resource_ids
        )

    # -- Upload / replace operations --

    async def replace_resource(
        self,
        resource_id: uuid.UUID,
        file_content: BinaryIO,
        file_size: int,
        mime_type: str,
        file_extension: str,
        display_name: Optional[str] = None,
    ) -> OrgFile:
        return await self._upload_service.replace_resource(
            resource_id=resource_id,
            file_content=file_content,
            file_size=file_size,
            mime_type=mime_type,
            file_extension=file_extension,
            display_name=display_name,
        )

    async def upload_file(
        self,
        organization_id: uuid.UUID,
        file_content: BinaryIO,
        file_size: int,
        mime_type: str,
        file_extension: str,
        display_name: str,
    ) -> OrgFile:
        return await self._upload_service.upload_file(
            organization_id=organization_id,
            file_content=file_content,
            file_size=file_size,
            mime_type=mime_type,
            file_extension=file_extension,
            display_name=display_name,
        )

    async def upload_file_to_step(
        self,
        instance_id: uuid.UUID,
        step_key: str,
        organization_id: uuid.UUID,
        file_content: BinaryIO,
        file_size: int,
        mime_type: str,
        file_extension: str,
        display_name: str,
        job_execution_id: Optional[uuid.UUID] = None,
        instance_step_id: Optional[uuid.UUID] = None,
    ) -> OrgFile:
        return await self._upload_service.upload_file_to_step(
            instance_id=instance_id,
            step_key=step_key,
            organization_id=organization_id,
            file_content=file_content,
            file_size=file_size,
            mime_type=mime_type,
            file_extension=file_extension,
            display_name=display_name,
            job_execution_id=job_execution_id,
            instance_step_id=instance_step_id,
        )

    async def add_library_file_to_step(
        self,
        source_resource_id: uuid.UUID,
        instance_id: uuid.UUID,
        instance_step_id: uuid.UUID,
        organization_id: uuid.UUID,
    ) -> OrgFile:
        return await self._upload_service.add_library_file_to_step(
            source_resource_id=source_resource_id,
            instance_id=instance_id,
            instance_step_id=instance_step_id,
            organization_id=organization_id,
        )
