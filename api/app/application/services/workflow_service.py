# api/app/application/services/workflow_service.py

import secrets
import uuid
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional

from app.config.settings import settings
from app.application.dtos.workflow_dto import (
    WorkflowCreate,
    WorkflowUpdate,
    WorkflowResponse,
)
from app.application.interfaces.event_bus import EventBus
from app.application.interfaces import EntityNotFoundError
from app.application.interfaces.exceptions import DuplicateEntityError
from app.domain.common.exceptions import BusinessRuleViolation
from app.domain.common.value_objects import StepConfig, Visibility
from app.domain.provider.repository import ProviderRepository
from app.domain.workflow.models import (
    Workflow,
    WorkflowScope,
    WorkflowStatus,
    WorkflowTriggerType,
)
from app.domain.workflow.repository import WorkflowRepository
from app.domain.organization_secret import (
    OrganizationSecret,
    OrganizationSecretRepository,
)

# secret_type tags for the OrganizationSecret rows that hold workflow trigger
# creds. One credential per row; the type fully determines the data key, so the
# reuse picker filters on the column with no decrypt-and-sniff.
TRIGGER_CRED_SECRET_TYPE = {
    "api_key": "api_key",
    "webhook_secret": "webhook_hmac",
    "webhook_auth_value": "webhook_header",
    "webhook_jwt_secret": "webhook_jwt",
}
TRIGGER_SECRET_TYPES = frozenset(TRIGGER_CRED_SECRET_TYPE.values())

# Egress sentinel for a configured-but-not-revealed secret-class trigger cred.
# Returned on read in place of the plaintext; ignored as a no-op on update so a
# round-trip save does not overwrite the stored secret with the sentinel.
CONFIGURED_SENTINEL = "[CONFIGURED]"


class WorkflowService:

    def __init__(
        self,
        workflow_repository: WorkflowRepository,
        event_bus: EventBus,
        provider_repository: Optional[ProviderRepository] = None,
        organization_secret_repository: Optional[OrganizationSecretRepository] = None,
    ):
        self.workflow_repository = workflow_repository
        self.event_bus = event_bus
        self.provider_repository = provider_repository
        self.organization_secret_repository = organization_secret_repository

    async def _get_workflow_or_raise(self, workflow_id: uuid.UUID) -> Workflow:
        workflow = await self.workflow_repository.get_by_id(workflow_id)
        if not workflow:
            raise EntityNotFoundError("Workflow", workflow_id)
        return workflow

    # ── Trigger-credential store (org_secrets single store) ──────────────
    # Trigger creds (api_key, webhook_secret, webhook_auth_value, webhook_jwt_secret)
    # live encrypted + recoverable in the OrganizationSecret the workflow references
    # via trigger_secret_id - the ONLY place they're persisted. Each cred lives in
    # its own TYPED secret (one cred per row); these helpers mint/repoint/clear that
    # secret and read it back for presence flags and auth.

    async def _unique_trigger_secret_name(self, workflow: Workflow) -> str:
        """Default the secret name to the workflow name; (org, name) is unique, so
        fall back to a workflow-id suffix if that name is already taken."""
        repo = self.organization_secret_repository
        base = workflow.name or "Workflow trigger"
        assert repo is not None
        if await repo.get_by_name(workflow.organization_id, base) is None:
            return base
        return f"{base} ({str(workflow.id)[:8]})"

    async def _store_trigger_cred(
        self, workflow: Workflow, cred_key: str, value: str
    ) -> None:
        """Store a single trigger credential in a TYPED OrganizationSecret (one
        cred per row; secret_type = TRIGGER_CRED_SECRET_TYPE[cred_key]). If the
        workflow's referenced secret is already of this type, update it in place
        (covers regenerate + shared-secret rotation); otherwise mint a new typed
        secret and repoint the FK - the old secret persists (admin owns it). No-op
        if no secret repo is wired (keeps unit constructions that omit it working)."""
        repo = self.organization_secret_repository
        if repo is None:
            return
        secret_type = TRIGGER_CRED_SECRET_TYPE[cred_key]
        if workflow.trigger_secret_id:
            secret = await repo.get_by_id(
                workflow.trigger_secret_id, workflow.organization_id
            )
            if secret is not None and secret.secret_type == secret_type:
                secret.secret_data = {**secret.secret_data, cred_key: value}
                await repo.update(secret)
                return
            # FK absent, dangling, or pointing at a different-typed secret → mint.
        name = await self._unique_trigger_secret_name(workflow)
        created = await repo.create(
            OrganizationSecret.create(
                organization_id=workflow.organization_id,
                name=name,
                secret_type=secret_type,
                secret_data={cred_key: value},
                created_by=workflow.created_by,
            )
        )
        workflow.trigger_secret_id = created.id

    async def _unlink_and_cleanup_trigger_secret(self, workflow: Workflow) -> None:
        """Null the workflow's trigger-secret FK, then delete the secret if no
        workflow still references it."""
        secret_id = workflow.trigger_secret_id
        workflow.trigger_secret_id = None
        await self.workflow_repository.update(workflow)
        if secret_id is None:
            return
        repo = self.organization_secret_repository
        if repo is None:
            return
        if await self.workflow_repository.count_by_trigger_secret_id(secret_id) == 0:
            await repo.delete(secret_id, workflow.organization_id)

    async def _secret_data(self, workflow: Workflow) -> Dict[str, Any]:
        """Trigger creds from the workflow's referenced OrganizationSecret, or {}
        when none is set / no secret repo is wired. The repo decrypts on read."""
        repo = self.organization_secret_repository
        if repo is None or not workflow.trigger_secret_id:
            return {}
        secret = await repo.get_by_id(
            workflow.trigger_secret_id, workflow.organization_id
        )
        return dict(secret.secret_data) if secret else {}

    async def _build_response(self, workflow: Workflow) -> WorkflowResponse:
        """WorkflowResponse enriched with the trigger-cred presence/values that
        live in the referenced OrganizationSecret. `from_domain` is pure (no secret
        access); these four fields are the sole reason this is async - they're
        sourced here so the legacy workflow columns could be dropped."""
        response = WorkflowResponse.from_domain(workflow)
        data = await self._secret_data(workflow)
        response.api_key_set = bool(data.get("api_key"))
        response.webhook_secret = (
            CONFIGURED_SENTINEL if data.get("webhook_secret") else None
        )
        response.webhook_auth_header_value = (
            CONFIGURED_SENTINEL if data.get("webhook_auth_value") else None
        )
        response.webhook_jwt_secret = (
            CONFIGURED_SENTINEL if data.get("webhook_jwt_secret") else None
        )
        return response

    async def to_responses(
        self, workflows: List[Workflow]
    ) -> List[WorkflowResponse]:
        """Batch `_build_response` for list endpoints that fetch workflows directly
        off the repository."""
        return [await self._build_response(w) for w in workflows]

    async def _persist_and_publish(self, workflow: Workflow) -> Workflow:
        events = workflow.clear_events()
        workflow = await self.workflow_repository.update(workflow)
        for event in events:
            await self.event_bus.publish(event)
        return workflow

    async def _pin_step_versions(
        self, steps: Dict[str, Dict[str, Any]]
    ) -> Dict[str, Dict[str, Any]]:
        """Pin provider/service versions; core services (no provider_id) are skipped."""
        if not self.provider_repository:
            return steps

        version_cache: Dict[str, Optional[str]] = {}

        for step_config in steps.values():
            if not isinstance(step_config, dict):
                continue
            job = step_config.get("job")
            if not isinstance(job, dict):
                continue

            provider_id_str = step_config.get("provider_id") or job.get("provider_id")
            if not provider_id_str:
                continue

            pid_key = str(provider_id_str)
            if pid_key not in version_cache:
                try:
                    pid = uuid.UUID(pid_key)
                    provider = await self.provider_repository.get_by_id(pid)
                    version_cache[pid_key] = provider.version if provider else None
                except (ValueError, TypeError):
                    version_cache[pid_key] = None

            version = version_cache[pid_key]
            if version is not None and not job.get("provider_version"):
                job["provider_version"] = version
                job["service_version"] = version

        return steps

    async def create_workflow(self, command: WorkflowCreate) -> WorkflowResponse:
        if command.organization_id is None:
            raise ValueError("organization_id is required")

        created_by = command.created_by if command.created_by else uuid.uuid4()
        scope = (
            WorkflowScope(command.scope)
            if command.scope
            else WorkflowScope.ORGANIZATION
        )

        # Check for duplicate workflow name org-wide
        existing = await self.workflow_repository.get_by_name(
            command.organization_id,
            command.name,
        )
        if existing:
            raise DuplicateEntityError(
                entity_type="Workflow", field="name", value=command.name
            )

        # Pin provider versions and convert steps dict to StepConfig if provided
        raw_steps = command.steps
        if raw_steps:
            raw_steps = await self._pin_step_versions(raw_steps)
        steps_dict = None
        if raw_steps:
            steps_dict = {}
            for step_id, step_config_dict in raw_steps.items():
                steps_dict[step_id] = StepConfig(**step_config_dict)

        workflow = Workflow.create(
            name=command.name,
            organization_id=command.organization_id,
            created_by=created_by,
            description=command.description,
            steps=steps_dict,
            trigger_type=(
                command.trigger_type
                if command.trigger_type
                else WorkflowTriggerType.MANUAL
            ),
            client_metadata=command.client_metadata,
            scope=scope,
        )

        # Apply trigger_input_schema if provided (not supported in create, only update)
        if command.trigger_input_schema:
            workflow.update(trigger_input_schema=command.trigger_input_schema)

        events = workflow.clear_events()

        workflow = await self.workflow_repository.create(workflow)

        for event in events:
            await self.event_bus.publish(event)

        return await self._build_response(workflow)

    async def get_workflow(self, workflow_id: uuid.UUID) -> WorkflowResponse:
        workflow = await self._get_workflow_or_raise(workflow_id)
        return await self._build_response(workflow)

    async def list_workflows(
        self,
        organization_id: uuid.UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> List[WorkflowResponse]:
        workflows = await self.workflow_repository.list_by_organization(
            organization_id,
            skip=skip,
            limit=limit,
        )
        return await self.to_responses(workflows)

    async def update_workflow(
        self,
        workflow_id: uuid.UUID,
        command: WorkflowUpdate,
        actor_id: Optional[uuid.UUID] = None,
    ) -> WorkflowResponse:
        workflow = await self._get_workflow_or_raise(workflow_id)

        # Archiving a pending submission is reserved for its creator - an admin
        # declines via reject, not archive.
        if command.status == WorkflowStatus.ARCHIVED:
            workflow.validate_can_be_archived(actor_id)

        # If name is being changed, check for duplicates org-wide (exclude self)
        if command.name and command.name != workflow.name:
            existing = await self.workflow_repository.get_by_name(
                workflow.organization_id,
                command.name,
                exclude_id=workflow.id,
            )
            if existing:
                raise DuplicateEntityError(
                    entity_type="Workflow", field="name", value=command.name
                )

        # Pin provider versions on steps before saving
        steps_to_save = command.steps
        if steps_to_save is not None:
            steps_to_save = await self._pin_step_versions(steps_to_save)

        # Call domain update method with all parameters, including status
        # Domain method handles version increment when status == ACTIVE
        workflow.update(
            name=command.name,
            description=command.description,
            steps=steps_to_save,
            trigger_type=command.trigger_type,
            client_metadata=command.client_metadata,
            status=command.status,
            trigger_input_schema=command.trigger_input_schema,
            webhook_method=command.webhook_method,
            webhook_auth_type=command.webhook_auth_type,
            webhook_auth_header_name=command.webhook_auth_header_name,
        )

        # Header-auth value and JWT secret are secret-class: each lives in its own
        # typed OrganizationSecret (one cred per row), not on the workflow row. A
        # workflow has a single webhook auth mode, so store only the cred for the
        # active mode (gating on it prevents a stray dual-mint / FK churn).
        if (
            command.webhook_auth_header_value is not None
            and command.webhook_auth_header_value != CONFIGURED_SENTINEL
            and workflow.webhook_auth_type == "header"
        ):
            await self._store_trigger_cred(
                workflow, "webhook_auth_value", command.webhook_auth_header_value
            )
        if (
            command.webhook_jwt_secret is not None
            and command.webhook_jwt_secret != CONFIGURED_SENTINEL
            and workflow.webhook_auth_type == "jwt"
        ):
            await self._store_trigger_cred(
                workflow, "webhook_jwt_secret", command.webhook_jwt_secret
            )

        workflow = await self._persist_and_publish(workflow)
        return await self._build_response(workflow)

    async def activate_workflow(
        self, workflow_id: uuid.UUID, activated_by: uuid.UUID
    ) -> WorkflowResponse:
        workflow = await self._get_workflow_or_raise(workflow_id)
        workflow.activate()
        workflow = await self._persist_and_publish(workflow)
        return await self._build_response(workflow)

    async def deactivate_workflow(
        self, workflow_id: uuid.UUID, deactivated_by: uuid.UUID
    ) -> WorkflowResponse:
        workflow = await self._get_workflow_or_raise(workflow_id)
        workflow.deactivate()
        workflow = await self._persist_and_publish(workflow)
        return await self._build_response(workflow)

    async def add_step(
        self,
        workflow_id: uuid.UUID,
        step_id: str,
        step_config: Dict[str, Any],
        added_by: uuid.UUID,
    ) -> WorkflowResponse:
        workflow = await self._get_workflow_or_raise(workflow_id)
        config = StepConfig(**step_config)
        workflow.add_step(step_id=step_id, step_config=config)
        workflow = await self._persist_and_publish(workflow)
        return await self._build_response(workflow)

    async def remove_step(
        self, workflow_id: uuid.UUID, step_id: str, removed_by: uuid.UUID
    ) -> WorkflowResponse:
        workflow = await self._get_workflow_or_raise(workflow_id)
        workflow.remove_step(step_id)
        workflow = await self._persist_and_publish(workflow)
        return await self._build_response(workflow)

    async def update_step(
        self,
        workflow_id: uuid.UUID,
        step_id: str,
        step_config: Dict[str, Any],
        updated_by: uuid.UUID,
    ) -> WorkflowResponse:
        workflow = await self._get_workflow_or_raise(workflow_id)
        config = StepConfig(**step_config)
        workflow.remove_step(step_id)
        workflow.add_step(step_id=step_id, step_config=config)
        workflow = await self._persist_and_publish(workflow)
        return await self._build_response(workflow)

    async def delete_workflow(
        self, workflow_id: uuid.UUID, actor_id: Optional[uuid.UUID] = None
    ) -> bool:
        # Workflow must be INACTIVE, ARCHIVED, or DRAFT - domain enforces this.
        # actor_id lets the domain block deletion of a pending submission by
        # anyone but its creator.
        workflow = await self._get_workflow_or_raise(workflow_id)
        workflow.validate_can_be_deleted(actor_id)
        return await self.workflow_repository.delete(workflow_id)

    async def set_visibility(
        self, workflow_id: uuid.UUID, new_visibility: Visibility
    ) -> tuple[Visibility, WorkflowResponse]:
        """Transition a workflow's cross-org marketplace visibility. Returns
        (old_visibility, updated) so the caller can audit-log the transition.
        Authorization (super_admin-only) is enforced at the API boundary."""
        workflow = await self._get_workflow_or_raise(workflow_id)
        old_visibility = workflow.set_visibility(new_visibility)
        updated = await self.workflow_repository.update(workflow)
        return old_visibility, await self._build_response(updated)

    async def generate_webhook_token(self, workflow_id: uuid.UUID) -> Dict[str, str]:
        workflow = await self._get_workflow_or_raise(workflow_id)
        token, secret = workflow.generate_webhook_token()
        await self._store_trigger_cred(workflow, "webhook_secret", secret)
        await self.workflow_repository.update(workflow)
        return {"token": token, "secret": secret}

    async def regenerate_webhook_token(self, workflow_id: uuid.UUID) -> Dict[str, str]:
        workflow = await self._get_workflow_or_raise(workflow_id)
        token, secret = workflow.regenerate_webhook_token()
        await self._store_trigger_cred(workflow, "webhook_secret", secret)
        await self.workflow_repository.update(workflow)
        return {"token": token, "secret": secret}

    async def clear_webhook_token(self, workflow_id: uuid.UUID) -> None:
        workflow = await self._get_workflow_or_raise(workflow_id)
        workflow.clear_webhook_token()
        await self._unlink_and_cleanup_trigger_secret(workflow)

    # ── Schedule trigger ──────────────────────────────────────────────────
    async def set_schedule(
        self,
        workflow_id: uuid.UUID,
        *,
        dtstart: Optional[datetime],
        rrule: Optional[str],
        timezone: str,
        enabled: bool,
    ) -> Dict[str, Any]:
        """Validate the RRULE schedule, compute the first run, and persist it."""
        from app.infrastructure.scheduling.rrule_schedule import (
            ScheduleError,
            compute_next_run,
        )

        workflow = await self._get_workflow_or_raise(workflow_id)
        next_run = None
        if enabled:
            try:
                next_run = compute_next_run(
                    dtstart, rrule, timezone, after=datetime.now(UTC)
                )
            except ScheduleError as e:
                raise BusinessRuleViolation(
                    message=str(e),
                    code="INVALID_SCHEDULE",
                    context={"workflow_id": str(workflow_id)},
                )
        workflow.set_schedule(
            dtstart=dtstart,
            rrule=rrule,
            timezone=timezone,
            enabled=enabled,
            next_run_at=next_run,
        )
        await self.workflow_repository.update(workflow)
        return {
            "enabled": enabled,
            "next_run_at": next_run.isoformat() if next_run else None,
        }

    async def clear_schedule(self, workflow_id: uuid.UUID) -> None:
        workflow = await self._get_workflow_or_raise(workflow_id)
        workflow.clear_schedule()
        await self.workflow_repository.update(workflow)

    # ── API trigger ───────────────────────────────────────────────────────
    # The key lives only in the OrganizationSecret now (no api_key_hash column),
    # so the generate-vs-regenerate conflict gate that used to live in the domain
    # reads the secret here instead.
    async def generate_api_key(self, workflow_id: uuid.UUID) -> str:
        workflow = await self._get_workflow_or_raise(workflow_id)
        if (await self._secret_data(workflow)).get("api_key"):
            raise BusinessRuleViolation(
                message="API key already exists. Use regenerate to replace it.",
                code="API_KEY_EXISTS",
                context={"workflow_id": str(workflow_id)},
            )
        key = workflow.generate_api_key()
        await self._store_trigger_cred(workflow, "api_key", key)
        await self.workflow_repository.update(workflow)
        return key

    async def _share_count(self, workflow: Workflow) -> int:
        """How many workflows reference this workflow's trigger secret (incl.
        itself). 0 when no secret is set. >1 means the secret is shared."""
        if not workflow.trigger_secret_id:
            return 0
        return await self.workflow_repository.count_by_trigger_secret_id(
            workflow.trigger_secret_id
        )

    async def trigger_secret_share_count(self, workflow_id: uuid.UUID) -> int:
        """Public share count for a workflow's trigger secret - drives the UI's
        decision to keep Regenerate in the workflow (unshared) vs. point to the
        Secrets page (shared). 0 when no secret / no key is set."""
        workflow = await self._get_workflow_or_raise(workflow_id)
        return await self._share_count(workflow)

    async def regenerate_api_key(self, workflow_id: uuid.UUID) -> str:
        workflow = await self._get_workflow_or_raise(workflow_id)
        if not (await self._secret_data(workflow)).get("api_key"):
            raise BusinessRuleViolation(
                message="No API key exists. Generate one first.",
                code="NO_API_KEY",
                context={"workflow_id": str(workflow_id)},
            )
        if await self._share_count(workflow) > 1:
            raise BusinessRuleViolation(
                message=(
                    "This trigger secret is shared by other workflows. "
                    "Regenerate it from the Secrets page so the change is "
                    "deliberate across every workflow that uses it."
                ),
                code="TRIGGER_SECRET_SHARED",
                context={"workflow_id": str(workflow_id)},
            )
        key = workflow.generate_api_key()
        await self._store_trigger_cred(workflow, "api_key", key)
        await self.workflow_repository.update(workflow)
        return key

    async def clear_api_key(self, workflow_id: uuid.UUID) -> None:
        workflow = await self._get_workflow_or_raise(workflow_id)
        workflow.clear_api_key()
        await self._unlink_and_cleanup_trigger_secret(workflow)

    async def regenerate_trigger_secret_key(
        self, secret_id: uuid.UUID, organization_id: uuid.UUID
    ) -> Dict[str, Any]:
        """Mint a fresh API key into an existing `workflow_trigger` secret - the
        deliberate rotation surface for a *shared* secret (the Secrets page). Every
        workflow referencing it immediately uses the new key. Returns the new key
        and how many workflows share it (the blast radius)."""
        repo = self.organization_secret_repository
        if repo is None:
            raise BusinessRuleViolation(
                message="Secret store is unavailable.",
                code="SECRET_STORE_UNAVAILABLE",
                context={"secret_id": str(secret_id)},
            )
        secret = await repo.get_by_id(secret_id, organization_id)
        if secret is None or secret.secret_type != "api_key":
            raise BusinessRuleViolation(
                message="No such API-key trigger secret in this organization.",
                code="INVALID_TRIGGER_SECRET",
                context={"secret_id": str(secret_id)},
            )
        new_key = Workflow.new_api_key()
        secret.secret_data = {**secret.secret_data, "api_key": new_key}
        await repo.update(secret)
        count = await self.workflow_repository.count_by_trigger_secret_id(secret_id)
        return {"api_key": new_key, "shared_by_count": count}

    async def recall_api_key(self, workflow_id: uuid.UUID) -> Optional[str]:
        """Return the workflow's stored API key from its OrganizationSecret, or
        None if no key is set. Admin-gated at the endpoint; this is the recall
        the hash-only storage couldn't do (the key was never recoverable)."""
        workflow = await self._get_workflow_or_raise(workflow_id)
        value = (await self._secret_data(workflow)).get("api_key")
        return value if isinstance(value, str) else None

    async def list_trigger_secrets(
        self, organization_id: uuid.UUID, secret_type: str
    ) -> List[Dict[str, Any]]:
        """The org's trigger secrets of a single TYPE with a shared-by-N count, for
        the 'reference an existing secret' picker. Each cred lives in its own typed
        row, so this filters on the `secret_type` column alone - no decrypting to
        sniff which field is populated."""
        repo = self.organization_secret_repository
        if repo is None:
            return []
        options: List[Dict[str, Any]] = []
        for meta in await repo.list_metadata_only(organization_id):
            if meta.get("secret_type") != secret_type:
                continue
            sid = uuid.UUID(meta["id"])
            count = await self.workflow_repository.count_by_trigger_secret_id(sid)
            options.append(
                {"id": meta["id"], "name": meta["name"], "shared_by_count": count}
            )
        return options

    async def set_trigger_secret(
        self, workflow_id: uuid.UUID, secret_id: uuid.UUID
    ) -> WorkflowResponse:
        """Point a workflow at an EXISTING `api_key` trigger secret (share it)
        instead of minting a new key, and switch it to the API trigger. Only API
        keys are shareable - a webhook's URL token is per-workflow and its signing
        secret has no cross-workflow meaning, so webhook-typed secrets are rejected.
        The previously-referenced secret (if any) is left intact - admin owns it."""
        workflow = await self._get_workflow_or_raise(workflow_id)
        repo = self.organization_secret_repository
        if repo is None:
            raise BusinessRuleViolation(
                message="Secret store is unavailable.",
                code="SECRET_STORE_UNAVAILABLE",
                context={"workflow_id": str(workflow_id)},
            )
        secret = await repo.get_by_id(secret_id, workflow.organization_id)
        if secret is None or secret.secret_type != "api_key":
            raise BusinessRuleViolation(
                message="No such API-key trigger secret in this organization.",
                code="INVALID_TRIGGER_SECRET",
                context={"workflow_id": str(workflow_id)},
            )
        workflow.trigger_secret_id = secret.id
        workflow.trigger_type = WorkflowTriggerType.API
        workflow.updated_at = datetime.now(UTC)
        await self.workflow_repository.update(workflow)
        return await self._build_response(workflow)

    async def get_trigger_secret_usage(
        self, secret_id: uuid.UUID, name_cap: int = 50
    ) -> Dict[str, Any]:
        """Who depends on this OrganizationSecret as their trigger credential, for
        the in-use warning before deletion. Returns the full count plus up to
        `name_cap` workflow names (the warning lists names when there aren't too
        many, falls back to the count otherwise)."""
        rows = await self.workflow_repository.list_by_trigger_secret_id(secret_id)
        return {
            "count": len(rows),
            "workflow_names": [r["name"] for r in rows[:name_cap]],
        }

    async def reset_workflows_for_trigger_secret(
        self, secret_id: uuid.UUID
    ) -> int:
        """Fall every workflow referencing this trigger secret back to manual - the
        secret is about to be deleted. Done in the app (not via the FK's SET NULL)
        because SET NULL nulls the link but leaves `trigger_type` stale at API /
        WEBHOOK, stranding the workflow as 'triggered but credential-less'. Returns
        how many workflows were reset."""
        rows = await self.workflow_repository.list_by_trigger_secret_id(secret_id)
        for row in rows:
            workflow = await self.workflow_repository.get_by_id(row["id"])
            if workflow is None:
                continue
            workflow.detach_trigger_secret()
            await self.workflow_repository.update(workflow)
        return len(rows)

    # ── Event trigger ─────────────────────────────────────────────────────
    async def set_event_trigger(
        self, workflow_id: uuid.UUID, source_workflow_id: uuid.UUID, on: str
    ) -> None:
        workflow = await self._get_workflow_or_raise(workflow_id)
        # Confirm the source exists and is in the same org (no cross-org chaining).
        source = await self._get_workflow_or_raise(source_workflow_id)
        if source.organization_id != workflow.organization_id:
            raise BusinessRuleViolation(
                message="Event source workflow must belong to the same organization.",
                code="EVENT_SOURCE_CROSS_ORG",
                context={"workflow_id": str(workflow_id)},
            )
        workflow.set_event_trigger(source_workflow_id, on)
        await self.workflow_repository.update(workflow)

    async def clear_event_trigger(self, workflow_id: uuid.UUID) -> None:
        workflow = await self._get_workflow_or_raise(workflow_id)
        workflow.clear_event_trigger()
        await self.workflow_repository.update(workflow)

    async def generate_step_webhook_token(
        self, workflow_id: uuid.UUID, step_id: str
    ) -> Dict[str, str]:
        # Token and secret stored in step.client_metadata; used by core.webhook_wait callbacks.
        workflow = await self._get_workflow_or_raise(workflow_id)

        if step_id not in workflow.steps:
            raise EntityNotFoundError("Step", step_id)

        step_config = workflow.steps[step_id]

        # Check if token already exists
        if step_config.client_metadata.get("webhook_token"):
            raise BusinessRuleViolation(
                message="Step webhook token already exists. Use regenerate to replace it.",
                code="TOKEN_EXISTS",
                context={"workflow_id": str(workflow_id), "step_id": step_id},
            )

        # Generate token and secret
        token = secrets.token_urlsafe(settings.WEBHOOK_TOKEN_LENGTH)
        secret = secrets.token_urlsafe(settings.WEBHOOK_SECRET_LENGTH)
        step_config.client_metadata["webhook_token"] = token
        step_config.client_metadata["webhook_secret"] = secret

        await self.workflow_repository.update(workflow)

        return {"token": token, "secret": secret}

    async def regenerate_step_webhook_token(
        self, workflow_id: uuid.UUID, step_id: str
    ) -> Dict[str, str]:
        workflow = await self._get_workflow_or_raise(workflow_id)

        if step_id not in workflow.steps:
            raise EntityNotFoundError("Step", step_id)

        step_config = workflow.steps[step_id]

        # Check if token exists
        if not step_config.client_metadata.get("webhook_token"):
            raise BusinessRuleViolation(
                message="No step webhook token exists. Use generate first.",
                code="NO_TOKEN",
                context={"workflow_id": str(workflow_id), "step_id": step_id},
            )

        # Generate new token and secret
        token = secrets.token_urlsafe(settings.WEBHOOK_TOKEN_LENGTH)
        secret = secrets.token_urlsafe(settings.WEBHOOK_SECRET_LENGTH)
        step_config.client_metadata["webhook_token"] = token
        step_config.client_metadata["webhook_secret"] = secret

        await self.workflow_repository.update(workflow)

        return {"token": token, "secret": secret}

    async def get_step_webhook_token(
        self, workflow_id: uuid.UUID, step_id: str
    ) -> Dict[str, str | None]:
        workflow = await self._get_workflow_or_raise(workflow_id)

        if step_id not in workflow.steps:
            raise EntityNotFoundError("Step", step_id)

        step_config = workflow.steps[step_id]
        return {
            "token": step_config.client_metadata.get("webhook_token"),
            "secret": step_config.client_metadata.get("webhook_secret"),
        }

    async def copy_workflow(
        self,
        workflow_id: uuid.UUID,
        user_id: uuid.UUID,
        organization_id: uuid.UUID,
        target_scope: str = "personal",
    ) -> WorkflowResponse:
        source = await self._get_workflow_or_raise(workflow_id)

        # Serialize steps for deep copy
        steps_dict = None
        if source.steps:
            steps_dict = {}
            for step_id, step_config in source.steps.items():
                steps_dict[step_id] = step_config.model_dump(mode="json")

        # Handle name collision
        copy_name = f"{source.name} (copy)"
        existing = await self.workflow_repository.get_by_name(
            organization_id, copy_name
        )
        if existing:
            counter = 2
            while True:
                copy_name = f"{source.name} (copy {counter})"
                existing = await self.workflow_repository.get_by_name(
                    organization_id, copy_name
                )
                if not existing:
                    break
                counter += 1

        command = WorkflowCreate(
            name=copy_name,
            description=source.description,
            organization_id=organization_id,
            created_by=user_id,
            steps=steps_dict,
            trigger_type=source.trigger_type,
            trigger_input_schema=source.trigger_input_schema,
            client_metadata={
                **(source.client_metadata or {}),
                "copied_from": str(source.id),
            },
            scope=target_scope,
        )
        return await self.create_workflow(command)

    async def request_publish(
        self, workflow_id: uuid.UUID, user_id: uuid.UUID
    ) -> WorkflowResponse:
        workflow = await self._get_workflow_or_raise(workflow_id)
        if workflow.created_by != user_id:
            raise BusinessRuleViolation(
                message="Only the workflow owner can request publishing",
                code="NOT_OWNER",
                context={
                    "workflow_id": str(workflow_id),
                    "created_by": str(workflow.created_by),
                    "user_id": str(user_id),
                },
            )
        workflow.request_publish()
        workflow = await self._persist_and_publish(workflow)
        return await self._build_response(workflow)

    async def approve_publish(self, workflow_id: uuid.UUID) -> WorkflowResponse:
        workflow = await self._get_workflow_or_raise(workflow_id)

        # Check name won't collide with existing org workflows
        existing = await self.workflow_repository.get_by_name(
            workflow.organization_id,
            workflow.name,
            exclude_id=workflow.id,
        )
        if existing:
            raise DuplicateEntityError(
                entity_type="Workflow", field="name", value=workflow.name
            )

        workflow.approve_publish()
        workflow = await self._persist_and_publish(workflow)
        return await self._build_response(workflow)

    async def reject_publish(self, workflow_id: uuid.UUID) -> WorkflowResponse:
        workflow = await self._get_workflow_or_raise(workflow_id)
        workflow.reject_publish()
        workflow = await self._persist_and_publish(workflow)
        return await self._build_response(workflow)

    async def import_workflow(
        self,
        data: Dict[str, Any],
        organization_id: uuid.UUID,
        provider_repo: Any = None,  # Optional ProviderRepository for validation
        prompt_repo: Any = None,  # Optional PromptRepository for validation
        created_by: Optional[uuid.UUID] = None,
        scope: WorkflowScope = WorkflowScope.PERSONAL,
    ) -> tuple[WorkflowResponse, List[str]]:
        # Validate required fields. BusinessRuleViolation is allowlisted by
        # safe_error_message, so the user-facing message is preserved.
        # ValueError would be masked to type-name-only.
        if "name" not in data:
            raise BusinessRuleViolation(
                "Workflow export must contain 'name' field"
            )
        if "steps" not in data:
            raise BusinessRuleViolation(
                "Workflow export must contain 'steps' field"
            )

        warnings: List[str] = []

        # Check provider compatibility if repo provided
        steps = data.get("steps", {})
        if provider_repo:
            for step_id, step_config in steps.items():
                if not isinstance(step_config, dict):
                    continue
                job = step_config.get("job", {})
                if not isinstance(job, dict):
                    job = {}
                # Step level takes precedence over job level.
                provider_id_str = step_config.get("provider_id") or job.get(
                    "provider_id"
                )
                if provider_id_str:
                    try:
                        provider_id = uuid.UUID(provider_id_str)
                        provider = await provider_repo.get_by_id(provider_id)
                        if not provider:
                            warnings.append(
                                f"Step '{step_id}': Provider {provider_id_str} not found"
                            )
                    except (ValueError, TypeError):
                        warnings.append(f"Step '{step_id}': Invalid provider_id format")

        # Check AI prompt availability if repo provided
        if prompt_repo:
            for step_id, step_config in steps.items():
                if not isinstance(step_config, dict):
                    continue
                input_mappings = step_config.get("input_mappings", {})
                if not isinstance(input_mappings, dict):
                    continue
                for _param, mapping in input_mappings.items():
                    if not isinstance(mapping, dict):
                        continue
                    if mapping.get("mappingType") != "prompt":
                        continue
                    prompt_id_str = mapping.get("promptId")
                    if not prompt_id_str:
                        warnings.append(
                            f"Step '{step_id}': No AI prompt selected"
                        )
                        continue
                    try:
                        prompt_id = uuid.UUID(prompt_id_str)
                        prompt = await prompt_repo.get_by_id(prompt_id)
                        if not prompt:
                            warnings.append(
                                f"Step '{step_id}': AI prompt {prompt_id_str} not found"
                            )
                    except (ValueError, TypeError):
                        warnings.append(
                            f"Step '{step_id}': Invalid AI prompt ID format"
                        )

        # Handle name collision
        workflow_name = data["name"]
        existing = await self.workflow_repository.list_by_organization(
            organization_id, skip=0, limit=settings.DEFAULT_FETCH_LIMIT
        )
        existing_names = {w.name for w in existing}
        if workflow_name in existing_names:
            workflow_name = f"{workflow_name} (imported)"
            counter = 2
            while workflow_name in existing_names:
                workflow_name = f"{data['name']} (imported {counter})"
                counter += 1

        # Parse trigger type
        trigger_type_str = data.get("trigger_type", "manual")
        try:
            trigger_type = WorkflowTriggerType(trigger_type_str.lower())
        except ValueError:
            trigger_type = WorkflowTriggerType.MANUAL

        # Create workflow
        workflow_create = WorkflowCreate(
            name=workflow_name,
            description=data.get("description"),
            organization_id=organization_id,
            created_by=created_by,
            trigger_type=trigger_type,
            steps=steps,
            trigger_input_schema=data.get("trigger_input_schema"),
            client_metadata=data.get("client_metadata"),
            scope=scope.value,
        )

        created_workflow = await self.create_workflow(workflow_create)
        return created_workflow, warnings
