# api/app/infrastructure/logging/filters.py

"""Log filters: token redaction, sensitive-data scrubbing, and noise suppression."""

import logging
import re
from typing import Any

from contracts.redaction import (
    REDACTED_PLACEHOLDER,
    is_pii_key,
    is_sensitive_key,
    redact_sensitive_data,
)

from app.config.settings import settings


class TokenRedactionFilter(logging.Filter):
    """Redact token strings (JWTs, ?token=, Authorization headers) from message text."""

    PATTERNS = [
        (r"([?&]token=)[^\s&]+", r"\1[REDACTED]"),
        (r"(Authorization:\s*Bearer\s+)[^\s]+", r"\1[REDACTED]"),
        (r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", r"[REDACTED_JWT]"),
    ]

    def filter(self, record: logging.LogRecord) -> bool:
        if hasattr(record, "msg"):
            message = str(record.msg)
            for pattern, replacement in self.PATTERNS:
                message = re.sub(pattern, replacement, message)
            record.msg = message

        if hasattr(record, "args") and record.args:
            cleaned_args: list[Any] = []
            for arg in record.args:
                if isinstance(arg, str):
                    cleaned_arg = arg
                    for pattern, replacement in self.PATTERNS:
                        cleaned_arg = re.sub(pattern, replacement, cleaned_arg)
                    cleaned_args.append(cleaned_arg)
                else:
                    cleaned_args.append(arg)
            record.args = tuple(cleaned_args)

        return True


# Reserved LogRecord attributes set by the logging machinery - never scrub these.
# Anything else in record.__dict__ is an `extra={}` key and is a redaction candidate.
_BUILTIN_LOGRECORD_ATTRS = frozenset(
    {
        "name",
        "msg",
        "args",
        "levelname",
        "levelno",
        "pathname",
        "filename",
        "module",
        "exc_info",
        "exc_text",
        "stack_info",
        "lineno",
        "funcName",
        "created",
        "msecs",
        "relativeCreated",
        "thread",
        "threadName",
        "processName",
        "process",
        "message",
        "asctime",
        "taskName",
    }
)


class SensitiveDataFilter(logging.Filter):
    """Scrub structured log fields whose keys match SENSITIVE_KEYS or PII_KEYS.

    Complements TokenRedactionFilter, which only scrubs the final message string -
    this filter covers `extra={...}` and dict args that never get string-formatted.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if record.args and isinstance(record.args, tuple):
            record.args = tuple(
                redact_sensitive_data(arg) if isinstance(arg, (dict, list)) else arg
                for arg in record.args
            )
        elif isinstance(record.args, dict):
            record.args = redact_sensitive_data(record.args)

        # Snapshot keys: we mutate __dict__ in place.
        for attr_name in list(record.__dict__.keys()):
            if attr_name in _BUILTIN_LOGRECORD_ATTRS or attr_name.startswith("_"):
                continue
            value = record.__dict__[attr_name]
            if is_sensitive_key(attr_name) or is_pii_key(attr_name):
                record.__dict__[attr_name] = REDACTED_PLACEHOLDER
            elif isinstance(value, (dict, list)):
                record.__dict__[attr_name] = redact_sensitive_data(value)

        return True


class HealthCheckFilter(logging.Filter):
    """Suppress the exact `GET /health` ping (not paths that merely contain /health)."""

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        if "GET /health HTTP" in message:
            return False
        return True


class WebSocketFilter(logging.Filter):
    """Suppress WebSocket connection chatter when SUPPRESS_WEBSOCKET_LOGS is set."""

    def __init__(self) -> None:
        super().__init__()
        self.enabled = settings.SUPPRESS_WEBSOCKET_LOGS

    def filter(self, record: logging.LogRecord) -> bool:
        if not self.enabled:
            return True

        if hasattr(record, "msg"):
            message = str(record.msg)
            if (
                "WebSocket" in message
                or "connection open" in message
                or "connection close" in message
            ):
                return False

        return True


class AccessLogBlocker(logging.Filter):
    """Block every access log record (used when ENABLE_ACCESS_LOGS=false)."""

    def filter(self, record: logging.LogRecord) -> bool:
        return False


class WorkerPollingFilter(logging.Filter):
    """Drop heartbeats, empty job claims, and the matching INFO chatter."""

    def __init__(self) -> None:
        self.enabled = settings.SUPPRESS_WORKER_POLLING_LOGS

    def filter(self, record: logging.LogRecord) -> bool:
        if not self.enabled:
            return True

        # Uvicorn access log: msg = '%s - "%s %s HTTP/%s" %d', args = (addr, method, path, ver, status).
        message = record.getMessage()
        status_code = None

        raw_status = getattr(record, "status_code", None)
        if raw_status is not None:
            try:
                status_code = int(raw_status)
            except (ValueError, TypeError):
                pass

        # Fallback: uvicorn's raw access-log args put the status code last.
        if status_code is None and isinstance(record.args, tuple) and record.args:
            try:
                status_code = int(record.args[-1])  # type: ignore[arg-type]
            except (ValueError, TypeError):
                pass

        if "/heartbeat" in message:
            return False

        if "/jobs/claim" in message and status_code == 204:
            return False

        if "claiming job from queue" in message and record.levelno <= logging.INFO:
            return False

        return True


class AccessLogStatusFilter(logging.Filter):
    """Drop successful (2xx) access logs; keep 4xx/5xx and unknown-status records."""

    def __init__(self) -> None:
        super().__init__()
        self.enabled = settings.SUPPRESS_ACCESS_LOG_SUCCESS

    def filter(self, record: logging.LogRecord) -> bool:
        if not self.enabled:
            return True

        status_code = None
        raw_status = getattr(record, "status_code", None)
        if raw_status is not None:
            try:
                status_code = int(raw_status)
            except (ValueError, TypeError):
                pass

        if status_code is None and isinstance(record.args, tuple) and record.args:
            try:
                status_code = int(record.args[-1])  # type: ignore[arg-type]
            except (ValueError, TypeError):
                pass

        if status_code is not None and 200 <= status_code < 300:
            return False

        return True


class SuppressASGITracebackFilter(logging.Filter):
    """Suppress uvicorn's full-traceback re-log - the global handler already logs a concise line."""

    def filter(self, record: logging.LogRecord) -> bool:
        return "Exception in ASGI application" not in record.getMessage()
