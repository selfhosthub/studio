# api/app/application/services/worker_cleanup_service.py

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Optional

from app.config.settings import settings

if TYPE_CHECKING:
    from app.domain.instance_step.step_execution_repository import StepExecutionRepository
    from app.domain.queue.repository import QueuedJobRepository, WorkerRepository

logger = logging.getLogger(__name__)


class WorkerCleanupService:
    """Cleanup stale workers and requeue jobs orphaned by vanished workers."""

    def __init__(
        self,
        worker_repository: "WorkerRepository",
        queued_job_repository: "Optional[QueuedJobRepository]" = None,
        step_execution_repository: "Optional[StepExecutionRepository]" = None,
    ):
        self.worker_repository = worker_repository
        self.queued_job_repository = queued_job_repository
        self.step_execution_repository = step_execution_repository

    async def cleanup_stale_workers(self) -> int:
        """Mark workers with stale heartbeats as deregistered."""
        try:
            stale_workers = await self.worker_repository.get_stale_workers(
                heartbeat_timeout_minutes=settings.WORKER_HEARTBEAT_TIMEOUT_MINUTES
            )

            if not stale_workers:
                logger.debug("No stale workers found")
                return 0

            worker_ids = [w.id for w in stale_workers]
            count = await self.worker_repository.mark_workers_as_deregistered(worker_ids)

            logger.info(
                f"Marked {count} stale workers as deregistered "
                f"(heartbeat > {settings.WORKER_HEARTBEAT_TIMEOUT_MINUTES} min)"
            )
            return count

        except Exception as e:
            logger.error(f"Error cleaning up stale workers: {e}")
            raise

    async def requeue_orphaned_jobs(self) -> dict[str, int]:
        """Requeue RUNNING jobs whose worker has vanished from the workers table.

        Only fires if both queued_job_repository and step_execution_repository
        were provided at construction time.

        Returns dict with requeued and failed counts.
        """
        if self.queued_job_repository is None or self.step_execution_repository is None:
            return {"requeued": 0, "failed": 0}

        try:
            r = await self.queued_job_repository.requeue_orphaned_jobs()

            if r.requeued_step_ids:
                await self.step_execution_repository.reset_to_queued(r.requeued_step_ids)

            if r.requeued or r.failed:
                logger.info(
                    f"Orphaned job requeue: {r.requeued} requeued, {r.failed} failed "
                    "(retry limit exhausted)"
                )

            return {"requeued": r.requeued, "failed": r.failed}

        except Exception as e:
            logger.error(f"Error requeueing orphaned jobs: {e}")
            raise

    async def delete_old_deregistered_workers(self) -> int:
        return 0

    async def run_cleanup(self) -> dict[str, Any]:
        logger.debug("Starting worker cleanup cycle")

        stale_count = await self.cleanup_stale_workers()
        orphan_result = await self.requeue_orphaned_jobs()
        deleted_count = await self.delete_old_deregistered_workers()

        result = {
            "stale_deregistered": stale_count,
            "orphaned_requeued": orphan_result["requeued"],
            "orphaned_failed": orphan_result["failed"],
            "old_deleted": deleted_count,
            "timestamp": datetime.now(UTC).isoformat(),
        }

        logger.debug(f"Worker cleanup complete: {result}")
        return result
