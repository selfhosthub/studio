# api/app/domain/common/interfaces.py

"""Domain-level interfaces for infrastructure services."""

from abc import ABC, abstractmethod
from typing import Any, Dict


class JobStatusPublisher(ABC):
    """Publishes job status updates."""

    @abstractmethod
    async def publish_status(self, status: Dict[str, Any]) -> None: ...

    @abstractmethod
    def get_queue_length(self, queue_name: str = "step_jobs") -> int: ...
