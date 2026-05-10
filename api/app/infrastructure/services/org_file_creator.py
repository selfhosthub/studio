# api/app/infrastructure/services/org_file_creator.py

"""Creates job output resource records from downloaded file metadata."""

import logging
from datetime import datetime, UTC
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.org_file.models import (
    OrgFile,
    ResourceSource,
    ResourceStatus,
)
from app.infrastructure.repositories.org_file_repository import (
    SQLAlchemyOrgFileRepository,
)

logger = logging.getLogger(__name__)


class OrgFileCreator:
    """Creates OrgFile records from downloaded file metadata."""

    MIME_TYPE_MAP = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
        ".mp4": "video/mp4",
        ".pdf": "application/pdf",
    }

    async def create_from_downloaded_files(
        self,
        session: AsyncSession,
        job_execution_id: UUID,
        instance_id: UUID,
        organization_id: UUID,
        downloaded_files: List[Dict[str, Any]],
        instance_step_id: Optional[UUID] = None,
    ) -> int:
        if not downloaded_files:
            return 0

        resource_repo = SQLAlchemyOrgFileRepository(session)
        created_count = 0

        for file_info in downloaded_files:
            try:
                resource = self._build_resource(
                    file_info=file_info,
                    job_execution_id=job_execution_id,
                    instance_id=instance_id,
                    organization_id=organization_id,
                    instance_step_id=instance_step_id,
                )
                await resource_repo.create(resource)
                created_count += 1
                logger.debug(
                    f"Created OrgFile for {file_info.get('filename', 'unknown')} "
                    f"(thumbnail: {file_info.get('has_thumbnail', False)})"
                )
            except Exception as e:
                logger.warning(f"Failed to create resource for {file_info}: {e}")
                continue

        if created_count > 0:
            logger.debug(
                f"Created {created_count} OrgFile records for job {job_execution_id}"
            )

        return created_count

    def _build_resource(
        self,
        file_info: Dict[str, Any],
        job_execution_id: UUID,
        instance_id: UUID,
        organization_id: UUID,
        instance_step_id: Optional[UUID],
    ) -> OrgFile:
        filename = file_info.get("filename", "unknown")
        file_size = file_info.get("file_size", 0)
        checksum = file_info.get("checksum")
        virtual_path = file_info.get("virtual_path", "")
        source_url = file_info.get("source_url")
        has_thumbnail = file_info.get("has_thumbnail", False)
        thumbnail_path = file_info.get("thumbnail_path")

        file_extension, mime_type = self._detect_file_type(filename)
        metadata = self._build_metadata(file_info, thumbnail_path)
        display_name = file_info.get("display_name") or "Image"

        resource = OrgFile.create(
            job_execution_id=job_execution_id,
            instance_id=instance_id,
            organization_id=organization_id,
            file_extension=file_extension,
            file_size=file_size,
            mime_type=mime_type,
            virtual_path=virtual_path,
            display_name=display_name,
            source=ResourceSource.JOB_DOWNLOAD,
            checksum=checksum,
            provider_url=source_url,
            download_timestamp=datetime.now(UTC),
            metadata=metadata,
            has_thumbnail=has_thumbnail,
            instance_step_id=instance_step_id,
        )

        resource.status = ResourceStatus.AVAILABLE
        return resource

    def _detect_file_type(self, filename: str) -> tuple[str, str]:
        file_extension = ""
        mime_type = "application/octet-stream"

        if "." in filename:
            file_extension = "." + filename.rsplit(".", 1)[-1].lower()
            mime_type = self.MIME_TYPE_MAP.get(file_extension, "application/octet-stream")

        return file_extension, mime_type

    def _build_metadata(
        self,
        file_info: Dict[str, Any],
        thumbnail_path: Optional[str],
    ) -> Dict[str, Any]:
        metadata: Dict[str, Any] = {"index": file_info.get("index", 0)}

        # iteration_index comes from the worker's per-file dict (file_info),
        # not from Instance.output_data.
        iteration_index = file_info.get("iteration_index")
        if iteration_index is not None:
            metadata["iteration_index"] = iteration_index

        if thumbnail_path:
            metadata["thumbnail_path"] = thumbnail_path

        seed = file_info.get("seed")
        if seed is not None:
            metadata["seed"] = seed

        original_filename = file_info.get("original_filename")
        if original_filename:
            metadata["original_filename"] = original_filename

        return metadata
