# workers/studio_workers/utils/error_codes.py

"""Bounded error codes workers report on failure.

The API owns the code -> user-message mapping (api worker_error_codes). Workers
emit a code plus structured detail (connect cause and host, provider HTTP status
and the provider's scrubbed message); exception text goes to worker logs only.
Keep these strings in sync with the API's WorkerErrorCode enum.
"""

from __future__ import annotations

import json
import subprocess
from typing import TypedDict

import httpx

from studio_workers.contracts.redaction import is_sensitive_key

INTERNAL = "INTERNAL"
TIMEOUT = "TIMEOUT"
PROVIDER_ERROR = "PROVIDER_ERROR"
VALIDATION = "VALIDATION"
RESOURCE_UNAVAILABLE = "RESOURCE_UNAVAILABLE"


class ResourceUnavailableError(Exception):
    """A resource the job needs, such as a model file, is missing on this worker."""


def classify_error_code(exc: BaseException) -> str:
    """Map an exception to a bounded worker error code; default INTERNAL."""
    if isinstance(exc, (TimeoutError, httpx.TimeoutException)):
        return TIMEOUT
    if isinstance(exc, httpx.HTTPStatusError):
        return PROVIDER_ERROR
    if isinstance(
        exc,
        (httpx.HTTPError, ConnectionError, subprocess.CalledProcessError, ResourceUnavailableError),
    ):
        return RESOURCE_UNAVAILABLE
    if isinstance(exc, (ValueError, KeyError, TypeError)):
        return VALIDATION
    return INTERNAL


class ConnectFailureDetail(TypedDict, total=False):
    error_cause: str
    error_host: str


_DNS_MARKERS = ("name or service not known", "name resolution", "nodename nor servname", "getaddrinfo")


def connect_failure_detail(exc: BaseException) -> ConnectFailureDetail:
    """error_cause and error_host for a connect-phase httpx failure; empty for anything else."""
    if not isinstance(exc, (httpx.ConnectTimeout, httpx.ConnectError)):
        return {}
    text = str(exc).lower()
    if isinstance(exc, httpx.ConnectTimeout):
        cause = "tls_handshake" if "handshake" in text else "connect_timeout"
    elif "ssl" in text or "certificate" in text:
        cause = "tls_error"
    elif any(marker in text for marker in _DNS_MARKERS):
        cause = "dns"
    elif "refused" in text:
        cause = "connection_refused"
    else:
        cause = "connect_error"
    detail = ConnectFailureDetail(error_cause=cause)
    try:
        detail["error_host"] = exc.request.url.host
    except RuntimeError:
        pass
    return detail


class ProviderErrorDetail(TypedDict, total=False):
    error_status: int
    error_detail: str


# Where common provider APIs put their human-readable error message.
_MESSAGE_PATHS: tuple[tuple[str | int, ...], ...] = (
    ("error", "message"),
    ("error",),
    ("message",),
    ("detail",),
    ("error_description",),
    ("errors", 0, "message"),
)
_DETAIL_MAX_CHARS = 300
_MIN_SECRET_CHARS = 8


def _body_message(response: httpx.Response) -> str | None:
    """The provider's own error message from a JSON error body, or None."""
    try:
        body = response.json()
    except (ValueError, httpx.ResponseNotRead):
        return None
    for path in _MESSAGE_PATHS:
        node = body
        for part in path:
            if isinstance(part, int):
                node = node[part] if isinstance(node, list) and len(node) > part else None
            else:
                node = node.get(part) if isinstance(node, dict) else None
        if isinstance(node, str) and node.strip():
            return node
    return None


def _sensitive_body_values(node: object) -> list[str]:
    """String values under credential-named keys anywhere in a JSON body."""
    if isinstance(node, dict):
        found: list[str] = []
        for key, value in node.items():
            if isinstance(value, str) and is_sensitive_key(str(key)):
                found.append(value)
            else:
                found += _sensitive_body_values(value)
        return found
    if isinstance(node, list):
        return [v for item in node for v in _sensitive_body_values(item)]
    return []


def _scrub_sent_values(message: str, request: httpx.Request) -> str:
    """Mask every credential header, query and body value the request sent, so an echoed key never leaves the worker."""
    items = [*request.headers.multi_items(), *request.url.params.multi_items()]
    sent = [value for name, value in items if is_sensitive_key(name)]
    try:
        sent += _sensitive_body_values(json.loads(request.content or b"null"))
    except (ValueError, httpx.RequestNotRead):
        pass
    pieces = {piece for value in sent for piece in [value, *value.split()]}
    for piece in sorted(pieces, key=len, reverse=True):
        if len(piece) >= _MIN_SECRET_CHARS:
            message = message.replace(piece, "[REDACTED]")
    return message


def provider_error_detail(exc: BaseException) -> ProviderErrorDetail:
    """error_status and the provider's scrubbed error message for an HTTP status failure; empty for anything else."""
    if not isinstance(exc, httpx.HTTPStatusError):
        return {}
    detail = ProviderErrorDetail(error_status=exc.response.status_code)
    message = _body_message(exc.response)
    if message:
        scrubbed = " ".join(_scrub_sent_values(message, exc.request).split())
        detail["error_detail"] = scrubbed[:_DETAIL_MAX_CHARS]
    return detail


class FailureDetail(ConnectFailureDetail, ProviderErrorDetail, total=False):
    pass


def failure_detail(exc: BaseException) -> FailureDetail:
    """Every structured field a failed job reports alongside its error code."""
    return FailureDetail(**connect_failure_detail(exc), **provider_error_detail(exc))
