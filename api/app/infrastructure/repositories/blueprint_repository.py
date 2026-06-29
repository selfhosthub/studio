# api/app/infrastructure/repositories/blueprint_repository.py

"""SQLAlchemy implementation of the Blueprint repository."""
import uuid
from datetime import UTC, datetime
from typing import List, Optional

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.common.exceptions import EntityNotFoundError
from app.domain.common.json_serialization import deserialize_steps, serialize_steps
from app.domain.blueprint.models import Blueprint, BlueprintCategory, BlueprintStatus
from app.domain.blueprint.repository import BlueprintRepository
from app.infrastructure.persistence.models import BlueprintModel


class SQLAlchemyBlueprintRepository(BlueprintRepository):
    """SQLAlchemy implementation of the Blueprint repository."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, blueprint: Blueprint) -> Blueprint:
        model = BlueprintModel(
            id=blueprint.id,
            name=blueprint.name,
            description=blueprint.description,
            organization_id=blueprint.organization_id,
            created_by=blueprint.created_by,
            version=blueprint.version,
            status=blueprint.status,  # type: ignore[assignment]  - domain enum assigned to SQLAlchemy column; SA type stubs expect Column type
            category=blueprint.category,  # type: ignore[assignment]  - domain enum assigned to SQLAlchemy column; SA type stubs expect Column type
            steps=serialize_steps(blueprint.steps) if blueprint.steps else {},
            tags=blueprint.tags or [],
            client_metadata=blueprint.client_metadata or {},
            created_at=blueprint.created_at,
            updated_at=blueprint.updated_at,
        )

        self.session.add(model)
        await self.session.commit()
        await self.session.refresh(model)

        return self._to_domain(model)

    async def update(self, blueprint: Blueprint) -> Blueprint:
        stmt = select(BlueprintModel).where(BlueprintModel.id == blueprint.id)
        result = await self.session.execute(stmt)
        model = result.scalars().first()

        if not model:
            raise EntityNotFoundError(
                entity_type="Blueprint",
                entity_id=blueprint.id,
            )

        model.name = blueprint.name
        model.description = blueprint.description
        model.version = blueprint.version
        model.status = blueprint.status  # type: ignore[assignment]  - domain enum assigned to SQLAlchemy column; SA type stubs expect Column type
        model.category = blueprint.category  # type: ignore[assignment]  - domain enum assigned to SQLAlchemy column; SA type stubs expect Column type
        model.steps = serialize_steps(blueprint.steps) if blueprint.steps else {}
        model.tags = blueprint.tags or []
        model.client_metadata = blueprint.client_metadata or {}
        model.updated_at = blueprint.updated_at or datetime.now(UTC)

        await self.session.commit()
        await self.session.refresh(model)

        return self._to_domain(model)

    async def get_by_id(self, blueprint_id: uuid.UUID) -> Optional[Blueprint]:
        stmt = select(BlueprintModel).where(BlueprintModel.id == blueprint_id)
        result = await self.session.execute(stmt)
        model = result.scalars().first()

        if not model:
            return None

        return self._to_domain(model)

    async def get_by_name(
        self,
        organization_id: uuid.UUID,
        name: str,
    ) -> Optional[Blueprint]:
        stmt = select(BlueprintModel).where(
            BlueprintModel.organization_id == organization_id,
            BlueprintModel.name == name,
        )
        result = await self.session.execute(stmt)
        model = result.scalars().first()

        if not model:
            return None

        return self._to_domain(model)

    async def find_published_blueprints(
        self,
        organization_id: uuid.UUID,
        skip: int,
        limit: int,
    ) -> List[Blueprint]:
        stmt = select(BlueprintModel).where(
            BlueprintModel.organization_id == organization_id,
            BlueprintModel.status == BlueprintStatus.PUBLISHED,
        )

        stmt = stmt.offset(skip).limit(limit)

        result = await self.session.execute(stmt)
        models = result.scalars().all()

        return [self._to_domain(m) for m in models]

    async def find_blueprints_by_category(
        self,
        category: BlueprintCategory,
        skip: int,
        limit: int,
    ) -> List[Blueprint]:
        stmt = select(BlueprintModel).where(BlueprintModel.category == category)

        stmt = stmt.offset(skip).limit(limit)

        result = await self.session.execute(stmt)
        models = result.scalars().all()

        return [self._to_domain(m) for m in models]

    async def list_by_organization(
        self,
        organization_id: uuid.UUID,
        skip: int,
        limit: int,
        category: Optional[BlueprintCategory] = None,
        status: Optional[BlueprintStatus] = None,
    ) -> List[Blueprint]:
        stmt = select(BlueprintModel).where(
            BlueprintModel.organization_id == organization_id
        )

        if category is not None:
            stmt = stmt.where(BlueprintModel.category == category)

        if status is not None:
            stmt = stmt.where(BlueprintModel.status == status)

        stmt = stmt.offset(skip).limit(limit)

        result = await self.session.execute(stmt)
        models = result.scalars().all()

        return [self._to_domain(m) for m in models]

    async def search(
        self,
        query: str,
        skip: int,
        limit: int,
        organization_id: Optional[uuid.UUID] = None,
    ) -> List[Blueprint]:
        search_pattern = f"%{query}%"
        stmt = select(BlueprintModel).where(
            or_(
                BlueprintModel.name.ilike(search_pattern),
                BlueprintModel.description.ilike(search_pattern),
            )
        )

        if organization_id is not None:
            stmt = stmt.where(BlueprintModel.organization_id == organization_id)

        stmt = stmt.offset(skip).limit(limit)

        result = await self.session.execute(stmt)
        models = result.scalars().all()

        return [self._to_domain(m) for m in models]

    async def count_by_organization(
        self,
        organization_id: uuid.UUID,
        status: Optional[BlueprintStatus] = None,
    ) -> int:
        stmt = select(func.count(BlueprintModel.id)).where(
            BlueprintModel.organization_id == organization_id
        )

        if status is not None:
            stmt = stmt.where(BlueprintModel.status == status)

        result = await self.session.execute(stmt)
        return result.scalar() or 0

    async def exists(
        self,
        blueprint_id: uuid.UUID,
    ) -> bool:
        stmt = select(func.count(BlueprintModel.id)).where(
            BlueprintModel.id == blueprint_id
        )
        result = await self.session.execute(stmt)
        count = result.scalar() or 0
        return count > 0

    async def delete(self, blueprint_id: uuid.UUID) -> bool:
        stmt = select(BlueprintModel).where(BlueprintModel.id == blueprint_id)
        result = await self.session.execute(stmt)
        model = result.scalars().first()

        if not model:
            return False

        await self.session.delete(model)
        await self.session.commit()

        return True

    def _to_domain(self, model: BlueprintModel) -> Blueprint:
        steps = deserialize_steps(model.steps)

        return Blueprint(
            id=model.id,
            name=model.name,
            description=model.description,
            organization_id=model.organization_id,
            created_by=model.created_by,
            version=model.version,
            status=model.status,
            category=model.category,
            steps=steps,
            tags=model.tags,
            client_metadata=model.client_metadata,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
