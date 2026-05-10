# api/app/presentation/api/workflows.py

"""Workflow management API endpoints."""

import logging
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from app.config.settings import settings
from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Path,
    Query,
    UploadFile,
    status,
)
from fastapi.responses import Response
from pydantic import BaseModel

from app.application.dtos.workflow_dto import (
    FormFieldConfigResponse,
    FormFieldResponse,
    FormFieldType,
    WorkflowCreate,
    WorkflowFormSchemaResponse,
    WorkflowResponse,
    WorkflowUpdate,
)
from app.application.interfaces.exceptions import DuplicateEntityError
from app.domain.common.exceptions import BusinessRuleViolation, EntityNotFoundError
from app.application.services.workflow_credential_service import (
    CredentialCheckResult as CredentialCheckResponse,
    WorkflowCredentialService,
)
from app.application.services.workflow_service import WorkflowService
from app.domain.prompt.repository import PromptRepository
from app.domain.provider.repository import (
    ProviderCredentialRepository,
    ProviderRepository,
    ProviderServiceRepository,
)
from app.presentation.api.dependencies import (
    CurrentUser,
    get_current_user,
    get_effective_org_id,
    get_prompt_repository,
    get_provider_credential_repository,
    get_provider_repository,
    get_provider_service_repository,
    get_workflow_service,
    require_admin,
    require_user,
    validate_organization_access,
)
from app.infrastructure.errors import safe_error_message

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/", response_model=WorkflowResponse, status_code=status.HTTP_201_CREATED)
async def create_workflow(
    workflow: WorkflowCreate,
    user: CurrentUser = Depends(get_current_user),
    service: WorkflowService = Depends(get_workflow_service),
):
    """
    Create a new workflow.

    The organization_id is optional in the request body. If not provided,
    it will be derived from the user's JWT token. Super-admins can specify
    a different organization_id to create workflows for other organizations.
    """
    # Get effective organization ID (from request or derived from user token)
    effective_org_id = get_effective_org_id(
        str(workflow.organization_id) if workflow.organization_id else None, user
    )

    # Update workflow with the effective organization_id and creator
    workflow.organization_id = UUID(effective_org_id)
    workflow.created_by = UUID(user["id"])

    try:
        return await service.create_workflow(workflow)
    except DuplicateEntityError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=safe_error_message(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=safe_error_message(e))


@router.get("/", response_model=List[WorkflowResponse])
async def list_workflows(
    organization_id: Optional[UUID] = Query(
        None,
        description="Organization ID to filter by (optional, derived from user token if not provided)",
    ),
    scope: Optional[str] = Query(
        None,
        description="Filter by scope: 'personal' or 'organization'",
    ),
    skip: int = Query(0, ge=0),
    limit: int = Query(settings.API_PAGE_LIMIT_DEFAULT, ge=1, le=settings.API_PAGE_MAX),
    user: CurrentUser = Depends(get_current_user),
    service: WorkflowService = Depends(get_workflow_service),
):
    """
    List workflows for an organization with pagination.

    Use scope=personal to list only the current user's personal workflows.
    Use scope=organization to list only organization-level workflows.
    Omit scope to list all workflows (backward compatible).
    """
    effective_org_id = get_effective_org_id(
        str(organization_id) if organization_id else None, user
    )
    org_uuid = UUID(effective_org_id)

    if scope == "personal":
        workflows = await service.workflow_repository.list_personal_workflows(
            org_uuid, UUID(user["id"]), skip=skip, limit=limit
        )
    elif scope == "organization":
        workflows = await service.workflow_repository.list_organization_workflows(
            org_uuid, skip=skip, limit=limit
        )
    else:
        workflows = await service.workflow_repository.list_by_organization(
            org_uuid, skip=skip, limit=limit
        )
    return [WorkflowResponse.from_domain(w) for w in workflows]


@router.get("/by-blueprint/{blueprint_id}", response_model=List[WorkflowResponse])
async def list_workflows_by_blueprint(
    blueprint_id: UUID = Path(...),
    skip: int = Query(0, ge=0),
    limit: int = Query(settings.API_PAGE_LIMIT_DEFAULT, ge=1, le=settings.API_PAGE_MAX),
    user: CurrentUser = Depends(get_current_user),
    service: WorkflowService = Depends(get_workflow_service),
):
    """
    List workflows derived from a blueprint with pagination.

    Users can only list workflows for blueprints they have access to.
    Super-admins can access all workflows.
    """
    workflows = await service.workflow_repository.list_by_blueprint(
        blueprint_id, skip=skip, limit=limit
    )

    if workflows and len(workflows) > 0:
        first_workflow = workflows[0]
        await validate_organization_access(str(first_workflow.organization_id), user)

    return [WorkflowResponse.from_domain(w) for w in workflows]


@router.get("/pending-publish", response_model=List[WorkflowResponse])
async def list_pending_publish(
    organization_id: Optional[UUID] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(settings.API_PAGE_LIMIT_DEFAULT, ge=1, le=settings.API_PAGE_MAX),
    user: CurrentUser = Depends(require_admin),
    service: WorkflowService = Depends(get_workflow_service),
):
    """List workflows pending publish approval (admin only)."""
    effective_org_id = get_effective_org_id(
        str(organization_id) if organization_id else None, user
    )
    workflows = await service.workflow_repository.list_pending_publish(
        UUID(effective_org_id), skip=skip, limit=limit
    )
    return [WorkflowResponse.from_domain(w) for w in workflows]


@router.post("/{workflow_id}/copy", response_model=WorkflowResponse)
async def copy_workflow(
    workflow_id: UUID = Path(...),
    user: CurrentUser = Depends(get_current_user),
    service: WorkflowService = Depends(get_workflow_service),
):
    """Copy a workflow to the current user's personal scope."""
    effective_org_id = get_effective_org_id(None, user)
    try:
        return await service.copy_workflow(
            workflow_id=workflow_id,
            user_id=UUID(user["id"]),
            organization_id=UUID(effective_org_id),
            target_scope="personal",
        )
    except EntityNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow {workflow_id} not found",
        )
    except DuplicateEntityError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=safe_error_message(e))


@router.post("/{workflow_id}/request-publish", response_model=WorkflowResponse)
async def request_publish(
    workflow_id: UUID = Path(...),
    user: CurrentUser = Depends(get_current_user),
    service: WorkflowService = Depends(get_workflow_service),
):
    """Request publishing a personal workflow to the organization."""
    try:
        return await service.request_publish(workflow_id, UUID(user["id"]))
    except EntityNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow {workflow_id} not found",
        )
    except BusinessRuleViolation as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=safe_error_message(e))


@router.post("/{workflow_id}/approve-publish", response_model=WorkflowResponse)
async def approve_publish(
    workflow_id: UUID = Path(...),
    user: CurrentUser = Depends(require_admin),
    service: WorkflowService = Depends(get_workflow_service),
):
    """Admin approves a pending publish request."""
    try:
        return await service.approve_publish(workflow_id)
    except EntityNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow {workflow_id} not found",
        )
    except BusinessRuleViolation as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=safe_error_message(e))


@router.post("/{workflow_id}/reject-publish", response_model=WorkflowResponse)
async def reject_publish(
    workflow_id: UUID = Path(...),
    user: CurrentUser = Depends(require_admin),
    service: WorkflowService = Depends(get_workflow_service),
):
    """Admin rejects a pending publish request."""
    try:
        return await service.reject_publish(workflow_id)
    except EntityNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow {workflow_id} not found",
        )
    except BusinessRuleViolation as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=safe_error_message(e))


@router.get("/{workflow_id}", response_model=WorkflowResponse)
async def get_workflow(
    workflow_id: UUID = Path(...),
    user: CurrentUser = Depends(get_current_user),
    service: WorkflowService = Depends(get_workflow_service),
):
    """
    Get a workflow by ID.

    Users can only access workflows for organizations they belong to.
    Super-admins can access all workflows.
    """
    workflow = await service.get_workflow(workflow_id)

    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow with ID {workflow_id} not found",
        )

    await validate_organization_access(str(workflow.organization_id), user)
    return workflow


@router.patch("/{workflow_id}", response_model=WorkflowResponse)
async def update_workflow(
    workflow_id: UUID,
    workflow_update: WorkflowUpdate,
    user: CurrentUser = Depends(get_current_user),
    service: WorkflowService = Depends(get_workflow_service),
):
    """
    Update a workflow.

    Users can only update workflows for organizations they belong to.
    Super-admins can update any workflow.
    """
    workflow = await service.get_workflow(workflow_id)

    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow with ID {workflow_id} not found",
        )

    await validate_organization_access(str(workflow.organization_id), user)

    try:
        return await service.update_workflow(workflow_id, workflow_update)
    except DuplicateEntityError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=safe_error_message(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=safe_error_message(e))


@router.delete("/{workflow_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workflow(
    workflow_id: UUID = Path(...),
    user: CurrentUser = Depends(require_user),
    service: WorkflowService = Depends(get_workflow_service),
):
    """
    Delete a workflow.

    Business Rule: Workflow must be deactivated before deletion.
    Active workflows cannot be deleted.

    Admins can delete any workflow in their org.
    Regular users can only delete workflows they created (created_by matches).
    Super-admins can delete any workflow.

    Raises:
        404: Workflow not found
        403: User doesn't have access to organization, or doesn't own the workflow
        409: Workflow is ACTIVE (must deactivate first)
    """
    workflow = await service.get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow with ID {workflow_id} not found",
        )

    await validate_organization_access(str(workflow.organization_id), user)

    user_role = user.get("role", "")
    if user_role not in ("admin", "super_admin"):
        user_id = user.get("id", "")
        if str(workflow.created_by) != str(user_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only delete workflows you created",
            )

    try:
        await service.delete_workflow(workflow_id)
    except BusinessRuleViolation as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=safe_error_message(e),
        )


@router.get("/{workflow_id}/credentials/check", response_model=CredentialCheckResponse)
async def check_workflow_credentials(
    workflow_id: UUID = Path(...),
    user: CurrentUser = Depends(get_current_user),
    service: WorkflowService = Depends(get_workflow_service),
    credential_repo: ProviderCredentialRepository = Depends(
        get_provider_credential_repository
    ),
    provider_repo: ProviderRepository = Depends(get_provider_repository),
    service_repo: ProviderServiceRepository = Depends(get_provider_service_repository),
    prompt_repo: PromptRepository = Depends(get_prompt_repository),
):
    """
    Check if all required credentials are ready for workflow execution.

    Returns:
        - ready: true if workflow can run without credential issues
        - issues: list of problems that need to be resolved before running

    Use this endpoint on workflow detail page load to show warnings
    before the user clicks "Run".
    """
    workflow = await service.get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow with ID {workflow_id} not found",
        )

    await validate_organization_access(str(workflow.organization_id), user)

    credential_service = WorkflowCredentialService()
    return await credential_service.check_workflow_credentials(
        workflow_id=workflow_id,
        organization_id=UUID(str(workflow.organization_id)),
        steps=workflow.steps,
        provider_repo=provider_repo,
        credential_repo=credential_repo,
        service_repo=service_repo,
        prompt_repo=prompt_repo,
    )


def _derive_field_type_from_schema(param_schema: Dict[str, Any]) -> FormFieldType:
    """
    Derive form field type from JSON Schema parameter type.

    Mapping:
    - ui.widget=tags (array) -> tags
    - ui.widget=key-value (object) -> key-value
    - string -> text (or textarea if format=textarea)
    - string with enum -> select
    - array with items.enum -> multiselect
    - number/integer -> number
    - boolean -> checkbox
    - string with format=date -> date
    - string with format=date-time -> datetime
    - string with format=json -> json
    - object/array -> json
    """
    schema_type = param_schema.get("type", "string")
    schema_format = param_schema.get("format")
    ui_widget = (param_schema.get("ui") or {}).get("widget")

    # Explicit ui.widget overrides for structured widgets
    if ui_widget == "tags" and schema_type == "array":
        return "tags"
    if ui_widget == "key-value" and schema_type == "object":
        return "key-value"

    # Check for enum first (dropdown)
    if param_schema.get("enum"):
        return "select"

    if schema_type == "boolean":
        return "checkbox"

    if schema_type in ("number", "integer"):
        return "number"

    # Array with items.enum -> multiselect dropdown
    if schema_type == "array" and isinstance(param_schema.get("items"), dict):
        if param_schema["items"].get("enum"):
            return "multiselect"

    # Object and array types get JSON editor
    if schema_type in ("object", "array"):
        return "json"

    if schema_type == "string":
        if schema_format == "textarea":
            return "textarea"
        if schema_format == "date":
            return "date"
        if schema_format in ("date-time", "datetime"):
            return "datetime"
        if schema_format == "json":
            return "json"
        return "text"

    return "text"


def _get_nested_value(obj: Any, path: str) -> Any:
    """
    Navigate a nested path like "scenes[0].fade_in" in an object.
    Returns the value at the path, or None if not found.
    """
    import re

    if not obj or not path:
        return None

    try:
        # Convert "scenes[0].fade_in" to ["scenes", "0", "fade_in"]
        parts = re.sub(r"\[(\d+)\]", r".\1", path).split(".")
        value = obj
        for key in parts:
            if value is None:
                return None
            if isinstance(value, dict):
                value = value.get(key)
            elif isinstance(value, list) and key.isdigit():
                idx = int(key)
                value = value[idx] if 0 <= idx < len(value) else None
            else:
                return None
        return value
    except (KeyError, IndexError, TypeError):
        return None


def _get_nested_schema(schema_properties: Dict[str, Any], path: str) -> Dict[str, Any]:
    """
    Navigate a nested path like "messages[0].content" in a JSON Schema.
    Returns the schema definition for the field at the path, or {} if not found.

    For array-indexed paths like "messages[0].content":
    1. Look up "messages" in schema_properties
    2. If type is "array", navigate into .items
    3. Look up "content" in .items.properties
    """
    import re

    if not schema_properties or not path:
        return {}

    try:
        # Convert "messages[0].content" to ["messages", "[0]", "content"]
        # We keep the array index markers to detect when to navigate into .items
        parts = re.split(r"(\[\d+\])", path)
        parts = [
            p for p in parts if p and p != "."
        ]  # Remove empty strings and standalone dots

        current_schema = None

        for i, part in enumerate(parts):
            # Check if this is an array index marker like "[0]"
            if re.match(r"^\[\d+\]$", part):
                # Navigate into the .items schema of the current array
                if current_schema and current_schema.get("type") == "array":
                    current_schema = current_schema.get("items", {})
                else:
                    return {}
            else:
                # This is a property name
                # Split by dots to handle "field.subfield" within a single part
                subparts = part.split(".")
                for subpart in subparts:
                    if not subpart:
                        continue

                    if current_schema is None:
                        # First lookup: use the root schema_properties
                        current_schema = schema_properties.get(subpart, {})
                    else:
                        # Subsequent lookups: navigate into .properties
                        properties = current_schema.get("properties", {})
                        current_schema = properties.get(subpart, {})

                    if not current_schema:
                        return {}

        return current_schema or {}

    except (KeyError, AttributeError):
        return {}


def _infer_field_type_from_value(value: Any) -> FormFieldType:
    """
    Infer the form field type from an actual value.
    Returns the field type string compatible with FormFieldType.
    """
    if value is None:
        return "text"
    if isinstance(value, bool):
        return "checkbox"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        if len(value) > 100:
            return "textarea"
        return "text"
    if isinstance(value, (dict, list)):
        return "json"
    return "text"


def _format_param_key_as_label(param_key: str) -> str:
    """
    Convert a parameter key to a human-readable label.

    Handles nested array field notation like:
    - "batch_size" -> "Batch Size"
    - "scenes[0].fade_in" -> "Scene 1: Fade In"
    - "items[2].name" -> "Item 3: Name"
    - "prompt" -> "Prompt"
    """
    import re

    # Check for array notation like "scenes[0].field_name"
    array_match = re.match(r"^([a-zA-Z_][a-zA-Z0-9_]*)\[(\d+)\]\.(.+)$", param_key)

    if array_match:
        base_name = array_match.group(1)  # e.g., "scenes"
        index = int(array_match.group(2))  # e.g., 0
        field_name = array_match.group(3)  # e.g., "fade_in"

        # Convert base name to singular form (simple heuristic)
        # "scenes" -> "Scene", "items" -> "Item", "slides" -> "Slide"
        singular_base = (
            base_name.rstrip("s")
            if base_name.endswith("s") and len(base_name) > 2
            else base_name
        )
        singular_base = singular_base.replace("_", " ").title()

        # Convert field name to title case
        formatted_field = field_name.replace("_", " ").title()

        # Use 1-based indexing for user-friendliness
        return f"{singular_base} {index + 1}: {formatted_field}"

    # Simple key - just title case
    return param_key.replace("_", " ").title()


def _derive_form_config_from_schema(
    param_key: str, param_schema: Dict[str, Any], required_params: List[str]
) -> FormFieldConfigResponse:
    """
    Derive form field configuration from JSON Schema parameter definition.

    The form config is derived automatically:
    - label: from schema title, or formatted param_key
    - description: from schema description
    - required: from schema required list
    - field_type: from schema type/format/enum
    - options: from schema enum/enumNames
    - default_value: from schema default
    - min/max: from schema minimum/maximum
    - min_length/max_length: from schema minLength/maxLength
    """
    # Derive label from title or param key (with smart formatting for nested array fields)
    label = param_schema.get("title") or _format_param_key_as_label(param_key)

    # Derive description
    description = param_schema.get("description")

    # Derive required
    is_required = param_key in required_params

    # Derive field type
    field_type = _derive_field_type_from_schema(param_schema)

    # Derive options for select/multiselect fields
    options = None
    if param_schema.get("enum"):
        enum_values = param_schema["enum"]
        enum_names = param_schema.get("enumNames", enum_values)
        options = [
            {"value": str(v), "label": str(n)} for v, n in zip(enum_values, enum_names)
        ]
    elif field_type == "multiselect":
        # field_type is "multiselect" only when items.enum exists (see _derive_field_type_from_schema)
        items = param_schema.get("items", {})
        enum_values = items.get("enum", [])
        enum_names = items.get("enumNames", enum_values)
        options = [
            {"value": str(v), "label": str(n)} for v, n in zip(enum_values, enum_names)
        ]

    # Get default value
    default_value = param_schema.get("default")

    # Derive size hint from schema or field type
    # Textareas and JSON fields default to full width
    size = param_schema.get("size")
    if size is None and field_type in ("textarea", "json", "tags", "key-value"):
        size = "full"

    # Widget-specific metadata
    ui = param_schema.get("ui") or {}
    item_type = None
    key_placeholder = None
    value_placeholder = None
    add_label = None
    if field_type == "tags":
        items = param_schema.get("items") or {}
        item_type = items.get("type") or "string"
    elif field_type == "key-value":
        key_placeholder = ui.get("keyPlaceholder")
        value_placeholder = ui.get("valuePlaceholder")
        add_label = ui.get("addLabel")

    return FormFieldConfigResponse(
        label=label,
        placeholder=ui.get("placeholder"),
        description=description,
        required=is_required,
        field_type=field_type,
        default_value=default_value,
        options=options,
        min_length=param_schema.get("minLength"),
        max_length=param_schema.get("maxLength"),
        min=param_schema.get("minimum"),
        max=param_schema.get("maximum"),
        accepted_file_types=None,
        max_file_size_mb=None,
        size=size,
        item_type=item_type,
        key_placeholder=key_placeholder,
        value_placeholder=value_placeholder,
        add_label=add_label,
    )


@router.get("/{workflow_id}/form-schema", response_model=WorkflowFormSchemaResponse)
async def get_workflow_form_schema(
    workflow_id: UUID = Path(...),
    user: CurrentUser = Depends(get_current_user),
    service: WorkflowService = Depends(get_workflow_service),
    service_repo: ProviderServiceRepository = Depends(get_provider_service_repository),
    prompt_repo: PromptRepository = Depends(get_prompt_repository),
):
    """
    Get the form schema for a workflow.

    Returns a form schema containing all parameters marked as 'form' type
    in the workflow's step input mappings. This schema is used to generate
    the form shown to end-users when creating a new instance.

    Form field configuration is derived automatically from the parameter's
    JSON Schema definition (type, description, enum, etc.), so no manual
    form configuration is required when setting mappingType to 'form'.

    Fields are ordered by step sequence in the workflow.
    """
    workflow = await service.get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow with ID {workflow_id} not found",
        )

    await validate_organization_access(str(workflow.organization_id), user)

    form_fields: List[FormFieldResponse] = []

    # Cache for service parameter schemas to avoid repeated lookups
    service_schemas: Dict[str, Dict[str, Any]] = {}

    # Extract form fields from workflow steps
    # workflow.steps is Dict[str, Dict[str, Any]] from the DTO
    step_order = 0
    for step_id, step_config in workflow.steps.items():
        step_name = (
            step_config.get("name", step_id)
            if step_config
            else getattr(step_config, "name", step_id)
        )

        # Get input_mappings - MERGE from both client_metadata and step level
        # First-step params may be in client_metadata, nested array fields at step level
        input_mappings = {}
        if step_config:
            # Get from client_metadata (where frontend stores explicit configs)
            client_metadata = step_config.get("client_metadata", {})
            if isinstance(client_metadata, dict):
                cm_mappings = client_metadata.get("input_mappings", {})
                if isinstance(cm_mappings, dict):
                    input_mappings.update(cm_mappings)
            # Merge with step-level mappings (where nested array fields are stored)
            step_mappings = step_config.get("input_mappings", {})
            if isinstance(step_mappings, dict):
                input_mappings.update(step_mappings)
        else:
            client_metadata = getattr(step_config, "client_metadata", {})
            if client_metadata:
                cm_mappings = client_metadata.get("input_mappings", {})
                if isinstance(cm_mappings, dict):
                    input_mappings.update(cm_mappings)
            step_mappings = getattr(step_config, "input_mappings", None)
            if isinstance(step_mappings, dict):
                input_mappings.update(step_mappings)

        if not input_mappings:
            step_order += 1
            continue

        # Get the service's parameter schema for this step
        # Get service_id: step level takes precedence over job level.
        parameter_schema = {}
        if step_config:
            service_id = step_config.get("service_id")
            if not service_id:
                job = step_config.get("job", {})
                service_id = job.get("service_id") if isinstance(job, dict) else None
        else:
            service_id = getattr(step_config, "service_id", None)
            if not service_id:
                job = getattr(step_config, "job", None)
                service_id = getattr(job, "service_id", None) if job else None

        if service_id and service_id not in service_schemas:
            # Look up the service to get its parameter schema
            provider_svc = await service_repo.get_by_service_id(
                service_id, skip=0, limit=1
            )
            if provider_svc:
                service_schemas[service_id] = provider_svc.parameter_schema or {}
            else:
                service_schemas[service_id] = {}

        if service_id:
            parameter_schema = service_schemas.get(service_id, {})

        # Get properties and required list from schema
        schema_properties = parameter_schema.get("properties", {})
        required_params = parameter_schema.get("required", [])

        # Process each input mapping
        for param_key, mapping in input_mappings.items():
            if not isinstance(mapping, dict):
                continue

            mapping_type = mapping.get("mappingType") or mapping.get("mapping_type")

            # Handle prompt mappings: each prompt variable becomes a form field
            if mapping_type == "prompt":
                variable_values = mapping.get("variableValues", {})
                if not isinstance(variable_values, dict):
                    variable_values = {}

                # Collect variables mapped from other steps via _prompt_variable:* entries
                mapped_from_steps = set()
                for map_key, map_entry in input_mappings.items():
                    if map_key.startswith("_prompt_variable:") and isinstance(
                        map_entry, dict
                    ):
                        if map_entry.get("mappingType") == "mapped":
                            mapped_from_steps.add(map_key.split(":", 1)[1])

                # Fetch prompt - its variables are the source of truth for form fields
                prompt_id = mapping.get("promptId")
                prompt_vars: list = []
                if prompt_id:
                    try:
                        prompt = await prompt_repo.get_by_id(UUID(str(prompt_id)))
                        if prompt:
                            prompt_vars = prompt.variables
                    except (ValueError, Exception):
                        pass

                for var_meta in prompt_vars:
                    var_name = var_meta.name
                    # Skip variables mapped from other steps
                    if var_name in mapped_from_steps:
                        continue
                    # Also skip if variableValues contains a {{ }} template expression
                    var_override = variable_values.get(var_name, "")
                    if (
                        isinstance(var_override, str)
                        and "{{" in var_override
                        and "}}" in var_override
                    ):
                        continue

                    var_label = var_meta.label
                    var_type = var_meta.type
                    default_val = (
                        var_override if var_override else (var_meta.default or None)
                    )

                    # Map prompt variable type to form field type
                    prompt_field_type: FormFieldType
                    if var_type == "enum" and var_meta.options:
                        prompt_field_type = "select"
                        # Use explicit option_labels when present (mirrors provider `enumNames`).
                        # Fall back to titlecasing the raw value.
                        labels = var_meta.option_labels
                        if labels and len(labels) == len(var_meta.options):
                            options = [
                                {"value": v, "label": lbl}
                                for v, lbl in zip(var_meta.options, labels)
                            ]
                        else:
                            options = [
                                {"value": o, "label": o.title()}
                                for o in var_meta.options
                            ]
                    elif var_type == "number":
                        prompt_field_type = "number"
                        options = None
                    else:
                        prompt_field_type = "textarea"
                        options = None

                    form_fields.append(
                        FormFieldResponse(
                            parameter_key=f"_prompt_variable:{var_name}",
                            step_id=step_id,
                            step_name=step_name,
                            step_order=step_order,
                            config=FormFieldConfigResponse(
                                label=var_label,
                                placeholder=f"Enter {var_label.lower()}...",
                                description=None,
                                required=bool(getattr(var_meta, "required", False)),
                                field_type=prompt_field_type,
                                default_value=default_val,
                                options=options,
                            ),
                        )
                    )
                continue

            if mapping_type != "form":
                continue

            # Get the parameter's schema definition
            # Use nested schema navigation (handles both simple and array-indexed paths)
            param_schema = _get_nested_schema(schema_properties, param_key)

            # Get step parameters to infer types from actual values
            step_params = {}
            if step_config:
                job = step_config.get("job", {})
                step_params = job.get("parameters", {}) if isinstance(job, dict) else {}
            else:
                job = getattr(step_config, "job", None)
                step_params = getattr(job, "parameters", {}) if job else {}

            # For nested paths or when schema not found, infer type from actual value
            inferred_field_type = None
            if not param_schema or not param_schema.get("type"):
                # Get the actual value using nested path navigation
                actual_value = _get_nested_value(step_params, param_key)
                if actual_value is not None:
                    inferred_field_type = _infer_field_type_from_value(actual_value)

            # Derive form config from parameter schema
            field_config = _derive_form_config_from_schema(
                param_key=param_key,
                param_schema=param_schema,
                required_params=required_params,
            )

            # Override field_type if we inferred it from actual values
            if inferred_field_type and field_config.field_type == "text":
                field_config = FormFieldConfigResponse(
                    label=field_config.label,
                    placeholder=field_config.placeholder,
                    description=field_config.description,
                    required=field_config.required,
                    field_type=inferred_field_type,
                    default_value=field_config.default_value,
                    options=field_config.options,
                    min_length=field_config.min_length,
                    max_length=field_config.max_length,
                    min=field_config.min,
                    max=field_config.max,
                    accepted_file_types=field_config.accepted_file_types,
                    max_file_size_mb=field_config.max_file_size_mb,
                    size=field_config.size,
                )

            form_fields.append(
                FormFieldResponse(
                    parameter_key=param_key,
                    step_id=step_id,
                    step_name=step_name,
                    step_order=step_order,
                    config=field_config,
                )
            )

        step_order += 1

    # Sort fields by step order
    form_fields.sort(key=lambda f: f.step_order)

    return WorkflowFormSchemaResponse(
        workflow_id=workflow_id,
        workflow_name=workflow.name,
        has_form_fields=len(form_fields) > 0,
        fields=form_fields,
    )


# Response model for webhook token
class WebhookTokenResponse(BaseModel):
    """Response for webhook token operations."""

    webhook_token: str
    webhook_secret: str
    webhook_url: str


@router.post(
    "/{workflow_id}/webhook-token",
    response_model=WebhookTokenResponse,
    status_code=status.HTTP_201_CREATED,
)
async def generate_webhook_token(
    workflow_id: UUID = Path(...),
    user: CurrentUser = Depends(require_admin),
    service: WorkflowService = Depends(get_workflow_service),
):
    """
    Generate a secure webhook token for triggering this workflow.

    This creates a unique, unguessable URL that external systems can call
    to start new workflow instances.

    Requires ADMIN or SUPER_ADMIN role.

    Returns:
        - webhook_token: The generated token
        - webhook_url: The full URL to call

    Raises:
        404: Workflow not found
        409: Token already exists (use regenerate instead)
    """
    workflow = await service.get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow with ID {workflow_id} not found",
        )

    await validate_organization_access(str(workflow.organization_id), user)

    try:
        result = await service.generate_webhook_token(workflow_id)
        webhook_url = f"{settings.API_BASE_URL}/webhooks/incoming/{result['token']}"
        return WebhookTokenResponse(
            webhook_token=result["token"],
            webhook_secret=result["secret"],
            webhook_url=webhook_url,
        )
    except BusinessRuleViolation as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=safe_error_message(e),
        )


@router.post(
    "/{workflow_id}/webhook-token/regenerate", response_model=WebhookTokenResponse
)
async def regenerate_webhook_token(
    workflow_id: UUID = Path(...),
    user: CurrentUser = Depends(require_admin),
    service: WorkflowService = Depends(get_workflow_service),
):
    """
    Regenerate the webhook token for this workflow.

    WARNING: This will invalidate the previous webhook URL.
    Any external systems using the old URL will need to be updated.

    Requires ADMIN or SUPER_ADMIN role.

    Returns:
        - webhook_token: The new token
        - webhook_url: The new URL to call

    Raises:
        404: Workflow not found or no token exists
    """
    workflow = await service.get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow with ID {workflow_id} not found",
        )

    await validate_organization_access(str(workflow.organization_id), user)

    try:
        result = await service.regenerate_webhook_token(workflow_id)
        webhook_url = f"{settings.API_BASE_URL}/webhooks/incoming/{result['token']}"
        return WebhookTokenResponse(
            webhook_token=result["token"],
            webhook_secret=result["secret"],
            webhook_url=webhook_url,
        )
    except BusinessRuleViolation as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=safe_error_message(e),
        )


@router.delete("/{workflow_id}/webhook-token", status_code=status.HTTP_204_NO_CONTENT)
async def delete_webhook_token(
    workflow_id: UUID = Path(...),
    user: CurrentUser = Depends(require_admin),
    service: WorkflowService = Depends(get_workflow_service),
):
    """
    Remove the webhook token from this workflow.

    This disables webhook triggering for this workflow.

    Requires ADMIN or SUPER_ADMIN role.

    Raises:
        404: Workflow not found
    """
    workflow = await service.get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow with ID {workflow_id} not found",
        )

    await validate_organization_access(str(workflow.organization_id), user)
    await service.clear_webhook_token(workflow_id)


# =============================================================================
# Step Webhook Token Endpoints (for core.webhook_wait steps)
# =============================================================================


class StepWebhookTokenResponse(BaseModel):
    """Response for step webhook token operations."""

    step_id: str
    webhook_token: str
    webhook_secret: str
    webhook_url: str


@router.post(
    "/{workflow_id}/steps/{step_id}/webhook-token",
    response_model=StepWebhookTokenResponse,
    status_code=status.HTTP_201_CREATED,
)
async def generate_step_webhook_token(
    workflow_id: UUID = Path(...),
    step_id: str = Path(...),
    user: CurrentUser = Depends(require_admin),
    service: WorkflowService = Depends(get_workflow_service),
):
    """
    Generate a secure webhook token for a workflow step.

    Used for core.webhook_wait steps that pause the workflow and wait
    for an external callback.

    Requires ADMIN or SUPER_ADMIN role.

    Returns:
        - step_id: The step ID
        - webhook_token: The generated token
        - webhook_url: The full URL for callbacks

    Raises:
        404: Workflow or step not found
        409: Token already exists (use regenerate instead)
    """
    workflow = await service.get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow with ID {workflow_id} not found",
        )

    await validate_organization_access(str(workflow.organization_id), user)

    try:
        result = await service.generate_step_webhook_token(workflow_id, step_id)
        webhook_url = f"/webhooks/incoming/{result['token']}"
        return StepWebhookTokenResponse(
            step_id=step_id,
            webhook_token=result["token"],
            webhook_secret=result["secret"],
            webhook_url=webhook_url,
        )
    except EntityNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=safe_error_message(e),
        )
    except BusinessRuleViolation as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=safe_error_message(e),
        )


@router.post(
    "/{workflow_id}/steps/{step_id}/webhook-token/regenerate",
    response_model=StepWebhookTokenResponse,
)
async def regenerate_step_webhook_token(
    workflow_id: UUID = Path(...),
    step_id: str = Path(...),
    user: CurrentUser = Depends(require_admin),
    service: WorkflowService = Depends(get_workflow_service),
):
    """
    Regenerate the webhook token for a workflow step.

    WARNING: This will invalidate the previous callback URL.
    Any external systems using the old URL will need to be updated.

    Requires ADMIN or SUPER_ADMIN role.

    Returns:
        - step_id: The step ID
        - webhook_token: The new token
        - webhook_url: The new URL for callbacks

    Raises:
        404: Workflow, step, or token not found
    """
    workflow = await service.get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow with ID {workflow_id} not found",
        )

    await validate_organization_access(str(workflow.organization_id), user)

    try:
        result = await service.regenerate_step_webhook_token(workflow_id, step_id)
        webhook_url = f"/webhooks/incoming/{result['token']}"
        return StepWebhookTokenResponse(
            step_id=step_id,
            webhook_token=result["token"],
            webhook_secret=result["secret"],
            webhook_url=webhook_url,
        )
    except EntityNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=safe_error_message(e),
        )
    except BusinessRuleViolation as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=safe_error_message(e),
        )


@router.get(
    "/{workflow_id}/steps/{step_id}/webhook-token",
    response_model=StepWebhookTokenResponse,
)
async def get_step_webhook_token(
    workflow_id: UUID = Path(...),
    step_id: str = Path(...),
    user: CurrentUser = Depends(require_admin),
    service: WorkflowService = Depends(get_workflow_service),
):
    """
    Get the webhook token for a workflow step.

    Requires ADMIN or SUPER_ADMIN role.

    Returns:
        - step_id: The step ID
        - webhook_token: The token
        - webhook_url: The callback URL

    Raises:
        404: Workflow, step, or token not found
    """
    workflow = await service.get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow with ID {workflow_id} not found",
        )

    await validate_organization_access(str(workflow.organization_id), user)

    try:
        result = await service.get_step_webhook_token(workflow_id, step_id)
        if not result["token"]:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No webhook token found for step {step_id}",
            )
        webhook_url = f"/webhooks/incoming/{result['token']}"
        return StepWebhookTokenResponse(
            step_id=step_id,
            webhook_token=result["token"],
            webhook_secret=result["secret"] or "",
            webhook_url=webhook_url,
        )
    except EntityNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=safe_error_message(e),
        )


# =============================================================================
# Workflow Export/Import Endpoints
# =============================================================================


class WorkflowImportResponse(BaseModel):
    """Response for workflow import."""

    workflow: WorkflowResponse
    warnings: List[str] = []


@router.get("/{workflow_id}/export")
async def export_workflow(
    workflow_id: UUID = Path(...),
    user: CurrentUser = Depends(get_current_user),
    service: WorkflowService = Depends(get_workflow_service),
):
    """
    Export a workflow as a JSON file.

    The exported file contains the workflow definition without organization-specific
    IDs, making it portable for import into other organizations.

    Returns a downloadable JSON file.
    """
    workflow = await service.get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow with ID {workflow_id} not found",
        )

    await validate_organization_access(str(workflow.organization_id), user)

    # Build export data - exclude org-specific fields
    export_data = {
        "export_version": 1,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "name": workflow.name,
        "description": workflow.description,
        "trigger_type": (
            workflow.trigger_type.value
            if hasattr(workflow.trigger_type, "value")
            else workflow.trigger_type
        ),
        "steps": workflow.steps,
        "trigger_input_schema": workflow.trigger_input_schema,
        "client_metadata": workflow.client_metadata,
    }

    # Sanitize filename
    safe_name = "".join(c if c.isalnum() or c in "._- " else "_" for c in workflow.name)
    filename = f"{safe_name}.json"

    return Response(
        content=json.dumps(export_data, indent=2, default=str),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post(
    "/import",
    response_model=WorkflowImportResponse,
    status_code=status.HTTP_201_CREATED,
)
async def import_workflow(
    file: UploadFile = File(..., description="Workflow JSON file to import"),
    organization_id: Optional[UUID] = Query(
        None, description="Target organization (optional)"
    ),
    user: CurrentUser = Depends(get_current_user),
    service: WorkflowService = Depends(get_workflow_service),
    provider_repo: ProviderRepository = Depends(get_provider_repository),
    prompt_repo: PromptRepository = Depends(get_prompt_repository),
):
    """
    Import a workflow from a JSON file.

    Creates a new workflow in the target organization from an exported workflow file.
    The workflow name will have "(imported)" appended if a workflow with the same
    name already exists.

    Returns the created workflow and any warnings (e.g., missing providers).
    """
    # Validate file type (presentation layer concern)
    if not file.filename or not file.filename.endswith(".json"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be a .json file",
        )

    # Read and parse JSON (presentation layer concern - file handling)
    try:
        content = await file.read()
        data = json.loads(content.decode("utf-8"))
    except json.JSONDecodeError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid JSON: {str(e)}",
        )
    except Exception:
        logger.exception("Failed to read uploaded workflow file")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to read file",
        )

    # Get target organization
    effective_org_id = get_effective_org_id(
        str(organization_id) if organization_id else None, user
    )

    # Delegate business logic to service
    try:
        created_workflow, warnings = await service.import_workflow(
            data=data,
            organization_id=UUID(effective_org_id),
            provider_repo=provider_repo,
            prompt_repo=prompt_repo,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=safe_error_message(e))
    except DuplicateEntityError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=safe_error_message(e))

    return WorkflowImportResponse(
        workflow=created_workflow,
        warnings=warnings,
    )
