# api/app/application/services/trigger_dispatcher.py

"""Single instance-creation path shared by every workflow trigger.

Webhook, schedule, api and event triggers all funnel through TriggerDispatcher.fire()
so the active-check, concurrency guard and InstanceCreate shape stay identical no
matter what kicked the workflow off. Trigger-specific auth (HMAC, bearer key, etc.)
happens in each caller *before* fire() is reached.
"""

import logging
import re
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from app.application.dtos.instance_dto import InstanceCreate
from app.application.dtos.workflow_dto import FormFieldResponse
from app.application.services.form_field_resolver import FormFieldResolver
from app.domain.common.exceptions import BusinessRuleViolation, ValidationError
from app.domain.workflow.models import Workflow, WorkflowStatus

if TYPE_CHECKING:
    from app.application.services.instance_service import InstanceService

logger = logging.getLogger(__name__)

# Triggers whose caller is a synchronous client we can fail fast: a missing
# required-no-default field is a request error to surface, not a default to
# paper over. Background triggers (schedule/event) have no caller to correct the
# payload, so they proceed on whatever defaults exist.
_SYNCHRONOUS_SOURCES = frozenset({"api", "webhook"})

# The UI trigger-snippet pre-fills no-default fields as blank ("") and, for any
# older/hand-edited snippet, may carry a "<required: ...>"/"<optional: ...>"
# placeholder. Either way the caller hasn't filled the field, so treat it as
# not-supplied — the field falls back to its default or is reported missing,
# rather than a blank/help-text value being injected as if real.
_PLACEHOLDER_RE = re.compile(r"^<(?:required|optional): .*>$")


def _is_unfilled_value(value: Any) -> bool:
    """True for a blank string or an unfilled trigger-snippet placeholder."""
    return isinstance(value, str) and (
        value.strip() == "" or bool(_PLACEHOLDER_RE.match(value))
    )


# Services that block concurrent workflow instances because they share resources
# across instances (e.g., webhook_wait shares callback URLs). Add new services
# here rather than hardcoding service_id checks throughout the codebase.
SERVICES_BLOCKING_CONCURRENT_INSTANCES = frozenset(
    {
        "core.webhook_wait",
    }
)


class TriggerDispatcher:
    """Creates a workflow instance for a trigger, enforcing the rules common to all."""

    def __init__(
        self,
        instance_service: "InstanceService",
        form_field_resolver: FormFieldResolver,
    ) -> None:
        self.instance_service = instance_service
        self.form_field_resolver = form_field_resolver

    async def fire(
        self,
        workflow: Workflow,
        payload: Dict[str, Any],
        source: str,
        extra_metadata: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """Create one instance of `workflow`, resolving form defaults, and run it.

        The incoming `payload` is keyed by stable `field_id`s. Defaults from the
        experience config are merged underneath it (incoming wins), the result is
        translated to internal `{step_id}.{parameter_key}` form-value keys, and
        the instance is started through the same snapshot-injection path the UI
        run form uses — so a triggered run executes at its configured defaults
        instead of being created and parked.

        Args:
            workflow: the workflow to run (must be ACTIVE).
            payload: field_id-keyed form values plus any trigger-context data.
            source: trigger origin tag stored in client_metadata.source
                    (e.g. "webhook", "schedule", "api", "event").
            extra_metadata: merged into client_metadata for trigger-specific context.

        Returns the InstanceResponse from instance_service.submit_form_and_start.
        Raises ValidationError on inactive workflow or blocking-step contention,
        and BusinessRuleViolation (api/webhook only) on a missing
        required-no-default field.
        """
        if workflow.status != WorkflowStatus.ACTIVE:
            raise ValidationError(
                message=f"Workflow is not active (status: {workflow.status.value})",
                code="WORKFLOW_INACTIVE",
            )

        # Merge defaults under the payload and enforce the api/webhook contract
        # before creating anything, so a rejected sync request leaves no instance.
        fields = await self.form_field_resolver.resolve_fields(workflow)
        form_values = self._resolve_form_values(fields, payload, source)

        # A step that shares resources across instances can't run concurrently.
        has_blocking_step = any(
            step.job and step.job.service_id in SERVICES_BLOCKING_CONCURRENT_INSTANCES
            for step in workflow.steps.values()
        )
        if has_blocking_step:
            running_count = await self.instance_service.count_running_instances(
                workflow.id
            )
            if running_count > 0:
                raise ValidationError(
                    message="This workflow contains a step that blocks concurrent "
                    "instances. Only one instance can run at a time because "
                    "resources are shared.",
                    code="BLOCKING_STEP_INSTANCE_RUNNING",
                )

        client_metadata: Dict[str, Any] = {"source": source}
        if extra_metadata:
            client_metadata.update(extra_metadata)

        # Keep the raw payload in input_data for trigger-context mappings
        # (mappingType=trigger); resolved form values go through form_values.
        instance_create = InstanceCreate(
            workflow_id=workflow.id,
            user_id=workflow.created_by,
            created_by=workflow.created_by,
            input_data=payload,
            client_metadata=client_metadata,
        )
        instance = await self.instance_service.create_instance(instance_create)
        return await self.instance_service.submit_form_and_start(
            instance.id, form_values
        )

    def _resolve_form_values(
        self,
        fields: List[FormFieldResponse],
        payload: Dict[str, Any],
        source: str,
    ) -> Dict[str, Any]:
        """Merge defaults under the payload in field_id space, enforce the
        api/webhook contract, and translate to internal form-value keys.

        Returns ``{f"{step_id}.{parameter_key}": value}`` ready for
        ``submit_form_and_start``.
        """
        known_ids = {f.field_id for f in fields}
        is_sync = source in _SYNCHRONOUS_SOURCES

        # Keep only recognised form fields; any other key (the webhook envelope's
        # body/query/method, n8n-style trigger context, etc.) is left for
        # mappingType=trigger to read from input_data and never treated as a form
        # value. Blank/placeholder values count as not-supplied, so firing the
        # snippet verbatim falls back to defaults (or reports a missing required
        # field) instead of injecting a blank or the help text as a real value.
        incoming = {
            k: v
            for k, v in payload.items()
            if k in known_ids and not _is_unfilled_value(v)
        }

        merged = {**FormFieldResolver.resolve_defaults(fields), **incoming}

        missing = [
            fid
            for fid in FormFieldResolver.required_without_default(fields)
            if fid not in merged
        ]
        if missing:
            if is_sync:
                raise BusinessRuleViolation(
                    message="Missing required field(s): " + ", ".join(sorted(missing)),
                    code="MISSING_REQUIRED_FORM_FIELD",
                )
            logger.warning(
                "Trigger %s for workflow is missing required field(s) %s; "
                "running on available defaults.",
                source,
                sorted(missing),
            )

        key_map = FormFieldResolver.field_id_to_internal_key(fields)
        return {key_map[fid]: value for fid, value in merged.items()}
