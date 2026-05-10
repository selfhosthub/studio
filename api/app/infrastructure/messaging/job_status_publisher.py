# api/app/infrastructure/messaging/job_status_publisher.py

"""Publishes job-status updates for the result processor and progress tracking."""

import logging
from typing import Any, Awaitable, Callable, Dict

from app.domain.common.interfaces import JobStatusPublisher

logger = logging.getLogger(__name__)


class NullJobStatusPublisher(JobStatusPublisher):
    """No-op publisher used when no result processor is available."""

    async def publish_status(self, status: Dict[str, Any]) -> None:
        pass

    def get_queue_length(self, queue_name: str = "step_jobs") -> int:
        return 0


class DirectJobStatusPublisher(JobStatusPublisher):
    """Feeds inline results straight into the result processor - no queue hop."""

    def __init__(
        self,
        process_result_fn: Callable[[Dict[str, Any]], Awaitable[None]],
    ):
        self._process_result = process_result_fn

    async def publish_status(self, status: Dict[str, Any]) -> None:
        await self._process_result(status)

    def get_queue_length(self, queue_name: str = "step_jobs") -> int:
        return 0
