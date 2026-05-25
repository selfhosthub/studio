# api/app/application/services/mapping_resolver.py

"""Field-mapping resolver for workflow step parameters.

Sources: trigger data, completed step extracted_outputs, static values.
Supports JSONPath, array-index syntax, and [*] prototype expansion (one item
with [*] mappings expands to N copies, zip-style across multiple iterables).
"""

import copy
import logging
import re
from typing import Any, Dict, List, Optional

import jsonpath_ng

logger = logging.getLogger(__name__)


class MappingResolver:
    """Field-mapping resolver.

    Mapping syntax:
      trigger.path            - trigger data
      steps.step_id.path      - completed step extracted_outputs
      value:literal           - static literal
      JSONPath / arr[N].path  - nested access
    """

    def __init__(self):
        pass

    @staticmethod
    def _resolve_instance_form_field(
        output_field: str, trigger_data: Dict[str, Any]
    ) -> Any:
        """Resolve an __instance_form__ field from instance trigger data.

        Form submissions live under form_values keyed as `{step_id}.{param_path}`.
        """
        tv_key = f"_prompt_variable:{output_field}"

        search_dicts = [trigger_data]
        form_vals = trigger_data.get("form_values")
        if isinstance(form_vals, dict):
            search_dicts.append(form_vals)

        for search_dict in search_dicts:
            if output_field in search_dict:
                return search_dict[output_field]
            if tv_key in search_dict:
                return search_dict[tv_key]
            for key, value in search_dict.items():
                if key.endswith(f".{output_field}") or key.endswith(f".{tv_key}"):
                    return value

        return None

    def resolve_mappings(
        self, input_mappings: Dict[str, str], execution_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Resolve all input mappings against the execution context."""
        resolved = {}

        for param_name, mapping_expr in input_mappings.items():
            try:
                value = self._resolve_single_mapping(mapping_expr, execution_context)
                if value is not None:
                    resolved[param_name] = value
                elif (
                    isinstance(mapping_expr, dict)
                    and mapping_expr.get("mappingType") == "form"
                ):
                    logger.debug(
                        f"Form mapping for parameter '{param_name}' skipped "
                        f"(handled by inject_form_values_into_snapshot)"
                    )
                else:
                    logger.warning(
                        f"Mapping '{mapping_expr}' for parameter '{param_name}' "
                        f"resolved to None"
                    )
            except Exception as e:
                logger.error(
                    f"Failed to resolve mapping '{mapping_expr}' for '{param_name}': {e}"
                )
                # One failure must not block other mappings.

        return resolved

    def _resolve_single_mapping(
        self, mapping_expr: Any, execution_context: Dict[str, Any]
    ) -> Any:
        """Resolve one mapping expression. Accepts string ("trigger.x", "steps.y.z",
        "value:literal") or dict ({"mappingType": "mapped"|"static"|"trigger"|"form", ...}).
        """
        if isinstance(mapping_expr, dict):
            mapping_type = mapping_expr.get("mappingType")
            if mapping_type == "mapped":
                step_id = mapping_expr.get("stepId")
                output_field = mapping_expr.get("outputField")

                if step_id == "__instance_form__" and output_field:
                    trigger_data = execution_context.get("trigger", {})
                    resolved = self._resolve_instance_form_field(
                        output_field, trigger_data
                    )
                    if resolved is not None:
                        return resolved
                    logger.warning(
                        f"Instance form field '{output_field}' not found in trigger data. "
                        f"Available keys: {list(trigger_data.keys())}"
                    )
                    return None

                if step_id and output_field:
                    string_expr = f"steps.{step_id}.{output_field}"
                    return self._resolve_single_mapping(string_expr, execution_context)
                else:
                    logger.warning(
                        f"Dict mapping missing stepId or outputField: {mapping_expr}"
                    )
                    return None
            elif mapping_type == "static":
                return mapping_expr.get("value")
            elif mapping_type == "trigger":
                field = mapping_expr.get("field") or mapping_expr.get("outputField")
                if field:
                    return self._resolve_from_trigger(field, execution_context)
                return None
            elif mapping_type == "form":
                # Form values are injected upstream, not resolved here.
                return None
            else:
                logger.warning(f"Unknown mappingType in dict mapping: {mapping_type}")
                return None

        if not isinstance(mapping_expr, str):
            logger.warning(f"Unexpected mapping_expr type: {type(mapping_expr)}")
            return None

        if mapping_expr.startswith("value:"):
            literal_value = mapping_expr[6:]
            return self._parse_literal(literal_value)

        parts = mapping_expr.split(".", 1)
        if len(parts) < 2:
            logger.warning(f"Invalid mapping expression format: '{mapping_expr}'")
            return None

        source_type = parts[0]
        path = parts[1]

        if source_type == "trigger":
            return self._resolve_from_trigger(path, execution_context)
        elif source_type == "steps":
            return self._resolve_from_steps(path, execution_context)
        else:
            logger.warning(
                f"Unknown source type in mapping: '{source_type}' "
                f"(expected 'trigger', 'steps', or 'value:')"
            )
            return None

    def _resolve_from_trigger(
        self, path: str, execution_context: Dict[str, Any]
    ) -> Any:
        trigger_data = execution_context.get("trigger", {})
        if not trigger_data:
            logger.debug("No trigger data available in execution context")
            return None

        return self._extract_value_by_path(path, trigger_data)

    def _resolve_from_steps(self, path: str, execution_context: Dict[str, Any]) -> Any:
        steps_data = execution_context.get("steps", {})
        if not steps_data:
            logger.debug("No steps data available in execution context")
            return None

        parts = path.split(".", 1)

        step_id = parts[0]
        field_path = parts[1] if len(parts) > 1 else None

        step_outputs = steps_data.get(step_id)
        if step_outputs is None:
            logger.warning(
                f"Step '{step_id}' not found in execution context. "
                f"Available steps: {list(steps_data.keys())}"
            )
            return None

        if not field_path:
            return step_outputs

        return self._extract_value_by_path(field_path, step_outputs)

    def _extract_value_by_path(self, path: str, data: Dict[str, Any]) -> Any:
        """Extract via dot notation, JSONPath, or array-index syntax."""
        logger.debug(
            f"Extracting path '{path}' from data keys: {list(data.keys()) if isinstance(data, dict) else type(data)}"
        )

        if "[" in path:
            return self._extract_with_array_index(path, data)

        if "." in path:
            try:
                expr = jsonpath_ng.parse(path)
                matches = expr.find(data)
                if matches:
                    values = [m.value for m in matches]
                    return values[0] if len(values) == 1 else values
                else:
                    logger.debug(f"Path '{path}' not found in data")
                    return None
            except Exception as e:
                logger.error(f"JSONPath parsing failed for '{path}': {e}")
                return None
        else:
            value = data.get(path)
            if value is None:
                logger.debug(f"Field '{path}' not found in data")
            return value

    def _extract_with_array_index(self, path: str, data: Any) -> Any:
        """Extract via array-index syntax: 'field[0]', 'field[0].nested', etc."""
        current = data

        # Split on dots, preserving array indices.
        segments = re.split(r"\.(?![^\[]*\])", path)

        for segment in segments:
            if current is None:
                logger.debug(
                    f"Path segment '{segment}' cannot be resolved - current is None"
                )
                return None

            array_match = re.match(r"^(\w+)\[(\d+)\]$", segment)
            if array_match:
                field_name = array_match.group(1)
                index = int(array_match.group(2))
                logger.debug(
                    f"Processing array segment: field='{field_name}', index={index}"
                )

                if isinstance(current, dict):
                    current = current.get(field_name)
                    if current is None:
                        return None
                else:
                    logger.debug(
                        f"Cannot get field '{field_name}' from {type(current)}"
                    )
                    return None

                if isinstance(current, list):
                    if 0 <= index < len(current):
                        current = current[index]
                    else:
                        logger.debug(
                            f"Index {index} out of bounds for array of length {len(current)}"
                        )
                        return None
                else:
                    logger.debug(f"Cannot index {type(current)} with index {index}")
                    return None
            else:
                if isinstance(current, dict):
                    current = current.get(segment)
                    if current is None:
                        logger.debug(f"Field '{segment}' not found")
                        return None
                else:
                    logger.debug(f"Cannot get field '{segment}' from {type(current)}")
                    return None

        logger.debug(f"Extracted value: {current}")
        return current

    def _parse_literal(self, literal_str: str) -> Any:
        """Try JSON, then int, then float, fall back to string."""
        import json

        try:
            return json.loads(literal_str)
        except (json.JSONDecodeError, ValueError):
            pass

        try:
            return int(literal_str)
        except ValueError:
            pass

        try:
            return float(literal_str)
        except ValueError:
            pass

        return literal_str

    def build_execution_context(
        self, trigger_data: Dict[str, Any], completed_steps: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Build {"trigger": ..., "steps": {step_id: extracted_outputs}}."""
        context = {"trigger": trigger_data or {}, "steps": {}}

        for step in completed_steps:
            step_id = step.get("step_id")
            extracted_outputs = step.get("extracted_outputs", {})

            if step_id:
                context["steps"][step_id] = extracted_outputs

        logger.debug(
            f"Built execution context with trigger and "
            f"{len(context['steps'])} completed steps"
        )

        return context

    def expand_array_parameter(
        self,
        prototype_array: List[Dict[str, Any]],
        iteration_config: Dict[str, Any],
        execution_context: Dict[str, Any],
        input_mappings: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Expand a single prototype item to N items by zipping [*] expressions.

        iteration_mode: shortest (default), longest, strict, primary.
        Multiple [*] expressions in the prototype zip together - all use the
        same index per copy.
        """
        if not iteration_config.get("enabled"):
            return prototype_array

        source_step_id = iteration_config.get("source_step_id")
        source_output_field = iteration_config.get("source_output_field")

        if not source_step_id or not source_output_field:
            logger.warning(
                "Iteration config missing source_step_id or source_output_field"
            )
            return prototype_array

        if not prototype_array:
            logger.warning("Prototype array is empty")
            return []

        prototype_item = prototype_array[0]

        loop_settings = self._build_loop_settings(input_mappings)

        array_refs = self._scan_array_references(
            prototype_item, execution_context, loop_settings
        )

        if not array_refs:
            logger.warning("No [*] array references found in prototype")
            return prototype_array

        for ref_key, ref_info in array_refs.items():
            loop_str = " (loop)" if ref_info.get("loop") else ""
            logger.debug(
                f"Found array ref: {ref_key} (length={ref_info['length']}{loop_str})"
            )

        # Looped arrays cycle - they don't constrain iteration count.
        all_lengths = [
            ref["length"] for ref in array_refs.values() if ref["length"] is not None
        ]
        non_looped_lengths = [
            ref["length"]
            for ref in array_refs.values()
            if ref["length"] is not None and not ref.get("loop", False)
        ]

        if not all_lengths:
            logger.warning("No valid arrays found for iteration")
            return []

        iteration_mode = iteration_config.get("iteration_mode", "shortest")

        effective_lengths = non_looped_lengths if non_looped_lengths else all_lengths

        if iteration_mode == "strict":
            if len(set(effective_lengths)) > 1:
                logger.error(
                    f"Strict mode: array lengths don't match: {array_refs}. "
                    f"Lengths: {effective_lengths}"
                )
                return prototype_array
            iteration_count = effective_lengths[0]
        elif iteration_mode == "longest":
            iteration_count = max(effective_lengths)
        elif iteration_mode == "primary":
            primary_key = f"{source_step_id}.{source_output_field}"
            if primary_key in array_refs and array_refs[primary_key]["length"]:
                iteration_count = array_refs[primary_key]["length"]
            else:
                iteration_count = effective_lengths[0] if effective_lengths else 0
        else:
            iteration_count = min(effective_lengths)

        if iteration_count == 0:
            logger.warning("Iteration count is 0, returning empty array")
            return []

        logger.info(
            f"Iteration mode '{iteration_mode}': {iteration_count} iterations "
            f"(array lengths: {effective_lengths})"
        )

        expanded_array = []
        for index in range(iteration_count):
            expanded_item = self._expand_item_with_index(
                prototype_item=prototype_item,
                index=index,
                array_refs=array_refs,
                execution_context=execution_context,
                iteration_mode=iteration_mode,
            )
            expanded_array.append(expanded_item)

        logger.info(
            f"Expanded array from {len(prototype_array)} prototype(s) to "
            f"{len(expanded_array)} items"
        )

        return expanded_array

    def _build_loop_settings(
        self,
        input_mappings: Optional[Dict[str, Any]],
    ) -> Dict[str, bool]:
        """Map "step_id.field" → True for any mapping flagged loop=True."""
        loop_settings: Dict[str, bool] = {}

        if not input_mappings:
            return loop_settings

        # "generated_images[*].url" → "generated_images"
        pattern = r"^(\w+)\[\*\]"

        for _param_key, mapping in input_mappings.items():
            if not isinstance(mapping, dict):
                continue

            loop = mapping.get("loop", False)
            if not loop:
                continue

            step_id = mapping.get("stepId") or mapping.get("source_step_id")
            if not step_id:
                continue

            output_field = mapping.get("outputField") or mapping.get(
                "source_output_field"
            )
            if not output_field:
                continue

            match = re.match(pattern, output_field)
            if match:
                field = match.group(1)
            else:
                # Field without [*] - strip any nested suffix.
                field = output_field.split("[")[0].split(".")[0]

            ref_key = f"{step_id}.{field}"
            loop_settings[ref_key] = True
            logger.debug(f"Loop setting: {ref_key} = True")

        return loop_settings

    def _scan_array_references(
        self,
        data: Any,
        execution_context: Dict[str, Any],
        loop_settings: Optional[Dict[str, bool]] = None,
    ) -> Dict[str, Dict[str, Any]]:
        """Find all [*] refs in data: {"step_id.field": {array, length, loop}}."""
        refs: Dict[str, Dict[str, Any]] = {}
        pattern = r"\{\{\s*(?:steps\.)?(\w+)\.(\w+)\[\*\](?:\.(.+?))?\s*\}\}"

        def scan_value(value: Any) -> None:
            if isinstance(value, str):
                match = re.match(pattern, value.strip())
                if match:
                    step_id = match.group(1)
                    field = match.group(2)
                    ref_key = f"{step_id}.{field}"

                    if ref_key not in refs:
                        array = self._get_array_from_context(
                            step_id, field, execution_context
                        )
                        loop = (
                            loop_settings.get(ref_key, False)
                            if loop_settings
                            else False
                        )
                        refs[ref_key] = {
                            "step_id": step_id,
                            "field": field,
                            "array": array,
                            "length": len(array) if isinstance(array, list) else None,
                            "loop": loop,
                        }
            elif isinstance(value, dict):
                for v in value.values():
                    scan_value(v)
            elif isinstance(value, list):
                for item in value:
                    scan_value(item)

        scan_value(data)
        return refs

    def _get_array_from_context(
        self,
        step_id: str,
        field: str,
        execution_context: Dict[str, Any],
    ) -> Optional[List[Any]]:
        steps_data = execution_context.get("steps", {})
        step_outputs = steps_data.get(step_id, {})

        if not step_outputs:
            logger.debug(f"Step '{step_id}' not found in execution context")
            return None

        value = step_outputs.get(field)

        if not isinstance(value, list):
            logger.debug(
                f"Field '{step_id}.{field}' is not an array: " f"{type(value).__name__}"
            )
            return None

        return value

    def _extract_element_value(
        self,
        element: Any,
        nested_path: Optional[str],
    ) -> Any:
        if not nested_path:
            return element

        if isinstance(element, dict):
            return self._extract_value_by_path(nested_path, element)

        logger.debug(
            f"Cannot extract nested path '{nested_path}' from "
            f"{type(element).__name__}, returning element as-is"
        )
        return element

    def _expand_item_with_index(
        self,
        prototype_item: Dict[str, Any],
        index: int,
        array_refs: Dict[str, Dict[str, Any]],
        execution_context: Dict[str, Any],
        iteration_mode: str = "shortest",
    ) -> Dict[str, Any]:
        """Deep-copy the prototype and resolve every [*] expression at index."""
        expanded_item = copy.deepcopy(prototype_item)

        self._resolve_array_mappings_recursive(
            data=expanded_item,
            index=index,
            array_refs=array_refs,
            iteration_mode=iteration_mode,
        )

        return expanded_item

    def _resolve_array_mappings_recursive(
        self,
        data: Any,
        index: int,
        array_refs: Dict[str, Dict[str, Any]],
        iteration_mode: str,
    ) -> None:
        """Mutates `data` in place."""
        if isinstance(data, dict):
            for key, value in list(data.items()):
                if isinstance(value, str):
                    resolved = self._resolve_array_expression(
                        value=value,
                        index=index,
                        array_refs=array_refs,
                        iteration_mode=iteration_mode,
                    )
                    if resolved is not None:
                        data[key] = resolved
                elif isinstance(value, (dict, list)):
                    self._resolve_array_mappings_recursive(
                        data=value,
                        index=index,
                        array_refs=array_refs,
                        iteration_mode=iteration_mode,
                    )
        elif isinstance(data, list):
            for i, item in enumerate(data):
                if isinstance(item, str):
                    resolved = self._resolve_array_expression(
                        value=item,
                        index=index,
                        array_refs=array_refs,
                        iteration_mode=iteration_mode,
                    )
                    if resolved is not None:
                        data[i] = resolved
                elif isinstance(item, (dict, list)):
                    self._resolve_array_mappings_recursive(
                        data=item,
                        index=index,
                        array_refs=array_refs,
                        iteration_mode=iteration_mode,
                    )

    def _resolve_array_expression(
        self,
        value: str,
        index: int,
        array_refs: Dict[str, Dict[str, Any]],
        iteration_mode: str,
    ) -> Optional[Any]:
        """Resolve a `{{ step.field[*].nested }}` expression at the given index.

        Returns None when value isn't a [*] expression. All [*] expressions in
        the same prototype use the same index (zip-style).
        """
        # {{ step.field[*].nested }} or {{ steps.step.field[*].nested }}
        pattern = r"\{\{\s*(?:steps\.)?(\w+)\.(\w+)\[\*\](?:\.(.+?))?\s*\}\}"
        match = re.match(pattern, value.strip())

        if not match:
            return None

        step_id = match.group(1)
        field = match.group(2)
        nested_path = match.group(3)

        ref_key = f"{step_id}.{field}"

        ref_info = array_refs.get(ref_key)
        if not ref_info:
            logger.warning(f"Array ref '{ref_key}' not found in pre-scanned refs")
            return None

        array = ref_info.get("array")
        loop_enabled = ref_info.get("loop", False)

        if array is None:
            logger.debug(f"'{ref_key}' is not an array, returning None")
            return None

        effective_index = index

        if index >= len(array):
            if loop_enabled:
                effective_index = index % len(array)
                logger.debug(
                    f"Loop mode: index {index} -> {effective_index} for '{ref_key}' "
                    f"(length={len(array)})"
                )
            elif iteration_mode == "longest":
                logger.debug(
                    f"Index {index} >= length {len(array)} for '{ref_key}', "
                    f"returning None (longest mode)"
                )
                return None
            else:
                # shortest/strict modes should never hit OOB if validation was correct.
                logger.warning(
                    f"Unexpected: index {index} >= length {len(array)} for '{ref_key}'"
                )
                return None

        element = array[effective_index]

        result = self._extract_element_value(element, nested_path)

        logger.debug(
            f"Resolved {ref_key}[{index}]{f'.{nested_path}' if nested_path else ''} = {result}"
        )

        return result

    def _resolve_scalar_expression(
        self, value: str, execution_context: Dict[str, Any]
    ) -> Any:
        """Resolve `{{ step.path }}` (no [*]). Returns the value unchanged on no match."""
        pattern = r"\{\{\s*(?:steps\.)?(\w+)\.(.+?)\s*\}\}"
        match = re.match(pattern, value.strip())

        if not match:
            return value

        step_id = match.group(1)
        field_path = match.group(2)

        steps_data = execution_context.get("steps", {})
        step_outputs = steps_data.get(step_id, {})

        if not step_outputs:
            logger.warning(f"Step '{step_id}' not found in execution context")
            return value

        return self._extract_value_by_path_with_index(field_path, step_outputs)

    def _extract_value_by_path_with_index(self, path: str, data: Dict[str, Any]) -> Any:
        """Extract by path with array indices (`array[0].field`).

        Returns the original path string when extraction fails (caller signals
        unresolved expression by string-equality check).
        """
        current = data

        parts = re.split(r"\.(?![^\[]*\])", path)

        for part in parts:
            if current is None:
                return path

            array_match = re.match(r"(\w+)?\[(\d+)\]", part)
            if array_match:
                field_name = array_match.group(1)
                index = int(array_match.group(2))

                if field_name:
                    if isinstance(current, dict):
                        current = current.get(field_name)
                    else:
                        return path

                if isinstance(current, list) and 0 <= index < len(current):
                    current = current[index]
                else:
                    logger.warning(
                        f"Cannot index into {type(current)} with index {index}"
                    )
                    return path
            else:
                if isinstance(current, dict):
                    current = current.get(part)
                else:
                    return path

        return current if current is not None else path
