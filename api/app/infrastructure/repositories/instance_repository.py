# api/app/infrastructure/repositories/instance_repository.py

"""SQLAlchemy repository implementation for workflow instances."""
import uuid
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import inspect, select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import attributes, selectinload

from app.domain.common.exceptions import EntityNotFoundError
from app.domain.instance.models import InstanceStatus, Instance
from app.domain.instance.repository import InstanceRepository
from app.domain.instance_step.step_execution import StepExecution
from app.infrastructure.persistence.models import (
    InstanceModel,
    StepExecutionModel,
    WorkflowModel,
)


class SQLAlchemyInstanceRepository(InstanceRepository):
    """SQLAlchemy implementation of the workflow-instance repository."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, instance: Instance) -> Instance:
        instance_model = InstanceModel(
            id=instance.id,
            workflow_id=instance.workflow_id,
            organization_id=instance.organization_id,
            status=instance.status,
            version=instance.version,
            input_data=instance.input_data,
            output_data=instance.output_data,
            client_metadata=instance.client_metadata,
            started_at=instance.started_at,
            completed_at=instance.completed_at,
            current_step_ids=instance.current_step_ids,
            workflow_snapshot=instance.workflow_snapshot,
            is_debug_mode=instance.is_debug_mode,
            created_at=instance.created_at,
            updated_at=instance.updated_at,
        )

        self.session.add(instance_model)
        await self.session.commit()
        await self.session.refresh(instance_model)

        return self._to_domain(instance_model)

    async def update(self, instance: Instance, *, commit: bool = True) -> Instance:
        stmt = select(InstanceModel).where(InstanceModel.id == instance.id)
        result = await self.session.execute(stmt)
        instance_model = result.scalars().first()

        if not instance_model:
            raise EntityNotFoundError(
                entity_type="Instance",
                entity_id=instance.id,
                code=f"Instance with ID {instance.id} not found",
            )

        # SQLAlchemy's type stubs don't recognize str-based Enum inheritance
        instance_model.status = instance.status  # type: ignore[assignment]
        instance_model.version = instance.version
        instance_model.input_data = instance.input_data
        instance_model.output_data = instance.output_data
        instance_model.client_metadata = instance.client_metadata
        instance_model.started_at = instance.started_at
        instance_model.completed_at = instance.completed_at
        instance_model.current_step_ids = instance.current_step_ids
        instance_model.failed_step_ids = instance.failed_step_ids
        instance_model.error_data = instance.error_data
        instance_model.workflow_snapshot = instance.workflow_snapshot
        instance_model.is_debug_mode = instance.is_debug_mode

        # Mark JSON columns as modified to ensure SQLAlchemy detects in-place mutations
        attributes.flag_modified(instance_model, "output_data")

        instance_model.updated_at = instance.updated_at or datetime.now(UTC)  # type: ignore[assignment]

        if commit:
            await self.session.commit()
            await self.session.refresh(instance_model)
        else:
            await self.session.flush()

        return self._to_domain(instance_model)

    async def get_by_id(self, instance_id: uuid.UUID) -> Optional[Instance]:
        stmt = (
            select(InstanceModel, WorkflowModel.name)
            .join(WorkflowModel, InstanceModel.workflow_id == WorkflowModel.id)
            .where(InstanceModel.id == instance_id)
            .options(selectinload(InstanceModel.step_executions))
        )
        result = await self.session.execute(stmt)
        row = result.first()

        if not row:
            return None

        instance_model, workflow_name = row
        return self._to_domain(instance_model, workflow_name)

    async def get_instance_summary(self, instance_id: uuid.UUID) -> Optional[Instance]:
        return await self.get_by_id(instance_id)

    async def find_running_instances(
        self,
        organization_id: uuid.UUID,
        skip: int,
        limit: int,
    ) -> List[Instance]:
        stmt = (
            select(InstanceModel, WorkflowModel.name)
            .join(WorkflowModel, InstanceModel.workflow_id == WorkflowModel.id)
            .where(
                InstanceModel.organization_id == organization_id,
                InstanceModel.status == InstanceStatus.PROCESSING,
            )
            .options(selectinload(InstanceModel.step_executions))
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        rows = result.all()
        return [
            self._to_domain(instance_model, workflow_name)
            for instance_model, workflow_name in rows
        ]

    async def find_instances_by_workflow(
        self,
        workflow_id: uuid.UUID,
        skip: int,
        limit: int,
    ) -> List[Instance]:
        stmt = (
            select(InstanceModel, WorkflowModel.name)
            .join(WorkflowModel, InstanceModel.workflow_id == WorkflowModel.id)
            .where(InstanceModel.workflow_id == workflow_id)
            .options(selectinload(InstanceModel.step_executions))
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        rows = result.all()
        return [
            self._to_domain(instance_model, workflow_name)
            for instance_model, workflow_name in rows
        ]

    async def find_instances_requiring_attention(
        self,
        organization_id: uuid.UUID,
        skip: int,
        limit: int,
    ) -> List[Instance]:
        stmt = (
            select(InstanceModel, WorkflowModel.name)
            .join(WorkflowModel, InstanceModel.workflow_id == WorkflowModel.id)
            .where(
                InstanceModel.organization_id == organization_id,
                InstanceModel.status.in_(
                    [InstanceStatus.FAILED, InstanceStatus.PAUSED]
                ),
            )
            .options(selectinload(InstanceModel.step_executions))
        )
        result = await self.session.execute(stmt)
        rows = result.all()
        return [
            self._to_domain(instance_model, workflow_name)
            for instance_model, workflow_name in rows
        ]

    async def list_by_workflow(
        self,
        workflow_id: uuid.UUID,
        skip: int,
        limit: int,
        status: Optional[InstanceStatus] = None,
        statuses: Optional[List[InstanceStatus]] = None,
    ) -> List[Instance]:
        stmt = (
            select(InstanceModel, WorkflowModel.name)
            .join(WorkflowModel, InstanceModel.workflow_id == WorkflowModel.id)
            .where(InstanceModel.workflow_id == workflow_id)
            .options(selectinload(InstanceModel.step_executions))
        )

        if statuses:
            stmt = stmt.where(InstanceModel.status.in_(statuses))
        elif status is not None:
            stmt = stmt.where(InstanceModel.status == status)

        stmt = stmt.offset(skip).limit(limit)

        result = await self.session.execute(stmt)
        rows = result.all()
        return [
            self._to_domain(instance_model, workflow_name)
            for instance_model, workflow_name in rows
        ]

    async def list_by_organization(
        self,
        organization_id: uuid.UUID,
        skip: int,
        limit: int,
        status: Optional[InstanceStatus] = None,
        statuses: Optional[List[InstanceStatus]] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> List[Instance]:
        stmt = (
            select(InstanceModel, WorkflowModel.name)
            .join(WorkflowModel, InstanceModel.workflow_id == WorkflowModel.id)
            .where(InstanceModel.organization_id == organization_id)
            .options(selectinload(InstanceModel.step_executions))
        )

        if statuses:
            stmt = stmt.where(InstanceModel.status.in_(statuses))
        elif status is not None:
            stmt = stmt.where(InstanceModel.status == status)
        if start_date is not None:
            stmt = stmt.where(InstanceModel.created_at >= start_date)
        if end_date is not None:
            stmt = stmt.where(InstanceModel.created_at <= end_date)

        stmt = (
            stmt.order_by(InstanceModel.created_at.desc())
            .offset(skip)
            .limit(limit)
        )

        result = await self.session.execute(stmt)
        rows = result.all()
        return [
            self._to_domain(instance_model, workflow_name)
            for instance_model, workflow_name in rows
        ]

    async def count_by_status(
        self,
        organization_id: uuid.UUID,
        status: InstanceStatus,
    ) -> int:
        stmt = (
            select(func.count())
            .select_from(InstanceModel)
            .where(
                InstanceModel.organization_id == organization_id,
                InstanceModel.status == status,
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar() or 0

    async def count_by_organization(
        self,
        organization_id: uuid.UUID,
        status: Optional[InstanceStatus] = None,
        statuses: Optional[List[InstanceStatus]] = None,
    ) -> int:
        stmt = (
            select(func.count())
            .select_from(InstanceModel)
            .where(InstanceModel.organization_id == organization_id)
        )
        if statuses:
            stmt = stmt.where(InstanceModel.status.in_(statuses))
        elif status is not None:
            stmt = stmt.where(InstanceModel.status == status)
        result = await self.session.execute(stmt)
        return result.scalar() or 0

    async def count_running_by_workflow(self, workflow_id: uuid.UUID) -> int:
        stmt = (
            select(func.count())
            .select_from(InstanceModel)
            .where(
                InstanceModel.workflow_id == workflow_id,
                InstanceModel.status == InstanceStatus.PROCESSING,
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar() or 0

    async def get_waiting_for_webhook(
        self, workflow_id: uuid.UUID
    ) -> Optional[Instance]:
        stmt = (
            select(InstanceModel, WorkflowModel.name)
            .join(WorkflowModel, InstanceModel.workflow_id == WorkflowModel.id)
            .where(
                InstanceModel.workflow_id == workflow_id,
                InstanceModel.status == InstanceStatus.WAITING_FOR_WEBHOOK,
            )
            .options(selectinload(InstanceModel.step_executions))
            .limit(1)
        )
        result = await self.session.execute(stmt)
        row = result.first()
        if not row:
            return None
        instance_model, workflow_name = row
        return self._to_domain(instance_model, workflow_name)

    async def delete(self, instance_id: uuid.UUID) -> bool:
        stmt = select(InstanceModel).where(InstanceModel.id == instance_id)
        result = await self.session.execute(stmt)
        instance_model = result.scalars().first()
        if not instance_model:
            return False
        await self.session.delete(instance_model)
        await self.session.commit()
        return True

    async def exists(self, instance_id: uuid.UUID) -> bool:
        stmt = select(InstanceModel.id).where(InstanceModel.id == instance_id)
        result = await self.session.execute(stmt)
        return result.scalars().first() is not None

    async def atomic_complete_step(
        self,
        instance_id: uuid.UUID,
        step_id: str,
        step_output: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Atomically remove the step from the active-step list and store per-step output under output_data['steps']."""
        stmt = (
            select(InstanceModel)
            .where(InstanceModel.id == instance_id)
            .with_for_update()
        )
        result = await self.session.execute(stmt)
        instance_model = result.scalars().first()
        if not instance_model:
            return

        current = list(instance_model.current_step_ids or [])
        if step_id in current:
            current.remove(step_id)
            instance_model.current_step_ids = current

        if step_output is not None:
            data = dict(instance_model.output_data or {})
            steps = dict(data.get("steps") or {})
            steps[step_id] = step_output
            data["steps"] = steps
            instance_model.output_data = data
            attributes.flag_modified(instance_model, "output_data")

        await self.session.commit()

    # ------------------------------------------------------------------
    # Model ⇄ domain mapping
    # ------------------------------------------------------------------

    @staticmethod
    def _step_model_to_domain(step_model: StepExecutionModel) -> StepExecution:
        return StepExecution(
            id=step_model.id,
            instance_id=step_model.instance_id,
            step_key=step_model.step_key,
            step_name=step_model.step_name,
            status=step_model.status,
            output_data=step_model.output_data or {},
            result=step_model.result,
            extracted_outputs=step_model.extracted_outputs or {},
            error_message=step_model.error_message,
            retry_count=step_model.retry_count,
            max_retries=step_model.max_retries,
            execution_data=step_model.execution_data or {},
            input_data=step_model.input_data or {},
            request_body=step_model.request_body,
            iteration_requests=step_model.iteration_requests,
            parameters=step_model.parameters or {},
            active_operation=step_model.active_operation,
            started_at=step_model.started_at,
            completed_at=step_model.completed_at,
            created_at=step_model.created_at,
            updated_at=step_model.updated_at,
        )

    def _to_domain(
        self, model: InstanceModel, workflow_name: Optional[str] = None
    ) -> Instance:
        # Build step_entities from eagerly-loaded step_executions relationship.
        step_entities: Dict[str, StepExecution] = {}
        state = inspect(model, raiseerr=False)
        steps_loaded = (
            state and "step_executions" not in state.unloaded if state else False
        )
        if steps_loaded and model.step_executions:
            for step_model in model.step_executions:
                step_entities[step_model.step_key] = self._step_model_to_domain(
                    step_model
                )

        # Compute completed_step_ids from step entities
        completed_step_ids = [
            key
            for key, entity in step_entities.items()
            if entity.allows_dependency_start()
        ]

        instance = Instance(
            id=model.id,
            workflow_id=model.workflow_id,
            organization_id=model.organization_id,
            workflow_name=workflow_name,
            status=model.status,
            version=model.version,
            input_data=model.input_data,
            output_data=model.output_data,
            client_metadata=model.client_metadata,
            started_at=model.started_at,
            completed_at=model.completed_at,
            current_step_ids=model.current_step_ids,
            workflow_snapshot=model.workflow_snapshot,
            failed_step_ids=model.failed_step_ids or [],
            error_data=model.error_data,
            is_debug_mode=model.is_debug_mode,
            created_at=model.created_at,
            updated_at=model.updated_at,
            completed_step_ids=completed_step_ids,
        )
        instance.step_entities = step_entities
        return instance
