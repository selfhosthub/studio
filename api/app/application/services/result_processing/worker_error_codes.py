# api/app/application/services/result_processing/worker_error_codes.py

"""Server-authored client messages for worker-reported failures.

Workers emit a bounded error code; the client-visible message comes only from
this table, never from worker free-text, so a worker cannot inject job secrets
into a user-facing field. Raw worker detail stays in server logs.
"""

from __future__ import annotations

from enum import Enum


class WorkerErrorCode(str, Enum):
    INTERNAL = "INTERNAL"
    TIMEOUT = "TIMEOUT"
    PROVIDER_ERROR = "PROVIDER_ERROR"
    VALIDATION = "VALIDATION"
    RESOURCE_UNAVAILABLE = "RESOURCE_UNAVAILABLE"


_MESSAGES: dict[WorkerErrorCode, str] = {
    WorkerErrorCode.INTERNAL: "The step failed while processing.",
    WorkerErrorCode.TIMEOUT: "The step timed out.",
    WorkerErrorCode.PROVIDER_ERROR: "The provider returned an error.",
    WorkerErrorCode.VALIDATION: "The step input was invalid.",
    WorkerErrorCode.RESOURCE_UNAVAILABLE: "A required resource was unavailable.",
}


def client_message_for_worker_error(code: str | None) -> str:
    """Map a worker error code to a safe client message; unknown/missing -> INTERNAL."""
    try:
        resolved = WorkerErrorCode(code) if code else WorkerErrorCode.INTERNAL
    except ValueError:
        resolved = WorkerErrorCode.INTERNAL
    return _MESSAGES[resolved]
