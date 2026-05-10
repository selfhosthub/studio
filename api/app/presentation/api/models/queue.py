# api/app/presentation/api/models/queue.py

"""Pydantic models for queue API operations."""

from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.config.settings import settings


class QueueBase(BaseModel):
    """Base fields for queue data."""

    name: str = Field(..., description="Queue name")
    description: Optional[str] = Field(default=None, description="Queue description")
    max_workers: int = Field(..., gt=0, description="Maximum number of workers")
    max_jobs: int = Field(..., gt=0, description="Maximum number of jobs")
    priority: int = Field(default=0, description="Queue priority")
    timeout: int = Field(..., gt=0, description="Job timeout in seconds")
    retry_limit: int = Field(default=settings.DEFAULT_MAX_RETRIES, ge=0, description="Maximum retry attempts")
    config: Dict[str, Any] = Field(
        default_factory=dict, description="Queue configuration"
    )


class QueueCreate(QueueBase):
    """Request model for creating a queue."""

    organization_id: UUID = Field(..., description="Organization identifier")


class QueueUpdate(BaseModel):
    """Request model for updating a queue."""

    name: Optional[str] = Field(default=None, description="Queue name")
    description: Optional[str] = Field(default=None, description="Queue description")
    max_workers: Optional[int] = Field(
        None, gt=0, description="Maximum number of workers"
    )
    max_jobs: Optional[int] = Field(
        default=None, gt=0, description="Maximum number of jobs"
    )
    priority: Optional[int] = Field(default=None, description="Queue priority")
    timeout: Optional[int] = Field(
        default=None, gt=0, description="Job timeout in seconds"
    )
    retry_limit: Optional[int] = Field(
        default=None, ge=0, description="Maximum retry attempts"
    )
    config: Optional[Dict[str, Any]] = Field(
        default=None, description="Queue configuration"
    )


class QueueStats(BaseModel):
    name: str = Field(..., description="Queue name")
    length: int = Field(..., ge=0, description="Number of jobs in queue")
    active_workers: int = Field(..., ge=0, description="Number of active workers")
    max_workers: int = Field(..., gt=0, description="Maximum number of workers")
    pending_jobs: int = Field(..., ge=0, description="Number of pending jobs")
    priority: int = Field(..., description="Queue priority")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")


class QueueInfo(BaseModel):
    """Detailed information about a queue."""

    id: UUID = Field(..., description="Queue identifier")
    organization_id: UUID = Field(..., description="Organization identifier")
    name: str = Field(..., description="Queue name")
    description: Optional[str] = Field(default=None, description="Queue description")
    max_workers: int = Field(..., gt=0, description="Maximum number of workers")
    active_workers: int = Field(..., ge=0, description="Number of active workers")
    max_jobs: int = Field(..., gt=0, description="Maximum number of jobs")
    pending_jobs: int = Field(..., ge=0, description="Number of pending jobs")
    priority: int = Field(..., description="Queue priority")
    timeout: int = Field(..., gt=0, description="Job timeout in seconds")
    retry_limit: int = Field(default=settings.DEFAULT_MAX_RETRIES, ge=0, description="Maximum retry attempts")
    config: Dict[str, Any] = Field(
        default_factory=dict, description="Queue configuration"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata"
    )
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")


class QueueResponse(QueueInfo):
    """Response model for queue operations."""

    pass


class QueueListResponse(BaseModel):
    queues: list[QueueResponse] = Field(..., description="List of queues")
    total: int = Field(..., ge=0, description="Total number of queues")
