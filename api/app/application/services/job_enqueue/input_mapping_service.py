# api/app/application/services/job_enqueue/input_mapping_service.py

"""
Input mapping resolution for step parameters.

Handles explicit field-to-field mappings between steps and
prompt pre-resolution.
"""

import logging
import re
import uuid
from typing import Any, Dict, Optional

from app.application.services.mapping_resolver import MappingResolver

logger = logging.getLogger(__name__)


def _resolve_expression(
    value: str,
    previous_step_results: Dict[str, Any],
    instance_parameters: Dict[str, Any],
) -> str:
    """Resolve {{ step_id.field }} expressions in a single string value.

    Only resolves simple step_id.field patterns (the most common case
    for expression variable mappings).
    """
    jinja_pattern = r"\{\{\s*([\w.\[\]\*\d-]+)\s*\}\}"

    # Skip [*] expressions - they're for array expansion
    if "[*]" in value:
        return value

    match = re.fullmatch(jinja_pattern, value.strip())
    if match:
        path = match.group(1)
        resolved = _resolve_path(path, previous_step_results, instance_parameters)
        if resolved is not None:
            return str(resolved)
    return value


def _resolve_path(
    path: str,
    previous_step_results: Dict[str, Any],
    instance_parameters: Dict[str, Any],
) -> Any:
    """Resolve a dot-notation path against step results and instance params."""
    context: Dict[str, Any] = {
        "steps": previous_step_results,
        "input": instance_parameters,
    }
    parts = path.split(".")

    # __instance_form__ is a virtual step - resolve from instance parameters
    if parts and parts[0] == "__instance_form__":
        parts = ["input"] + parts[1:]

    # Shorthand: step_id.field → steps.step_id.field
    if parts and parts[0] not in ("steps", "input"):
        if parts[0] in context.get("steps", {}):
            parts = ["steps"] + parts

    current: Any = context
    for part in parts:
        array_match = re.match(r"^(\w+)\[(\d+|\*)\]$", part)
        if array_match:
            field_name = array_match.group(1)
            index_str = array_match.group(2)
            if isinstance(current, dict) and field_name in current:
                current = current[field_name]
            else:
                return None
            if isinstance(current, list):
                if index_str == "*":
                    index_str = "0"
                idx = int(index_str)
                if 0 <= idx < len(current):
                    current = current[idx]
                else:
                    return None
            else:
                return None
        elif isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None

    return current


def _resolve_instance_form_field(
    output_field: str,
    instance_parameters: Dict[str, Any],
) -> Any:
    """Resolve an __instance_form__ field from instance parameters.

    Searches both top-level keys and form_values (where submit_form_and_start
    stores form submissions keyed as `{step_id}.{param_path}`).

    Returns the resolved value or None.
    """
    tv_key = f"_prompt_variable:{output_field}"

    # Build list of dicts to search: top-level + form_values
    search_dicts = [instance_parameters]
    form_vals = instance_parameters.get("form_values")
    if isinstance(form_vals, dict):
        search_dicts.append(form_vals)

    for search_dict in search_dicts:
        # Direct key
        if output_field in search_dict:
            return search_dict[output_field]
        # _prompt_variable: prefix
        if tv_key in search_dict:
            return search_dict[tv_key]
        # {step_id}.{field} suffix match
        for ip_key, ip_value in search_dict.items():
            if ip_key.endswith(f".{output_field}") or ip_key.endswith(f".{tv_key}"):
                return ip_value

    return None


def _set_nested_param(params: Dict[str, Any], key: str, value: Any) -> None:
    """Set a value at a nested path in the parameters dict.

    Handles keys like `scenes[0].elements[0].count` by navigating through
    dicts and lists.  Falls back to flat-key assignment if the path cannot be
    followed (e.g. the parent array or object does not exist yet).
    """
    # Split "scenes[0].elements[0].count" into segments:
    # ["scenes", "[0]", "elements", "[0]", "count"]
    segments = re.split(r"\.|\[", key)
    # Re-add brackets for index segments: "0]" -> 0
    parsed: list = []
    for seg in segments:
        if not seg:
            continue
        if seg.endswith("]"):
            try:
                parsed.append(int(seg[:-1]))
            except ValueError:
                # Not a valid index, treat the whole key as flat
                params[key] = value
                return
        else:
            parsed.append(seg)

    if not parsed:
        params[key] = value
        return

    current: Any = params
    for i, segment in enumerate(parsed[:-1]):
        next_seg = parsed[i + 1]
        if isinstance(segment, int):
            if isinstance(current, list) and 0 <= segment < len(current):
                current = current[segment]
            else:
                # Index out of bounds or not a list - fall back to flat key
                params[key] = value
                return
        else:
            if isinstance(current, dict):
                if segment not in current:
                    # Auto-create missing intermediate containers
                    if isinstance(next_seg, int):
                        current[segment] = []
                    else:
                        current[segment] = {}
                current = current[segment]
            else:
                params[key] = value
                return

    # Set the final value
    last = parsed[-1]
    if isinstance(last, int):
        if isinstance(current, list) and 0 <= last < len(current):
            current[last] = value
        else:
            params[key] = value
    elif isinstance(current, dict):
        current[last] = value
    else:
        params[key] = value


def get_input_mappings(step_config: Dict[str, Any]) -> Dict[str, Any]:
    """Merge input_mappings from client_metadata and step level into one dict."""
    input_mappings = {}

    # Get from client_metadata (where frontend stores explicit configs)
    client_metadata = step_config.get("client_metadata", {})
    if isinstance(client_metadata, dict):
        cm_mappings = client_metadata.get("input_mappings", {})
        if isinstance(cm_mappings, dict):
            input_mappings.update(cm_mappings)

    # Get from step level (may have additional mappings)
    step_mappings = step_config.get("input_mappings", {})
    if isinstance(step_mappings, dict):
        input_mappings.update(step_mappings)

    return input_mappings


def apply_input_mappings(
    step_config: Dict[str, Any],
    input_mappings: Dict[str, str],
    previous_step_results: Dict[str, Any],
    instance_parameters: Dict[str, Any],
) -> Dict[str, Any]:
    """Resolve input_mappings and merge into step's job.parameters.

    Input mappings allow explicit field-to-field mapping between steps:
    {"board_id": "steps.get_boards.boards[0].id"}
    """
    import copy

    # Build execution context for MappingResolver
    # The resolver expects: {"steps": {step_id: {outputs}}, "trigger": {input_data}}
    execution_context = {
        "steps": previous_step_results,
        "trigger": instance_parameters,
    }

    # Resolve all input mappings
    resolver = MappingResolver()
    logger.debug(f"Resolving input_mappings: {input_mappings}")
    logger.debug(f"Execution context steps: {list(execution_context['steps'].keys())}")
    resolved_params = resolver.resolve_mappings(input_mappings, execution_context)
    logger.debug(f"Resolved params: {resolved_params}")

    if not resolved_params:
        logger.debug(
            "No params resolved from input_mappings (may be expected if iteration target was excluded)"
        )
        return step_config

    # Deep copy to avoid mutating original
    result = copy.deepcopy(step_config)

    # Merge resolved params into job.parameters
    if "job" not in result:
        result["job"] = {}
    if "parameters" not in result["job"]:
        result["job"]["parameters"] = {}

    # Resolved params override static params.
    # For nested keys like "scenes[0].elements[0].count", navigate into the
    # actual data structure instead of creating a flat top-level key.
    for param_key, param_value in resolved_params.items():
        if "[" in param_key or "." in param_key:
            _set_nested_param(result["job"]["parameters"], param_key, param_value)
        else:
            result["job"]["parameters"][param_key] = param_value

    logger.debug(
        f"Applied {len(resolved_params)} input mappings: {list(resolved_params.keys())}"
    )

    return result


async def pre_resolve_prompts(
    input_mappings: Dict[str, Any],
    organization_id: uuid.UUID,
    prompt_service: Any,
    previous_step_results: Optional[Dict[str, Any]] = None,
    instance_parameters: Optional[Dict[str, Any]] = None,
) -> tuple[Dict[str, Any], Dict[str, str]]:
    """Pre-resolve prompt mappings into static values.

    Scans input_mappings for entries with mappingType == "prompt",
    loads the prompt, assembles it with the variable values, and replaces
    the mapping with a static value. This keeps MappingResolver pure (no DB).

    Variable values may contain {{ step_id.field }} expressions that reference
    outputs from previous steps. These are resolved before prompt assembly.

    Args:
        input_mappings: The raw input_mappings dict from step config
        organization_id: Org ID for access control
        prompt_service: Service for assembling prompts
        previous_step_results: Results from completed steps (for resolving expressions)
        instance_parameters: Instance-level input parameters

    Returns:
        Tuple of (resolved_mappings, collected_prompt_variables).
        collected_prompt_variables is a flat dict of all variable values
        used across all prompt mappings in this step.
    """
    resolved = {}
    collected_prompt_variables: Dict[str, str] = {}

    for key, mapping in input_mappings.items():
        # Skip _prompt_variable:* entries - they are consumed during prompt
        # assembly and must not leak into job parameters / API requests.
        if key.startswith("_prompt_variable:"):
            continue

        if not isinstance(mapping, dict):
            resolved[key] = mapping
            continue

        if mapping.get("mappingType") != "prompt":
            resolved[key] = mapping
            continue

        prompt_id = mapping.get("promptId", "")
        variable_values = mapping.get("variableValues", {})

        # Resolve _prompt_variable:* mapped entries from sibling input_mappings.
        # These handle step-to-step data flow (e.g. story_text from generate_story).
        for map_key, map_entry in input_mappings.items():
            if not map_key.startswith("_prompt_variable:"):
                continue
            if not isinstance(map_entry, dict):
                continue
            if map_entry.get("mappingType") != "mapped":
                continue
            var_name = map_key.split(":", 1)[1]
            step_id = map_entry.get("stepId", "")
            output_field = map_entry.get("outputField", "")

            # Instance Form fields - resolve from instance parameters
            if step_id == "__instance_form__" and output_field and instance_parameters:
                form_value = _resolve_instance_form_field(
                    output_field, instance_parameters
                )
                if form_value is not None:
                    variable_values[var_name] = str(form_value)
                continue

            if step_id and output_field and previous_step_results:
                step_result = previous_step_results.get(step_id, {})
                resolved_value = step_result.get(output_field)
                if resolved_value is not None:
                    variable_values[var_name] = str(resolved_value)

        # Override with instance parameters from form submission
        # Form fields for prompt variables are keyed as _prompt_variable:{var_name}
        if instance_parameters:
            for ip_key, ip_value in instance_parameters.items():
                if ip_key.startswith("_prompt_variable:"):
                    var_name = ip_key.split(":", 1)[1]
                    variable_values[var_name] = ip_value

        # Resolve any remaining {{ step_id.field }} expressions in variable values
        if previous_step_results:
            resolved_vars: Dict[str, str] = {}
            for var_name, var_value in variable_values.items():
                if isinstance(var_value, str) and "{{" in var_value:
                    resolved_vars[var_name] = _resolve_expression(
                        var_value,
                        previous_step_results,
                        instance_parameters or {},
                    )
                else:
                    resolved_vars[var_name] = var_value
            variable_values = resolved_vars

        if not prompt_id:
            logger.warning(f"prompt mapping for '{key}' has no promptId, skipping")
            resolved[key] = {"mappingType": "static", "value": ""}
            continue

        try:
            assert prompt_service is not None
            messages = await prompt_service.assemble_prompt(
                prompt_id=uuid.UUID(prompt_id),
                variable_values=variable_values,
                organization_id=organization_id,
            )
            logger.debug(f"Assembled prompt for '{key}': {len(messages)} messages")
            resolved[key] = {"mappingType": "static", "value": messages}
            # Collect non-empty variable values for downstream reference
            for var_name, var_value in variable_values.items():
                if var_value:
                    collected_prompt_variables[var_name] = var_value
        except Exception as e:
            logger.error(f"Failed to assemble prompt for '{key}': {e}")
            raise ValueError(f"Prompt assembly failed for '{key}': {e}") from e

    return resolved, collected_prompt_variables
