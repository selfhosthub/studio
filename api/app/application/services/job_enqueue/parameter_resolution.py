# api/app/application/services/job_enqueue/parameter_resolution.py

"""Enqueue-time parameter resolution - group expansion + file URL resolution.

Applied before HTTP envelope construction so the pre-built body is
byte-equivalent to the wire body the worker would otherwise compute.
Both transforms are pure functions with no DB or storage dependency.
"""

import logging
from typing import Any, Dict, Optional

from app.config.settings import settings
from app.infrastructure.security.asset_signing import build_signed_asset_path
from studio_workers.contracts.group_expansion import expand_groups as _expand_groups_list

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


def _resolve_single(
    value: str, org_id: str, instance_id: str, api_base: str
) -> Any:
    """Rewrite one string into a media-source record.

    File references that map to a workspace path become a dual-view dict
    ``{"virtual_path", "url", "filename"}`` so workers can implement the
    uniform "local first, URL fallback" policy. External URLs and
    non-file-like strings pass through unchanged.

    The dual-view dict matches ``DownloadedFileContract``'s wire shape but
    is intentionally minimal (no size / mime / extension) - operator
    decision: same shape, not same fullness. A DB-backed enrichment can be
    added later for any consumer that needs it.
    """
    if not value:
        return value
    if value.startswith("http://") or value.startswith("https://"):
        return value
    if not _looks_like_file_reference(value):
        return value

    if value.startswith("uploads/"):
        virtual_path = f"/orgs/{org_id}/{value[8:]}"
    elif value.startswith("/orgs/"):
        virtual_path = value
    elif "/" not in value:
        virtual_path = f"/orgs/{org_id}/instances/{instance_id}/{value}"
    else:
        return value

    # virtual_path is always /orgs/{org_id}/...; strip that prefix for the
    # signed public route /api/v1/public/assets/{org_id}/{rel_path}.
    rel_path = virtual_path[len(f"/orgs/{org_id}/"):]
    return {
        "virtual_path": virtual_path,
        "url": f"{api_base}{build_signed_asset_path(org_id, rel_path)}",
        "filename": virtual_path.rsplit("/", 1)[-1],
    }


def is_media_ref(value: Any) -> bool:
    """Structural check for a media-source dual-view dict.

    Used at the http_request body boundary to flatten records back to URL
    strings for byte-equivalent wire output. The shape ``{virtual_path,
    url, filename}`` is the minimal form emitted by ``_resolve_single``;
    DownloadedFileContract dicts with more fields are also media refs.
    """
    return (
        isinstance(value, dict)
        and "virtual_path" in value
        and "url" in value
        and "filename" in value
    )


def flatten_media_refs_to_urls(value: Any) -> Any:
    """Walk a structure and replace media-ref dicts with their ``url`` string.

    Used by ``http_request_builder.try_build_http_request`` to keep the
    pre-built body byte-equivalent to today's wire (the dual-write
    invariant). The original structure is not mutated; a copy is returned
    only when a media ref is found in the subtree.
    """
    if is_media_ref(value):
        return value.get("url") or ""
    if isinstance(value, dict):
        return {k: flatten_media_refs_to_urls(v) for k, v in value.items()}
    if isinstance(value, list):
        return [flatten_media_refs_to_urls(v) for v in value]
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


def collapse_file_source_to_local_path(
    parameters: Dict[str, Any],
    parameter_mapping: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Replace the declared file-source param's media ref with its virtual_path.

    The catalog declares which param carries the upload file via
    ``parameter_mapping.file_source_param``. Workers receive a local-filesystem
    path string for it; the workspace volume is mounted, so the worker streams
    the file directly without a network round-trip.
    """
    if not parameter_mapping:
        return parameters
    key = parameter_mapping.get("file_source_param")
    if not key or key not in parameters:
        return parameters
    value = parameters[key]
    if not is_media_ref(value):
        return parameters
    return {**parameters, key: value["virtual_path"]}


def resolve_step_parameters(
    parameters: Dict[str, Any],
    org_id: str,
    instance_id: str,
    expand_groups: bool = True,
) -> Dict[str, Any]:
    """Apply group expansion (unless expand_groups=False) then file URL resolution in order."""
    expanded = expand_groups_in_parameters(parameters) if expand_groups else parameters
    return resolve_file_references(expanded, org_id, instance_id)
