# api/app/infrastructure/scheduling/cleanup_task.py

"""Periodic cleanup callback: dead-letter replay → worker cleanup → stale-step sweep.

Replay runs first so results land in the DB before the sweep checks for staleness.
Each cycle opens a fresh session; failures in one step are logged and don't abort others.
"""

import logging
from typing import Any, Awaitable, Callable, Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.services.dead_letter_replay_service import (
    DeadLetterReplayService,
)
from app.application.services.instance_notifier import InstanceNotifier
from app.application.services.stale_step_sweep_service import (
    StaleStepSweepService,
)
from app.application.services.worker_cleanup_service import WorkerCleanupService
from app.infrastructure.repositories.instance_repository import (
    SQLAlchemyInstanceRepository,
)
from app.infrastructure.repositories.queue_job_repository import (
    SQLAlchemyQueuedJobRepository,
)
from app.infrastructure.repositories.step_execution_repository import (
    SQLAlchemyStepExecutionRepository,
)
from app.infrastructure.repositories.worker_repository import (
    SQLAlchemyWorkerRepository,
)

logger = logging.getLogger(__name__)


def build_cleanup_callback(
    session_factory: async_sessionmaker[AsyncSession],
    notifier: Optional[InstanceNotifier] = None,
    process_result_fn: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
):
    """Build a zero-arg async cleanup callback for the scheduler.

    Captures dependencies at build time. Each invocation opens a fresh session.
    When process_result_fn is None, dead-letter replay is skipped (tests or cold startup).
    """

    async def _run_cleanup_cycle() -> None:
        # Step 1: Dead-letter replay (no DB session needed - process_result
        # opens its own as part of normal result handling).
        if process_result_fn is not None:
            try:
                replay_service = DeadLetterReplayService(
                    process_result_fn=process_result_fn
                )
                await replay_service.replay()
            except Exception as e:
                logger.error(f"Dead-letter replay failed: {e}", exc_info=True)

        # Steps 2-3: DB-touching cleanup under one session.
        try:
            async with session_factory() as session:
                worker_repo = SQLAlchemyWorkerRepository(session)
                step_repo = SQLAlchemyStepExecutionRepository(session)
                job_repo = SQLAlchemyQueuedJobRepository(session)
                try:
                    await WorkerCleanupService(
                        worker_repository=worker_repo,
                        queued_job_repository=job_repo,
                        step_execution_repository=step_repo,
                    ).run_cleanup()
                except Exception as e:
                    logger.error(f"Worker cleanup failed: {e}", exc_info=True)

                try:
                    sweep = StaleStepSweepService(
                        session=session,
                        step_execution_repository=step_repo,
                        instance_repository=SQLAlchemyInstanceRepository(session),
                        notifier=notifier,
                    )
                    await sweep.sweep_stale_steps()
                except Exception as e:
                    logger.error(f"Stale step sweep failed: {e}", exc_info=True)
        except Exception as e:
            # Session factory itself failed (DB down, etc.) - log and move on
            logger.error(f"Cleanup cycle could not open session: {e}", exc_info=True)

    return _run_cleanup_cycle


__all__ = ["build_cleanup_callback"]
