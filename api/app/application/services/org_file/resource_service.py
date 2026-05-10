# api/app/application/services/org_file/resource_service.py

"""
Resource CRUD, query, reorder, and delete operations.
"""

import logging
import uuid
from typing import Any, List, Optional, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)

from app.application.interfaces import EntityNotFoundError
from app.application.interfaces.event_bus import EventBus
from app.domain.org_file.models import (
    OrgFile,
    ResourceSource,
    ResourceStatus,
)
from app.domain.org_file.repository import OrgFileRepository
from app.domain.instance.repository import InstanceRepository
from app.domain.workflow.repository import WorkflowRepository
from app.infrastructure.storage.workspace import (
    cleanup_resource_files,
    get_workspace_path,
    resolve_safe_path,
)


class ResourceService:
    """CRUD, query, reorder, and delete operations for job output resources."""

    def __init__(
        self,
        resource_repository: OrgFileRepository,
        instance_repository: InstanceRepository,
        workflow_repository: WorkflowRepository,
        event_bus: EventBus,
    ):
        self.resource_repository = resource_repository
        self.instance_repository = instance_repository
        self.workflow_repository = workflow_repository
        self.event_bus = event_bus

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
        """
        Register a new job output resource.

        Called by webhook when worker completes a job and creates/downloads a resource.
        """
        # Instance lookup is not yet implemented; always raises.
        raise EntityNotFoundError(
            entity_type="Instance",
            entity_id=job_execution_id,
            code="Instance not found for job execution",
        )

    async def get_resource(self, resource_id: uuid.UUID) -> Optional[OrgFile]:
        """Return the resource, or None if not found."""
        return await self.resource_repository.get_by_id(resource_id)

    async def get_resources_for_instance(
        self,
        instance_id: uuid.UUID,
        status: Optional[ResourceStatus] = None,
        source: Optional[ResourceSource] = None,
    ) -> List[OrgFile]:
        return await self.resource_repository.list_by_instance(
            instance_id, status=status, source=source
        )

    async def get_resources_for_job(
        self, job_execution_id: uuid.UUID
    ) -> List[OrgFile]:
        return await self.resource_repository.list_by_job(job_execution_id)

    async def get_resources_for_organization(
        self, organization_id: uuid.UUID, skip: int = 0, limit: int = 20
    ) -> List[OrgFile]:
        return await self.resource_repository.list_by_organization(
            organization_id, skip=skip, limit=limit
        )

    async def get_resource_file_path(self, resource_id: uuid.UUID) -> Tuple[Path, str]:
        """Return (file_path, mime_type) for the resource, raising if not found."""
        resource = await self.resource_repository.get_by_id(resource_id)
        if not resource:
            raise EntityNotFoundError(
                entity_type="OrgFile",
                entity_id=resource_id,
                code="Resource not found",
            )

        if not resource.virtual_path:
            raise EntityNotFoundError(
                entity_type="OrgFile",
                entity_id=resource_id,
                code="Resource has no virtual_path - file location unknown",
            )

        workspace_path = get_workspace_path()
        file_path = resolve_safe_path(workspace_path, resource.virtual_path)

        return (file_path, resource.mime_type)

    async def get_resource_thumbnail_path(
        self, resource_id: uuid.UUID
    ) -> Optional[Path]:
        """Get the thumbnail path for a resource."""
        resource = await self.resource_repository.get_by_id(resource_id)
        if not resource:
            logger.warning(f"Thumbnail 404: resource {resource_id} not found")
            return None

        if not resource.has_thumbnail:
            logger.warning(f"Thumbnail 404: resource {resource_id} has_thumbnail=False")
            return None

        thumbnail_virtual_path = (
            resource.metadata.get("thumbnail_path") if resource.metadata else None
        )
        if not thumbnail_virtual_path:
            logger.warning(
                f"Thumbnail 404: resource {resource_id} has_thumbnail=True "
                f"but no thumbnail_path in metadata: {resource.metadata}"
            )
            return None

        workspace_path = get_workspace_path()
        thumbnail_path = resolve_safe_path(workspace_path, thumbnail_virtual_path)

        if thumbnail_path.exists():
            return thumbnail_path

        logger.warning(
            f"Thumbnail 404: resource {resource_id} file not on disk: "
            f"{thumbnail_path} (virtual_path={thumbnail_virtual_path})"
        )
        return None

    async def delete_resource(self, resource_id: uuid.UUID) -> None:
        """
        Delete a resource (hard delete from database + file cleanup).

        Also updates the instance's output_data to remove the deleted resource
        from downloaded_files arrays.
        """
        resource = await self.resource_repository.get_by_id(resource_id)
        if not resource:
            raise EntityNotFoundError(
                entity_type="OrgFile",
                entity_id=resource_id,
                code="Resource not found",
            )

        virtual_path = resource.virtual_path
        thumbnail_path = (
            resource.metadata.get("thumbnail_path") if resource.metadata else None
        )
        instance_id = resource.instance_id

        await self.resource_repository.delete(resource_id)

        cleanup_resource_files(
            virtual_path=virtual_path,
            thumbnail_path=thumbnail_path,
        )

        if instance_id is not None:
            await self._remove_resource_from_output_data(instance_id, virtual_path)

    async def _remove_resource_from_output_data(
        self, instance_id: uuid.UUID, virtual_path: str
    ) -> None:
        """
        Remove a deleted resource from the instance's output_data.

        Searches through all step outputs for downloaded_files arrays and removes
        entries matching the virtual_path.
        """
        instance = await self.instance_repository.get_by_id(instance_id)
        if not instance or not instance.output_data:
            return

        modified = False
        for _step_id, step_output in instance.output_data.items():
            if not isinstance(step_output, dict):
                continue

            downloaded_files = step_output.get("downloaded_files")
            if not isinstance(downloaded_files, list):
                continue

            original_count = len(downloaded_files)
            filtered_files = [
                f
                for f in downloaded_files
                if isinstance(f, dict) and f.get("virtual_path") != virtual_path
            ]

            if len(filtered_files) < original_count:
                step_output["downloaded_files"] = filtered_files
                if "image_count" in step_output:
                    step_output["image_count"] = len(filtered_files)
                modified = True

        if modified:
            await self.instance_repository.update(instance)

    async def reorder_resources(
        self,
        job_execution_id: uuid.UUID,
        resource_ids: List[uuid.UUID],
    ) -> List[OrgFile]:
        """Reorder resources within a job execution."""
        job_resources = await self.resource_repository.list_by_job(job_execution_id)
        resource_map = {r.id: r for r in job_resources}

        for rid in resource_ids:
            if rid not in resource_map:
                raise EntityNotFoundError(
                    entity_type="OrgFile",
                    entity_id=rid,
                    code=f"Resource {rid} not found in job {job_execution_id}",
                )

        for index, rid in enumerate(resource_ids):
            resource_map[rid].set_display_order(index)

        order_updates = [(rid, idx) for idx, rid in enumerate(resource_ids)]
        updated_resources = await self.resource_repository.batch_update_order(
            order_updates
        )

        return updated_resources

    async def reorder_step_resources(
        self,
        instance_step_id: uuid.UUID,
        resource_ids: List[uuid.UUID],
    ) -> List[OrgFile]:
        """Reorder resources within an instance step (across all iteration jobs)."""
        step_resources = await self.resource_repository.list_by_instance_step(
            instance_step_id
        )
        resource_map = {r.id: r for r in step_resources}

        for rid in resource_ids:
            if rid not in resource_map:
                raise EntityNotFoundError(
                    entity_type="OrgFile",
                    entity_id=rid,
                    code=f"Resource {rid} not found in step {instance_step_id}",
                )

        for index, rid in enumerate(resource_ids):
            resource_map[rid].set_display_order(index)

        order_updates = [(rid, idx) for idx, rid in enumerate(resource_ids)]
        updated_resources = await self.resource_repository.batch_update_order(
            order_updates
        )

        return updated_resources
