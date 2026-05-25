# api/app/infrastructure/messaging/event_bus.py

"""Event bus implementations for domain events."""

import asyncio
import logging
from typing import Any, Callable, Dict, List

from app.application.interfaces.event_bus import EventBus
from app.domain.common.events import DomainEvent

EventHandler = Callable[[DomainEvent], Any]


class BaseEventBus(EventBus):
    """Shared subscription and dispatch logic for event bus implementations."""

    def __init__(self):
        self._handlers: Dict[str, List[EventHandler]] = {}
        self._logger = logging.getLogger(__name__)

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        if event_type not in self._handlers:
            self._handlers[event_type] = []

        self._handlers[event_type].append(handler)
        self._logger.debug(f"Subscribed handler to {event_type}: {handler.__name__}")

    def unsubscribe(self, event_type: str, handler: EventHandler) -> None:
        if event_type in self._handlers:
            try:
                self._handlers[event_type].remove(handler)
                self._logger.debug(
                    f"Unsubscribed handler from {event_type}: {handler.__name__}"
                )
            except ValueError:
                self._logger.warning(
                    f"Handler not found for {event_type}: {handler.__name__}"
                )

    def subscribe_to_all(self, handler: EventHandler) -> None:
        """Subscribe to every event type via the "*" wildcard."""
        self.subscribe("*", handler)
        self._logger.debug(f"Subscribed handler to all events: {handler.__name__}")

    async def _execute_handler(self, handler: EventHandler, event: DomainEvent) -> None:
        try:
            result = handler(event)
            if asyncio.iscoroutine(result):
                await result
        except Exception as e:
            self._logger.error(
                f"Error executing event handler {handler.__name__} for event {event.event_type}: {str(e)}"
            )

    def _get_handlers_for_event(self, event_type: str) -> List[EventHandler]:
        handlers: List[EventHandler] = []

        if event_type in self._handlers:
            type_handlers: List[EventHandler] = self._handlers[event_type]
            handlers.extend(type_handlers)

        if "*" in self._handlers:
            global_handlers: List[EventHandler] = self._handlers["*"]
            handlers.extend(global_handlers)

        return handlers

    async def _publish_to_handlers(self, event: DomainEvent) -> None:
        event_type = event.event_type
        self._logger.debug(
            f"Publishing event {event_type} with aggregate ID {event.aggregate_id}"
        )

        handlers = self._get_handlers_for_event(event_type)

        if handlers:
            await asyncio.gather(
                *[self._execute_handler(handler, event) for handler in handlers]
            )
        else:
            # Some events (e.g. worker.heartbeat) intentionally have no handlers.
            self._logger.debug(f"No handlers registered for event type: {event_type}")


class InMemoryEventBus(BaseEventBus):
    """In-process event bus - handlers run asynchronously in the current process."""

    async def publish(self, event: DomainEvent) -> None:
        await self._publish_to_handlers(event)
