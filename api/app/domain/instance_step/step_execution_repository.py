# api/app/domain/instance_step/step_execution_repository.py

"""Repository interface for the StepExecution aggregate."""

import uuid
from abc import ABC, abstractmethod
from typing import List, Optional

from app.domain.instance_step.models import StepExecutionStatus
from app.domain.instance_step.step_execution import StepExecution


class StepExecutionRepository(ABC):
    """Persistence operations for StepExecution aggregates."""

    @abstractmethod
    async def create(self, step: StepExecution) -> StepExecution: ...

    @abstractmethod
    async def create_many(
        self, steps: List[StepExecution]
    ) -> List[StepExecution]: ...

    @abstractmethod
    async def get_by_id(
        self, step_execution_id: uuid.UUID
    ) -> Optional[StepExecution]: ...

    @abstractmethod
    async def get_by_instance_and_key(
        self,
        instance_id: uuid.UUID,
        step_key: str,
    ) -> Optional[StepExecution]:
        """(instance_id, step_key) is the natural unique key."""

    @abstractmethod
    async def list_by_instance(
        self,
        instance_id: uuid.UUID,
        status: Optional[StepExecutionStatus] = None,
        skip: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> List[StepExecution]:
        """skip/limit accepted for legacy compatibility; one row per step per instance, so usually unused."""

    @abstractmethod
    async def list_completed_by_instance(
        self, instance_id: uuid.UUID
    ) -> List[StepExecution]:
        """Terminal-success steps (COMPLETED, SKIPPED), ordered by created_at asc for dependency-chain traversal."""

    @abstractmethod
    async def list_stale_steps(
        self, timeout_minutes: int
    ) -> List[StepExecution]:
        """QUEUED/RUNNING/PENDING older than the timeout. WAITING_*, STOPPED, BLOCKED are intentional holds and excluded."""

    @abstractmethod
    async def reset_to_queued(self, step_execution_ids: List[uuid.UUID]) -> int:
        """Reset the given steps to QUEUED so a live worker can pick them up."""

    @abstractmethod
    async def claim_for_enqueue(
        self,
        instance_id: uuid.UUID,
        step_key: str,
    ) -> bool:
        """Row-lock for enqueue without status change. True iff PENDING and lock acquired via FOR UPDATE SKIP LOCKED."""

    @abstractmethod
    async def update(
        self,
        step: StepExecution,
        *,
        commit: bool = True,
    ) -> StepExecution:
        """commit=False flushes without committing; caller owns the transaction boundary."""

    @abstractmethod
    async def delete(self, step_execution_id: uuid.UUID) -> None: ...

    @abstractmethod
    async def delete_by_instance(self, instance_id: uuid.UUID) -> int:
        """Returns the number of rows removed."""
