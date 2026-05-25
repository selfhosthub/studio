# workers/engines/comfyui/server.py

"""ComfyUI server lifecycle: subprocess (internal) or connect to existing instance (external)."""

import os
import subprocess
import time
import logging
from typing import Optional

import httpx

from shared.settings import settings
from engines.comfyui.settings import settings as comfyui_settings

logger = logging.getLogger(__name__)


class ComfyUIServer:
    """ComfyUI server lifecycle. Set COMFYUI_EXTERNAL_URL for external mode."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8188,
        comfyui_path: Optional[str] = None,
        external_url: Optional[str] = None,
    ):
        self.external_url = external_url or comfyui_settings.COMFYUI_EXTERNAL_URL
        self.external_mode = bool(self.external_url)

        if self.external_mode:
            self.url = (self.external_url or "").rstrip("/")
            logger.debug(f"ComfyUI external mode: connecting to {self.url}")
        else:
            self.host = host
            self.port = port
            self.comfyui_path = comfyui_path or comfyui_settings.COMFYUI_PATH
            self.url = f"http://{host}:{port}"

        self.process: Optional[subprocess.Popen] = None

    def start(self) -> bool:
        """Start ComfyUI as a subprocess; no-op in external mode."""
        if self.external_mode:
            logger.debug(f"External mode: ComfyUI expected at {self.url}")
            return True

        if self.process is not None and self.process.poll() is None:
            logger.info("ComfyUI server already running")
            return True

        if not os.path.exists(self.comfyui_path):
            logger.error(f"ComfyUI not found at: {self.comfyui_path}")
            return False

        main_py = os.path.join(self.comfyui_path, "main.py")
        if not os.path.exists(main_py):
            logger.error(f"ComfyUI main.py not found: {main_py}")
            return False

        cmd = [
            "python",
            "main.py",
            "--listen",
            self.host,
            "--port",
            str(self.port),
            "--disable-auto-launch",
        ]

        logger.info(f"Starting ComfyUI server: {' '.join(cmd)}")

        try:
            self.process = subprocess.Popen(
                cmd,
                cwd=self.comfyui_path,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,  # line-buffered
            )

            logger.info(f"ComfyUI process started (PID: {self.process.pid})")
            return True

        except Exception as e:
            logger.error(f"Failed to start ComfyUI: {e}")
            self.process = None
            return False

    def wait_for_ready(self, timeout: int = comfyui_settings.COMFYUI_STARTUP_TIMEOUT_S, poll_interval: float = comfyui_settings.COMFYUI_HEALTH_POLL_INTERVAL_S) -> bool:
        """Poll until ComfyUI responds; False on timeout or process death."""
        start_time = time.time()

        while time.time() - start_time < timeout:
            if not self.is_running():
                logger.error("ComfyUI process died during startup")
                self._log_process_output()
                return False

            try:
                response = httpx.get(
                    f"{self.url}/system_stats",
                    timeout=settings.HEALTH_CHECK_TIMEOUT_S,
                )
                if response.status_code == 200:
                    logger.info(f"ComfyUI server ready at {self.url}")
                    return True
            except (httpx.HTTPError, OSError):
                pass

            time.sleep(poll_interval)

        logger.error(f"ComfyUI server not ready after {timeout}s")
        return False

    def is_running(self) -> bool:
        """True in external mode (assumed managed separately)."""
        if self.external_mode:
            return True
        if self.process is None:
            return False
        return self.process.poll() is None

    def stop(self, timeout: int = comfyui_settings.COMFYUI_STOP_TIMEOUT_S):
        """Stop the subprocess; no-op in external mode."""
        if self.external_mode:
            logger.debug("External mode: not stopping external ComfyUI server")
            return

        if self.process is None:
            return

        logger.info("Stopping ComfyUI server...")

        try:
            self.process.terminate()

            try:
                self.process.wait(timeout=timeout)
                logger.info("ComfyUI server stopped gracefully")
            except subprocess.TimeoutExpired:
                logger.warning("ComfyUI not responding, force killing...")
                self.process.kill()
                self.process.wait()
                logger.info("ComfyUI server killed")

        except Exception as e:
            logger.error(f"Error stopping ComfyUI: {e}")

        finally:
            self.process = None

    def restart(self) -> bool:
        logger.info("Restarting ComfyUI server...")
        self.stop()
        time.sleep(comfyui_settings.COMFYUI_RESTART_PAUSE_S)
        return self.start()

    def get_pid(self) -> Optional[int]:
        if self.process is not None and self.is_running():
            return self.process.pid
        return None

    def _log_process_output(self):
        if self.process is None:
            return

        try:
            if self.process.stdout:
                output = []
                while True:
                    line = self.process.stdout.readline()
                    if not line:
                        break
                    output.append(line.strip())
                    if len(output) > 50:
                        break

                if output:
                    logger.error("ComfyUI output:\n" + "\n".join(output))
        except Exception as e:
            logger.error(f"Failed to read ComfyUI output: {e}")

    def health_check(self) -> bool:
        if not self.is_running():
            return False

        try:
            response = httpx.get(
                f"{self.url}/system_stats",
                timeout=settings.HEALTH_CHECK_TIMEOUT_S,
            )
            return response.status_code == 200
        except (httpx.HTTPError, OSError):
            return False
