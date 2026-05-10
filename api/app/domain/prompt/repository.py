# api/app/domain/prompt/repository.py

"""Repository interface for the prompt domain."""

import uuid
from abc import ABC, abstractmethod
from typing import List, Optional

from app.domain.prompt.models import Prompt, PromptSource


class PromptRepository(ABC):
    """Persistence operations for Prompts."""

    @abstractmethod
    async def create(self, prompt: Prompt) -> Prompt: ...

    @abstractmethod
    async def update(self, prompt: Prompt) -> Prompt: ...

    @abstractmethod
    async def get_by_id(self, prompt_id: uuid.UUID) -> Optional[Prompt]: ...

    @abstractmethod
    async def list_by_organization(
        self,
        organization_id: uuid.UUID,
        category: Optional[str] = None,
        enabled_only: bool = True,
    ) -> List[Prompt]: ...

    @abstractmethod
    async def delete(self, prompt_id: uuid.UUID) -> bool:
        """Returns True if deleted."""

    @abstractmethod
    async def get_by_marketplace_slug(
        self,
        slug: str,
        organization_id: uuid.UUID,
    ) -> Optional[Prompt]:
        """Lookup for idempotent install."""

    @abstractmethod
    async def list_by_source(self, source: PromptSource) -> List[Prompt]:
        """All prompts with a given source, across organizations."""

    @abstractmethod
    async def soft_delete_marketplace(self, prompt_id: uuid.UUID) -> None:
        """Mark uninstalled: source='uninstalled', is_enabled=False."""

    @abstractmethod
    async def reactivate_marketplace(self, prompt_id: uuid.UUID) -> None:
        """Re-activate a previously uninstalled marketplace prompt."""

    @abstractmethod
    async def list_all_by_marketplace_slug(self, slug: str) -> List[Prompt]: ...

    @abstractmethod
    async def list_marketplace_installed(self) -> List[Prompt]:
        """source='marketplace' with marketplace_slug set."""

    @abstractmethod
    async def list_personal_prompts(
        self,
        organization_id: uuid.UUID,
        created_by: uuid.UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Prompt]: ...

    @abstractmethod
    async def list_organization_prompts(
        self,
        organization_id: uuid.UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Prompt]: ...

    @abstractmethod
    async def list_pending_publish(
        self,
        organization_id: uuid.UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Prompt]: ...
