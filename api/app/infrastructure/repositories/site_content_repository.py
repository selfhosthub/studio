# api/app/infrastructure/repositories/site_content_repository.py

"""SQLAlchemy implementation of site content repository."""

from datetime import UTC, datetime
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import attributes

from app.domain.site_content.models import SiteContent
from app.domain.site_content.repository import SiteContentRepository
from app.infrastructure.persistence.models import SiteContentModel


class SQLAlchemySiteContentRepository(SiteContentRepository):
    """SQLAlchemy implementation of site content repository."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_all(self) -> List[SiteContent]:
        stmt = select(SiteContentModel).order_by(SiteContentModel.page_id)
        result = await self.session.execute(stmt)
        models = result.scalars().all()

        return [self._to_domain(model) for model in models]

    async def get_by_page_id(self, page_id: str) -> Optional[SiteContent]:
        stmt = select(SiteContentModel).where(SiteContentModel.page_id == page_id)
        result = await self.session.execute(stmt)
        model = result.scalars().first()

        if not model:
            return None

        return self._to_domain(model)

    async def update_or_create(
        self, page_id: str, content: Dict[str, Any], updated_by: UUID
    ) -> SiteContent:
        stmt = select(SiteContentModel).where(SiteContentModel.page_id == page_id)
        result = await self.session.execute(stmt)
        model = result.scalars().first()

        if model:
            # Update existing
            model.content = content
            model.updated_by = updated_by
            model.updated_at = datetime.now(UTC)
        else:
            # Create new
            model = SiteContentModel(
                id=uuid4(),
                page_id=page_id,
                content=content,
                updated_by=updated_by,
            )
            self.session.add(model)

        await self.session.commit()
        await self.session.refresh(model)

        return self._to_domain(model)

    async def merge_content(
        self, page_id: str, key: str, value: Any, updated_by: UUID
    ) -> SiteContent:
        stmt = select(SiteContentModel).where(SiteContentModel.page_id == page_id)
        result = await self.session.execute(stmt)
        model = result.scalars().first()

        if model:
            # Merge with existing content
            existing = dict(model.content or {})
            existing[key] = value
            model.content = existing
            model.updated_by = updated_by
            model.updated_at = datetime.now(UTC)
            # Explicitly mark the content column as modified
            attributes.flag_modified(model, "content")
        else:
            # Create new with just this key
            model = SiteContentModel(
                id=uuid4(),
                page_id=page_id,
                content={key: value},
                updated_by=updated_by,
            )
            self.session.add(model)

        await self.session.commit()
        await self.session.refresh(model)

        return self._to_domain(model)

    def _to_domain(self, model: SiteContentModel) -> SiteContent:
        return SiteContent(
            id=model.id,
            page_id=model.page_id,
            content=model.content,
            updated_by=model.updated_by,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
