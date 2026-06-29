# api/app/infrastructure/scheduling/cleanup_task.py

"""Periodic cleanup callback: dead-letter replay → worker cleanup → stale-step sweep.

Replay runs first so results land in the DB before the sweep checks for staleness.
Each cycle opens a fresh session; failures in one step are logged and don't abort others.
"""

import logging
from typing import Any, Awaitable, Callable, Dict, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.services.dead_letter_replay_service import (
    DeadLetterReplayService,
)
from app.infrastructure.errors import safe_error_message
from app.application.services.result_processing.step_result_enrichment import (
    build_step_result_payload,
)
from app.application.services.instance_notifier import InstanceNotifier
from app.application.services.webhook_reconcile_sweep_service import (
    WebhookReconcileSweepService,
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


def _build_webhook_reconcile_sweep(
    session: AsyncSession,
    step_repo: SQLAlchemyStepExecutionRepository,
    notifier: Optional[InstanceNotifier],
) -> WebhookReconcileSweepService:
    """Assemble the WFW notify sweep, bound to one cleanup-cycle session.

    Notify-only (I-13): it fires the once-per-step "still awaiting provider
    callback" notification for WFW steps idle past their notify window. It never
    enqueues a poll or fails a step on a timer."""
    return WebhookReconcileSweepService(
        step_execution_repository=step_repo,
        instance_repository=SQLAlchemyInstanceRepository(session),
        notifier=notifier,
        session=session,
    )


def build_cleanup_callback(
    session_factory: async_sessionmaker[AsyncSession],
    notifier: Optional[InstanceNotifier] = None,
    process_result_fn: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
):
    """Build a zero-arg async cleanup callback for the scheduler.

    Captures dependencies at build time. Each invocation opens a fresh session.
    When process_result_fn is None, dead-letter replay is skipped (tests or cold startup).
    """

    async def _enrich_dead_letter(
        thin: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Resolve a thin worker payload to the full routing payload by
        job_id, mirroring the live /step-results endpoint. Returns None when
        the job can't be resolved (no job_id, malformed id, or job gone) so
        the replay drops the file instead of feeding the processor a payload
        with no step_id (Bug #2)."""
        job_id = thin.get("job_id")
        if not job_id:
            # Legacy / already-enriched payloads carry routing fields directly.
            if thin.get("step_id") and thin.get("instance_id"):
                return thin
            logger.error(
                "Dead-letter payload has no job_id and no routing fields; "
                "cannot route"
            )
            return None
        try:
            job_uuid = UUID(str(job_id))
        except (ValueError, TypeError):
            logger.error(f"Dead-letter payload has invalid job_id={job_id!r}")
            return None

        async with session_factory() as session:
            job_repo = SQLAlchemyQueuedJobRepository(session)
            job = await job_repo.get_by_id(job_uuid)

        if job is None:
            logger.warning(
                f"Dead-letter job {job_id} not found at replay time; "
                "cannot route, dropping"
            )
            return None

        return build_step_result_payload(
            job,
            status=thin.get("status", ""),
            result=thin.get("result"),
            error=thin.get("error"),
            webhook_pending=thin.get("webhook_pending", False),
        )

    async def _run_cleanup_cycle() -> None:
        # Step 1: Dead-letter replay. Enrichment resolves routing fields by
        # job_id (its own short-lived session per file); process_result opens
        # its own session for the actual result handling.
        if process_result_fn is not None:
            try:
                replay_service = DeadLetterReplayService(
                    process_result_fn=process_result_fn,
                    enrich_fn=_enrich_dead_letter,
                )
                await replay_service.replay()
            except Exception as e:
                logger.error(f"Dead-letter replay failed: {safe_error_message(e)}")

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
                    logger.error(f"Worker cleanup failed: {safe_error_message(e)}")

                try:
                    await _build_webhook_reconcile_sweep(
                        session, step_repo, notifier
                    ).reconcile_webhook_steps()
                except Exception as e:
                    logger.error(
                        f"Webhook notify sweep failed: {safe_error_message(e)}"
                    )
        except Exception as e:
            # Session factory itself failed (DB down, etc.) - log and move on
            logger.error(
                f"Cleanup cycle could not open session: {safe_error_message(e)}"
            )

    return _run_cleanup_cycle


__all__ = ["build_cleanup_callback"]
