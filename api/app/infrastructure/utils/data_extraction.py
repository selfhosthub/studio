# api/app/infrastructure/utils/data_extraction.py
"""Path-expression extraction from nested structures (dot notation, array index, array filter)."""

import re
from typing import Any, Dict, List, Optional


def extract_by_path(
    data: Any,
    path: str,
    params: Optional[Dict[str, Any]] = None,
    default: Any = None,
) -> Any:
    if params is None:
        params = {}

    if not path:
        return data if data is not None else default

    return _extract_recursive(data, path, params)


def _extract_recursive(data: Any, path: str, params: Dict[str, Any]) -> Any:
    if data is None:
        return None

    filter_match = re.match(r"^(\w+)\[(\w+)=\$\{(\w+)\}\](?:\.(.+))?$", path)
    if filter_match:
        return _handle_array_filter(data, filter_match, params)

    index_match = re.match(r"^(\w+)\[(\d+)\](?:\.(.+))?$", path)
    if index_match:
        return _handle_array_index(data, index_match, params)

    return _handle_dot_notation(data, path, params)


def _handle_array_filter(
    data: Any, match: re.Match[str], params: Dict[str, Any]
) -> Any:
    array_field, filter_field, param_name, remaining_path = match.groups()

    # Get the array from data
    if not isinstance(data, dict):
        return None
    array_data = data.get(array_field)

    if not isinstance(array_data, list):
        return None

    # Get filter value from params
    filter_value = params.get(param_name)
    if filter_value is None:
        return []

    # Find matching items
    matching_items = [
        item
        for item in array_data
        if isinstance(item, dict) and item.get(filter_field) == filter_value
    ]

    if not matching_items:
        return []

    # If there's a remaining path, extract from the first match
    if remaining_path:
        return _extract_recursive(matching_items[0], remaining_path, params)

    return matching_items


def _handle_array_index(data: Any, match: re.Match[str], params: Dict[str, Any]) -> Any:
    array_field, index_str, remaining_path = match.groups()
    index = int(index_str)

    # Get the array from data
    if not isinstance(data, dict):
        return None
    array_data = data.get(array_field)

    if not isinstance(array_data, list):
        return None

    # Bounds check
    if index < 0 or index >= len(array_data):
        return None

    item = array_data[index]

    # If there's a remaining path, continue extraction
    if remaining_path:
        return _extract_recursive(item, remaining_path, params)

    return item


def _handle_dot_notation(data: Any, path: str, params: Dict[str, Any]) -> Any:
    parts = path.split(".", 1)
    current_key = parts[0]
    remaining_path = parts[1] if len(parts) > 1 else None

    if not isinstance(data, dict):
        return None

    if current_key not in data:
        return None

    result = data[current_key]

    if remaining_path:
        return _extract_recursive(result, remaining_path, params)

    return result


def extract_list(
    data: Any,
    path: str,
    params: Optional[Dict[str, Any]] = None,
) -> List[Any]:
    """Convenience wrapper that guarantees a list return; empty list on mismatch."""
    result = extract_by_path(data, path, params, default=[])
    if isinstance(result, list):
        return result
    return []
