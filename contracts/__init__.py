# contracts/__init__.py

"""
Shared contract types between API and workers.

Pydantic models define canonical payload shapes for cross-component
communication. Log schema defines canonical JSON log field names.
Both sides import from here - one source of truth.

Python 3.11 compatible (workers use 3.11, API uses 3.12).
"""

from contracts.log_schema import (
    FIELD_CORRELATION_ID,
    FIELD_EXCEPTION,
    FIELD_EXTRA,
    FIELD_HOST,
    FIELD_LEVEL,
    FIELD_LOGGER,
    FIELD_MESSAGE,
    FIELD_SERVICE,
    FIELD_TIMESTAMP,
    VERBOSITY_FULL,
    VERBOSITY_MINIMAL,
    VERBOSITY_STANDARD,
    format_timestamp,
    get_log_verbosity,
)
from contracts.redaction import (
    PII_KEYS,
    REDACTED_PLACEHOLDER,
    SENSITIVE_KEYS,
    is_pii_key,
    is_sensitive_key,
    redact_sensitive_data,
    redact_url,
)

__all__ = [
    "DownloadedFileContract",
    "JobClaimContract",
    "StepResultContract",
    "FIELD_TIMESTAMP",
    "FIELD_LEVEL",
    "FIELD_SERVICE",
    "FIELD_MESSAGE",
    "FIELD_HOST",
    "FIELD_LOGGER",
    "FIELD_CORRELATION_ID",
    "FIELD_EXCEPTION",
    "FIELD_EXTRA",
    "VERBOSITY_MINIMAL",
    "VERBOSITY_STANDARD",
    "VERBOSITY_FULL",
    "get_log_verbosity",
    "format_timestamp",
    "SENSITIVE_KEYS",
    "PII_KEYS",
    "REDACTED_PLACEHOLDER",
    "is_sensitive_key",
    "is_pii_key",
    "redact_sensitive_data",
    "redact_url",
]


def __getattr__(name: str):
    """Lazy-import pydantic-dependent contracts to avoid pulling in pydantic
    for lightweight consumers (e.g., workers that only need log_schema)."""
    if name == "DownloadedFileContract":
        from contracts.downloaded_file import DownloadedFileContract

        return DownloadedFileContract
    if name == "JobClaimContract":
        from contracts.job_claim import JobClaimContract

        return JobClaimContract
    if name == "StepResultContract":
        from contracts.step_result import StepResultContract

        return StepResultContract
    raise AttributeError(f"module 'contracts' has no attribute {name!r}")
