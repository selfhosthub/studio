# workers/studio_workers/utils/file_upload_client.py

"""HTTP client for uploading and downloading worker output files via the API."""

import hashlib
import logging
import mimetypes
import os
import shutil
import time
from pathlib import Path
from typing import Callable, Optional

import httpx

from studio_workers.settings import settings
from studio_workers.utils.cf_access import cf_access_headers

logger = logging.getLogger(__name__)

_BASE_DELAY = settings.TRANSFER_RETRY_BASE_DELAY
_MAX_DELAY = settings.TRANSFER_RETRY_MAX_DELAY
_MAX_RETRIES = settings.HTTP_MAX_RETRIES


def _sanitize_step_filename(display_name: str, file_extension: str) -> str:
    """Mirror of `contracts.workspace_paths.sanitize_step_filename`.

    Inlined to keep workers/ from depending on contracts/ at import time
    (worker pyrightconfig scopes only `studio_workers/`). Must
    stay byte-for-byte identical with the API-side helper or the worker
    writes one path and the API stats another, defeating the local
    optimization and silently falling back to multipart.
    """
    base_name = display_name
    if "." in base_name:
        base_name = base_name.rsplit(".", 1)[0]
    safe_name = "".join(
        c if c.isalnum() or c in "-_." else "_" for c in base_name
    )
    safe_name = safe_name[:100]
    return f"{safe_name}{file_extension}"


class FileUploadClient:
    """Upload files to the API and download them back via the internal endpoints.

    Two upload paths:

    1. **Remote** (`storage_mode != "local"`, or `organization_id` /
       `instance_id` not supplied): multipart `POST /files/upload` -
       bytes travel over HTTP. Always the safe fallback.
    2. **Local** (worker shares the API's `/workspace` mount AND the
       caller supplied org_id + instance_id): atomic-rename into the
       canonical `/workspace/orgs/{org}/instances/{inst}/{sanitized}`
       path, then `POST /files/register` with metadata only - no bytes
       on the wire. Any failure transparently falls back to multipart.
    """

    def __init__(
        self,
        token_getter: Callable[[], Optional[str]],
        storage_mode_getter: Optional[Callable[[], str]] = None,
    ) -> None:
        self._base_url = settings.API_BASE_URL.rstrip("/")
        self._token_getter = token_getter
        # Default getter: "remote". Old engines that don't pass a getter
        # keep doing multipart, no behavior change.
        self._storage_mode_getter = storage_mode_getter or (lambda: "remote")

    def _auth_headers(self) -> dict:
        token = self._token_getter()
        if not token:
            raise RuntimeError("Worker JWT not available - not yet registered")
        return {"Authorization": f"Bearer {token}", **cf_access_headers()}

    def upload(
        self,
        local_path: str,
        filename: Optional[str] = None,
        job_id: Optional[str] = None,
        thumbnail_path: Optional[str] = None,
        organization_id: Optional[str] = None,
        instance_id: Optional[str] = None,
    ) -> str:
        """Upload a local file to the API; returns the virtual_path.

        thumbnail_path: optional sibling thumbnail (e.g. video poster frame)
        sent in the same multipart request. The API cannot extract a video
        thumbnail itself (no ffmpeg), so the producing worker supplies one.

        organization_id + instance_id: when both supplied and the worker
        is in storage_mode=local, take the direct-write path. Either
        argument missing → multipart upload (the safe default).
        """
        if filename is None:
            filename = os.path.basename(local_path)

        if (
            organization_id
            and instance_id
            and self._storage_mode_getter() == "local"
        ):
            try:
                return self._upload_local(
                    local_path=local_path,
                    filename=filename,
                    organization_id=organization_id,
                    instance_id=instance_id,
                    job_id=job_id,
                    thumbnail_path=thumbnail_path,
                )
            except Exception as exc:
                # Any failure on the local path - write error, register
                # 404/422, network blip - falls back to multipart. The
                # optimization is opportunistic; correctness comes from
                # the existing endpoint.
                logger.warning(
                    f"Local upload failed for {filename}; falling back to "
                    f"multipart: {exc}"
                )

        return self._upload_multipart(
            local_path=local_path,
            filename=filename,
            job_id=job_id,
            thumbnail_path=thumbnail_path,
        )

    def _upload_local(
        self,
        local_path: str,
        filename: str,
        organization_id: str,
        instance_id: str,
        job_id: Optional[str],
        thumbnail_path: Optional[str],
    ) -> str:
        """Atomic-rename into canonical path, POST metadata, return virtual_path."""
        workspace_root = settings.WORKSPACE_ROOT
        if not workspace_root:
            raise RuntimeError("WORKSPACE_ROOT not set; cannot use local write path")

        file_extension = ""
        ext_index = filename.rfind(".")
        if ext_index != -1:
            file_extension = filename[ext_index:]

        sanitized = _sanitize_step_filename(filename, file_extension)
        target_dir = (
            Path(workspace_root)
            / "orgs"
            / organization_id
            / "instances"
            / instance_id
        )
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / sanitized

        # Atomic-rename on same filesystem; falls back to shutil.move
        # (copy + remove) across filesystems. We compute checksum from
        # the *source* before moving so a mid-rename interruption can't
        # leave us with checksum from a half-written destination.
        hasher = hashlib.sha256()
        size = 0
        with open(local_path, "rb") as f:
            while chunk := f.read(8192):
                hasher.update(chunk)
                size += len(chunk)
        checksum = hasher.hexdigest()

        tmp_path = target_dir / f".{sanitized}.{os.getpid()}.tmp"
        shutil.move(local_path, tmp_path)
        os.replace(tmp_path, target_path)

        has_thumbnail = False
        thumb_target: Optional[Path] = None
        if thumbnail_path:
            name_part = sanitized.rsplit(".", 1)[0]
            thumb_target = target_dir / f"{name_part}-thumbnail.jpg"
            try:
                shutil.move(thumbnail_path, thumb_target)
                has_thumbnail = True
            except OSError as exc:
                logger.warning(
                    f"Failed to place thumbnail at {thumb_target}: {exc}"
                )
                thumb_target = None

        mime_type, _ = mimetypes.guess_type(filename)
        mime_type = mime_type or "application/octet-stream"

        body: dict = {
            "filename": filename,
            "file_extension": file_extension,
            "mime_type": mime_type,
            "size": size,
            "checksum": checksum,
            "has_thumbnail": has_thumbnail,
        }
        if job_id:
            body["job_id"] = job_id

        try:
            response = httpx.post(
                f"{self._base_url}/api/v1/internal/files/register",
                headers=self._auth_headers(),
                json=body,
                timeout=settings.TRANSFER_TIMEOUT_S,
            )
            response.raise_for_status()
        except Exception:
            # Register failed - restore the source so the multipart
            # fallback in upload() finds bytes where it expects them.
            # If the restore itself fails, log loudly and let the
            # original register error propagate; the job will be a
            # known failure rather than a silent corruption.
            try:
                shutil.move(str(target_path), local_path)
                if thumb_target is not None and thumbnail_path is not None:
                    shutil.move(str(thumb_target), thumbnail_path)
            except OSError as restore_exc:
                logger.error(
                    f"Local-upload register failed AND restore failed; "
                    f"source {local_path} is gone, canonical write at "
                    f"{target_path} survives: {restore_exc}"
                )
                raise
            raise

        virtual_path = response.json()["virtual_path"]
        logger.debug(f"Registered {filename} → {virtual_path} (local write)")
        return virtual_path

    def _upload_multipart(
        self,
        local_path: str,
        filename: str,
        job_id: Optional[str],
        thumbnail_path: Optional[str],
    ) -> str:
        """Existing multipart path; unchanged from pre-storage_mode behavior."""
        mime_type, _ = mimetypes.guess_type(filename)
        mime_type = mime_type or "application/octet-stream"

        delay = _BASE_DELAY
        last_exc: Exception = RuntimeError("upload never attempted")

        form_data: dict = {"filename": filename}
        if job_id:
            form_data["job_id"] = job_id

        for attempt in range(_MAX_RETRIES + 1):
            thumb_fh = None
            try:
                with open(local_path, "rb") as fh:
                    files_payload = {"file": (filename, fh, mime_type)}
                    if thumbnail_path:
                        thumb_fh = open(thumbnail_path, "rb")
                        files_payload["thumbnail"] = (
                            os.path.basename(thumbnail_path),
                            thumb_fh,
                            "image/jpeg",
                        )
                    response = httpx.post(
                        f"{self._base_url}/api/v1/internal/files/upload",
                        headers=self._auth_headers(),
                        data=form_data,
                        files=files_payload,
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
            finally:
                if thumb_fh is not None:
                    thumb_fh.close()

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
