# api/app/application/interfaces/message_queue.py

"""Async message queue interface for background jobs."""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
import uuid


class MessageQueue(ABC):
    @abstractmethod
    async def enqueue_job(
        self,
        queue_name: str,
        job_data: Dict[str, Any],
        priority: int = 0,
        delay_seconds: Optional[int] = None,
    ) -> bool:
        pass

    @abstractmethod
    async def enqueue_workflow_step(
        self,
        instance_id: uuid.UUID,
        step_id: str,
        execution_data: Dict[str, Any],
        retry_count: int = 0,
    ) -> bool:
        pass

    @abstractmethod
    async def enqueue_notification(
        self,
        notification_id: uuid.UUID,
        channel: str,
        recipient: str,
        payload: Dict[str, Any],
    ) -> bool:
        pass

    @abstractmethod
    async def enqueue_webhook(
        self,
        webhook_id: uuid.UUID,
        delivery_id: uuid.UUID,
        url: str,
        payload: Dict[str, Any],
        headers: Dict[str, str],
        retry_count: int = 0,
    ) -> bool:
        pass

    @abstractmethod
    async def dequeue_job(
        self,
        queue_name: str,
        worker_id: uuid.UUID,
        timeout_seconds: int = 30,
    ) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    async def acknowledge_job(
        self,
        queue_name: str,
        job_id: str,
        success: bool,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> bool:
        pass

    @abstractmethod
    async def get_queue_stats(
        self,
        queue_name: str,
    ) -> Dict[str, Any]:
        pass
