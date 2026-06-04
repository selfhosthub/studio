# api/app/application/services/webhook_service.py

import hashlib
import hmac
import json
import logging
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

from app.application.dtos.instance_dto import InstanceCreate
from app.application.interfaces import EventBus
from app.domain.common.exceptions import (
    EntityNotFoundError,
    ValidationError,
)
from app.domain.instance.iteration_execution import IterationExecutionStatus
from app.domain.workflow.models import WorkflowStatus
from app.domain.workflow.repository import WorkflowRepository

if TYPE_CHECKING:
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

# Services that block concurrent workflow instances because they share
# resources across instances (e.g., callback URLs). Add new services here
# rather than hardcoding service_id checks throughout the codebase.
SERVICES_BLOCKING_CONCURRENT_INSTANCES = frozenset(
    {
        "core.webhook_wait",
    }
)


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
    ):
        self.workflow_repository = workflow_repository
        self.instance_service = instance_service
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

    def _verify_webhook_auth(
        self,
        workflow: Any,
        headers: Dict[str, str],
    ) -> None:
        auth_type = getattr(workflow, "webhook_auth_type", "none")

        if auth_type == "none":
            return  # No auth required

        if auth_type == "header":
            header_name = workflow.webhook_auth_header_name
            header_value = workflow.webhook_auth_header_value
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
            jwt_secret = workflow.webhook_jwt_secret
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

    async def handle_incoming_webhook_by_token(
        self,
        token: str,
        payload: Dict[str, Any],
        headers: Dict[str, str],
    ) -> Dict[str, Any]:
        # Try workflow token first (trigger), then step token (callback)
        workflow = await self.workflow_repository.get_by_webhook_token(token)

        if workflow:
            # This is a workflow trigger - create new instance
            return await self._handle_workflow_trigger(workflow, payload, headers)

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

        # Token not found anywhere
        raise EntityNotFoundError(
            "Webhook",
            token,
            "No workflow or step found with this webhook token",
        )

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
        svc_repo = cast("ProviderServiceRepository", self.provider_service_repository)
        provider_repo = cast("ProviderRepository", self.provider_repository)
        instance_repo = cast("InstanceRepository", self.instance_repository)
        step_repo = cast("StepExecutionRepository", self.step_execution_repository)
        enqueue = cast("JobEnqueueService", self.job_enqueue_service)
        process_result = cast(ProcessResultFn, self.process_result_fn)

        # Provider-level envelope: the inbound callback shape + auth, one per
        # provider, resolvable from the credential alone (pre-demux).
        provider = await provider_repo.get_by_id(credential.provider_id)
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
            raise EntityNotFoundError(
                "WebhookGeneration", str(raw_id), "Unknown generation id"
            )

        # Resolve the parked step from the matched row (no assignment): the
        # StepExecution carries the workflow step_key; the instance carries org
        # + workflow, and the workflow step's job carries service/provider ids.
        step_execution = await step_repo.get_by_id(row.step_id)
        instance = await instance_repo.get_by_id(row.instance_id)
        if step_execution is None or instance is None:
            raise EntityNotFoundError(
                "WebhookStep",
                str(row.step_id),
                "Parked workflow step no longer exists",
            )
        step_key = step_execution.step_key
        organization_id = instance.organization_id
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
        provider_id = str(job.provider_id) if job.provider_id else None

        # Service-level block: the asset shape inside the envelope, tied to this
        # endpoint (image vs. video vs. audio result_callback_path).
        service = await svc_repo.get_by_service_id(service_id, 0, 1)
        service_completion = (getattr(service, "client_metadata", None) or {}).get(
            "webhook_completion"
        )
        if not service_completion:
            raise ValidationError(
                message="Service is not configured for webhook completion",
                code="WEBHOOK_COMPLETION_NOT_CONFIGURED",
            )

        # Idempotency: a row past PENDING was already handled (dup callback). A
        # sibling already in a failed/cancelled terminal means the step is
        # finishing or gone - drop late callbacks (I-5).
        if row.status != IterationExecutionStatus.PENDING:
            return self._callback_noop("duplicate", str(raw_id))
        siblings = await iter_repo.list_by_step_id(row.step_id)
        group_siblings = [
            s for s in siblings if s.iteration_group_id == row.iteration_group_id
        ]
        if any(
            s.status
            in (IterationExecutionStatus.FAILED, IterationExecutionStatus.CANCELLED)
            for s in group_siblings
        ):
            return self._callback_noop("step_terminal", str(raw_id))

        # Status gate. Absent failure_values => any non-success terminal fails.
        # Status + success/failure values are envelope (provider-level); the
        # asset shape (result_callback_path) is the service block.
        status_value = self._extract_jsonpath(
            payload, envelope["status_callback_path"]
        )
        success_values = envelope.get("success_values") or []
        failure_values = envelope.get("failure_values")
        iteration_count = len(group_siblings)
        group_id = (
            str(row.iteration_group_id) if row.iteration_group_id else None
        )

        if status_value in success_values:
            asset_urls = self._extract_jsonpath_all(
                payload, service_completion["result_callback_path"]
            )
            # Mark the row in-flight so a duplicate callback is a no-op, then
            # enqueue the seeded download whose result completes the iteration.
            row.queue()
            await iter_repo.update(row)
            await enqueue.enqueue_webhook_retrieve_job(
                instance_id=row.instance_id,
                organization_id=organization_id,
                step_id=step_key,
                service_id=service_id,
                provider_id=provider_id,
                credential_id=str(credential.id),
                asset_urls=asset_urls,
                iteration_index=row.iteration_index,
                iteration_count=iteration_count,
                iteration_group_id=group_id,
            )
            return self._callback_accepted("retrieving", str(raw_id))

        is_failure = failure_values is None or status_value in failure_values
        if is_failure:
            # Route a failed iteration through the same processor a worker
            # result uses; the shared finalizer fails the step once the
            # aggregate is terminal and cancels siblings.
            await process_result(
                {
                    "instance_id": str(row.instance_id),
                    "step_id": step_key,
                    "status": "FAILED",
                    "result": {},
                    "error": f"Provider reported callback status '{status_value}'",
                    "iteration_index": row.iteration_index,
                    "iteration_count": iteration_count,
                    "iteration_group_id": group_id,
                }
            )
            return self._callback_accepted("failed", str(raw_id))

        # Non-terminal status (provider still working): nothing to do yet.
        return self._callback_noop("pending", str(raw_id))

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
    ) -> Dict[str, Any]:
        # Verify webhook authentication based on auth type
        auth_type = getattr(workflow, "webhook_auth_type", "none")

        if auth_type == "hmac":
            # HMAC authentication: verify signature
            if workflow.webhook_secret:
                # Support both X-Hub-Signature-256 (GitHub/standard) and X-Webhook-Signature
                signature = headers.get("x-hub-signature-256") or headers.get(
                    "x-webhook-signature"
                )
                if not self._verify_signature(
                    workflow.webhook_secret, payload, signature
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
        else:
            # Header Auth or JWT Auth
            self._verify_webhook_auth(workflow, headers)

        # Check if workflow is active
        if workflow.status != WorkflowStatus.ACTIVE:
            raise ValidationError(
                message=f"Workflow is not active (status: {workflow.status.value})",
                code="WORKFLOW_INACTIVE",
            )

        # Check if workflow contains a step that blocks concurrent instances
        # (e.g., webhook_wait shares callback URLs across instances)
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
                    message="This workflow contains a step that blocks concurrent instances. "
                    "Only one instance can run at a time because resources are shared.",
                    code="BLOCKING_STEP_INSTANCE_RUNNING",
                )

        # Create workflow instance
        instance_create = InstanceCreate(
            workflow_id=workflow.id,
            user_id=workflow.created_by,
            created_by=workflow.created_by,
            input_data=payload,
            client_metadata={
                "source": "webhook",
                "webhook_type": "workflow_trigger",
                "headers": {
                    k: v
                    for k, v in headers.items()
                    if k.lower() not in ("authorization", "x-webhook-signature")
                },
            },
        )

        instance_response = await self.instance_service.create_instance(instance_create)

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
