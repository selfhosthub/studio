# api/app/domain/documentation/models.py

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID


class DocType(str, Enum):
    """Documentation category. PG enum labels are the member NAMES (invariant #1)."""

    USER = "user"
    PROVIDER = "provider"
    WORKFLOW = "workflow"


class DocVisibility(str, Enum):
    """Minimum role required to read a doc. PG enum labels are the member NAMES (invariant #1)."""

    PUBLIC = "public"
    ADMIN = "admin"
    SUPER_ADMIN = "super_admin"


@dataclass
class Documentation:
    """A documentation page sourced from a marketplace source (community/plus).

    User docs (user/admin/super-admin guides) and workflow feature docs are
    synced from the community source's docs-catalog.json at boot, catalog
    refresh, and seeding. Provider docs follow the provider install lifecycle:
    fetched on install/reinstall, flagged inactive on uninstall.
    """

    id: UUID
    slug: str
    doc_type: DocType
    title: str
    content: str
    description: str = ""
    icon: str = "box"
    visibility: DocVisibility = DocVisibility.PUBLIC
    source_tier: str = "community"
    active: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
