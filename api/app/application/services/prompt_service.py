# api/app/application/services/prompt_service.py

"""
Application service for prompt operations.
"""

import re
import uuid
from typing import Dict, List, Optional

from app.application.dtos.prompt_dto import (
    ChunkDTO,
    PromptCreateDTO,
    PromptResponseDTO,
    PromptUpdateDTO,
    VariableDTO,
)
from app.domain.common.exceptions import (
    BusinessRuleViolation,
    EntityNotFoundError,
    PermissionDeniedError,
)
from app.domain.common.value_objects import PromptScope, Visibility
from app.domain.prompt.models import (
    Prompt,
    PromptChunk,
    PromptSource,
    PromptVariable,
)
from app.domain.prompt.repository import PromptRepository


_SLUG_BASENAME_RE = re.compile(r"[^a-z0-9]+")


def _derive_slug(org_slug: str, name: str) -> str:
    """Assemble the namespaced prompt slug from org slug + slugified name."""
    basename = _SLUG_BASENAME_RE.sub("-", name.lower()).strip("-") or "prompt"
    if not basename[0].isalpha():
        basename = f"p-{basename}"
    return f"{org_slug}/{basename}"


class PromptService:
    """Application service for prompt CRUD and assembly."""

    def __init__(self, repository: PromptRepository):
        self.repository = repository

    async def create_prompt(
        self,
        dto: PromptCreateDTO,
        organization_id: uuid.UUID,
        org_slug: str,
        source: PromptSource = PromptSource.CUSTOM,
        created_by: Optional[uuid.UUID] = None,
        scope: PromptScope = PromptScope.ORGANIZATION,
    ) -> PromptResponseDTO:
        prompt = Prompt.create(
            organization_id=organization_id,
            name=dto.name,
            slug=_derive_slug(org_slug, dto.name),
            description=dto.description,
            category=dto.category,
            chunks=[
                PromptChunk(
                    text=c.text, variable=c.variable, order=c.order, role=c.role
                )
                for c in dto.chunks
            ],
            variables=[
                PromptVariable(
                    name=v.name,
                    label=v.label,
                    type=v.type,
                    options=v.options,
                    option_labels=v.option_labels,
                    default=v.default,
                    required=v.required,
                )
                for v in dto.variables
            ],
            source=source,
            created_by=created_by,
            scope=scope,
        )

        created = await self.repository.create(prompt)
        return self._to_response(created)

    async def import_prompt(
        self,
        data: Dict[str, object],
        organization_id: uuid.UUID,
        org_slug: str,
        created_by: Optional[uuid.UUID] = None,
        scope: PromptScope = PromptScope.PERSONAL,
    ) -> tuple[PromptResponseDTO, List[str]]:
        """Create a prompt from a JSON payload.

        Accepts two shapes: the per-prompt export format (`name`, `chunks`) and
        the marketplace catalog format (`prompt.schema.json`: `display_name`,
        plus catalog-only `id`/`version`/`tier`/`author` which are ignored).
        Required after normalization are name and chunks. BusinessRuleViolation
        is allowlisted by safe_error_message so the message reaches the user;
        ValueError would be masked. Name collisions get a "(imported)" /
        "(imported N)" suffix. Returns (prompt, warnings).
        """
        # Normalize catalog format → name. display_name is the catalog field;
        # name is the export field. Either satisfies the requirement.
        raw_name = data.get("name") or data.get("display_name")
        if not raw_name:
            raise BusinessRuleViolation(
                "Prompt import must contain a 'name' or 'display_name' field"
            )
        if "chunks" not in data:
            raise BusinessRuleViolation("Prompt import must contain 'chunks' field")
        # category is schema-required for prompts - do not substitute a guess.
        if not data.get("category"):
            raise BusinessRuleViolation("Prompt import must contain a 'category' field")

        warnings: List[str] = []

        # Resolve a non-colliding name org-wide.
        base_name = str(raw_name)
        existing = await self.repository.list_by_organization(
            organization_id=organization_id,
            enabled_only=False,
        )
        existing_names = {p.name for p in existing}
        name = base_name
        if name in existing_names:
            name = f"{base_name} (imported)"
            counter = 2
            while name in existing_names:
                name = f"{base_name} (imported {counter})"
                counter += 1

        raw_chunks = data.get("chunks") or []
        raw_variables = data.get("variables") or []
        dto = PromptCreateDTO(
            name=name,
            description=data.get("description"),  # type: ignore[arg-type]
            category=str(data["category"]),
            chunks=[ChunkDTO(**c) for c in raw_chunks],  # type: ignore[misc]
            variables=[VariableDTO(**v) for v in raw_variables],  # type: ignore[misc]
        )

        created = await self.create_prompt(
            dto=dto,
            organization_id=organization_id,
            org_slug=org_slug,
            source=PromptSource.CUSTOM,
            created_by=created_by,
            scope=scope,
        )
        return created, warnings

    async def update_prompt(
        self,
        prompt_id: uuid.UUID,
        dto: PromptUpdateDTO,
        organization_id: uuid.UUID,
    ) -> PromptResponseDTO:
        prompt = await self.repository.get_by_id(prompt_id)
        if not prompt:
            raise EntityNotFoundError("Prompt", prompt_id)

        if prompt.organization_id != organization_id:
            raise PermissionDeniedError("Access denied")

        chunks = None
        if dto.chunks is not None:
            chunks = [
                PromptChunk(
                    text=c.text, variable=c.variable, order=c.order, role=c.role
                )
                for c in dto.chunks
            ]

        variables = None
        if dto.variables is not None:
            variables = [
                PromptVariable(
                    name=v.name,
                    label=v.label,
                    type=v.type,
                    options=v.options,
                    option_labels=v.option_labels,
                    default=v.default,
                    required=v.required,
                )
                for v in dto.variables
            ]

        prompt.update(
            name=dto.name,
            description=dto.description,
            category=dto.category,
            chunks=chunks,
            variables=variables,
            is_enabled=dto.is_enabled,
        )

        updated = await self.repository.update(prompt)
        return self._to_response(updated)

    async def delete_prompt(
        self,
        prompt_id: uuid.UUID,
        organization_id: uuid.UUID,
        actor_id: Optional[uuid.UUID] = None,
    ) -> None:
        prompt = await self.repository.get_by_id(prompt_id)
        if not prompt:
            raise EntityNotFoundError("Prompt", prompt_id)

        if prompt.organization_id != organization_id:
            raise PermissionDeniedError("Access denied")

        prompt.validate_can_be_deleted(actor_id)
        await self.repository.delete(prompt_id)

    async def list_prompts(
        self,
        organization_id: uuid.UUID,
        category: Optional[str] = None,
        scope: Optional[PromptScope] = None,
    ) -> List[PromptResponseDTO]:
        """List prompts in an org.

        scope=organization → only org-scoped prompts (mirrors the workflow
        Organization tab; keeps personal prompts out). scope omitted → all
        scopes (backward compatible).
        """
        if scope == PromptScope.ORGANIZATION:
            prompts = await self.repository.list_organization_prompts(
                organization_id=organization_id,
            )
            if category is not None:
                prompts = [p for p in prompts if p.category == category]
        else:
            prompts = await self.repository.list_by_organization(
                organization_id=organization_id,
                category=category,
                enabled_only=False,
            )
        return [self._to_response(p) for p in prompts]

    async def get_prompt(
        self, prompt_id: uuid.UUID, organization_id: uuid.UUID
    ) -> PromptResponseDTO:
        prompt = await self.repository.get_by_id(prompt_id)
        if not prompt:
            raise EntityNotFoundError("Prompt", prompt_id)

        if prompt.organization_id != organization_id:
            raise PermissionDeniedError("Access denied")

        return self._to_response(prompt)

    async def set_visibility(
        self, prompt_id: uuid.UUID, new_visibility: Visibility
    ) -> tuple[Visibility, PromptResponseDTO]:
        """Transition a prompt's cross-org marketplace visibility. Returns
        (old_visibility, updated). Authorization is enforced at the API
        boundary (super_admin-only)."""
        prompt = await self.repository.get_by_id(prompt_id)
        if not prompt:
            raise EntityNotFoundError("Prompt", prompt_id)
        old_visibility = prompt.set_visibility(new_visibility)
        updated = await self.repository.update(prompt)
        return old_visibility, self._to_response(updated)

    async def copy_prompt(
        self,
        prompt_id: uuid.UUID,
        organization_id: uuid.UUID,
        org_slug: str,
        created_by: uuid.UUID,
    ) -> PromptResponseDTO:
        prompt = await self.repository.get_by_id(prompt_id)
        if not prompt:
            raise EntityNotFoundError("Prompt", prompt_id)

        if prompt.organization_id != organization_id:
            raise PermissionDeniedError("Access denied")

        copy_name = f"{prompt.name} (copy)"
        copy = Prompt.create(
            organization_id=organization_id,
            name=copy_name,
            slug=_derive_slug(org_slug, copy_name),
            description=prompt.description,
            category=prompt.category,
            chunks=list(prompt.chunks),
            variables=list(prompt.variables),
            source=PromptSource.CUSTOM,
            created_by=created_by,
            scope=PromptScope.PERSONAL,
        )
        created = await self.repository.create(copy)
        return self._to_response(created)

    async def request_publish(
        self,
        prompt_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> PromptResponseDTO:
        prompt = await self.repository.get_by_id(prompt_id)
        if not prompt:
            raise EntityNotFoundError("Prompt", prompt_id)

        if prompt.created_by != user_id:
            raise PermissionDeniedError("Only the prompt owner can request publishing")

        prompt.request_publish()
        updated = await self.repository.update(prompt)
        return self._to_response(updated)

    async def approve_publish(self, prompt_id: uuid.UUID) -> PromptResponseDTO:
        prompt = await self.repository.get_by_id(prompt_id)
        if not prompt:
            raise EntityNotFoundError("Prompt", prompt_id)

        prompt.approve_publish()
        updated = await self.repository.update(prompt)
        return self._to_response(updated)

    async def reject_publish(self, prompt_id: uuid.UUID) -> PromptResponseDTO:
        prompt = await self.repository.get_by_id(prompt_id)
        if not prompt:
            raise EntityNotFoundError("Prompt", prompt_id)

        prompt.reject_publish()
        updated = await self.repository.update(prompt)
        return self._to_response(updated)

    async def assemble_prompt(
        self,
        prompt_id: uuid.UUID,
        variable_values: Dict[str, str],
        organization_id: uuid.UUID,
    ) -> List[Dict[str, str]]:
        prompt = await self.repository.get_by_id(prompt_id)
        if not prompt:
            raise EntityNotFoundError("Prompt", prompt_id)

        if prompt.organization_id != organization_id:
            raise PermissionDeniedError("Access denied")

        return prompt.assemble(variable_values)

    def _to_response(self, prompt: Prompt) -> PromptResponseDTO:
        return PromptResponseDTO(
            id=prompt.id,
            organization_id=prompt.organization_id,
            name=prompt.name,
            description=prompt.description,
            category=prompt.category,
            chunks=[
                ChunkDTO(text=c.text, variable=c.variable, order=c.order, role=c.role)
                for c in prompt.chunks
            ],
            variables=[
                VariableDTO(
                    name=v.name,
                    label=v.label,
                    type=v.type,
                    options=v.options,
                    option_labels=v.option_labels,
                    default=v.default,
                    required=v.required,
                )
                for v in prompt.variables
            ],
            is_enabled=prompt.is_enabled,
            source=prompt.source,
            slug=prompt.slug,
            created_by=prompt.created_by,
            scope=prompt.scope.value if prompt.scope else "organization",
            publish_status=prompt.publish_status.value if prompt.publish_status else None,
            visibility=(
                prompt.visibility.value
                if hasattr(prompt.visibility, "value")
                else "private"
            ),
            created_at=prompt.created_at,
            updated_at=prompt.updated_at,
        )
