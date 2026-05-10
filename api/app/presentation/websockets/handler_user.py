# api/app/presentation/websockets/handler_user.py

"""WebSocket handlers for user-specific real-time updates."""

import asyncio
import json
from datetime import UTC, datetime
from uuid import UUID

from fastapi import Depends, WebSocket, WebSocketDisconnect, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.constants import (
    WS_CLOSE_REASON_AUTH_REQUIRED,
    WS_CLOSE_REASON_IDLE,
    WS_CLOSE_REASON_RATE_LIMIT,
)
from app.config.settings import settings
from app.domain.common.events import (
    DomainEvent,
    NotificationCreatedEvent,
    NotificationDeletedEvent,
    NotificationReadEvent,
)
from app.domain.notification.models import (
    NotificationCreated,
    NotificationSent,
)
from app.infrastructure.auth.jwt import get_current_user_ws
from app.infrastructure.auth.websocket_auth import (
    extract_subprotocol_from_websocket,
    extract_token_from_websocket,
)
from app.infrastructure.messaging.event_bus import EventBus
from app.infrastructure.messaging.pg_notify import notify_user
from app.infrastructure.persistence.database import get_db_session
from app.presentation.websockets.handlers import WSEventMessage, router
from app.presentation.websockets.manager import manager
from app.presentation.websockets.rate_limit import (
    enforce_connection_limits,
    make_rate_limiter,
    release_connection,
)


@router.websocket("/ws/user/{user_id}")
async def user_websocket_endpoint(
    websocket: WebSocket,
    user_id: str,
    session: AsyncSession = Depends(get_db_session),
):
    """User-scoped feed. Auth REQUIRED via Bearer.<token> in Sec-WebSocket-Protocol; ?token= deprecated."""
    # RFC 6455 requires server to select a sub-protocol on accept
    subprotocol = extract_subprotocol_from_websocket(websocket)

    client_ip = await enforce_connection_limits(websocket, manager, subprotocol)
    if client_ip is None:
        return

    token = extract_token_from_websocket(websocket)

    if not token:
        await manager.release_ip(client_ip)
        try:
            if subprotocol:
                await websocket.accept(subprotocol=subprotocol)
            else:
                await websocket.accept()
            await websocket.close(
                code=status.WS_1008_POLICY_VIOLATION,
                reason=WS_CLOSE_REASON_AUTH_REQUIRED,
            )
        except Exception:
            pass
        return

    user = await get_current_user_ws(token, session)
    if not user:
        await manager.release_ip(client_ip)
        try:
            if subprotocol:
                await websocket.accept(subprotocol=subprotocol)
            else:
                await websocket.accept()
            await websocket.close(
                code=status.WS_1008_POLICY_VIOLATION, reason="Invalid token"
            )
        except Exception:
            pass
        return

    try:
        user_uuid = UUID(user_id)
    except ValueError:
        await manager.release_ip(client_ip)
        try:
            if subprotocol:
                await websocket.accept(subprotocol=subprotocol)
            else:
                await websocket.accept()
            await websocket.close(
                code=status.WS_1003_UNSUPPORTED_DATA, reason="Invalid user ID"
            )
        except Exception:
            pass
        return

    authenticated_user_id = UUID(user["id"])
    is_admin = user.get("is_admin", False)

    if not is_admin and authenticated_user_id != user_uuid:
        await manager.release_ip(client_ip)
        try:
            if subprotocol:
                await websocket.accept(subprotocol=subprotocol)
            else:
                await websocket.accept()
            await websocket.close(
                code=status.WS_1008_POLICY_VIOLATION,
                reason="Not authorized to access this user's feed",
            )
        except Exception:
            pass
        return

    await manager.connect(
        websocket=websocket,
        user_id=user_uuid,
        subprotocol=subprotocol,
        ip=client_ip,
    )

    welcome_message: WSEventMessage = {
        "event_type": "connection_established",
        "timestamp": datetime.now(UTC).isoformat(),
        "data": {
            "message": "User WebSocket connection established",
            "user_id": str(user_uuid),
        },
    }
    await manager.send_personal_message(welcome_message, websocket)

    rate_limiter = make_rate_limiter()

    try:
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
        await manager.disconnect(websocket=websocket, user_id=user_uuid)
        await release_connection(websocket, manager)


async def handle_user_events(event: DomainEvent):
    """Notification events → user-scoped WebSocket broadcasts."""
    match event:
        case NotificationCreatedEvent(user_id=uid) if uid:
            await notify_user(
                uid,
                {
                    "event_type": "notification_created",
                    "timestamp": datetime.now(UTC).isoformat(),
                    "data": {
                        "notification_id": str(event.notification_id),
                        "organization_id": str(event.organization_id),
                    },
                },
            )

        case NotificationReadEvent(user_id=uid) if uid:
            await notify_user(
                uid,
                {
                    "event_type": "notification_read",
                    "timestamp": datetime.now(UTC).isoformat(),
                    "data": {
                        "notification_id": str(event.notification_id),
                    },
                },
            )

        case NotificationDeletedEvent(user_id=uid) if uid:
            await notify_user(
                uid,
                {
                    "event_type": "notification_deleted",
                    "timestamp": datetime.now(UTC).isoformat(),
                    "data": {
                        "notification_id": str(event.notification_id),
                    },
                },
            )

        case NotificationCreated():
            await notify_user(
                event.recipient_id,
                {
                    "event_type": "notification_created",
                    "timestamp": datetime.now(UTC).isoformat(),
                    "data": {
                        "notification_id": str(event.aggregate_id),
                        "channel_type": event.channel_type.value,
                        "recipient_id": str(event.recipient_id),
                    },
                },
            )

        case NotificationSent():
            await notify_user(
                event.aggregate_id,
                {
                    "event_type": "notification_sent",
                    "timestamp": datetime.now(UTC).isoformat(),
                    "data": {
                        "notification_id": str(event.aggregate_id),
                    },
                },
            )

        case _:
            pass


def register_user_event_handlers(event_bus: EventBus):
    """Register user notification-related event handlers."""
    from typing import Awaitable, Callable

    notification_handler: Callable[[DomainEvent], Awaitable[None]] = (
        lambda event: handle_user_events(event)
    )
    event_bus.subscribe("notification.created", notification_handler)
    event_bus.subscribe("notification.read", notification_handler)
    event_bus.subscribe("notification.deleted", notification_handler)
    event_bus.subscribe("notification.sent", notification_handler)
    event_bus.subscribe("notification.failed", notification_handler)
