# api/app/infrastructure/repositories/step_execution_repository.py

"""SQLAlchemy implementation of the step-execution repository."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import List, Optional

from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.common.exceptions import EntityNotFoundError
from app.domain.instance_step.models import StepExecutionStatus
from app.domain.instance_step.step_execution import StepExecution
from app.domain.instance_step.step_execution_repository import (
    StepExecutionRepository,
)
from app.infrastructure.persistence.models import StepExecutionModel


class SQLAlchemyStepExecutionRepository(StepExecutionRepository):
    """SQLAlchemy implementation of the unified step-execution repository."""

    def __init__(self, session: AsyncSession):
        self.session = session

    # ------------------------------------------------------------------
    # Create / update / delete
    # ------------------------------------------------------------------

    async def create(self, step: StepExecution) -> StepExecution:
        model = self._to_model(step)
        self.session.add(model)
        await self.session.flush()
        await self.session.refresh(model)
        await self.session.commit()
        return self._to_domain(model)

    async def create_many(
        self, steps: List[StepExecution]
    ) -> List[StepExecution]:
        models = [self._to_model(step) for step in steps]
        self.session.add_all(models)
        await self.session.flush()
        for model in models:
            await self.session.refresh(model)
        await self.session.commit()
        return [self._to_domain(model) for model in models]

    async def update(
        self,
        step: StepExecution,
        *,
        commit: bool = True,
    ) -> StepExecution:
        stmt = select(StepExecutionModel).where(StepExecutionModel.id == step.id)
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()

        if not model:
            raise EntityNotFoundError("StepExecution", step.id)

        # Lifecycle-side fields
        model.status = step.status
        model.output_data = step.output_data
        model.error_message = step.error_message
        model.started_at = step.started_at
        model.completed_at = step.completed_at

        # Worker-attempt fields
        model.result = step.result
        model.extracted_outputs = step.extracted_outputs
        model.retry_count = step.retry_count
        model.max_retries = step.max_retries
        model.execution_data = step.execution_data
        model.input_data = step.input_data
        model.request_body = step.request_body
        model.iteration_requests = step.iteration_requests

        # Phase pre-factor fields
        model.parameters = step.parameters
        model.active_operation = step.active_operation

        await self.session.flush()
        if commit:
            await self.session.refresh(model)
            await self.session.commit()
        return self._to_domain(model)

    async def delete(self, step_execution_id: uuid.UUID) -> None:
        stmt = delete(StepExecutionModel).where(
            StepExecutionModel.id == step_execution_id
        )
        await self.session.execute(stmt)
        await self.session.commit()

    async def delete_by_instance(self, instance_id: uuid.UUID) -> int:
        stmt = delete(StepExecutionModel).where(
            StepExecutionModel.instance_id == instance_id
        )
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.rowcount

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    async def get_by_id(
        self, step_execution_id: uuid.UUID
    ) -> Optional[StepExecution]:
        stmt = select(StepExecutionModel).where(
            StepExecutionModel.id == step_execution_id
        )
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model else None

    async def get_by_instance_and_key(
        self,
        instance_id: uuid.UUID,
        step_key: str,
    ) -> Optional[StepExecution]:
        stmt = select(StepExecutionModel).where(
            StepExecutionModel.instance_id == instance_id,
            StepExecutionModel.step_key == step_key,
        )
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model else None

    async def list_by_instance(
        self,
        instance_id: uuid.UUID,
        status: Optional[StepExecutionStatus] = None,
        skip: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> List[StepExecution]:
        stmt = select(StepExecutionModel).where(
            StepExecutionModel.instance_id == instance_id
        )
        if status:
            stmt = stmt.where(StepExecutionModel.status == status)
        stmt = stmt.order_by(StepExecutionModel.created_at)
        if skip is not None:
            stmt = stmt.offset(skip)
        if limit is not None:
            stmt = stmt.limit(limit)

        result = await self.session.execute(stmt)
        models = result.scalars().all()
        return [self._to_domain(model) for model in models]

    async def list_completed_by_instance(
        self, instance_id: uuid.UUID
    ) -> List[StepExecution]:
        stmt = (
            select(StepExecutionModel)
            .where(
                StepExecutionModel.instance_id == instance_id,
                StepExecutionModel.status.in_(
                    [
                        StepExecutionStatus.COMPLETED,
                        StepExecutionStatus.SKIPPED,
                    ]
                ),
            )
            .order_by(StepExecutionModel.created_at)
        )
        result = await self.session.execute(stmt)
        models = result.scalars().all()
        return [self._to_domain(model) for model in models]

    async def list_stale_steps(
        self, timeout_minutes: int
    ) -> List[StepExecution]:
        cutoff = datetime.now(UTC) - timedelta(minutes=timeout_minutes)
        stale_statuses = [
            StepExecutionStatus.QUEUED.value,
            StepExecutionStatus.RUNNING.value,
            StepExecutionStatus.PENDING.value,
        ]
        stmt = (
            select(StepExecutionModel)
            .where(
                StepExecutionModel.status.in_(stale_statuses),
                StepExecutionModel.updated_at < cutoff,
            )
            .order_by(StepExecutionModel.updated_at)
        )
        result = await self.session.execute(stmt)
        models = result.scalars().all()
        return [self._to_domain(model) for model in models]

    async def reset_to_queued(self, step_execution_ids: List[uuid.UUID]) -> int:
        from sqlalchemy import update

        if not step_execution_ids:
            return 0
        await self.session.execute(
            text("SELECT set_config('app.is_service_account', 'true', true)")
        )
        stmt = (
            update(StepExecutionModel)
            .where(StepExecutionModel.id.in_(step_execution_ids))
            .values(
                status=StepExecutionStatus.QUEUED.value,
                updated_at=datetime.now(UTC),
            )
        )
        result = await self.session.execute(stmt)
        return result.rowcount or 0

    async def claim_for_enqueue(
        self,
        instance_id: uuid.UUID,
        step_key: str,
    ) -> bool:
        stmt = (
            select(StepExecutionModel)
            .where(
                StepExecutionModel.instance_id == instance_id,
                StepExecutionModel.step_key == step_key,
            )
            .with_for_update(skip_locked=True)
        )
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None or model.status != StepExecutionStatus.PENDING.value:
            return False
        return True

    # ------------------------------------------------------------------
    # Model ⇄ domain mapping
    # ------------------------------------------------------------------

    def _to_model(self, step: StepExecution) -> StepExecutionModel:
        return StepExecutionModel(
            id=step.id,
            instance_id=step.instance_id,
            step_key=step.step_key,
            step_name=step.step_name,
            status=step.status,
            output_data=step.output_data,
            result=step.result,
            extracted_outputs=step.extracted_outputs,
            error_message=step.error_message,
            retry_count=step.retry_count,
            max_retries=step.max_retries,
            execution_data=step.execution_data,
            input_data=step.input_data,
            request_body=step.request_body,
            iteration_requests=step.iteration_requests,
            parameters=step.parameters,
            active_operation=step.active_operation,
            started_at=step.started_at,
            completed_at=step.completed_at,
            created_at=step.created_at,
            updated_at=step.updated_at,
        )

    def _to_domain(self, model: StepExecutionModel) -> StepExecution:
        return StepExecution(
            id=model.id,
            instance_id=model.instance_id,
            step_key=model.step_key,
            step_name=model.step_name,
            status=model.status,
            output_data=model.output_data or {},
            result=model.result,
            extracted_outputs=model.extracted_outputs or {},
            error_message=model.error_message,
            retry_count=model.retry_count,
            max_retries=model.max_retries,
            execution_data=model.execution_data or {},
            input_data=model.input_data or {},
            request_body=model.request_body,
            iteration_requests=model.iteration_requests,
            parameters=model.parameters or {},
            active_operation=model.active_operation,
            started_at=model.started_at,
            completed_at=model.completed_at,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
