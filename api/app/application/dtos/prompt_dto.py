# api/app/application/dtos/prompt_dto.py

"""DTOs for prompt operations."""

import uuid
from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class ChunkDTO(BaseModel):
    text: str
    variable: Optional[str] = None
    order: int = 0
    role: Optional[str] = None


class VariableDTO(BaseModel):
    name: str
    label: str
    type: str = "string"
    options: Optional[List[str]] = None
    option_labels: Optional[List[str]] = None
    default: Optional[str] = None
    required: bool = False


class PromptCreateDTO(BaseModel):
    name: str = Field(..., min_length=1)
    description: Optional[str] = None
    category: str = "general"
    chunks: List[ChunkDTO] = Field(default_factory=list)
    variables: List[VariableDTO] = Field(default_factory=list)


class PromptUpdateDTO(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    chunks: Optional[List[ChunkDTO]] = None
    variables: Optional[List[VariableDTO]] = None
    is_enabled: Optional[bool] = None


class PromptResponseDTO(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    description: Optional[str] = None
    category: str
    chunks: List[ChunkDTO]
    variables: List[VariableDTO]
    is_enabled: bool
    source: str
    marketplace_slug: Optional[str] = None
    created_by: Optional[uuid.UUID] = None
    scope: str = "organization"
    publish_status: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class AssembleRequestDTO(BaseModel):
    variable_values: Dict[str, str] = Field(default_factory=dict)
