# workers/shared/utils/logging_config.py

"""
Logging configuration for studio workers.

Environment Variables:
    LOG_LEVEL: Set log level (DEBUG, INFO, WARNING, ERROR). Default: INFO
    LOG_FORMAT: rich (colorful), pretty (simple colors), or json (machine-parseable). Default: rich
    LOG_VERBOSITY: Controls context fields in JSON logs:
        - "minimal": timestamp, level, service, message only
        - "standard": + host, logger (good for dev)
        - "full": + job_id, instance_id, step_id, etc. (for production)
        Default: "full" when LOG_FORMAT=json, "standard" otherwise
    LOG_PREFIX: Optional prefix for log lines (e.g., container name). Default: auto-detect
    LOG_COLORS: Enable/disable colors (pretty/rich format only). Default: true
    COLUMNS: Terminal width for Rich output (required in Docker). Default: 120

Production Usage (ELK/Prometheus):
    LOG_FORMAT=json LOG_LEVEL=INFO python worker.py

Development Usage (colorful output):
    LOG_LEVEL=DEBUG python worker.py

Example JSON output (for ELK):
    {"timestamp": "2024-12-30T15:30:45.123Z", "level": "INFO", "service": "comfyui-image",
     "host": "172.17.0.5", "message": "Job completed", "job_id": "abc123", ...}
"""

import os
import sys
import json
import socket
import logging
import traceback
import contextvars
from datetime import datetime
from typing import TYPE_CHECKING, Optional

# Rich is optional but provides much nicer output
try:
    from rich.logging import RichHandler
    from rich.console import Console
    from rich.theme import Theme

    RICH_AVAILABLE = True
except (
    ImportError
):  # pragma: no cover - optional rich dependency; falls back to stdlib logging when not installed
    RICH_AVAILABLE = False

if TYPE_CHECKING:
    from rich.logging import (
        RichHandler,
    )  # noqa: F811 - TYPE_CHECKING re-import; real import shadows the TYPE_CHECKING-only import above
    from rich.console import (
        Console,
    )  # noqa: F811 - TYPE_CHECKING re-import; real import shadows the TYPE_CHECKING-only import above
    from rich.theme import (
        Theme,
    )  # noqa: F811 - TYPE_CHECKING re-import; real import shadows the TYPE_CHECKING-only import above


# --- Job context for correlation_id propagation ---
# Set when a job is claimed, cleared when done. A log filter reads this and
# injects correlation_id into every LogRecord during job execution.

_correlation_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "_correlation_id_var", default=None
)


def set_job_correlation_id(correlation_id: Optional[str]) -> None:
    """Set correlation_id for the current job execution context."""
    _correlation_id_var.set(correlation_id)


def clear_job_correlation_id() -> None:
    """Clear correlation_id after job completes."""
    _correlation_id_var.set(None)


class CorrelationIdFilter(logging.Filter):
    """Inject correlation_id from job context into every LogRecord."""

    def filter(self, record: logging.LogRecord) -> bool:
        correlation_id = _correlation_id_var.get()
        if correlation_id:
            record.correlation_id = correlation_id  # type: ignore[attr-defined] - dynamic attribute; logging.LogRecord has no correlation_id field but custom filters read it downstream
        return True


# Built-in LogRecord attributes - never scrubbed.
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
        # Worker-specific built-ins set by CorrelationIdFilter + the emit chain:
        "correlation_id",
    }
)


class SensitiveDataFilter(logging.Filter):
    """Scrub sensitive and PII keys from log records at egress.

    api/ and workers/ share the same authoritative redaction policy; both
    apply equivalent protection over adapter requests, URLs, and job payloads.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        from contracts.redaction import (
            REDACTED_PLACEHOLDER,
            is_pii_key,
            is_sensitive_key,
            redact_sensitive_data,
        )

        if record.args and isinstance(record.args, tuple):
            record.args = tuple(
                redact_sensitive_data(arg) if isinstance(arg, (dict, list)) else arg
                for arg in record.args
            )
        elif isinstance(record.args, dict):
            record.args = redact_sensitive_data(record.args)

        for attr_name in list(record.__dict__.keys()):
            if attr_name in _BUILTIN_LOGRECORD_ATTRS or attr_name.startswith("_"):
                continue
            value = record.__dict__[attr_name]
            if is_sensitive_key(attr_name) or is_pii_key(attr_name):
                record.__dict__[attr_name] = REDACTED_PLACEHOLDER
            elif isinstance(value, (dict, list)):
                record.__dict__[attr_name] = redact_sensitive_data(value)

        return True


def _get_log_verbosity() -> str:
    """Resolve log verbosity from the contracts schema."""
    from contracts.log_schema import get_log_verbosity

    return get_log_verbosity()


def _is_running_in_docker() -> bool:
    """Check if running inside a Docker container."""
    # Check for /.dockerenv file (standard Docker indicator)
    if os.path.exists("/.dockerenv"):
        return True
    # Check for Docker cgroup (Linux only - /proc doesn't exist on macOS/Windows)
    if sys.platform == "linux":
        try:
            with open("/proc/1/cgroup", "r") as f:
                return "docker" in f.read()
        except (FileNotFoundError, PermissionError):
            pass
    return False


def _get_log_prefix() -> str:
    """
    Get log prefix from environment or auto-detect.

    When running in Docker, returns empty string since Docker Compose
    already prefixes logs with the container name.

    Priority:
    1. LOG_PREFIX env var (explicit override)
    2. Empty string if running in Docker (avoid duplicate prefix)
    3. Hostname + IP (for non-Docker environments)

    Example (non-Docker): shs-worker-comfyui (172.17.0.5)
    """
    from shared.settings import settings as _settings

    # Check for explicit prefix
    prefix = _settings.LOG_PREFIX
    if prefix:
        return prefix

    # In Docker, don't add prefix - Docker Compose already adds container name
    if _is_running_in_docker():
        return ""

    # Non-Docker: include hostname + IP for identification
    hostname = socket.gethostname()
    try:
        ip = socket.gethostbyname(hostname)
    except socket.gaierror:
        ip = "unknown"

    # If hostname looks like a container ID (hex), use WORKER_TYPE
    if len(hostname) == 12 and all(c in "0123456789abcdef" for c in hostname.lower()):
        return f"shs-worker-{_settings.WORKER_TYPE} ({ip})"

    return f"{hostname} ({ip})"


class PrettyFormatter(logging.Formatter):
    """
    Format logs with colors: timestamp, level, logger, and highlighted content.

    Example: 2026-01-16 03:00:00 INFO     worker_base - Registered with API
    """

    # ANSI color codes
    DIM = "\033[2m"
    CYAN = "\033[36m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    RESET = "\033[0m"

    LEVEL_COLORS = {
        "DEBUG": "\033[36m",  # Cyan
        "INFO": "\033[32m",  # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",  # Red
        "CRITICAL": "\033[35m",  # Magenta
    }

    def __init__(self, use_colors: bool = True, prefix: str = ""):
        super().__init__()
        self.use_colors = use_colors
        self.prefix = prefix

    def _colorize_message(self, message: str) -> str:
        """Add colors to URLs and UUIDs in the message."""
        import re

        # Color URLs (http/https)
        message = re.sub(r"(https?://[^\s]+)", f"{self.CYAN}\\1{self.RESET}", message)
        # Color UUIDs
        message = re.sub(
            r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})",
            f"{self.YELLOW}\\1{self.RESET}",
            message,
            flags=re.IGNORECASE,
        )
        return message

    def format(self, record: logging.LogRecord) -> str:
        # Timestamp: YYYY-MM-DD HH:MM:SS
        timestamp = datetime.fromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S")

        # Level name padded to 8 chars
        level = record.levelname.ljust(8)

        # Logger name (module name)
        logger_name = record.name

        # Format message
        message = record.getMessage()

        # Include exception info if present
        if record.exc_info:
            if not record.exc_text:
                record.exc_text = self.formatException(record.exc_info)
            message = f"{message}\n{record.exc_text}"

        # Add colors if enabled
        if self.use_colors:
            timestamp = f"{self.DIM}{timestamp}{self.RESET}"
            if record.levelname in self.LEVEL_COLORS:
                level = f"{self.LEVEL_COLORS[record.levelname]}{level}{self.RESET}"
            logger_name = f"{self.DIM}{logger_name}{self.RESET}"
            message = self._colorize_message(message)

        if self.prefix:
            return f"{self.prefix} {timestamp} {level} {logger_name} - {message}"
        return f"{timestamp} {level} {logger_name} - {message}"


class JsonFormatter(logging.Formatter):
    """
    Format logs as JSON for production/ELK ingestion.

    Conforms to the canonical log schema in contracts/log_schema.py.

    Verbosity controlled by LOG_VERBOSITY env var:
    - minimal: timestamp, level, service, message
    - standard: + host, logger
    - full: + correlation_id, job_id, instance_id, step_id, etc.

    Additional fields can be passed via extra= parameter in logger calls.
    """

    def __init__(self, service: str = "", host: str = ""):
        super().__init__()
        from shared.settings import settings as _s

        self.service = service or _s.WORKER_TYPE
        self.host = host

    def format(self, record: logging.LogRecord) -> str:
        from contracts.log_schema import (
            VERBOSITY_FULL,
            VERBOSITY_STANDARD,
            format_timestamp,
            get_log_verbosity,
        )

        verbosity = get_log_verbosity()

        # Minimal: core fields (always present)
        log_data = {
            "timestamp": format_timestamp(record.created),
            "level": record.levelname,
            "service": self.service,
            "message": record.getMessage(),
        }

        # Standard: add host and logger
        if verbosity in (VERBOSITY_STANDARD, VERBOSITY_FULL):
            log_data["host"] = self.host
            log_data["logger"] = record.name

        # Full: add correlation_id and job context fields
        if verbosity == VERBOSITY_FULL:
            for key in [
                "correlation_id",
                "job_id",
                "instance_id",
                "step_id",
                "operation",
                "prompt_id",
                "duration_ms",
            ]:
                if hasattr(record, key):
                    log_data[key] = getattr(record, key)

        # Exception info - unified field name per contracts/log_schema.py
        if record.exc_info:
            log_data["exception"] = "".join(
                traceback.format_exception(*record.exc_info)
            )

        # Developer-provided structured fields
        extra = getattr(record, "extra", None)
        if extra is not None:
            log_data["extra"] = extra

        return json.dumps(log_data, ensure_ascii=False)


def setup_logging(default_level: str = "INFO") -> None:
    # Env vars: LOG_LEVEL, LOG_FORMAT (rich/pretty/json), LOG_COLORS, LOG_PREFIX
    from shared.settings import settings as _settings

    # Get log level from settings
    level_name = _settings.LOG_LEVEL.upper()
    level = getattr(logging, level_name, logging.INFO)

    # Get format type
    log_format = _settings.LOG_FORMAT.lower()

    # Create handler based on format
    if log_format == "json":
        # JSON format for production/ELK
        handler = logging.StreamHandler(sys.stdout)
        hostname = socket.gethostname()
        try:
            host_ip = socket.gethostbyname(hostname)
        except socket.gaierror:
            host_ip = "unknown"
        handler.setFormatter(JsonFormatter(service=_settings.WORKER_TYPE, host=host_ip))

    elif log_format == "rich" and RICH_AVAILABLE:
        # Rich format - beautiful colored output with syntax highlighting
        use_colors = _settings.LOG_COLORS

        # Custom theme for worker logs
        custom_theme = Theme(
            {
                "info": "green",
                "warning": "yellow",
                "error": "bold red",
                "debug": "dim cyan",
                "repr.number": "bold cyan",
                "repr.str": "green",
                "repr.path": "cyan",
            }
        )

        # Use COLUMNS env var for terminal width (required in Docker)
        console_width = int(os.getenv("COLUMNS", "120"))
        console = Console(
            force_terminal=True,  # Force colors in Docker
            theme=custom_theme,
            no_color=not use_colors,
            width=console_width,
        )

        handler = RichHandler(
            console=console,
            show_time=True,
            show_level=True,
            show_path=False,  # Don't show file:line - too verbose
            rich_tracebacks=True,
            tracebacks_show_locals=False,  # Set True for debugging
            markup=True,  # Allows [bold]text[/] in messages
            log_time_format="[%Y-%m-%d %H:%M:%S]",
        )

    else:
        # Pretty format - simple colored output (fallback)
        handler = logging.StreamHandler(sys.stdout)
        use_colors = _settings.LOG_COLORS
        prefix = _get_log_prefix()
        handler.setFormatter(PrettyFormatter(use_colors=use_colors, prefix=prefix))

    # Add correlation_id filter to inject job context into all log records.
    # SensitiveDataFilter comes right after so secrets in `extra={}` dicts
    # and in dict-valued %-args are scrubbed before formatting.
    handler.addFilter(CorrelationIdFilter())
    handler.addFilter(SensitiveDataFilter())

    # Configure root logger
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()
    root.addHandler(handler)

    # Suppress noisy HTTP client loggers - worker polling creates too much noise
    # Actual errors will still surface via exception handling in worker code
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    logging.getLogger("hpack").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
