# api/app/application/services/result_processing/worker_error_codes.py

"""Server-authored client messages for worker-reported failures.

Workers emit a bounded error code; the client-visible message comes from this
table, never from worker exception text. A provider failure adds the HTTP status
and the provider's own message, which the worker scrubs of sent credentials and
this module scrubs again of token-shaped strings. Raw worker detail stays in
server logs.
"""

from __future__ import annotations

import ipaddress
import re
from enum import Enum


class WorkerErrorCode(str, Enum):
    INTERNAL = "INTERNAL"
    TIMEOUT = "TIMEOUT"
    PROVIDER_ERROR = "PROVIDER_ERROR"
    VALIDATION = "VALIDATION"
    RESOURCE_UNAVAILABLE = "RESOURCE_UNAVAILABLE"


_MESSAGES: dict[WorkerErrorCode, str] = {
    WorkerErrorCode.INTERNAL: "The node failed while processing.",
    WorkerErrorCode.TIMEOUT: "The node timed out.",
    WorkerErrorCode.PROVIDER_ERROR: "The provider returned an error.",
    WorkerErrorCode.VALIDATION: "The node input was invalid.",
    WorkerErrorCode.RESOURCE_UNAVAILABLE: "A required resource was unavailable.",
}


class ConnectCause(str, Enum):
    TLS_HANDSHAKE = "tls_handshake"
    CONNECT_TIMEOUT = "connect_timeout"
    DNS = "dns"
    CONNECTION_REFUSED = "connection_refused"
    TLS_ERROR = "tls_error"
    CONNECT_ERROR = "connect_error"


_CAUSE_LABELS: dict[ConnectCause, str] = {
    ConnectCause.TLS_HANDSHAKE: "TLS handshake",
    ConnectCause.CONNECT_TIMEOUT: "TCP connect",
    ConnectCause.DNS: "DNS lookup",
    ConnectCause.CONNECTION_REFUSED: "connection refused",
    ConnectCause.TLS_ERROR: "TLS error",
    ConnectCause.CONNECT_ERROR: "connection error",
}

_CONNECT_PHASE_LEADS: dict[WorkerErrorCode, str] = {
    WorkerErrorCode.TIMEOUT: "The node timed out connecting",
    WorkerErrorCode.RESOURCE_UNAVAILABLE: "The node could not connect",
}

_HOSTNAME = re.compile(r"(?=.{1,253}$)[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*")


def _display_host(host: str | None) -> str | None:
    """The host as shown to clients, or None when it is not a plain hostname or IP."""
    if not host:
        return None
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return host if _HOSTNAME.fullmatch(host) else None
    return f"[{ip}]" if ip.version == 6 else str(ip)


_DETAIL_MAX_CHARS = 300
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")
_SECRET_SHAPES = (
    re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"),
    re.compile(r"(?i)\bbearer\s+\S+"),
    re.compile(r"\b(?=[A-Za-z0-9_\-]*\d)(?=[A-Za-z0-9_\-]*[A-Za-z])[A-Za-z0-9_\-]{24,}"),
)


def _display_detail(detail: str | None) -> str | None:
    """The provider's message as shown to clients: one line, token-shaped strings masked, capped."""
    if not detail:
        return None
    text = " ".join(_CONTROL_CHARS.sub(" ", detail).split())
    for shape in _SECRET_SHAPES:
        text = shape.sub("[REDACTED]", text)
    text = text[:_DETAIL_MAX_CHARS].rstrip()
    return text or None


def _provider_message(status: int | None, detail: str | None) -> str:
    """The provider-error sentence with the HTTP status and provider message when present."""
    shown_status = status if status is not None and 100 <= status <= 599 else None
    shown_detail = _display_detail(detail)
    if shown_status is None and shown_detail is None:
        return _MESSAGES[WorkerErrorCode.PROVIDER_ERROR]
    lead = "The provider returned an error"
    if shown_status is not None:
        lead += f" (HTTP {shown_status})"
    if shown_detail is None:
        return f"{lead}."
    end = "" if shown_detail[-1] in ".!?" else "."
    return f"{lead}: {shown_detail}{end}"


def client_message_for_worker_error(
    code: str | None,
    cause: str | None = None,
    host: str | None = None,
    status: int | None = None,
    detail: str | None = None,
) -> str:
    """Map a worker error code, plus connect-phase cause and host or provider status and message, to a safe client message."""
    try:
        resolved = WorkerErrorCode(code) if code else WorkerErrorCode.INTERNAL
    except ValueError:
        resolved = WorkerErrorCode.INTERNAL
    if resolved == WorkerErrorCode.PROVIDER_ERROR:
        return _provider_message(status, detail)
    lead = _CONNECT_PHASE_LEADS.get(resolved)
    try:
        label = _CAUSE_LABELS[ConnectCause(cause)] if cause else None
    except ValueError:
        label = None
    if lead is None or label is None:
        return _MESSAGES[resolved]
    shown = _display_host(host)
    target = f" to {shown}" if shown else ""
    return f"{lead}{target} ({label})."
