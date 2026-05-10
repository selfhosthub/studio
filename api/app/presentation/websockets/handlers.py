# api/app/presentation/websockets/handlers.py

import asyncio
import json
import logging
from datetime import UTC, datetime
from typing import Any, Dict, Optional, TypedDict, Union
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.constants import (
    WS_CLOSE_REASON_AUTH_REQUIRED,
    WS_CLOSE_REASON_IDLE,
    WS_CLOSE_REASON_RATE_LIMIT,
)
from app.config.settings import settings
from app.infrastructure.auth.jwt import get_current_user_ws
from app.infrastructure.auth.websocket_auth import (
    extract_subprotocol_from_websocket,
    extract_token_from_websocket,
)
from app.infrastructure.messaging.event_bus import EventBus
from app.infrastructure.persistence.database import get_db_session
from app.presentation.websockets.manager import manager
from app.presentation.websockets.rate_limit import (
    enforce_connection_limits,
    make_rate_limiter,
    release_connection,
)

logger = logging.getLogger(__name__)

router = APIRouter()


class SubscriptionRequest(BaseModel):
    subscription_type: str = Field(
        ..., description="Type of subscription: 'organization', 'instance', or 'all'"
    )
    entity_id: Optional[UUID] = Field(
        None, description="ID of the entity to subscribe to (organization or instance)"
    )


class SubscriptionInfo(TypedDict):
    organization: Optional[str]
    instance: Optional[str]
    user: Optional[str]


class ConnectionData(TypedDict):
    message: str
    subscriptions: SubscriptionInfo


class SubscriptionUpdatedData(TypedDict):
    subscription_type: str
    entity_id: str


class UnsubscriptionData(TypedDict):
    message: str
    subscriptions: SubscriptionInfo


class WSEventMessage(TypedDict):
    event_type: str
    timestamp: str
    data: Union[
        ConnectionData, SubscriptionUpdatedData, UnsubscriptionData, Dict[str, Any]
    ]


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    instance_id: Optional[str] = None,
    organization_id: Optional[str] = None,
    session: AsyncSession = Depends(get_db_session),
):
    """
    WebSocket endpoint for real-time updates.

    Clients can connect to receive updates about workflow instances, jobs,
    and other system events.

    Authentication:
        **Required.** Pass JWT token via Sec-WebSocket-Protocol header:
        ```javascript
        // nosemgrep: detect-insecure-websocket
        const ws = new WebSocket('ws://api/ws', [`Bearer.${token}`]);
        ```

        Query parameter authentication (?token=...) is deprecated but supported
        for backward compatibility.

    Args:
        websocket: The WebSocket connection
        instance_id: Optional instance ID to subscribe to
        organization_id: Optional organization ID to subscribe to
    """
    user = None
    user_id = None
    org_id = None
    inst_id = None

    # Extract sub-protocol to accept (RFC 6455 requires server to select a sub-protocol)
    subprotocol = extract_subprotocol_from_websocket(websocket)

    # Enforce global + per-IP connection caps before anything else.
    client_ip = await enforce_connection_limits(websocket, manager, subprotocol)
    if client_ip is None:
        return

    # Extract token from Sec-WebSocket-Protocol header or query param (deprecated)
    token = extract_token_from_websocket(websocket)

    # /ws requires auth. /ws/public is the single unauthenticated exception.
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
                code=status.WS_1008_POLICY_VIOLATION,
                reason=WS_CLOSE_REASON_AUTH_REQUIRED,
            )
        except Exception:
            pass
        return

    user_id = UUID(user["id"])

    if organization_id:
        try:
            org_id = UUID(organization_id)
        except ValueError:
            await manager.release_ip(client_ip)
            if subprotocol:
                await websocket.accept(subprotocol=subprotocol)
            else:
                await websocket.accept()
            await websocket.close(
                code=status.WS_1003_UNSUPPORTED_DATA, reason="Invalid organization ID"
            )
            return

    if instance_id:
        try:
            inst_id = UUID(instance_id)
        except ValueError:
            await manager.release_ip(client_ip)
            if subprotocol:
                await websocket.accept(subprotocol=subprotocol)
            else:
                await websocket.accept()
            await websocket.close(
                code=status.WS_1003_UNSUPPORTED_DATA, reason="Invalid instance ID"
            )
            return

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
            "message": "WebSocket connection established",
            "subscriptions": {
                "organization": str(org_id) if org_id else None,
                "instance": str(inst_id) if inst_id else None,
                "user": str(user_id) if user_id else None,
            },
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

                if message.get("action") == "subscribe":
                    subscription_type = message.get("subscription_type")
                    entity_id_str = message.get("entity_id")

                    if not subscription_type or subscription_type not in [
                        "organization",
                        "instance",
                        "user",
                    ]:
                        await manager.send_personal_message(
                            {"error": "Invalid subscription type"}, websocket
                        )
                        continue

                    if not entity_id_str:
                        await manager.send_personal_message(
                            {"error": "Entity ID is required for subscription"},
                            websocket,
                        )
                        continue

                    try:
                        entity_id = UUID(entity_id_str)
                    except ValueError:
                        await manager.send_personal_message(
                            {"error": "Invalid entity ID format"}, websocket
                        )
                        continue

                    if subscription_type == "organization":
                        await manager.disconnect(websocket, organization_id=org_id)
                        org_id = entity_id
                        await manager.connect(
                            websocket,
                            organization_id=org_id,
                            instance_id=inst_id,
                            user_id=user_id,
                        )
                    elif subscription_type == "instance":
                        await manager.disconnect(websocket, instance_id=inst_id)
                        inst_id = entity_id
                        await manager.connect(
                            websocket,
                            organization_id=org_id,
                            instance_id=inst_id,
                            user_id=user_id,
                        )
                    else:  # subscription_type == "user"
                        await manager.disconnect(websocket, user_id=user_id)
                        user_id = entity_id
                        await manager.connect(
                            websocket,
                            organization_id=org_id,
                            instance_id=inst_id,
                            user_id=user_id,
                        )

                    subscription_event: WSEventMessage = {
                        "event_type": "subscription_updated",
                        "timestamp": datetime.now(UTC).isoformat(),
                        "data": {
                            "subscription_type": subscription_type,
                            "entity_id": str(entity_id),
                        },
                    }
                    await manager.send_personal_message(subscription_event, websocket)

                elif message.get("action") == "unsubscribe":
                    subscription_type = message.get("subscription_type")

                    if not subscription_type or subscription_type not in [
                        "organization",
                        "instance",
                        "user",
                    ]:
                        await manager.send_personal_message(
                            {"error": "Invalid subscription type"}, websocket
                        )
                        continue

                    if subscription_type == "organization" and org_id:
                        await manager.disconnect(websocket, organization_id=org_id)
                        org_id = None
                    elif subscription_type == "instance" and inst_id:
                        await manager.disconnect(websocket, instance_id=inst_id)
                        inst_id = None
                    elif subscription_type == "user" and user_id:
                        await manager.disconnect(websocket, user_id=user_id)
                        user_id = None

                    unsubscribe_event: WSEventMessage = {
                        "event_type": "subscription_updated",
                        "timestamp": datetime.now(UTC).isoformat(),
                        "data": {
                            "message": f"Unsubscribed from {subscription_type}",
                            "subscriptions": {
                                "organization": str(org_id) if org_id else None,
                                "instance": str(inst_id) if inst_id else None,
                                "user": str(user_id) if user_id else None,
                            },
                        },
                    }
                    await manager.send_personal_message(unsubscribe_event, websocket)

                elif message.get("action") == "ping":
                    pong_event: WSEventMessage = {
                        "event_type": "pong",
                        "timestamp": datetime.now(UTC).isoformat(),
                        "data": {},
                    }
                    await manager.send_personal_message(pong_event, websocket)

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


@router.websocket("/ws/public")
async def public_websocket_endpoint(websocket: WebSocket):
    """
    Public WebSocket endpoint for maintenance updates (no authentication required).

    Clients connect to receive real-time maintenance mode announcements.
    Only broadcasts maintenance events - no other data is sent.
    """
    # Even the unauthenticated endpoint gets global + per-IP connection
    # caps and per-message rate limiting / idle timeout.
    client_ip = await enforce_connection_limits(websocket, manager)
    if client_ip is None:
        return

    await manager.connect(websocket=websocket, ip=client_ip)

    welcome_message: WSEventMessage = {
        "event_type": "connection_established",
        "timestamp": datetime.now(UTC).isoformat(),
        "data": {
            "message": "Public WebSocket connection established (maintenance updates only)",
            "subscriptions": {
                "organization": None,
                "instance": None,
                "user": None,
            },
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

                # Only handle ping messages
                if message.get("action") == "ping":
                    pong_event: WSEventMessage = {
                        "event_type": "pong",
                        "timestamp": datetime.now(UTC).isoformat(),
                        "data": {},
                    }
                    await manager.send_personal_message(pong_event, websocket)
                else:
                    await manager.send_personal_message(
                        {"error": "Only ping action is supported on public endpoint"},
                        websocket,
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
        await manager.disconnect(websocket=websocket)
        await release_connection(websocket, manager)


def register_event_handlers(event_bus: EventBus):
    """Register all WebSocket event handlers."""
    from app.presentation.websockets.handler_instance import (
        register_instance_event_handlers,
    )
    from app.presentation.websockets.handler_organization import (
        register_organization_event_handlers,
    )
    from app.presentation.websockets.handler_user import register_user_event_handlers

    register_instance_event_handlers(event_bus)
    register_organization_event_handlers(event_bus)
    register_user_event_handlers(event_bus)


# Handler modules register their routes when imported. They are imported lazily
# inside register_event_handlers() to avoid a circular import that forms when
# handler modules are loaded at module import time. The lazy import also triggers
# route registration and event handler subscription in a single call.
__all__ = [
    "register_event_handlers",
    "router",
    "WSEventMessage",
    "logger",
]
