# api/app/domain/marketplace/models.py

"""Marketplace catalog domain entity."""

import uuid
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional

from app.domain.provider.models import CatalogType


class MarketplaceCatalog:
    """Fetched catalog of available packages from a remote source. Only one active catalog per type at a time."""

    def __init__(
        self,
        id: uuid.UUID,
        catalog_type: CatalogType,
        catalog_data: Dict[str, Any],
        source_url: Optional[str] = None,
        source_tag: Optional[str] = None,
        version: Optional[str] = None,
        is_active: bool = True,
        fetch_error: Optional[str] = None,
        fetched_at: Optional[datetime] = None,
        created_at: Optional[datetime] = None,
        updated_at: Optional[datetime] = None,
    ):
        self.id = id
        self.catalog_type = catalog_type
        self.catalog_data = catalog_data
        self.source_url = source_url
        self.source_tag = source_tag
        self.version = version
        self.is_active = is_active
        self.fetch_error = fetch_error
        self.fetched_at = fetched_at
        self.created_at = created_at or datetime.now(UTC)
        self.updated_at = updated_at or datetime.now(UTC)

    @property
    def packages(self) -> List[Dict[str, Any]]:
        return self.catalog_data.get("packages", [])
