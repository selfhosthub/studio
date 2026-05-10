# api/app/infrastructure/repositories/iteration_execution_repository.py

"""SQLAlchemy implementation of IterationExecution repository."""

import uuid
from typing import List, Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.common.exceptions import EntityNotFoundError
from app.domain.instance.iteration_execution import (
    IterationExecution,
    IterationExecutionStatus,
)
from app.domain.instance.iteration_execution_repository import (
    IterationExecutionRepository,
)
from app.infrastructure.persistence.models import IterationExecutionModel


class SQLAlchemyIterationExecutionRepository(IterationExecutionRepository):
    """SQLAlchemy implementation of iteration execution repository."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self, iteration: IterationExecution, *, commit: bool = True
    ) -> IterationExecution:
        model = self._to_model(iteration)
        self.session.add(model)
        await self.session.flush()
        if commit:
            await self.session.refresh(model)
            await self.session.commit()
        return self._to_domain(model)

    async def create_many(
        self, iterations: List[IterationExecution], *, commit: bool = True
    ) -> List[IterationExecution]:
        models = [self._to_model(iteration) for iteration in iterations]
        self.session.add_all(models)
        await self.session.flush()
        if commit:
            for model in models:
                await self.session.refresh(model)
            await self.session.commit()
        return [self._to_domain(model) for model in models]

    async def get_by_id(
        self, iteration_id: uuid.UUID
    ) -> Optional[IterationExecution]:
        stmt = select(IterationExecutionModel).where(
            IterationExecutionModel.id == iteration_id
        )
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model else None

    async def get_by_step_and_index(
        self,
        step_id: uuid.UUID,
        iteration_index: int,
        iteration_group_id: Optional[uuid.UUID] = None,
    ) -> Optional[IterationExecution]:
        stmt = select(IterationExecutionModel).where(
            IterationExecutionModel.step_id == step_id,
            IterationExecutionModel.iteration_index == iteration_index,
        )
        if iteration_group_id is not None:
            stmt = stmt.where(
                IterationExecutionModel.iteration_group_id == iteration_group_id
            )
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model else None

    async def list_by_step_id(
        self,
        step_id: uuid.UUID,
        status: Optional[IterationExecutionStatus] = None,
    ) -> List[IterationExecution]:
        stmt = select(IterationExecutionModel).where(
            IterationExecutionModel.step_id == step_id
        )
        if status is not None:
            stmt = stmt.where(IterationExecutionModel.status == status)
        stmt = stmt.order_by(IterationExecutionModel.iteration_index)
        result = await self.session.execute(stmt)
        models = result.scalars().all()
        return [self._to_domain(model) for model in models]

    async def list_by_instance_id(
        self,
        instance_id: uuid.UUID,
        status: Optional[IterationExecutionStatus] = None,
    ) -> List[IterationExecution]:
        stmt = select(IterationExecutionModel).where(
            IterationExecutionModel.instance_id == instance_id
        )
        if status is not None:
            stmt = stmt.where(IterationExecutionModel.status == status)
        stmt = stmt.order_by(
            IterationExecutionModel.step_id,
            IterationExecutionModel.iteration_index,
        )
        result = await self.session.execute(stmt)
        models = result.scalars().all()
        return [self._to_domain(model) for model in models]

    async def update(
        self, iteration: IterationExecution, *, commit: bool = True
    ) -> IterationExecution:
        stmt = select(IterationExecutionModel).where(
            IterationExecutionModel.id == iteration.id
        )
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        if not model:
            raise EntityNotFoundError("IterationExecution", iteration.id)

        model.status = iteration.status
        model.parameters = iteration.parameters
        model.result = iteration.result
        model.error = iteration.error
        model.started_at = iteration.started_at
        model.completed_at = iteration.completed_at

        await self.session.flush()
        if commit:
            await self.session.refresh(model)
            await self.session.commit()
        return self._to_domain(model)

    async def delete(self, iteration_id: uuid.UUID) -> None:
        stmt = delete(IterationExecutionModel).where(
            IterationExecutionModel.id == iteration_id
        )
        await self.session.execute(stmt)
        await self.session.commit()

    async def delete_by_step_id(self, step_id: uuid.UUID) -> int:
        stmt = delete(IterationExecutionModel).where(
            IterationExecutionModel.step_id == step_id
        )
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.rowcount

    def _to_model(self, iteration: IterationExecution) -> IterationExecutionModel:
        return IterationExecutionModel(
            id=iteration.id,
            instance_id=iteration.instance_id,
            step_id=iteration.step_id,
            iteration_index=iteration.iteration_index,
            iteration_group_id=iteration.iteration_group_id,
            status=iteration.status,
            parameters=iteration.parameters,
            result=iteration.result,
            error=iteration.error,
            started_at=iteration.started_at,
            completed_at=iteration.completed_at,
            created_at=iteration.created_at,
            updated_at=iteration.updated_at,
        )

    def _to_domain(self, model: IterationExecutionModel) -> IterationExecution:
        return IterationExecution(
            id=model.id,
            instance_id=model.instance_id,
            step_id=model.step_id,
            iteration_index=model.iteration_index,
            iteration_group_id=model.iteration_group_id,
            status=model.status,
            parameters=model.parameters or {},
            result=model.result,
            error=model.error,
            started_at=model.started_at,
            completed_at=model.completed_at,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
