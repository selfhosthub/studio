# contracts/downloaded_file.py

"""
Downloaded File Contract: API → Worker transport shape.

Canonical definition of the file metadata dicts inside the
``downloaded_files`` array that flows from the API result processor
to downstream workers (group expansion, transfer, etc.).

Producer: ``resources_to_downloaded_files()`` in resource_converter.py.
Consumer: ``pull_from_circular_stack()`` in group_expansion.py (and others).

Python 3.11 compatible.
"""

from typing import Any, Dict, Optional

from pydantic import BaseModel


class DownloadedFileContract(BaseModel):
    """
    One entry in the ``downloaded_files`` transport array.

    Rules:
    - ``url`` is the single canonical URL that downstream consumers use
      to fetch the file.  It is always populated by the producer from
      ``API_BASE_URL + /uploads + virtual_path``.
    - Consumers must read ``url`` only.  No fallback chains
      (``source_url or virtual_path or ...``).
    - ``source_url`` is the original provider CDN URL preserved for
      audit/debug.  It must never be used as a fetch target.
    - ``virtual_path`` is the workspace-relative storage path
      (e.g. ``/orgs/{org}/instances/{inst}/file.png``).
    """

    # ── Core access ──────────────────────────────────────────────────
    url: str  # Canonical fetch URL (absolute or relative)
    filename: str
    virtual_path: Optional[str] = None
    file_size: int = 0

    # ── Provider audit ───────────────────────────────────────────────
    source_url: Optional[str] = None  # Original CDN URL (do NOT fetch)

    # ── Display / metadata ───────────────────────────────────────────
    index: int = 0
    display_name: str = "File"
    mime_type: Optional[str] = None
    file_extension: Optional[str] = None
    has_thumbnail: bool = False

    # ── Optional metadata (set when present) ─────────────────────────
    iteration_index: Optional[int] = None
    seed: Optional[int] = None
    thumbnail_path: Optional[str] = None
    original_filename: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    duration: Optional[float] = None

    def to_transport(self) -> Dict[str, Any]:
        """Serialize to the dict shape consumed by workers.

        Excludes None-valued optional fields to keep payloads compact.
        """
        data = self.model_dump(exclude_none=True)
        # Always include core fields even when falsy
        data["file_size"] = self.file_size
        data["index"] = self.index
        data["has_thumbnail"] = self.has_thumbnail
        return data
