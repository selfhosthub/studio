# api/app/infrastructure/logging/config.py

"""dictConfig builders for the three log format paths (pretty, json, rich).

Env: LOG_FORMAT, LOG_VERBOSITY, ENABLE_ACCESS_LOGS, COLUMNS, LOG_COLORS.
"""

import logging
import logging.config
import os
from typing import Any

from app.config.settings import settings

from app.infrastructure.logging.formatters import (
    ColoredFormatter,
    JSONFormatter,
    LOG_FORMAT,
    LOG_DATE_FORMAT,
)
from app.infrastructure.logging.filters import (
    SensitiveDataFilter,
    TokenRedactionFilter,
    HealthCheckFilter,
    WebSocketFilter,
    WorkerPollingFilter,
    AccessLogStatusFilter,
)

# Rich is optional.
try:
    from rich.logging import RichHandler
    from rich.console import Console
    from rich.theme import Theme

    RICH_AVAILABLE = True
except ImportError:  # pragma: no cover
    RICH_AVAILABLE = False


def suppress_third_party_loggers() -> None:
    """Pin noisy third-party loggers to WARNING."""
    for name in ("httpx", "httpcore", "asyncio"):
        logging.getLogger(name).setLevel(logging.WARNING)


def get_base_log_config(
    log_level: str = "INFO",
    uvicorn_log_level: str = "INFO",
    uvicorn_error_log_level: str = "ERROR",
    enable_access_logs: bool = False,
) -> dict[str, Any]:
    """Minimal log config used when access logs are disabled."""
    config: dict[str, Any] = {
        "version": 1,
        "disable_existing_loggers": False,
        "filters": {
            "worker_polling": {
                "()": WorkerPollingFilter,
            },
            "access_log_status": {
                "()": AccessLogStatusFilter,
            },
        },
        "formatters": {
            "default": {
                "()": ColoredFormatter,
                "fmt": LOG_FORMAT,
                "datefmt": LOG_DATE_FORMAT,
            },
        },
        "handlers": {
            "default": {
                "formatter": "default",
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
                "filters": ["worker_polling", "access_log_status"],
            },
        },
        "loggers": {
            "uvicorn": {
                "handlers": ["default"],
                "level": uvicorn_log_level,
                "propagate": False,
            },
            "uvicorn.error": {
                "handlers": ["default"],
                "level": uvicorn_error_log_level,
                "propagate": False,
            },
            # No handlers + level 100 (above CRITICAL) silences uvicorn.access entirely.
            "uvicorn.access": {
                "handlers": [],
                "level": 100,
                "propagate": False,
            },
        },
        "root": {
            "level": log_level,
            "handlers": ["default"],
        },
    }

    if enable_access_logs:
        config["formatters"]["access"] = {
            "()": "uvicorn.logging.AccessFormatter",
            "fmt": '%(asctime)s ACCESS   uvicorn.access - %(client_addr)s "%(request_line)s" %(status_code)s',
            "datefmt": LOG_DATE_FORMAT,
        }
        config["handlers"]["access"] = {
            "formatter": "access",
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout",
            "filters": ["worker_polling", "access_log_status"],
        }
        config["loggers"]["uvicorn.access"] = {
            "handlers": ["access"],
            "level": "INFO",
            "propagate": False,
        }

    return config


def get_log_config(
    log_level: str = "INFO",
    uvicorn_log_level: str = "INFO",
    uvicorn_error_log_level: str = "INFO",
) -> dict[str, Any]:
    """Unified pretty-text log config - same format across app, uvicorn, third-party."""
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "filters": {
            "token_redaction": {
                "()": TokenRedactionFilter,
            },
            "sensitive_data": {
                "()": SensitiveDataFilter,
            },
            "health_check": {
                "()": HealthCheckFilter,
            },
            "websocket": {
                "()": WebSocketFilter,
            },
            "worker_polling": {
                "()": WorkerPollingFilter,
            },
            "access_log_status": {
                "()": AccessLogStatusFilter,
            },
        },
        "formatters": {
            "default": {
                "()": ColoredFormatter,
                "fmt": LOG_FORMAT,
                "datefmt": LOG_DATE_FORMAT,
            },
            "access": {
                "()": "uvicorn.logging.AccessFormatter",
                "fmt": '%(asctime)s ACCESS   uvicorn.access - %(client_addr)s "%(request_line)s" %(status_code)s',
                "datefmt": LOG_DATE_FORMAT,
            },
        },
        "handlers": {
            "default": {
                "formatter": "default",
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
                "filters": [
                    "sensitive_data",
                    "token_redaction",
                    "websocket",
                    "worker_polling",
                    "access_log_status",
                ],
            },
            "access": {
                "formatter": "access",
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
                "filters": [
                    "sensitive_data",
                    "token_redaction",
                    "health_check",
                    "worker_polling",
                    "access_log_status",
                ],
            },
        },
        "loggers": {
            "uvicorn": {
                "handlers": ["default"],
                "level": uvicorn_log_level,
                "propagate": False,
            },
            "uvicorn.error": {
                "level": uvicorn_error_log_level,
                "handlers": ["default"],
                "propagate": False,
            },
            "uvicorn.access": {
                "handlers": ["access"],
                "level": log_level,
                "propagate": False,
            },
        },
        "root": {
            "level": log_level,
            "handlers": ["default"],
        },
    }


def setup_rich_logging(
    log_level: str = "INFO",
    uvicorn_log_level: str = "INFO",
    uvicorn_error_log_level: str = "ERROR",
    enable_access_logs: bool = False,
) -> None:
    """Configure Rich logging; falls back to base config if rich is not installed."""
    if not RICH_AVAILABLE:
        logging.config.dictConfig(
            get_base_log_config(
                log_level=log_level,
                uvicorn_log_level=uvicorn_log_level,
                uvicorn_error_log_level=uvicorn_error_log_level,
                enable_access_logs=False,
            )
        )
        suppress_third_party_loggers()
        return

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

    # COLUMNS env var sets terminal width - required in Docker.
    console_width = int(os.getenv("COLUMNS", "120"))
    use_colors = settings.LOG_COLORS
    console = Console(
        force_terminal=True,
        theme=custom_theme,
        no_color=not use_colors,
        width=console_width,
        soft_wrap=True,
    )

    handler = RichHandler(
        console=console,
        show_time=True,
        show_level=True,
        show_path=False,
        rich_tracebacks=False,
        tracebacks_show_locals=False,
        markup=True,
        log_time_format="[%Y-%m-%d %H:%M:%S]",
    )

    # Filter order matters: scrub dict/extra args, then string patterns, then drop noise.
    handler.addFilter(SensitiveDataFilter())
    handler.addFilter(TokenRedactionFilter())
    handler.addFilter(WorkerPollingFilter())
    handler.addFilter(AccessLogStatusFilter())

    numeric_level = getattr(logging, log_level.upper(), logging.INFO)
    numeric_uvicorn_level = getattr(logging, uvicorn_log_level.upper(), logging.INFO)
    numeric_uvicorn_error_level = getattr(
        logging, uvicorn_error_log_level.upper(), logging.ERROR
    )

    root = logging.getLogger()
    root.setLevel(numeric_level)
    root.handlers.clear()
    root.addHandler(handler)

    uvicorn_logger = logging.getLogger("uvicorn")
    uvicorn_logger.setLevel(numeric_uvicorn_level)
    uvicorn_logger.handlers.clear()
    uvicorn_logger.addHandler(handler)
    uvicorn_logger.propagate = False

    uvicorn_error = logging.getLogger("uvicorn.error")
    uvicorn_error.setLevel(numeric_uvicorn_error_level)
    uvicorn_error.handlers.clear()
    uvicorn_error.addHandler(handler)
    uvicorn_error.propagate = False

    access_logger = logging.getLogger("uvicorn.access")
    if enable_access_logs:
        access_logger.disabled = False
        access_logger.handlers.clear()
        access_logger.addHandler(handler)
        access_logger.setLevel(numeric_uvicorn_level)
        access_logger.propagate = False
        access_logger.addFilter(SensitiveDataFilter())
        access_logger.addFilter(TokenRedactionFilter())
        access_logger.addFilter(HealthCheckFilter())
        access_logger.addFilter(WorkerPollingFilter())
        access_logger.addFilter(AccessLogStatusFilter())
        access_logger.addFilter(WebSocketFilter())
    else:
        access_logger.disabled = True
        access_logger.handlers.clear()
        access_logger.addHandler(logging.NullHandler())
        access_logger.setLevel(100)
        access_logger.propagate = False

    suppress_third_party_loggers()


def get_json_log_config(
    log_level: str = "INFO",
    uvicorn_log_level: str = "INFO",
    uvicorn_error_log_level: str = "ERROR",
    enable_access_logs: bool = False,
) -> dict[str, Any]:
    """JSON log config for ELK/Prometheus/Loki ingest."""
    access_log_config: dict[str, Any] = (
        {
            "handlers": ["json"],
            "level": uvicorn_log_level,
            "filters": ["health_check"],
            "propagate": False,
        }
        if enable_access_logs
        else {
            "handlers": [],
            "level": 100,
            "propagate": False,
        }
    )

    filters: dict[str, Any] = {
        "worker_polling": {
            "()": WorkerPollingFilter,
        },
        "access_log_status": {
            "()": AccessLogStatusFilter,
        },
        "token_redaction": {
            "()": TokenRedactionFilter,
        },
        "sensitive_data": {
            "()": SensitiveDataFilter,
        },
    }
    if enable_access_logs:
        filters["health_check"] = {
            "()": HealthCheckFilter,
        }

    return {
        "version": 1,
        "disable_existing_loggers": False,
        "filters": filters,
        "formatters": {
            "json": {
                "()": JSONFormatter,
            },
        },
        "handlers": {
            "json": {
                "formatter": "json",
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
                "filters": [
                    "sensitive_data",
                    "token_redaction",
                    "worker_polling",
                    "access_log_status",
                ],
            },
        },
        "loggers": {
            "uvicorn": {
                "handlers": ["json"],
                "level": uvicorn_log_level,
                "propagate": False,
            },
            "uvicorn.error": {
                "handlers": ["json"],
                "level": uvicorn_error_log_level,
                "propagate": False,
            },
            "uvicorn.access": access_log_config,
        },
        "root": {
            "level": log_level,
            "handlers": ["json"],
        },
    }
