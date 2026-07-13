# api/app/infrastructure/errors.py

"""Classify an exception into a client-safe message: clean DomainException text
verbatim, everything else a generic sentence plus the request correlation id."""

from __future__ import annotations

import logging
import re
from typing import Any

from app.domain.common.exceptions import DomainException
from app.infrastructure.logging.request_context import get_request_context

logger = logging.getLogger(__name__)

_GENERIC = "The request could not be completed."

# Internal-data signatures that must not reach a client.
_LEAK_SIGNATURES = re.compile(
    r"INSERT INTO|UPDATE \w+ SET|DELETE FROM|VALUES\s*\(|sqlalche\.me|"
    r"asyncpg\.|\bUUID\(|/[a-z_/]+\.py|0x[0-9a-fA-F]{6,}",
    re.IGNORECASE,
)


def _reference_suffix() -> str:
    """Return ` Reference: <correlation_id>.` for the current request, or ``""``."""
    ctx = get_request_context()
    ref = ctx.correlation_id if ctx else None
    return f" Reference: {ref}." if ref else ""


def generic_error_message() -> str:
    """The client-safe sentence for any non-author-controlled failure."""
    return _GENERIC + _reference_suffix()


def safe_error_message(e: BaseException | Any) -> str:
    """Classify an exception into a client-safe message.

    See module docstring for policy. Never raises; non-Exception input falls
    back to the generic sentence so callers do not need to guard.
    """
    if not isinstance(e, BaseException):
        return generic_error_message()

    if isinstance(e, DomainException):
        message = str(e)
        if not _LEAK_SIGNATURES.search(message):
            return message
        logger.warning(
            "Suppressed DomainException message carrying a leak signature (%s)",
            type(e).__name__,
        )

    return generic_error_message()
