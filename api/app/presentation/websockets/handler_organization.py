# api/app/presentation/websockets/handler_organization.py

"""WebSocket handlers for organization-specific real-time updates."""

import asyncio
import json
from datetime import UTC, datetime
from uuid import UUID

from fastapi import Depends, WebSocket, WebSocketDisconnect, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.services.organization import OrganizationService
from app.config.constants import (
    WS_CLOSE_REASON_IDLE,
    WS_CLOSE_REASON_RATE_LIMIT,
)
from app.config.settings import settings
from app.domain.common.events import DomainEvent
from app.domain.workflow.events import (
    WorkflowCreatedEvent,
    WorkflowEvent,
    WorkflowUpdatedEvent,
)
from app.infrastructure.auth.jwt import get_current_user_ws
from app.infrastructure.auth.websocket_auth import (
    extract_subprotocol_from_websocket,
    extract_token_from_websocket,
)
from app.infrastructure.messaging.event_bus import EventBus
from app.infrastructure.messaging.pg_notify import notify_organization
from app.infrastructure.persistence.database import get_db_session
from app.presentation.api.dependencies import get_organization_service_for_ws
from app.presentation.websockets.handlers import WSEventMessage, logger, router
from app.presentation.websockets.manager import manager
from app.presentation.websockets.rate_limit import (
    enforce_connection_limits,
    make_rate_limiter,
    release_connection,
)


@router.websocket("/ws/organization/{organization_id}")
async def organization_websocket_endpoint(
    websocket: WebSocket,
    organization_id: str,
    organization_service: OrganizationService = Depends(
        get_organization_service_for_ws
    ),
    session: AsyncSession = Depends(get_db_session),
):
    """Org-scoped updates. Auth via Bearer.<token> in Sec-WebSocket-Protocol; ?token= deprecated."""
    user = None
    user_id = None

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
        org_id = UUID(organization_id)
    except ValueError:
        await manager.release_ip(client_ip)
        try:
            if subprotocol:
                await websocket.accept(subprotocol=subprotocol)
            else:
                await websocket.accept()
            await websocket.close(
                code=status.WS_1003_UNSUPPORTED_DATA, reason="Invalid organization ID"
            )
        except Exception:
            pass
        return

    try:
        organization = await organization_service.get_organization(org_id)
    except Exception:
        organization = None

    if not organization:
        await manager.release_ip(client_ip)
        try:
            if subprotocol:
                await websocket.accept(subprotocol=subprotocol)
            else:
                await websocket.accept()
            await websocket.close(
                code=status.WS_1008_POLICY_VIOLATION,
                reason="Organization not found or access denied",
            )
        except Exception:
            pass
        return

    if user:
        is_super_admin = user.get("role") == "super_admin"
        is_own_org = str(user.get("org_id")) == str(org_id)
        if not is_super_admin and not is_own_org:
            await manager.release_ip(client_ip)
            try:
                if subprotocol:
                    await websocket.accept(subprotocol=subprotocol)
                else:
                    await websocket.accept()
                await websocket.close(
                    code=status.WS_1008_POLICY_VIOLATION,
                    reason="Access to this organization not allowed",
                )
            except Exception:
                pass
            return

    await manager.connect(
        websocket=websocket,
        organization_id=org_id,
        user_id=user_id,
        subprotocol=subprotocol,
        ip=client_ip,
    )

    welcome_message: WSEventMessage = {
        "event_type": "connection_established",
        "timestamp": datetime.now(UTC).isoformat(),
        "data": {
            "message": "Organization WebSocket connection established",
            "organization_id": str(org_id),
            "user_id": str(user_id) if user_id else None,
        },
    }
    await manager.send_personal_message(welcome_message, websocket)

    try:
        from typing import cast

        from app.domain.organization.models import Organization

        org = cast(Organization, organization)

        org_data: WSEventMessage = {
            "event_type": "organization_data",
            "timestamp": datetime.now(UTC).isoformat(),
            "data": {
                "organization_id": str(org.id),
                "name": org.name,
                "slug": org.slug,
                "is_active": org.is_active,
            },
        }
        await manager.send_personal_message(org_data, websocket)

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
            websocket=websocket, organization_id=org_id, user_id=user_id
        )
        await release_connection(websocket, manager)


async def handle_organization_events(event: DomainEvent):
    """Workflow events → org-scoped WebSocket broadcasts."""
    if not isinstance(event, WorkflowEvent):
        logger.warning(
            f"Non-workflow event received by workflow handler: {event.event_type}"
        )
        return

    match event:
        case WorkflowCreatedEvent():
            await notify_organization(
                event.organization_id,
                {
                    "event_type": "workflow_created",
                    "timestamp": datetime.now(UTC).isoformat(),
                    "data": {
                        "workflow_id": str(event.workflow_id),
                        "organization_id": str(event.organization_id),
                        "name": event.name,
                    },
                },
            )

        case WorkflowUpdatedEvent():
            await notify_organization(
                event.organization_id,
                {
                    "event_type": "workflow_updated",
                    "timestamp": datetime.now(UTC).isoformat(),
                    "data": {
                        "workflow_id": str(event.workflow_id),
                        "organization_id": str(event.organization_id),
                        "name": event.name,
                    },
                },
            )

        case _:
            pass


def register_organization_event_handlers(event_bus: EventBus):
    """Register organization and workflow-related event handlers."""
    from typing import Awaitable, Callable

    workflow_handler: Callable[[DomainEvent], Awaitable[None]] = (
        lambda event: handle_organization_events(event)
    )
    event_bus.subscribe("workflow.created", workflow_handler)
    event_bus.subscribe("workflow.updated", workflow_handler)
    event_bus.subscribe("workflow.activated", workflow_handler)
    event_bus.subscribe("workflow.deactivated", workflow_handler)
