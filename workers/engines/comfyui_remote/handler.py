# workers/engines/comfyui_remote/handler.py

"""Lightweight worker that calls an external ComfyUI server. COMFYUI_URL is required."""

import os
import sys
import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
_startup_logger = logging.getLogger("comfyui-remote.startup")

# Validate COMFYUI_URL before importing the handler so failure mode is a clear startup error.
from engines.comfyui.settings import settings as _comfyui_settings

COMFYUI_URL = _comfyui_settings.COMFYUI_URL
if not COMFYUI_URL:  # pragma: no cover - module-level startup guard
    _startup_logger.error("COMFYUI_URL environment variable is REQUIRED")
    _startup_logger.error(
        "The comfyui-remote worker requires an external ComfyUI server."
    )
    _startup_logger.error("Examples:")
    _startup_logger.error("  COMFYUI_URL=https://your-runpod-pod.runpod.io")
    _startup_logger.error("  COMFYUI_URL=http://gpu-server.local:8188")
    _startup_logger.error("  COMFYUI_URL=http://192.168.1.100:8188")
    _startup_logger.error(
        "If you want to run ComfyUI locally, use 'comfyui-image' worker instead:"
    )
    _startup_logger.error("  make run-comfyui-image    # Embedded ComfyUI with GPU")
    sys.exit(1)
elif not COMFYUI_URL.startswith(("http://", "https://")):  # pragma: no cover
    _startup_logger.error(
        f"COMFYUI_URL must start with http:// or https:// (got: {COMFYUI_URL})"
    )
    sys.exit(1)

from engines.comfyui.handler import ComfyUIWorker
from shared.settings import settings
from engines.comfyui.settings import settings as comfyui_settings
from shared.worker_types import get_worker_config

logger = logging.getLogger(__name__)


class ComfyUIRemoteWorker(ComfyUIWorker):
    """Remote ComfyUI worker - no embedded server, COMFYUI_URL required."""

    def __init__(self, worker_type: str = "comfyui-remote"):
        config = get_worker_config(worker_type)

        # Skip parent __init__ (which assumes embedded server) - go straight to grandparent.
        super(ComfyUIWorker, self).__init__(
            worker_type=config.type_id,
            queue_labels=config.queue_labels,
            capabilities=config.capabilities,
        )

        self.queue_name = config.queue_name

        self.job_client = None
        from shared.utils import ResultPublisher, StorageClient
        from shared.utils.file_upload_client import FileUploadClient

        self.result_publisher = ResultPublisher(token_getter=self.get_token)
        self._file_upload_client = FileUploadClient(token_getter=self.get_token)
        self.storage_client = StorageClient()

        self.comfyui_url = COMFYUI_URL

        # Default keeps docker (WORKSPACE_ROOT=/workspace) and native paths working.
        self.output_dir = comfyui_settings.COMFYUI_OUTPUT_DIR or os.path.join(
            settings.WORKSPACE_ROOT, "data", "comfyui_output"
        )
        os.makedirs(self.output_dir, exist_ok=True)

        self.poll_interval = comfyui_settings.COMFYUI_POLL_INTERVAL_S
        self.comfyui_retry_interval = comfyui_settings.COMFYUI_RETRY_INTERVAL_S

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

        self.client = None
        self._comfyui_available = False
        self._last_availability_log = 0

    def process_jobs(self):
        """Main worker loop."""
        logger.info("COMFYUI-REMOTE Worker Started")
        logger.debug("Mode: REMOTE (no embedded ComfyUI)")
        logger.info(f"Monitoring queue: {self.queue_name}")
        logger.debug(f"External ComfyUI: {self.comfyui_url}")
        logger.debug(f"Output directory: {self.output_dir}")
        logger.debug(f"Operations: {', '.join(self.OPERATIONS.keys())}")

        from shared.utils import create_job_client
        import time

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
            logger.debug(f"External ComfyUI available at {self.comfyui_url}")
        else:
            logger.warning(
                f"External ComfyUI not available at {self.comfyui_url}, will retry..."
            )

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


def main():
    worker = ComfyUIRemoteWorker()
    worker.run()


if __name__ == "__main__":
    main()
