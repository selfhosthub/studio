# workers/shared/utils/error_codes.py

"""Bounded error codes workers report on failure.

The API owns the code -> user-message mapping (api worker_error_codes). Workers
only emit a code; free-text detail goes to worker logs, never to the client.
Keep these strings in sync with the API's WorkerErrorCode enum.
"""

from __future__ import annotations

import subprocess

import httpx

INTERNAL = "INTERNAL"
TIMEOUT = "TIMEOUT"
PROVIDER_ERROR = "PROVIDER_ERROR"
VALIDATION = "VALIDATION"
RESOURCE_UNAVAILABLE = "RESOURCE_UNAVAILABLE"


def classify_error_code(exc: BaseException) -> str:
    """Map an exception to a bounded worker error code; default INTERNAL."""
    if isinstance(exc, (TimeoutError, httpx.TimeoutException)):
        return TIMEOUT
    if isinstance(exc, httpx.HTTPStatusError):
        return PROVIDER_ERROR
    if isinstance(exc, (httpx.HTTPError, ConnectionError, subprocess.CalledProcessError)):
        return RESOURCE_UNAVAILABLE
    if isinstance(exc, (ValueError, KeyError, TypeError)):
        return VALIDATION
    return INTERNAL
