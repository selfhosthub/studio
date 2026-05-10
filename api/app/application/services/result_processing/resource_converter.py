# api/app/application/services/result_processing/resource_converter.py

"""Converts `OrgFile` domain objects to the `downloaded_files` transport format (DownloadedFileContract)."""

import os
from datetime import datetime
from typing import Any, Dict, List

from app.domain.org_file.models import OrgFile


def resources_to_downloaded_files(
    resources: List[OrgFile],
    api_base_url: str = "",
) -> List[Dict[str, Any]]:
    """
    Convert OrgFile records to downloaded_files format.

    This is the inverse of creating OrgFile from downloaded_files.
    It rebuilds the array from database records, ensuring that:
    1. Regeneration doesn't lose reference to non-regenerated files
    2. Downstream steps see ALL available files, not just newly created ones
    3. File metadata is preserved for mapping (virtual_path, seed, etc.)

    Args:
        resources: List of OrgFile domain objects
        api_base_url: Base URL for constructing canonical `url` field.
            Empty string produces relative URLs (works behind reverse proxy).

    Returns:
        List of file info dicts in downloaded_files format, sorted by:
        - iteration_index (for iteration jobs)
        - index (position within batch)
        - created_at descending (newest first for regenerated images)
    """
    # Sort by iteration_index, then by index, then by created_at descending
    # This ensures regenerated images appear at their correct position
    sorted_resources = sorted(
        resources,
        key=lambda r: (
            (r.metadata or {}).get("iteration_index", 0),
            (r.metadata or {}).get("index", 0),
            -(r.created_at or datetime.min).timestamp(),
        ),
    )

    downloaded_files: List[Dict[str, Any]] = []
    for resource in sorted_resources:
        metadata = resource.metadata or {}

        # Recover actual filename from virtual_path (display_name may be a formatted label)
        filename = (
            os.path.basename(resource.virtual_path)
            if resource.virtual_path
            else (resource.display_name or "file")
        )

        # Build canonical URL: API_BASE_URL + /uploads + virtual_path
        url = ""
        if resource.virtual_path:
            url = f"{api_base_url}/uploads{resource.virtual_path}"

        file_info: Dict[str, Any] = {
            # Canonical fetch URL (DownloadedFileContract.url)
            "url": url,
            # Core fields for file access
            "filename": filename,
            "virtual_path": resource.virtual_path,
            "file_size": resource.file_size or 0,
            # Source URL (CDN URL for externally hosted files - audit only)
            "source_url": resource.provider_url,
            # Metadata for downstream mapping
            "index": metadata.get("index", 0),
            "display_name": resource.display_name or "Image",
            "mime_type": resource.mime_type,
            "file_extension": resource.file_extension,
            # Optional fields from metadata
            "has_thumbnail": resource.has_thumbnail,
        }

        if "iteration_index" in metadata:
            file_info["iteration_index"] = metadata["iteration_index"]
        if "seed" in metadata:
            file_info["seed"] = metadata["seed"]
        if "thumbnail_path" in metadata:
            file_info["thumbnail_path"] = metadata["thumbnail_path"]
        if "original_filename" in metadata:
            file_info["original_filename"] = metadata["original_filename"]
        if "width" in metadata:
            file_info["width"] = metadata["width"]
        if "height" in metadata:
            file_info["height"] = metadata["height"]
        if "duration" in metadata:
            file_info["duration"] = metadata["duration"]

        downloaded_files.append(file_info)

    return downloaded_files
