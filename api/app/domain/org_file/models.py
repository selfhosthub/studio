# api/app/domain/org_file/models.py

"""Domain model for resources (images, videos, docs, etc.) generated or downloaded by job executions."""

import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from pydantic import Field, field_validator

from app.domain.common.base_entity import AggregateRoot
from app.domain.common.exceptions import InvalidStateTransition, ValidationError


class ResourceSource(str, Enum):
    JOB_GENERATED = "job_generated"
    JOB_DOWNLOAD = "job_download"
    USER_UPLOAD = "user_upload"


class ResourceStatus(str, Enum):
    PENDING = "pending"
    GENERATING = "generating"
    AVAILABLE = "available"
    FAILED = "failed"
    ORPHANED = "orphaned"
    DELETED = "deleted"


class OrgFile(AggregateRoot):
    """Aggregate for job-generated or downloaded resource files. Stored flat with human-readable names; thumbnails get a -thumbnail suffix."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    job_execution_id: Optional[uuid.UUID] = None  # None for standalone user uploads
    instance_id: Optional[uuid.UUID] = None  # None for standalone user uploads
    instance_step_id: Optional[uuid.UUID] = None
    organization_id: uuid.UUID

    file_extension: str  # includes the leading dot
    file_size: int
    mime_type: str
    checksum: Optional[str] = None  # SHA256

    # Virtual organization for the UI; not a real filesystem path.
    virtual_path: str
    display_name: str

    source: ResourceSource

    # Provider metadata for job_download source.
    provider_id: Optional[uuid.UUID] = None
    provider_resource_id: Optional[str] = None
    provider_url: Optional[str] = None
    download_timestamp: Optional[datetime] = None

    status: ResourceStatus = ResourceStatus.PENDING
    metadata: Dict[str, Any] = Field(default_factory=dict)
    has_thumbnail: bool = False

    display_order: int = 0

    # The active variant for its (step, iteration_index) slot; downstream uses only selected.
    is_selected: bool = True

    @field_validator("status", mode="before")
    @classmethod
    def convert_status_to_enum(cls, v):
        if isinstance(v, str) and not isinstance(v, ResourceStatus):
            return ResourceStatus(v)
        return v

    @classmethod
    def create(
        cls,
        job_execution_id: Optional[uuid.UUID],
        instance_id: Optional[uuid.UUID],
        organization_id: uuid.UUID,
        file_extension: str,
        file_size: int,
        mime_type: str,
        virtual_path: str,
        display_name: str,
        source: ResourceSource,
        checksum: Optional[str] = None,
        provider_id: Optional[uuid.UUID] = None,
        provider_resource_id: Optional[str] = None,
        provider_url: Optional[str] = None,
        download_timestamp: Optional[datetime] = None,
        metadata: Optional[Dict[str, Any]] = None,
        has_thumbnail: bool = False,
        instance_step_id: Optional[uuid.UUID] = None,
        display_order: int = 0,
    ) -> "OrgFile":
        if display_order < 0:
            raise ValidationError(
                message="Display order cannot be negative",
                code="INVALID_DISPLAY_ORDER",
            )

        resource_id = uuid.uuid4()

        resource = cls(
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
            source=source,
            status=ResourceStatus.PENDING,
            checksum=checksum,
            provider_id=provider_id,
            provider_resource_id=provider_resource_id,
            provider_url=provider_url,
            download_timestamp=download_timestamp,
            metadata=metadata or {},
            has_thumbnail=has_thumbnail,
            display_order=display_order,
        )

        return resource

    def mark_available(self, has_thumbnail: bool = False) -> None:
        if (
            self.status != ResourceStatus.GENERATING
            and self.status != ResourceStatus.PENDING
        ):
            raise InvalidStateTransition(
                message=f"Cannot mark resource as available from status {self.status.value}",
                code="INVALID_RESOURCE_TRANSITION",
                context={
                    "entity_type": "OrgFile",
                    "entity_id": str(self.id),
                    "current_state": self.status.value,
                    "attempted_state": ResourceStatus.AVAILABLE.value,
                },
            )

        self.status = ResourceStatus.AVAILABLE
        self.has_thumbnail = has_thumbnail

    def mark_failed(self, error: str) -> None:
        self.status = ResourceStatus.FAILED
        self.metadata["error"] = error
        self.metadata["failed_at"] = datetime.now(UTC).isoformat()

    def mark_orphaned(self) -> None:
        """Job failed mid-execution; resource is incomplete."""
        self.status = ResourceStatus.ORPHANED

    def soft_delete(self) -> None:
        self.status = ResourceStatus.DELETED

    def set_display_order(self, order: int) -> None:
        if order < 0:
            raise ValidationError(
                message="Display order cannot be negative",
                code="INVALID_DISPLAY_ORDER",
            )
        self.display_order = order

    def set_selected(self, selected: bool) -> None:
        """Mark this variant as the selected one for its slot (or deselect it)."""
        self.is_selected = selected

    @staticmethod
    def slot_key(resource: "OrgFile") -> Any:
        """The (iteration_index) slot a variant belongs to; siblings share it."""
        return (resource.metadata or {}).get("iteration_index")

    @staticmethod
    def enforce_single_selected_per_slot(
        resources: List["OrgFile"],
        fresh_ids: Set[uuid.UUID],
    ) -> List["OrgFile"]:
        """Make exactly one variant selected per slot touched by `fresh_ids`.

        The newest fresh variant (by display_order, then id) wins its slot; every
        other variant in that slot — batch siblings and prior generations — is
        deselected. Returns the resources whose is_selected changed."""
        fresh = [r for r in resources if r.id in fresh_ids]
        if not fresh:
            return []
        by_slot: Dict[Any, List["OrgFile"]] = {}
        for r in resources:
            by_slot.setdefault(OrgFile.slot_key(r), []).append(r)
        changed: List["OrgFile"] = []
        for slot in {OrgFile.slot_key(r) for r in fresh}:
            siblings = by_slot.get(slot, [])
            fresh_in_slot = [r for r in siblings if r.id in fresh_ids]
            primary = sorted(
                fresh_in_slot, key=lambda r: (r.display_order, str(r.id))
            )[0]
            for resource in siblings:
                want = resource.id == primary.id
                if resource.is_selected != want:
                    resource.set_selected(want)
                    changed.append(resource)
        return changed

    def replace_file(
        self,
        file_size: int,
        mime_type: str,
        file_extension: str,
        virtual_path: str,
        display_name: str,
        checksum: str,
        source: ResourceSource,
    ) -> None:
        """Swap file content (e.g. user-uploaded replacement). Preserves resource identity and workflow position."""
        if self.status == ResourceStatus.DELETED:
            raise InvalidStateTransition(
                message="Cannot replace a deleted resource",
                code="INVALID_RESOURCE_REPLACE",
                context={
                    "entity_type": "OrgFile",
                    "entity_id": str(self.id),
                    "current_state": self.status.value,
                    "attempted_state": ResourceStatus.AVAILABLE.value,
                },
            )

        self.file_size = file_size
        self.mime_type = mime_type
        self.file_extension = file_extension
        self.virtual_path = virtual_path
        self.display_name = display_name
        self.checksum = checksum
        self.source = source
        self.status = ResourceStatus.AVAILABLE
        self.has_thumbnail = False  # new file needs a fresh thumbnail
        self.metadata["replaced_at"] = datetime.now(UTC).isoformat()

    @classmethod
    def create_user_upload(
        cls,
        organization_id: uuid.UUID,
        file_extension: str,
        file_size: int,
        mime_type: str,
        display_name: str,
        checksum: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "OrgFile":
        """Standalone user upload, not tied to any workflow or job. Created in AVAILABLE status."""
        resource_id = uuid.uuid4()

        return cls(
            id=resource_id,
            job_execution_id=None,
            instance_id=None,
            instance_step_id=None,
            organization_id=organization_id,
            file_extension=file_extension,
            file_size=file_size,
            mime_type=mime_type,
            virtual_path=f"/uploads/{display_name}",
            display_name=display_name,
            source=ResourceSource.USER_UPLOAD,
            status=ResourceStatus.AVAILABLE,
            checksum=checksum,
            metadata=metadata or {"uploaded_at": datetime.now(UTC).isoformat()},
            has_thumbnail=False,
        )
