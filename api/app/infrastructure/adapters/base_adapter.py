# api/app/infrastructure/adapters/base_adapter.py

"""Base provider adapter with retry, rate-limit, and error handling for HTTP integrations."""

import httpx
import asyncio
import logging
from typing import Any, Callable, Dict, Optional, Tuple
from uuid import UUID
from abc import abstractmethod

from app.application.interfaces.provider_adapter import (
    IProviderAdapter,
    ProviderExecutionResult,
    CredentialValidationResult,
    HealthCheckResult,
)
from app.config.settings import settings


logger = logging.getLogger(__name__)


class BaseProviderAdapter(IProviderAdapter):
    """Base adapter for HTTP-based provider integrations with exponential backoff retry."""

    def __init__(
        self,
        base_url: str,
        timeout_seconds: float = settings.ADAPTER_CLIENT_TIMEOUT,
        max_retries: int = settings.JOB_RETRY_LIMIT,
        initial_backoff: float = 1.0,
        backoff_multiplier: float = 2.0,
    ):
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries
        self._initial_backoff = initial_backoff
        self._backoff_multiplier = backoff_multiplier
        self._client = httpx.AsyncClient(timeout=timeout_seconds)

    async def _request_with_retry(
        self,
        method: str,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        json: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None,
    ) -> httpx.Response:
        """HTTP request with retry on network errors, 429, and 5xx. Client errors pass through."""
        last_exception = None
        effective_timeout = timeout or self._timeout_seconds

        for attempt in range(self._max_retries):
            try:
                logger.debug(
                    f"HTTP {method} {url} (attempt {attempt + 1}/{self._max_retries})"
                )

                response = await self._client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    json=json,
                    params=params,
                    timeout=effective_timeout,
                )

                if response.status_code == 429:
                    retry_after = self._get_retry_after(response, attempt)
                    logger.warning(
                        f"Rate limit hit (429), retrying after {retry_after}s"
                    )
                    await asyncio.sleep(retry_after)
                    continue

                if 500 <= response.status_code < 600:
                    if attempt < self._max_retries - 1:
                        backoff = self._calculate_backoff(attempt)
                        logger.warning(
                            f"Server error ({response.status_code}), "
                            f"retrying after {backoff}s"
                        )
                        await asyncio.sleep(backoff)
                        continue

                return response

            except (httpx.ConnectError, httpx.TimeoutException) as e:
                last_exception = e
                if attempt < self._max_retries - 1:
                    backoff = self._calculate_backoff(attempt)
                    logger.warning(
                        f"Network error ({type(e).__name__}), "
                        f"retrying after {backoff}s: {str(e)}"
                    )
                    await asyncio.sleep(backoff)
                    continue

            except httpx.HTTPError as e:
                logger.error(f"HTTP error on {method} {url}: {str(e)}")
                raise

        if last_exception:
            logger.error(
                f"All {self._max_retries} retries exhausted for {method} {url}"
            )
            raise last_exception

        raise RuntimeError(
            f"Request failed after {self._max_retries} attempts without clear error"
        )

    def _calculate_backoff(self, attempt: int) -> float:
        return self._initial_backoff * (self._backoff_multiplier**attempt)

    def _get_retry_after(self, response: httpx.Response, attempt: int) -> float:
        """Honor Retry-After header on 429; fall back to exponential backoff."""
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                return float(retry_after)
            except ValueError:
                logger.warning(f"Invalid Retry-After header: {retry_after}")

        return self._calculate_backoff(attempt)

    def _should_retry(
        self, exception: Optional[Exception], response: Optional[httpx.Response]
    ) -> bool:
        if isinstance(exception, (httpx.ConnectError, httpx.TimeoutException)):
            return True

        if response and response.status_code == 429:
            return True

        if response and 500 <= response.status_code < 600:
            return True

        return False

    async def _poll_for_completion(
        self,
        status_url: str,
        headers: Dict[str, str],
        status_check_fn: Callable[[Dict[str, Any]], Tuple[str, Any]],
        max_attempts: int = settings.BASE_ADAPTER_MAX_POLL_ATTEMPTS,
        interval_seconds: float = settings.BASE_ADAPTER_POLL_INTERVAL,
        initial_delay: float = settings.BASE_ADAPTER_INITIAL_DELAY,
    ) -> Dict[str, Any]:
        """Poll a status endpoint until status_check_fn returns 'complete' or 'failed'.

        status_check_fn takes response JSON and returns one of:
            ('complete', data) | ('failed', error) | ('pending', None)
        """
        if initial_delay > 0:
            await asyncio.sleep(initial_delay)

        for attempt in range(max_attempts):
            logger.debug(f"Polling {status_url} (attempt {attempt + 1}/{max_attempts})")

            try:
                response = await self._request_with_retry(
                    method="GET",
                    url=status_url,
                    headers=headers,
                )

                data = response.json()

                status, result = status_check_fn(data)

                if status == "complete":
                    logger.info(
                        f"Polling completed successfully after {attempt + 1} attempts"
                    )
                    return result

                elif status == "failed":
                    error_msg = result or "Job failed without error message"
                    logger.error(f"Polling detected job failure: {error_msg}")
                    raise Exception(f"Provider job failed: {error_msg}")

                elif status == "pending":
                    if attempt < max_attempts - 1:
                        await asyncio.sleep(interval_seconds)
                        continue

            except Exception as e:
                if "Provider job failed" in str(e):
                    raise
                logger.warning(f"Error during polling attempt {attempt + 1}: {str(e)}")
                if attempt < max_attempts - 1:
                    await asyncio.sleep(interval_seconds)
                    continue
                else:
                    raise

        timeout_msg = (
            f"Polling timeout: job did not complete after {max_attempts} attempts "
            f"({max_attempts * interval_seconds}s total)"
        )
        logger.error(timeout_msg)
        raise TimeoutError(timeout_msg)

    async def close(self) -> None:
        await self._client.aclose()

    @property
    @abstractmethod
    def provider_name(self) -> str:
        pass

    @property
    @abstractmethod
    def supported_services(self) -> list[str]:
        pass

    @abstractmethod
    async def execute_service(
        self,
        service_id: str,
        parameters: Dict[str, Any],
        credentials: Dict[str, Any],
        organization_id: UUID,
        timeout_seconds: Optional[int] = None,
        service_config: Optional[Dict[str, Any]] = None,
    ) -> ProviderExecutionResult:
        pass

    @abstractmethod
    async def validate_credentials(
        self, credentials: Dict[str, Any]
    ) -> CredentialValidationResult:
        pass

    @abstractmethod
    async def health_check(self) -> HealthCheckResult:
        pass

    @abstractmethod
    def get_service_schema(self, service_id: str) -> Dict[str, Any]:
        pass

    @abstractmethod
    def supports_service(self, service_id: str) -> bool:
        pass
