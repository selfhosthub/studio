# api/app/domain/common/base_entity.py

"""Base entity classes for domain objects."""
import uuid
from datetime import UTC, datetime
from typing import Any, List, Optional
from pydantic import BaseModel, ConfigDict, Field
from app.domain.common.events import DomainEvent


class Entity(BaseModel):
    """Base class for domain entities with identity."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    created_at: Optional[datetime] = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: Optional[datetime] = Field(default_factory=lambda: datetime.now(UTC))

    model_config = ConfigDict(arbitrary_types_allowed=True, from_attributes=True)

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, Entity):
            return False
        return self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)


class AggregateRoot(Entity):
    """Aggregate root: consistency boundary that emits domain events."""

    def __init__(self, **data: Any):
        super().__init__(**data)
        self._events: List[DomainEvent] = []

    def add_event(self, event: DomainEvent) -> None:
        self._events.append(event)

    def clear_events(self) -> List[DomainEvent]:
        if not hasattr(self, "_events"):
            self._events = []
        events = self._events.copy()
        self._events = []
        return events

    def get_pending_events(self) -> List[DomainEvent]:
        return self._events.copy()
