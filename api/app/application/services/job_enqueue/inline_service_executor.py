# api/app/application/services/job_enqueue/inline_service_executor.py

"""
Inline execution of services that don't require a worker queue.

Services opt in via orchestrator_hints.inline: true in their adapter-config.
These are simple data transforms and utilities that execute in the API process.

Any service from any provider can be inline - the decision is driven by
service metadata, not provider identity.
"""

import inspect
import json
import logging
import uuid
from datetime import datetime, UTC
from typing import Any, Dict, List, Optional

from app.config.settings import settings
from app.domain.notification.models import (
    ChannelType,
    Notification,
    NotificationPriority,
)
from app.domain.notification.repository import NotificationRepository
from app.domain.organization.repository import UserRepository
from app.domain.provider.repository import ProviderCredentialRepository
from app.domain.workflow.repository import WorkflowRepository
from app.domain.common.interfaces import JobStatusPublisher
from app.domain.common.exceptions import BusinessRuleViolation
from app.infrastructure.errors import safe_error_message
from app.infrastructure.security.step_secrets import (
    step_secret_paths,
    without_secret_values,
)

logger = logging.getLogger(__name__)

_NOTIFY_PRIORITY = {
    "error": NotificationPriority.HIGH,
    "warning": NotificationPriority.MEDIUM,
}


class InlineServiceExecutor:
    """Executes services inline without going through a worker queue.

    Services declare themselves as inline via orchestrator_hints.inline: true
    in their adapter-config. The handler registry maps service names to
    execution functions.
    """

    def __init__(
        self,
        credential_repository: ProviderCredentialRepository,
        status_publisher: JobStatusPublisher,
        notification_repository: Optional[NotificationRepository] = None,
        user_repository: Optional[UserRepository] = None,
        workflow_repository: Optional[WorkflowRepository] = None,
    ):
        self.credential_repository = credential_repository
        self.status_publisher = status_publisher
        self.notification_repository = notification_repository
        self.user_repository = user_repository
        self.workflow_repository = workflow_repository

    def can_handle(self, service_id: str) -> bool:
        """Check if this executor has an inline handler for the given service."""
        service_name = service_id.split(".")[-1] if "." in service_id else service_id
        return service_name in self._handlers

    async def execute(
        self,
        instance_id: uuid.UUID,
        step_id: str,
        organization_id: uuid.UUID,
        service_id: str,
        resolved_step_config: Dict[str, Any],
        park_for_webhook: bool = False,
        workflow_id: Optional[uuid.UUID] = None,
        workflow_name: Optional[str] = None,
    ) -> str:
        """Execute a service inline and return the generated job ID; park_for_webhook completes it as a parked step."""
        job_id = str(uuid.uuid4())
        logger.info(f"Executing service inline: {service_id} (step={step_id})")

        # Get parameters from step config
        job_config = resolved_step_config.get("job") or {}
        parameters = job_config.get("parameters") or {}
        shown = without_secret_values(parameters, step_secret_paths(resolved_step_config))

        # Publish PROCESSING status first (same as worker would)
        processing_result = {
            "instance_id": str(instance_id),
            "step_id": step_id,
            "status": "PROCESSING",
            "result": {"message": f"Executing {service_id} inline"},
            "error": None,
            "input_data": shown,
            "published_at": datetime.now(UTC).isoformat(),
        }
        await self.status_publisher.publish_status(processing_result)

        try:
            # Extract service name from service_id (e.g., "core.set_fields" -> "set_fields")
            service_name = (
                service_id.split(".")[-1] if "." in service_id else service_id
            )

            # Dispatch to handler
            handler = self._handlers.get(service_name)
            if not handler:
                # BusinessRuleViolation is allowlisted by safe_error_message,
                # so the user-facing service_id is preserved in the published
                # FAILED status. ValueError would be masked to type-name-only.
                raise BusinessRuleViolation(
                    f"No inline handler for service: {service_id}"
                )

            if inspect.iscoroutinefunction(handler):
                result_data = await handler(
                    parameters,
                    {
                        "instance_id": instance_id,
                        "organization_id": organization_id,
                        "workflow_id": workflow_id,
                        "workflow_name": workflow_name,
                    },
                )
            else:
                result_data = handler(parameters)

            # Publish COMPLETED status with result
            completed_result = {
                "instance_id": str(instance_id),
                "step_id": step_id,
                "status": "COMPLETED",
                "result": result_data,
                "error": None,
                "input_data": shown,
                "published_at": datetime.now(UTC).isoformat(),
                "webhook_pending": park_for_webhook,
            }
            await self.status_publisher.publish_status(completed_result)
            logger.info(f"Inline service {service_id} completed: {result_data}")

        except Exception as e:
            # Publish FAILED status on exception
            failed_result = {
                "instance_id": str(instance_id),
                "step_id": step_id,
                "status": "FAILED",
                "result": {},
                "error": safe_error_message(e),
                "input_data": shown,
                "published_at": datetime.now(UTC).isoformat(),
            }
            await self.status_publisher.publish_status(failed_result)
            logger.exception(f"Inline service {service_id} exception")

        return job_id

    @property
    def _handlers(self) -> Dict[str, Any]:
        """Handler registry mapping service names to execution functions."""
        return {
            "set_fields": self._execute_set_fields,
            "log": self._execute_log,
            "notify": self._execute_notify,
            "webhook_trigger": self._execute_webhook_trigger,
            "webhook_response": self._execute_webhook_response,
            "webhook_wait": self._execute_webhook_wait,
        }

    def _execute_webhook_wait(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Record what the parked step waits for; its callback supplies the result."""
        return {
            "wait_for": "webhook_callback",
            "expected_fields": parameters.get("expected_fields", []),
        }

    def _execute_set_fields(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Set/transform workflow data fields."""
        fields = parameters.get("fields", [])
        include_input = parameters.get("include_input_fields", False)

        result: Dict[str, Any] = {}

        if include_input:
            input_data = parameters.get("_input", {})
            if isinstance(input_data, dict):
                result.update(input_data)

        for field in fields:
            name = field.get("name")
            value = field.get("value")
            field_type = field.get("type", "string")

            if name:
                if field_type in ("array", "object") and isinstance(value, str):
                    try:
                        value = json.loads(value)
                    except json.JSONDecodeError:
                        pass
                result[name] = value

        return result

    def _execute_log(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Log a message to workflow execution history."""
        message = parameters.get("message", "")
        level = parameters.get("level", "info")

        log_level: int = (
            logging.getLevelName(level.upper())  # type: ignore[assignment]
            if level.upper() in ("DEBUG", "INFO", "WARNING", "ERROR")
            else logging.INFO
        )
        logger.log(log_level, f"[core.log] {message}")

        now = datetime.now(UTC).isoformat()
        return {
            "logged_at": now,
            "log_id": f"log-{now}",
            "message": message,
            "level": level,
        }

    async def _execute_notify(
        self, parameters: Dict[str, Any], context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Send an in-app notification to the listed org members, or the workflow owner."""
        title = parameters.get("title", "Notification")
        message = parameters.get("message", "")
        level = parameters.get("level", "info")

        logger.info(f"[core.notify] {title}: {message} (level={level})")

        now = datetime.now(UTC).isoformat()
        notification_repository = self.notification_repository
        user_repository = self.user_repository
        workflow_repository = self.workflow_repository
        if (
            notification_repository is None
            or user_repository is None
            or workflow_repository is None
        ):
            return {
                "notification_id": f"notif-{now}",
                "sent_at": now,
                "acknowledged": False,
            }

        organization_id: uuid.UUID = context["organization_id"]
        instance_id = str(context["instance_id"])
        workflow_id = context["workflow_id"]
        members = await user_repository.find_active_users_in_organization(
            organization_id=organization_id,
            skip=0,
            limit=settings.DEFAULT_FETCH_LIMIT,
        )
        notify_users = {str(u) for u in parameters.get("notify_users") or []}
        if notify_users:
            recipients = [u.id for u in members if str(u.id) in notify_users]
        else:
            workflow = (
                await workflow_repository.get_by_id(workflow_id)
                if workflow_id
                else None
            )
            owner = workflow.created_by if workflow else None
            recipients = [u.id for u in members if u.id == owner]
        notification_ids: List[str] = []
        for recipient_id in recipients:
            notification = Notification.create(
                recipient_id=recipient_id,
                organization_id=organization_id,
                created_by=recipient_id,
                channel_type=ChannelType.IN_APP,
                message=message,
                title=title,
                priority=_NOTIFY_PRIORITY.get(level, NotificationPriority.LOW),
                client_metadata={
                    "workflow_id": str(workflow_id) if workflow_id else None,
                    "workflow_name": context["workflow_name"],
                    "instance_id": instance_id,
                    "resource_type": "instance",
                    "resource_id": instance_id,
                    "source": "core.notify",
                },
            )
            await notification_repository.create(notification)
            notification_ids.append(str(notification.id))

        return {
            "notification_id": notification_ids[0] if notification_ids else None,
            "sent_at": now,
            "acknowledged": False,
        }

    def _execute_webhook_trigger(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Return webhook trigger configuration (actual handling by webhook system)."""
        return {
            "message": "Webhook trigger configured",
            "config": parameters,
        }

    def _execute_webhook_response(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Configure the response to send back to webhook caller."""
        return {
            "status_code": parameters.get("status_code", 200),
            "body": parameters.get("body", {}),
            "headers": parameters.get("headers", {}),
            "content_type": parameters.get("content_type", "application/json"),
        }
