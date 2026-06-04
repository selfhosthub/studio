# api/app/application/dtos/blueprint_dto.py

"""DTOs for blueprint operations."""

import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict

from app.domain.blueprint.models import Blueprint, BlueprintCategory, BlueprintStatus


class BlueprintBase(BaseModel):
    name: str
    description: Optional[str] = None
    category: BlueprintCategory = BlueprintCategory.GENERAL
    steps: Optional[Dict[str, Dict[str, Any]]] = None
    client_metadata: Optional[Dict[str, Any]] = None


class BlueprintCreate(BlueprintBase):
    """When organization_id is omitted it is derived from the caller's JWT;
    super-admins may set it explicitly to act on another tenant."""

    organization_id: Optional[uuid.UUID] = None
    created_by: Optional[uuid.UUID] = None


class BlueprintUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[BlueprintCategory] = None
    steps: Optional[Dict[str, Dict[str, Any]]] = None
    client_metadata: Optional[Dict[str, Any]] = None
    status: Optional[BlueprintStatus] = None


class BlueprintResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: Optional[str] = None
    organization_id: uuid.UUID
    created_by: Optional[uuid.UUID] = None
    category: BlueprintCategory
    status: BlueprintStatus
    version: int
    steps: Optional[Dict[str, Dict[str, Any]]] = None
    client_metadata: Optional[Dict[str, Any]] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_domain(cls, blueprint: Blueprint) -> "BlueprintResponse":
        steps = {}
        if blueprint.steps:
            for step_id, step_config in blueprint.steps.items():
                steps[step_id] = step_config.model_dump()

        return cls(
            id=blueprint.id,
            name=blueprint.name,
            description=blueprint.description,
            organization_id=blueprint.organization_id,
            created_by=blueprint.created_by,
            category=blueprint.category,
            status=blueprint.status,
            version=blueprint.version,
            steps=steps,
            client_metadata=blueprint.client_metadata,
            created_at=blueprint.created_at,
            updated_at=blueprint.updated_at,
        )
