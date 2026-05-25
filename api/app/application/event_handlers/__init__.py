# api/app/application/event_handlers/__init__.py

"""Domain-event handlers - side effects only (notifications, workspace dirs, etc.)."""

from typing import cast

from app.application.event_handlers.organization_handler import EVENT_HANDLERS
from app.application.interfaces.event_bus import EventBus, EventHandler

__all__ = ["register_event_handlers"]


def register_event_handlers(event_bus: EventBus) -> None:
    for event_cls, handler in EVENT_HANDLERS.items():
        # Subscribe using the event_type default - lookup keys must match publish keys.
        event_type_key = event_cls.model_fields["event_type"].default
        event_bus.subscribe(event_type_key, cast(EventHandler, handler))
