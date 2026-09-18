# api/app/application/services/org_file/file_cleanup.py

"""Remove a deleted file's bytes only when no remaining row stores it."""

from pathlib import Path
from typing import Optional

from app.domain.org_file.repository import OrgFileRepository
from app.infrastructure.storage.workspace import cleanup_resource_files


async def cleanup_unreferenced_files(
    repository: OrgFileRepository,
    virtual_path: Optional[str],
    thumbnail_path: Optional[str] = None,
    workspace_path: Optional[Path] = None,
) -> int:
    """Unlink the file and thumbnail that no row references any more; returns how many were unlinked."""
    orphan_file = (
        virtual_path
        if virtual_path and await repository.count_referencing_path(virtual_path) == 0
        else None
    )
    orphan_thumbnail = (
        thumbnail_path
        if thumbnail_path
        and await repository.count_referencing_path(thumbnail_path) == 0
        else None
    )
    if not (orphan_file or orphan_thumbnail):
        return 0
    cleanup_resource_files(
        virtual_path=orphan_file or "",
        thumbnail_path=orphan_thumbnail,
        workspace_path=workspace_path,
    )
    return int(bool(orphan_file)) + int(bool(orphan_thumbnail))
