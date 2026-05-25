# api/app/infrastructure/repositories/queue_repository.py

"""SQLAlchemy implementation of Queue repository."""

import uuid
from datetime import UTC, datetime
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.common.exceptions import EntityNotFoundError
from app.domain.common.value_objects import ResourceRequirements
from app.domain.queue.models import Queue
from app.domain.queue.repository import QueueRepository
from app.infrastructure.persistence.models import QueueModel


class SQLAlchemyQueueRepository(QueueRepository):
    """SQLAlchemy implementation of queue repository."""

    def __init__(self, session: AsyncSession):
        self.session = session

    def _to_domain(self, model: QueueModel) -> Queue:
        # Handle ResourceRequirements conversion
        resource_req = None
        if model.resource_requirements:
            try:
                resource_req = ResourceRequirements(**model.resource_requirements)
            except (TypeError, ValueError):
                resource_req = None

        return Queue(
            id=model.id,
            name=model.name,
            description=model.description,
            organization_id=model.organization_id,
            queue_type=model.queue_type,
            status=model.status,
            max_concurrency=model.max_concurrency,
            max_pending_jobs=model.max_pending_jobs,
            default_timeout_seconds=model.default_timeout_seconds,
            resource_requirements=resource_req,
            tags=model.tags,
            client_metadata=model.client_metadata,
            created_at=model.created_at,
            updated_at=model.updated_at,
            created_by=model.created_by,
        )

    async def create(self, queue: Queue) -> Queue:
        """
        Create a new queue.

        Args:
            queue: The queue to create

        Returns:
            The created queue
        """
        db_queue = QueueModel(
            id=queue.id,
            name=queue.name,
            description=queue.description,
            organization_id=queue.organization_id,
            queue_type=queue.queue_type,  # type: ignore[assignment]  - domain enum assigned to SA column; SA type stubs expect Column type
            status=queue.status,  # type: ignore[assignment]  - domain enum assigned to SA column; SA type stubs expect Column type
            max_concurrency=queue.max_concurrency,
            max_pending_jobs=queue.max_pending_jobs,
            default_timeout_seconds=queue.default_timeout_seconds,
            resource_requirements=(
                queue.resource_requirements.model_dump()
                if queue.resource_requirements
                else None
            ),
            tags=queue.tags,
            client_metadata=queue.client_metadata,
            created_at=queue.created_at,
            updated_at=queue.updated_at or datetime.now(UTC),  # type: ignore[assignment]  - domain datetime assigned to SA column; SA type stubs expect Column type
            created_by=queue.created_by,
        )

        self.session.add(db_queue)
        await self.session.commit()
        await self.session.refresh(db_queue)

        return self._to_domain(db_queue)

    async def update(self, queue: Queue) -> Queue:
        """
        Update an existing queue.

        Args:
            queue: The queue to update

        Returns:
            The updated queue
        """
        stmt = select(QueueModel).where(QueueModel.id == queue.id)

        result = await self.session.execute(stmt)
        db_queue = result.scalars().first()

        if not db_queue:
            raise EntityNotFoundError(
                entity_type="Queue",
                entity_id=queue.id,
            )

        db_queue.name = queue.name
        db_queue.description = queue.description
        db_queue.queue_type = queue.queue_type  # type: ignore[assignment]  - domain enum assigned to SA column; SA type stubs expect Column type
        db_queue.status = queue.status  # type: ignore[assignment]  - domain enum assigned to SA column; SA type stubs expect Column type
        db_queue.max_concurrency = queue.max_concurrency
        db_queue.max_pending_jobs = queue.max_pending_jobs
        db_queue.default_timeout_seconds = queue.default_timeout_seconds
        db_queue.resource_requirements = (
            queue.resource_requirements.model_dump()
            if queue.resource_requirements
            else None
        )
        db_queue.tags = queue.tags
        db_queue.client_metadata = queue.client_metadata
        db_queue.updated_at = queue.updated_at or datetime.now(UTC)  # type: ignore[assignment]  - domain datetime assigned to SA column; SA type stubs expect Column type

        await self.session.commit()
        await self.session.refresh(db_queue)

        return self._to_domain(db_queue)

    async def get_by_id(self, queue_id: uuid.UUID) -> Optional[Queue]:
        """
        Retrieve a queue by its ID.

        Args:
            queue_id: The queue ID to retrieve

        Returns:
            The queue if found, None otherwise
        """
        stmt = select(QueueModel).where(QueueModel.id == queue_id)

        result = await self.session.execute(stmt)
        db_queue = result.scalars().first()

        if not db_queue:
            return None

        return self._to_domain(db_queue)

    async def get_by_name(
        self, name: str, organization_id: uuid.UUID
    ) -> Optional[Queue]:
        """
        Retrieve a queue by organization and name.

        Args:
            organization_id: The organization ID
            name: The queue name

        Returns:
            The queue if found, None otherwise
        """
        stmt = (
            select(QueueModel)
            .where(QueueModel.organization_id == organization_id)
            .where(QueueModel.name == name)
        )

        result = await self.session.execute(stmt)
        db_queue = result.scalars().first()

        if not db_queue:
            return None

        return self._to_domain(db_queue)

    async def list_by_organization(
        self,
        organization_id: uuid.UUID,
        skip: int,
        limit: int,
    ) -> List[Queue]:
        """
        List queues for an organization.

        Args:
            organization_id: The organization ID

        Returns:
            List of queues ordered by creation date (newest first)
        """
        stmt = (
            select(QueueModel)
            .where(QueueModel.organization_id == organization_id)
            .order_by(QueueModel.created_at.desc())
        )

        stmt = stmt.offset(skip).limit(limit)

        result = await self.session.execute(stmt)
        db_queues = result.scalars().all()

        return [self._to_domain(db_queue) for db_queue in db_queues]

    async def delete(self, queue_id: uuid.UUID) -> bool:
        """
        Delete a queue.

        Args:
            queue_id: The queue ID to delete

        Returns:
            True if deleted, False if not found
        """
        stmt = select(QueueModel).where(QueueModel.id == queue_id)

        result = await self.session.execute(stmt)
        db_queue = result.scalars().first()

        if not db_queue:
            return False

        await self.session.delete(db_queue)
        await self.session.commit()

        return True

    async def exists(self, queue_id: uuid.UUID) -> bool:
        """
        Check if a queue exists.

        Args:
            queue_id: The ID to check

        Returns:
            True if exists, False otherwise
        """
        stmt = select(QueueModel).where(QueueModel.id == queue_id)

        result = await self.session.execute(stmt)
        db_queue = result.scalars().first()

        return db_queue is not None
