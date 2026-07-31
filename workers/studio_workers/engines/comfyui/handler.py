# workers/studio_workers/engines/comfyui/handler.py

"""GPU worker for AI image generation via ComfyUI. Database-free; jobs come from queue payload.

Workflow source priority: parameters.workflow (operator override) > synced catalog packages.
"""

import os
import shutil
import logging
import time
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

try:
    from PIL import Image

    PIL_AVAILABLE = True
except ImportError:  # pragma: no cover
    PIL_AVAILABLE = False

from studio_workers.utils import ResultPublisher, WorkerBase, create_job_client
from studio_workers.utils.error_codes import classify_error_code
from studio_workers.utils.file_upload_client import FileUploadClient
from studio_workers.worker_types import get_worker_config
from studio_workers.settings import settings
from studio_workers.engines.comfyui.settings import settings as comfyui_settings

from studio_workers.engines.comfyui import ComfyUIClient
from studio_workers.engines.comfyui.manifest import (
    inject_from_manifest,
    validate_manifest_parameters,
)
from studio_workers.engines.comfyui.package_store import ComfyUIPackageStore

logger = logging.getLogger(__name__)

# Parameters that reference input images (need download + upload to ComfyUI).
IMAGE_INPUT_PARAMS = ["image"]


class ComfyUIWorker(WorkerBase):
    """GPU worker for ComfyUI-based image/video generation."""

    def __init__(self, worker_type: str = "comfyui-image"):
        config = get_worker_config(worker_type)

        super().__init__(
            worker_type=config.type_id,
            queue_labels=config.queue_labels,
            capabilities=config.capabilities,
        )

        self.queue_name = config.queue_name

        # Job client initialized after registration so we have real worker_id from the API.
        self.job_client = None
        self.result_publisher = ResultPublisher(token_getter=self.get_token)
        self._file_upload_client = FileUploadClient(
            token_getter=self.get_token,
            storage_mode_getter=self._detect_storage_mode,
        )

        # Operator runs ComfyUI; worker connects and waits if unavailable.
        self.comfyui_url = comfyui_settings.COMFYUI_URL

        # Default keeps docker (WORKSPACE_ROOT=/workspace) and native paths working
        # without hardcoding a docker-only absolute path.
        self.output_dir = comfyui_settings.COMFYUI_OUTPUT_DIR or os.path.join(
            settings.WORKSPACE_ROOT, "data", "comfyui_output"
        )
        os.makedirs(self.output_dir, exist_ok=True)

        self.poll_interval = comfyui_settings.COMFYUI_POLL_INTERVAL_S
        self.comfyui_retry_interval = comfyui_settings.COMFYUI_RETRY_INTERVAL_S

        self.client: Optional[ComfyUIClient] = None
        self._comfyui_available = False
        self._last_availability_log = 0

        # Catalog packages synced from the API; disk cache covers API outages.
        self.package_store = ComfyUIPackageStore()
        self._resync_needed = False

    def on_heartbeat_response(self, data: Dict[str, Any]) -> None:
        """Flag a resync when the API's catalog hash moves; the claim loop syncs."""
        remote_hash = data.get("comfyui_catalog_hash")
        if remote_hash and remote_hash != self.package_store.catalog_hash:
            self._resync_needed = True

    def _check_comfyui_available(self) -> bool:
        """Non-blocking health check; logs only on status change or every 60s while waiting."""
        if self.client is None:
            self.client = ComfyUIClient(self.comfyui_url)

        is_available = self.client.health_check()

        if is_available and not self._comfyui_available:
            logger.info(f"ComfyUI is now available at {self.comfyui_url}")
            self._comfyui_available = True
        elif not is_available and self._comfyui_available:
            logger.warning(f"ComfyUI became unavailable at {self.comfyui_url}")
            self._comfyui_available = False
        elif not is_available:
            now = time.time()
            if now - self._last_availability_log > 60:
                logger.debug(f"Waiting for ComfyUI at {self.comfyui_url}...")
                self._last_availability_log = now

        return is_available

    def _prepare_input_images(
        self,
        parameters: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Download virtual_path images from storage and upload them to ComfyUI's input folder."""
        assert self.client is not None, "ComfyUI client not initialized"

        updated_params = parameters.copy()

        for param_name in IMAGE_INPUT_PARAMS:
            if param_name not in parameters:
                continue

            image_ref = parameters[param_name]

            # Enqueue-side ships file refs as dual-view {virtual_path, url,
            # filename} dicts; this engine downloads via the /orgs/ form,
            # so collapse the record to virtual_path here. URL-string and
            # legacy /orgs/ string inputs pass through unchanged.
            if isinstance(image_ref, dict):
                image_ref = image_ref.get("virtual_path")

            if not isinstance(image_ref, str):
                continue

            if not image_ref.startswith("/orgs/"):
                logger.debug(
                    f"Image param '{param_name}' is not a virtual_path: {image_ref[:50]}"
                )
                continue

            logger.debug(f"Downloading input image from storage: {image_ref}")

            try:
                local_path = self._file_upload_client.download(image_ref)
                logger.debug(f"Downloaded to temp: {local_path}")

                comfyui_filename = self.client.upload_image(local_path)
                logger.debug(f"Uploaded to ComfyUI as: {comfyui_filename}")

                updated_params[param_name] = comfyui_filename

                if os.path.exists(local_path):
                    os.remove(local_path)

            except Exception as e:
                logger.error(f"Failed to prepare input image '{param_name}': {e}")
                raise RuntimeError(f"Failed to load input image: {e}")

        return updated_params

    def process_jobs(self):
        """Main worker loop - wait for ComfyUI and process jobs."""
        logger.info(f"{self.worker_type.upper()} Worker Started")
        logger.info(f"Monitoring queue: {self.queue_name}")
        logger.debug(f"ComfyUI URL: {self.comfyui_url}")
        logger.debug(f"Output directory: {self.output_dir}")

        self.job_client = create_job_client(
            worker_id=self.worker_id or self.worker_name,
            token_getter=self.get_token,
        )

        if self.worker_token:
            logger.debug(f"Using JWT auth (worker_id: {self.worker_id})")
        elif self.worker_id:
            logger.debug(f"Using registered worker_id: {self.worker_id} (legacy mode)")
        else:
            logger.warning(
                "Not registered - job claims may fail. Waiting for registration..."
            )

        if self._check_comfyui_available():
            logger.debug(f"ComfyUI available at {self.comfyui_url}")
        else:
            logger.info(f"ComfyUI not available at {self.comfyui_url}, will retry...")

        cached = self.package_store.load_cached()
        if cached:
            logger.info(f"Loaded {cached} cached comfyui packages")
        if not self.package_store.sync(token_getter=self.get_token):
            logger.warning("Package sync unavailable - using cached packages")

        logger.info("Listening for jobs...")

        # Desync simultaneous container boots before the first claim.
        self.job_client.startup_jitter()

        try:
            while self.running:
                if self._resync_needed:
                    self._resync_needed = False
                    self.package_store.sync(token_getter=self.get_token)

                if not self._check_comfyui_available():
                    time.sleep(self.comfyui_retry_interval)
                    continue

                job = self.job_client.claim_job(
                    self.queue_name, timeout=settings.JOB_CLAIM_TIMEOUT_S
                )

                if job is None:
                    sleep_duration = self.job_client.get_sleep_duration()
                    if sleep_duration > 0:
                        time.sleep(sleep_duration)
                    continue

                self._process_job(job)

        finally:
            if self.client:
                self.client.close()
            self.job_client.close()
            self.result_publisher.close()

    def _process_job(self, job: Dict[str, Any]):
        """Process a single ComfyUI image generation job."""
        job_id = job.get("job_id", "unknown")
        step_id = job.get("step_id", job_id)

        service_id = job.get("service_id", "")
        if "." in service_id:
            operation = service_id.split(".")[-1]
        else:
            operation = job.get("operation", "comfyui_txt2img")

        step_config = job.get("step_config") or {}
        job_config = step_config.get("job") or {}
        parameters = job_config.get("parameters") or step_config.get("parameters") or {}

        # Worker receives already-styled prompts with positive/negative merged.

        if any(param in parameters for param in IMAGE_INPUT_PARAMS):
            parameters = self._prepare_input_images(parameters)

        prompt_preview = parameters.get("prompt", "")[:60]
        if len(parameters.get("prompt", "")) > 60:
            prompt_preview += "..."

        logger.info(
            f"Processing job: job_id={job_id}, operation={operation}, prompt={prompt_preview}"
        )

        self.set_busy(job_id)

        if job.get("notify_api", True):
            self.result_publisher.publish_step_result(status="PROCESSING")
            logger.debug("Published PROCESSING status")

        job_start_time = time.time()
        try:
            custom_workflow = parameters.get("workflow")

            manifest = self.package_store.resolve(
                operation, parameters.get("model")
            )

            if custom_workflow:
                logger.debug("Using custom workflow from job payload")
                workflow = custom_workflow
            elif manifest:
                is_valid, error_msg = validate_manifest_parameters(
                    manifest, parameters
                )
                if not is_valid:
                    raise ValueError(f"Invalid parameters: {error_msg}")
                model = parameters.get("model") or manifest.default_model
                logger.info(
                    f"Using catalog package {manifest.slug}@{manifest.version}"
                    + (f" model={model}" if model else "")
                )
                workflow = inject_from_manifest(manifest, parameters, model=model)
            else:
                raise ValueError(
                    f"No catalog package for operation '{operation}'"
                    + (
                        f" model '{parameters.get('model')}'"
                        if parameters.get("model")
                        else ""
                    )
                )

            assert self.client is not None, "ComfyUI client not initialized"
            logger.info("Submitting workflow to ComfyUI")
            comfyui_start = time.time()
            prompt_id = self.client.queue_prompt(workflow)
            logger.debug(
                f"Queued as prompt_id={prompt_id}",
                extra={"job_id": job_id, "prompt_id": prompt_id},
            )

            self.client.wait_for_completion(
                prompt_id,
                timeout=comfyui_settings.COMFYUI_JOB_TIMEOUT_S,
                poll_interval=self.poll_interval,
            )
            comfyui_ms = int((time.time() - comfyui_start) * 1000)
            logger.debug(
                f"ComfyUI operation completed ({comfyui_ms}ms)",
                extra={"prompt_id": prompt_id, "duration_ms": comfyui_ms},
            )

            output_images = self.client.get_output_images(prompt_id)
            logger.debug(f"Downloading {len(output_images)} image(s)")

            downloaded_files = []
            job_output_dir = os.path.join(self.output_dir, job_id)

            base_seed = parameters.get("seed", -1)
            if base_seed == -1:
                # Randomized - recover seed from RandomNoise node.
                base_seed = self._get_workflow_seed(workflow)

            for i, image_info in enumerate(output_images):
                local_path = self.client.download_image(
                    filename=image_info["filename"],
                    output_dir=job_output_dir,
                    subfolder=image_info.get("subfolder", ""),
                    image_type=image_info.get("type", "output"),
                )

                if os.path.exists(local_path):
                    # Capture size + name before upload (local-write path
                    # consumes local_path via atomic rename).
                    file_size = os.path.getsize(local_path)
                    original_filename = os.path.basename(local_path)

                    storage_url, thumbnail_url = self._upload_to_storage(
                        local_path=local_path,
                        step_id=step_id,
                        index=i,
                        job_id=job_id,
                        organization_id=job.get("organization_id"),
                        instance_id=job.get("instance_id"),
                    )
                    # ComfyUI/Flux produce batch image i from base_seed + i.
                    image_seed = base_seed + i
                    file_info = {
                        "filename": original_filename,
                        "original_filename": original_filename,
                        "virtual_path": storage_url,
                        "file_size": file_size,
                        "display_name": "Generated Image",
                        "index": i,
                        "seed": image_seed,
                    }
                    if thumbnail_url:
                        file_info["thumbnail_path"] = thumbnail_url
                        file_info["has_thumbnail"] = True
                    downloaded_files.append(file_info)

            seed_used = parameters.get("seed", -1)
            if seed_used == -1:
                seed_used = self._get_workflow_seed(workflow)

            request_data = {
                "prompt": parameters.get("prompt", ""),
                "seed": seed_used,
                "width": parameters.get("width"),
                "height": parameters.get("height"),
                "steps": parameters.get("steps"),
                "guidance": parameters.get("guidance"),
            }
            request_data = {k: v for k, v in request_data.items() if v is not None}

            result = {
                "success": True,
                "downloaded_files": downloaded_files,
                "image_count": len(downloaded_files),
                "seed_used": seed_used,
                "prompt_id": prompt_id,
                "request_data": request_data,
            }

            if job.get("notify_api", True):
                if not self.result_publisher.publish_step_result(status="COMPLETED", result=result):
                    logger.critical(
                        "Failed to publish step result after retries - job will be orphaned",
                        extra={"job_id": job_id, "status": "COMPLETED"},
                    )

            job_duration_ms = int((time.time() - job_start_time) * 1000)
            logger.info(
                f"ComfyUI job {job_id} completed: images={len(downloaded_files)}, "
                f"duration={job_duration_ms}ms",
                extra={
                    "job_id": job_id,
                    "step_id": step_id,
                    "duration_ms": job_duration_ms,
                    "image_count": len(downloaded_files),
                },
            )

            self._cleanup_output(job_output_dir)

        except Exception as e:
            # Classified sentence to the published result; full exception to worker
            # logs. Raw str(e) leaks infra detail (paths, ComfyUI/node error bodies)
            # to UI clients. safe_error_message lives in api/, not importable here, so
            # workers inline the classifier (transfer-worker idiom).
            duration_ms = int((time.time() - job_start_time) * 1000)
            logger.exception(
                f"Job failed ({duration_ms}ms): job_id={job_id}, error={e}",
                extra={"job_id": job_id, "duration_ms": duration_ms},
            )
            error_msg = f"ComfyUI job failed ({type(e).__name__}). See worker logs."
            self._handle_failure(job, error_msg, error_code=classify_error_code(e))

        finally:
            self.set_idle()

    @staticmethod
    def _get_workflow_seed(workflow: Dict[str, Any]) -> int:
        """Find the noise seed from the RandomNoise node in a workflow."""
        for node in workflow.values():
            if isinstance(node, dict) and node.get("class_type") == "RandomNoise":
                return node.get("inputs", {}).get("noise_seed", 0)
        return 0

    def _generate_thumbnail(
        self,
        image_path: Path,
        output_dir: Path,
        size: Optional[Tuple[int, int]] = None,
    ) -> Optional[Path]:
        """Generate a JPEG thumbnail; returns path or None on failure."""
        if not PIL_AVAILABLE:
            logger.warning("Skipping thumbnail - PIL not available")
            return None

        if size is None:
            size = (settings.THUMBNAIL_WIDTH, settings.THUMBNAIL_HEIGHT)

        try:
            thumbnail_filename = image_path.stem + "-thumbnail.jpg"
            thumbnail_path = output_dir / thumbnail_filename

            with Image.open(image_path) as img:
                if img.mode in ("RGBA", "LA", "P"):
                    background = Image.new("RGB", img.size, (255, 255, 255))
                    if img.mode == "P":
                        img = img.convert("RGBA")
                    background.paste(img, mask=img.split()[-1])
                    img = background
                elif img.mode != "RGB":
                    img = img.convert("RGB")

                img.thumbnail(size, Image.Resampling.LANCZOS)
                img.save(
                    thumbnail_path, "JPEG", quality=settings.THUMBNAIL_JPEG_QUALITY
                )

            logger.debug(f"Generated thumbnail: {thumbnail_filename}")
            return thumbnail_path

        except Exception as e:
            logger.warning(f"Thumbnail generation failed for {image_path.name}: {e}")
            return None

    def _upload_to_storage(
        self,
        local_path: str,
        step_id: str,
        index: int = 0,
        job_id: str = "unknown",
        organization_id: Optional[str] = None,
        instance_id: Optional[str] = None,
    ) -> Tuple[str, Optional[str]]:
        """Upload output image via the API upload endpoint; returns (image_url, thumbnail_url|None)."""
        import uuid as uuid_module

        ext = os.path.splitext(local_path)[1].lower()
        file_uuid = uuid_module.uuid4().hex[:8]
        filename = f"{step_id}_{file_uuid}{ext}"

        url_path = self._file_upload_client.upload(
            local_path,
            filename=filename,
            job_id=job_id if job_id != "unknown" else None,
            organization_id=organization_id,
            instance_id=instance_id,
        )
        logger.debug(f"Uploaded: {url_path}")
        return url_path, None

    def _handle_failure(
        self, job: Dict[str, Any], error_msg: str, error_code: str = "INTERNAL"
    ):
        """Handle job failure - write error and notify."""
        job_id = job.get("job_id", "unknown")

        if job.get("notify_api", True):
            if not self.result_publisher.publish_step_result(
                status="FAILED", error=error_msg, error_code=error_code
            ):
                logger.critical(
                    "Failed to publish step result after retries - job will be orphaned",
                    extra={"job_id": job_id, "status": "FAILED"},
                )

    def _cleanup_output(self, output_dir: str):
        """Clean up temporary output directory after job completion."""
        if output_dir and os.path.exists(output_dir):
            try:
                shutil.rmtree(output_dir)
                logger.debug(f"Cleaned up output: {output_dir}")
            except Exception as e:
                logger.warning(f"Failed to cleanup output {output_dir}: {e}")


def main():
    worker = ComfyUIWorker()
    worker.run()


if __name__ == "__main__":
    main()
