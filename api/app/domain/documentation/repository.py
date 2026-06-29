# api/app/domain/documentation/repository.py

from abc import ABC, abstractmethod
from typing import List, Optional

from app.domain.documentation.models import Documentation, DocType, DocVisibility


class DocumentationRepository(ABC):
    """Persistence operations for documentation pages (global, not org-scoped)."""

    @abstractmethod
    async def get(
        self, slug: str, doc_type: DocType, active_only: bool = True
    ) -> Optional[Documentation]: ...

    @abstractmethod
    async def list_by_type(
        self, doc_type: DocType, active_only: bool = True
    ) -> List[Documentation]: ...

    @abstractmethod
    async def upsert(
        self,
        slug: str,
        doc_type: DocType,
        *,
        title: str,
        content: str,
        description: str = "",
        icon: str = "box",
        visibility: DocVisibility = DocVisibility.PUBLIC,
        source_tier: str = "community",
        active: bool = True,
    ) -> Documentation:
        """Insert or update the row keyed by (slug, doc_type). Flushes; caller commits."""

    @abstractmethod
    async def set_active(self, slug: str, doc_type: DocType, active: bool) -> bool:
        """Toggle a doc's active flag. Returns False if no row exists. Flushes; caller commits."""
