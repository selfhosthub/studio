# api/app/infrastructure/persistence/rls_context.py

"""Per-request org context (contextvars) consumed by Postgres RLS policies."""

from contextvars import ContextVar
from typing import Optional
import uuid


_current_org_id: ContextVar[Optional[uuid.UUID]] = ContextVar(
    "current_org_id", default=None
)


def set_org_context(org_id: uuid.UUID) -> None:
    _current_org_id.set(org_id)


def get_org_context() -> Optional[uuid.UUID]:
    return _current_org_id.get()


def clear_org_context() -> None:
    _current_org_id.set(None)
