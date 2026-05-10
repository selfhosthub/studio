# api/app/application/services/site_content_service.py

"""
Application service for site content management.

Manages public page content including testimonials, terms, privacy policy,
about page content, and contact info. Super-admin only.
"""

import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from app.domain.common.exceptions import EntityNotFoundError
from app.domain.site_content.models import SiteContent
from app.domain.site_content.repository import SiteContentRepository

logger = logging.getLogger(__name__)


class SiteContentService:
    """Application service for site content operations."""

    def __init__(self, repo: SiteContentRepository):
        self.repo = repo

    async def list_all(self) -> List[Dict[str, Any]]:
        """List all site content pages."""
        contents = await self.repo.list_all()

        return [self._to_dict(c) for c in contents]

    async def get_by_page_id(self, page_id: str) -> Dict[str, Any]:
        """Return site content for a page, raising EntityNotFoundError if not found."""
        content = await self.repo.get_by_page_id(page_id)

        if not content:
            raise EntityNotFoundError(
                entity_type="SiteContent",
                entity_id=page_id,
                code="SITE_CONTENT_NOT_FOUND",
            )

        return self._to_dict(content)

    async def get_by_page_id_or_none(self, page_id: str) -> Optional[Dict[str, Any]]:
        """Return site content for a page, or None if not found."""
        content = await self.repo.get_by_page_id(page_id)

        if not content:
            return None

        return self._to_dict(content)

    async def update_or_create(
        self, page_id: str, content_data: Dict[str, Any], updated_by: UUID
    ) -> Dict[str, Any]:
        """Update or create site content for a page."""
        content = await self.repo.update_or_create(
            page_id=page_id,
            content=content_data,
            updated_by=updated_by,
        )

        return self._to_dict(content)

    async def merge_content(
        self, page_id: str, key: str, value: Any, updated_by: UUID
    ) -> Dict[str, Any]:
        """Merge a single key into a page's existing content without overwriting other sections."""
        content = await self.repo.merge_content(
            page_id=page_id,
            key=key,
            value=value,
            updated_by=updated_by,
        )

        return self._to_dict(content)

    @staticmethod
    def _to_dict(entity: SiteContent) -> Dict[str, Any]:
        """Convert a SiteContent domain entity to a response dictionary."""
        return {
            "id": entity.id,
            "page_id": entity.page_id,
            "content": entity.content,
            "updated_at": entity.updated_at,
        }
