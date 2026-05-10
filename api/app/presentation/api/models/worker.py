# api/app/presentation/api/models/worker.py

"""Pydantic models for worker API operations."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.domain.queue.models import WorkerStatus


class WorkerRegistrationRequest(BaseModel):
    secret: str = Field(..., description="Shared secret for worker registration")
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
    created_at: Optional[datetime] = Field(
        default=None, description="Creation timestamp"
    )
    updated_at: Optional[datetime] = Field(
        default=None, description="Last update timestamp"
    )
