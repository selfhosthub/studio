# api/app/infrastructure/messaging/queue_router.py

"""Routes jobs to worker queues. Resolution: override → service metadata → local_worker
→ prefix mapping → provider default. No silent fallback - unroutable services fail at enqueue.
"""

import logging
from typing import Any, Dict, Optional

from app.domain.common.exceptions import DomainServiceError
from app.domain.queue.interfaces import (
    QueueRouter as QueueRouterABC,
    QueueRoutingContext,
)

logger = logging.getLogger(__name__)

# Fallback prefix mappings for self-hosted (shs-*) providers without local_worker.queue.
PREFIX_QUEUE_MAPPINGS: Dict[str, str] = {
    "shs-comfyui.": "comfyui_image_jobs",
    "shs-mmaudio.": "mmaudio_jobs",
    "shs-ltxvideo.": "ltxvideo_jobs",
    "shs-wan.": "wan_jobs",
}

# Per-service overrides for cases where one service needs a different queue
# than its provider's default.
SERVICE_QUEUE_OVERRIDES: Dict[str, str] = {
    "shs-comfyui.comfyui_imgedit": "comfyui_image_edit_jobs",
}


class QueueRoutingError(DomainServiceError):
    pass


class QueueRouter(QueueRouterABC):
    def get_queue_name(self, context: QueueRoutingContext) -> str:
        """Resolve a queue name; raise QueueRoutingError if no rule matches."""
        service_id = context.service_id or ""

        if service_id in SERVICE_QUEUE_OVERRIDES:
            queue = SERVICE_QUEUE_OVERRIDES[service_id]
            logger.debug(f"Queue routing: service override '{service_id}' -> '{queue}'")
            return queue

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

        for prefix, queue in PREFIX_QUEUE_MAPPINGS.items():
            if service_id.startswith(prefix):
                logger.debug(f"Queue routing: prefix match '{service_id}' -> '{queue}'")
                return queue

        if context.provider_default_queue:
            logger.debug(
                f"Queue routing: provider default '{service_id}' -> '{context.provider_default_queue}'"
            )
            return context.provider_default_queue

        raise QueueRoutingError(
            f"No queue route for service '{service_id}'. "
            f"Add client_metadata.queue to the service's adapter-config, "
            f"add default_queue to the provider's adapter-config, "
            f"or add a PREFIX_QUEUE_MAPPINGS entry for this provider."
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
