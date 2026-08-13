# api/app/application/services/form_field_resolver.py

"""Derive a workflow's run-form field set from its config - the single owner of
the external ``field_id`` ⇄ internal ``{step_id}.{parameter_key}`` contract.

Used by both the form-schema endpoint (UI run form) and ``TriggerDispatcher``
so api/webhook/schedule/event triggers resolve form defaults identically to the
UI. The field set is 100% computable from workflow config - no instance state.
"""

import logging
import re
from typing import Any, Dict, List
from uuid import UUID

from app.application.dtos.workflow_dto import (
    FormFieldConfigResponse,
    FormFieldResponse,
    FormFieldType,
)
from app.application.services.instance.step_ordering import order_steps_topologically
from app.domain.common.json_serialization import serialize_step_config
from app.domain.common.value_objects import StepConfig
from app.domain.prompt.repository import PromptRepository
from app.domain.provider.repository import ProviderServiceRepository

logger = logging.getLogger(__name__)

_PROMPT_VARIABLE_PREFIX = "_prompt_variable:"


def _derive_field_type_from_schema(param_schema: Dict[str, Any]) -> FormFieldType:
    """
    Derive form field type from JSON Schema parameter type.

    Mapping:
    - ui.widget=tags (array) -> tags
    - ui.widget=key-value (object) -> key-value
    - ui.widget=combobox (string) -> combobox
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
    if ui_widget == "combobox" and schema_type == "string":
        return "combobox"

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
    elif field_type == "combobox":
        # Suggestions may be {"value","label"} dicts or plain strings
        suggestions = (param_schema.get("ui") or {}).get("suggestions") or []
        options = [
            (
                {"value": str(s["value"]), "label": str(s.get("label", s["value"]))}
                if isinstance(s, dict)
                else {"value": str(s), "label": str(s)}
            )
            for s in suggestions
        ] or None

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
        pattern=param_schema.get("pattern"),
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


def _derive_field_id(mapping: Dict[str, Any], param_key: str) -> str:
    """External field_id for a form field: operator override wins, else the
    parameter key (prompt-variable prefix stripped for a clean default)."""
    override = mapping.get("fieldId")
    if override:
        return str(override)
    if param_key.startswith(_PROMPT_VARIABLE_PREFIX):
        return param_key[len(_PROMPT_VARIABLE_PREFIX) :]
    return param_key


def _resolve_field_id_collisions(form_fields: List[FormFieldResponse]) -> None:
    """Two fields deriving the same field_id collide; fall back to the internal
    composite ``{step_id}.{parameter_key}`` for the colliding fields only and
    warn. The composite is unique by construction. Mutates in place."""
    counts: Dict[str, int] = {}
    for f in form_fields:
        counts[f.field_id] = counts.get(f.field_id, 0) + 1
    for f in form_fields:
        if counts[f.field_id] > 1:
            composite = f"{f.step_id}.{f.parameter_key}"
            logger.warning(
                "Form field_id collision: %r maps to multiple fields; "
                "falling back to composite key %r",
                f.field_id,
                composite,
            )
            f.field_id = composite


class FormFieldResolver:
    """Resolves a workflow's run-form fields and the external⇄internal key map.

    The resolver is the single authority for ``field_id``; callers must route
    every external→internal key translation through ``field_id_to_internal_key``
    so re-ordering steps or swapping a provider never breaks a saved trigger.
    """

    def __init__(
        self,
        provider_service_repository: ProviderServiceRepository,
        prompt_repository: PromptRepository,
    ) -> None:
        self.provider_service_repository = provider_service_repository
        self.prompt_repository = prompt_repository

    @staticmethod
    def _normalize_steps(steps: Dict[str, Any]) -> Dict[str, Any]:
        """The walk is dict-based. The dispatcher passes a domain Workflow whose
        step values are StepConfig - serialize those to dicts. The form-schema
        endpoint passes a WorkflowResponse (already dicts), which passes through
        untouched."""
        return {
            step_id: (
                serialize_step_config(sc) if isinstance(sc, StepConfig) else sc
            )
            for step_id, sc in steps.items()
        }

    async def resolve_fields(self, workflow: Any) -> List[FormFieldResponse]:
        """The full run-form field set, ordered by step topology, each carrying
        its stable ``field_id``. Identical to what the form-schema endpoint and
        the UI run form see."""
        form_fields: List[FormFieldResponse] = []

        # Cache for service parameter schemas to avoid repeated lookups
        service_schemas: Dict[str, Dict[str, Any]] = {}

        # The form-schema endpoint passes a WorkflowResponse (dict steps); the
        # dispatcher passes a domain Workflow (StepConfig steps). The walk is
        # dict-based, so normalize domain StepConfig values to plain dicts.
        steps = self._normalize_steps(workflow.steps or {})

        # Step keys come from a JSONB column whose order is not preserved, so
        # iterate in topological (depends_on) order to match the flow editor.
        ordered_step_ids = order_steps_topologically({"steps": steps})
        step_order = 0
        for step_id in ordered_step_ids:
            step_config = steps.get(step_id)
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
                    service_id = (
                        job.get("service_id") if isinstance(job, dict) else None
                    )
            else:
                service_id = getattr(step_config, "service_id", None)
                if not service_id:
                    job = getattr(step_config, "job", None)
                    service_id = getattr(job, "service_id", None) if job else None

            if service_id and service_id not in service_schemas:
                # Look up the service to get its parameter schema
                provider_svc = await self.provider_service_repository.get_by_service_id(
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
                            prompt_uuid = UUID(str(prompt_id))
                        except ValueError:
                            logger.warning(
                                "Skipping form fields for malformed promptId=%s",
                                prompt_id,
                            )
                        else:
                            prompt = await self.prompt_repository.get_by_id(
                                prompt_uuid
                            )
                            if prompt:
                                prompt_vars = prompt.variables

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
                                field_id=_derive_field_id(
                                    mapping, f"_prompt_variable:{var_name}"
                                ),
                                parameter_key=f"_prompt_variable:{var_name}",
                                step_id=step_id,
                                step_name=step_name,
                                step_order=step_order,
                                config=FormFieldConfigResponse(
                                    label=var_label,
                                    placeholder=f"Enter {var_label.lower()}...",
                                    description=None,
                                    required=bool(
                                        getattr(var_meta, "required", False)
                                    ),
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
                    step_params = (
                        job.get("parameters", {}) if isinstance(job, dict) else {}
                    )
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
                        pattern=field_config.pattern,
                        min=field_config.min,
                        max=field_config.max,
                        accepted_file_types=field_config.accepted_file_types,
                        max_file_size_mb=field_config.max_file_size_mb,
                        size=field_config.size,
                    )

                form_fields.append(
                    FormFieldResponse(
                        field_id=_derive_field_id(mapping, param_key),
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

        # field_id is the external contract; collisions fall back to composite.
        _resolve_field_id_collisions(form_fields)

        return form_fields

    @staticmethod
    def resolve_defaults(fields: List[FormFieldResponse]) -> Dict[str, Any]:
        """``{field_id: default}`` for every field with a non-None default."""
        return {
            f.field_id: f.config.default_value
            for f in fields
            if f.config.default_value is not None
        }

    @staticmethod
    def field_id_to_internal_key(fields: List[FormFieldResponse]) -> Dict[str, str]:
        """``{field_id: "{step_id}.{parameter_key}"}`` - the external→internal
        translation the dispatcher applies last, before writing form_values."""
        return {f.field_id: f"{f.step_id}.{f.parameter_key}" for f in fields}

    @staticmethod
    def required_without_default(fields: List[FormFieldResponse]) -> List[str]:
        """field_ids of fields that are required and have no default - the set a
        synchronous (api/webhook) trigger must supply or be rejected."""
        return [
            f.field_id
            for f in fields
            if f.config.required and f.config.default_value is None
        ]
