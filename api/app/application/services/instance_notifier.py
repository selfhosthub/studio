# api/app/application/services/instance_notifier.py

"""WebSocket publishing and bell notifications for instance lifecycle changes."""

import logging
from datetime import datetime, UTC
from typing import Any, Awaitable, Callable, Dict, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import settings

from app.domain.common.value_objects import Role
from app.domain.instance.models import Instance, InstanceStatus
from app.domain.notification.models import (
    ChannelType,
    Notification,
    NotificationPriority,
)
from app.domain.notification.repository import NotificationRepository
from app.domain.organization.repository import UserRepository

logger = logging.getLogger(__name__)


class InstanceNotifier:
    """WS + bell notifications for instance lifecycle changes.

    All callers must use the single announce_state_change entry point to
    satisfy the pairing contract enforced by the contract test.
    """

    # WS publish + bell.
    TERMINAL_ACTIONS = frozenset({"completed", "failed", "cancelled"})
    WAITING_ACTIONS = frozenset({"waiting_approval", "waiting_manual_trigger"})
    LIFECYCLE_ACTIONS = frozenset({"processing_started"})

    # WS publish only - no bell.
    PUBLISH_ONLY_ACTIONS = frozenset({"progress", "rolled_back", "debug_paused", "step_started", "step_skipped", "step_blocked", "step_completed"})

    _ACTION_TO_STATUS = {
        "completed": InstanceStatus.COMPLETED,
        "failed": InstanceStatus.FAILED,
        "cancelled": InstanceStatus.CANCELLED,
        "waiting_approval": InstanceStatus.WAITING_FOR_APPROVAL,
        "waiting_manual_trigger": InstanceStatus.WAITING_FOR_MANUAL_TRIGGER,
        "processing_started": InstanceStatus.PROCESSING,
        "debug_paused": InstanceStatus.DEBUG_PAUSED,
    }

    def __init__(
        self,
        broadcast_instance_update_fn: Callable[..., Awaitable[None]],
        notification_repo_factory: Callable[[AsyncSession], NotificationRepository],
        user_repo_factory: Callable[[AsyncSession], UserRepository],
        broadcast_notification_fn: Optional[Any] = None,
    ):
        # Repos are created via factories because each call needs a per-request
        # session, but this service is a long-lived singleton.
        self._broadcast_instance_update = broadcast_instance_update_fn
        self._notification_repo_factory = notification_repo_factory
        self._user_repo_factory = user_repo_factory
        self._broadcast_notification = broadcast_notification_fn

    async def publish_instance_update(
        self,
        instance_id: str,
        organization_id: str,
        workflow_id: str,
        status: str,
        result_data: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> None:
        safe_result: Dict[str, Any] = {}
        if result_data:
            for k, v in result_data.items():
                if k == "downloaded_files":
                    continue
                if k == "step_result" and isinstance(v, dict):
                    safe_result[k] = {fk: fv for fk, fv in v.items() if fk != "downloaded_files"}
                else:
                    safe_result[k] = v
        ws_message = {
            "event_type": "instance_status_changed",
            "timestamp": datetime.now(UTC).isoformat(),
            "data": {
                "instance_id": instance_id,
                "organization_id": organization_id,
                "workflow_id": workflow_id,
                "new_status": status,
                "result": safe_result,
                "error": error,
            },
        }

        try:
            await self._broadcast_instance_update(
                organization_id, instance_id, ws_message
            )
            logger.debug(f"Broadcast instance update: {instance_id} -> {status}")
        except Exception as e:
            logger.warning(f"Failed to broadcast instance update: {e}")

    async def create_notification(
        self,
        session: AsyncSession,
        organization_id: UUID,
        instance_id: UUID,
        workflow_id: UUID,
        workflow_name: Optional[str],
        status: InstanceStatus,
        error: Optional[str] = None,
    ) -> None:
        """IN_APP bell notification fan-out to all admin/super_admin users in the org."""
        try:
            notification_repo = self._notification_repo_factory(session)
            user_repo = self._user_repo_factory(session)

            all_users = await user_repo.find_active_users_in_organization(
                organization_id=organization_id,
                skip=0,
                limit=settings.DEFAULT_FETCH_LIMIT,
            )

            recipients = [
                u for u in all_users if u.role in (Role.ADMIN, Role.SUPER_ADMIN)
            ]

            if not recipients:
                logger.debug(f"No admin users to notify for org {organization_id}")
                return

            display_name = workflow_name or "Workflow"
            if status == InstanceStatus.COMPLETED:
                title = "Instance Completed"
                message = f"{display_name} completed successfully."
                priority = NotificationPriority.MEDIUM
                tags = ["workflow", "success"]
            elif status == InstanceStatus.FAILED:
                title = "Instance Failed"
                message = error or f"{display_name} failed."
                priority = NotificationPriority.HIGH
                tags = ["workflow", "error"]
            elif status == InstanceStatus.PROCESSING:
                title = "Instance Started"
                message = f"{display_name} started running."
                priority = NotificationPriority.LOW
                tags = ["workflow", "started"]
            elif status == InstanceStatus.WAITING_FOR_APPROVAL:
                title = "Approval Required"
                message = f"{display_name} is waiting for approval."
                priority = NotificationPriority.HIGH
                tags = ["workflow", "approval"]
            elif status == InstanceStatus.WAITING_FOR_MANUAL_TRIGGER:
                title = "Manual Trigger Required"
                message = f"{display_name} is waiting for a manual trigger."
                priority = NotificationPriority.MEDIUM
                tags = ["workflow", "manual_trigger"]
            elif status == InstanceStatus.CANCELLED:
                title = "Instance Cancelled"
                message = f"{display_name} was cancelled."
                priority = NotificationPriority.LOW
                tags = ["workflow", "cancelled"]
            else:
                return

            for recipient in recipients:
                notification = Notification.create(
                    recipient_id=recipient.id,
                    organization_id=organization_id,
                    # System-generated; recipient stands in as creator.
                    created_by=recipient.id,
                    channel_type=ChannelType.IN_APP,
                    message=message,
                    title=title,
                    priority=priority,
                    tags=tags,
                    client_metadata={
                        "workflow_id": str(workflow_id),
                        "workflow_name": workflow_name,
                        "instance_id": str(instance_id),
                        "resource_type": "instance",
                        "resource_id": str(instance_id),
                        "error": error,
                    },
                )

                await notification_repo.create(notification)
                logger.debug(f"Created notification for user {recipient.id}")

                if self._broadcast_notification:
                    ws_message = {
                        "event_type": "notification_created",
                        "timestamp": datetime.now(UTC).isoformat(),
                        "data": {
                            "notification_id": str(notification.id),
                            "organization_id": str(organization_id),
                            "title": notification.title,
                            "message": notification.message,
                            "priority": notification.priority.value,
                            "tags": notification.tags,
                            "client_metadata": notification.client_metadata,
                        },
                    }
                    try:
                        await self._broadcast_notification(recipient.id, ws_message)
                    except Exception as e:
                        logger.warning(
                            f"Failed to broadcast notification to user {recipient.id}: {e}"
                        )

            logger.info(
                f"Created {status.value} notifications for {len(recipients)} users in org {organization_id}"
            )

        except Exception as e:
            # Notification failures must not fail result processing.
            logger.warning(f"Failed to create notification: {e}")

    def _status_for_action(self, action_type: str) -> Optional[InstanceStatus]:
        """Map lifecycle action type to canonical status, or None to use instance.status."""
        return self._ACTION_TO_STATUS.get(action_type)

    async def announce_state_change(
        self,
        instance: Instance,
        action_type: str,
        step_id: Optional[str] = None,
        error: Optional[str] = None,
        result_data: Optional[Dict[str, Any]] = None,
        session: Optional[AsyncSession] = None,
    ) -> None:
        """Announce a lifecycle state change: commit bell notification then publish WS.

        WS publish follows commit so UI refetches see committed state.
        """
        bell_fires = action_type in (
            self.TERMINAL_ACTIONS | self.WAITING_ACTIONS | self.LIFECYCLE_ACTIONS
        )
        derived_status = self._status_for_action(action_type)

        if bell_fires:
            if session is None:
                logger.warning(
                    f"announce_state_change({action_type}): no session provided, "
                    "skipping bell notification"
                )
            else:
                status_for_bell = derived_status or instance.status
                await self.create_notification(
                    session=session,
                    organization_id=instance.organization_id,
                    instance_id=instance.id,
                    workflow_id=instance.workflow_id,
                    workflow_name=instance.workflow_name,
                    status=status_for_bell,
                    error=error,
                )
                await session.commit()

        status_for_ws = (
            derived_status if derived_status is not None else instance.status
        )
        status_str = (
            status_for_ws.value.upper()
            if hasattr(status_for_ws, "value")
            else str(status_for_ws).upper()
        )
        payload: Dict[str, Any] = {}
        if step_id is not None:
            payload["step_id"] = step_id
        if result_data:
            payload.update(result_data)
        await self.publish_instance_update(
            instance_id=str(instance.id),
            organization_id=str(instance.organization_id),
            workflow_id=str(instance.workflow_id),
            status=status_str,
            result_data=payload if payload else None,
            error=error,
        )
