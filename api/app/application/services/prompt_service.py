# api/app/application/services/prompt_service.py

"""
Application service for prompt operations.
"""

import uuid
from typing import Dict, List, Optional

from app.application.dtos.prompt_dto import (
    ChunkDTO,
    PromptCreateDTO,
    PromptResponseDTO,
    PromptUpdateDTO,
    VariableDTO,
)
from app.domain.common.exceptions import EntityNotFoundError, PermissionDeniedError
from app.domain.common.value_objects import PromptScope
from app.domain.prompt.models import (
    Prompt,
    PromptChunk,
    PromptSource,
    PromptVariable,
)
from app.domain.prompt.repository import PromptRepository


class PromptService:
    """Application service for prompt CRUD and assembly."""

    def __init__(self, repository: PromptRepository):
        self.repository = repository

    async def create_prompt(
        self,
        dto: PromptCreateDTO,
        organization_id: uuid.UUID,
        source: PromptSource = PromptSource.CUSTOM,
    ) -> PromptResponseDTO:
        prompt = Prompt.create(
            organization_id=organization_id,
            name=dto.name,
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
        )

        created = await self.repository.create(prompt)
        return self._to_response(created)

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
        self, prompt_id: uuid.UUID, organization_id: uuid.UUID
    ) -> None:
        prompt = await self.repository.get_by_id(prompt_id)
        if not prompt:
            raise EntityNotFoundError("Prompt", prompt_id)

        if prompt.organization_id != organization_id:
            raise PermissionDeniedError("Access denied")

        await self.repository.delete(prompt_id)

    async def list_prompts(
        self,
        organization_id: uuid.UUID,
        category: Optional[str] = None,
    ) -> List[PromptResponseDTO]:
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

    async def copy_prompt(
        self,
        prompt_id: uuid.UUID,
        organization_id: uuid.UUID,
        created_by: uuid.UUID,
    ) -> PromptResponseDTO:
        prompt = await self.repository.get_by_id(prompt_id)
        if not prompt:
            raise EntityNotFoundError("Prompt", prompt_id)

        if prompt.organization_id != organization_id:
            raise PermissionDeniedError("Access denied")

        copy = Prompt.create(
            organization_id=organization_id,
            name=f"{prompt.name} (copy)",
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
            marketplace_slug=prompt.marketplace_slug,
            created_by=prompt.created_by,
            scope=prompt.scope.value if prompt.scope else "organization",
            publish_status=prompt.publish_status.value if prompt.publish_status else None,
            created_at=prompt.created_at,
            updated_at=prompt.updated_at,
        )
