# api/app/presentation/websockets/handler_instance.py

"""WebSocket handler for workflow instance events."""
import asyncio
import json
from datetime import UTC, datetime
from typing import Any, Dict, Optional, cast
from uuid import UUID

from fastapi import Depends, HTTPException, WebSocket, WebSocketDisconnect, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.services.instance_service import InstanceService
from app.config.constants import (
    WS_CLOSE_REASON_IDLE,
    WS_CLOSE_REASON_RATE_LIMIT,
)
from app.config.settings import settings
from app.domain.common.events import DomainEvent
from app.domain.instance.events import (
    InstanceCancelledEvent,
    InstanceCompletedEvent,
    InstanceCreatedEvent,
    InstanceEvent,
    InstanceFailedEvent,
    InstancePausedEvent,
    InstanceResumedEvent,
    InstanceStartedEvent,
    InstanceStatusChangedEvent,
    InstanceStepCompletedEvent,
    InstanceStepFailedEvent,
    InstanceStepStartedEvent,
)
from app.infrastructure.auth.jwt import get_current_user_ws
from app.infrastructure.auth.websocket_auth import (
    extract_subprotocol_from_websocket,
    extract_token_from_websocket,
)
from app.infrastructure.messaging.event_bus import EventBus
from app.infrastructure.messaging.pg_notify import notify_instance, notify_organization
from app.infrastructure.persistence.database import get_db_session
from app.presentation.api.dependencies import (
    CurrentUser,
    get_instance_service_for_ws,
    validate_organization_access,
)
from app.presentation.websockets.handlers import WSEventMessage, logger, router
from app.presentation.websockets.manager import manager
from app.presentation.websockets.rate_limit import (
    enforce_connection_limits,
    make_rate_limiter,
    release_connection,
)


@router.websocket("/ws/instance/{instance_id}")
async def instance_websocket_endpoint(
    websocket: WebSocket,
    instance_id: str,
    instance_service: InstanceService = Depends(get_instance_service_for_ws),
    session: AsyncSession = Depends(get_db_session),
):
    """Instance-scoped feed. Auth via Bearer.<token> in Sec-WebSocket-Protocol; ?token= deprecated."""
    user: Optional[Dict[str, Any]] = None
    user_id: Optional[UUID] = None

    # RFC 6455 requires server to select a sub-protocol on accept
    subprotocol = extract_subprotocol_from_websocket(websocket)

    client_ip = await enforce_connection_limits(websocket, manager, subprotocol)
    if client_ip is None:
        return

    token = extract_token_from_websocket(websocket)

    if token:
        user = await get_current_user_ws(token, session)
        if user:
            user_id = UUID(user["id"])

    try:
        inst_id = UUID(instance_id)
    except ValueError:
        await manager.release_ip(client_ip)
        try:
            if subprotocol:
                await websocket.accept(subprotocol=subprotocol)
            else:
                await websocket.accept()
            await websocket.close(
                code=status.WS_1003_UNSUPPORTED_DATA, reason="Invalid instance ID"
            )
        except Exception:
            pass
        return

    try:
        instance = await instance_service.get_instance(inst_id)
    except Exception:
        instance = None

    if not instance:
        await manager.release_ip(client_ip)
        try:
            if subprotocol:
                await websocket.accept(subprotocol=subprotocol)
            else:
                await websocket.accept()
            await websocket.close(
                code=status.WS_1008_POLICY_VIOLATION, reason="Instance not found"
            )
        except Exception:
            pass
        return

    if user:
        try:
            user_typed = cast(CurrentUser, user)
            await validate_organization_access(
                str(instance.organization_id), user_typed
            )
        except HTTPException:
            await manager.release_ip(client_ip)
            try:
                if subprotocol:
                    await websocket.accept(subprotocol=subprotocol)
                else:
                    await websocket.accept()
                await websocket.close(
                    code=status.WS_1008_POLICY_VIOLATION, reason="Access denied"
                )
            except Exception:
                pass
            return

    org_id = instance.organization_id

    await manager.connect(
        websocket=websocket,
        organization_id=org_id,
        instance_id=inst_id,
        user_id=user_id,
        subprotocol=subprotocol,
        ip=client_ip,
    )

    welcome_message: WSEventMessage = {
        "event_type": "connection_established",
        "timestamp": datetime.now(UTC).isoformat(),
        "data": {
            "message": "Instance WebSocket connection established",
            "instance_id": str(inst_id),
            "organization_id": str(org_id),
            "user_id": str(user_id) if user_id else None,
        },
    }
    await manager.send_personal_message(welcome_message, websocket)

    try:
        instance_data: WSEventMessage = {
            "event_type": "instance_data",
            "timestamp": datetime.now(UTC).isoformat(),
            "data": {
                "instance_id": str(instance.id),
                "workflow_id": str(instance.workflow_id),
                "status": instance.status,
                "created_at": (
                    instance.created_at.isoformat() if instance.created_at else None
                ),
                "updated_at": (
                    instance.updated_at.isoformat() if instance.updated_at else None
                ),
            },
        }
        await manager.send_personal_message(instance_data, websocket)

        rate_limiter = make_rate_limiter()

        while True:
            try:
                try:
                    data = await asyncio.wait_for(
                        websocket.receive_text(),
                        timeout=settings.WS_IDLE_TIMEOUT_SECONDS,
                    )
                except asyncio.TimeoutError:
                    await websocket.close(
                        code=status.WS_1008_POLICY_VIOLATION,
                        reason=WS_CLOSE_REASON_IDLE,
                    )
                    break

                if not rate_limiter.check():
                    await websocket.close(
                        code=status.WS_1008_POLICY_VIOLATION,
                        reason=WS_CLOSE_REASON_RATE_LIMIT,
                    )
                    break

                message = json.loads(data)

                if message.get("action") == "ping":
                    await manager.send_personal_message(
                        {
                            "event_type": "pong",
                            "timestamp": datetime.now(UTC).isoformat(),
                            "data": {},
                        },
                        websocket,
                    )
                else:
                    await manager.send_personal_message(
                        {"error": "Unknown action"}, websocket
                    )

            except json.JSONDecodeError:
                await manager.send_personal_message(
                    {"error": "Invalid JSON format"}, websocket
                )

    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        await manager.disconnect(
            websocket=websocket,
            organization_id=org_id,
            instance_id=inst_id,
            user_id=user_id,
        )
        await release_connection(websocket, manager)


async def handle_instance_events(event: DomainEvent):
    """Instance events → org and instance-scoped WebSocket broadcasts."""
    if not isinstance(event, InstanceEvent):
        logger.warning(
            f"Non-instance event received by instance handler: {event.event_type}"
        )
        return

    match event:
        case InstanceCreatedEvent():
            await notify_organization(
                event.organization_id,
                {
                    "event_type": "instance_created",
                    "timestamp": datetime.now(UTC).isoformat(),
                    "data": {
                        "instance_id": str(event.instance_id),
                        "workflow_id": str(event.workflow_id),
                        "organization_id": str(event.organization_id),
                        "status": "CREATED",
                    },
                },
            )

        case InstanceStatusChangedEvent():
            message: WSEventMessage = {
                "event_type": "instance_status_changed",
                "timestamp": datetime.now(UTC).isoformat(),
                "data": {
                    "instance_id": str(event.instance_id),
                    "workflow_id": str(event.workflow_id),
                    "organization_id": str(event.organization_id),
                    "old_status": event.old_status,
                    "new_status": event.new_status,
                },
            }
            await notify_organization(event.organization_id, message)
            await notify_instance(event.instance_id, message)

        case InstanceStepCompletedEvent():
            message: WSEventMessage = {
                "event_type": "instance_step_completed",
                "timestamp": datetime.now(UTC).isoformat(),
                "data": {
                    "instance_id": str(event.instance_id),
                    "workflow_id": str(event.workflow_id),
                    "organization_id": str(event.organization_id),
                    "step_id": event.step_id,
                    "step_name": event.step_name,
                    "step_status": "completed",
                },
            }
            await notify_organization(event.organization_id, message)
            await notify_instance(event.instance_id, message)

        case InstanceStepStartedEvent():
            message: WSEventMessage = {
                "event_type": "instance_step_started",
                "timestamp": datetime.now(UTC).isoformat(),
                "data": {
                    "instance_id": str(event.instance_id),
                    "workflow_id": str(event.workflow_id),
                    "organization_id": str(event.organization_id),
                    "step_id": event.step_id,
                    "step_name": event.step_name,
                    "step_status": "running",
                },
            }
            await notify_organization(event.organization_id, message)
            await notify_instance(event.instance_id, message)

        case InstancePausedEvent():
            message: WSEventMessage = {
                "event_type": "instance_status_changed",
                "timestamp": datetime.now(UTC).isoformat(),
                "data": {
                    "instance_id": str(event.instance_id),
                    "workflow_id": str(event.workflow_id),
                    "organization_id": str(event.organization_id),
                    "old_status": "PROCESSING",
                    "new_status": "PAUSED",
                },
            }
            await notify_organization(event.organization_id, message)
            await notify_instance(event.instance_id, message)

        case InstanceResumedEvent():
            message: WSEventMessage = {
                "event_type": "instance_status_changed",
                "timestamp": datetime.now(UTC).isoformat(),
                "data": {
                    "instance_id": str(event.instance_id),
                    "workflow_id": str(event.workflow_id),
                    "organization_id": str(event.organization_id),
                    "old_status": "PAUSED",
                    "new_status": "PROCESSING",
                },
            }
            await notify_organization(event.organization_id, message)
            await notify_instance(event.instance_id, message)

        case InstanceStartedEvent():
            message: WSEventMessage = {
                "event_type": "instance_status_changed",
                "timestamp": datetime.now(UTC).isoformat(),
                "data": {
                    "instance_id": str(event.instance_id),
                    "workflow_id": str(event.workflow_id),
                    "organization_id": str(event.organization_id),
                    "old_status": "PENDING",
                    "new_status": "PROCESSING",
                },
            }
            await notify_organization(event.organization_id, message)
            await notify_instance(event.instance_id, message)

        case InstanceCompletedEvent():
            message: WSEventMessage = {
                "event_type": "instance_status_changed",
                "timestamp": datetime.now(UTC).isoformat(),
                "data": {
                    "instance_id": str(event.instance_id),
                    "workflow_id": str(event.workflow_id),
                    "organization_id": str(event.organization_id),
                    "new_status": "COMPLETED",
                },
            }
            await notify_organization(event.organization_id, message)
            await notify_instance(event.instance_id, message)

        case InstanceFailedEvent():
            message: WSEventMessage = {
                "event_type": "instance_status_changed",
                "timestamp": datetime.now(UTC).isoformat(),
                "data": {
                    "instance_id": str(event.instance_id),
                    "workflow_id": str(event.workflow_id),
                    "organization_id": str(event.organization_id),
                    "new_status": "FAILED",
                    "error": event.error_message,
                },
            }
            await notify_organization(event.organization_id, message)
            await notify_instance(event.instance_id, message)

        case InstanceCancelledEvent():
            message: WSEventMessage = {
                "event_type": "instance_status_changed",
                "timestamp": datetime.now(UTC).isoformat(),
                "data": {
                    "instance_id": str(event.instance_id),
                    "workflow_id": str(event.workflow_id),
                    "organization_id": str(event.organization_id),
                    "new_status": "CANCELLED",
                },
            }
            await notify_organization(event.organization_id, message)
            await notify_instance(event.instance_id, message)

        case InstanceStepFailedEvent():
            message: WSEventMessage = {
                "event_type": "instance_step_failed",
                "timestamp": datetime.now(UTC).isoformat(),
                "data": {
                    "instance_id": str(event.instance_id),
                    "workflow_id": str(event.workflow_id),
                    "organization_id": str(event.organization_id),
                    "step_id": event.step_id,
                    "step_name": event.step_name,
                    "step_status": "failed",
                    "error": event.error_message,
                },
            }
            await notify_organization(event.organization_id, message)
            await notify_instance(event.instance_id, message)

        case _:
            pass


def register_instance_event_handlers(event_bus: EventBus) -> None:
    """Register instance-related event handlers."""
    from typing import Awaitable, Callable

    instance_handler: Callable[[DomainEvent], Awaitable[None]] = (
        lambda event: handle_instance_events(event)
    )
    event_bus.subscribe("instance.created", instance_handler)
    event_bus.subscribe("instance.started", instance_handler)
    event_bus.subscribe("instance.status_changed", instance_handler)
    event_bus.subscribe("instance.step_started", instance_handler)
    event_bus.subscribe("instance.step_completed", instance_handler)
    event_bus.subscribe("instance.step_failed", instance_handler)
    event_bus.subscribe("instance.completed", instance_handler)
    event_bus.subscribe("instance.failed", instance_handler)
    event_bus.subscribe("instance.cancelled", instance_handler)
    event_bus.subscribe("instance.paused", instance_handler)
    event_bus.subscribe("instance.resumed", instance_handler)
