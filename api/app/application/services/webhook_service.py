# api/app/application/services/webhook_service.py

import hashlib
import hmac
import json
import logging
from typing import Any, Dict, Optional, TYPE_CHECKING

import jwt
from jwt.exceptions import ExpiredSignatureError, PyJWTError as JWTError

from app.application.dtos.instance_dto import InstanceCreate
from app.application.interfaces import EventBus
from app.domain.common.exceptions import (
    EntityNotFoundError,
    ValidationError,
)
from app.domain.workflow.models import WorkflowStatus
from app.domain.workflow.repository import WorkflowRepository

if TYPE_CHECKING:
    from app.application.services.instance_service import InstanceService

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
    ):
        self.workflow_repository = workflow_repository
        self.instance_service = instance_service
        self.event_bus = event_bus

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

        # Token not found anywhere
        raise EntityNotFoundError(
            "Webhook",
            token,
            "No workflow or step found with this webhook token",
        )

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
