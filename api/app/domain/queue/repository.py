# api/app/domain/queue/repository.py

"""Repository interfaces for the queue domain."""

import uuid
from abc import ABC, abstractmethod
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from app.domain.instance_step.models import StepExecutionStatus
from app.domain.queue.models import Queue, QueuedJob, Worker

if TYPE_CHECKING:
    from app.infrastructure.repositories.queue_job_repository import OrphanedJobResult


class QueueRepository(ABC):
    """Persistence operations for Queue aggregates."""

    @abstractmethod
    async def create(self, queue: Queue) -> Queue: ...

    @abstractmethod
    async def update(self, queue: Queue) -> Queue: ...

    @abstractmethod
    async def get_by_id(self, queue_id: uuid.UUID) -> Optional[Queue]: ...

    @abstractmethod
    async def get_by_name(
        self, name: str, organization_id: uuid.UUID
    ) -> Optional[Queue]: ...

    @abstractmethod
    async def list_by_organization(
        self,
        organization_id: uuid.UUID,
        skip: int,
        limit: int,
    ) -> List[Queue]: ...

    @abstractmethod
    async def delete(self, queue_id: uuid.UUID) -> bool:
        """Returns True if deleted, False if not found."""

    @abstractmethod
    async def exists(self, queue_id: uuid.UUID) -> bool: ...


class QueuedJobRepository(ABC):
    """Persistence operations for QueuedJob aggregates."""

    @abstractmethod
    async def create(self, job: QueuedJob) -> QueuedJob: ...

    @abstractmethod
    async def update(self, job: QueuedJob) -> QueuedJob: ...

    @abstractmethod
    async def get_by_id(self, job_id: uuid.UUID) -> Optional[QueuedJob]: ...

    @abstractmethod
    async def get_claimed_job_by_worker(self, worker_id: uuid.UUID) -> Optional[QueuedJob]:
        """Return the RUNNING job currently assigned to this worker, or None."""

    @abstractmethod
    async def list_by_queue(
        self,
        skip: int,
        limit: int,
    ) -> List[QueuedJob]: ...

    @abstractmethod
    async def list_by_status(
        self,
        status: StepExecutionStatus,
        skip: int,
        limit: int,
    ) -> List[QueuedJob]: ...

    @abstractmethod
    async def get_next_pending_jobs(
        self,
        limit: int,
    ) -> List[QueuedJob]:
        """Pending jobs in priority order."""

    @abstractmethod
    async def count_by_status(
        self,
    ) -> Dict[StepExecutionStatus, int]: ...

    @abstractmethod
    async def cleanup_expired(
        self,
        before: datetime,
    ) -> int:
        """Delete jobs older than before; returns count removed."""

    @abstractmethod
    async def delete(self, job_id: uuid.UUID) -> bool:
        """Returns True if deleted, False if not found."""

    @abstractmethod
    async def delete_by_instance(self, instance_id: uuid.UUID) -> int:
        """Delete all queued jobs for a given instance; returns count removed."""

    @abstractmethod
    async def exists(self, job_id: uuid.UUID) -> bool: ...

    @abstractmethod
    async def claim_next_pending_by_queue_name(
        self,
        queue_name: str,
        worker_id: str,
    ) -> Optional[QueuedJob]:
        """Atomically claim the next pending job from the named queue."""

    @abstractmethod
    async def complete_job(
        self,
        job_id: uuid.UUID,
        output_data: Dict[str, Any],
    ) -> Optional[QueuedJob]: ...

    @abstractmethod
    async def fail_job(
        self,
        job_id: uuid.UUID,
        error_message: str,
    ) -> Optional[QueuedJob]: ...

    @abstractmethod
    async def requeue_orphaned_jobs(self) -> "OrphanedJobResult":
        """Reset RUNNING jobs whose worker_id is absent from the workers table.

        Jobs within retry limit are reset to PENDING; exhausted jobs are failed.
        """


class WorkerRepository(ABC):
    """Persistence operations for Worker aggregates."""

    @abstractmethod
    async def create(self, worker: Worker) -> Worker: ...

    @abstractmethod
    async def update(self, worker: Worker) -> Worker: ...

    @abstractmethod
    async def get_by_id(self, worker_id: uuid.UUID) -> Optional[Worker]: ...

    @abstractmethod
    async def list_by_queue(
        self,
        queue_id: uuid.UUID,
        skip: int,
        limit: int,
    ) -> List[Worker]: ...

    @abstractmethod
    async def list_active_workers(
        self,
        skip: int,
        limit: int,
        queue_id: Optional[uuid.UUID] = None,
    ) -> List[Worker]:
        """Workers with heartbeats within the last 3 minutes."""

    @abstractmethod
    async def delete(self, worker_id: uuid.UUID) -> bool:
        """Returns True if deleted, False if not found."""

    @abstractmethod
    async def exists(self, worker_id: uuid.UUID) -> bool: ...

    @abstractmethod
    async def get_stale_workers(
        self,
        heartbeat_timeout_minutes: int = 3,
    ) -> List[Worker]:
        """Workers with stale heartbeats not yet deregistered."""

    @abstractmethod
    async def mark_workers_as_deregistered(
        self,
        worker_ids: List[uuid.UUID],
    ) -> int:
        """Returns number of workers marked as deregistered."""
