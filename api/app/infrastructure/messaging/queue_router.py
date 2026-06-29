# api/app/infrastructure/messaging/queue_router.py

"""Routes jobs to worker queues. Resolution: service metadata → local_worker
→ provider default. No fallback - unroutable services fail at enqueue. Every queue
route is declared in the catalog (service client_metadata.queue, provider
local_worker.queue, or provider adapter-config.default_queue), never guessed here.
"""

import logging
from typing import Any, Dict, Optional

from app.domain.common.exceptions import DomainServiceError
from app.domain.queue.interfaces import (
    QueueRouter as QueueRouterABC,
    QueueRoutingContext,
)

logger = logging.getLogger(__name__)


class QueueRoutingError(DomainServiceError):
    pass


class QueueRouter(QueueRouterABC):
    def get_queue_name(self, context: QueueRoutingContext) -> str:
        """Resolve a queue name; raise QueueRoutingError if no rule matches."""
        service_id = context.service_id or ""

        if context.service_metadata:
            metadata_queue = context.service_metadata.get("queue")
            if metadata_queue:
                logger.debug(
                    f"Queue routing: service metadata '{service_id}' -> '{metadata_queue}'"
                )
                return metadata_queue

        if context.local_worker:
            if context.local_worker.get("enabled") and context.local_worker.get(
                "queue"
            ):
                queue = context.local_worker["queue"]
                logger.debug(f"Queue routing: local_worker '{service_id}' -> '{queue}'")
                return queue

        if context.provider_default_queue:
            logger.debug(
                f"Queue routing: provider default '{service_id}' -> '{context.provider_default_queue}'"
            )
            return context.provider_default_queue

        raise QueueRoutingError(
            f"No queue route for service '{service_id}'. "
            f"Declare the route in the catalog: add 'queue' to the service, "
            f"'local_worker.queue' to the provider, "
            f"or 'default_queue' to the provider's adapter-config."
        )

    def get_queue_name_simple(
        self,
        service_id: str,
        local_worker: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Convenience wrapper for get_queue_name when service metadata is unavailable."""
        context = QueueRoutingContext(
            service_id=service_id,
            local_worker=local_worker,
        )
        return self.get_queue_name(context)


_queue_router: Optional[QueueRouter] = None


def get_queue_router() -> QueueRouter:
    global _queue_router
    if _queue_router is None:
        _queue_router = QueueRouter()
    return _queue_router
