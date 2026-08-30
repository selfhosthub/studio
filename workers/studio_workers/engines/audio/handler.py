# workers/studio_workers/engines/audio/handler.py

"""GPU worker for text-to-speech with Chatterbox TTS."""

import gc
import os
import tempfile
import time
import uuid
import logging
from typing import Dict, Any, Optional

import httpx

from studio_workers.utils import WorkerBase, create_job_client
from studio_workers.utils.file_upload_client import FileUploadClient
from studio_workers.utils.result_publisher import ResultPublisher
from studio_workers.utils.error_codes import classify_error_code
from studio_workers.worker_types import get_worker_config, resolve_queues
from studio_workers.settings import settings
from studio_workers.engines.audio.settings import settings as audio_settings

logger = logging.getLogger(__name__)

_models: Dict[str, Any] = {}
_device: Optional[str] = None
_last_used: float = 0.0


def _detect_device() -> str:
    """Auto-detect best available device: cuda > mps > cpu."""
    global _device
    if _device is not None:
        return _device

    import torch

    if torch.cuda.is_available():
        _device = "cuda"
    elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        _device = "mps"
    else:
        _device = "cpu"

    logger.debug(f"Device selected: {_device}")
    return _device


def _unload_models() -> None:
    """Drop every loaded model and hand the VRAM back to the driver.

    empty_cache() is the part that actually matters. Deleting the model object is not
    enough: PyTorch's caching allocator keeps the freed blocks RESERVED, so nvidia-smi
    still reports the memory as held and another process on the same GPU still cannot
    have it. Without this call the eviction looks like it worked and frees nothing.
    """
    if not _models:
        return

    freed = list(_models)
    _models.clear()
    gc.collect()

    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception as exc:  # never let a cleanup failure kill the worker loop
        logger.warning(f"empty_cache failed: {exc}")

    logger.info(f"Unloaded idle model(s): {', '.join(freed)}")


def _maybe_unload_idle() -> None:
    """Called from the poll loop while the queue is empty."""
    idle_after = audio_settings.AUDIO_MODEL_IDLE_SECONDS
    if idle_after <= 0 or not _models:       # 0 = never evict (default)
        return
    if time.time() - _last_used >= idle_after:
        _unload_models()


def _get_model(variant: str):
    """Lazy-load a Chatterbox variant; avoids loading both at startup."""
    global _last_used
    _last_used = time.time()

    if variant in _models:
        return _models[variant]

    device = _detect_device()
    logger.debug(f"Loading Chatterbox model: {variant} (device: {device})")

    if variant == "tts":
        from chatterbox.tts import ChatterboxTTS

        model = ChatterboxTTS.from_pretrained(device=device)
    elif variant == "tts_turbo":
        from chatterbox.tts import ChatterboxTurboTTS

        model = ChatterboxTurboTTS.from_pretrained(device=device)
    else:
        raise ValueError(f"Unknown model variant: {variant}")

    _models[variant] = model
    logger.info(f"Model loaded: {variant}")
    return model


def _download_audio_ref(url: str) -> str:
    """Download a remote audio reference URL to a local temp file (caller cleans up)."""
    from studio_workers.engines.video.common import (
        translate_url_for_docker,
        translate_to_internal_endpoint,
    )
    from studio_workers.utils.security import validate_url_scheme

    validate_url_scheme(url)
    translated = translate_url_for_docker(url)
    translated, needs_worker_auth = translate_to_internal_endpoint(translated)

    headers = {}
    if needs_worker_auth:
        worker_secret = settings.auth_secret
        if worker_secret:
            headers["X-Worker-Secret"] = worker_secret

    ext = os.path.splitext(url.split("?")[0])[1] or ".wav"
    fd, tmp_path = tempfile.mkstemp(suffix=ext)
    os.close(fd)

    try:
        with httpx.Client(timeout=settings.HTTP_HANDLER_TIMEOUT_S) as client:
            with client.stream("GET", translated, headers=headers) as response:
                response.raise_for_status()
                with open(tmp_path, "wb") as f:
                    for chunk in response.iter_bytes(
                        chunk_size=settings.HTTP_CHUNK_SIZE
                    ):
                        f.write(chunk)
        logger.debug(f"Downloaded audio reference to: {tmp_path}")
        return tmp_path
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


class AudioWorker(WorkerBase):
    """GPU worker for text-to-speech audio generation."""

    OPERATIONS = {
        "tts": "tts",
        "tts_turbo": "tts_turbo",
    }

    def __init__(self, worker_type: str = "audio"):
        config = get_worker_config(worker_type)

        super().__init__(
            worker_type=config.type_id,
            queue_labels=config.queue_labels,
            capabilities=config.capabilities,
        )

        self.queue_name = config.queue_name
        self.queues = resolve_queues(config)

        # Job client initialized after registration so we have real worker_id from the API.
        self.job_client = None
        self.result_publisher = ResultPublisher(token_getter=self.get_token)
        self._file_upload_client = FileUploadClient(
            token_getter=self.get_token,
            storage_mode_getter=self._detect_storage_mode,
        )

    def process_jobs(self):
        """Main worker loop."""
        global _last_used

        logger.info(f"{self.worker_type.upper()} Worker Started")
        logger.info(f"Monitoring queues: {', '.join(self.queues)}")
        logger.debug(f"Operations: {', '.join(self.OPERATIONS.keys())}")

        _detect_device()

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

        try:
            while self.running:

                job = self.job_client.claim_from(self.queues)

                if job is None:
                    # Idle. The only safe moment to drop the model: no job is in flight,
                    # so nothing can be holding a reference to it.
                    _maybe_unload_idle()

                    sleep_duration = self.job_client.get_sleep_duration()
                    if sleep_duration > 0:
                        time.sleep(sleep_duration)
                    continue

                self._process_job(job)

                # Idle is measured from the end of the last job, not its start -- a long
                # job would otherwise burn its own runtime off the timer.
                _last_used = time.time()

        finally:
            self.job_client.close()
            self.result_publisher.close()

    def _process_job(self, job: Dict[str, Any]):
        """Process a single TTS job."""
        job_id = job.get("job_id", "unknown")
        step_id = job.get("step_id", job_id)

        service_id = job.get("service_id", "")
        if "." in service_id:
            operation = service_id.split(".")[-1]
        else:
            operation = job.get("operation", "unknown")

        step_config = job.get("step_config") or {}
        job_config = step_config.get("job") or {}
        parameters = job_config.get("parameters") or step_config.get("parameters") or {}

        logger.info(f"Processing Audio Job: {job_id}")
        logger.debug(f"Operation: {operation}")

        # set_busy expects queued_jobs.id - workers.current_job_id FKs to it.
        # Passing instance_id here would cause FK violations on every busy heartbeat.
        self.set_busy(job_id)

        if job.get("notify_api", True):
            self.result_publisher.publish_step_result(status="PROCESSING")
            logger.debug("Published PROCESSING status")

        try:
            if operation not in self.OPERATIONS:
                raise ValueError(
                    f"Unknown operation: {operation}. "
                    f"Valid operations: {', '.join(self.OPERATIONS.keys())}"
                )

            text = parameters.get("text")
            if not text:
                raise ValueError("'text' parameter is required")

            audio_prompt_path = parameters.get("audio_prompt_path")
            # Enqueue-side ships file refs as dual-view {virtual_path, url,
            # filename} dicts; this engine still consumes a URL string, so
            # collapse the record here. URL-string inputs pass through.
            if isinstance(audio_prompt_path, dict):
                audio_prompt_path = audio_prompt_path.get("url")
            exaggeration = float(
                parameters.get("exaggeration", audio_settings.AUDIO_TTS_EXAGGERATION)
            )
            cfg_weight = float(
                parameters.get("cfg_weight", audio_settings.AUDIO_TTS_CFG_WEIGHT)
            )

            logger.debug(f"Text length: {len(text)} chars")
            if audio_prompt_path:
                logger.debug(f"Voice cloning from: {audio_prompt_path}")
            logger.debug(
                f"Params: exaggeration={exaggeration}, cfg_weight={cfg_weight}"
            )

            temp_audio_ref = None
            if audio_prompt_path and audio_prompt_path.startswith(
                ("http://", "https://")
            ):
                temp_audio_ref = _download_audio_ref(audio_prompt_path)
                audio_prompt_path = temp_audio_ref

            variant = self.OPERATIONS[operation]
            model = _get_model(variant)

            logger.debug(f"Generating audio with {variant}...")
            generate_start = time.time()
            try:
                wav = model.generate(
                    text,
                    audio_prompt_path=audio_prompt_path,
                    exaggeration=exaggeration,
                    cfg_weight=cfg_weight,
                )
            finally:
                if temp_audio_ref and os.path.exists(temp_audio_ref):
                    os.unlink(temp_audio_ref)
            generate_ms = int((time.time() - generate_start) * 1000)
            logger.debug(
                f"Audio generated ({generate_ms}ms)",
                extra={"duration_ms": generate_ms, "job_id": job_id},
            )

            import soundfile as sf  # type: ignore[import-untyped]

            sample_rate = model.sr
            output_filename = f"audio_{step_id}_{uuid.uuid4().hex[:8]}.wav"

            output_dir = audio_settings.AUDIO_OUTPUT_DIR or os.path.join(
                settings.WORKSPACE_ROOT, "data", "audio_output"
            )
            output_path = os.path.join(output_dir, output_filename)
            os.makedirs(output_dir, exist_ok=True)

            # soundfile writes WAV directly without additional audio codec dependencies.
            wav_numpy = wav.cpu().squeeze().numpy()
            sf.write(output_path, wav_numpy, sample_rate)
            duration_seconds = wav.shape[-1] / sample_rate

            logger.debug(f"Audio saved: {output_path}")
            logger.debug(
                f"Duration: {duration_seconds:.2f}s, Sample rate: {sample_rate}Hz"
            )

            result = {
                "audio_file": output_filename,
                "sample_rate": sample_rate,
                "duration_seconds": round(duration_seconds, 3),
            }

            # Compute size before upload - the local-write path consumes
            # `output_path` via atomic rename, so stat() would 404 after.
            file_size = os.path.getsize(output_path)

            storage_url = self._file_upload_client.upload(
                output_path,
                filename=output_filename,
                job_id=job_id,
                organization_id=job.get("organization_id"),
                instance_id=job.get("instance_id"),
            )
            result["storage_url"] = storage_url
            result["downloaded_files"] = [
                {
                    "filename": output_filename,
                    "virtual_path": storage_url,
                    "file_size": file_size,
                    "display_name": f"TTS Audio ({duration_seconds:.1f}s)",
                    "index": 0,
                }
            ]

            if job.get("notify_api", True):
                if not self.result_publisher.publish_step_result(status="COMPLETED", result=result):
                    logger.critical(
                        "Failed to publish step result after retries - job will be orphaned",
                        extra={"job_id": job_id, "status": "COMPLETED"},
                    )

            logger.info(
                f"Audio job {job_id} completed: {duration_seconds:.1f}s audio, "
                f"text_length={len(text)}",
                extra={"job_id": job_id},
            )

        except Exception as e:
            # Classified sentence to the published result; full exception to worker
            # logs. Raw str(e) leaks infra detail (paths, upstream bodies, CUDA/
            # driver strings) to UI clients. safe_error_message lives in api/, not
            # importable here, so workers inline the classifier (transfer-worker idiom).
            logger.exception(f"Audio job {job_id} failed: {e}")
            error_msg = f"Audio job failed ({type(e).__name__}). See worker logs."
            self._handle_failure(job, error_msg, error_code=classify_error_code(e))

        finally:
            self.set_idle()

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


def main():
    worker = AudioWorker()
    worker.run()


if __name__ == "__main__":
    main()
