# api/app/application/services/org_file/resource_upload_service.py

"""
File upload, replace, and library-to-step operations for job output resources.
"""

import hashlib
import uuid
from typing import Any, BinaryIO, Optional

from app.application.interfaces import EntityNotFoundError
from app.application.interfaces.event_bus import EventBus
from app.domain.org_file.models import (
    OrgFile,
    ResourceSource,
    ResourceStatus,
)
from app.domain.org_file.repository import OrgFileRepository
from app.infrastructure.storage.workspace import (
    cleanup_resource_files,
    get_workspace_path,
)

from .thumbnail import generate_thumbnail


class ResourceUploadService:
    """File upload, replace, and library-to-step operations."""

    def __init__(
        self,
        resource_repository: OrgFileRepository,
        event_bus: EventBus,
    ):
        self.resource_repository = resource_repository
        self.event_bus = event_bus

    async def replace_resource(
        self,
        resource_id: uuid.UUID,
        file_content: BinaryIO,
        file_size: int,
        mime_type: str,
        file_extension: str,
        display_name: Optional[str] = None,
    ) -> OrgFile:
        """
        Replace a resource's file content with a user-uploaded file.

        Preserves the resource's position in the workflow.
        """
        resource = await self.resource_repository.get_by_id(resource_id)
        if not resource:
            raise EntityNotFoundError(
                entity_type="OrgFile",
                entity_id=resource_id,
                code="Resource not found",
            )

        old_virtual_path = resource.virtual_path
        old_thumbnail_path = (
            resource.metadata.get("thumbnail_path") if resource.metadata else None
        )

        workspace_path = get_workspace_path()
        relative_dir = (
            f"orgs/{resource.organization_id}/instances/{resource.instance_id}"
        )
        new_filename = f"{resource.id}{file_extension}"
        new_virtual_path = f"/{relative_dir}/{new_filename}"

        file_dir = workspace_path / relative_dir
        file_dir.mkdir(parents=True, exist_ok=True)

        file_path = workspace_path / relative_dir / new_filename
        hasher = hashlib.sha256()
        with open(file_path, "wb") as f:
            while chunk := file_content.read(8192):
                hasher.update(chunk)
                f.write(chunk)
        new_checksum = hasher.hexdigest()

        resource.replace_file(
            file_size=file_size,
            mime_type=mime_type,
            file_extension=file_extension,
            virtual_path=new_virtual_path,
            display_name=display_name or resource.display_name,
            checksum=new_checksum,
            source=ResourceSource.USER_UPLOAD,
        )
        events = resource.clear_events()
        resource = await self.resource_repository.update(resource)

        for event in events:
            await self.event_bus.publish(event)

        if old_virtual_path and old_virtual_path != new_virtual_path:
            cleanup_resource_files(
                virtual_path=old_virtual_path,
                thumbnail_path=old_thumbnail_path,
            )

        return resource

    async def upload_file(
        self,
        organization_id: uuid.UUID,
        file_content: BinaryIO,
        file_size: int,
        mime_type: str,
        file_extension: str,
        display_name: str,
    ) -> OrgFile:
        """
        Upload a standalone file to the organization's file library.

        Creates a new resource not tied to any workflow instance.
        Files are stored in /orgs/{org_id}/uploads/ directory.
        Thumbnails are generated for image files.
        """
        resource_id = uuid.uuid4()

        base_name = display_name
        if "." in base_name:
            base_name = base_name.rsplit(".", 1)[0]
        safe_name = "".join(c if c.isalnum() or c in "-_." else "_" for c in base_name)
        safe_name = safe_name[:100]
        filename = f"{safe_name}{file_extension}"

        workspace_path = get_workspace_path()
        relative_dir = f"orgs/{organization_id}/uploads"
        virtual_path = f"/{relative_dir}/{filename}"

        file_dir = workspace_path / relative_dir
        file_dir.mkdir(parents=True, exist_ok=True)

        file_path = file_dir / filename
        hasher = hashlib.sha256()
        with open(file_path, "wb") as f:
            while chunk := file_content.read(8192):
                hasher.update(chunk)
                f.write(chunk)
        checksum = hasher.hexdigest()

        has_thumbnail = False
        thumbnail_path = None
        if mime_type.startswith("image/"):
            thumbnail_result = generate_thumbnail(file_path, file_dir, filename)
            if thumbnail_result:
                has_thumbnail = True
                thumbnail_path = f"/{relative_dir}/{thumbnail_result}"

        metadata: dict[str, Any] = {}
        if thumbnail_path:
            metadata["thumbnail_path"] = thumbnail_path

        resource = OrgFile(
            id=resource_id,
            job_execution_id=None,
            instance_id=None,
            instance_step_id=None,
            organization_id=organization_id,
            file_extension=file_extension,
            file_size=file_size,
            mime_type=mime_type,
            virtual_path=virtual_path,
            display_name=display_name,
            source=ResourceSource.USER_UPLOAD,
            status=ResourceStatus.AVAILABLE,
            checksum=checksum,
            metadata=metadata,
            has_thumbnail=has_thumbnail,
        )
        events = resource.clear_events()
        resource = await self.resource_repository.create(resource)

        for event in events:
            await self.event_bus.publish(event)

        return resource

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
        """
        Upload a file to a specific workflow step.

        Creates a new resource tied to a workflow instance and step.
        Files are stored in /orgs/{org_id}/instances/{instance_id}/ directory.
        Thumbnails are generated for image files.
        """
        resource_id = uuid.uuid4()

        base_name = display_name
        if "." in base_name:
            base_name = base_name.rsplit(".", 1)[0]
        safe_name = "".join(c if c.isalnum() or c in "-_." else "_" for c in base_name)
        safe_name = safe_name[:100]
        filename = f"{safe_name}{file_extension}"

        workspace_path = get_workspace_path()
        relative_dir = f"orgs/{organization_id}/instances/{instance_id}"
        virtual_path = f"/{relative_dir}/{filename}"

        file_dir = workspace_path / relative_dir
        file_dir.mkdir(parents=True, exist_ok=True)

        file_path = file_dir / filename
        hasher = hashlib.sha256()
        with open(file_path, "wb") as f:
            while chunk := file_content.read(8192):
                hasher.update(chunk)
                f.write(chunk)
        checksum = hasher.hexdigest()

        has_thumbnail = False
        thumbnail_path = None
        if mime_type.startswith("image/"):
            thumbnail_result = generate_thumbnail(file_path, file_dir, filename)
            if thumbnail_result:
                has_thumbnail = True
                thumbnail_path = f"/{relative_dir}/{thumbnail_result}"

        display_order = 0
        if instance_step_id:
            existing_resources = await self.resource_repository.list_by_instance_step(
                instance_step_id
            )
            if existing_resources:
                display_order = max(r.display_order for r in existing_resources) + 1

        metadata: dict[str, Any] = {}
        if thumbnail_path:
            metadata["thumbnail_path"] = thumbnail_path

        resource = OrgFile(
            id=resource_id,
            job_execution_id=job_execution_id,
            instance_id=instance_id,
            instance_step_id=instance_step_id,
            organization_id=organization_id,
            file_extension=file_extension,
            file_size=file_size,
            mime_type=mime_type,
            virtual_path=virtual_path,
            display_name=display_name,
            source=ResourceSource.USER_UPLOAD,
            status=ResourceStatus.AVAILABLE,
            checksum=checksum,
            metadata=metadata,
            has_thumbnail=has_thumbnail,
            display_order=display_order,
        )
        events = resource.clear_events()
        resource = await self.resource_repository.create(resource)

        for event in events:
            await self.event_bus.publish(event)

        return resource

    async def add_library_file_to_step(
        self,
        source_resource_id: uuid.UUID,
        instance_id: uuid.UUID,
        instance_step_id: uuid.UUID,
        organization_id: uuid.UUID,
    ) -> OrgFile:
        """
        Add an existing library file to a workflow step.

        Creates a new resource record that references the same underlying file
        from the library. The file is not duplicated on disk.
        """
        source_resource = await self.resource_repository.get_by_id(source_resource_id)
        if not source_resource:
            raise EntityNotFoundError(
                entity_type="OrgFile",
                entity_id=source_resource_id,
                code="Resource not found",
            )

        if source_resource.organization_id != organization_id:
            raise ValueError("Resource does not belong to this organization")

        display_order = 0
        existing_resources = await self.resource_repository.list_by_instance_step(
            instance_step_id
        )
        if existing_resources:
            display_order = max(r.display_order for r in existing_resources) + 1

        new_resource_id = uuid.uuid4()

        metadata: dict[str, Any] = {
            "original_filename": source_resource.display_name,
            "source_resource_id": str(source_resource_id),
        }
        if source_resource.metadata and source_resource.metadata.get("thumbnail_path"):
            metadata["thumbnail_path"] = source_resource.metadata["thumbnail_path"]

        resource = OrgFile(
            id=new_resource_id,
            job_execution_id=None,
            instance_id=instance_id,
            instance_step_id=instance_step_id,
            organization_id=organization_id,
            file_extension=source_resource.file_extension,
            file_size=source_resource.file_size,
            mime_type=source_resource.mime_type,
            virtual_path=source_resource.virtual_path,
            display_name=source_resource.display_name,
            source=ResourceSource.USER_UPLOAD,
            status=ResourceStatus.AVAILABLE,
            checksum=source_resource.checksum,
            metadata=metadata,
            has_thumbnail=source_resource.has_thumbnail,
            display_order=display_order,
        )
        events = resource.clear_events()
        resource = await self.resource_repository.create(resource)

        for event in events:
            await self.event_bus.publish(event)

        return resource
