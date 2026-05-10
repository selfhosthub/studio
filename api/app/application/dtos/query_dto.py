# api/app/application/dtos/query_dto.py

"""Query DTOs for read operations."""
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class QueryBase(BaseModel):
    limit: int = Field(default=10, ge=1, le=100)
    offset: int = Field(default=0, ge=0)
    sort_by: Optional[str] = None
    sort_order: str = Field(default="desc", pattern="^(asc|desc)$")
    filters: Dict[str, Any] = Field(default_factory=dict)


class EntityQuery(QueryBase):
    entity_id: uuid.UUID


class OrganizationQuery(QueryBase):
    organization_id: uuid.UUID


class UserQuery(QueryBase):
    user_id: uuid.UUID


class TimeRangeQuery(QueryBase):
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None


class SearchQuery(QueryBase):
    search_term: Optional[str] = None
    search_fields: List[str] = Field(default_factory=list)


class WorkflowQuery(OrganizationQuery):
    status: Optional[str] = None
    blueprint_id: Optional[uuid.UUID] = None
    created_by: Optional[uuid.UUID] = None


class InstanceQuery(OrganizationQuery, TimeRangeQuery):
    workflow_id: Optional[uuid.UUID] = None
    status: Optional[str] = None
    user_id: Optional[uuid.UUID] = None


class BlueprintQuery(OrganizationQuery):
    category: Optional[str] = None
    published: Optional[bool] = None
    created_by: Optional[uuid.UUID] = None


class QueueQuery(OrganizationQuery):
    queue_type: Optional[str] = None
    status: Optional[str] = None


class JobQuery(OrganizationQuery, TimeRangeQuery):
    instance_id: Optional[uuid.UUID] = None
    status: Optional[str] = None
    worker_id: Optional[uuid.UUID] = None


class NotificationQuery(UserQuery, TimeRangeQuery):
    category: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    unread_only: bool = False


class ProviderQuery(OrganizationQuery):
    provider_type: Optional[str] = None
    service_type: Optional[str] = None
    status: Optional[str] = None
    is_global: Optional[bool] = None


class WebhookQuery(OrganizationQuery):
    resource_id: Optional[uuid.UUID] = None
    resource_type: Optional[str] = None
    status: Optional[str] = None
    event_type: Optional[str] = None


class AuditLogQuery(OrganizationQuery, TimeRangeQuery):
    user_id: Optional[uuid.UUID] = None
    action: Optional[str] = None
    resource_type: Optional[str] = None
    resource_id: Optional[uuid.UUID] = None


class MetricsQuery(OrganizationQuery, TimeRangeQuery):
    metric_type: str
    aggregation: str = "sum"  # sum, avg, min, max, count
    group_by: Optional[str] = None
    interval: Optional[str] = None  # hour, day, week, month


class PaginatedResponse(BaseModel):
    items: List[Any]
    total: int
    limit: int
    offset: int
    has_more: bool

    @classmethod
    def create(
        cls, items: List[Any], total: int, limit: int, offset: int
    ) -> "PaginatedResponse":
        return cls(
            items=items,
            total=total,
            limit=limit,
            offset=offset,
            has_more=(offset + len(items)) < total,
        )


class BatchResponse(BaseModel):
    # Pyright cannot infer Field(default_factory=list) return as List[UUID]/List[Dict].
    succeeded: List[uuid.UUID] = Field(default_factory=list)  # type: ignore[assignment]
    failed: List[Dict[str, Any]] = Field(default_factory=list)  # type: ignore[assignment]
    total: int = 0
    success_count: int = 0
    failure_count: int = 0
