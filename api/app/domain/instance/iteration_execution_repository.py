# api/app/domain/instance/iteration_execution_repository.py

"""Repository interface for IterationExecution entities."""

import uuid
from abc import ABC, abstractmethod
from typing import List, Optional

from app.domain.instance.iteration_execution import (
    IterationExecution,
    IterationExecutionStatus,
)


class IterationExecutionRepository(ABC):
    """Persistence for per-iteration execution rows."""

    @abstractmethod
    async def create(
        self, iteration: IterationExecution, *, commit: bool = True
    ) -> IterationExecution:
        """commit=False when the caller owns the transaction boundary."""
        pass

    @abstractmethod
    async def create_many(
        self, iterations: List[IterationExecution], *, commit: bool = True
    ) -> List[IterationExecution]:
        pass

    @abstractmethod
    async def get_by_id(
        self, iteration_id: uuid.UUID
    ) -> Optional[IterationExecution]:
        pass

    @abstractmethod
    async def get_by_step_and_index(
        self,
        step_id: uuid.UUID,
        iteration_index: int,
        iteration_group_id: Optional[uuid.UUID] = None,
    ) -> Optional[IterationExecution]:
        """Lookup by (step_id, iteration_index[, group_id]); the tuple is uniquely indexed."""
        pass

    @abstractmethod
    async def list_by_step_id(
        self,
        step_id: uuid.UUID,
        status: Optional[IterationExecutionStatus] = None,
    ) -> List[IterationExecution]:
        """Ordered by iteration_index asc for deterministic aggregation."""
        pass

    @abstractmethod
    async def list_by_instance_id(
        self,
        instance_id: uuid.UUID,
        status: Optional[IterationExecutionStatus] = None,
    ) -> List[IterationExecution]:
        pass

    @abstractmethod
    async def update(
        self, iteration: IterationExecution, *, commit: bool = True
    ) -> IterationExecution:
        pass

    @abstractmethod
    async def delete(self, iteration_id: uuid.UUID) -> None:
        pass

    @abstractmethod
    async def delete_by_step_id(self, step_id: uuid.UUID) -> int:
        """Returns rows deleted."""
        pass
