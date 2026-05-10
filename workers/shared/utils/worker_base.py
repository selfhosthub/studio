# workers/shared/utils/worker_base.py

"""
Base Worker Class with Registration and Heartbeat

All workers should inherit from this base class to get automatic
registration and heartbeat functionality.

Usage:
    class MyWorker(WorkerBase):
        def __init__(self):
            super().__init__(
                worker_type="my-worker",
                queue_labels=["my-queue"],
                capabilities={"gpu": True}
            )

        def process_job(self, job):
            # Handle the job
            pass
"""

import logging
import signal
import socket
import sys
import threading
import time
import uuid
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

import httpx

from shared.settings import settings

logger = logging.getLogger(__name__)

# Try to import psutil for system metrics (optional)
try:
    import psutil

    HAS_PSUTIL = True
except (
    ImportError
):  # pragma: no cover - optional psutil dependency; memory reporting disabled when not installed
    HAS_PSUTIL = False
    logger.warning("psutil not installed - system metrics will not be reported")


class WorkerBase(ABC):
    """
    Base class for all workers with registration and heartbeat support.

    Provides:
    - Automatic registration with the API on startup
    - Background heartbeat thread
    - Graceful shutdown handling
    """

    def __init__(
        self,
        worker_type: str,
        queue_labels: Optional[List[str]] = None,
        capabilities: Optional[Dict[str, Any]] = None,
    ):
        """Initialize the worker base."""
        self.worker_type = worker_type
        self.queue_labels = queue_labels or [worker_type]
        self.capabilities = capabilities or {"type": worker_type}

        # Configuration from settings
        self.api_base_url = settings.API_BASE_URL
        self.worker_secret = settings.WORKER_SHARED_SECRET
        self.worker_name = (
            settings.WORKER_NAME or f"worker-{worker_type}-{uuid.uuid4().hex[:8]}"
        )
        self.heartbeat_interval = settings.HEARTBEAT_INTERVAL_S
        self.registration_retry_interval = settings.REGISTRATION_RETRY_INTERVAL

        # State
        self.worker_id: Optional[str] = None
        self.worker_token: Optional[str] = None  # JWT for job claims
        self.running = False
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._registration_thread: Optional[threading.Thread] = None
        self._current_status = "idle"
        self._current_job_id: Optional[str] = None
        self._busy_since: Optional[float] = None
        # Max time a worker can stay busy before auto-logging a warning (seconds).
        # Does not forcibly kill the job - just ensures visibility for stuck workers.
        self._busy_timeout = settings.WORKER_BUSY_TIMEOUT
        self._token_lock = threading.Lock()  # Protects worker_token updates

        # Connection error tracking (to reduce log noise during restarts)
        self._consecutive_registration_errors = 0
        self._consecutive_heartbeat_errors = 0

        # HTTP client for API calls
        self._http_client = httpx.Client(timeout=settings.HTTP_INTERNAL_TIMEOUT_S)

        # Get network info once at startup
        self._ip_address = self._get_ip_address()
        self._hostname = socket.gethostname()

    def _get_ip_address(self) -> Optional[str]:
        """Get the worker's IP address."""
        try:
            # Create a socket to determine which interface is used for external connections
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except OSError:
            # Narrowed from Exception: only socket/network errors expected here
            return None

    def _get_system_metrics(self) -> Dict[str, Any]:
        """Collect current system metrics (CPU, memory, disk, GPU where available)."""
        metrics = {}

        if not HAS_PSUTIL:
            return metrics

        try:
            # CPU - use interval=None for non-blocking (uses cached value)
            metrics["cpu_percent"] = psutil.cpu_percent(interval=None)

            # Memory
            mem = psutil.virtual_memory()
            metrics["memory_percent"] = mem.percent
            metrics["memory_used_mb"] = int(mem.used / (1024 * 1024))
            metrics["memory_total_mb"] = int(mem.total / (1024 * 1024))

            # Disk (workspace only)
            workspace = settings.WORKSPACE_ROOT
            if not workspace:
                logger.warning("WORKSPACE_ROOT not set - skipping disk metric")
            else:
                try:
                    disk = psutil.disk_usage(workspace)
                    metrics["disk_percent"] = disk.percent
                except OSError:
                    logger.warning(
                        f"disk_usage failed for WORKSPACE_ROOT={workspace} - skipping disk metric"
                    )

        except Exception as e:
            logger.warning(f"Error collecting system metrics: {e}")

        # GPU metrics (if nvidia-smi available)
        try:
            import subprocess

            result = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=utilization.gpu,memory.used,memory.total",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=settings.HEALTH_CHECK_TIMEOUT_S,
            )
            if result.returncode == 0:
                lines = result.stdout.strip().split("\n")
                if lines and lines[0]:
                    parts = lines[0].split(", ")
                    if (
                        len(parts) >= 1
                    ):  # pragma: no branch - defensive guard; split always returns at least one element but guard prevents index error on empty string
                        metrics["gpu_percent"] = float(parts[0])
                    if len(parts) >= 3:
                        mem_used = float(parts[1])
                        mem_total = float(parts[2])
                        metrics["gpu_memory_percent"] = (
                            (mem_used / mem_total) * 100 if mem_total > 0 else 0
                        )
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
            # nvidia-smi not available or failed
            pass

        return metrics

    def register(self) -> bool:
        """Register this worker with the API; returns True on success."""
        try:
            # Collect system metrics for registration
            metrics = self._get_system_metrics()

            payload = {
                "secret": self.worker_secret,
                "name": self.worker_name,
                "capabilities": self.capabilities,
                "queue_labels": self.queue_labels,
                "ip_address": self._ip_address,
                "hostname": self._hostname,
                **metrics,  # Include CPU, memory, disk, GPU metrics
            }

            response = self._http_client.post(
                f"{self.api_base_url}/api/v1/workers/register",
                json=payload,
            )

            if response.status_code == 201:
                data = response.json()
                self.worker_id = data.get("worker_id")
                # Store JWT token (thread-safe)
                with self._token_lock:
                    self.worker_token = data.get("token")
                # Clear error counter and log success
                if self._consecutive_registration_errors > 0:
                    logger.info(
                        f"Registered with API after {self._consecutive_registration_errors} retries"
                    )
                    self._consecutive_registration_errors = 0
                if self.worker_token:
                    logger.info(
                        f"Registered with API as worker {self.worker_id} (JWT token received)"
                    )
                else:
                    logger.info(
                        f"Registered with API as worker {self.worker_id} (no JWT token)"
                    )
                return True
            else:
                body_preview = " ".join(response.text.split())[:120]
                self._log_registration_error(
                    f"Registration failed: {response.status_code} - {body_preview}"
                )
                return False

        except httpx.ConnectError:
            self._log_registration_error(
                f"Could not connect to API at {self.api_base_url}"
            )
            return False
        except Exception as e:
            self._log_registration_error(f"Registration error: {e}")
            return False

    def _log_registration_error(self, message: str):
        """Log registration error with reduced verbosity for repeated failures."""
        self._consecutive_registration_errors += 1
        if self._consecutive_registration_errors == 1:
            logger.warning(message)
        elif self._consecutive_registration_errors == 2:
            logger.warning(
                "Suppressing repeated registration errors (will log when resolved)"
            )
        else:
            logger.debug(message)

    def send_heartbeat(
        self, status: str = "idle", job_id: Optional[str] = None
    ) -> bool:
        """Send a heartbeat to the API; returns True on success."""
        if not self.worker_id:
            return False

        try:
            # Collect current system metrics
            metrics = self._get_system_metrics()

            payload = {
                "status": status,
                **metrics,  # Include CPU, memory, disk, GPU metrics
            }
            if job_id:
                payload["current_job_id"] = job_id

            response = self._http_client.post(
                f"{self.api_base_url}/api/v1/workers/{self.worker_id}/heartbeat",
                json=payload,
            )

            if response.status_code == 200:
                # Clear error counter on success
                if self._consecutive_heartbeat_errors > 0:
                    logger.debug("Heartbeat restored")
                    self._consecutive_heartbeat_errors = 0

                # Check if we've been deregistered by an admin
                data = response.json()
                if data.get("deregistered", False):
                    logger.warning(
                        "Worker deregistered by admin - will attempt re-registration"
                    )
                    self.worker_id = (
                        None  # Clear worker ID so we stop sending heartbeats
                    )
                    with self._token_lock:
                        self.worker_token = None
                    # Start re-registration retry
                    self.start_registration_retry()
                else:
                    # Update JWT token if provided (refreshed on each heartbeat)
                    new_token = data.get("token")
                    if new_token:
                        with self._token_lock:
                            self.worker_token = new_token
                return True
            elif response.status_code == 404:
                # Worker was deleted from the system - trigger re-registration
                logger.debug(
                    "Worker no longer registered (404) - will attempt re-registration"
                )
                self.worker_id = None  # Clear worker ID so we stop sending heartbeats
                with self._token_lock:
                    self.worker_token = None
                # Start re-registration retry
                self.start_registration_retry()
                return False

            # Other non-200 status - log with reduced verbosity
            self._log_heartbeat_error(f"Heartbeat failed: {response.status_code}")
            return False

        except Exception as e:
            self._log_heartbeat_error(f"Heartbeat failed: {e}")
            return False

    def _log_heartbeat_error(self, message: str):
        """Log heartbeat error with reduced verbosity for repeated failures."""
        self._consecutive_heartbeat_errors += 1
        if self._consecutive_heartbeat_errors == 1:
            logger.warning(message)
        elif self._consecutive_heartbeat_errors == 2:
            logger.warning("Suppressing repeated heartbeat errors")
        else:
            logger.debug(message)

    def _heartbeat_loop(self):
        """Background thread that sends periodic heartbeats."""
        while self.running:
            # Check for stuck busy state
            if (
                self._current_status == "busy"
                and self._busy_since is not None
                and time.monotonic() - self._busy_since > self._busy_timeout
            ):
                elapsed = int(time.monotonic() - self._busy_since)
                logger.warning(
                    f"Worker stuck in busy state for {elapsed}s "
                    f"(job: {self._current_job_id}, timeout: {self._busy_timeout}s)"
                )

            self.send_heartbeat(
                status=self._current_status, job_id=self._current_job_id
            )
            time.sleep(self.heartbeat_interval)

    def start_heartbeat(self):
        """Start the background heartbeat thread."""
        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            return

        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            daemon=True,
            name=f"heartbeat-{self.worker_name}",
        )
        self._heartbeat_thread.start()
        logger.debug(f"Heartbeat thread started (interval: {self.heartbeat_interval}s)")

    def _registration_retry_loop(self):
        """Background thread that retries registration until successful."""
        while self.running and not self.worker_id:
            time.sleep(self.registration_retry_interval)
            if not self.running:
                break
            if self.register():
                # Registration successful, start heartbeat
                self.start_heartbeat()
                break

    def start_registration_retry(self):
        """Start background registration retry thread."""
        if self._registration_thread and self._registration_thread.is_alive():
            return

        logger.info(
            f"Will retry registration every {self.registration_retry_interval}s"
        )
        self._registration_thread = threading.Thread(
            target=self._registration_retry_loop,
            daemon=True,
            name=f"registration-{self.worker_name}",
        )
        self._registration_thread.start()

    def set_busy(self, job_id: str):
        """Mark worker as busy processing a job.

        `job_id` MUST be the value from the claimed `queued_jobs` row
        (`job["job_id"]`) - the API's `workers.current_job_id` column
        carries a foreign key to `queued_jobs.id`. Passing anything else
        (e.g. instance_id) triggers a FK violation on every busy heartbeat
        and the heartbeat endpoint 500s silently. If you can't commit to
        the right value, leave the worker reporting idle instead.
        """
        self._current_status = "busy"
        self._current_job_id = job_id
        self._busy_since = time.monotonic()

    def set_idle(self):
        """Mark worker as idle (not processing)."""
        self._current_status = "idle"
        self._current_job_id = None
        self._busy_since = None

    def get_token(self) -> Optional[str]:
        """Thread-safe access to the current JWT token; None if not yet registered."""
        with self._token_lock:
            return self.worker_token

    @abstractmethod
    def process_jobs(self):
        """
        Main job processing loop. Implement in subclass.

        Should:
        1. Poll for jobs from queue
        2. Call self.set_busy(job_id) when starting a job
        3. Process the job
        4. Call self.set_idle() when done
        """
        pass  # pragma: no cover - abstract method placeholder; always overridden by concrete worker subclasses

    def _setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown."""

        def signal_handler(signum, frame):
            logger.info("Shutting down gracefully...")
            self.shutdown()
            sys.exit(0)

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

    def run(self):
        """Register and start processing jobs."""
        # Setup signal handlers first to catch Ctrl+C cleanly
        self._setup_signal_handlers()

        self.running = True

        # Attempt initial registration
        if self.register():
            # Registration successful, start heartbeat immediately
            self.start_heartbeat()
        else:
            # Registration failed - retry in background
            # Worker can start processing jobs while waiting for API
            self.start_registration_retry()

        try:
            # Run the main processing loop
            self.process_jobs()
        except KeyboardInterrupt:
            pass  # Already handled by signal handler
        except SystemExit:
            pass  # Clean exit
        finally:
            self.running = False
            try:
                self._http_client.close()
            except Exception:
                pass  # Ignore errors during cleanup

    def deregister(self):
        """Deregister this worker from the API."""
        if not self.worker_id:
            return
        try:
            response = self._http_client.request(
                "DELETE",
                f"{self.api_base_url}/api/v1/workers/{self.worker_id}",
                json={"secret": self.worker_secret},
            )
            if response.status_code == 200:
                logger.info(f"Deregistered worker {self.worker_id}")
            else:
                logger.warning(f"Deregister failed: {response.status_code}")
        except Exception as e:
            logger.debug(f"Deregister error (shutting down): {e}")

    def shutdown(self):
        """Gracefully shutdown the worker."""
        self.running = False
        self.deregister()
