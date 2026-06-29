# api/app/domain/workflow/events.py

"""Domain events for the workflow context."""
from typing import Optional
from uuid import UUID

from app.domain.common.events import DomainEvent


class WorkflowEvent(DomainEvent):
    """Base class for workflow-related events."""

    workflow_id: UUID
    organization_id: UUID


class WorkflowCreatedEvent(WorkflowEvent):
    event_type: str = "workflow.created"
    name: str
    description: Optional[str] = None
    created_by: Optional[UUID] = None


class WorkflowUpdatedEvent(WorkflowEvent):
    event_type: str = "workflow.updated"
    name: Optional[str] = None
    description: Optional[str] = None
    updated_by: Optional[UUID] = None


class WorkflowActivatedEvent(WorkflowEvent):
    event_type: str = "workflow.activated"
    activated_by: Optional[UUID] = None


class WorkflowDeactivatedEvent(WorkflowEvent):
    event_type: str = "workflow.deactivated"
    deactivated_by: Optional[UUID] = None


class WorkflowDeletedEvent(WorkflowEvent):
    event_type: str = "workflow.deleted"
    deleted_by: Optional[UUID] = None


class WorkflowStepAddedEvent(WorkflowEvent):
    event_type: str = "workflow.step_added"
    step_id: str
    step_name: str
    step_type: Optional[str] = None
    added_by: Optional[UUID] = None


class WorkflowStepRemovedEvent(WorkflowEvent):
    event_type: str = "workflow.step_removed"
    step_id: str
    removed_by: Optional[UUID] = None
