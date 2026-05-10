# workers/shared/utils/file_upload_client.py

"""HTTP client for uploading and downloading worker output files via the API."""

import logging
import mimetypes
import os
import time
from typing import Callable, Optional

import httpx

from shared.settings import settings

logger = logging.getLogger(__name__)

_BASE_DELAY = settings.TRANSFER_RETRY_BASE_DELAY
_MAX_DELAY = settings.TRANSFER_RETRY_MAX_DELAY
_MAX_RETRIES = settings.HTTP_MAX_RETRIES


class FileUploadClient:
    """Upload files to the API and download them back via the internal endpoints."""

    def __init__(self, token_getter: Callable[[], Optional[str]]) -> None:
        self._base_url = settings.API_BASE_URL.rstrip("/")
        self._token_getter = token_getter

    def _auth_headers(self) -> dict:
        token = self._token_getter()
        if not token:
            raise RuntimeError("Worker JWT not available - not yet registered")
        return {"Authorization": f"Bearer {token}"}

    def upload(
        self,
        local_path: str,
        filename: Optional[str] = None,
        job_id: Optional[str] = None,
    ) -> str:
        """Upload a local file to the API; returns the virtual_path."""
        if filename is None:
            filename = os.path.basename(local_path)

        mime_type, _ = mimetypes.guess_type(filename)
        mime_type = mime_type or "application/octet-stream"

        delay = _BASE_DELAY
        last_exc: Exception = RuntimeError("upload never attempted")

        form_data: dict = {"filename": filename}
        if job_id:
            form_data["job_id"] = job_id

        for attempt in range(_MAX_RETRIES + 1):
            try:
                with open(local_path, "rb") as fh:
                    response = httpx.post(
                        f"{self._base_url}/api/v1/internal/files/upload",
                        headers=self._auth_headers(),
                        data=form_data,
                        files={"file": (filename, fh, mime_type)},
                        timeout=settings.TRANSFER_TIMEOUT_S,
                    )
                response.raise_for_status()
                virtual_path = response.json()["virtual_path"]
                logger.debug(f"Uploaded {filename} → {virtual_path}")
                return virtual_path
            except Exception as exc:
                last_exc = exc
                if attempt < _MAX_RETRIES:
                    logger.warning(
                        f"File upload attempt {attempt + 1}/{_MAX_RETRIES + 1} failed: {exc}. "
                        f"Retrying in {delay:.0f}s"
                    )
                    time.sleep(delay)
                    delay = min(delay * 2, _MAX_DELAY)

        raise RuntimeError(
            f"File upload failed after {_MAX_RETRIES + 1} attempts: {last_exc}"
        ) from last_exc

    def download(self, resource_id: str) -> str:
        """Download a file by resource_id from the API to a temp file; returns local path."""
        import tempfile

        temp_dir = tempfile.mkdtemp(prefix="studio_worker_dl_")
        temp_path = os.path.join(temp_dir, resource_id)

        delay = _BASE_DELAY
        last_exc: Exception = RuntimeError("download never attempted")

        for attempt in range(_MAX_RETRIES + 1):
            try:
                with httpx.stream(
                    "GET",
                    f"{self._base_url}/api/v1/internal/files/{resource_id}/download",
                    headers=self._auth_headers(),
                    timeout=settings.TRANSFER_TIMEOUT_S,
                ) as response:
                    response.raise_for_status()
                    with open(temp_path, "wb") as fh:
                        for chunk in response.iter_bytes(
                            chunk_size=settings.HTTP_CHUNK_SIZE
                        ):
                            fh.write(chunk)
                logger.debug(f"Downloaded {resource_id} → {temp_path}")
                return temp_path
            except Exception as exc:
                last_exc = exc
                if attempt < _MAX_RETRIES:
                    logger.warning(
                        f"File download attempt {attempt + 1}/{_MAX_RETRIES + 1} failed: {exc}. "
                        f"Retrying in {delay:.0f}s"
                    )
                    time.sleep(delay)
                    delay = min(delay * 2, _MAX_DELAY)

        raise RuntimeError(
            f"File download failed after {_MAX_RETRIES + 1} attempts: {last_exc}"
        ) from last_exc
