# workers/shared/utils/result_publisher.py

"""HTTP client for publishing step results to the API."""

import logging
import time
from typing import Any, Callable, Dict, Optional

import httpx

logger = logging.getLogger(__name__)

from shared.settings import settings
from shared.utils.dead_letter import write_dead_letter

_TERMINAL_STATUSES = frozenset({"COMPLETED", "FAILED"})


class ResultPublisher:
    """Publishes step results to the API via JWT-authenticated HTTP."""

    def __init__(self, token_getter: Callable[[], Optional[str]]):
        self.api_base_url = settings.API_BASE_URL.rstrip("/")
        self._token_getter = token_getter
        self.http_client = httpx.Client(timeout=settings.HTTP_INTERNAL_TIMEOUT_S)

    def _auth_headers(self) -> Dict[str, str]:
        token = self._token_getter()
        if not token:
            raise RuntimeError("Worker JWT not available - not yet registered")
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    def publish_step_result(
        self,
        status: str,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
        job_id: Optional[str] = None,
    ) -> bool:
        """Publish a step result to the API; returns True on success."""
        payload: Dict[str, Any] = {
            "status": status,
            "result": result or {},
            "error": error,
        }
        if job_id:
            payload["job_id"] = job_id

        url = f"{self.api_base_url}/api/v1/internal/step-results"

        for attempt in range(settings.PUBLISH_MAX_RETRIES + 1):
            try:
                response = self.http_client.post(
                    url, json=payload, headers=self._auth_headers()
                )

                if response.status_code in (200, 201, 202):
                    logger.debug(f"Published step result: status={status}")
                    return True

                if (
                    response.status_code in (500, 502, 503, 504)
                    and attempt < settings.PUBLISH_MAX_RETRIES
                ):
                    delay = min(
                        settings.PUBLISH_RETRY_BASE_DELAY * (2**attempt),
                        settings.PUBLISH_RETRY_MAX_DELAY,
                    )
                    logger.warning(
                        f"Publish failed ({response.status_code}), retry {attempt + 1}/{settings.PUBLISH_MAX_RETRIES} in {delay:.1f}s"
                    )
                    time.sleep(delay)
                    continue

                body_preview = " ".join(response.text.split())[:120]
                logger.error(
                    f"Failed to publish step result: {response.status_code} - {body_preview}"
                )
                self._dead_letter_on_terminal(payload, status)
                return False

            except (httpx.ConnectError, httpx.TimeoutException) as e:
                if attempt < settings.PUBLISH_MAX_RETRIES:
                    delay = min(
                        settings.PUBLISH_RETRY_BASE_DELAY * (2**attempt),
                        settings.PUBLISH_RETRY_MAX_DELAY,
                    )
                    logger.warning(
                        f"Publish network error: {e} - retry {attempt + 1}/{settings.PUBLISH_MAX_RETRIES} in {delay:.1f}s"
                    )
                    time.sleep(delay)
                    continue
                logger.error(
                    f"Failed to publish step result after {settings.PUBLISH_MAX_RETRIES} retries: {e}"
                )
                self._dead_letter_on_terminal(payload, status)
                return False

            except Exception as e:
                logger.error(f"Failed to publish step result: {type(e).__name__}: {e}")
                self._dead_letter_on_terminal(payload, status)
                return False

        return False

    @staticmethod
    def _dead_letter_on_terminal(payload: Dict[str, Any], status: str) -> None:
        if status not in _TERMINAL_STATUSES:
            return
        write_dead_letter(payload)

    def close(self):
        self.http_client.close()
