# api/app/infrastructure/logging/context_middleware.py

"""Middleware that surfaces JWT identity (user_id, org_id, correlation_id) to log formatters."""

import uuid
from starlette.requests import Request

from app.infrastructure.logging.request_context import (
    set_request_context,
    clear_request_context,
)


class LoggingContextMiddleware:
    """Raw-ASGI middleware (not BaseHTTPMiddleware so WebSocket upgrades pass through)."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope)

        correlation_id = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())

        user_id = None
        username = None
        org_id = None
        org_slug = None

        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:]
            try:
                # Local import: avoids circular dependency.
                from app.infrastructure.auth.jwt import verify_token

                payload = verify_token(token)
                user_id = payload.get("sub")
                username = payload.get("username")
                org_id = payload.get("org_id")
                org_slug = payload.get("org_slug")
            except Exception:
                # Token invalid/expired - security audit handles the auth failure.
                pass

        set_request_context(
            user_id=user_id,
            username=username,
            org_id=org_id,
            org_slug=org_slug,
            correlation_id=correlation_id,
        )

        async def send_with_correlation(message):
            if message["type"] == "http.response.start":
                raw_headers = list(message.get("headers", []))
                raw_headers.append((b"x-correlation-id", correlation_id.encode()))
                message = {**message, "headers": raw_headers}
            await send(message)

        try:
            await self.app(scope, receive, send_with_correlation)
        finally:
            clear_request_context()
