# api/app/domain/queue/interfaces.py

"""Domain interfaces for queue routing."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class QueueRoutingContext:
    """Inputs for queue routing decisions."""

    service_id: str
    local_worker: Optional[Dict[str, Any]] = None
    service_metadata: Optional[Dict[str, Any]] = None
    provider_default_queue: Optional[str] = None


class QueueRouter(ABC):
    """Routes jobs to worker queues. Every service must resolve to an explicit queue; there is no default fallback."""

    @abstractmethod
    def get_queue_name(self, context: QueueRoutingContext) -> str:
        """Raises QueueRoutingError when no route can be determined."""

    @abstractmethod
    def get_queue_name_simple(
        self,
        service_id: str,
        local_worker: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Routing without service metadata."""
