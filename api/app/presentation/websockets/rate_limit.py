# api/app/presentation/websockets/rate_limit.py

"""WebSocket DDoS protection: client-IP extraction, per-connection rate limiter, and connection-cap gates."""

import time
from collections import deque
from typing import Deque, Optional

from fastapi import WebSocket, status

from app.config.constants import (
    WS_CLOSE_REASON_IP_LIMIT,
    WS_CLOSE_REASON_TOTAL_LIMIT,
)
from app.config.settings import settings
from app.presentation.websockets.manager import ConnectionManager


def extract_client_ip(websocket: WebSocket) -> str:
    """Originating client IP via deployment-aware fallback.

    Order: CF-Connecting-IP (Cloudflare tunnel) → X-Forwarded-For leftmost
    (generic reverse proxy) → websocket.client.host (direct/dev) → "unknown".
    Without this chain, the per-IP cap collapses to the proxy endpoint and
    becomes useless. All four tiers must work with zero configuration.
    """
    cf = websocket.headers.get("cf-connecting-ip")
    if cf:
        return cf
    xff = websocket.headers.get("x-forwarded-for", "").split(",")[0].strip()
    if xff:
        return xff
    if websocket.client and websocket.client.host:
        return websocket.client.host
    return "unknown"


class MessageRateLimiter:
    """Per-connection sliding-window rate limiter. Pure in-memory; one per handler."""

    def __init__(self, limit: int, window_seconds: int) -> None:
        self._limit = limit
        self._window = window_seconds
        self._events: Deque[float] = deque()

    def check(self, now: Optional[float] = None) -> bool:
        """Record an attempt; True if it fits the window. now is injectable for tests."""
        current = now if now is not None else time.monotonic()
        cutoff = current - self._window
        while self._events and self._events[0] < cutoff:
            self._events.popleft()
        if len(self._events) >= self._limit:
            return False
        self._events.append(current)
        return True


async def enforce_connection_limits(
    websocket: WebSocket,
    manager: ConnectionManager,
    subprotocol: Optional[str] = None,
) -> Optional[str]:
    """Reserve a slot. Success → returns client IP. Failure → accept+1008 close+None.

    The handshake is accepted on failure so the 1008 close frame can actually be delivered.
    """
    ip = extract_client_ip(websocket)
    ok, reason = await manager.register_ip(ip)
    if ok:
        return ip

    if reason == "total_limit":
        close_reason = WS_CLOSE_REASON_TOTAL_LIMIT
    else:
        close_reason = WS_CLOSE_REASON_IP_LIMIT

    try:
        if subprotocol:
            await websocket.accept(subprotocol=subprotocol)
        else:
            await websocket.accept()
        await websocket.close(
            code=status.WS_1008_POLICY_VIOLATION,
            reason=close_reason,
        )
    except Exception:
        pass
    return None


async def release_connection(
    websocket: WebSocket, manager: ConnectionManager
) -> None:
    """Release the per-IP slot reserved by enforce_connection_limits."""
    ip = getattr(websocket.state, "client_ip", None)
    if ip:
        await manager.release_ip(ip)


def make_rate_limiter() -> MessageRateLimiter:
    """Rate limiter built from current settings."""
    return MessageRateLimiter(
        limit=settings.WS_MESSAGE_RATE_LIMIT,
        window_seconds=settings.WS_RATE_LIMIT_WINDOW_SECONDS,
    )
