# workers/engines/transfer/handler.py

"""Streaming file-transfer worker. No GPU, no media processing - streams bytes in chunks."""

import asyncio
import os
import time
import random
import logging
import tempfile
from typing import Dict, Any, Optional, Tuple

import httpx

# Logging is configured by the entry point before this module loads - don't call basicConfig here.
logger = logging.getLogger(__name__)

from shared.settings import settings

RETRY_MAX_ATTEMPTS = settings.HTTP_MAX_RETRIES
TRANSFER_CHUNK_SIZE = settings.TRANSFER_CHUNK_SIZE
RETRY_BASE_DELAY = settings.TRANSFER_RETRY_BASE_DELAY
RETRY_MAX_DELAY = settings.TRANSFER_RETRY_MAX_DELAY
TRANSFER_TIMEOUT = settings.TRANSFER_TIMEOUT_S
RETRY_BACKOFF_FACTOR = settings.HTTP_RETRY_BACKOFF_FACTOR

RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}

from shared.utils import (
    WorkerBase,
    create_job_client,
)
from shared.utils.result_publisher import ResultPublisher
from shared.utils.credential_client import CredentialClient
from shared.utils.redaction import redact_url
from shared.worker_types import get_worker_config


class TransferWorker(WorkerBase):
    """Lightweight worker for streaming file transfers."""

    def __init__(self, worker_type: str = "transfer"):
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
        self.credential_client = CredentialClient()

        # Persistent event loop. CredentialClient caches an httpx.AsyncClient bound to
        # this loop; creating a fresh loop per call would orphan that client on a dead
        # loop and the next call would fail with "Event loop is closed".
        self._async_loop: Optional[asyncio.AbstractEventLoop] = None

    def process_jobs(self):
        """Main worker loop."""
        logger.info(f"{self.worker_type.upper()} Worker Started")
        logger.info(f"Monitoring queue: {self.queue_name}")
        logger.debug(f"Transfer timeout: {TRANSFER_TIMEOUT}s")
        logger.debug(f"Chunk size: {TRANSFER_CHUNK_SIZE} bytes")

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
            self.job_client.close()
            self.result_publisher.close()
            if self._async_loop is not None and not self._async_loop.is_closed():
                try:
                    self._async_loop.run_until_complete(self.credential_client.close())
                except Exception:
                    pass
                self._async_loop.close()
                self._async_loop = None

    def _run_async(self, coro):
        """Run an async coroutine on the worker's persistent event loop."""
        if self._async_loop is None or self._async_loop.is_closed():
            self._async_loop = asyncio.new_event_loop()
        return self._async_loop.run_until_complete(coro)

    def _process_job(self, job: Dict[str, Any]):
        job_id: str = job.get("job_id") or "unknown"
        service_id = job.get("service_id", "")
        step_config = job.get("step_config") or {}
        job_config = step_config.get("job") or {}
        parameters = job_config.get("parameters") or step_config.get("parameters") or {}
        credential_id = job.get("credential_id")
        request_url = job.get("request_url")
        http_method = job.get("http_method", "POST")
        auth_config = job.get("auth_config")
        default_headers = job.get("default_headers")
        parameter_mapping = job.get("parameter_mapping")

        logger.info(f"Processing Transfer Job: {job_id}", extra={"job_id": job_id, "service_id": service_id})
        self.set_busy(job_id)

        try:
            self.result_publisher.publish_step_result(status="PROCESSING")

            result, _ = self._execute_transfer(
                request_url=request_url,
                http_method=http_method,
                credential_id=credential_id,
                parameters=parameters,
                auth_config=auth_config,
                default_headers=default_headers,
                parameter_mapping=parameter_mapping,
            )

            if not self.result_publisher.publish_step_result(status="COMPLETED", result=result):
                logger.critical("Failed to publish step result after retries - job will be orphaned")

            logger.info(f"Transfer job {job_id} completed", extra={"job_id": job_id})

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Transfer job {job_id} failed: {error_msg}", extra={"job_id": job_id})

            if not self.result_publisher.publish_step_result(status="FAILED", error=error_msg):
                logger.critical("Failed to publish step result after retries - job will be orphaned")

        finally:
            self.set_idle()

    def _execute_transfer(
        self,
        request_url: Optional[str],
        http_method: str,
        credential_id: Optional[str],
        parameters: Dict[str, Any],
        auth_config: Optional[Dict[str, Any]] = None,
        default_headers: Optional[Dict[str, str]] = None,
        parameter_mapping: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
        """Route and execute a transfer; returns (result, request_body)."""
        if not request_url:
            raise ValueError("No request URL provided for transfer")

        headers = {}
        if default_headers:
            headers.update(default_headers)

        if credential_id:
            self._apply_credentials(credential_id, auth_config, headers)

        # File-source parameter name is declared by the catalog in parameter_mapping.
        file_source = None
        if parameter_mapping and "file_source_param" in parameter_mapping:
            file_source = parameters.get(parameter_mapping["file_source_param"])

        # Structured body mapping indicates the resumable-upload pattern.
        has_body_mapping = parameter_mapping and "body" in parameter_mapping

        logger.debug(
            f"Upload detection: file_source={bool(file_source)}, "
            f"has_body_mapping={has_body_mapping}, "
            f"parameter_mapping_keys={list(parameter_mapping.keys()) if parameter_mapping else None}"
        )

        request_body = dict(parameters)

        if file_source and has_body_mapping:
            result = self._resumable_upload(
                request_url=request_url,
                http_method=http_method,
                headers=headers,
                parameters=parameters,
                file_source=file_source,
                parameter_mapping=parameter_mapping or {},
            )
        elif file_source:
            result = self._stream_file_upload(
                request_url=request_url,
                http_method=http_method,
                headers=headers,
                parameters=parameters,
                file_source=file_source,
                parameter_mapping=parameter_mapping,
            )
        else:
            result = self._json_request_with_headers(
                request_url=request_url,
                http_method=http_method,
                headers=headers,
                parameters=parameters,
                parameter_mapping=parameter_mapping,
            )

        return result, request_body

    def _resumable_upload(
        self,
        request_url: str,
        http_method: str,
        headers: Dict[str, str],
        parameters: Dict[str, Any],
        file_source: str,
        parameter_mapping: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Two-phase resumable upload: JSON init returns Location, then stream PUT."""
        body_mapping = parameter_mapping["body"]

        structured_body = self._build_structured_body(parameters, body_mapping)

        query_params: Dict[str, Any] = {}
        for key in parameter_mapping.get("query", []):
            if key in parameters and parameters[key] is not None:
                query_params[key] = parameters[key]

        # Phase 1: init (JSON POST with structured body).
        logger.debug("Resumable upload - Phase 1: Init")

        # YouTube's resumable API rejects bare "application/json" with HTTP 400 -
        # it requires "application/json; charset=UTF-8" exactly. Catalog declares this.
        init_headers = dict(headers)
        init_headers["Content-Type"] = parameter_mapping.get(
            "init_content_type", "application/json"
        )

        # Routed through _json_request_with_headers to reuse retry + URL merging.
        init_params = dict(structured_body)
        init_params.update(query_params)
        phase1_result = self._json_request_with_headers(
            request_url=request_url,
            http_method=http_method,
            headers=init_headers,
            parameters=init_params,
            parameter_mapping=(
                {"query": list(query_params.keys())} if query_params else None
            ),
        )

        upload_url = (phase1_result.get("response_headers") or {}).get("location")
        if not upload_url:
            raise RuntimeError(
                "Resumable upload init failed - no Location header in response"
            )

        logger.debug(f"Phase 1 complete - upload URL: {redact_url(upload_url)}")

        # Phase 2: stream file to upload URL.
        logger.debug("Resumable upload - Phase 2: Stream file")
        result = self._stream_file_upload(
            request_url=upload_url,
            http_method="PUT",
            headers=headers,
            parameters=parameters,
            file_source=file_source,
            parameter_mapping={"query": []},
        )

        return result

    def _build_structured_body(
        self,
        parameters: Dict[str, Any],
        body_mapping: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Build a nested JSON body from flat parameters using a body mapping.

        Leaf values in body_mapping are parameter names to look up. None/missing values
        are omitted. e.g. {"snippet": {"title": "title"}} + {"title": "X"}
        -> {"snippet": {"title": "X"}}.
        """
        result: Dict[str, Any] = {}
        for key, value in body_mapping.items():
            if isinstance(value, dict):
                nested = self._build_structured_body(parameters, value)
                if nested:
                    result[key] = nested
            else:
                param_value = parameters.get(value)
                if param_value is not None:
                    result[key] = param_value
        return result

    def _apply_credentials(
        self,
        credential_id: str,
        auth_config: Optional[Dict[str, Any]],
        headers: Dict[str, str],
    ):
        """Fetch credentials and apply auth headers."""
        auth_type = "bearer"
        if auth_config:
            auth_type = auth_config.get("type", "bearer")

        if auth_type in ("header", "basic", "custom"):
            logger.debug("Fetching credentials from API...")
            credentials = self._run_async(
                self.credential_client.get_credential(credential_id)
            )
            if not credentials:
                raise RuntimeError(f"Failed to fetch credentials for {credential_id}")

            if auth_type == "header":
                api_key = (
                    credentials.get("api_key")
                    or credentials.get("access_token")
                    or credentials.get("token")
                )
                if api_key:
                    header_name = (auth_config or {}).get("header", "x-api-key")
                    headers[header_name] = api_key
                    logger.debug(f"Credentials loaded (header: {header_name})")
            elif auth_type == "basic":
                import base64

                api_key = (
                    credentials.get("api_key")
                    or credentials.get("access_token")
                    or credentials.get("token")
                )
                if api_key:
                    encoded = base64.b64encode(f"{api_key}:".encode()).decode()
                    headers["Authorization"] = f"Basic {encoded}"
                    logger.debug("Credentials loaded (basic auth)")
            else:
                # custom: credential fields go to query params, handled by caller.
                pass
        else:
            # Bearer: /token endpoint triggers OAuth refresh.
            logger.debug("Fetching fresh token from API...")
            access_token = self._run_async(
                self.credential_client.get_token(credential_id)
            )
            if access_token:
                headers["Authorization"] = f"Bearer {access_token}"
                logger.debug("Credentials loaded (bearer - fresh token)")
            else:
                raise RuntimeError(
                    f"Failed to fetch token for credential {credential_id}"
                )

    def _resolve_file_source(self, file_source: str) -> str:
        """Resolve a URL or absolute path to a local path."""
        if file_source.startswith("http://") or file_source.startswith("https://"):
            return self._download_to_temp(file_source)

        if os.path.isabs(file_source):
            if not os.path.exists(file_source):
                raise FileNotFoundError(f"File not found: {file_source}")
            return file_source

        raise FileNotFoundError(f"Cannot resolve file source: {file_source}")

    def _download_to_temp(self, url: str) -> str:
        """Stream a URL to a temp path; caller cleans up."""
        logger.debug(f"Downloading file: {url}")

        temp_fd, temp_path = tempfile.mkstemp(prefix="transfer_")
        try:
            with httpx.Client(timeout=httpx.Timeout(TRANSFER_TIMEOUT)) as client:
                with client.stream("GET", url) as response:
                    response.raise_for_status()
                    total_bytes = 0
                    with os.fdopen(temp_fd, "wb") as f:
                        for chunk in response.iter_bytes(
                            chunk_size=TRANSFER_CHUNK_SIZE
                        ):
                            f.write(chunk)
                            total_bytes += len(chunk)

            logger.debug(f"Downloaded {total_bytes} bytes to {temp_path}")
            return temp_path
        except Exception:
            try:
                os.unlink(temp_path)
            except OSError:
                pass
            raise

    def _stream_file_upload(
        self,
        request_url: str,
        http_method: str,
        headers: Dict[str, str],
        parameters: Dict[str, Any],
        file_source: str,
        parameter_mapping: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Stream a file as the HTTP request body."""
        local_path = self._resolve_file_source(file_source)
        temp_downloaded = file_source.startswith("http://") or file_source.startswith(
            "https://"
        )

        try:
            file_size = os.path.getsize(local_path)

            if parameter_mapping and "body_content_type_param" in parameter_mapping:
                ct_param = parameter_mapping["body_content_type_param"]
                content_type = parameters.get(ct_param, "application/octet-stream")
            else:
                content_type = "application/octet-stream"

            upload_headers = dict(headers)
            upload_headers["Content-Type"] = content_type
            upload_headers["Content-Length"] = str(file_size)

            logger.debug(f"Streaming upload: {local_path} ({file_size} bytes)")
            logger.debug(f"-> {http_method} {request_url}")
            logger.debug(f"Content-Type: {content_type}")

            query_params: Dict[str, Any] = {}
            if parameter_mapping is not None:
                for key in parameter_mapping.get("query", []):
                    if key in parameters and parameters[key] is not None:
                        query_params[key] = parameters[key]

            return self._stream_with_retry(
                request_url=request_url,
                http_method=http_method,
                headers=upload_headers,
                local_path=local_path,
                file_size=file_size,
                query_params=query_params if query_params else None,
            )

        finally:
            if temp_downloaded and os.path.exists(local_path):
                try:
                    os.unlink(local_path)
                    logger.debug(f"Cleaned up temp file: {local_path}")
                except OSError:
                    pass

    def _stream_with_retry(
        self,
        request_url: str,
        http_method: str,
        headers: Dict[str, str],
        local_path: str,
        file_size: int,
        query_params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Stream file upload with retry on transient errors."""
        last_exception = None

        for attempt in range(RETRY_MAX_ATTEMPTS + 1):
            try:
                if attempt > 0:
                    logger.debug(f"Retry {attempt}/{RETRY_MAX_ATTEMPTS}")

                with httpx.Client(
                    timeout=httpx.Timeout(
                        connect=30.0,
                        read=TRANSFER_TIMEOUT,
                        write=TRANSFER_TIMEOUT,
                        pool=30.0,
                    )
                ) as client:
                    # httpx 0.28 REPLACES (not merges) the URL's query string when
                    # params= is also passed - pre-merge to keep query params baked
                    # into endpoint_url.
                    merged_url = httpx.URL(request_url).copy_merge_params(
                        query_params or {}
                    )
                    with open(local_path, "rb") as f:
                        response = client.request(
                            method=http_method.upper(),
                            url=merged_url,
                            content=self._file_chunk_iterator(f, file_size),
                            headers=headers,
                        )

                if response.status_code in RETRYABLE_STATUS_CODES:
                    delay = self._calculate_retry_delay(response, attempt)
                    logger.warning(
                        f"{response.status_code} - retrying in {delay:.1f}s..."
                    )
                    time.sleep(delay)
                    continue

                if response.status_code >= 400:
                    error_text = (
                        response.text[:500] if response.text else "No response body"
                    )
                    raise RuntimeError(
                        f"Transfer failed: HTTP {response.status_code} - {error_text}"
                    )

                return self._build_transfer_result(response, file_size)

            except (httpx.ConnectError, httpx.TimeoutException) as e:
                last_exception = e
                if attempt < RETRY_MAX_ATTEMPTS:
                    delay = self._calculate_retry_delay(None, attempt)
                    logger.warning(
                        f"Connection error: {e} - retrying in {delay:.1f}s..."
                    )
                    time.sleep(delay)
                    continue
                raise

        if last_exception:
            raise last_exception
        raise RuntimeError(f"Transfer failed after {RETRY_MAX_ATTEMPTS} retries")

    def _file_chunk_iterator(self, file_obj, file_size: int):
        """Yield file chunks; logs progress every 10%."""
        bytes_sent = 0
        last_log_pct = 0

        while True:
            chunk = file_obj.read(TRANSFER_CHUNK_SIZE)
            if not chunk:
                break
            bytes_sent += len(chunk)
            yield chunk

            if file_size > 0:
                pct = int(bytes_sent * 100 / file_size)
                if pct >= last_log_pct + 10:
                    last_log_pct = pct
                    logger.debug(
                        f"Upload progress: {pct}% ({bytes_sent}/{file_size} bytes)"
                    )

    def _json_request_with_headers(
        self,
        request_url: str,
        http_method: str,
        headers: Dict[str, str],
        parameters: Dict[str, Any],
        parameter_mapping: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """JSON request; result includes both body and response headers."""
        query_params: Dict[str, Any] = {}
        body_params = dict(parameters)

        if parameter_mapping:
            query_keys = parameter_mapping.get("query", [])
            for key in query_keys:
                if key in body_params:
                    query_params[key] = body_params.pop(key)

        if body_params and "Content-Type" not in headers:
            headers["Content-Type"] = "application/json"

        logger.debug(f"{http_method} {request_url}")
        if query_params:
            logger.debug(f"Query params: {list(query_params.keys())}")

        last_exception = None

        for attempt in range(RETRY_MAX_ATTEMPTS + 1):
            try:
                if attempt > 0:
                    logger.debug(f"Retry {attempt}/{RETRY_MAX_ATTEMPTS}")

                with httpx.Client(
                    timeout=httpx.Timeout(
                        connect=30.0,
                        read=TRANSFER_TIMEOUT,
                        write=60.0,
                        pool=30.0,
                    )
                ) as client:
                    # httpx 0.28 REPLACES (not merges) the URL's query string when
                    # params= is also passed - pre-merge to preserve query baked into URL.
                    merged_url = httpx.URL(request_url).copy_merge_params(
                        query_params or {}
                    )
                    response = client.request(
                        method=http_method.upper(),
                        url=merged_url,
                        json=body_params if body_params else None,
                        headers=headers,
                    )

                if response.status_code in RETRYABLE_STATUS_CODES:
                    delay = self._calculate_retry_delay(response, attempt)
                    logger.warning(
                        f"{response.status_code} - retrying in {delay:.1f}s..."
                    )
                    time.sleep(delay)
                    continue

                if response.status_code >= 400:
                    error_text = (
                        response.text[:500] if response.text else "No response body"
                    )
                    raise RuntimeError(
                        f"Request failed: HTTP {response.status_code} - {error_text}"
                    )

                return self._build_transfer_result(response)

            except (httpx.ConnectError, httpx.TimeoutException) as e:
                last_exception = e
                if attempt < RETRY_MAX_ATTEMPTS:
                    delay = self._calculate_retry_delay(None, attempt)
                    logger.warning(
                        f"Connection error: {e} - retrying in {delay:.1f}s..."
                    )
                    time.sleep(delay)
                    continue
                raise

        if last_exception:
            raise last_exception
        raise RuntimeError(f"Request failed after {RETRY_MAX_ATTEMPTS} retries")

    def _build_transfer_result(
        self,
        response: httpx.Response,
        bytes_transferred: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Build result dict from response, including lowercased headers."""
        content_type = response.headers.get("content-type", "").lower()
        if "application/json" in content_type:
            try:
                body = response.json()
                if isinstance(body, list):
                    body = {"data": body}
            except ValueError:
                body = {"raw_response": response.text}
        elif response.text:
            body = {"raw_response": response.text}
        else:
            body = {}

        # Lowercase keys so downstream lookups don't depend on server casing.
        response_headers = {k.lower(): v for k, v in response.headers.items()}

        result: Dict[str, Any] = {
            "status_code": response.status_code,
            "response_headers": response_headers,
            "response_body": body,
        }

        if bytes_transferred is not None:
            result["bytes_transferred"] = bytes_transferred

        logger.debug(f"<- {response.status_code} OK")
        if "location" in response_headers:
            logger.debug(f"Location header: {response_headers['location']}")

        return result

    def _calculate_retry_delay(
        self, response: Optional[httpx.Response], attempt: int
    ) -> float:
        """Exponential backoff with jitter; honors Retry-After on 429."""
        if response is not None and response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            if retry_after:
                try:
                    return min(float(retry_after), RETRY_MAX_DELAY)
                except ValueError:
                    pass

        delay = RETRY_BASE_DELAY * (RETRY_BACKOFF_FACTOR**attempt)
        jitter = delay * 0.25 * random.random()
        delay = delay + jitter

        return min(delay, RETRY_MAX_DELAY)


def main():
    worker = TransferWorker()
    worker.run()


if __name__ == "__main__":
    main()
