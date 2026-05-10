# workers/shared/utils/http_job_client.py

"""
HTTP Job Client for Worker Architecture.

Workers poll GET /internal/jobs/claim to get work.
Results are published to POST /internal/step-results.

Authentication: JWT Bearer + X-Worker-Secret header.
"""

import logging
import os
from typing import Any, Callable, Dict, Optional

import httpx

logger = logging.getLogger(__name__)

from shared.settings import settings

# Configuration
API_BASE_URL: str = settings.API_BASE_URL
WORKER_SHARED_SECRET: str = settings.WORKER_SHARED_SECRET
JOB_POLL_INTERVAL = settings.JOB_POLL_INTERVAL_S
JOB_POLL_BACKOFF_MAX = settings.JOB_POLL_BACKOFF_MAX_S


class HTTPJobClient:
    """HTTP client for claiming jobs from the API."""

    def __init__(
        self,
        worker_id: Optional[str] = None,
        token_getter: Optional[Callable[[], Optional[str]]] = None,
    ):
        self.api_base_url = API_BASE_URL.rstrip("/")
        self.worker_secret = WORKER_SHARED_SECRET
        self.worker_id = worker_id or f"worker-{os.getpid()}"
        self.token_getter = token_getter
        self.poll_interval = JOB_POLL_INTERVAL
        self.backoff_max = JOB_POLL_BACKOFF_MAX
        self.current_backoff = JOB_POLL_INTERVAL
        self.consecutive_empty = 0

        # Connection error tracking (to reduce log noise during restarts)
        self._consecutive_connection_errors = 0
        self._last_token_warning = False  # Track if we've warned about missing token

        # HTTP client with connection pooling
        self.client = httpx.Client(
            timeout=settings.HTTP_INTERNAL_TIMEOUT_S,
            headers={
                "X-Worker-Secret": self.worker_secret,
                "Content-Type": "application/json",
            },
        )

        logger.debug(
            f"HTTPJobClient initialized: api={self.api_base_url}, worker_id={self.worker_id}"
        )

    def claim_job(self, queue_name: str, timeout: int = 1) -> Optional[Dict[str, Any]]:
        """Claim the next available job from a queue; returns None if empty."""
        try:
            # Clear previous job's correlation_id before claiming next
            from shared.utils.logging_config import clear_job_correlation_id

            clear_job_correlation_id()

            headers = {}
            params = {"queue_name": queue_name}

            # Get JWT token for authentication
            if self.token_getter:
                token = self.token_getter()
                if token:
                    headers["Authorization"] = f"Bearer {token}"
                    # Clear token warning flag when token becomes available
                    if self._last_token_warning:
                        self._last_token_warning = False
                        logger.debug("JWT token now available")
                else:
                    # Only warn once about missing token to reduce log noise
                    if not self._last_token_warning:
                        logger.warning(
                            "No JWT token available - waiting for registration"
                        )
                        self._last_token_warning = True

            response = self.client.get(
                f"{self.api_base_url}/api/v1/internal/jobs/claim",
                params=params,
                headers=headers,
            )

            if response.status_code == 200:
                job_data = response.json()
                self._reset_backoff()
                self._clear_connection_errors()
                logger.info(
                    f"Claimed job {job_data.get('job_id')} from queue {queue_name}"
                )

                payload = job_data.get("payload", job_data)

                # Propagate correlation_id from job payload to logging context
                from shared.utils.logging_config import set_job_correlation_id

                set_job_correlation_id(payload.get("correlation_id"))

                return payload

            elif response.status_code == 204:
                # No jobs available - this is normal, don't log
                self._increase_backoff()
                self._clear_connection_errors()
                return None

            elif response.status_code == 401:
                # Auth error - only log once to reduce noise during startup
                if self._consecutive_connection_errors == 0:
                    logger.debug("Auth failed (401) - waiting for registration")
                self._log_connection_error(f"Auth failed: {response.status_code}")
                self._increase_backoff()
                return None

            else:
                body_preview = " ".join(response.text.split())[:120]
                self._log_connection_error(
                    f"Failed to claim job: {response.status_code} - {body_preview}"
                )
                self._increase_backoff()
                return None

        except httpx.RequestError as e:
            self._log_connection_error(f"HTTP error claiming job: {e}")
            self._increase_backoff()
            return None

    def get_sleep_duration(self) -> float:
        return self.current_backoff

    def _reset_backoff(self):
        """Reset backoff to base interval after successful claim."""
        self.current_backoff = self.poll_interval
        self.consecutive_empty = 0

    def _increase_backoff(self):
        """Increase backoff (exponential) when no jobs found."""
        self.consecutive_empty += 1
        # Exponential backoff: 5 -> 10 -> 20 -> 40 -> 60 (max)
        self.current_backoff = min(
            self.poll_interval * (2 ** min(self.consecutive_empty, 4)), self.backoff_max
        )

    def _log_connection_error(self, message: str):
        # First error at ERROR level; subsequent errors at DEBUG to reduce noise during restarts.
        self._consecutive_connection_errors += 1
        if self._consecutive_connection_errors == 1:
            logger.error(message)
        elif self._consecutive_connection_errors == 2:
            logger.warning(
                "Suppressing repeated connection errors (will log when resolved)"
            )
        else:
            logger.debug(message)

    def _clear_connection_errors(self):
        """Clear connection error counter when connection is restored."""
        if self._consecutive_connection_errors > 0:
            if self._consecutive_connection_errors > 1:
                logger.warning(
                    f"Connection restored (after {self._consecutive_connection_errors} errors)"
                )
            self._consecutive_connection_errors = 0

    def close(self):
        self.client.close()
        logger.debug("HTTPJobClient closed")


class JobClient:
    """HTTP job client for polling jobs from the API."""

    def __init__(
        self,
        worker_id: Optional[str] = None,
        token_getter: Optional[Callable[[], Optional[str]]] = None,
    ):
        self.worker_id = worker_id or f"worker-{os.getpid()}"
        self._token_getter = token_getter
        self._http_client = HTTPJobClient(
            worker_id=self.worker_id,
            token_getter=token_getter,
        )
        self._current_job_id: Optional[str] = None

    def claim_job(self, queue_name: str, timeout: int = 1) -> Optional[Dict[str, Any]]:
        """Claim the next available job from a queue; returns None if empty."""
        job = self._http_client.claim_job(queue_name, timeout)
        if job:
            self._current_job_id = job.get("job_id")
        return job

    def get_sleep_duration(self) -> float:
        """Get the recommended sleep duration between polls (with backoff)."""
        return self._http_client.get_sleep_duration()

    def get_current_job_id(self) -> Optional[str]:
        """Get the job_id from the last claimed job."""
        return self._current_job_id

    def close(self):
        self._http_client.close()


# Backwards compatibility aliases
UnifiedJobClient = JobClient


def create_job_client(
    worker_id: Optional[str] = None,
    token_getter: Optional[Callable[[], Optional[str]]] = None,
) -> JobClient:
    """Factory for creating a job client."""
    return JobClient(worker_id=worker_id, token_getter=token_getter)
