# api/app/application/services/job_enqueue/parameter_resolution.py

"""Enqueue-time parameter resolution - group expansion + file URL resolution.

Applied before HTTP envelope construction so the pre-built body is
byte-equivalent to the wire body the worker would otherwise compute.
Both transforms are pure functions with no DB or storage dependency.
"""

import logging
from typing import Any, Dict

from app.config.settings import settings
from contracts.group_expansion import expand_groups as _expand_groups_list

logger = logging.getLogger(__name__)


# File extensions the resolver recognizes as referenceable artifacts.
_FILE_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".bmp",
    ".svg",
    ".mp4",
    ".webm",
    ".mov",
    ".avi",
    ".mkv",
    ".mp3",
    ".wav",
    ".ogg",
    ".flac",
    ".pdf",
    ".doc",
    ".docx",
    ".txt",
    ".json",
    ".xml",
    ".csv",
}


def _looks_like_file_reference(value: str) -> bool:
    """String is plausibly a file reference (has a known extension or uploads/ prefix)."""
    lower = value.lower()
    for ext in _FILE_EXTENSIONS:
        if lower.endswith(ext):
            return True
    return value.startswith("uploads/")


def _resolve_single(value: str, org_id: str, instance_id: str, api_base: str) -> str:
    """Rewrite one string. External URLs and non-file-like strings pass through."""
    if not value:
        return value
    if value.startswith("http://") or value.startswith("https://"):
        return value
    if not _looks_like_file_reference(value):
        return value

    if value.startswith("uploads/"):
        return f"{api_base}/uploads/orgs/{org_id}/{value[8:]}"
    if value.startswith("/orgs/"):
        return f"{api_base}/uploads{value}"
    if "/" not in value:
        return f"{api_base}/uploads/orgs/{org_id}/instances/{instance_id}/{value}"
    return value


def _resolve_recursive(value: Any, org_id: str, instance_id: str, api_base: str) -> Any:
    """Walk a value recursively, rewriting any file-reference strings."""
    if isinstance(value, str):
        return _resolve_single(value, org_id, instance_id, api_base)
    if isinstance(value, dict):
        return {
            k: _resolve_recursive(v, org_id, instance_id, api_base)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [
            _resolve_recursive(item, org_id, instance_id, api_base) for item in value
        ]
    return value


def resolve_file_references(
    parameters: Dict[str, Any],
    org_id: str,
    instance_id: str,
) -> Dict[str, Any]:
    """Rewrite local file references into absolute URLs the provider can fetch.

    Uses the configured public base URL. Idempotent - already-absolute URLs
    and strings without recognized extensions pass through unchanged.
    """
    api_base = settings.API_BASE_URL.rstrip("/")
    return _resolve_recursive(parameters, org_id, instance_id, api_base)


def expand_groups_in_parameters(parameters: Dict[str, Any]) -> Dict[str, Any]:
    """Replace item_group entries under the scenes key with their expanded items.

    Idempotent - no-op returns the same dict instance.
    """
    scenes = parameters.get("scenes")
    if not isinstance(scenes, list):
        return parameters
    expanded = _expand_groups_list(scenes)
    if expanded is scenes:
        return parameters
    return {**parameters, "scenes": expanded}


def resolve_step_parameters(
    parameters: Dict[str, Any],
    org_id: str,
    instance_id: str,
) -> Dict[str, Any]:
    """Apply group expansion then file URL resolution in order."""
    expanded = expand_groups_in_parameters(parameters)
    return resolve_file_references(expanded, org_id, instance_id)
