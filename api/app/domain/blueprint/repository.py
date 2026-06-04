# api/app/domain/blueprint/repository.py

"""Repository interface for the Blueprint aggregate."""
import uuid
from abc import ABC, abstractmethod
from typing import List, Optional

from app.domain.blueprint.models import Blueprint, BlueprintStatus, BlueprintCategory


class BlueprintRepository(ABC):
    """Persistence repository for blueprint aggregates."""

    @abstractmethod
    async def create(self, blueprint: Blueprint) -> Blueprint:
        """Create a new blueprint."""

    @abstractmethod
    async def update(self, blueprint: Blueprint) -> Blueprint:
        """Update an existing blueprint."""

    @abstractmethod
    async def get_by_id(self, blueprint_id: uuid.UUID) -> Optional[Blueprint]:
        """Retrieve a blueprint by its ID."""

    @abstractmethod
    async def get_by_name(
        self,
        organization_id: uuid.UUID,
        name: str,
    ) -> Optional[Blueprint]:
        """Get a blueprint by name within an organization."""

    @abstractmethod
    async def find_published_blueprints(
        self,
        organization_id: uuid.UUID,
        skip: int,
        limit: int,
    ) -> List[Blueprint]:
        """Find published blueprints for an organization."""

    @abstractmethod
    async def find_blueprints_by_category(
        self,
        category: BlueprintCategory,
        skip: int,
        limit: int,
    ) -> List[Blueprint]:
        """Find blueprints by category."""

    @abstractmethod
    async def list_by_organization(
        self,
        organization_id: uuid.UUID,
        skip: int,
        limit: int,
        category: Optional[BlueprintCategory] = None,
        status: Optional[BlueprintStatus] = None,
    ) -> List[Blueprint]:
        """List blueprints by organization with optional filters."""

    @abstractmethod
    async def search(
        self,
        query: str,
        skip: int,
        limit: int,
        organization_id: Optional[uuid.UUID] = None,
    ) -> List[Blueprint]:
        """Search blueprints by query string."""

    @abstractmethod
    async def count_by_organization(
        self,
        organization_id: uuid.UUID,
        status: Optional[BlueprintStatus] = None,
    ) -> int:
        """Count blueprints for an organization."""

    @abstractmethod
    async def exists(
        self,
        blueprint_id: uuid.UUID,
    ) -> bool:
        """Check if a blueprint exists."""

    @abstractmethod
    async def delete(self, blueprint_id: uuid.UUID) -> bool:
        """Delete a blueprint. Returns True if deleted, False if not found."""
