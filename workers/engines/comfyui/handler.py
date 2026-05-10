# workers/engines/comfyui/handler.py

"""GPU worker for AI image generation via ComfyUI. Database-free; jobs come from queue payload.

Workflow source priority: parameters.workflow (operator override) > built-in templates.
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

from shared.utils import ResultPublisher, WorkerBase, create_job_client
from shared.utils.file_upload_client import FileUploadClient
from shared.worker_types import get_worker_config
from shared.settings import settings
from engines.comfyui.settings import settings as comfyui_settings

from engines.comfyui import (
    ComfyUIClient,
    load_workflow_template,
    inject_parameters,
)
from engines.comfyui.templates import validate_parameters

logger = logging.getLogger(__name__)

# Parameters that reference input images (need download + upload to ComfyUI).
IMAGE_INPUT_PARAMS = ["image"]


class ComfyUIWorker(WorkerBase):
    """GPU worker for ComfyUI-based image/video generation."""

    ALL_OPERATIONS = {
        "comfyui_txt2img": "comfyui_txt2img",
        "comfyui_txt2img_flux2": "comfyui_txt2img_flux2",
        "comfyui_txt2img_flux2_9b": "comfyui_txt2img_flux2_9b",
        "comfyui_imgedit": "comfyui_imgedit",
    }

    TXT2IMG_MODEL_TEMPLATES = {
        "flux1-schnell": "comfyui_txt2img",
        "flux1-schnell-fp8": "comfyui_txt2img_fp8",
        "flux1-schnell-q4": "comfyui_txt2img_gguf",
        "flux-2-klein-4b": "comfyui_txt2img_flux2",
        "flux-2-klein-9b": "comfyui_txt2img_flux2_9b",
    }

    def __init__(self, worker_type: str = "comfyui-image"):
        config = get_worker_config(worker_type)

        super().__init__(
            worker_type=config.type_id,
            queue_labels=config.queue_labels,
            capabilities=config.capabilities,
        )

        self.queue_name = config.queue_name

        # Worker types may handle a subset of operations - filter from capabilities.
        allowed_ops = config.capabilities.get("operations", [])
        if allowed_ops:
            self.OPERATIONS = {
                op: template
                for op, template in self.ALL_OPERATIONS.items()
                if op in allowed_ops
            }
        else:
            self.OPERATIONS = self.ALL_OPERATIONS.copy()

        # Job client initialized after registration so we have real worker_id from the API.
        self.job_client = None
        self.result_publisher = ResultPublisher(token_getter=self.get_token)
        self._file_upload_client = FileUploadClient(token_getter=self.get_token)

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
        logger.debug(f"Operations: {', '.join(self.OPERATIONS.keys())}")

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

        logger.info("Listening for jobs...")

        try:
            while self.running:
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

            if custom_workflow:
                logger.debug("Using custom workflow from job payload")
                workflow = custom_workflow
                workflow = inject_parameters(workflow, parameters, "custom")
            else:
                if operation not in self.OPERATIONS:
                    raise ValueError(
                        f"Unknown operation: {operation}. "
                        f"Valid operations: {', '.join(self.OPERATIONS.keys())}"
                    )

                is_valid, error_msg = validate_parameters(operation, parameters)
                if not is_valid:
                    raise ValueError(f"Invalid parameters: {error_msg}")

                workflow_name = self.OPERATIONS[operation]

                if operation == "comfyui_txt2img":
                    model = parameters.get("model")
                    if model:
                        if model not in self.TXT2IMG_MODEL_TEMPLATES:
                            raise ValueError(
                                f"Unknown model: '{model}'. "
                                f"Available models: {', '.join(sorted(self.TXT2IMG_MODEL_TEMPLATES.keys()))}"
                            )
                        workflow_name = self.TXT2IMG_MODEL_TEMPLATES[model]
                        logger.info(f"Model override: {model} → {workflow_name}")

                workflow = load_workflow_template(workflow_name)

                # Surface model file in logs to diagnose workflow selection issues.
                model_name = "unknown"
                for node in workflow.values():
                    if isinstance(node, dict) and node.get("class_type") in (
                        "UNETLoader",
                        "UnetLoaderGGUF",
                    ):
                        model_name = node.get("inputs", {}).get("unet_name", "unknown")
                        break

                workflow = inject_parameters(workflow, parameters, workflow_name)

                # Read actual values from workflow nodes (post-injection).
                node50 = workflow.get("50", {}).get("inputs", {})
                gen_w, gen_h = "?", "?"
                for node in workflow.values():
                    if isinstance(node, dict) and "LatentImage" in node.get(
                        "class_type", ""
                    ):
                        gen_w = node.get("inputs", {}).get("width", "?")
                        gen_h = node.get("inputs", {}).get("height", "?")
                        break
                upscale = parameters.get("upscale", True)
                logger.debug("=== WORKFLOW DEBUG ===")
                logger.debug(f"  operation: {operation}")
                logger.debug(f"  workflow_name: {workflow_name}")
                logger.debug(f"  model file: {model_name}")
                logger.debug(f"  steps: {parameters.get('steps', 'default')}")
                logger.debug(f"  seed: {parameters.get('seed', 'default')}")
                if upscale:
                    logger.debug("  fast mode: on")
                    logger.debug(f"  gen: {gen_w}x{gen_h}")
                    logger.debug(
                        f"  output: {node50.get('width')}x{node50.get('height')} ({node50.get('upscale_method', 'lanczos')})"
                    )
                else:
                    logger.debug("  fast mode: off")
                    logger.debug(
                        f"  output: {node50.get('width')}x{node50.get('height')}"
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
                    storage_url, thumbnail_url = self._upload_to_storage(
                        local_path=local_path,
                        step_id=step_id,
                        index=i,
                        job_id=job_id,
                    )

                    file_size = os.path.getsize(local_path)
                    original_filename = os.path.basename(local_path)
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

        except ValueError as e:
            error_msg = str(e)
            duration_ms = int((time.time() - job_start_time) * 1000)
            logger.error(
                f"Job failed (validation, {duration_ms}ms): job_id={job_id}, error={error_msg}",
                extra={"job_id": job_id, "duration_ms": duration_ms},
            )
            self._handle_failure(job, error_msg)

        except TimeoutError as e:
            error_msg = str(e)
            duration_ms = int((time.time() - job_start_time) * 1000)
            logger.error(
                f"Job failed (timeout, {duration_ms}ms): job_id={job_id}, error={error_msg}",
                extra={"job_id": job_id, "duration_ms": duration_ms},
            )
            self._handle_failure(job, error_msg)

        except RuntimeError as e:
            error_msg = str(e)
            duration_ms = int((time.time() - job_start_time) * 1000)
            logger.error(
                f"Job failed (execution, {duration_ms}ms): job_id={job_id}, error={error_msg}",
                extra={"job_id": job_id, "duration_ms": duration_ms},
            )
            self._handle_failure(job, error_msg)

        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            logger.exception(f"Job failed: job_id={job_id}, error={error_msg}")
            self._handle_failure(job, error_msg)

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
        size: Tuple[int, int] = (300, 300),
    ) -> Optional[Path]:
        """Generate a JPEG thumbnail; returns path or None on failure."""
        if not PIL_AVAILABLE:
            logger.warning("Skipping thumbnail - PIL not available")
            return None

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
                img.save(thumbnail_path, "JPEG", quality=85)

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
    ) -> Tuple[str, Optional[str]]:
        """Upload output image via the API upload endpoint; returns (image_url, thumbnail_url|None)."""
        import uuid as uuid_module

        ext = os.path.splitext(local_path)[1].lower()
        file_uuid = uuid_module.uuid4().hex[:8]
        filename = f"{step_id}_{file_uuid}{ext}"

        url_path = self._file_upload_client.upload(local_path, filename=filename)
        logger.debug(f"Uploaded: {url_path}")
        return url_path, None

    def _handle_failure(self, job: Dict[str, Any], error_msg: str):
        """Handle job failure - write error and notify."""
        job_id = job.get("job_id", "unknown")

        if job.get("notify_api", True):
            if not self.result_publisher.publish_step_result(status="FAILED", error=error_msg):
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
