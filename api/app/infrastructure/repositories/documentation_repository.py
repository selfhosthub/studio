# api/app/infrastructure/repositories/documentation_repository.py

"""SQLAlchemy implementation of DocumentationRepository.

documentation is NOT RLS-protected (global content, like providers and
site_content) - use a plain session. Mutations flush but do not commit;
the caller owns the transaction.
"""

from datetime import UTC, datetime
from typing import List, Optional
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.documentation.models import Documentation, DocType, DocVisibility
from app.domain.documentation.repository import DocumentationRepository
from app.infrastructure.persistence.models import DocumentationModel


class SQLAlchemyDocumentationRepository(DocumentationRepository):
    """Documentation repository backed by the documentation table."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(
        self, slug: str, doc_type: DocType, active_only: bool = True
    ) -> Optional[Documentation]:
        stmt = select(DocumentationModel).where(
            DocumentationModel.slug == slug,
            DocumentationModel.doc_type == doc_type,
        )
        if active_only:
            stmt = stmt.where(DocumentationModel.active.is_(True))
        result = await self.session.execute(stmt)
        model = result.scalars().first()
        return self._to_domain(model) if model else None

    async def list_by_type(
        self, doc_type: DocType, active_only: bool = True
    ) -> List[Documentation]:
        stmt = select(DocumentationModel).where(
            DocumentationModel.doc_type == doc_type
        )
        if active_only:
            stmt = stmt.where(DocumentationModel.active.is_(True))
        stmt = stmt.order_by(DocumentationModel.slug)
        result = await self.session.execute(stmt)
        return [self._to_domain(model) for model in result.scalars().all()]

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
        stmt = select(DocumentationModel).where(
            DocumentationModel.slug == slug,
            DocumentationModel.doc_type == doc_type,
        )
        result = await self.session.execute(stmt)
        model = result.scalars().first()
        if model:
            model.title = title
            model.description = description
            model.icon = icon
            model.content = content
            model.visibility = visibility
            model.source_tier = source_tier
            model.active = active
            model.updated_at = datetime.now(UTC)
        else:
            model = DocumentationModel(
                id=uuid4(),
                slug=slug,
                doc_type=doc_type,
                title=title,
                description=description,
                icon=icon,
                content=content,
                visibility=visibility,
                source_tier=source_tier,
                active=active,
            )
            self.session.add(model)
        await self.session.flush()
        return self._to_domain(model)

    async def set_active(self, slug: str, doc_type: DocType, active: bool) -> bool:
        stmt = select(DocumentationModel).where(
            DocumentationModel.slug == slug,
            DocumentationModel.doc_type == doc_type,
        )
        result = await self.session.execute(stmt)
        model = result.scalars().first()
        if not model:
            return False
        model.active = active
        model.updated_at = datetime.now(UTC)
        await self.session.flush()
        return True

    def _to_domain(self, model: DocumentationModel) -> Documentation:
        return Documentation(
            id=model.id,
            slug=model.slug,
            doc_type=model.doc_type,
            title=model.title,
            description=model.description,
            icon=model.icon,
            content=model.content,
            visibility=model.visibility,
            source_tier=model.source_tier,
            active=model.active,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
