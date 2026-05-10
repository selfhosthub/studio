# api/app/presentation/websockets/manager.py

"""WebSocket connection manager: tracks active connections and broadcasts messages."""

import asyncio
import json
import logging
from datetime import UTC, datetime
from typing import Any, Dict, List, Literal, Optional, Tuple
from uuid import UUID

from fastapi import WebSocket
from pydantic import BaseModel, ConfigDict

from app.config.settings import settings

RegisterIpReason = Literal["ok", "total_limit", "ip_limit"]


class CustomJSONEncoder(json.JSONEncoder):
    """Handles datetime and UUID types. Any other non-standard type is a bug - raises TypeError."""

    def default(self, o: Any) -> Any:
        if isinstance(o, datetime):
            return o.isoformat()
        if isinstance(o, UUID):
            return str(o)
        return super().default(o)


logger = logging.getLogger(__name__)


class ConnectionManager:
    """WebSocket connection manager - tracks active connections and provides broadcast methods."""

    def __init__(self) -> None:
        # General connections
        self.active_connections: List[WebSocket] = []

        # Organization-specific connections
        self.org_connections: Dict[UUID, List[WebSocket]] = {}

        # Instance-specific connections
        self.instance_connections: Dict[UUID, List[WebSocket]] = {}

        # User-specific connections
        self.user_connections: Dict[UUID, List[WebSocket]] = {}

        # Per-IP connection counts (DDoS protection)
        self.ip_connections: Dict[str, int] = {}

        # Track which websockets have been accepted (survives re-subscribe)
        self._accepted: set[WebSocket] = set()

        # Lock for thread-safe operations
        self.lock = asyncio.Lock()

    async def register_ip(self, ip: str) -> Tuple[bool, RegisterIpReason]:
        """
        Reserve a connection slot for ip against the global and per-IP caps.

        Returns (True, "ok") when accepted, (False, "total_limit") when the
        global cap is reached, or (False, "ip_limit") when the per-IP cap is
        reached. On success the caller must call release_ip exactly once when
        the connection is fully torn down. The disconnect method does not
        auto-release because it is also called during mid-session subscription
        updates.
        """
        async with self.lock:
            if len(self.active_connections) >= settings.WS_MAX_TOTAL_CONNECTIONS:
                return False, "total_limit"
            if self.ip_connections.get(ip, 0) >= settings.WS_MAX_CONNECTIONS_PER_IP:
                return False, "ip_limit"
            self.ip_connections[ip] = self.ip_connections.get(ip, 0) + 1
            return True, "ok"

    async def release_ip(self, ip: str) -> None:
        """Release a previously registered IP slot."""
        async with self.lock:
            count = self.ip_connections.get(ip, 0)
            if count <= 1:
                self.ip_connections.pop(ip, None)
            else:
                self.ip_connections[ip] = count - 1

    async def connect(
        self,
        websocket: WebSocket,
        organization_id: Optional[UUID] = None,
        instance_id: Optional[UUID] = None,
        user_id: Optional[UUID] = None,
        subprotocol: Optional[str] = None,
        ip: Optional[str] = None,
    ) -> None:
        """
        Connect a WebSocket client and register it in the appropriate groups.

        When ip is provided it is tagged on the socket state so the teardown
        path can release the slot without re-extracting headers.
        """
        # Accept the WebSocket connection (skip if already accepted - e.g., re-subscribe)
        if websocket not in self._accepted:
            if subprotocol:
                await websocket.accept(subprotocol=subprotocol)
            else:
                await websocket.accept()
            self._accepted.add(websocket)

        # Tag the socket with its IP so disconnect() can release the slot
        # without the caller having to remember the value.
        if ip is not None:
            websocket.state.client_ip = ip

        async with self.lock:
            self.active_connections.append(websocket)

            # Register in organization-specific group
            if organization_id:
                if organization_id not in self.org_connections:
                    self.org_connections[organization_id] = []
                self.org_connections[organization_id].append(websocket)

            # Register in instance-specific group
            if instance_id:
                if instance_id not in self.instance_connections:
                    self.instance_connections[instance_id] = []
                self.instance_connections[instance_id].append(websocket)

            # Register in user-specific group
            if user_id:
                if user_id not in self.user_connections:
                    self.user_connections[user_id] = []
                self.user_connections[user_id].append(websocket)

        logger.debug(
            f"WebSocket client connected - Org: {organization_id}, Instance: {instance_id}, User: {user_id}"
        )

    async def disconnect(
        self,
        websocket: WebSocket,
        organization_id: Optional[UUID] = None,
        instance_id: Optional[UUID] = None,
        user_id: Optional[UUID] = None,
    ) -> None:
        """Disconnect a WebSocket client and remove it from all groups."""
        async with self.lock:
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)

            if organization_id and organization_id in self.org_connections:
                conns = self.org_connections[organization_id]
                if websocket in conns:
                    conns.remove(websocket)
                if not conns:
                    del self.org_connections[organization_id]

            if instance_id and instance_id in self.instance_connections:
                conns = self.instance_connections[instance_id]
                if websocket in conns:
                    conns.remove(websocket)
                if not conns:
                    del self.instance_connections[instance_id]

            if user_id and user_id in self.user_connections:
                conns = self.user_connections[user_id]
                if websocket in conns:
                    conns.remove(websocket)
                if not conns:
                    del self.user_connections[user_id]

        logger.debug(
            f"WebSocket client disconnected - Org: {organization_id}, Instance: {instance_id}, User: {user_id}"
        )

    async def _send_with_timeout(
        self, websocket: WebSocket, message: str
    ) -> Optional[WebSocket]:
        """Send with a bounded delivery budget.

        Returns None on success and the websocket on failure (timeout or any
        exception). The caller collects failed sockets and removes them from its
        connection registry. Bounded liveness prevents one half-open client from
        pinning a coroutine indefinitely.
        """
        try:
            await asyncio.wait_for(
                websocket.send_text(message),
                timeout=settings.WS_SEND_TIMEOUT_SECONDS,
            )
            return None
        except Exception:  # noqa: BLE001 - any failure means drop the connection
            return websocket

    @staticmethod
    async def _chunked_gather(
        coros: list, chunk_size: int = 250
    ) -> list:
        """Run coroutines in chunks to avoid an unbounded gather at high fanout."""
        results: list = []
        for i in range(0, len(coros), chunk_size):
            chunk_results = await asyncio.gather(*coros[i : i + chunk_size], return_exceptions=True)
            results.extend(chunk_results)
        return results

    async def send_personal_message(self, message: Any, websocket: WebSocket) -> None:
        """Send a message to a specific WebSocket connection."""
        if isinstance(message, str):
            text = message
        elif isinstance(message, BaseModel):
            text = json.dumps(message.model_dump(), cls=CustomJSONEncoder)
        else:
            text = json.dumps(message, cls=CustomJSONEncoder)
        if (await self._send_with_timeout(websocket, text)) is not None:
            logger.debug("Failed to send personal message to WebSocket")

    async def broadcast(self, message: Any) -> None:
        """Broadcast a message to all connected clients."""
        if isinstance(message, dict) or isinstance(message, BaseModel):
            message = json.dumps(
                message if isinstance(message, dict) else message.model_dump(),
                cls=CustomJSONEncoder,
            )

        results = await self._chunked_gather(
            [self._send_with_timeout(c, message) for c in self.active_connections]
        )
        disconnected: List[WebSocket] = [r for r in results if isinstance(r, WebSocket)]

        if disconnected:
            async with self.lock:
                for ws in disconnected:
                    if ws in self.active_connections:
                        self.active_connections.remove(ws)

    async def broadcast_to_organization(
        self, organization_id: UUID, message: Any
    ) -> None:
        """Broadcast a message to all clients subscribed to a specific organization."""
        if organization_id not in self.org_connections:
            return

        if isinstance(message, dict) or isinstance(message, BaseModel):
            message = json.dumps(
                message if isinstance(message, dict) else message.model_dump(),
                cls=CustomJSONEncoder,
            )

        results = await self._chunked_gather(
            [self._send_with_timeout(c, message) for c in self.org_connections[organization_id]]
        )
        disconnected: List[WebSocket] = [r for r in results if isinstance(r, WebSocket)]

        if disconnected:
            async with self.lock:
                conns = self.org_connections.get(organization_id, [])
                for ws in disconnected:
                    if ws in conns:
                        conns.remove(ws)
                if (
                    organization_id in self.org_connections
                    and not self.org_connections[organization_id]
                ):
                    del self.org_connections[organization_id]

    async def broadcast_to_instance(self, instance_id: UUID, message: Any) -> None:
        """Broadcast a message to all clients subscribed to a specific workflow instance."""
        if instance_id not in self.instance_connections:
            return

        if isinstance(message, dict) or isinstance(message, BaseModel):
            message = json.dumps(
                message if isinstance(message, dict) else message.model_dump(),
                cls=CustomJSONEncoder,
            )

        results = await self._chunked_gather(
            [self._send_with_timeout(c, message) for c in self.instance_connections[instance_id]]
        )
        disconnected: List[WebSocket] = [r for r in results if isinstance(r, WebSocket)]

        if disconnected:
            async with self.lock:
                conns = self.instance_connections.get(instance_id, [])
                for ws in disconnected:
                    if ws in conns:
                        conns.remove(ws)
                if (
                    instance_id in self.instance_connections
                    and not self.instance_connections[instance_id]
                ):
                    del self.instance_connections[instance_id]

    async def broadcast_to_user(self, user_id: UUID, message: Any) -> None:
        """Broadcast a message to all connections of a specific user."""
        if user_id not in self.user_connections:
            return

        if isinstance(message, dict) or isinstance(message, BaseModel):
            message = json.dumps(
                message if isinstance(message, dict) else message.model_dump(),
                cls=CustomJSONEncoder,
            )

        results = await self._chunked_gather(
            [self._send_with_timeout(c, message) for c in self.user_connections[user_id]]
        )
        disconnected: List[WebSocket] = [r for r in results if isinstance(r, WebSocket)]

        if disconnected:
            async with self.lock:
                conns = self.user_connections.get(user_id, [])
                for ws in disconnected:
                    if ws in conns:
                        conns.remove(ws)
                if (
                    user_id in self.user_connections
                    and not self.user_connections[user_id]
                ):
                    del self.user_connections[user_id]


# Global connection manager instance
manager = ConnectionManager()


class WebSocketEvent(BaseModel):
    event_type: str
    timestamp: datetime = datetime.now(UTC)
    data: Dict[str, Any]

    model_config = ConfigDict(arbitrary_types_allowed=True)
