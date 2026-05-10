# api/app/infrastructure/repositories/marketplace_catalog_repository.py

"""SQLAlchemy implementation of MarketplaceCatalog repository. Only one active catalog per type is allowed."""

import logging
import uuid
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.marketplace.models import MarketplaceCatalog
from app.domain.marketplace.repository import MarketplaceCatalogRepository
from app.domain.provider.models import CatalogType
from app.infrastructure.persistence.models import MarketplaceCatalogModel

logger = logging.getLogger(__name__)


class SQLAlchemyMarketplaceCatalogRepository(MarketplaceCatalogRepository):
    """SQLAlchemy implementation of marketplace catalog repository."""

    def __init__(self, session: AsyncSession):
        self.session = session

    def _to_domain(self, model: MarketplaceCatalogModel) -> MarketplaceCatalog:
        return MarketplaceCatalog(
            id=model.id,
            catalog_type=model.catalog_type,
            catalog_data=model.catalog_data or {},
            source_url=model.source_url,
            source_tag=model.source_tag,
            version=model.version,
            is_active=model.is_active,
            fetch_error=model.fetch_error,
            fetched_at=model.fetched_at,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    async def get_active(
        self, catalog_type: CatalogType
    ) -> Optional[MarketplaceCatalog]:
        # Only one catalog per type can be active at a time.
        stmt = select(MarketplaceCatalogModel).where(
            MarketplaceCatalogModel.catalog_type == catalog_type,
            MarketplaceCatalogModel.is_active == True,
        )
        result = await self.session.execute(stmt)
        model = result.scalars().first()
        return self._to_domain(model) if model else None

    async def get_by_id(self, catalog_id: uuid.UUID) -> Optional[MarketplaceCatalog]:
        stmt = select(MarketplaceCatalogModel).where(
            MarketplaceCatalogModel.id == catalog_id
        )
        result = await self.session.execute(stmt)
        model = result.scalars().first()
        return self._to_domain(model) if model else None

    async def list_all(
        self, catalog_type: Optional[CatalogType] = None, limit: int = 100
    ) -> List[MarketplaceCatalog]:
        stmt = (
            select(MarketplaceCatalogModel)
            .order_by(MarketplaceCatalogModel.created_at.desc())
            .limit(limit)
        )

        if catalog_type:
            stmt = stmt.where(MarketplaceCatalogModel.catalog_type == catalog_type)

        result = await self.session.execute(stmt)
        models = result.scalars().all()
        return [self._to_domain(model) for model in models]

    async def upsert_active(
        self,
        catalog_type: CatalogType,
        catalog_data: Dict[str, Any],
        source_url: Optional[str] = None,
        source_tag: Optional[str] = None,
    ) -> MarketplaceCatalog:
        # Deactivate all existing active catalogs of this type
        await self.session.execute(
            update(MarketplaceCatalogModel)
            .where(
                MarketplaceCatalogModel.catalog_type == catalog_type,
                MarketplaceCatalogModel.is_active == True,
            )
            .values(is_active=False, updated_at=datetime.now(UTC))
        )

        # Extract version from catalog data
        version = catalog_data.get("version")

        # Create new active catalog
        model = MarketplaceCatalogModel(
            id=uuid.uuid4(),
            catalog_type=catalog_type,
            catalog_data=catalog_data,
            source_url=source_url,
            source_tag=source_tag,
            version=version,
            is_active=True,
            fetch_error=None,
            fetched_at=datetime.now(UTC),
        )
        self.session.add(model)
        await self.session.commit()
        await self.session.refresh(model)

        logger.info(
            f"Upserted active {catalog_type.value} catalog: "
            f"version={version}, packages={len(catalog_data.get('packages', []))}"
        )

        return self._to_domain(model)

    async def set_fetch_error(
        self,
        catalog_type: CatalogType,
        error_message: str,
    ) -> None:
        # If no active catalog exists, creates a placeholder with the error.
        stmt = select(MarketplaceCatalogModel).where(
            MarketplaceCatalogModel.catalog_type == catalog_type,
            MarketplaceCatalogModel.is_active == True,
        )
        result = await self.session.execute(stmt)
        model = result.scalars().first()

        if model:
            model.fetch_error = error_message
            model.updated_at = datetime.now(UTC)
        else:
            # Create a placeholder catalog with the error
            model = MarketplaceCatalogModel(
                id=uuid.uuid4(),
                catalog_type=catalog_type,
                catalog_data={},
                is_active=True,
                fetch_error=error_message,
            )
            self.session.add(model)

        await self.session.commit()
        logger.warning(
            f"Set fetch error for {catalog_type.value} catalog: {error_message}"
        )

    async def delete(self, catalog_id: uuid.UUID) -> bool:
        stmt = select(MarketplaceCatalogModel).where(
            MarketplaceCatalogModel.id == catalog_id
        )
        result = await self.session.execute(stmt)
        model = result.scalars().first()

        if not model:
            return False

        await self.session.delete(model)
        await self.session.commit()
        return True
