# api/app/infrastructure/repositories/workflow_repository.py

"""SQLAlchemy implementation of Workflow repository."""

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
from app.infrastructure.persistence.models import WorkflowModel
from app.infrastructure.security.credential_encryption import (
    get_credential_encryption,
)

# Sentinel prefix: encrypted Fernet ciphertext starts with "gAAAAAB..." (base64
# of Fernet's version byte + timestamp). We tag stored values with this marker
# so the read path can distinguish encrypted-at-rest from legacy plaintext and
# decrypt accordingly - existing plaintext rows continue to read correctly.
_ENCRYPTED_MARKER = "enc:v1:"


def _encrypt_field(plaintext: Optional[str]) -> Optional[str]:
    """Encrypt a secret-class field before writing to the DB.

    Returns None unchanged; otherwise returns `_ENCRYPTED_MARKER + ciphertext`.
    The marker lets the read path distinguish encrypted from legacy plaintext.

    Used for: webhook_secret, webhook_auth_header_value, webhook_jwt_secret.
    """
    if plaintext is None:
        return None
    if plaintext.startswith(_ENCRYPTED_MARKER):
        # Idempotent: already-encrypted value passes through. Guards against
        # accidental double-encryption if a caller reads, mutates another
        # field, and writes back without touching the secret field.
        return plaintext
    encryption = get_credential_encryption()
    return _ENCRYPTED_MARKER + encryption.encrypt(plaintext)


def _decrypt_field(stored: Optional[str]) -> Optional[str]:
    """Decrypt a secret-class field read from the DB.

    Recognizes the `_ENCRYPTED_MARKER` prefix; values without it are returned as-is (see sentinel comment above).

    Used for: webhook_secret, webhook_auth_header_value, webhook_jwt_secret.
    """
    if stored is None:
        return None
    if not stored.startswith(_ENCRYPTED_MARKER):
        # Legacy plaintext row; return as-is.
        return stored
    ciphertext = stored[len(_ENCRYPTED_MARKER) :]
    encryption = get_credential_encryption()
    return encryption.decrypt(ciphertext)


# Back-compat aliases.
_encrypt_webhook_secret = _encrypt_field
_decrypt_webhook_secret = _decrypt_field


class SQLAlchemyWorkflowRepository(WorkflowRepository):
    """SQLAlchemy implementation of workflow repository."""

    def __init__(self, session: AsyncSession):
        self.session = session

    def _to_domain(self, model: WorkflowModel) -> Workflow:
        steps_dict = model.steps or {}
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
            description=model.description,
            organization_id=model.organization_id,
            blueprint_id=model.blueprint_id,
            blueprint_name=blueprint_name,
            blueprint_version=None,  # Not stored in DB model
            version=model.version,
            status=model.status,
            steps=steps,
            trigger_type=model.trigger_type,
            priority=model.priority,
            execution_mode=model.execution_mode,
            client_metadata=metadata_dict,
            tags=tags_list,
            instance_count=model.instance_count,
            last_instance_at=model.last_instance_at,
            created_by=model.created_by,
            scope=model.scope,
            publish_status=model.publish_status,
            max_concurrent_instances=model.max_concurrent_instances,
            webhook_token=model.webhook_token,
            # Decrypt at the infra/domain boundary so domain logic always works with plaintext.
            webhook_secret=_decrypt_field(model.webhook_secret),
            webhook_method=model.webhook_method,
            webhook_auth_type=model.webhook_auth_type,
            webhook_auth_header_name=model.webhook_auth_header_name,
            webhook_auth_header_value=_decrypt_field(model.webhook_auth_header_value),
            webhook_jwt_secret=_decrypt_field(model.webhook_jwt_secret),
            trigger_input_schema=model.trigger_input_schema,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    async def create(self, workflow: Workflow) -> Workflow:
        workflow_model = WorkflowModel(
            id=workflow.id,
            name=workflow.name,
            description=workflow.description,
            organization_id=workflow.organization_id,
            blueprint_id=workflow.blueprint_id,
            version=workflow.version,
            status=workflow.status,  # type: ignore[assignment]  - domain enum assigned to SA column; SA type stubs expect Column type
            trigger_type=workflow.trigger_type,  # type: ignore[assignment]  - domain enum assigned to SA column; SA type stubs expect Column type
            priority=workflow.priority,  # type: ignore[assignment]  - domain enum assigned to SA column; SA type stubs expect Column type
            execution_mode=workflow.execution_mode,  # type: ignore[assignment]  - domain enum assigned to SA column; SA type stubs expect Column type
            max_concurrent_instances=workflow.max_concurrent_instances or 1,
            instance_count=workflow.instance_count,
            last_instance_at=workflow.last_instance_at,
            steps=serialize_steps(workflow.steps) if workflow.steps else {},
            webhook_token=workflow.webhook_token,
            # Encrypt at the domain/infra boundary. Idempotent on
            # already-encrypted strings (see _encrypt_webhook_secret).
            webhook_secret=_encrypt_field(workflow.webhook_secret),
            webhook_method=workflow.webhook_method,
            webhook_auth_type=workflow.webhook_auth_type,
            webhook_auth_header_name=workflow.webhook_auth_header_name,
            webhook_auth_header_value=_encrypt_field(
                workflow.webhook_auth_header_value
            ),
            webhook_jwt_secret=_encrypt_field(workflow.webhook_jwt_secret),
            trigger_input_schema=workflow.trigger_input_schema,
            tags=workflow.tags or [],
            client_metadata=workflow.client_metadata or {},
            created_by=workflow.created_by,
            scope=(
                workflow.scope.value
                if hasattr(workflow.scope, "value")
                else workflow.scope
            ),
            publish_status=workflow.publish_status,
            created_at=workflow.created_at,
            updated_at=workflow.updated_at or datetime.now(UTC),  # type: ignore[assignment]  - domain datetime assigned to SA column; SA type stubs expect Column type
        )

        self.session.add(workflow_model)
        await self.session.commit()
        await self.session.refresh(workflow_model)

        return self._to_domain(workflow_model)

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
        workflow_model.description = workflow.description
        workflow_model.version = workflow.version
        workflow_model.status = workflow.status  # type: ignore[assignment]  - domain enum assigned to SA column; SA type stubs expect Column type
        workflow_model.trigger_type = workflow.trigger_type  # type: ignore[assignment]  - domain enum assigned to SA column; SA type stubs expect Column type
        workflow_model.priority = workflow.priority  # type: ignore[assignment]  - domain enum assigned to SA column; SA type stubs expect Column type
        workflow_model.execution_mode = workflow.execution_mode  # type: ignore[assignment]  - domain enum assigned to SA column; SA type stubs expect Column type
        workflow_model.max_concurrent_instances = workflow.max_concurrent_instances or 1
        workflow_model.instance_count = workflow.instance_count
        workflow_model.last_instance_at = workflow.last_instance_at
        workflow_model.steps = serialize_steps(workflow.steps) if workflow.steps else {}
        workflow_model.webhook_token = workflow.webhook_token
        # Encrypt at the domain/infra boundary on update, same as _to_model.
        workflow_model.webhook_secret = _encrypt_field(workflow.webhook_secret)
        workflow_model.webhook_method = workflow.webhook_method
        workflow_model.webhook_auth_type = workflow.webhook_auth_type
        workflow_model.webhook_auth_header_name = workflow.webhook_auth_header_name
        workflow_model.webhook_auth_header_value = _encrypt_field(
            workflow.webhook_auth_header_value
        )
        workflow_model.webhook_jwt_secret = _encrypt_field(workflow.webhook_jwt_secret)
        workflow_model.trigger_input_schema = workflow.trigger_input_schema
        workflow_model.tags = workflow.tags or []
        workflow_model.client_metadata = workflow.client_metadata or {}
        workflow_model.scope = workflow.scope
        workflow_model.publish_status = workflow.publish_status
        workflow_model.updated_at = workflow.updated_at or datetime.now(UTC)  # type: ignore[assignment]  - domain datetime assigned to SA column; SA type stubs expect Column type

        await self.session.commit()
        await self.session.refresh(workflow_model)

        return self._to_domain(workflow_model)

    async def get_by_id(self, workflow_id: uuid.UUID) -> Optional[Workflow]:
        stmt = select(WorkflowModel).where(WorkflowModel.id == workflow_id)
        result = await self.session.execute(stmt)
        workflow_model = result.scalars().first()

        if not workflow_model:
            return None

        return self._to_domain(workflow_model)

    async def get_by_id_and_version(
        self, workflow_id: uuid.UUID, version: int
    ) -> Optional[Workflow]:
        stmt = select(WorkflowModel).where(
            WorkflowModel.id == workflow_id,
            WorkflowModel.version == version,
        )
        result = await self.session.execute(stmt)
        workflow_model = result.scalars().first()

        if not workflow_model:
            return None

        return self._to_domain(workflow_model)

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

        return self._to_domain(workflow_model)

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

        return [self._to_domain(model) for model in workflow_models]

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

        return [self._to_domain(model) for model in workflow_models]

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

        return [self._to_domain(model) for model in workflow_models]

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

        return [self._to_domain(model) for model in workflow_models]

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

        return [self._to_domain(model) for model in workflow_models]

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

        return [self._to_domain(model) for model in workflow_models]

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

        return [self._to_domain(model) for model in workflow_models]

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
        return [self._to_domain(m) for m in result.scalars().all()]

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
        return [self._to_domain(m) for m in result.scalars().all()]

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
        return [self._to_domain(m) for m in result.scalars().all()]

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

        return self._to_domain(workflow_model)

    async def get_by_step_webhook_token(
        self, token: str
    ) -> Optional[tuple[Workflow, str]]:
        """
        Get a workflow by a step's webhook token.

        Searches all active workflows' steps for a matching webhook_token
        in client_metadata. Used to handle incoming webhook callbacks for
        core.webhook_wait steps.

        Args:
            token: Secure webhook token to search for in step client_metadata

        Returns:
            Tuple of (Workflow, step_id) if found, None otherwise
        """
        # Use jsonb_each to search step webhook tokens at the database level.
        # Cast steps (JSON) to JSONB so we can use jsonb_each, then extract
        # the nested client_metadata.webhook_token from each step value.
        stmt = text("""
            SELECT w.id, s.key AS step_key
            FROM workflows w,
                 jsonb_each(w.steps::jsonb) AS s(key, value)
            WHERE w.status = 'ACTIVE'
              AND s.value -> 'client_metadata' ->> 'webhook_token' = :token
            LIMIT 1
            """)

        result = await self.session.execute(stmt, {"token": token})
        row = result.first()

        if not row:
            return None

        # Fetch the full workflow model by the matched ID
        wf_result = await self.session.execute(
            select(WorkflowModel).where(WorkflowModel.id == row.id)
        )
        db_workflow = wf_result.scalars().first()

        if not db_workflow:
            return None

        return (self._to_domain(db_workflow), row.step_key)
