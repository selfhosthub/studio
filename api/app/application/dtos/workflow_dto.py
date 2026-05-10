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
    blueprint_id: Optional[uuid.UUID] = None
    steps: Optional[Dict[str, Dict[str, Any]]] = None
    status: Optional[WorkflowStatus] = None
    trigger_type: Optional[WorkflowTriggerType] = None
    trigger_input_schema: Optional[Dict[str, Any]] = None
    scope: Optional[str] = None


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


class WorkflowResponse(WorkflowBase):
    id: uuid.UUID
    organization_id: uuid.UUID
    blueprint_id: Optional[uuid.UUID] = None
    blueprint_name: Optional[str] = None
    status: WorkflowStatus
    trigger_type: WorkflowTriggerType
    version: int
    steps: Dict[str, Dict[str, Any]]
    webhook_token: Optional[str] = None
    # On read, this is either None (no secret configured) or "[CONFIGURED]"
    # (secret present but withheld). Plaintext is returned exactly once at
    # creation/regeneration time via the dedicated token response.
    webhook_secret: Optional[str] = None
    webhook_method: str
    webhook_auth_type: str
    webhook_auth_header_name: Optional[str] = None
    webhook_auth_header_value: Optional[str] = None  # masked in response
    webhook_jwt_secret: Optional[str] = None  # masked in response
    trigger_input_schema: Optional[Dict[str, Any]] = None
    created_by: Optional[uuid.UUID] = None
    scope: str
    tags: List[str] = Field(default_factory=list)
    publish_status: Optional[str] = None
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
            description=workflow.description,
            organization_id=workflow.organization_id,
            blueprint_id=workflow.blueprint_id,
            blueprint_name=workflow.blueprint_name,
            status=workflow.status,
            trigger_type=workflow.trigger_type,
            version=workflow.version,
            steps=steps,
            webhook_token=workflow.webhook_token,
            # Sentinel value - plaintext is never returned on read.
            webhook_secret=("[CONFIGURED]" if workflow.webhook_secret else None),
            webhook_method=workflow.webhook_method,
            webhook_auth_type=workflow.webhook_auth_type,
            webhook_auth_header_name=workflow.webhook_auth_header_name,
            webhook_auth_header_value=workflow.webhook_auth_header_value,
            webhook_jwt_secret=workflow.webhook_jwt_secret,
            trigger_input_schema=workflow.trigger_input_schema,
            created_by=workflow.created_by,
            scope=(
                workflow.scope.value
                if hasattr(workflow.scope, "value")
                else workflow.scope
            ),
            tags=workflow.tags or [],
            publish_status=workflow.publish_status,
            client_metadata=workflow.client_metadata,
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
