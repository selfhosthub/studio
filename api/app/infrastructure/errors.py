# api/app/infrastructure/errors.py

"""
Safe error-message classifier.

`safe_error_message(e)` produces an operator-actionable, secret-free string
suitable for HTTP response bodies, WebSocket payloads, and stored job/instance
state that flows back to the UI. It exists because raw `str(e)` on infrastructure
exceptions leaks SQL statements, bind parameters, response bodies, file paths,
and stack-frame addresses.

Allowlist (tight by deliberate policy):
  - DomainException subclasses pass through verbatim. Their messages are
    author-controlled and intended for client display.
  - A small set of known-dangerous infrastructure exceptions get classified
    sentences mapped from the type, with no exception text echoed.
  - Everything else (including built-in ValueError, KeyError, TypeError) returns
    the type name only: "<TypeName> occurred". These types echo internal paths,
    dict keys, and repr'd objects too often to trust.

Callers must invoke `logger.exception(...)` before this helper if they want
diagnosis preserved. This module never logs; logging is the caller's job.
"""

from __future__ import annotations

import subprocess
from typing import Any

import httpx
from asyncpg.exceptions import PostgresError
from sqlalchemy.exc import DBAPIError

from app.domain.common.exceptions import DomainException


def safe_error_message(e: BaseException | Any) -> str:
    """Classify an exception into a UI-safe message.

    See module docstring for policy. Never raises; non-Exception input
    falls back to a generic sentence so callers do not need to guard.
    """
    if not isinstance(e, BaseException):
        return "An unexpected error occurred."

    if isinstance(e, DomainException):
        return str(e)

    if isinstance(e, (DBAPIError, PostgresError)):
        return (
            "A database error occurred. The data could not be stored. "
            "See server logs for details."
        )

    if isinstance(e, httpx.HTTPStatusError):
        return "An upstream service returned an error. See server logs for details."

    # httpx.HTTPError is the base of RequestError + HTTPStatusError. We've
    # already handled HTTPStatusError above; this catches the rest
    # (ConnectError, TimeoutException, etc).
    if isinstance(e, httpx.HTTPError):
        return "An upstream service could not be reached. See server logs for details."

    if isinstance(e, subprocess.CalledProcessError):
        return "A subprocess failed. See server logs for details."

    if isinstance(e, TimeoutError):
        return "The operation timed out. See server logs for details."

    return f"{type(e).__name__} occurred. See server logs for details."
