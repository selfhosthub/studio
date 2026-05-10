# workers/shared/worker.py
# !/usr/bin/env python3
"""
Unified Worker Entry Point

Configuration-driven worker that routes to appropriate handler based on WORKER_TYPE.

Standard Worker Types:
    - general: Lightweight API worker (HTTP calls, webhooks, data transforms)
    - video: GPU worker for video processing (FFmpeg, Whisper STT)
    - audio: GPU worker for text-to-speech (Chatterbox TTS)
    - comfyui-image: GPU worker for ComfyUI image generation (Flux, SDXL)
    - comfyui-image-edit: GPU worker for ComfyUI image editing (Flux 2 Klein)
    - comfyui-video: GPU worker for ComfyUI video generation

Legacy aliases:
    - orchestrator: Alias for "general"

Environment Variables:
    WORKER_TYPE: Type of worker to run (general, video, audio, comfyui-image, comfyui-image-edit, comfyui-video)
    API_BASE_URL: API base URL for job polling and webhooks
    WORKSPACE_ROOT: Workspace root path (default: /workspace)
    STARTUP_RETRY_INTERVAL: Seconds between startup retries (default: 5)
    STARTUP_MAX_RETRIES: Max retries before giving up, 0=infinite (default: 0)
    LOG_LEVEL: Logging level - DEBUG, INFO, WARNING, ERROR (default: INFO)

Examples:
    WORKER_TYPE=general python -m shared.worker      # HTTP calls, webhooks
    WORKER_TYPE=video python -m shared.worker        # GPU video processing
    WORKER_TYPE=comfyui-image python -m shared.worker  # GPU ComfyUI image gen
"""
import logging
import os
import sys
import time

# Ensure files created by the worker are world-readable (0644 for files,
# 0755 for directories). Some tools default to 0600 which prevents the API
# from serving downloaded assets.
os.umask(0o022)

# Setup logging early so all modules use consistent format
from shared.utils.logging_config import setup_logging

setup_logging()

logger = logging.getLogger(__name__)

from shared.settings import settings
from shared.worker_types import WORKER_TYPES

# Legacy aliases.
LEGACY_ALIASES = {
    "orchestrator": "general",
}

VALID_TYPES = set(WORKER_TYPES.keys()) | set(LEGACY_ALIASES.keys())

# Handler registry: maps worker type -> (module_path, class_name)
# Lazy-imported at runtime so each Docker image only needs its own handler.
# Multiple types can share a handler (e.g. all comfyui-* variants).
HANDLER_REGISTRY = {
    "general": ("engines.general.handler", "WorkflowOrchestrator"),
    "video": ("engines.video.handler", "VideoWorker"),
    "audio": ("engines.audio.handler", "AudioWorker"),
    "comfyui-image": ("engines.comfyui.handler", "ComfyUIWorker"),
    "comfyui-image-edit": ("engines.comfyui.handler", "ComfyUIWorker"),
    "comfyui-video": ("engines.comfyui.handler", "ComfyUIWorker"),
    "transfer": ("engines.transfer.handler", "TransferWorker"),
}


def get_worker_handler(worker_type: str):
    """
    Lazily import and return the handler class for the given worker type.
    This allows each worker image to only include its own handler.
    """
    # Resolve aliases.
    resolved = LEGACY_ALIASES.get(worker_type, worker_type)

    if resolved not in HANDLER_REGISTRY:
        valid = ", ".join(sorted(VALID_TYPES - set(LEGACY_ALIASES.keys())))
        raise ValueError(f"Unknown worker type: {worker_type}. Valid types: {valid}")

    module_path, class_name = HANDLER_REGISTRY[resolved]
    module = __import__(module_path, fromlist=[class_name])
    return getattr(module, class_name)


def wait_for_api(retry_interval: int = 5, max_retries: int = 0) -> bool:
    import httpx

    api_base_url = settings.API_BASE_URL
    health_url = f"{api_base_url}/health"
    attempt = 0

    while True:
        attempt += 1
        try:
            with httpx.Client(timeout=settings.HEALTH_CHECK_TIMEOUT_S) as client:
                response = client.get(health_url)
                if response.status_code == 200:
                    logger.info(f"API is available at {api_base_url}")
                    return True
                raise httpx.ConnectError(f"health check returned {response.status_code}")

        except (httpx.ConnectError, httpx.TimeoutException) as e:
            if max_retries > 0 and attempt >= max_retries:
                logger.error(f"Failed to connect to API after {attempt} attempts")
                return False

            retry_msg = f"(attempt {attempt}"
            if max_retries > 0:
                retry_msg += f"/{max_retries}"
            retry_msg += ")"

            logger.debug(f"Waiting for API at {api_base_url}... {retry_msg}: {e}")
            time.sleep(retry_interval)

        except Exception as e:
            logger.error(f"Unexpected error checking API: {e}")
            if max_retries > 0 and attempt >= max_retries:
                return False
            time.sleep(retry_interval)


def main():
    worker_type = settings.WORKER_TYPE.lower()
    retry_interval = settings.API_STARTUP_RETRY_INTERVAL_S
    max_retries = settings.API_STARTUP_MAX_RETRIES

    # Resolve aliases.
    standard_type = LEGACY_ALIASES.get(worker_type, worker_type)
    display_type = worker_type
    if worker_type in LEGACY_ALIASES:
        display_type = f"{standard_type} (legacy: {worker_type})"

    logger.info("Studio Framework Worker starting")
    logger.info(f"Worker Type: {display_type}")
    logger.info(f"API URL: {settings.API_BASE_URL}")
    logger.debug(f"Workspace: {settings.WORKSPACE_ROOT}")

    if worker_type not in VALID_TYPES:
        valid = ", ".join(sorted(VALID_TYPES - set(LEGACY_ALIASES.keys())))
        logger.error(f"Unknown WORKER_TYPE '{worker_type}'")
        logger.error(f"Valid types: {valid}")
        sys.exit(1)

    # Wait for API before starting
    logger.debug("Checking dependencies...")
    if not wait_for_api(retry_interval, max_retries):
        logger.error("API is not available. Exiting.")
        sys.exit(1)

    logger.info("Polling for jobs...")

    # Lazily import and instantiate the appropriate worker
    worker_class = get_worker_handler(worker_type)
    worker = worker_class(worker_type=standard_type)
    worker.run()


if __name__ == "__main__":
    main()
