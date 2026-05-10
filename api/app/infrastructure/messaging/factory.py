# api/app/infrastructure/messaging/factory.py

"""Factory functions for messaging components."""

from app.application.interfaces.event_bus import EventBus
from app.infrastructure.messaging.event_bus import InMemoryEventBus


def create_event_bus() -> EventBus:
    return InMemoryEventBus()
