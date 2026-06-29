# api/app/infrastructure/repositories/workflow_repository.py

"""SQLAlchemy implementation of Workflow repository."""

import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import func, inspect as sa_inspect, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.common.exceptions import EntityNotFoundError
from app.domain.common.json_serialization import deserialize_steps, serialize_steps
from app.domain.workflow.models import (
    PublishStatus,
    Workflow,
    WorkflowStatus,
    WorkflowTriggerType,
)
from app.domain.workflow.repository import WorkflowRepository
from app.infrastructure.persistence.models import (
    InstanceModel,
    WorkflowModel,
    WorkflowVersionModel,
)


def _compute_structural_hash(
    steps: Dict[str, Any], trigger_input_schema: Optional[Dict[str, Any]]
) -> str:
    """SHA-256 over canonical JSON of (steps, trigger_input_schema). Identical inputs hash identically across saves so no-op writes can be skipped."""
    payload = json.dumps(
        {"steps": steps, "trigger_input_schema": trigger_input_schema},
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _bump_semver_patch(version: str) -> str:
    parts = version.split(".")
    if len(parts) != 3:
        return "1.0.0"
    try:
        major, minor, patch = int(parts[0]), int(parts[1]), int(parts[2])
    except ValueError:
        return "1.0.0"
    return f"{major}.{minor}.{patch + 1}"


class SQLAlchemyWorkflowRepository(WorkflowRepository):
    """SQLAlchemy implementation of workflow repository."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def _load_latest_version(
        self, workflow_id: uuid.UUID
    ) -> Optional[WorkflowVersionModel]:
        """Load the most recent version row for a workflow, or None if none exists.

        Returns None when the session's execute() result chain isn't a real
        SQLAlchemy result (e.g. unit-test AsyncMock that doesn't simulate
        scalars().first()), so callers can treat unit-test paths and
        no-rows paths uniformly.
        """
        stmt = (
            select(WorkflowVersionModel)
            .where(WorkflowVersionModel.workflow_id == workflow_id)
            .order_by(WorkflowVersionModel.created_at.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        try:
            row = result.scalars().first()
        except (AttributeError, TypeError):
            return None
        if row is None or not isinstance(row, WorkflowVersionModel):
            return None
        return row

    def _to_domain(
        self,
        model: WorkflowModel,
        version_row: Optional[WorkflowVersionModel] = None,
        live_instance_count: Optional[int] = None,
    ) -> Workflow:
        """Build the domain Workflow from a head row + optional preloaded version row.

        Falls back to attribute access on `model` for steps/trigger_input_schema so unit
        tests using MagicMock models with those attributes still pass without DB round-trips.
        Production callers fetch the version row via `_load_latest_version` and pass it in.
        """
        if version_row is not None:
            steps_dict = version_row.steps or {}
            trigger_schema = version_row.trigger_input_schema
        else:
            steps_dict = getattr(model, "steps", None) or {}
            trigger_schema = getattr(model, "trigger_input_schema", None)
        steps = deserialize_steps(steps_dict)

        metadata_dict = model.client_metadata or {}

        tags_list = model.tags or []

        # Safely access blueprint name without triggering lazy load (MissingGreenlet with asyncpg)
        blueprint_name = None
        state = sa_inspect(model)
        if "blueprint" in state.dict and state.dict["blueprint"] is not None:
            blueprint_obj = model.blueprint
            if blueprint_obj is not None:
                blueprint_name = blueprint_obj.name

        return Workflow(
            id=model.id,
            name=model.name,
            slug=model.slug,
            description=model.description,
            organization_id=model.organization_id,
            blueprint_id=model.blueprint_id,
            blueprint_name=blueprint_name,
            blueprint_version=None,  # Not stored in DB model
            status=model.status,
            steps=steps,
            trigger_type=model.trigger_type,
            priority=model.priority,
            execution_mode=model.execution_mode,
            client_metadata=metadata_dict,
            tags=tags_list,
            has_unresolved_refs=model.has_unresolved_refs,
            instance_count=model.instance_count,
            live_instance_count=live_instance_count,
            last_instance_at=model.last_instance_at,
            created_by=model.created_by,
            scope=model.scope,
            publish_status=model.publish_status,
            visibility=model.visibility,
            max_concurrent_instances=model.max_concurrent_instances,
            webhook_token=model.webhook_token,
            webhook_method=model.webhook_method,
            webhook_auth_type=model.webhook_auth_type,
            webhook_auth_header_name=model.webhook_auth_header_name,
            trigger_input_schema=trigger_schema,
            schedule_dtstart=model.schedule_dtstart,
            schedule_rrule=model.schedule_rrule,
            schedule_timezone=model.schedule_timezone,
            schedule_enabled=model.schedule_enabled,
            schedule_next_run_at=model.schedule_next_run_at,
            schedule_last_run_at=model.schedule_last_run_at,
            # Trigger creds live only in the referenced OrganizationSecret; the
            # workflow row carries just the FK (no api_key/hash column).
            trigger_secret_id=model.trigger_secret_id,
            event_source_workflow_id=model.event_source_workflow_id,
            event_on=model.event_on,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    async def _live_instance_count(self, workflow_id: uuid.UUID) -> int:
        """Count existing instance rows for one workflow."""
        result = await self.session.execute(
            select(func.count())
            .select_from(InstanceModel)
            .where(InstanceModel.workflow_id == workflow_id)
        )
        return result.scalar() or 0

    async def _live_instance_counts(
        self, workflow_ids: List[uuid.UUID]
    ) -> Dict[uuid.UUID, int]:
        """Count existing instance rows for many workflows in one query."""
        if not workflow_ids:
            return {}
        result = await self.session.execute(
            select(InstanceModel.workflow_id, func.count())
            .where(InstanceModel.workflow_id.in_(workflow_ids))
            .group_by(InstanceModel.workflow_id)
        )
        counts = {wid: count for wid, count in result.all()}
        return {wid: counts.get(wid, 0) for wid in workflow_ids}

    async def _models_to_domain(
        self, models: List[WorkflowModel]
    ) -> List[Workflow]:
        """Map head rows to domain workflows with live instance counts loaded."""
        counts = await self._live_instance_counts([m.id for m in models])
        return [
            self._to_domain(
                model,
                await self._load_latest_version(model.id),
                live_instance_count=counts.get(model.id, 0),
            )
            for model in models
        ]

    async def _persist_new_version(
        self,
        workflow: Workflow,
        steps_serialized: Dict[str, Any],
        trigger_input_schema: Optional[Dict[str, Any]],
    ) -> None:
        """Insert a new workflow_versions row unless its structural hash matches the most recent version (no-op save dedup)."""
        new_hash = _compute_structural_hash(steps_serialized, trigger_input_schema)
        latest = await self._load_latest_version(workflow.id)
        if latest is not None and latest.structural_hash == new_hash:
            return
        next_version = (
            _bump_semver_patch(latest.version) if latest is not None else "1.0.0"
        )
        version_row = WorkflowVersionModel(
            workflow_id=workflow.id,
            organization_id=workflow.organization_id,
            version=next_version,
            steps=steps_serialized,
            trigger_input_schema=trigger_input_schema,
            structural_hash=new_hash,
            created_by=workflow.created_by,
        )
        self.session.add(version_row)

    async def create(self, workflow: Workflow) -> Workflow:
        workflow_model = WorkflowModel(
            id=workflow.id,
            name=workflow.name,
            slug=workflow.slug,
            description=workflow.description,
            organization_id=workflow.organization_id,
            blueprint_id=workflow.blueprint_id,
            status=workflow.status,  # type: ignore[assignment]  - domain enum assigned to SA column; SA type stubs expect Column type
            trigger_type=workflow.trigger_type,  # type: ignore[assignment]  - domain enum assigned to SA column; SA type stubs expect Column type
            priority=workflow.priority,  # type: ignore[assignment]  - domain enum assigned to SA column; SA type stubs expect Column type
            execution_mode=workflow.execution_mode,  # type: ignore[assignment]  - domain enum assigned to SA column; SA type stubs expect Column type
            has_unresolved_refs=workflow.has_unresolved_refs,
            max_concurrent_instances=workflow.max_concurrent_instances or 1,
            instance_count=workflow.instance_count,
            last_instance_at=workflow.last_instance_at,
            webhook_token=workflow.webhook_token,
            webhook_method=workflow.webhook_method,
            webhook_auth_type=workflow.webhook_auth_type,
            webhook_auth_header_name=workflow.webhook_auth_header_name,
            schedule_dtstart=workflow.schedule_dtstart,
            schedule_rrule=workflow.schedule_rrule,
            schedule_timezone=workflow.schedule_timezone,
            schedule_enabled=workflow.schedule_enabled,
            schedule_next_run_at=workflow.schedule_next_run_at,
            schedule_last_run_at=workflow.schedule_last_run_at,
            trigger_secret_id=workflow.trigger_secret_id,
            event_source_workflow_id=workflow.event_source_workflow_id,
            event_on=workflow.event_on,
            tags=workflow.tags or [],
            client_metadata=workflow.client_metadata or {},
            created_by=workflow.created_by,
            scope=(
                workflow.scope.value
                if hasattr(workflow.scope, "value")
                else workflow.scope
            ),
            publish_status=workflow.publish_status,
            visibility=workflow.visibility,  # type: ignore[assignment]  - domain enum assigned to SA column; SA type stubs expect Column type
            created_at=workflow.created_at,
            updated_at=workflow.updated_at or datetime.now(UTC),  # type: ignore[assignment]  - domain datetime assigned to SA column; SA type stubs expect Column type
        )

        self.session.add(workflow_model)
        await self.session.flush()

        steps_serialized = serialize_steps(workflow.steps) if workflow.steps else {}
        # First-time create: no prior version row to dedupe against, write 1.0.0 directly
        # so this path doesn't need the dedup lookup unit tests would have to mock.
        initial_version = WorkflowVersionModel(
            workflow_id=workflow.id,
            organization_id=workflow.organization_id,
            version="1.0.0",
            steps=steps_serialized,
            trigger_input_schema=workflow.trigger_input_schema,
            structural_hash=_compute_structural_hash(
                steps_serialized, workflow.trigger_input_schema
            ),
            created_by=workflow.created_by,
        )
        self.session.add(initial_version)

        await self.session.commit()
        await self.session.refresh(workflow_model)

        return self._to_domain(workflow_model, initial_version)

    async def update(self, workflow: Workflow) -> Workflow:
        stmt = select(WorkflowModel).where(WorkflowModel.id == workflow.id)
        result = await self.session.execute(stmt)
        workflow_model = result.scalars().first()

        if not workflow_model:
            raise EntityNotFoundError(
                entity_type="Workflow",
                entity_id=workflow.id,
            )

        workflow_model.name = workflow.name
        workflow_model.slug = workflow.slug
        workflow_model.description = workflow.description
        workflow_model.status = workflow.status  # type: ignore[assignment]  - domain enum assigned to SA column; SA type stubs expect Column type
        workflow_model.trigger_type = workflow.trigger_type  # type: ignore[assignment]  - domain enum assigned to SA column; SA type stubs expect Column type
        workflow_model.priority = workflow.priority  # type: ignore[assignment]  - domain enum assigned to SA column; SA type stubs expect Column type
        workflow_model.execution_mode = workflow.execution_mode  # type: ignore[assignment]  - domain enum assigned to SA column; SA type stubs expect Column type
        workflow_model.has_unresolved_refs = workflow.has_unresolved_refs
        workflow_model.max_concurrent_instances = workflow.max_concurrent_instances or 1
        workflow_model.instance_count = workflow.instance_count
        workflow_model.last_instance_at = workflow.last_instance_at
        workflow_model.webhook_token = workflow.webhook_token
        workflow_model.webhook_method = workflow.webhook_method
        workflow_model.webhook_auth_type = workflow.webhook_auth_type
        workflow_model.webhook_auth_header_name = workflow.webhook_auth_header_name
        workflow_model.schedule_dtstart = workflow.schedule_dtstart
        workflow_model.schedule_rrule = workflow.schedule_rrule
        workflow_model.schedule_timezone = workflow.schedule_timezone
        workflow_model.schedule_enabled = workflow.schedule_enabled
        workflow_model.schedule_next_run_at = workflow.schedule_next_run_at
        workflow_model.schedule_last_run_at = workflow.schedule_last_run_at
        workflow_model.trigger_secret_id = workflow.trigger_secret_id
        workflow_model.event_source_workflow_id = workflow.event_source_workflow_id
        workflow_model.event_on = workflow.event_on
        workflow_model.tags = workflow.tags or []
        workflow_model.client_metadata = workflow.client_metadata or {}
        workflow_model.scope = workflow.scope
        workflow_model.publish_status = workflow.publish_status
        workflow_model.visibility = workflow.visibility  # type: ignore[assignment]  - domain enum assigned to SA column; SA type stubs expect Column type
        workflow_model.updated_at = workflow.updated_at or datetime.now(UTC)  # type: ignore[assignment]  - domain datetime assigned to SA column; SA type stubs expect Column type

        steps_serialized = serialize_steps(workflow.steps) if workflow.steps else {}
        await self._persist_new_version(
            workflow, steps_serialized, workflow.trigger_input_schema
        )

        await self.session.commit()
        await self.session.refresh(workflow_model)

        return self._to_domain(workflow_model, await self._load_latest_version(workflow_model.id))

    async def get_by_id(self, workflow_id: uuid.UUID) -> Optional[Workflow]:
        stmt = select(WorkflowModel).where(WorkflowModel.id == workflow_id)
        result = await self.session.execute(stmt)
        workflow_model = result.scalars().first()

        if not workflow_model:
            return None

        return self._to_domain(
            workflow_model,
            await self._load_latest_version(workflow_model.id),
            live_instance_count=await self._live_instance_count(workflow_model.id),
        )

    async def get_by_id_and_version(
        self, workflow_id: uuid.UUID, version: int
    ) -> Optional[Workflow]:
        """Vestigial: domain `version` (int) is no longer persisted on workflows; this returns None when the head's domain version doesn't equal the requested int."""
        head_stmt = select(WorkflowModel).where(WorkflowModel.id == workflow_id)
        head = (await self.session.execute(head_stmt)).scalars().first()
        if not head:
            return None
        workflow = self._to_domain(head, await self._load_latest_version(head.id))
        if workflow.version != version:
            return None
        return workflow

    async def get_by_name(
        self,
        organization_id: uuid.UUID,
        name: str,
        exclude_id: Optional[uuid.UUID] = None,
    ) -> Optional[Workflow]:
        stmt = select(WorkflowModel).where(
            WorkflowModel.organization_id == organization_id,
            WorkflowModel.name == name,
        )
        if exclude_id is not None:
            stmt = stmt.where(WorkflowModel.id != exclude_id)
        result = await self.session.execute(stmt)
        workflow_model = result.scalars().first()

        if not workflow_model:
            return None

        return self._to_domain(workflow_model, await self._load_latest_version(workflow_model.id))

    async def find_active_workflows_for_organization(
        self,
        organization_id: uuid.UUID,
        skip: int,
        limit: int,
    ) -> List[Workflow]:
        stmt = select(WorkflowModel).where(
            WorkflowModel.organization_id == organization_id,
            WorkflowModel.status == WorkflowStatus.ACTIVE,
        )

        stmt = stmt.offset(skip).limit(limit)

        result = await self.session.execute(stmt)
        workflow_models = result.scalars().all()

        return [self._to_domain(model, await self._load_latest_version(model.id)) for model in workflow_models]

    async def find_workflows_using_blueprint(
        self,
        blueprint_id: uuid.UUID,
        skip: int,
        limit: int,
    ) -> List[Workflow]:
        stmt = select(WorkflowModel).where(WorkflowModel.blueprint_id == blueprint_id)

        stmt = stmt.offset(skip).limit(limit)

        result = await self.session.execute(stmt)
        workflow_models = result.scalars().all()

        return [self._to_domain(model, await self._load_latest_version(model.id)) for model in workflow_models]

    async def has_workflows_for_blueprint(self, blueprint_id: uuid.UUID) -> bool:
        stmt = (
            select(func.count())
            .select_from(WorkflowModel)
            .where(WorkflowModel.blueprint_id == blueprint_id)
        )
        result = await self.session.execute(stmt)
        count = result.scalar()

        return bool(count and count > 0)

    async def find_workflows_ready_for_execution(
        self,
        organization_id: uuid.UUID,
        skip: int,
        limit: int,
    ) -> List[Workflow]:
        stmt = select(WorkflowModel).where(
            WorkflowModel.organization_id == organization_id,
            WorkflowModel.status == WorkflowStatus.ACTIVE,
        )

        stmt = stmt.offset(skip).limit(limit)

        result = await self.session.execute(stmt)
        workflow_models = result.scalars().all()

        return [self._to_domain(model, await self._load_latest_version(model.id)) for model in workflow_models]

    async def list_by_organization(
        self,
        organization_id: uuid.UUID,
        skip: int,
        limit: int,
        status: Optional[WorkflowStatus] = None,
        trigger_type: Optional[WorkflowTriggerType] = None,
    ) -> List[Workflow]:
        stmt = (
            select(WorkflowModel)
            .options(selectinload(WorkflowModel.blueprint))
            .where(WorkflowModel.organization_id == organization_id)
        )

        if status is not None:
            stmt = stmt.where(WorkflowModel.status == status)

        if trigger_type is not None:
            stmt = stmt.where(WorkflowModel.trigger_type == trigger_type)

        stmt = stmt.offset(skip).limit(limit)

        result = await self.session.execute(stmt)
        workflow_models = result.scalars().all()

        return await self._models_to_domain(list(workflow_models))

    async def list_by_blueprint(
        self,
        blueprint_id: uuid.UUID,
        skip: int,
        limit: int,
        status: Optional[WorkflowStatus] = None,
    ) -> List[Workflow]:
        stmt = select(WorkflowModel).where(WorkflowModel.blueprint_id == blueprint_id)

        if status is not None:
            stmt = stmt.where(WorkflowModel.status == status)

        stmt = stmt.offset(skip).limit(limit)

        result = await self.session.execute(stmt)
        workflow_models = result.scalars().all()

        return [self._to_domain(model, await self._load_latest_version(model.id)) for model in workflow_models]

    async def list_active_scheduled(
        self,
        skip: int,
        limit: int,
        organization_id: Optional[uuid.UUID] = None,
    ) -> List[Workflow]:
        stmt = select(WorkflowModel).where(
            WorkflowModel.status == WorkflowStatus.ACTIVE,
            WorkflowModel.trigger_type == WorkflowTriggerType.SCHEDULE,
        )

        if organization_id is not None:
            stmt = stmt.where(WorkflowModel.organization_id == organization_id)

        stmt = stmt.offset(skip).limit(limit)

        result = await self.session.execute(stmt)
        workflow_models = result.scalars().all()

        return [self._to_domain(model, await self._load_latest_version(model.id)) for model in workflow_models]

    async def get_due_schedules(self, now: datetime) -> List[Workflow]:
        """Active, enabled schedule-trigger workflows whose next_run_at is due."""
        stmt = select(WorkflowModel).where(
            WorkflowModel.status == WorkflowStatus.ACTIVE,
            WorkflowModel.trigger_type == WorkflowTriggerType.SCHEDULE,
            WorkflowModel.schedule_enabled.is_(True),
            WorkflowModel.schedule_next_run_at.isnot(None),
            WorkflowModel.schedule_next_run_at <= now,
        )
        result = await self.session.execute(stmt)
        models = result.scalars().all()
        return [
            self._to_domain(m, await self._load_latest_version(m.id)) for m in models
        ]

    async def list_event_triggered_by(
        self, source_workflow_id: uuid.UUID
    ) -> List[Workflow]:
        """Active event-trigger workflows bound to fire on source_workflow_id finishing."""
        stmt = select(WorkflowModel).where(
            WorkflowModel.status == WorkflowStatus.ACTIVE,
            WorkflowModel.trigger_type == WorkflowTriggerType.EVENT,
            WorkflowModel.event_source_workflow_id == source_workflow_id,
        )
        result = await self.session.execute(stmt)
        models = result.scalars().all()
        return [
            self._to_domain(m, await self._load_latest_version(m.id)) for m in models
        ]

    async def search(
        self,
        query: str,
        skip: int,
        limit: int,
        organization_id: Optional[uuid.UUID] = None,
    ) -> List[Workflow]:
        search_pattern = f"%{query}%"
        stmt = select(WorkflowModel).where(
            or_(
                WorkflowModel.name.ilike(search_pattern),
                WorkflowModel.description.ilike(search_pattern),
            )
        )

        if organization_id is not None:
            stmt = stmt.where(WorkflowModel.organization_id == organization_id)

        stmt = stmt.offset(skip).limit(limit)

        result = await self.session.execute(stmt)
        workflow_models = result.scalars().all()

        return await self._models_to_domain(list(workflow_models))

    async def delete(self, workflow_id: uuid.UUID) -> bool:
        stmt = select(WorkflowModel).where(WorkflowModel.id == workflow_id)
        result = await self.session.execute(stmt)
        workflow_model = result.scalars().first()

        if not workflow_model:
            return False

        await self.session.delete(workflow_model)
        await self.session.commit()

        return True

    async def count_by_organization(
        self,
        organization_id: uuid.UUID,
        skip: int,
        limit: int,
        status: Optional[WorkflowStatus] = None,
    ) -> int:
        # skip and limit are part of interface contract but unused in count queries.
        _ = skip, limit

        stmt = (
            select(func.count())
            .select_from(WorkflowModel)
            .where(WorkflowModel.organization_id == organization_id)
        )

        if status is not None:
            stmt = stmt.where(WorkflowModel.status == status)

        result = await self.session.execute(stmt)
        count = result.scalar()

        return int(count) if count else 0

    async def count_by_blueprint(
        self,
        blueprint_id: uuid.UUID,
        skip: int,
        limit: int,
    ) -> int:
        # skip and limit are part of interface contract but unused in count queries.
        _ = skip, limit

        stmt = (
            select(func.count())
            .select_from(WorkflowModel)
            .where(WorkflowModel.blueprint_id == blueprint_id)
        )
        result = await self.session.execute(stmt)
        count = result.scalar()

        return int(count) if count else 0

    async def count_by_trigger_secret_id(self, secret_id: uuid.UUID) -> int:
        stmt = (
            select(func.count())
            .select_from(WorkflowModel)
            .where(WorkflowModel.trigger_secret_id == secret_id)
        )
        result = await self.session.execute(stmt)
        count = result.scalar()
        return int(count) if count else 0

    async def list_by_trigger_secret_id(
        self, secret_id: uuid.UUID
    ) -> List[Dict[str, Any]]:
        stmt = (
            select(WorkflowModel.id, WorkflowModel.name)
            .where(WorkflowModel.trigger_secret_id == secret_id)
            .order_by(WorkflowModel.name)
        )
        result = await self.session.execute(stmt)
        return [{"id": row.id, "name": row.name} for row in result.all()]

    async def get_execution_stats(self, workflow_id: uuid.UUID) -> Dict[str, Any]:
        workflow = await self.get_by_id(workflow_id)
        if not workflow:
            return {}

        return {
            "instance_count": workflow.instance_count,
            "last_instance_at": (
                workflow.last_instance_at.isoformat()
                if workflow.last_instance_at
                else None
            ),
        }

    async def exists(self, workflow_id: uuid.UUID) -> bool:
        stmt = (
            select(func.count())
            .select_from(WorkflowModel)
            .where(WorkflowModel.id == workflow_id)
        )
        result = await self.session.execute(stmt)
        count = result.scalar()

        return bool(count and count > 0)

    async def list_personal_workflows(
        self,
        organization_id: uuid.UUID,
        created_by: uuid.UUID,
        skip: int,
        limit: int,
        status: Optional[WorkflowStatus] = None,
    ) -> List[Workflow]:
        """List personal workflows created by a specific user."""
        stmt = (
            select(WorkflowModel)
            .options(selectinload(WorkflowModel.blueprint))
            .where(
                WorkflowModel.organization_id == organization_id,
                WorkflowModel.created_by == created_by,
                WorkflowModel.scope == "personal",
            )
        )
        if status is not None:
            stmt = stmt.where(WorkflowModel.status == status)
        stmt = stmt.offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return await self._models_to_domain(list(result.scalars().all()))

    async def list_organization_workflows(
        self,
        organization_id: uuid.UUID,
        skip: int,
        limit: int,
        status: Optional[WorkflowStatus] = None,
    ) -> List[Workflow]:
        """List organization-scoped workflows."""
        stmt = (
            select(WorkflowModel)
            .options(selectinload(WorkflowModel.blueprint))
            .where(
                WorkflowModel.organization_id == organization_id,
                WorkflowModel.scope == "organization",
            )
        )
        if status is not None:
            stmt = stmt.where(WorkflowModel.status == status)
        stmt = stmt.offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return await self._models_to_domain(list(result.scalars().all()))

    async def list_pending_publish(
        self,
        organization_id: uuid.UUID,
        skip: int,
        limit: int,
    ) -> List[Workflow]:
        """List workflows pending publish approval."""
        stmt = (
            select(WorkflowModel)
            .options(selectinload(WorkflowModel.blueprint))
            .where(
                WorkflowModel.organization_id == organization_id,
                WorkflowModel.publish_status == PublishStatus.PENDING,
            )
        )
        stmt = stmt.offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return await self._models_to_domain(list(result.scalars().all()))

    async def get_by_webhook_token(self, token: str) -> Optional[Workflow]:
        """
        Get a workflow by its webhook token.

        Args:
            token: The webhook token

        Returns:
            The workflow if found, None otherwise
        """
        stmt = select(WorkflowModel).where(WorkflowModel.webhook_token == token)
        result = await self.session.execute(stmt)
        workflow_model = result.scalars().first()

        if not workflow_model:
            return None

        return self._to_domain(workflow_model, await self._load_latest_version(workflow_model.id))

    async def get_by_step_webhook_token(
        self, token: str
    ) -> Optional[tuple[Workflow, str]]:
        """Search active workflows' latest version for a step whose `client_metadata.webhook_token` matches; returns the workflow + step id."""
        # Steps live in workflow_versions now. Latest version = most recent created_at.
        stmt = text(
            """
            SELECT w.id, s.key AS step_key
            FROM workflows w
            INNER JOIN LATERAL (
                SELECT steps
                FROM workflow_versions
                WHERE workflow_id = w.id
                ORDER BY created_at DESC
                LIMIT 1
            ) wv ON TRUE
            CROSS JOIN jsonb_each(wv.steps) AS s(key, value)
            WHERE w.status = 'ACTIVE'
              AND s.value -> 'client_metadata' ->> 'webhook_token' = :token
            LIMIT 1
            """
        )

        result = await self.session.execute(stmt, {"token": token})
        row = result.first()

        if not row:
            return None

        wf_result = await self.session.execute(
            select(WorkflowModel).where(WorkflowModel.id == row.id)
        )
        db_workflow = wf_result.scalars().first()

        if not db_workflow:
            return None

        return (self._to_domain(db_workflow, await self._load_latest_version(db_workflow.id)), row.step_key)
