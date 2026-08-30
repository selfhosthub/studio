# api/app/presentation/api/models/worker.py

"""Pydantic models for worker API operations."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.domain.queue.models import WorkerStatus


class WorkerRegistrationRequest(BaseModel):
    secret: str = Field(
        ...,
        description="The fleet shared secret, or an enrollment credential (shswrk_ prefix)",
    )
    worker_version: Optional[str] = Field(
        default=None,
        description="studio-workers version the worker runs; checked against the API's expected version",
    )
    name: str = Field(..., min_length=1, max_length=255, description="Worker name")
    queue_id: Optional[UUID] = Field(
        None, description="Queue ID this worker services (optional for general workers)"
    )
    capabilities: Dict[str, Any] = Field(
        default_factory=dict, description="Worker capabilities"
    )
    queue_labels: List[str] = Field(
        default_factory=list, description="Labels for queue matching"
    )
    queues: List[str] = Field(
        default_factory=list,
        description="Queues this worker actually serves (claim sweep list)",
    )
    ip_address: Optional[str] = Field(default=None, description="Worker IP address")
    hostname: Optional[str] = Field(default=None, description="Worker hostname")
    cpu_percent: Optional[float] = Field(
        default=None, description="CPU utilization percentage"
    )
    memory_percent: Optional[float] = Field(
        default=None, description="Memory utilization percentage"
    )
    memory_used_mb: Optional[int] = Field(default=None, description="Memory used in MB")
    memory_total_mb: Optional[int] = Field(
        default=None, description="Total memory in MB"
    )
    disk_percent: Optional[float] = Field(
        default=None, description="Disk utilization percentage"
    )
    gpu_percent: Optional[float] = Field(
        default=None, description="GPU utilization percentage"
    )
    gpu_memory_percent: Optional[float] = Field(
        default=None, description="GPU memory utilization percentage"
    )
    storage_mode: str = Field(
        default="remote",
        description=(
            "'local' if the worker shares the API's /workspace mount (writes "
            "results directly); 'remote' otherwise (uploads via HTTP)."
        ),
    )


class WorkerRegistrationResponse(BaseModel):
    """Response model for worker registration."""

    worker_id: UUID = Field(..., description="Newly registered worker ID")
    token: str = Field(
        ...,
        description="JWT token for job claims (expires in 5 min, refresh via heartbeat)",
    )


class WorkerHeartbeatRequest(BaseModel):
    status: str = Field(..., description="Worker status: 'idle' or 'busy'")
    current_job_id: Optional[UUID] = Field(
        default=None, description="Currently processing job ID"
    )
    cpu_percent: Optional[float] = Field(
        default=None, description="CPU utilization percentage"
    )
    memory_percent: Optional[float] = Field(
        default=None, description="Memory utilization percentage"
    )
    memory_used_mb: Optional[int] = Field(default=None, description="Memory used in MB")
    memory_total_mb: Optional[int] = Field(
        default=None, description="Total memory in MB"
    )
    disk_percent: Optional[float] = Field(
        default=None, description="Disk utilization percentage"
    )
    gpu_percent: Optional[float] = Field(
        default=None, description="GPU utilization percentage"
    )
    gpu_memory_percent: Optional[float] = Field(
        default=None, description="GPU memory utilization percentage"
    )
    storage_mode: Optional[str] = Field(
        default=None,
        description=(
            "Current workspace access mode ('local' or 'remote'). Omitting "
            "leaves the stored value unchanged - older workers that don't "
            "send the field stay on whatever they declared at registration."
        ),
    )


class WorkerHeartbeatResponse(BaseModel):
    """Response model for worker heartbeat."""

    status: str = Field(default="ok", description="Heartbeat acknowledgment")
    deregistered: bool = Field(
        default=False,
        description="True if worker has been deregistered by admin and should stop",
    )
    token: Optional[str] = Field(
        default=None,
        description="Refreshed JWT token (only included if worker is still registered)",
    )
    comfyui_catalog_hash: Optional[str] = Field(
        default=None,
        description="Current ComfyUI catalog hash (only for workers serving comfyui queues)",
    )


class WorkerDeregistrationRequest(BaseModel):
    secret: str = Field(..., description="Shared secret for authentication")


class WorkerDeregistrationResponse(BaseModel):
    """Response model for worker deregistration."""

    status: str = Field(default="ok", description="Deregistration acknowledgment")
    message: str = Field(..., description="Deregistration result message")


class WorkerResponse(BaseModel):
    """Response model for worker data (used in queue stats)."""

    id: UUID = Field(..., description="Worker identifier")
    name: str = Field(..., description="Worker name")
    queue_id: UUID = Field(..., description="Queue identifier")
    status: WorkerStatus = Field(..., description="Worker status")
    capabilities: Dict[str, Any] = Field(..., description="Worker capabilities")
    queue_labels: List[str] = Field(..., description="Queue labels")
    last_heartbeat: Optional[datetime] = Field(
        default=None, description="Last heartbeat timestamp"
    )
    current_job_id: Optional[UUID] = Field(
        default=None, description="Currently processing job ID"
    )
    jobs_completed: int = Field(..., ge=0, description="Total jobs completed")
    ip_address: Optional[str] = Field(default=None, description="Worker IP address")
    hostname: Optional[str] = Field(default=None, description="Worker hostname")
    cpu_percent: Optional[float] = Field(
        default=None, description="CPU utilization percentage"
    )
    memory_percent: Optional[float] = Field(
        default=None, description="Memory utilization percentage"
    )
    memory_used_mb: Optional[int] = Field(default=None, description="Memory used in MB")
    memory_total_mb: Optional[int] = Field(
        default=None, description="Total memory in MB"
    )
    disk_percent: Optional[float] = Field(
        default=None, description="Disk utilization percentage"
    )
    gpu_percent: Optional[float] = Field(
        default=None, description="GPU utilization percentage"
    )
    gpu_memory_percent: Optional[float] = Field(
        default=None, description="GPU memory utilization percentage"
    )
    storage_mode: str = Field(
        default="remote",
        description="Workspace access mode declared by the worker ('local' or 'remote').",
    )
    created_at: Optional[datetime] = Field(
        default=None, description="Creation timestamp"
    )
    updated_at: Optional[datetime] = Field(
        default=None, description="Last update timestamp"
    )


class WorkerEnrollRequest(BaseModel):
    join_token: str = Field(..., description="Single-use join token from a super admin")
    label: Optional[str] = Field(
        default=None,
        max_length=255,
        description="Name for this worker's credential; defaults to the token's label",
    )


class WorkerEnrollResponse(BaseModel):
    credential: str = Field(..., description="The worker's credential; shown once, never again")
    queues: List[str] = Field(..., description="Queues this credential may register for")


class JoinTokenCreateRequest(BaseModel):
    label: str = Field(..., min_length=1, max_length=255)
    queues: List[str] = Field(..., description="Queues a worker enrolling with this token may serve")
    ttl_seconds: int = Field(
        default=900, ge=60, le=86400, description="How long the token stays claimable"
    )


class JoinTokenCreateResponse(BaseModel):
    id: UUID
    token: str = Field(..., description="Shown once; only its hash is stored")
    expires_at: datetime


class JoinTokenResponse(BaseModel):
    id: UUID
    label: str
    queues: List[str]
    expires_at: datetime
    used_at: Optional[datetime] = None
    created_at: datetime


class WorkerEnrollmentResponse(BaseModel):
    id: UUID
    label: str
    queues: List[str]
    revoked_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None
    created_at: datetime
