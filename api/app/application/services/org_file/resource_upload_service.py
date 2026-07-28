# api/app/application/services/org_file/resource_upload_service.py

"""
File upload, replace, and library-to-step operations for job output resources.
"""

import hashlib
import logging
import uuid
from typing import Any, BinaryIO, Optional

logger = logging.getLogger(__name__)

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
from studio_workers.contracts.workspace_paths import (
    sanitize_step_filename,
    step_output_virtual_path,
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
        caller_thumbnail_content: Optional[BinaryIO] = None,
    ) -> OrgFile:
        """
        Upload a file to a specific workflow step.

        Creates a new resource tied to a workflow instance and step.
        Files are stored in /orgs/{org_id}/instances/{instance_id}/ directory.
        Thumbnails are generated for image files.
        """
        resource_id = uuid.uuid4()

        filename = sanitize_step_filename(display_name, file_extension)

        workspace_path = get_workspace_path()
        relative_dir = f"orgs/{organization_id}/instances/{instance_id}"
        virtual_path = step_output_virtual_path(
            str(organization_id), str(instance_id), filename
        )

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
        if caller_thumbnail_content is not None:
            # Caller (e.g. shs-video worker) supplied a pre-extracted thumbnail -
            # the API can't extract a video poster frame itself (no ffmpeg).
            # Write it under the same naming convention generate_thumbnail uses.
            name_part = filename.rsplit(".", 1)[0]
            thumb_filename = f"{name_part}-thumbnail.jpg"
            thumb_full = file_dir / thumb_filename
            try:
                with open(thumb_full, "wb") as tf:
                    while chunk := caller_thumbnail_content.read(8192):
                        tf.write(chunk)
                has_thumbnail = True
                thumbnail_path = f"/{relative_dir}/{thumb_filename}"
            except Exception as e:
                logger.warning(f"Failed to write caller-supplied thumbnail for {file_path}: {e}")
        elif mime_type.startswith("image/"):
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

    async def register_step_file_in_place(
        self,
        instance_id: uuid.UUID,
        step_key: str,
        organization_id: uuid.UUID,
        expected_size: int,
        expected_checksum: str,
        mime_type: str,
        file_extension: str,
        display_name: str,
        job_execution_id: Optional[uuid.UUID] = None,
        instance_step_id: Optional[uuid.UUID] = None,
        has_caller_thumbnail: bool = False,
    ) -> OrgFile:
        """Register a file the worker already wrote at the canonical path.

        Counterpart to `upload_file_to_step` for the `storage_mode=local`
        path: the worker put the bytes on disk; the API just stats,
        verifies size+checksum, and creates the OrgFile row.

        Raises:
            FileNotFoundError: file is absent at the derived path
                (worker lied about local mode, race with cleanup, or
                bad mount). Caller should surface a classified 404 so
                the worker falls back to multipart upload.
            ValueError: size or checksum mismatch - the file on disk is
                not what the worker said it wrote. Treated as a 422.
        """
        resource_id = uuid.uuid4()

        filename = sanitize_step_filename(display_name, file_extension)
        workspace_path = get_workspace_path()
        relative_dir = f"orgs/{organization_id}/instances/{instance_id}"
        virtual_path = step_output_virtual_path(
            str(organization_id), str(instance_id), filename
        )
        file_dir = workspace_path / relative_dir
        file_path = file_dir / filename

        if not file_path.is_file():
            raise FileNotFoundError(
                f"Expected worker-written file missing at {virtual_path}"
            )

        actual_size = file_path.stat().st_size
        if actual_size != expected_size:
            raise ValueError(
                f"Size mismatch for {virtual_path}: "
                f"expected {expected_size}, got {actual_size}"
            )

        hasher = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(8192):
                hasher.update(chunk)
        actual_checksum = hasher.hexdigest()
        if actual_checksum != expected_checksum:
            raise ValueError(
                f"Checksum mismatch for {virtual_path}"
            )

        has_thumbnail = False
        thumbnail_path: Optional[str] = None
        if has_caller_thumbnail:
            # Worker wrote `{base}-thumbnail.jpg` next to the file.
            name_part = filename.rsplit(".", 1)[0]
            thumb_filename = f"{name_part}-thumbnail.jpg"
            thumb_full = file_dir / thumb_filename
            if thumb_full.is_file():
                has_thumbnail = True
                thumbnail_path = f"/{relative_dir}/{thumb_filename}"
            else:
                logger.warning(
                    f"Worker declared thumbnail but {thumb_full} is absent"
                )
        elif mime_type.startswith("image/"):
            # Same fallback as the multipart path: generate from the file.
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
            file_size=actual_size,
            mime_type=mime_type,
            virtual_path=virtual_path,
            display_name=display_name,
            source=ResourceSource.USER_UPLOAD,
            status=ResourceStatus.AVAILABLE,
            checksum=actual_checksum,
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
