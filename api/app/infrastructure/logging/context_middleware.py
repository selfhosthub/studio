# api/app/infrastructure/logging/context_middleware.py

"""Middleware that surfaces request identity (user_id, correlation_id) to log
formatters. username/org_id/org_slug are filled in later by get_current_user from
the DB."""

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

        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:]
            try:
                # Local import: avoids circular dependency.
                from app.infrastructure.auth.jwt import verify_token

                payload = verify_token(token)
                user_id = payload.get("sub")
            except Exception:
                # Token invalid/expired - security audit handles the auth failure.
                pass

        # username/org_id/org_slug are intentionally NOT read from the JWT here.
        # They are filled in by get_current_user from the DB (source of truth)
        # once the request resolves, so log attribution matches the authz
        # decision. user_id (the token `sub`) is validated against the DB there.
        set_request_context(
            user_id=user_id,
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
