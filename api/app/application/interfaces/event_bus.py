# api/app/application/interfaces/event_bus.py

"""Async event bus interface. Events are published after persistence."""

from abc import ABC, abstractmethod
from typing import Any, Callable

from app.domain.common.events import DomainEvent

EventHandler = Callable[[DomainEvent], Any]


class EventBus(ABC):
    @abstractmethod
    async def publish(self, event: DomainEvent) -> None:
        pass

    @abstractmethod
    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        pass

    @abstractmethod
    def unsubscribe(self, event_type: str, handler: EventHandler) -> None:
        pass
