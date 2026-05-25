# api/app/application/dtos/org_file_dto.py

"""DTOs for job output resources."""

from datetime import UTC, datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.org_file.models import (
    OrgFile,
    ResourceSource,
    ResourceStatus,
)


class OrgFileResponse(BaseModel):
    id: UUID
    job_execution_id: Optional[UUID] = None  # Nullable for standalone uploads
    instance_id: Optional[UUID] = None  # Nullable for standalone uploads
    organization_id: UUID

    file_extension: str
    file_size: int
    mime_type: str
    checksum: Optional[str] = None

    virtual_path: str
    display_name: str

    source: ResourceSource

    provider_id: Optional[UUID] = None
    provider_resource_id: Optional[str] = None
    provider_url: Optional[str] = None
    download_timestamp: Optional[datetime] = None

    status: ResourceStatus
    metadata: Dict[str, Any] = Field(default_factory=dict)
    has_thumbnail: bool = False

    display_order: int = 0

    download_url: str
    preview_url: Optional[str] = None

    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_domain(
        cls, resource: OrgFile, api_base_url: str = ""
    ) -> "OrgFileResponse":
        download_url = f"{api_base_url}/api/v1/files/{resource.id}/download"
        preview_url = None
        if resource.has_thumbnail:
            preview_url = f"{api_base_url}/api/v1/files/{resource.id}/preview"

        return cls(
            id=resource.id,
            job_execution_id=resource.job_execution_id,
            instance_id=resource.instance_id,
            organization_id=resource.organization_id,
            file_extension=resource.file_extension,
            file_size=resource.file_size,
            mime_type=resource.mime_type,
            checksum=resource.checksum,
            virtual_path=resource.virtual_path,
            display_name=resource.display_name,
            source=resource.source,
            provider_id=resource.provider_id,
            provider_resource_id=resource.provider_resource_id,
            provider_url=resource.provider_url,
            download_timestamp=resource.download_timestamp,
            status=resource.status,
            metadata=resource.metadata,
            has_thumbnail=resource.has_thumbnail,
            display_order=resource.display_order,
            download_url=download_url,
            preview_url=preview_url,
            created_at=resource.created_at or datetime.now(UTC),
            updated_at=resource.updated_at or datetime.now(UTC),
        )

    model_config = ConfigDict(from_attributes=True)


class ResourceMetadata(BaseModel):
    width: Optional[int] = None
    height: Optional[int] = None
    duration: Optional[float] = None
    pages: Optional[int] = None
    extra: Dict[str, Any] = Field(default_factory=dict)


class JobStatusWebhookPayload(BaseModel):
    """Webhook payload from worker reporting job status and resources."""

    job_id: UUID
    status: str
    result: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    resources: List["ResourcePayload"] = Field(default_factory=list)


class ResourcePayload(BaseModel):
    display_name: str
    file_size: int
    mime_type: str
    source: ResourceSource
    file_extension: str
    checksum: Optional[str] = None
    suggested_virtual_path: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    provider_metadata: Optional["ProviderMetadata"] = None


class ProviderMetadata(BaseModel):
    provider_id: Optional[UUID] = None
    provider_resource_id: Optional[str] = None
    provider_url: Optional[str] = None
