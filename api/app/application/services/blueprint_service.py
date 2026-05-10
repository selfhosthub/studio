# api/app/application/services/blueprint_service.py

"""Blueprint orchestration. Business logic lives in the domain model."""
import uuid
from typing import Any, Dict, List, Optional

from app.application.dtos import (
    BlueprintCreate,
    BlueprintResponse,
    BlueprintUpdate,
)
from app.application.interfaces import EventBus, EntityNotFoundError
from app.domain.common.value_objects import StepConfig
from app.domain.organization.repository import OrganizationRepository
from app.domain.blueprint.models import Blueprint, BlueprintStatus, BlueprintCategory
from app.domain.blueprint.repository import BlueprintRepository


class BlueprintService:
    def __init__(
        self,
        blueprint_repository: BlueprintRepository,
        organization_repository: OrganizationRepository,
        event_bus: EventBus,
    ):
        self.blueprint_repository = blueprint_repository
        self.organization_repository = organization_repository
        self.event_bus = event_bus

    async def create_blueprint(self, command: BlueprintCreate) -> BlueprintResponse:
        assert command.organization_id is not None, "organization_id is required"

        organization = await self.organization_repository.get_by_id(
            command.organization_id
        )
        if not organization:
            raise EntityNotFoundError(
                entity_type="Organization",
                entity_id=uuid.uuid4(),
                code=f"Organization {command.organization_id} not found",
            )

        steps_dict = None
        if command.steps:
            steps_dict = {}
            for step_id, step_config_dict in command.steps.items():
                steps_dict[step_id] = StepConfig(**step_config_dict)

        blueprint = Blueprint.create(
            name=command.name,
            organization_id=command.organization_id,
            created_by=command.created_by,
            description=command.description,
            category=(
                BlueprintCategory(command.category)
                if command.category
                else BlueprintCategory.GENERAL
            ),
            client_metadata=command.client_metadata,
            steps=steps_dict,
        )

        events = blueprint.clear_events()

        blueprint = await self.blueprint_repository.create(blueprint)
        for event in events:
            await self.event_bus.publish(event)

        return BlueprintResponse.from_domain(blueprint)

    async def update_blueprint(
        self, blueprint_id: uuid.UUID, command: BlueprintUpdate
    ) -> BlueprintResponse:
        blueprint = await self.blueprint_repository.get_by_id(blueprint_id)
        if not blueprint:
            raise EntityNotFoundError(
                entity_type="Blueprint",
                entity_id=uuid.uuid4(),
                code=f"Blueprint {blueprint_id} not found",
            )

        if command.steps is not None:
            blueprint.steps = {}
            for step_id, step_config_dict in command.steps.items():
                step_config = StepConfig(**step_config_dict)
                blueprint.steps[step_id] = step_config

        blueprint.update(
            name=command.name,
            description=command.description,
            category=(
                BlueprintCategory(command.category) if command.category else None
            ),
            client_metadata=command.client_metadata,
            status=BlueprintStatus(command.status) if command.status else None,
        )

        events = blueprint.clear_events()

        blueprint = await self.blueprint_repository.update(blueprint)

        for event in events:
            await self.event_bus.publish(event)

        return BlueprintResponse.from_domain(blueprint)

    async def publish_blueprint(
        self,
        blueprint_id: uuid.UUID,
    ) -> BlueprintResponse:
        blueprint = await self.blueprint_repository.get_by_id(blueprint_id)
        if not blueprint:
            raise EntityNotFoundError(
                entity_type="Blueprint",
                entity_id=uuid.uuid4(),
                code=f"Blueprint {blueprint_id} not found",
            )

        blueprint.publish()

        events = blueprint.clear_events()

        blueprint = await self.blueprint_repository.update(blueprint)
        for event in events:
            await self.event_bus.publish(event)

        return BlueprintResponse.from_domain(blueprint)

    async def archive_blueprint(
        self, blueprint_id: uuid.UUID, archived_by: uuid.UUID
    ) -> BlueprintResponse:
        blueprint = await self.blueprint_repository.get_by_id(blueprint_id)
        if not blueprint:
            raise EntityNotFoundError(
                entity_type="Blueprint",
                entity_id=uuid.uuid4(),
                code=f"Blueprint {blueprint_id} not found",
            )

        blueprint.archive()

        events = blueprint.clear_events()

        blueprint = await self.blueprint_repository.update(blueprint)

        for event in events:
            await self.event_bus.publish(event)

        return BlueprintResponse.from_domain(blueprint)

    async def delete_blueprint(
        self, blueprint_id: uuid.UUID, force: bool = False
    ) -> bool:
        """Delete a blueprint; force=True bypasses the draft/archived guard."""
        from app.domain.common.exceptions import BusinessRuleViolation

        blueprint = await self.blueprint_repository.get_by_id(blueprint_id)
        if not blueprint:
            raise EntityNotFoundError(
                entity_type="Blueprint",
                entity_id=blueprint_id,
                code=f"Blueprint {blueprint_id} not found",
            )

        if not force and blueprint.status not in [
            BlueprintStatus.DRAFT,
            BlueprintStatus.ARCHIVED,
        ]:
            raise BusinessRuleViolation(
                f"Blueprint must be draft or archived before deletion. Current status: {blueprint.status.value}"
            )

        return await self.blueprint_repository.delete(blueprint_id)

    async def add_step(
        self,
        blueprint_id: uuid.UUID,
        step_id: str,
        step_config: Dict[str, Any],
        added_by: uuid.UUID,
    ) -> BlueprintResponse:
        blueprint = await self.blueprint_repository.get_by_id(blueprint_id)
        if not blueprint:
            raise EntityNotFoundError(
                entity_type="Blueprint",
                entity_id=uuid.uuid4(),
                code=f"Blueprint {blueprint_id} not found",
            )

        blueprint.add_step_from_dict(step_id, step_config)

        blueprint = await self.blueprint_repository.update(blueprint)

        return BlueprintResponse.from_domain(blueprint)

    async def remove_step(
        self, blueprint_id: uuid.UUID, step_id: str, removed_by: uuid.UUID
    ) -> BlueprintResponse:
        blueprint = await self.blueprint_repository.get_by_id(blueprint_id)
        if not blueprint:
            raise EntityNotFoundError(
                entity_type="Blueprint",
                entity_id=uuid.uuid4(),
                code=f"Blueprint {blueprint_id} not found",
            )

        blueprint.remove_step(step_id)

        blueprint = await self.blueprint_repository.update(blueprint)

        return BlueprintResponse.from_domain(blueprint)

    async def update_step(
        self,
        blueprint_id: uuid.UUID,
        step_id: str,
        step_config: Dict[str, Any],
        updated_by: uuid.UUID,
    ) -> BlueprintResponse:
        blueprint = await self.blueprint_repository.get_by_id(blueprint_id)
        if not blueprint:
            raise EntityNotFoundError(
                entity_type="Blueprint",
                entity_id=uuid.uuid4(),
                code=f"Blueprint {blueprint_id} not found",
            )

        config = StepConfig(**step_config)
        blueprint.update_step(step_id, config)

        blueprint = await self.blueprint_repository.update(blueprint)

        return BlueprintResponse.from_domain(blueprint)

    async def list_blueprints(
        self,
        organization_id: uuid.UUID,
        skip: int = 0,
        limit: int = 100,
        category: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[BlueprintResponse]:
        status_enum = None
        if status:
            status_enum = BlueprintStatus(status)

        category_enum = None
        if category:
            category_enum = BlueprintCategory(category)

        blueprints = await self.blueprint_repository.list_by_organization(
                organization_id=organization_id,
                status=status_enum,
                skip=skip,
                limit=limit,
            )

        if category_enum:
            blueprints = [t for t in blueprints if t.category == category_enum]

        return [BlueprintResponse.from_domain(t) for t in blueprints]

    async def get_blueprint(
        self, blueprint_id: uuid.UUID
    ) -> Optional[BlueprintResponse]:
        blueprint = await self.blueprint_repository.get_by_id(blueprint_id)
        if blueprint:
            return BlueprintResponse.from_domain(blueprint)
        return None
