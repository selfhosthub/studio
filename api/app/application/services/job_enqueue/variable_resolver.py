# api/app/application/services/job_enqueue/variable_resolver.py

"""
Variable resolution for step configuration parameters.

Resolves Jinja2-style {{ }} expressions in step configs using previous step
results and instance parameters. Preserves [*] expressions for array expansion.
"""

import re
from typing import Any, Dict


class VariableResolver:
    """Resolves variable references in step configuration."""

    def resolve_variables_in_config(
        self,
        step_config: Dict[str, Any],
        previous_step_results: Dict[str, Any],
        instance_parameters: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Resolve {{ }} variable references in job.parameters of the step config.

        Supports {{ steps.step_id.field }} and {{ input.field }} syntax.
        Preserves [*] expressions - array expansion runs after this.
        """
        import copy

        # Build resolution context
        context = {
            "steps": previous_step_results,
            "input": instance_parameters,
        }

        # Deep copy to avoid mutating original
        resolved = copy.deepcopy(step_config)

        # Resolve variables in the job.parameters section (where user input lives)
        if "job" in resolved and isinstance(resolved["job"], dict):
            if "parameters" in resolved["job"]:
                resolved["job"]["parameters"] = self._resolve_variables_in_value(
                    resolved["job"]["parameters"], context
                )

        return resolved

    def _resolve_variables_in_value(self, value: Any, context: Dict[str, Any]) -> Any:
        """Recursively resolve variables in a value (string, dict, list, or primitive)."""
        if isinstance(value, str):
            return self._resolve_string_variables(value, context)
        elif isinstance(value, dict):
            return {
                k: self._resolve_variables_in_value(v, context)
                for k, v in value.items()
            }
        elif isinstance(value, list):
            return [self._resolve_variables_in_value(item, context) for item in value]
        else:
            return value

    def _resolve_string_variables(self, value: str, context: Dict[str, Any]) -> Any:
        """Resolve variable references in a string value.

        A whole-string reference returns the native type. An embedded reference
        returns a string with the value interpolated.
        Preserves [*] expressions unchanged.
        """
        # Pattern for Jinja2-style variables: {{ path.to.value }} or {{ path[0].field }}
        # Supports: step_1.field, step-1.field, step_1.array[0].field, step_1.array[*].field
        jinja_pattern = r"\{\{\s*([\w.\[\]\*\d-]+)\s*\}\}"

        # IMPORTANT: Skip expressions with [*] - these are for array expansion, not regular resolution.
        # Array expansion happens AFTER variable resolution, so we must preserve these expressions.
        if "[*]" in value:
            return value

        # Check if entire string is a single variable reference
        match = re.fullmatch(jinja_pattern, value.strip())
        if match:
            # Entire value is a variable - return actual value (preserves type)
            path = match.group(1)
            resolved = self._resolve_path(path, context)
            if resolved is not None:
                return resolved
            # Variable not found - return original string
            return value

        # Check for embedded variables
        def replace_var(match: re.Match[str]) -> str:
            path = match.group(1)
            resolved = self._resolve_path(path, context)
            if resolved is not None:
                return str(resolved)
            return match.group(0)  # Keep original if not resolved

        resolved = re.sub(jinja_pattern, replace_var, value)
        return resolved

    def _resolve_path(self, path: str, context: Dict[str, Any]) -> Any:
        """Resolve a dot-notation path against the context.

        Supports explicit prefix (steps.step_id.field), shorthand (step_id.field),
        input.field, and bracket array indexing (array[0].field).
        Returns None if the path cannot be followed.
        """
        parts = path.split(".")

        # __instance_form__ is a virtual step - resolve from instance parameters
        if parts and parts[0] == "__instance_form__":
            parts = ["input"] + parts[1:]

        # Shorthand: if first segment is a known step ID (not "steps" or "input"),
        # auto-prepend "steps". This allows {{ my_step.url }} as shorthand for
        # {{ steps.my_step.url }}.
        if parts and parts[0] not in ("steps", "input"):
            steps_context = context.get("steps", {})
            if parts[0] in steps_context:
                parts = ["steps"] + parts

        current = context

        for part in parts:
            # Check for array indexing: field[0] or field[*]
            array_match = re.match(r"^(\w+)\[(\d+|\*)\]$", part)
            if array_match:
                field_name = array_match.group(1)
                index_str = array_match.group(2)

                # First resolve the field name
                if isinstance(current, dict) and field_name in current:
                    current = current[field_name]
                else:
                    return None

                # Then apply the array index
                if isinstance(current, list):
                    if index_str == "*":
                        # [*] should have been converted to [0] by now, but handle it anyway
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
            elif isinstance(current, list):
                # Support array indexing: items.0.name (legacy dot notation)
                try:
                    idx = int(part)
                    if 0 <= idx < len(current):
                        current = current[idx]
                    else:
                        return None
                except ValueError:
                    return None
            else:
                return None

        return current
