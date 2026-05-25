# api/app/domain/marketplace/repository.py

"""Repository interface for marketplace catalog persistence."""

import uuid
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from app.domain.marketplace.models import MarketplaceCatalog
from app.domain.provider.models import CatalogType


class MarketplaceCatalogRepository(ABC):
    """Persistence operations for marketplace catalogs."""

    @abstractmethod
    async def get_active(self, catalog_type: CatalogType) -> Optional[MarketplaceCatalog]: ...

    @abstractmethod
    async def get_by_id(self, catalog_id: uuid.UUID) -> Optional[MarketplaceCatalog]: ...

    @abstractmethod
    async def list_all(
        self, catalog_type: Optional[CatalogType] = None, limit: int = 100
    ) -> List[MarketplaceCatalog]: ...

    @abstractmethod
    async def upsert_active(
        self,
        catalog_type: CatalogType,
        catalog_data: Dict[str, Any],
        source_url: Optional[str] = None,
        source_tag: Optional[str] = None,
    ) -> MarketplaceCatalog:
        """Deactivates any existing active catalog and creates a new one."""

    @abstractmethod
    async def set_fetch_error(
        self,
        catalog_type: CatalogType,
        error_message: str,
    ) -> None: ...

    @abstractmethod
    async def delete(self, catalog_id: uuid.UUID) -> bool:
        """Returns True if deleted."""
