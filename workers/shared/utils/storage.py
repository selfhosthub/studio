# workers/shared/utils/storage.py

"""
Shared storage utilities for workers to write results to /workspace.

Workers write results to filesystem, API serves them to users.
"""
import logging
import os
import json
from pathlib import Path
from typing import Dict, Any

from shared.settings import settings
from shared.utils.security import validate_virtual_path

logger = logging.getLogger(__name__)


class StorageClient:
    """File storage client for job results."""

    def __init__(self):
        self.workspace_root: str = settings.WORKSPACE_ROOT
        logger.debug(f"Using workspace root: {self.workspace_root}")

    def get_instance_path(self, org_id: str, instance_id: str) -> Path:
        """Return the storage directory for a workflow instance, creating it if needed."""
        path = Path(self.workspace_root) / "orgs" / org_id / "instances" / instance_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def write_final_result(
        self, org_id: str, instance_id: str, result: Dict[str, Any]
    ) -> str:
        """Write final workflow result to storage; returns relative path."""
        instance_path = self.get_instance_path(org_id, instance_id)
        file_path = instance_path / "result.json"

        with open(file_path, "w") as f:
            json.dump(result, f, indent=2)

        relative_path = f"/orgs/{org_id}/instances/{instance_id}/result.json"
        logger.debug(f"Wrote final result to: {relative_path}")

        return relative_path

    def write_webhook_failure_marker(self, org_id: str, instance_id: str, error: str):
        """Write marker file for a failed webhook delivery; processed on the next cleanup tick."""
        instance_path = self.get_instance_path(org_id, instance_id)
        file_path = instance_path / "webhook_failed.json"

        with open(file_path, "w") as f:
            json.dump({"error": error, "timestamp": str(instance_id)}, f)

        logger.warning("Wrote webhook failure marker")

    def upload_file(
        self,
        org_id: str,
        local_path: str,
        storage_path: str,
        content_type: str = "application/octet-stream",
    ) -> str:
        """Copy a file into org storage; returns the URL path for API serving."""
        import shutil

        # Create destination directory
        dest_dir = (
            Path(self.workspace_root)
            / "orgs"
            / org_id
            / "files"
            / os.path.dirname(storage_path)
        )
        dest_dir.mkdir(parents=True, exist_ok=True)

        # Copy file to storage
        dest_path = Path(self.workspace_root) / "orgs" / org_id / "files" / storage_path
        shutil.copy2(local_path, dest_path)

        # Return URL path for API to serve
        url_path = f"/orgs/{org_id}/files/{storage_path}"
        logger.debug(f"Uploaded file to: {url_path}")

        return url_path

    def download_to_temp(self, virtual_path: str) -> str:
        """Copy a workspace file to a temp directory; returns the temp path.

        virtual_path: /orgs/{org_id}/instances/{inst_id}/file.png or /orgs/{org_id}/files/...
        """
        import shutil
        import tempfile

        # Parse virtual_path to get filesystem path
        # Format: /orgs/{org_id}/instances/{instance_id}/filename.png
        # or: /orgs/{org_id}/files/{storage_path}
        if not virtual_path.startswith("/orgs/"):
            raise ValueError(f"Invalid virtual_path format: {virtual_path}")

        # Validate path stays within workspace (prevents traversal like /orgs/../../etc/passwd)
        resolved = validate_virtual_path(virtual_path, self.workspace_root)
        source_path = Path(resolved)

        if not source_path.exists():
            raise FileNotFoundError(f"File not found in storage: {virtual_path}")

        # Copy to temp directory
        temp_dir = tempfile.mkdtemp(prefix="studio_worker_")
        filename = source_path.name
        temp_path = os.path.join(temp_dir, filename)

        shutil.copy2(source_path, temp_path)
        logger.debug(f"Downloaded {virtual_path} to temp: {temp_path}")

        return temp_path
