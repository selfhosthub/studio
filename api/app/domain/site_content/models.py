# api/app/domain/site_content/models.py

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID


@dataclass
class SiteContent:
    """Configurable public page content (terms, privacy, testimonials, etc.). Stored as a flexible JSON dict keyed by page_id."""

    id: UUID
    page_id: str
    content: Dict[str, Any]
    updated_by: Optional[UUID] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
