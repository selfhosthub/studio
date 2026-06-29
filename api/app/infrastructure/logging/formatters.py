# api/app/infrastructure/logging/formatters.py

"""ColoredFormatter (ANSI) and JSONFormatter (structured) for log output."""

import logging
import socket

from app.config.settings import settings


class Colors:
    RESET = "\033[0m"
    BOLD = "\033[1m"

    DEBUG = "\033[36m"
    INFO = "\033[32m"
    WARNING = "\033[33m"
    ERROR = "\033[31m"
    CRITICAL = "\033[1;31m"


class ColoredFormatter(logging.Formatter):
    """ANSI-colored level names. Disable with LOG_COLORS=false."""

    LEVEL_COLORS = {
        logging.DEBUG: Colors.DEBUG,
        logging.INFO: Colors.INFO,
        logging.WARNING: Colors.WARNING,
        logging.ERROR: Colors.ERROR,
        logging.CRITICAL: Colors.CRITICAL,
    }

    def __init__(self, fmt: str | None = None, datefmt: str | None = None):
        super().__init__(fmt, datefmt)
        self.use_colors = settings.LOG_COLORS

    def format(self, record: logging.LogRecord) -> str:
        # Copy: don't mutate the shared record.
        record = logging.makeLogRecord(record.__dict__)

        if self.use_colors:
            color = self.LEVEL_COLORS.get(record.levelno, Colors.RESET)
            record.levelname = f"{color}{record.levelname}{Colors.RESET}"

        return super().format(record)


class JSONFormatter(logging.Formatter):
    """Structured JSON output. Verbosity tiers: minimal / standard / full (LOG_VERBOSITY)."""

    def __init__(self) -> None:
        super().__init__()
        self.service = settings.API_SERVICE_NAME
        hostname = socket.gethostname()
        try:
            self.host = socket.gethostbyname(hostname)
        except socket.gaierror:
            self.host = "unknown"

    def format(self, record: logging.LogRecord) -> str:
        import json

        from contracts.log_schema import (
            VERBOSITY_FULL,
            VERBOSITY_STANDARD,
            format_timestamp,
            get_log_verbosity,
        )

        verbosity = get_log_verbosity()

        log_entry = {
            "timestamp": format_timestamp(record.created),
            "level": record.levelname,
            "service": self.service,
            "message": record.getMessage(),
        }

        if verbosity in (VERBOSITY_STANDARD, VERBOSITY_FULL):
            log_entry["host"] = self.host
            log_entry["logger"] = record.name

            try:
                from app.infrastructure.logging.request_context import (
                    get_request_context,
                )

                ctx = get_request_context()
                if ctx:
                    if ctx.username:
                        log_entry["username"] = ctx.username
                    if ctx.org_slug:
                        log_entry["org_slug"] = ctx.org_slug

                    if verbosity == VERBOSITY_FULL:
                        if ctx.user_id:
                            log_entry["user_id"] = ctx.user_id
                        if ctx.org_id:
                            log_entry["org_id"] = ctx.org_id
                        if ctx.correlation_id:
                            log_entry["correlation_id"] = ctx.correlation_id
            except ImportError:
                pass

        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        extra = getattr(record, "extra", None)
        if extra is not None:
            log_entry["extra"] = extra

        return json.dumps(log_entry)


LOG_FORMAT = "%(asctime)s %(levelname)-8s %(name)s - %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
