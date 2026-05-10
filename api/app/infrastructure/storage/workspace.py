# api/app/infrastructure/storage/workspace.py

"""Organization workspace directory management utilities."""

import json
import logging
import shutil
from pathlib import Path
from typing import Optional, Union
from uuid import UUID

from app.config.settings import settings

logger = logging.getLogger(__name__)


def get_workspace_path() -> Path:
    workspace = settings.WORKSPACE_ROOT
    if not workspace:
        raise RuntimeError("WORKSPACE_ROOT environment variable is not set")
    return Path(workspace)


def write_org_info(org_dir: Path, name: str, slug: str) -> None:
    """Atomic write (tmp + rename) to avoid partial reads."""
    info = {"name": name, "slug": slug}
    info_path = org_dir / ".org-info"
    tmp_path = org_dir / ".org-info.tmp"

    tmp_path.write_text(json.dumps(info, indent=2) + "\n")
    tmp_path.rename(info_path)

    logger.info(f"Wrote .org-info for {slug} at {info_path}")


def resolve_safe_path(base_dir: Path, untrusted_path: str) -> Path:
    """Resolve an untrusted path inside base_dir; raises ValueError on path traversal."""
    cleaned = untrusted_path.lstrip("/")
    resolved = (base_dir / cleaned).resolve()
    base_resolved = base_dir.resolve()

    if not resolved.is_relative_to(base_resolved):
        raise ValueError(
            f"Path traversal blocked: '{untrusted_path}' escapes '{base_dir}'"
        )
    return resolved


def resolve_org_path(
    org_id: UUID, relative_path: str, workspace_path: Optional[Path] = None
) -> Path:
    """Resolve a path within an org's workspace; raises ValueError on path traversal."""
    if workspace_path is None:
        workspace_path = get_workspace_path()
    org_dir = workspace_path / "orgs" / str(org_id)
    return resolve_safe_path(org_dir, relative_path)


def ensure_org_workspace(
    org_id: UUID,
    workspace_path: Optional[Path] = None,
    name: Optional[str] = None,
    slug: Optional[str] = None,
) -> None:
    if workspace_path is None:
        workspace_path = get_workspace_path()

    org_dir = workspace_path / "orgs" / str(org_id)

    # Define required subdirectories
    subdirs = [
        "",  # org root
        "uploads",
        "uploads/avatars",
        "instances",  # Workflow instance outputs (step JSON + downloaded files + thumbnails)
        "logs",
        "cache",
    ]

    for subdir in subdirs:
        dir_path = org_dir / subdir if subdir else org_dir
        dir_path.mkdir(parents=True, exist_ok=True)

    if name and slug:
        write_org_info(org_dir, name, slug)

    logger.info(f"Ensured workspace directories for organization {org_id} at {org_dir}")


def clear_workspace(workspace_path: Path) -> None:
    """Requires a .keep sentinel at the workspace root before deleting - guards against wrong-dir deletion."""
    if not workspace_path.exists():
        logger.warning(f"Workspace path does not exist: {workspace_path}")
        return

    # Safety check: verify this is a workspace directory by checking for .keep file at root
    keep_file = workspace_path / ".keep"
    if not keep_file.exists():
        # If no .keep file, create one for future safety checks
        keep_file.touch()
        logger.warning(
            f"Created .keep file in {workspace_path} for safety validation. "
            f"Future clear operations will require this file."
        )

    # Proceed with clearing
    orgs_dir = workspace_path / "orgs"
    if orgs_dir.exists():
        logger.info(f"Clearing workspace directory: {orgs_dir}")
        shutil.rmtree(orgs_dir)
        logger.info(f"Successfully cleared {orgs_dir}")
    else:
        logger.info(f"No orgs directory to clear at {orgs_dir}")


def sync_all_org_workspaces(
    orgs: Union[list[UUID], list[tuple[UUID, str, str]]],
    workspace_path: Optional[Path] = None,
) -> None:
    """Accept UUIDs or (UUID, name, slug) tuples; the latter also writes .org-info files."""
    if workspace_path is None:
        workspace_path = get_workspace_path()

    logger.info(f"Syncing workspace directories for {len(orgs)} organizations")

    for entry in orgs:
        try:
            if isinstance(entry, tuple):
                org_id, name, slug = entry
                ensure_org_workspace(org_id, workspace_path, name=name, slug=slug)
            else:
                ensure_org_workspace(entry, workspace_path)
        except Exception as e:
            logger.error(f"Failed to ensure workspace for org {entry}: {e}")

    logger.info(f"Completed workspace sync at {workspace_path}")


def cleanup_resource_files(
    virtual_path: str,
    thumbnail_path: Optional[str] = None,
    workspace_path: Optional[Path] = None,
) -> None:
    if workspace_path is None:
        workspace_path = get_workspace_path()

    # Delete resource file
    if virtual_path:
        resource_file = resolve_safe_path(workspace_path, virtual_path)
        if resource_file.exists():
            resource_file.unlink()
            logger.info(f"Deleted resource file: {resource_file}")

    # Delete thumbnail if exists
    if thumbnail_path:
        thumbnail_file = resolve_safe_path(workspace_path, thumbnail_path)
        if thumbnail_file.exists():
            thumbnail_file.unlink()
            logger.info(f"Deleted thumbnail file: {thumbnail_file}")
