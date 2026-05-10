# contracts/log_schema.py

"""
Log Schema Contract: canonical JSON log field names and verbosity tiers.

Both API and worker JSON formatters import from here to ensure
identical field names and structure in LOG_FORMAT=json output.

Python 3.11 compatible.
"""

import os

# --- Canonical field names ---
# These are the JSON keys emitted by both API and worker formatters.

# Minimal tier (always present)
FIELD_TIMESTAMP = "timestamp"
FIELD_LEVEL = "level"
FIELD_SERVICE = "service"
FIELD_MESSAGE = "message"

# Standard tier (adds observability context)
FIELD_HOST = "host"
FIELD_LOGGER = "logger"

# Full tier (adds tracing and identity)
FIELD_CORRELATION_ID = "correlation_id"

# Error (present only when exc_info is set)
FIELD_EXCEPTION = "exception"

# Developer-provided structured fields (present only when extra={} passed)
FIELD_EXTRA = "extra"

# --- Verbosity tiers ---
VERBOSITY_MINIMAL = "minimal"
VERBOSITY_STANDARD = "standard"
VERBOSITY_FULL = "full"

VALID_VERBOSITIES = (VERBOSITY_MINIMAL, VERBOSITY_STANDARD, VERBOSITY_FULL)


def get_log_verbosity() -> str:
    """
    Get log verbosity level from environment.

    Tiers:
    - minimal: timestamp, level, service, message
    - standard: + host, logger
    - full: + correlation_id and component-specific context fields

    Default: 'full' when LOG_FORMAT=json (production), 'standard' otherwise (dev)
    """
    verbosity = os.getenv("SHS_LOG_VERBOSITY", "").lower()
    if verbosity in VALID_VERBOSITIES:
        return verbosity
    log_format = os.getenv("SHS_LOG_FORMAT", "rich").lower()
    return VERBOSITY_FULL if log_format == "json" else VERBOSITY_STANDARD


def format_timestamp(created: float) -> str:
    """
    Format a LogRecord.created timestamp to canonical ISO 8601 with Z suffix.

    Output: "2026-03-04T10:30:45.123Z"
    """
    from datetime import datetime, timezone

    dt = datetime.fromtimestamp(created, tz=timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"
