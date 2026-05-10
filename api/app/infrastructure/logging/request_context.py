# api/app/infrastructure/logging/request_context.py
"""contextvars-based request context - surfaced into log formatters without explicit passing."""

from contextvars import ContextVar
from dataclasses import dataclass
from typing import Optional


@dataclass
class RequestContext:
    user_id: Optional[str] = None
    username: Optional[str] = None
    org_id: Optional[str] = None
    org_slug: Optional[str] = None
    correlation_id: Optional[str] = None


_request_context: ContextVar[Optional[RequestContext]] = ContextVar(
    "request_context", default=None
)


def get_request_context() -> Optional[RequestContext]:
    return _request_context.get()


def set_request_context(
    user_id: Optional[str] = None,
    username: Optional[str] = None,
    org_id: Optional[str] = None,
    org_slug: Optional[str] = None,
    correlation_id: Optional[str] = None,
) -> None:
    ctx = RequestContext(
        user_id=user_id,
        username=username,
        org_id=org_id,
        org_slug=org_slug,
        correlation_id=correlation_id,
    )
    _request_context.set(ctx)


def clear_request_context() -> None:
    _request_context.set(None)
