# workers/engines/general/executor.py

"""Pure execution logic for general worker steps. No queue/publish coupling."""

import asyncio
import json
import os
import time
import random
import uuid
import hashlib
import shutil
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
import httpx
from jsonpath_ng.ext import parse as jsonpath_parse

logger = logging.getLogger(__name__)

try:
    from PIL import Image

    PIL_AVAILABLE = True
except ImportError:  # pragma: no cover
    PIL_AVAILABLE = False

IMAGE_MIME_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}

from shared.settings import settings

FILE_DOWNLOAD_MAX_MB = settings.FILE_DOWNLOAD_MAX_MB
FFPROBE_TIMEOUT_S = settings.FFPROBE_TIMEOUT_S
RETRY_MAX_ATTEMPTS = settings.HTTP_MAX_RETRIES
RETRY_BASE_DELAY = settings.HTTP_RETRY_BASE_DELAY
RETRY_MAX_DELAY = settings.HTTP_RETRY_MAX_DELAY
RETRY_BACKOFF_FACTOR = settings.HTTP_RETRY_BACKOFF_FACTOR

RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}

from shared.utils.credential_client import CredentialClient
from shared.utils.file_upload_client import FileUploadClient


# Stripped from instance params before reaching core services.
# External HTTP bodies are filtered API-side in GenericHTTPAdapter.
INTERNAL_KEYS = {"form_values", "_meta", "_internal", "__studio"}


_sync_loop: Optional[asyncio.AbstractEventLoop] = None


def _run_sync(coro):
    # Reuse a single loop so cached AsyncClients stay bound to one loop.
    # Avoids the 3.12+ get_event_loop() deprecation when no loop is current.
    global _sync_loop
    if _sync_loop is None or _sync_loop.is_closed():
        _sync_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_sync_loop)
    return _sync_loop.run_until_complete(coro)


class JobExecutor:

    def __init__(
        self,
        http_client: httpx.Client,
        credential_client: CredentialClient,
        token_getter=None,
    ):
        self.http_client = http_client
        self.credential_client = credential_client
        if token_getter is None:
            raise ValueError("token_getter is required")
        self._upload_client = FileUploadClient(token_getter=token_getter)

    def execute(
        self,
        step_config: Dict[str, Any],
        instance_parameters: Dict[str, Any],
        previous_results: Dict[str, Any],
        credential_id: Optional[str],
        polling_config: Optional[Dict[str, Any]] = None,
        auth_config: Optional[Dict[str, Any]] = None,
        provider_id: Optional[str] = None,
        service_id: Optional[str] = None,
        local_worker: Optional[Dict[str, Any]] = None,
        post_processing_config: Optional[Dict[str, Any]] = None,
        result_schema: Optional[Dict[str, Any]] = None,
        org_settings: Optional[Dict[str, Any]] = None,
        iteration_index: Optional[int] = None,
        http_request: Optional[Dict[str, Any]] = None,
        dispatch: Optional[List[str]] = None,
        job_id: Optional[str] = None,
    ) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
        """Execute a single workflow step. Returns (result, request_body)."""
        job_config = step_config.get("job") or {}
        if not service_id:
            service_id = (
                step_config.get("service_id") or job_config.get("service_id") or ""
            )
        if not provider_id:
            provider_id = (
                step_config.get("provider_id") or job_config.get("provider_id") or ""
            )

        # job.parameters wins (API merges defaults there). Scene expansion and file URL
        # resolution already happened at enqueue, so these are wire-ready.
        step_params = (
            job_config.get("parameters") or step_config.get("parameters") or {}
        )
        filtered_instance_params = {
            k: v
            for k, v in (instance_parameters or {}).items()
            if k not in INTERNAL_KEYS
        }
        merged_params = {**filtered_instance_params, **(step_params or {})}
        request_body: Dict[str, Any] = dict(merged_params)

        service_id = service_id or ""
        if service_id.startswith("core."):
            result = self._execute_core_service(
                service_id, step_config, merged_params, dispatch=dispatch
            )

        elif local_worker and local_worker.get("enabled"):
            # Local worker jobs should reach their queues directly from API. Hitting
            # the general worker means routing is broken upstream.
            queue = local_worker.get("queue", "unknown")
            logger.error(
                f"Local worker job for {provider_id} was sent to general worker. "
                f"API should route this directly to {queue} queue."
            )
            result = {
                "status": "FAILED",
                "error": f"Routing error: {provider_id} jobs should go to {queue}, not step_jobs. Check API routing.",
            }

        elif http_request:
            result, actual_request = self._fire_prebuilt_request(
                http_request=http_request,
                credential_id=credential_id,
                auth_config=auth_config,
                polling_config=polling_config,
            )
            request_body = actual_request

        else:
            raise ValueError(
                f"Unknown service type: {service_id} (provider: {provider_id}). "
                f"HTTP-provider jobs require an `http_request` envelope from API enqueue."
            )

        # Project BEFORE post-processing: strips undeclared provider fields (e.g. echoed
        # render specs) while preserving downloaded_files/storage_url added afterward.
        # Binary and QUEUED results skip projection (no JSON response shape).
        if (
            result_schema
            and isinstance(result, dict)
            and not result.get("_binary_response")
            and result.get("status") != "QUEUED"
        ):
            from contracts.schema_projection import project_by_schema

            result = project_by_schema(result, result_schema)

        # Skip for QUEUED results (local worker routing).
        if post_processing_config and not (
            isinstance(result, dict) and result.get("status") == "QUEUED"
        ):
            result = self._post_process_result(
                result=result,
                post_processing_config=post_processing_config,
                org_settings=org_settings,
                iteration_index=iteration_index,
                job_id=job_id,
            )

        return result, request_body

    def _execute_core_service(
        self,
        service_id: str,
        step_config: Dict[str, Any],
        parameters: Dict[str, Any],
        dispatch: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Execute core services that reach the worker.

        poll_service has its own branch (loop + condition expressions). Other core
        services route by catalog dispatch (e.g. dispatch=["http_request"]) so new
        services adding HTTP-out auto-route here without code changes.
        Unknown service IDs pass through for backward compat with inline: true services.
        """

        if service_id == "core.poll_service":
            return self._execute_poll_service(step_config, parameters)

        if dispatch and "http_request" in dispatch:
            return self._execute_http_request(parameters)

        logger.info(f"→ Unknown core service: {service_id}")
        return parameters

    def _execute_http_request(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Fire a single outbound HTTP request from parameters.

        Network errors raise (step fails). 4xx/5xx return success=False with body intact
        so workflows can inspect failure detail. No retry; timeout is per-request.
        """
        url = parameters.get("url")
        if not url:
            raise ValueError("HTTP request service requires 'url' parameter")

        method = (parameters.get("method") or "POST").upper()
        body = parameters.get("body")
        if body is None:
            body = {}
        # UI textarea paths store object bodies as JSON-encoded strings. Coerce so httpx
        # posts the object, not a string. Non-JSON strings pass through (raw text bodies).
        if isinstance(body, str):
            stripped = body.strip()
            if stripped.startswith(("{", "[")):
                try:
                    body = json.loads(stripped)
                except ValueError:
                    pass
        extra_headers = parameters.get("headers") or {}
        timeout = parameters.get("timeout", 30)

        headers = dict(extra_headers)
        if method in ("POST", "PUT", "PATCH") and "Content-Type" not in headers:
            headers["Content-Type"] = "application/json"

        logger.debug(f"→ {method} {url} (timeout={timeout}s)")

        request_kwargs: Dict[str, Any] = {
            "headers": headers,
            "timeout": timeout,
        }
        if method in ("POST", "PUT", "PATCH"):
            request_kwargs["json"] = body

        start = time.time()
        response = self.http_client.request(method, url, **request_kwargs)
        elapsed_ms = round((time.time() - start) * 1000, 2)

        try:
            body_out: Any = response.json()
        except ValueError:
            body_out = response.text

        success = 200 <= response.status_code < 300
        logger.debug(f"← {response.status_code} ({elapsed_ms}ms, success={success})")

        return {
            "status_code": response.status_code,
            "body": body_out,
            "headers": dict(response.headers),
            "elapsed_ms": elapsed_ms,
            "success": success,
        }

    def _execute_poll_service(
        self, step_config: Dict[str, Any], parameters: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Generic HTTP polling.

        Stops on success_condition/success_codes (success), failure_condition/fail_codes
        (immediate fail), or max_attempts/timeout. condition_field+condition_value is the
        legacy path. Expression syntax supports ==/===/!=/!==/comparisons,
        AND/OR/NOT (case insensitive), parens, and literals.
        """
        import time

        url = parameters.get("url")
        if not url:
            raise ValueError("Poll service requires 'url' parameter")

        method = parameters.get("method", "GET").upper()
        extra_headers = parameters.get("headers", {})
        success_codes = parameters.get("success_codes", [200])
        fail_codes = parameters.get(
            "fail_codes",
            [
                400,
                401,
                402,
                403,
                404,
                405,
                406,
                408,
                409,
                410,
                422,
                429,
                500,
                501,
                502,
                503,
                504,
            ],
        )

        success_condition = parameters.get("success_condition")
        failure_condition = parameters.get("failure_condition")

        # Legacy field/value conditions.
        condition_field = parameters.get("condition_field")
        condition_value = parameters.get("condition_value")
        fail_values = parameters.get("fail_values", ["error", "failed"])

        interval_seconds = parameters.get("interval_seconds", 10)
        max_attempts = parameters.get("max_attempts", 60)
        timeout_seconds = parameters.get("timeout_seconds", 600)

        logger.debug(f"→ Poll service: {url}")
        logger.debug(
            f"  Method: {method}, Interval: {interval_seconds}s, Max attempts: {max_attempts}"
        )
        if success_condition:
            logger.debug(f"  Success when: {success_condition}")
        elif condition_field:
            logger.debug(f"  Success when: {condition_field} == {condition_value}")
        if failure_condition:
            logger.debug(f"  Fail when: {failure_condition}")

        job_config = step_config.get("job") or {}
        credential_id = job_config.get("credential_id") or step_config.get(
            "credential_id"
        )

        headers = {**extra_headers}
        if credential_id:
            try:
                creds = self._fetch_credential(credential_id)
                if creds:
                    api_key = creds.get("api_key")
                    if api_key:
                        auth_config = job_config.get("auth_config") or {}
                        auth_type = auth_config.get("type", "bearer")
                        if auth_type == "header":
                            header_name = auth_config.get("header", "x-api-key")
                            headers[header_name] = api_key
                        else:
                            headers["Authorization"] = f"Bearer {api_key}"
            except Exception as e:
                logger.warning(f" Failed to fetch credentials: {e}")

        start_time = time.time()
        attempt = 0
        last_result = None

        while attempt < max_attempts:
            elapsed = time.time() - start_time
            if timeout_seconds > 0 and elapsed > timeout_seconds:
                raise TimeoutError(f"Polling timed out after {timeout_seconds}s")

            if attempt > 0:
                time.sleep(interval_seconds)

            attempt += 1

            try:
                if method == "GET":
                    response = self.http_client.get(url, headers=headers)
                else:
                    response = self.http_client.post(url, headers=headers)

                status_code = response.status_code
                logger.debug(f"→ Poll {attempt}/{max_attempts}: HTTP {status_code}")

                if status_code in fail_codes:
                    error_text = (
                        response.text[:200] if response.text else "No response body"
                    )
                    raise RuntimeError(
                        f"Polling failed with HTTP {status_code}: {error_text}"
                    )

                if status_code not in success_codes:
                    logger.debug(f"  Unexpected status {status_code}, retrying...")
                    continue

                try:
                    last_result = response.json()
                except ValueError:
                    last_result = {"raw_response": response.text}

                # Check failure condition first so terminal failures short-circuit success.
                if failure_condition:
                    try:
                        if self._evaluate_condition(failure_condition, last_result):
                            error_msg = (
                                self._get_nested_value(last_result, "message")
                                or self._get_nested_value(last_result, "movie.message")
                                or self._get_nested_value(last_result, "error")
                                or f"Failure condition met: {failure_condition}"
                            )
                            raise RuntimeError(f"Polling failed: {error_msg}")
                    except RuntimeError:
                        raise
                    except Exception as e:
                        logger.info(f"  ⚠ Failed to evaluate failure_condition: {e}")

                if success_condition:
                    try:
                        if self._evaluate_condition(success_condition, last_result):
                            logger.debug(
                                f"✓ Poll complete after {attempt} attempts ({elapsed:.1f}s)"
                            )
                            return last_result
                        else:
                            status = self._get_nested_value(
                                last_result, "movie.status"
                            ) or self._get_nested_value(last_result, "status")
                            if status:
                                logger.debug(f"  status = {status} (waiting...)")
                            continue
                    except Exception as e:
                        logger.debug(f"  ⚠ Failed to evaluate success_condition: {e}")
                        continue

                elif condition_field:
                    field_value = self._get_nested_value(last_result, condition_field)
                    logger.debug(f"  {condition_field} = {field_value}")

                    if field_value in fail_values:
                        error_msg = (
                            last_result.get("message")
                            or last_result.get("error")
                            or f"{condition_field}={field_value}"
                        )
                        raise RuntimeError(f"Polling failed: {error_msg}")

                    if str(field_value) == str(condition_value):
                        logger.debug(
                            f"✓ Poll complete after {attempt} attempts ({elapsed:.1f}s)"
                        )
                        return last_result

                else:
                    # No conditions: a success status code is enough.
                    logger.debug(f"✓ Poll complete (HTTP {status_code})")
                    return last_result

            except RuntimeError:
                raise
            except TimeoutError:
                raise
            except Exception as e:
                logger.warning(f" Poll attempt {attempt} failed: {e}")
                last_result = {
                    "error": f"Poll attempt {attempt} failed ({type(e).__name__}). See worker logs."
                }

        raise TimeoutError(f"Polling exceeded max attempts ({max_attempts})")

    def _evaluate_condition(self, expression: str, data: Dict[str, Any]) -> bool:
        """Evaluate a boolean expression against JSON data; supports paths, comparisons, AND/OR/NOT."""
        tokens = self._tokenize_condition(expression)
        if not tokens:
            return False

        result, _ = self._parse_or_expression(tokens, 0, data)
        return result

    def _tokenize_condition(self, expression: str) -> list:
        """Tokenize a condition expression; returns (token_type, value) tuples."""
        import re

        tokens = []
        pattern = r"""
            \s*(?:
                (===|!==|==|!=|>=|<=|>|<)|    # Operators
                (\()|                           # Left paren
                (\))|                           # Right paren
                (\bAND\b|\band\b)|              # AND
                (\bOR\b|\bor\b)|                # OR
                (\bNOT\b|\bnot\b)|              # NOT
                ("(?:[^"\\]|\\.)*")|            # Double-quoted string
                ('(?:[^'\\]|\\.)*')|            # Single-quoted string
                (\btrue\b|\bfalse\b)|           # Boolean
                (\bnull\b)|                     # Null
                (-?\d+\.?\d*)|                  # Number
                ([a-zA-Z_][a-zA-Z0-9_.\[\]]*)   # Field path (allows dots, brackets)
            )\s*
        """

        for match in re.finditer(pattern, expression, re.VERBOSE | re.IGNORECASE):
            (
                op,
                lparen,
                rparen,
                and_op,
                or_op,
                not_op,
                dquote,
                squote,
                boolean,
                null,
                number,
                field,
            ) = match.groups()

            if op:
                tokens.append(("OP", op))
            elif lparen:
                tokens.append(("LPAREN", "("))
            elif rparen:
                tokens.append(("RPAREN", ")"))
            elif and_op:
                tokens.append(("AND", "AND"))
            elif or_op:
                tokens.append(("OR", "OR"))
            elif not_op:
                tokens.append(("NOT", "NOT"))
            elif dquote:
                tokens.append(("LITERAL", dquote[1:-1].replace('\\"', '"')))
            elif squote:
                tokens.append(("LITERAL", squote[1:-1].replace("\\'", "'")))
            elif boolean:
                tokens.append(("LITERAL", boolean.lower() == "true"))
            elif null:
                tokens.append(("LITERAL", None))
            elif number:
                val = float(number) if "." in number else int(number)
                tokens.append(("LITERAL", val))
            else:
                tokens.append(("FIELD", field))

        return tokens

    def _parse_or_expression(
        self, tokens: list, pos: int, data: Dict[str, Any]
    ) -> tuple:
        result, pos = self._parse_and_expression(tokens, pos, data)

        while pos < len(tokens) and tokens[pos][0] == "OR":
            pos += 1
            right, pos = self._parse_and_expression(tokens, pos, data)
            result = result or right

        return result, pos

    def _parse_and_expression(
        self, tokens: list, pos: int, data: Dict[str, Any]
    ) -> tuple:
        result, pos = self._parse_not_expression(tokens, pos, data)

        while pos < len(tokens) and tokens[pos][0] == "AND":
            pos += 1
            right, pos = self._parse_not_expression(tokens, pos, data)
            result = result and right

        return result, pos

    def _parse_not_expression(
        self, tokens: list, pos: int, data: Dict[str, Any]
    ) -> tuple:
        if pos < len(tokens) and tokens[pos][0] == "NOT":
            pos += 1
            result, pos = self._parse_not_expression(tokens, pos, data)
            return not result, pos
        return self._parse_comparison(tokens, pos, data)

    def _parse_comparison(self, tokens: list, pos: int, data: Dict[str, Any]) -> tuple:
        left, pos = self._parse_atom(tokens, pos, data)

        if pos < len(tokens) and tokens[pos][0] == "OP":
            op = tokens[pos][1]
            pos += 1
            right, pos = self._parse_atom(tokens, pos, data)

            match op:
                case "==":
                    result = left == right
                case "===":
                    result = left == right and type(left) is type(right)
                case "!=":
                    result = left != right
                case "!==":
                    result = left != right or type(left) is not type(right)
                case ">":
                    result = (
                        left > right
                        if (
                            isinstance(left, (int, float))
                            and isinstance(right, (int, float))
                        )
                        else False
                    )
                case "<":
                    result = (
                        left < right
                        if (
                            isinstance(left, (int, float))
                            and isinstance(right, (int, float))
                        )
                        else False
                    )
                case ">=":
                    result = (
                        left >= right
                        if (
                            isinstance(left, (int, float))
                            and isinstance(right, (int, float))
                        )
                        else False
                    )
                case "<=":
                    result = (
                        left <= right
                        if (
                            isinstance(left, (int, float))
                            and isinstance(right, (int, float))
                        )
                        else False
                    )
                case _:
                    result = False

            return result, pos

        # No operator: treat as truthy/falsy.
        return bool(left), pos

    def _parse_atom(self, tokens: list, pos: int, data: Dict[str, Any]) -> tuple:
        if pos >= len(tokens):
            return None, pos

        token_type, token_value = tokens[pos]

        if token_type == "LPAREN":
            pos += 1
            result, pos = self._parse_or_expression(tokens, pos, data)
            if pos < len(tokens) and tokens[pos][0] == "RPAREN":
                pos += 1
            return result, pos

        elif token_type == "LITERAL":
            return token_value, pos + 1

        elif token_type == "FIELD":
            value = self._get_nested_value(data, token_value)
            return value, pos + 1

        return None, pos + 1

    def _get_nested_value(self, data: Dict[str, Any], path: str) -> Any:
        """Get a nested value via dot notation, e.g. 'movie.status'."""
        parts = path.split(".")
        current = data
        for part in parts:
            if isinstance(current, dict):
                current = current.get(part)
            else:
                return None
        return current

    def _fetch_credential(self, credential_id: str) -> Optional[Dict[str, Any]]:
        """Sync wrapper for the async credential client."""
        return _run_sync(self.credential_client.get_credential(credential_id))

    def _fire_prebuilt_request(
        self,
        http_request: Dict[str, Any],
        credential_id: Optional[str],
        auth_config: Optional[Dict[str, Any]],
        polling_config: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Fire an API-prebuilt wire envelope with auth merged at fire time."""
        url = http_request.get("url") or ""
        method = (http_request.get("method") or "POST").upper()
        headers = dict(http_request.get("headers") or {})
        body = http_request.get("body")
        query_params = dict(http_request.get("query_params") or {})

        credentials: Optional[Dict[str, Any]] = None
        if credential_id:
            credentials = _run_sync(
                self.credential_client.get_credential(credential_id)
            )
            if credentials:
                self._merge_auth_into_envelope(
                    headers, query_params, credentials, auth_config
                )
            else:
                logger.warning(f"Failed to fetch credentials for {credential_id}")

        # Credential-stored path params (e.g. Airtable base_id) get substituted into URL.
        if credentials and "{" in url:
            import re

            def _sub(match: "re.Match[str]") -> str:
                param = match.group(1)
                val = credentials.get(param) if credentials else None
                return str(val) if val is not None else match.group(0)

            url = re.sub(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}", _sub, url)

        if method in ("POST", "PUT", "PATCH") and "Content-Type" not in headers:
            headers["Content-Type"] = "application/json"

        request_body_for_debug: Dict[str, Any] = (
            dict(body) if isinstance(body, dict) else {"_body": body}
        )

        result = self._fire_with_retry(
            url=url,
            method=method,
            headers=headers,
            body=body,
            query_params=query_params,
            credential_id=credential_id,
            auth_config=auth_config,
        )

        if polling_config and polling_config.get("enabled"):
            base_url = url.rsplit("/", 1)[0] if url else ""
            result = self._poll_for_completion(
                initial_result=result,
                polling_config=polling_config,
                base_url=base_url,
                headers=headers,
            )

        return result, request_body_for_debug

    def _merge_auth_into_envelope(
        self,
        headers: Dict[str, str],
        query_params: Dict[str, Any],
        credentials: Dict[str, Any],
        auth_config: Optional[Dict[str, Any]],
    ) -> None:
        """Merge credentials into headers/query_params per auth_config.

        Mirrors the API-side auth merging logic; both use the same auth config shape.
        """
        auth_type = (auth_config or {}).get("type", "bearer")
        cfg = (auth_config or {}).get("config", {})

        if auth_type == "custom":
            scheme = cfg.get("scheme")
            basic_auth_fields = cfg.get("basic_auth_fields")
            if scheme == "basic" and basic_auth_fields and len(basic_auth_fields) >= 2:
                import base64

                username = credentials.get(basic_auth_fields[0], "")
                password = credentials.get(basic_auth_fields[1], "")
                if username and password:
                    encoded = base64.b64encode(
                        f"{username}:{password}".encode()
                    ).decode()
                    headers["Authorization"] = f"Basic {encoded}"
                return
            fields_mapping = cfg.get("fields", {})
            if isinstance(fields_mapping, dict):
                for cred_field, param_name in fields_mapping.items():
                    if cred_field in credentials:
                        query_params[param_name] = credentials[cred_field]
            else:
                for cred_field in fields_mapping:
                    if cred_field in credentials:
                        query_params[cred_field] = credentials[cred_field]
            return

        if auth_type == "header":
            api_key = (
                credentials.get("api_key")
                or credentials.get("access_token")
                or credentials.get("token")
            )
            if api_key:
                header_name = (auth_config or {}).get("header", "x-api-key")
                headers[header_name] = api_key
            return

        if auth_type == "custom_header":
            header_name = (auth_config or {}).get("header_name", "x-api-key")
            value_source = (auth_config or {}).get("header_value_source", "api_key")
            if credentials.get(value_source):
                headers[header_name] = credentials[value_source]
            return

        if auth_type == "query_param":
            param_name = (auth_config or {}).get("param_name", "key")
            value_source = (auth_config or {}).get("param_value_source", "api_key")
            if credentials.get(value_source):
                query_params[param_name] = credentials[value_source]
            return

        if auth_type == "basic":
            import base64

            api_key = (
                credentials.get("api_key")
                or credentials.get("access_token")
                or credentials.get("token")
            )
            if api_key:
                encoded = base64.b64encode(f"{api_key}:".encode()).decode()
                headers["Authorization"] = f"Basic {encoded}"
            return

        # bearer (default)
        if "Authorization" not in headers:
            token_field = cfg.get("token_field")
            if token_field and token_field in credentials:
                api_key = credentials.get(token_field)
            else:
                api_key = (
                    credentials.get("api_key")
                    or credentials.get("access_token")
                    or credentials.get("token")
                    or credentials.get("secret")
                )
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"

    def _fire_with_retry(
        self,
        url: str,
        method: str,
        headers: Dict[str, str],
        body: Any,
        query_params: Dict[str, Any],
        credential_id: Optional[str],
        auth_config: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Fire with retries on 408/429/5xx + network errors. 401 triggers one credential refresh.

        Binary responses are streamed to disk and returned as _binary_response. JSON arrays
        wrap as {"data": [...]} so downstream JSONPath sees a dict.
        """
        auth_retried = False
        # httpx wants a sequence of tuples for duplicate-key params; our envelope is a dict.
        params_seq: Optional[List[Tuple[str, Any]]] = (
            [(k, v) for k, v in query_params.items()] if query_params else None
        )

        for attempt in range(RETRY_MAX_ATTEMPTS + 1):
            try:
                request_start = time.time()
                logger.debug(
                    f"→ {method} {url}" + (f" (retry {attempt})" if attempt > 0 else "")
                )

                use_form_encoding = (
                    headers.get("Content-Type") == "application/x-www-form-urlencoded"
                )
                request_kwargs: Dict[str, Any] = {"headers": headers}
                if params_seq:
                    request_kwargs["params"] = tuple(params_seq)
                if method in ("POST", "PUT", "PATCH") and body is not None:
                    if use_form_encoding:
                        request_kwargs["data"] = body
                    else:
                        request_kwargs["json"] = body

                response = self.http_client.request(method, url, **request_kwargs)

                if response.status_code in RETRYABLE_STATUS_CODES:
                    delay = self._calculate_retry_delay(response, attempt)
                    logger.warning(
                        f" {method} {url} → {response.status_code} "
                        f"retrying in {delay:.1f}s... body: {response.text[:500]}"
                    )
                    time.sleep(delay)
                    continue

                if response.status_code == 401 and credential_id and not auth_retried:
                    auth_retried = True
                    logger.warning(
                        "401 Unauthorized - refreshing credential and retrying..."
                    )
                    try:
                        fresh_creds = _run_sync(
                            self.credential_client.get_credential(credential_id)
                        )
                        if fresh_creds:
                            self._merge_auth_into_envelope(
                                headers, query_params, fresh_creds, auth_config
                            )
                            params_seq = (
                                [(k, v) for k, v in query_params.items()]
                                if query_params
                                else None
                            )
                            logger.debug("Credential refreshed, retrying request")
                            continue
                    except Exception as e:
                        logger.warning(f"Credential refresh failed: {e}")

                if response.status_code >= 400:
                    logger.error(f" Error response: status {response.status_code}")
                    response.raise_for_status()

                content_type = response.headers.get("content-type", "").lower()

                if any(
                    mime in content_type
                    for mime in ["audio/", "video/", "application/octet-stream"]
                ):
                    import tempfile

                    ext_map = {
                        "audio/mpeg": ".mp3",
                        "audio/mp3": ".mp3",
                        "audio/wav": ".wav",
                        "audio/x-wav": ".wav",
                        "audio/ogg": ".ogg",
                        "audio/opus": ".opus",
                        "audio/aac": ".aac",
                        "audio/flac": ".flac",
                        "video/mp4": ".mp4",
                    }
                    ext = next(
                        (v for k, v in ext_map.items() if k in content_type), ".bin"
                    )
                    temp_fd, temp_path = tempfile.mkstemp(suffix=ext)
                    file_size = 0
                    with os.fdopen(temp_fd, "wb") as f:
                        for chunk in response.iter_bytes(
                            chunk_size=settings.HTTP_CHUNK_SIZE
                        ):
                            f.write(chunk)
                            file_size += len(chunk)
                    duration_ms = int((time.time() - request_start) * 1000)
                    logger.debug(
                        f"← {response.status_code} OK (binary: {content_type}, "
                        f"{file_size} bytes → {temp_path}, {duration_ms}ms)",
                        extra={
                            "duration_ms": duration_ms,
                            "status_code": response.status_code,
                        },
                    )
                    return {
                        "_binary_response": True,
                        "_binary_path": temp_path,
                        "_content_type": content_type,
                        "_file_size": file_size,
                    }

                try:
                    result = response.json()
                    if isinstance(result, list):
                        result = {"data": result}
                except ValueError:
                    result = {"response": response.text}

                duration_ms = int((time.time() - request_start) * 1000)
                logger.debug(
                    f"← {response.status_code} OK ({duration_ms}ms)",
                    extra={
                        "duration_ms": duration_ms,
                        "status_code": response.status_code,
                    },
                )
                return result

            except (httpx.ConnectError, httpx.TimeoutException) as e:
                if attempt < RETRY_MAX_ATTEMPTS:
                    delay = self._calculate_retry_delay(None, attempt)
                    logger.warning(
                        f" Connection error: {e} - retrying in {delay:.1f}s..."
                    )
                    time.sleep(delay)
                    continue
                raise
            except httpx.HTTPStatusError:
                raise

        # Reaching here means every attempt returned a retryable status.
        raise RuntimeError(f"Request failed after {RETRY_MAX_ATTEMPTS} retries")

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

        # 25% jitter to spread retries across clients (thundering herd).
        jitter = delay * 0.25 * random.random()
        delay = delay + jitter

        return min(delay, RETRY_MAX_DELAY)

    def _poll_for_completion(
        self,
        initial_result: Dict[str, Any],
        polling_config: Dict[str, Any],
        base_url: str,
        headers: Dict[str, str],
    ) -> Dict[str, Any]:
        """Poll for async-API completion using a generation_id from the initial response."""
        import time

        # Missing generation_id at this point is a misconfigured adapter - fail fast.
        # Returning the initial POST would mark the step COMPLETED with empty content.
        generation_id_path = polling_config.get("generation_id_path", "$.generationId")
        try:
            jsonpath_expr = jsonpath_parse(generation_id_path)
        except Exception as e:
            logger.error(
                f"Polling config has invalid generation_id_path "
                f"{generation_id_path!r}: {e}"
            )
            raise RuntimeError(
                f"Invalid polling generation_id_path {generation_id_path!r}: {e}"
            ) from e

        matches = jsonpath_expr.find(initial_result)
        if not matches:
            logger.error(
                f"Polling enabled but no generation_id found at "
                f"{generation_id_path} in initial response - adapter polling "
                f"config does not match provider response shape"
            )
            raise RuntimeError(
                f"Polling enabled but generation_id missing at {generation_id_path}"
            )
        generation_id = matches[0].value

        logger.debug(f"→ Polling for completion (generation: {generation_id})")

        status_endpoint = polling_config.get(
            "status_endpoint", "/generations/{generationId}"
        )
        status_url = base_url + status_endpoint.format(generationId=generation_id)

        interval_ms = polling_config.get("interval_ms", 2000)
        max_attempts = polling_config.get("max_attempts", 60)
        timeout_seconds = polling_config.get("timeout_seconds", 120)
        complete_when = polling_config.get("complete_when", "COMPLETE")
        status_path = polling_config.get("status_path", "$.status")
        result_path = polling_config.get("result_path")

        start_time = time.time()
        attempt = 0

        while attempt < max_attempts:
            elapsed = time.time() - start_time
            if elapsed > timeout_seconds:
                raise TimeoutError(f"Polling timed out after {timeout_seconds}s")

            if attempt > 0:
                time.sleep(interval_ms / 1000)

            attempt += 1

            try:
                response = self.http_client.get(status_url, headers=headers)
                response.raise_for_status()
                poll_result = response.json()
            except Exception as e:
                logger.warning(f" Poll attempt {attempt} failed: {e}")
                continue

            try:
                jsonpath_expr = jsonpath_parse(status_path)
                matches = jsonpath_expr.find(poll_result)
                status = matches[0].value if matches else None
            except (ValueError, KeyError, IndexError, TypeError):
                status = None

            logger.debug(f"→ Poll {attempt}/{max_attempts}: status={status}")

            if status == complete_when:
                logger.debug(
                    f"✓ Generation complete after {attempt} polls ({elapsed:.1f}s)"
                )

                if result_path:
                    try:
                        jsonpath_expr = jsonpath_parse(result_path)
                        matches = jsonpath_expr.find(poll_result)
                        if matches:
                            extracted = matches[0].value
                            if isinstance(extracted, list):
                                return {
                                    "generated_images": extracted,
                                    "generation_id": generation_id,
                                    "poll_attempts": attempt,
                                    "elapsed_seconds": elapsed,
                                }
                            return extracted
                    except Exception as e:
                        logger.warning(f" Failed to extract result: {e}")

                return poll_result

            elif status == "FAILED":
                raise RuntimeError(f"Generation failed: {poll_result}")

        raise TimeoutError(f"Polling exceeded max attempts ({max_attempts})")

    def _generate_thumbnail(
        self,
        image_path: Path,
        output_dir: Path,
        size: Tuple[int, int] = (settings.THUMBNAIL_WIDTH, settings.THUMBNAIL_HEIGHT),
    ) -> Optional[Path]:
        """JPEG thumbnail saved alongside original with -thumbnail.jpg suffix."""
        if not PIL_AVAILABLE:
            logger.debug("PIL not available, skipping thumbnail generation")
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
                img.save(
                    thumbnail_path, "JPEG", quality=settings.THUMBNAIL_JPEG_QUALITY
                )

            logger.debug(f"  ✓ Generated thumbnail: {thumbnail_filename}")
            return thumbnail_path

        except Exception as e:
            logger.debug(f"  ⚠ Failed to generate thumbnail for {image_path.name}: {e}")
            return None

    def _is_image_file(self, filename: str, content_type: str) -> bool:
        if content_type and any(
            mime in content_type.lower() for mime in IMAGE_MIME_TYPES
        ):
            return True
        ext = Path(filename).suffix.lower()
        return ext in IMAGE_EXTENSIONS

    def _post_process_result(
        self,
        result: Dict[str, Any],
        post_processing_config: Dict[str, Any],
        org_settings: Optional[Dict[str, Any]] = None,
        iteration_index: Optional[int] = None,
        job_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Post-process: add_fields, save_binary, download_files, thumbnails."""
        org_settings = org_settings or {}
        if not post_processing_config:
            return result

        add_fields_config = post_processing_config.get("add_fields")
        if add_fields_config:
            result = self._add_computed_fields(result, add_fields_config)

        save_binary_config = post_processing_config.get("save_binary")
        if (
            save_binary_config
            and isinstance(result, dict)
            and result.get("_binary_response")
        ):
            result = self._save_binary_result(
                result=result,
                config=save_binary_config,
                iteration_index=iteration_index,
                job_id=job_id,
            )
            return result

        download_config = post_processing_config.get("download_files")
        if not download_config:
            return result

        source_path = download_config.get("source_path")
        if not source_path:
            logger.warning("download_files config missing source_path")
            return result

        try:
            jsonpath_expr = jsonpath_parse(source_path)
            matches = jsonpath_expr.find(result)
            urls = [match.value for match in matches if match.value]
        except Exception as e:
            logger.warning(f" Failed to parse JSONPath '{source_path}': {e}")
            return result

        if not urls:
            logger.debug(f"→ No URLs found at {source_path}")
            return result

        logger.debug(f"→ Found {len(urls)} file(s) to download")

        filename_pattern = download_config.get(
            "filename_pattern", "{uuid}_{index}.bin"
        )
        timeout_seconds = download_config.get("timeout_seconds", 60)
        max_file_size_mb = download_config.get("max_file_size_mb", FILE_DOWNLOAD_MAX_MB)
        max_file_size_bytes = max_file_size_mb * 1024 * 1024

        import tempfile
        iter_suffix = f"_{iteration_index}" if iteration_index is not None else ""
        temp_dir = Path(tempfile.mkdtemp(prefix=f"studio_dl{iter_suffix}_"))
        temp_dir.mkdir(parents=True, exist_ok=True)

        downloaded_files = []

        try:
            for index, url in enumerate(urls):
                try:
                    logger.debug(
                        f"→ Downloading file {index + 1}/{len(urls)}: {url[:80]}..."
                    )

                    file_uuid = str(uuid.uuid4())[:8]
                    filename = filename_pattern.format(
                        index=index, uuid=file_uuid
                    )

                    temp_file = temp_dir / f"_partial_{filename}"
                    content_type = ""
                    downloaded_size = 0
                    size_exceeded = False
                    sha256 = hashlib.sha256()

                    with self.http_client.stream(
                        "GET", url, timeout=timeout_seconds, follow_redirects=True
                    ) as response:
                        response.raise_for_status()
                        content_type = response.headers.get("content-type", "")

                        with open(temp_file, "wb") as f:
                            for chunk in response.iter_bytes(
                                chunk_size=settings.HTTP_CHUNK_SIZE
                            ):
                                downloaded_size += len(chunk)
                                if downloaded_size > max_file_size_bytes:
                                    size_exceeded = True
                                    break
                                f.write(chunk)
                                sha256.update(chunk)

                    if size_exceeded:
                        temp_file.unlink(missing_ok=True)
                        logger.warning(
                            f"File too large (>{max_file_size_bytes} bytes), skipping"
                        )
                        continue

                    if "." not in filename:
                        if "png" in content_type:
                            filename += ".png"
                        elif "jpeg" in content_type or "jpg" in content_type:
                            filename += ".jpg"
                        elif "webp" in content_type:
                            filename += ".webp"
                        else:
                            url_path = url.split("?")[0]
                            if "." in url_path.split("/")[-1]:
                                ext = "." + url_path.split(".")[-1]
                                filename += ext
                            else:
                                filename += ".bin"

                    final_temp = temp_dir / filename
                    temp_file.rename(final_temp)
                    temp_file = final_temp

                    checksum = sha256.hexdigest()

                    virtual_path = self._upload_client.upload(
                        str(temp_file), filename=filename, job_id=job_id,
                    )

                    file_info = {
                        "filename": filename,
                        "file_size": downloaded_size,
                        "checksum": checksum,
                        "virtual_path": virtual_path,
                        "source_url": url,
                        "index": index,
                    }

                    downloaded_files.append(file_info)

                    logger.debug(f"  ✓ Saved: {filename} ({downloaded_size} bytes)")

                except Exception as e:
                    logger.warning(f"  ✗ Failed to download {url}: {e}")
                    continue

        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

        # Partial results break downstream steps - fail loud.
        failed_count = len(urls) - len(downloaded_files)
        if failed_count > 0:
            raise RuntimeError(f"{failed_count} of {len(urls)} file downloads failed")

        result["downloaded_files"] = downloaded_files
        logger.debug(f"✓ Downloaded {len(downloaded_files)} file(s)")

        return result

    def _add_computed_fields(
        self,
        result: Dict[str, Any],
        add_fields_config: Dict[str, str],
    ) -> Dict[str, Any]:
        """Add fields from {{ field_path }} templates; supports dot notation."""
        import re

        for field_name, template in add_fields_config.items():
            try:

                def replace_template(match):
                    field_path = match.group(1).strip()
                    value = result
                    for part in field_path.split("."):
                        if isinstance(value, dict):
                            value = value.get(part)
                        else:
                            return match.group(0)
                    return str(value) if value is not None else ""

                computed_value = re.sub(
                    r"\{\{\s*([^}]+)\s*\}\}", replace_template, template
                )
                result[field_name] = computed_value
                logger.debug(f"→ Added field: {field_name}")
            except Exception as e:
                logger.warning(f" Failed to compute field '{field_name}': {e}")

        return result

    def _save_binary_result(
        self,
        result: Dict[str, Any],
        config: Dict[str, Any],
        iteration_index: Optional[int] = None,
        job_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        temp_path = result.get("_binary_path")
        if not temp_path or not os.path.exists(temp_path):
            logger.warning("save_binary: no temp file found")
            return result

        try:
            filename_pattern = config.get("filename_pattern", "{uuid}.bin")
            file_uuid = uuid.uuid4().hex[:8]
            filename = filename_pattern.format(uuid=file_uuid)

            virtual_path = self._upload_client.upload(temp_path, filename=filename, job_id=job_id)
            file_size = os.path.getsize(temp_path)

            logger.debug(f"→ Binary saved: {filename} ({file_size} bytes)")

            display_name = config.get("display_name", filename)

            file_metadata = {
                "filename": filename,
                "virtual_path": virtual_path,
                "file_size": file_size,
                "display_name": display_name,
                "index": 0,
            }

            if "_content_type" in result:
                file_metadata["mime_type"] = result["_content_type"]

            if iteration_index is not None:
                file_metadata["iteration_index"] = iteration_index

            file_key = config.get("file_key", "file")
            new_result = {
                file_key: filename,
                "storage_url": virtual_path,
                "downloaded_files": [file_metadata],
            }

            if config.get("compute_duration"):
                duration = self._get_audio_duration(str(temp_path))
                if duration is not None:
                    new_result["duration_seconds"] = round(duration, 3)
                    file_metadata["display_name"] = f"{display_name} ({duration:.1f}s)"
                    logger.debug(f"→ Audio duration: {duration:.2f}s")
                else:
                    logger.warning(
                        f"compute_duration requested but duration probe failed for {temp_path}. "
                        f"duration_seconds will be MISSING from result - downstream auto_duration will be disabled."
                    )

            return new_result

        except Exception as e:
            logger.error(f"save_binary failed: {e}")
            if temp_path and os.path.exists(temp_path):
                os.unlink(temp_path)
            raise

    def _get_audio_duration(self, file_path: str) -> Optional[float]:
        """Audio duration via mutagen (pure Python), falling back to ffprobe."""
        try:
            from mutagen import File as MutagenFile

            audio = MutagenFile(file_path)
            if audio is not None and audio.info is not None:
                duration = audio.info.length
                if duration and duration > 0:
                    logger.debug(f"Audio duration via mutagen: {duration:.3f}s")
                    return float(duration)
            logger.warning(f"mutagen returned no duration info for {file_path}")
        except ImportError:
            logger.warning(
                "mutagen not installed - cannot probe audio duration without ffprobe"
            )
        except Exception as e:
            logger.warning(f"mutagen failed for {file_path}: {e}")

        import subprocess

        try:
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "quiet",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    file_path,
                ],
                capture_output=True,
                text=True,
                timeout=FFPROBE_TIMEOUT_S,
            )
            if result.returncode == 0 and result.stdout.strip():
                logger.debug(f"Audio duration via ffprobe: {result.stdout.strip()}s")
                return float(result.stdout.strip())
        except FileNotFoundError:
            logger.warning("ffprobe not available - no fallback for audio duration")
        except Exception as e:
            logger.warning(f"ffprobe failed for {file_path}: {e}")

        # Last-resort estimate: ~128kbps MP3 = 16KB/s.
        try:
            file_size = os.path.getsize(file_path)
            if file_size > 0:
                estimated = file_size / 16000
                logger.warning(
                    f"All duration probes failed for {file_path}. "
                    f"Using file-size estimate: {estimated:.1f}s (from {file_size} bytes @ ~128kbps)"
                )
                return estimated
        except OSError:
            pass

        logger.error(
            f"Cannot determine duration for {file_path} - no probes available and file size unknown"
        )
        return None
