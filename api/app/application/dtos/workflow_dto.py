# api/app/application/dtos/workflow_dto.py

"""DTOs for workflow operations."""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from app.application.defaults import (
    FORM_FIELD_REQUIRED_DEFAULT,
    FORM_FIELD_TYPE_DEFAULT,
)
from app.domain.workflow.models import Workflow, WorkflowStatus, WorkflowTriggerType


class WorkflowBase(BaseModel):
    name: str
    description: Optional[str] = None
    client_metadata: Optional[Dict[str, Any]] = None


class WorkflowCreate(WorkflowBase):
    """When organization_id is omitted it is derived from the caller's JWT;
    super-admins may set it explicitly to act on another tenant."""

    organization_id: Optional[uuid.UUID] = None
    created_by: Optional[uuid.UUID] = None
    steps: Optional[Dict[str, Dict[str, Any]]] = None
    status: Optional[WorkflowStatus] = None
    trigger_type: Optional[WorkflowTriggerType] = None
    trigger_input_schema: Optional[Dict[str, Any]] = None
    scope: Optional[str] = None
    webhook_method: Optional[str] = None
    webhook_auth_type: Optional[str] = None
    webhook_auth_header_name: Optional[str] = None
    webhook_config: Optional[Dict[str, Any]] = None


class WorkflowUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[WorkflowStatus] = None
    trigger_type: Optional[WorkflowTriggerType] = None
    steps: Optional[Dict[str, Dict[str, Any]]] = None
    client_metadata: Optional[Dict[str, Any]] = None
    trigger_input_schema: Optional[Dict[str, Any]] = None
    webhook_method: Optional[str] = None
    webhook_auth_type: Optional[str] = None
    webhook_auth_header_name: Optional[str] = None
    webhook_auth_header_value: Optional[str] = None
    webhook_jwt_secret: Optional[str] = None
    webhook_secret: Optional[str] = None
    webhook_config: Optional[Dict[str, Any]] = None


class WorkflowResponse(WorkflowBase):
    id: uuid.UUID
    slug: str = ""
    organization_id: uuid.UUID
    status: WorkflowStatus
    trigger_type: WorkflowTriggerType
    version: int = 1
    has_unresolved_refs: bool = False
    steps: Dict[str, Dict[str, Any]]
    webhook_token: Optional[str] = None
    # Trigger creds (HMAC secret, header-auth value, JWT secret) live in the
    # referenced OrganizationSecret, not on the domain Workflow. `from_domain` is
    # pure and leaves these at their defaults; WorkflowService enriches them off
    # the secret. On read, each secret-class field is None (unset) or the
    # "[CONFIGURED]" sentinel - never the plaintext.
    webhook_secret: Optional[str] = None
    webhook_method: str
    webhook_auth_type: str
    webhook_auth_header_name: Optional[str] = None
    webhook_auth_header_value: Optional[str] = None  # None or "[CONFIGURED]" on read
    webhook_jwt_secret: Optional[str] = None  # None or "[CONFIGURED]" on read
    webhook_config: Optional[Dict[str, Any]] = None
    trigger_input_schema: Optional[Dict[str, Any]] = None
    # Schedule trigger (read-only view of the RRULE config).
    schedule_dtstart: Optional[datetime] = None
    schedule_rrule: Optional[str] = None
    schedule_timezone: Optional[str] = None
    schedule_enabled: bool = False
    schedule_next_run_at: Optional[datetime] = None
    # API trigger: the key itself is never returned on read; this only signals
    # whether one is configured (the plaintext is shown once at create/regenerate).
    api_key_set: bool = False
    # Event trigger binding.
    event_source_workflow_id: Optional[uuid.UUID] = None
    event_on: Optional[str] = None
    created_by: Optional[uuid.UUID] = None
    scope: str
    tags: List[str] = Field(default_factory=list)
    publish_status: Optional[str] = None
    visibility: str = "private"
    instance_count: int = 0
    can_be_deleted: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @classmethod
    def from_domain(cls, workflow: Workflow) -> "WorkflowResponse":
        steps = {}
        if workflow.steps:
            for step_id, step_config in workflow.steps.items():
                steps[step_id] = step_config.model_dump(mode="json")

        return cls(
            id=workflow.id,
            name=workflow.name,
            slug=workflow.slug,
            description=workflow.description,
            organization_id=workflow.organization_id,
            status=workflow.status,
            trigger_type=workflow.trigger_type,
            version=workflow.version,
            has_unresolved_refs=workflow.has_unresolved_refs,
            steps=steps,
            webhook_token=workflow.webhook_token,
            # webhook_secret / webhook_auth_header_value / webhook_jwt_secret and
            # api_key_set are left at their defaults here; WorkflowService fills
            # them from the referenced OrganizationSecret (from_domain is pure).
            webhook_method=workflow.webhook_method,
            webhook_auth_type=workflow.webhook_auth_type,
            webhook_auth_header_name=workflow.webhook_auth_header_name,
            webhook_config=workflow.webhook_config,
            trigger_input_schema=workflow.trigger_input_schema,
            schedule_dtstart=workflow.schedule_dtstart,
            schedule_rrule=workflow.schedule_rrule,
            schedule_timezone=workflow.schedule_timezone,
            schedule_enabled=workflow.schedule_enabled,
            schedule_next_run_at=workflow.schedule_next_run_at,
            event_source_workflow_id=workflow.event_source_workflow_id,
            event_on=workflow.event_on,
            created_by=workflow.created_by,
            scope=(
                workflow.scope.value
                if hasattr(workflow.scope, "value")
                else workflow.scope
            ),
            tags=workflow.tags or [],
            publish_status=workflow.publish_status,
            visibility=(
                workflow.visibility.value
                if hasattr(workflow.visibility, "value")
                else workflow.visibility
            ),
            client_metadata=workflow.client_metadata,
            instance_count=workflow.instance_count,
            can_be_deleted=workflow.can_be_deleted(),
            created_at=workflow.created_at,
            updated_at=workflow.updated_at,
        )


FormFieldType = Literal[
    "text",
    "textarea",
    "number",
    "select",
    "multiselect",
    "checkbox",
    "combobox",
    "file",
    "date",
    "datetime",
    "json",
    "tags",
    "key-value",
]


class FormFieldConfigResponse(BaseModel):
    label: str
    placeholder: Optional[str] = None
    description: Optional[str] = None
    required: bool = FORM_FIELD_REQUIRED_DEFAULT
    field_type: FormFieldType = FORM_FIELD_TYPE_DEFAULT
    default_value: Optional[Any] = None
    options: Optional[List[Dict[str, str]]] = None
    min_length: Optional[int] = None
    max_length: Optional[int] = None
    pattern: Optional[str] = None
    min: Optional[float] = None
    max: Optional[float] = None
    accepted_file_types: Optional[List[str]] = None
    max_file_size_mb: Optional[float] = None
    size: Optional[str] = None  # small, medium, large, full

    item_type: Optional[str] = None
    key_placeholder: Optional[str] = None
    value_placeholder: Optional[str] = None
    add_label: Optional[str] = None


class FormFieldResponse(BaseModel):
    # Stable external key for trigger payloads; defaults to parameter_key.
    # Owned by FormFieldResolver; the internal identity is (step_id, parameter_key).
    field_id: str
    parameter_key: str
    step_id: str
    step_name: str
    step_order: int
    config: FormFieldConfigResponse


class WorkflowFormSchemaResponse(BaseModel):
    workflow_id: uuid.UUID
    workflow_name: str
    has_form_fields: bool
    fields: List[FormFieldResponse]
