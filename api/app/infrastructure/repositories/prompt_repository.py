# api/app/infrastructure/repositories/prompt_repository.py

"""SQLAlchemy repository implementation for prompts."""

import uuid
from datetime import UTC, datetime
from typing import List, Optional

from sqlalchemy import select, update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.common.exceptions import EntityNotFoundError
from app.domain.common.value_objects import PromptPublishStatus, PromptScope
from app.domain.prompt.models import (
    Prompt,
    PromptChunk,
    PromptSource,
    PromptVariable,
)
from app.domain.prompt.repository import PromptRepository
from app.infrastructure.persistence.models import PromptModel


class SQLAlchemyPromptRepository(PromptRepository):

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, prompt: Prompt) -> Prompt:
        model = PromptModel(
            id=prompt.id,
            organization_id=prompt.organization_id,
            name=prompt.name,
            description=prompt.description,
            category=prompt.category,
            chunks=[c.model_dump() for c in prompt.chunks],
            variables=[v.model_dump() for v in prompt.variables],
            is_enabled=prompt.is_enabled,
            source=prompt.source,
            marketplace_slug=prompt.marketplace_slug,
            created_by=prompt.created_by,
            scope=prompt.scope,
            publish_status=prompt.publish_status,
            created_at=prompt.created_at,
            updated_at=prompt.updated_at,
        )

        self.session.add(model)
        await self.session.commit()
        await self.session.refresh(model)

        return self._to_domain(model)

    async def update(self, prompt: Prompt) -> Prompt:
        stmt = select(PromptModel).where(
            PromptModel.id == prompt.id
        )
        result = await self.session.execute(stmt)
        model = result.scalars().first()

        if not model:
            raise EntityNotFoundError(
                entity_type="Prompt",
                entity_id=prompt.id,
            )

        model.name = prompt.name
        model.description = prompt.description
        model.category = prompt.category
        model.chunks = [c.model_dump() for c in prompt.chunks]
        model.variables = [v.model_dump() for v in prompt.variables]
        model.is_enabled = prompt.is_enabled
        model.source = prompt.source  # type: ignore[assignment]
        model.marketplace_slug = prompt.marketplace_slug
        model.created_by = prompt.created_by
        model.scope = prompt.scope  # type: ignore[assignment]
        model.publish_status = prompt.publish_status  # type: ignore[assignment]
        model.updated_at = prompt.updated_at or datetime.now(UTC)

        await self.session.commit()
        await self.session.refresh(model)

        return self._to_domain(model)

    async def get_by_id(self, prompt_id: uuid.UUID) -> Optional[Prompt]:
        stmt = select(PromptModel).where(
            PromptModel.id == prompt_id
        )
        result = await self.session.execute(stmt)
        model = result.scalars().first()

        if not model:
            return None

        return self._to_domain(model)

    async def list_by_organization(
        self,
        organization_id: uuid.UUID,
        category: Optional[str] = None,
        enabled_only: bool = True,
    ) -> List[Prompt]:
        stmt = select(PromptModel).where(
            PromptModel.organization_id == organization_id,
            # Always exclude soft-deleted (uninstalled) marketplace prompts
            PromptModel.source != PromptSource.UNINSTALLED,
        )

        if category is not None:
            stmt = stmt.where(PromptModel.category == category)

        if enabled_only:
            stmt = stmt.where(PromptModel.is_enabled == True)  # noqa: E712 - SQLAlchemy requires == True for boolean column filter; is operator would not generate correct SQL

        stmt = stmt.order_by(PromptModel.name)

        result = await self.session.execute(stmt)
        models = result.scalars().all()

        return [self._to_domain(m) for m in models]

    async def delete(self, prompt_id: uuid.UUID) -> bool:
        stmt = select(PromptModel).where(
            PromptModel.id == prompt_id
        )
        result = await self.session.execute(stmt)
        model = result.scalars().first()

        if not model:
            return False

        await self.session.delete(model)
        await self.session.commit()

        return True

    async def get_by_marketplace_slug(
        self,
        slug: str,
        organization_id: uuid.UUID,
    ) -> Optional[Prompt]:
        stmt = select(PromptModel).where(
            PromptModel.organization_id == organization_id,
            PromptModel.marketplace_slug == slug,
        )
        result = await self.session.execute(stmt)
        model = result.scalars().first()

        if not model:
            return None

        return self._to_domain(model)

    async def list_by_source(self, source: PromptSource) -> List[Prompt]:
        stmt = (
            select(PromptModel)
            .where(PromptModel.source == source)
            .order_by(PromptModel.name)
        )
        result = await self.session.execute(stmt)
        models = result.scalars().all()
        return [self._to_domain(m) for m in models]

    async def soft_delete_marketplace(self, prompt_id: uuid.UUID) -> None:
        stmt = (
            sa_update(PromptModel)
            .where(PromptModel.id == prompt_id)
            .values(source=PromptSource.UNINSTALLED, is_enabled=False)
        )
        await self.session.execute(stmt)
        await self.session.commit()

    async def reactivate_marketplace(self, prompt_id: uuid.UUID) -> None:
        stmt = (
            sa_update(PromptModel)
            .where(PromptModel.id == prompt_id)
            .values(source=PromptSource.MARKETPLACE, is_enabled=True)
        )
        await self.session.execute(stmt)
        await self.session.commit()

    async def list_all_by_marketplace_slug(self, slug: str) -> List[Prompt]:
        stmt = select(PromptModel).where(
            PromptModel.marketplace_slug == slug,
            PromptModel.source == PromptSource.MARKETPLACE,
        )
        result = await self.session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    async def list_marketplace_installed(self) -> List[Prompt]:
        stmt = select(PromptModel).where(
            PromptModel.source == PromptSource.MARKETPLACE,
            PromptModel.marketplace_slug.isnot(None),
        )
        result = await self.session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    async def list_personal_prompts(
        self,
        organization_id: uuid.UUID,
        created_by: uuid.UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Prompt]:
        stmt = (
            select(PromptModel)
            .where(
                PromptModel.organization_id == organization_id,
                PromptModel.created_by == created_by,
                PromptModel.scope == PromptScope.PERSONAL,
            )
            .order_by(PromptModel.name)
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    async def list_organization_prompts(
        self,
        organization_id: uuid.UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Prompt]:
        stmt = (
            select(PromptModel)
            .where(
                PromptModel.organization_id == organization_id,
                PromptModel.scope == PromptScope.ORGANIZATION,
                PromptModel.source != PromptSource.UNINSTALLED,
            )
            .order_by(PromptModel.name)
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    async def list_pending_publish(
        self,
        organization_id: uuid.UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Prompt]:
        stmt = (
            select(PromptModel)
            .where(
                PromptModel.organization_id == organization_id,
                PromptModel.publish_status == PromptPublishStatus.PENDING,
            )
            .order_by(PromptModel.updated_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    def _to_domain(self, model: PromptModel) -> Prompt:
        chunks = [PromptChunk(**c) for c in (model.chunks or [])]
        variables = [PromptVariable(**v) for v in (model.variables or [])]

        return Prompt(
            id=model.id,
            organization_id=model.organization_id,
            name=model.name,
            description=model.description,
            category=model.category,
            chunks=chunks,
            variables=variables,
            is_enabled=model.is_enabled,
            source=model.source,
            marketplace_slug=model.marketplace_slug,
            created_by=model.created_by,
            scope=model.scope,
            publish_status=model.publish_status,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
