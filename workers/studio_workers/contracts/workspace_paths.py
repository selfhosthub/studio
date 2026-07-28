# workers/studio_workers/contracts/workspace_paths.py

"""Shared workspace-path helpers for API ↔ worker file naming.

The API has historically been the sole writer of `/workspace/orgs/`,
so the filename-sanitization rule lived inside the upload-resource
service. With workers now writing directly to that tree when
`storage_mode=local`, both sides must agree on the same sanitization
*byte-for-byte* - or the API stats the wrong path and falls back to
HTTP upload, defeating the optimization.

Keep this module dependency-free (stdlib only) so both `api/` and
`workers/` can import it without dragging in domain code.
"""

from __future__ import annotations

_MAX_BASE_LEN = 100


def sanitize_step_filename(display_name: str, file_extension: str) -> str:
    """Produce the on-disk filename for a step-output file.

    Mirrors the sanitization in `ResourceUploadService.upload_file_to_step`
    exactly: strip any extension already in `display_name`, replace any
    non-alphanumeric / non-`-_.` char with `_`, truncate the base to
    100 chars, then append `file_extension` (which already includes
    the leading `.` when present, matching how the upload route
    derives it).
    """
    base_name = display_name
    if "." in base_name:
        base_name = base_name.rsplit(".", 1)[0]
    safe_name = "".join(
        c if c.isalnum() or c in "-_." else "_" for c in base_name
    )
    safe_name = safe_name[:_MAX_BASE_LEN]
    return f"{safe_name}{file_extension}"


def step_output_virtual_path(
    organization_id: str, instance_id: str, filename: str
) -> str:
    """Return the canonical `virtual_path` for a sanitized step-output filename."""
    return f"/orgs/{organization_id}/instances/{instance_id}/{filename}"
