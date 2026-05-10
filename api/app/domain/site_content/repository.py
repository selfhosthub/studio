# api/app/domain/site_content/repository.py

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from uuid import UUID

from app.domain.site_content.models import SiteContent


class SiteContentRepository(ABC):
    """Persistence operations for site content pages."""

    @abstractmethod
    async def list_all(self) -> List[SiteContent]: ...

    @abstractmethod
    async def get_by_page_id(self, page_id: str) -> Optional[SiteContent]: ...

    @abstractmethod
    async def update_or_create(
        self, page_id: str, content: Dict[str, Any], updated_by: UUID
    ) -> SiteContent:
        """Replaces the full content dict for page_id; creates a new row if none exists."""

    @abstractmethod
    async def merge_content(
        self, page_id: str, key: str, value: Any, updated_by: UUID
    ) -> SiteContent:
        """Patch a single key into the page's content dict without overwriting other keys."""
