# api/app/application/services/webhook_service.py

import hashlib
import hmac
import json
import logging
import re
import time
import uuid
from typing import (
    Any,
    Awaitable,
    Callable,
    Dict,
    List,
    Optional,
    TYPE_CHECKING,
    cast,
)

import jsonpath_ng
import jwt
from jwt.exceptions import ExpiredSignatureError, PyJWTError as JWTError

from app.application.interfaces import EventBus
from app.application.services.trigger_dispatcher import TriggerDispatcher
from app.domain.common.exceptions import (
    EntityNotFoundError,
    ValidationError,
)
from app.domain.instance.iteration_execution import IterationExecutionStatus
from app.domain.workflow.repository import WorkflowRepository

if TYPE_CHECKING:
    from app.application.services.form_field_resolver import FormFieldResolver
    from app.domain.organization_secret import OrganizationSecretRepository
    from app.application.services.instance_service import InstanceService
    from app.application.services.job_enqueue import JobEnqueueService
    from app.domain.instance.iteration_execution_repository import (
        IterationExecutionRepository,
    )
    from app.domain.instance.repository import InstanceRepository
    from app.domain.instance_step.step_execution_repository import (
        StepExecutionRepository,
    )
    from app.domain.provider.repository import (
        ProviderCredentialRepository,
        ProviderRepository,
        ProviderServiceRepository,
    )

# Callback handler routes a step result back through the same processor a
# worker submission uses (one completion path for both triggers).
ProcessResultFn = Callable[[Dict[str, Any]], Awaitable[None]]

logger = logging.getLogger(__name__)

# ValidationError codes meaning "credentials were presented and rejected". Every
# trigger endpoint maps these to 401 and everything else to 400, so a new auth
# type joins this set rather than editing each endpoint. Server-side
# misconfiguration (UNSUPPORTED_AUTH_TYPE) is deliberately not here: no
# credential the sender can present would change the outcome.
AUTH_FAILURE_CODES = frozenset(
    {
        "HEADER_AUTH_FAILED",
        "JWT_AUTH_FAILED",
        "INVALID_SIGNATURE",
        "UNAUTHORIZED",
        "INVALID_API_KEY",
    }
)

# Hash functions a signed_raw_body verifier may name. An allowlist, so a config
# blob cannot select an arbitrary hashlib attribute.
SIGNATURE_ALGORITHMS = {
    "sha1": hashlib.sha1,
    "sha256": hashlib.sha256,
    "sha512": hashlib.sha512,
}

_SIGNED_TEMPLATE_TOKEN = re.compile(r"\{(body|timestamp)\}")


def render_signed_template(template: str, timestamp: str, raw_body: bytes) -> bytes:
    """Substitute {timestamp} and {body} in a single pass, so a substituted
    value cannot introduce a token the next substitution would expand."""
    out: List[bytes] = []
    pos = 0
    for match in _SIGNED_TEMPLATE_TOKEN.finditer(template):
        out.append(template[pos : match.start()].encode("utf-8"))
        out.append(raw_body if match.group(1) == "body" else timestamp.encode("utf-8"))
        pos = match.end()
    out.append(template[pos:].encode("utf-8"))
    return b"".join(out)


class WebhookService:

    def __init__(
        self,
        workflow_repository: WorkflowRepository,
        instance_service: "InstanceService",
        event_bus: EventBus,
        provider_repository: Optional["ProviderRepository"] = None,
        provider_service_repository: Optional["ProviderServiceRepository"] = None,
        provider_credential_repository: Optional["ProviderCredentialRepository"] = None,
        instance_repository: Optional["InstanceRepository"] = None,
        step_execution_repository: Optional["StepExecutionRepository"] = None,
        iteration_execution_repository: Optional[
            "IterationExecutionRepository"
        ] = None,
        job_enqueue_service: Optional["JobEnqueueService"] = None,
        process_result_fn: Optional[ProcessResultFn] = None,
        form_field_resolver: Optional["FormFieldResolver"] = None,
        organization_secret_repository: Optional[
            "OrganizationSecretRepository"
        ] = None,
    ):
        self.organization_secret_repository = organization_secret_repository
        self.workflow_repository = workflow_repository
        self.instance_service = instance_service
        self._trigger_dispatcher = TriggerDispatcher(
            instance_service, cast("FormFieldResolver", form_field_resolver)
        )
        self.event_bus = event_bus
        # Wired only for the public webhook endpoint, which routes declarative
        # provider-completion callbacks (resolved credential->provider envelope)
        # in addition to workflow-trigger and step-callback tokens.
        self.provider_repository = provider_repository
        self.provider_service_repository = provider_service_repository
        self.provider_credential_repository = provider_credential_repository
        self.instance_repository = instance_repository
        self.step_execution_repository = step_execution_repository
        self.iteration_execution_repository = iteration_execution_repository
        self.job_enqueue_service = job_enqueue_service
        self.process_result_fn = process_result_fn

    def _verify_signature(
        self,
        secret: str,
        payload: Dict[str, Any],
        signature_header: Optional[str],
    ) -> bool:
        if not signature_header:
            return False

        # Parse signature header (format: sha256=<hex-digest>)
        if not signature_header.startswith("sha256="):
            logger.warning("Invalid signature format: missing sha256= prefix")
            return False

        expected_signature = signature_header[7:]  # Remove "sha256=" prefix

        # Compute HMAC-SHA256 of the JSON-encoded payload
        payload_bytes = json.dumps(
            payload, separators=(",", ":"), sort_keys=True
        ).encode()
        computed_signature = hmac.new(
            secret.encode(),
            payload_bytes,
            hashlib.sha256,
        ).hexdigest()

        # Use constant-time comparison to prevent timing attacks
        return hmac.compare_digest(computed_signature, expected_signature)

    def _verify_header_auth(
        self,
        expected_header_name: str,
        expected_header_value: str,
        headers: Dict[str, str],
    ) -> bool:
        # Headers are case-insensitive
        header_name_lower = expected_header_name.lower()
        for key, value in headers.items():
            if key.lower() == header_name_lower:
                return hmac.compare_digest(value, expected_header_value)
        return False

    def _verify_jwt_auth(
        self,
        jwt_secret: str,
        headers: Dict[str, str],
    ) -> bool:
        # Expects Authorization: Bearer <jwt> (HS256)
        auth_header = None
        for key, value in headers.items():
            if key.lower() == "authorization":
                auth_header = value
                break

        if not auth_header:
            logger.warning("JWT auth required but no Authorization header found")
            return False

        # Parse "Bearer <token>"
        parts = auth_header.split(" ", 1)
        if len(parts) != 2 or parts[0].lower() != "bearer":
            logger.warning(
                "Invalid Authorization header format (expected 'Bearer <token>')"
            )
            return False

        token = parts[1]

        try:
            # Verify and decode the JWT using HS256
            jwt.decode(token, jwt_secret, algorithms=["HS256"])
            return True
        except ExpiredSignatureError:
            logger.warning("JWT has expired")
            return False
        except JWTError as e:
            logger.warning(f"Invalid JWT: {e}")
            return False

    def _handshake_response(
        self, workflow: Any, payload: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """The sender's URL-verification echo, described by webhook_config.handshake.
        Returns the reply to send, or None when this request is not a handshake."""
        config = (getattr(workflow, "webhook_config", None) or {}).get(
            "handshake"
        ) or {}
        match_field = config.get("match_field")
        echo_field = config.get("echo_field")
        if not match_field or not echo_field:
            return None

        body = payload.get("body")
        if not isinstance(body, dict) or body.get(match_field) != config.get(
            "match_value"
        ):
            return None

        echoed = body.get(echo_field)
        if not isinstance(echoed, str):
            logger.warning(
                f"Handshake on workflow {workflow.id} has no {echo_field} to echo"
            )
            raise ValidationError(
                message=f"Handshake request is missing its '{echo_field}' value",
                code="INVALID_HANDSHAKE",
            )
        return {"status": "handshake", "body": {echo_field: echoed}}

    def _verify_signed_raw_body(
        self,
        workflow: Any,
        headers: Dict[str, str],
        secret: Optional[str],
        raw_body: Optional[bytes],
    ) -> None:
        """Verify a signature computed over a template rendered from the request
        timestamp and the raw body. Every parameter is read from the workflow's
        webhook_config; nothing about a specific sender is encoded here.

        Unlike the header and jwt branches this fails closed on an incomplete
        config: there are no live workflows carrying this auth type, so rejecting
        cannot silently disable a working endpoint.
        """
        config = (getattr(workflow, "webhook_config", None) or {}).get("auth") or {}
        signature_header = config.get("signature_header")
        template = config.get("signed_template")
        algorithm = SIGNATURE_ALGORITHMS.get(str(config.get("algorithm", "")))

        if not signature_header or not template or algorithm is None or not secret:
            logger.warning(
                f"signed_raw_body auth is incompletely configured for workflow {workflow.id}"
            )
            raise ValidationError(
                message="Webhook signature verification is not fully configured",
                code="WEBHOOK_AUTH_MISCONFIGURED",
            )

        if raw_body is None:
            logger.warning(
                f"signed_raw_body auth has no raw body to verify for workflow {workflow.id}"
            )
            raise ValidationError(
                message="Webhook signature verification requires a request body",
                code="WEBHOOK_AUTH_MISCONFIGURED",
            )

        timestamp = ""
        if "{timestamp}" in template:
            timestamp_header = config.get("timestamp_header")
            max_age = config.get("max_age_seconds")
            if not timestamp_header or not isinstance(max_age, int):
                logger.warning(
                    f"signed_raw_body template needs a timestamp but none is configured for workflow {workflow.id}"
                )
                raise ValidationError(
                    message="Webhook signature verification is not fully configured",
                    code="WEBHOOK_AUTH_MISCONFIGURED",
                )
            timestamp = headers.get(str(timestamp_header).lower(), "")
            try:
                sent_at = int(timestamp)
            except ValueError:
                raise ValidationError(
                    message="Missing or invalid webhook signature timestamp",
                    code="INVALID_SIGNATURE",
                )
            # Checked in both directions: a far-future timestamp is as much a
            # replay marker as a stale one.
            if abs(int(time.time()) - sent_at) > max_age:
                raise ValidationError(
                    message="Webhook signature timestamp is outside the accepted window",
                    code="INVALID_SIGNATURE",
                )

        presented = headers.get(str(signature_header).lower(), "")
        prefix = config.get("signature_prefix") or ""
        if prefix:
            if not presented.startswith(str(prefix)):
                raise ValidationError(
                    message="Invalid webhook signature",
                    code="INVALID_SIGNATURE",
                )
            presented = presented[len(str(prefix)) :]

        expected = hmac.new(
            str(secret).encode("utf-8"),
            render_signed_template(str(template), timestamp, raw_body),
            algorithm,
        ).hexdigest()

        if not presented or not hmac.compare_digest(expected, presented):
            logger.warning(f"Invalid webhook signature for workflow {workflow.id}")
            raise ValidationError(
                message="Invalid webhook signature",
                code="INVALID_SIGNATURE",
            )

    def _verify_webhook_auth(
        self,
        workflow: Any,
        headers: Dict[str, str],
        secret_data: Dict[str, Any],
    ) -> None:
        # The header-auth value and JWT secret live in the workflow's
        # OrganizationSecret (keys: webhook_auth_value / webhook_jwt_secret); the
        # caller passes its decrypted secret_data in. The header NAME is non-secret
        # config and stays on the workflow row.
        auth_type = getattr(workflow, "webhook_auth_type", "none")

        if auth_type == "none":
            return  # No auth required

        if auth_type == "header":
            header_name = workflow.webhook_auth_header_name
            header_value = secret_data.get("webhook_auth_value")
            if not header_name or not header_value:
                logger.warning(
                    f"Header auth configured but missing header name/value for workflow {workflow.id}"
                )
                return  # Misconfigured - allow through (fail open)

            if not self._verify_header_auth(header_name, header_value, headers):
                raise ValidationError(
                    message=f"Invalid or missing {header_name} header",
                    code="HEADER_AUTH_FAILED",
                )

        elif auth_type == "jwt":
            jwt_secret = secret_data.get("webhook_jwt_secret")
            if not jwt_secret:
                logger.warning(
                    f"JWT auth configured but missing secret for workflow {workflow.id}"
                )
                return  # Misconfigured - allow through (fail open)

            if not self._verify_jwt_auth(jwt_secret, headers):
                raise ValidationError(
                    message="Invalid or missing JWT authentication",
                    code="JWT_AUTH_FAILED",
                )

        elif auth_type == "hmac":
            # HMAC verification requires the payload, handled separately in _handle_workflow_trigger
            pass

        elif auth_type == "signed_raw_body":
            # Signature verification requires the raw body, handled separately
            # in _handle_workflow_trigger
            pass

        else:
            # Unrecognized auth type rejects the request rather than falling
            # through to an implicit accept.
            logger.warning(
                f"Unrecognized webhook auth type {auth_type!r} for workflow {workflow.id}"
            )
            raise ValidationError(
                message="Unsupported webhook authentication type",
                code="UNSUPPORTED_AUTH_TYPE",
            )

    async def handle_incoming_webhook_by_token(
        self,
        token: str,
        payload: Dict[str, Any],
        headers: Dict[str, str],
        raw_body: Optional[bytes] = None,
    ) -> Dict[str, Any]:
        # Try workflow token first (trigger), then step token (callback)
        workflow = await self.workflow_repository.get_by_webhook_token(token)

        if workflow:
            # This is a workflow trigger - create new instance
            return await self._handle_workflow_trigger(
                workflow, payload, headers, raw_body
            )

        # Not a workflow token - try to find a step by its webhook_token (step callback)
        step_result = await self.workflow_repository.get_by_step_webhook_token(token)

        if step_result:
            workflow, step_id = step_result
            return await self._handle_step_callback(workflow, step_id, payload, headers)

        # Not a workflow/step token - try a declarative provider-completion
        # callback routed by the credential's stable webhook_callback_token. One
        # callback URL per credential (the Leonardo key's immutable binding);
        # callbacks demultiplex to the right parked step by generation id.
        if self.provider_credential_repository is not None:
            credential = (
                await self.provider_credential_repository.get_by_webhook_callback_token(
                    token
                )
            )
            if credential is not None:
                return await self._handle_provider_callback(credential, payload, headers)

        # Not a credential token - try a per-iteration execution token: the URL
        # token IS the parked iteration row's external_id (json2video-style
        # routing), self-routing with no credential or generation-id demux.
        if self.iteration_execution_repository is not None:
            row = await self.iteration_execution_repository.get_by_external_id(token)
            if row is not None:
                return await self._handle_execution_token_callback(
                    row, payload, headers
                )

        # Token not found anywhere
        raise EntityNotFoundError(
            "Webhook",
            token,
            "No workflow or step found with this webhook token",
        )

    async def _trigger_secret_data(self, workflow: Any) -> Dict[str, Any]:
        """Decrypted trigger creds for a workflow from its referenced
        OrganizationSecret, or {} when none is set / not wired."""
        repo = self.organization_secret_repository
        secret_id = getattr(workflow, "trigger_secret_id", None)
        if repo is None or not secret_id:
            return {}
        secret = await repo.get_by_id(secret_id, workflow.organization_id)
        return secret.secret_data if secret else {}

    async def handle_api_trigger(
        self,
        workflow_id: uuid.UUID,
        api_key: str,
        payload: Dict[str, Any],
        headers: Dict[str, str],
    ) -> Dict[str, Any]:
        """Trigger a workflow via its API key (API trigger). Bearer-key auth.

        The key is stored encrypted in the workflow's OrganizationSecret; the
        URL carries {workflow_id}, so resolve the workflow and constant-time
        compare the presented key to the stored one.
        """
        if not api_key:
            raise ValidationError(message="Missing API key", code="UNAUTHORIZED")

        # Do not leak whether the key or the workflow id was wrong: both 401.
        workflow = await self.workflow_repository.get_by_id(workflow_id)
        if workflow is None:
            raise ValidationError(message="Invalid API key", code="INVALID_API_KEY")
        stored = (await self._trigger_secret_data(workflow)).get("api_key")
        if not stored or not hmac.compare_digest(str(stored), api_key):
            raise ValidationError(message="Invalid API key", code="INVALID_API_KEY")

        instance = await self._trigger_dispatcher.fire(
            workflow, payload, source="api"
        )

        return {
            "status": "accepted",
            "workflow_id": str(workflow.id),
            "instance_id": str(instance.id),
            "message": "Workflow instance created",
        }

    def _extract_jsonpath(self, data: Dict[str, Any], path: str) -> Any:
        """First match of a JSONPath expression, or None when nothing matches."""
        matches = jsonpath_ng.parse(path).find(data)
        return matches[0].value if matches else None

    def _extract_jsonpath_all(self, data: Dict[str, Any], path: str) -> List[Any]:
        """Every match of a JSONPath expression (the asset list)."""
        return [m.value for m in jsonpath_ng.parse(path).find(data)]

    def _verify_bearer_credential(
        self, headers: Dict[str, str], expected_key: str
    ) -> bool:
        """Constant-time compare the inbound bearer token to the stored key."""
        for key, value in headers.items():
            if key.lower() == "authorization":
                parts = value.split(" ", 1)
                if len(parts) == 2 and parts[0].lower() == "bearer":
                    return hmac.compare_digest(parts[1], expected_key)
                return hmac.compare_digest(value, expected_key)
        return False

    async def _handle_provider_callback(
        self,
        credential: Any,  # ProviderCredential
        payload: Dict[str, Any],
        headers: Dict[str, str],
    ) -> Dict[str, Any]:
        """Declarative provider-completion callback. The credential's stable
        callback token is the auth gate; the provider-level webhook_completion
        envelope (one shape per provider) supplies the inbound paths + auth, and
        the generation id in the payload demultiplexes to the right parked
        iteration row. Success enqueues a retrieve sub-job; failure routes a
        failed iteration result through the shared completion path.

        Resolution after demux uses no assignment: row -> instance (org +
        workflow), row.step_id (StepExecution UUID) -> step_key -> workflow
        step -> job (service_id/provider_id), and the service-level
        webhook_completion supplies result_callback_path.
        """
        iter_repo = cast(
            "IterationExecutionRepository", self.iteration_execution_repository
        )
        provider_repo = cast("ProviderRepository", self.provider_repository)

        # Provider-level envelope: the inbound callback shape + auth, one per
        # provider, resolvable from the credential alone (pre-demux).
        provider = await provider_repo.get_by_slug(credential.provider_slug)
        envelope = (getattr(provider, "client_metadata", None) or {}).get(
            "webhook_completion"
        )
        if not envelope:
            raise ValidationError(
                message="Provider is not configured for webhook completion",
                code="WEBHOOK_COMPLETION_NOT_CONFIGURED",
            )

        # Inbound auth per the declared type. bearer_header compares a stored
        # credential field; url_token / none lean on the opaque callback token.
        auth = envelope.get("auth") or {}
        if auth.get("type") == "bearer_header":
            expected_key = (getattr(credential, "credentials", None) or {}).get(
                auth.get("credential_field")
            )
            if not expected_key or not self._verify_bearer_credential(
                headers, expected_key
            ):
                raise ValidationError(
                    message="Invalid or missing callback authentication",
                    code="CALLBACK_AUTH_FAILED",
                )

        # Match the provider's generation id to its iteration row.
        raw_id = self._extract_jsonpath(payload, envelope["id_callback_path"])
        if raw_id is None:
            raise EntityNotFoundError(
                "WebhookGeneration", "", "Callback carried no matchable id"
            )
        row = await iter_repo.get_by_external_id(str(raw_id))
        if row is None:
            # No live iteration row owns this generation id. Almost always a
            # late/duplicate callback for a generation whose row was cleared by
            # a rerun/retry/regenerate (the external_id is orphaned by design
            # now - Phase 2). Drop it gracefully (202) instead of 404 so the
            # provider doesn't retry or alarm on a callback there's nothing to
            # do with. A genuinely malformed callback (no id at all) still
            # errors above.
            return self._callback_noop("unmatched", str(raw_id))

        # Resolve the parked step + run the shared idempotency guards.
        ctx = await self._resolve_iteration_completion_context(row)
        guard = self._iteration_callback_guard(row, ctx, str(raw_id))
        if guard is not None:
            return guard

        # Status gate. Absent failure_values => any non-success terminal fails.
        # Status + success/failure values are envelope (provider-level); the
        # asset shape (result_callback_path) is the service block.
        status_value = self._extract_jsonpath(
            payload, envelope["status_callback_path"]
        )
        success_values = envelope.get("success_values") or []
        failure_values = envelope.get("failure_values")

        if status_value in success_values:
            asset_urls = self._extract_jsonpath_all(
                payload, ctx["service_completion"]["result_callback_path"]
            )
            await self._enqueue_retrieve_for_row(
                row, ctx, asset_urls, credential_id=str(credential.id)
            )
            return self._callback_accepted("retrieving", str(raw_id))

        is_failure = failure_values is None or status_value in failure_values
        if is_failure:
            await self._fail_iteration_from_callback(
                row,
                ctx,
                f"Provider reported callback status '{status_value}'",
            )
            return self._callback_accepted("failed", str(raw_id))

        # Non-terminal status (provider still working): nothing to do yet.
        return self._callback_noop("pending", str(raw_id))

    async def _handle_execution_token_callback(
        self,
        row: Any,  # IterationExecution
        payload: Dict[str, Any],
        headers: Dict[str, str],
    ) -> Dict[str, Any]:
        """Provider-completion callback routed by a per-iteration token: the URL
        token IS the row's external_id (minted at enqueue), so the row is matched
        before this is called - no credential, no demux, no inbound auth (the
        unguessable token is the only gate, e.g. json2video sends no signature).

        Success is asset-presence at the service's result_callback_path; an empty
        result means the provider failed the render. Assets download via the same
        seeded retrieve sub-job the generation_id path uses.
        """
        token = str(row.external_id)
        ctx = await self._resolve_iteration_completion_context(row)
        guard = self._iteration_callback_guard(row, ctx, token)
        if guard is not None:
            return guard

        # Success == a non-empty asset. json2video's failure callback still fires
        # but with an empty/absent url, so drop falsy matches before deciding.
        asset_urls = [
            u
            for u in self._extract_jsonpath_all(
                payload, ctx["service_completion"]["result_callback_path"]
            )
            if u
        ]
        if asset_urls:
            # credential_id=None: the asset is a public provider CDN URL; the
            # seeded download needs no auth.
            await self._enqueue_retrieve_for_row(
                row, ctx, asset_urls, credential_id=None
            )
            return self._callback_accepted("retrieving", token)

        await self._fail_iteration_from_callback(
            row, ctx, "Provider callback carried no result asset"
        )
        return self._callback_accepted("failed", token)

    async def _resolve_iteration_completion_context(
        self, row: Any
    ) -> Dict[str, Any]:
        """Resolve a matched iteration row to its step/service completion context.

        No assignment: row -> instance (org + workflow), row.step_id
        (StepExecution UUID) -> step_key -> workflow step -> job
        (service_id/provider_id), and the service-level webhook_completion
        supplies result_callback_path. Raises on a vanished step / unconfigured
        service.
        """
        iter_repo = cast(
            "IterationExecutionRepository", self.iteration_execution_repository
        )
        svc_repo = cast("ProviderServiceRepository", self.provider_service_repository)
        instance_repo = cast("InstanceRepository", self.instance_repository)
        step_repo = cast("StepExecutionRepository", self.step_execution_repository)

        step_execution = await step_repo.get_by_id(row.step_id)
        instance = await instance_repo.get_by_id(row.instance_id)
        if step_execution is None or instance is None:
            raise EntityNotFoundError(
                "WebhookStep",
                str(row.step_id),
                "Parked workflow step no longer exists",
            )
        step_key = step_execution.step_key
        workflow = await self.workflow_repository.get_by_id(instance.workflow_id)
        step = workflow.steps.get(step_key) if workflow else None
        job = step.job if step else None
        if job is None:
            raise EntityNotFoundError(
                "WebhookStep",
                step_key,
                "Parked workflow step no longer exists",
            )
        service_id = job.service_id or ""
        service = await svc_repo.get_by_service_id(service_id, 0, 1)
        service_completion = (getattr(service, "client_metadata", None) or {}).get(
            "webhook_completion"
        )
        if not service_completion:
            raise ValidationError(
                message="Service is not configured for webhook completion",
                code="WEBHOOK_COMPLETION_NOT_CONFIGURED",
            )
        siblings = await iter_repo.list_by_step_id(row.step_id)
        group_siblings = [
            s for s in siblings if s.iteration_group_id == row.iteration_group_id
        ]
        return {
            "step_key": step_key,
            "organization_id": instance.organization_id,
            "service_id": service_id,
            "provider_id": str(job.provider_id) if job.provider_id else None,
            "service_completion": service_completion,
            "group_siblings": group_siblings,
            "iteration_count": len(group_siblings),
            "group_id": (
                str(row.iteration_group_id) if row.iteration_group_id else None
            ),
        }

    def _iteration_callback_guard(
        self, row: Any, ctx: Dict[str, Any], match_id: str
    ) -> Optional[Dict[str, Any]]:
        """Shared idempotency guards: a row past PENDING was already handled
        (dup callback); a sibling in a failed/cancelled terminal means the step
        is finishing or gone (drop late callbacks, I-5). Returns a no-op response
        to return directly, or None to proceed."""
        if row.status != IterationExecutionStatus.PENDING:
            return self._callback_noop("duplicate", match_id)
        if any(
            s.status
            in (IterationExecutionStatus.FAILED, IterationExecutionStatus.CANCELLED)
            for s in ctx["group_siblings"]
        ):
            return self._callback_noop("step_terminal", match_id)
        return None

    async def _enqueue_retrieve_for_row(
        self,
        row: Any,
        ctx: Dict[str, Any],
        asset_urls: List[Any],
        *,
        credential_id: Optional[str],
    ) -> None:
        """Mark the row in-flight so a duplicate callback is a no-op, then enqueue
        the seeded download whose result completes the iteration."""
        iter_repo = cast(
            "IterationExecutionRepository", self.iteration_execution_repository
        )
        enqueue = cast("JobEnqueueService", self.job_enqueue_service)
        row.queue()
        await iter_repo.update(row)
        await enqueue.enqueue_webhook_retrieve_job(
            instance_id=row.instance_id,
            organization_id=ctx["organization_id"],
            step_id=ctx["step_key"],
            service_id=ctx["service_id"],
            provider_id=ctx["provider_id"],
            credential_id=credential_id,
            asset_urls=asset_urls,
            iteration_index=row.iteration_index,
            iteration_count=ctx["iteration_count"],
            iteration_group_id=ctx["group_id"],
        )

    async def _fail_iteration_from_callback(
        self, row: Any, ctx: Dict[str, Any], error: str
    ) -> None:
        """Route a failed iteration through the same processor a worker result
        uses; the shared finalizer fails the step once the aggregate is terminal
        and cancels siblings."""
        process_result = cast(ProcessResultFn, self.process_result_fn)
        await process_result(
            {
                "instance_id": str(row.instance_id),
                "step_id": ctx["step_key"],
                "status": "FAILED",
                "result": {},
                "error": error,
                "iteration_index": row.iteration_index,
                "iteration_count": ctx["iteration_count"],
                "iteration_group_id": ctx["group_id"],
            }
        )

    def _callback_accepted(self, outcome: str, generation_id: str) -> Dict[str, Any]:
        logger.info(
            "Webhook callback accepted: outcome=%s generation_id=%s",
            outcome,
            generation_id,
        )
        return {
            "status": "accepted",
            "webhook_type": "provider_callback",
            "outcome": outcome,
            "generation_id": generation_id,
        }

    def _callback_noop(self, reason: str, generation_id: str) -> Dict[str, Any]:
        logger.info(
            "Webhook callback ignored: reason=%s generation_id=%s",
            reason,
            generation_id,
        )
        return {
            "status": "ignored",
            "webhook_type": "provider_callback",
            "reason": reason,
            "generation_id": generation_id,
        }

    async def _handle_workflow_trigger(
        self,
        workflow: Any,  # Workflow type
        payload: Dict[str, Any],
        headers: Dict[str, str],
        raw_body: Optional[bytes] = None,
    ) -> Dict[str, Any]:
        # Verify webhook authentication based on auth type. All secret material
        # (HMAC secret, header-auth value, JWT secret) lives in the workflow's
        # OrganizationSecret; fetch it once and route by auth type.
        auth_type = getattr(workflow, "webhook_auth_type", "none")
        secret_data = await self._trigger_secret_data(workflow)

        if auth_type == "hmac":
            # HMAC authentication: verify signature against the stored signing secret.
            webhook_secret = secret_data.get("webhook_secret")
            if webhook_secret:
                # Support both X-Hub-Signature-256 (GitHub/standard) and X-Webhook-Signature
                signature = headers.get("x-hub-signature-256") or headers.get(
                    "x-webhook-signature"
                )
                if not self._verify_signature(
                    webhook_secret, payload, signature
                ):
                    logger.warning(
                        f"Invalid webhook signature for workflow {workflow.id}"
                    )
                    raise ValidationError(
                        message="Invalid webhook signature",
                        code="INVALID_SIGNATURE",
                    )
            else:
                logger.warning(
                    f"HMAC auth configured but missing secret for workflow {workflow.id}"
                )
        elif auth_type == "signed_raw_body":
            self._verify_signed_raw_body(
                workflow, headers, secret_data.get("webhook_secret"), raw_body
            )
        else:
            # Header Auth or JWT Auth
            self._verify_webhook_auth(workflow, headers, secret_data)

        # Answered after verification, so an unsigned request cannot learn that a
        # workflow exists by asking it to echo.
        handshake = self._handshake_response(workflow, payload)
        if handshake is not None:
            return handshake

        # Active-check, concurrency guard and instance creation are shared with
        # every other trigger type via TriggerDispatcher.
        instance_response = await self._trigger_dispatcher.fire(
            workflow,
            payload,
            source="webhook",
            extra_metadata={
                "webhook_type": "workflow_trigger",
                "headers": {
                    k: v
                    for k, v in headers.items()
                    if k.lower() not in ("authorization", "x-webhook-signature")
                },
            },
        )

        return {
            "status": "accepted",
            "webhook_type": "workflow_trigger",
            "workflow_id": str(workflow.id),
            "instance_id": str(instance_response.id),
            "message": "Webhook received and workflow instance created",
        }

    async def _handle_step_callback(
        self,
        workflow: Any,  # Workflow type
        step_id: str,
        payload: Dict[str, Any],
        headers: Dict[str, str],
    ) -> Dict[str, Any]:
        # Verify HMAC signature if secret is configured for this step
        step_config = workflow.steps.get(step_id)
        if step_config:
            step_secret = step_config.client_metadata.get("webhook_secret")
            if step_secret:
                # Support both X-Hub-Signature-256 (GitHub/standard) and X-Webhook-Signature
                signature = headers.get("x-hub-signature-256") or headers.get(
                    "x-webhook-signature"
                )
                if not self._verify_signature(step_secret, payload, signature):
                    logger.warning(
                        f"Invalid webhook signature for step {step_id} in workflow {workflow.id}"
                    )
                    raise ValidationError(
                        message="Invalid webhook signature",
                        code="INVALID_SIGNATURE",
                    )

        # Find the waiting instance
        waiting_instance = await self.instance_service.get_waiting_for_webhook(
            workflow.id
        )

        if not waiting_instance:
            raise ValidationError(
                message="No workflow instance is waiting for a callback on this step",
                code="NO_WAITING_INSTANCE",
            )

        # Resume the instance with callback data
        resumed_instance = await self.instance_service.resume_with_webhook_callback(
            instance_id=waiting_instance.id,
            step_id=step_id,
            callback_payload=payload,
        )

        return {
            "status": "accepted",
            "webhook_type": "step_callback",
            "workflow_id": str(workflow.id),
            "instance_id": str(resumed_instance.id),
            "step_id": step_id,
            "message": "Callback received and workflow instance resumed",
        }
