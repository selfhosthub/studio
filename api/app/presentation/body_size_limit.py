# api/app/presentation/body_size_limit.py

"""ASGI middleware that refuses HTTP request bodies over a byte limit with 413."""

import json
from typing import Any, Callable, Dict

from app.config.settings import settings

Scope = Dict[str, Any]
Message = Dict[str, Any]


class BodyTooLarge(Exception):
    """Raised from receive() once a streamed body passes the limit."""


def max_body_bytes() -> int:
    """The configured request body limit in bytes."""
    return settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024


class BodySizeLimitMiddleware:
    """Answer 413 for a request body over the limit, whether declared up front or streamed."""

    def __init__(self, app: Callable) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Callable, send: Callable) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        limit = max_body_bytes()
        declared = dict(scope.get("headers") or []).get(b"content-length")
        if declared is not None and declared.isdigit() and int(declared) > limit:
            await _send_413(send, limit)
            return

        received = 0
        exceeded = False
        responded = False

        async def limited_receive() -> Message:
            nonlocal received, exceeded
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    exceeded = True
                    raise BodyTooLarge()
            return message

        async def guarded_send(message: Message) -> None:
            nonlocal responded
            if exceeded:
                if not responded:
                    responded = True
                    await _send_413(send, limit)
                return
            if message["type"] == "http.response.start":
                responded = True
            await send(message)

        try:
            await self.app(scope, limited_receive, guarded_send)
        except BodyTooLarge:
            if not responded:
                await _send_413(send, limit)


async def _send_413(send: Callable, limit: int) -> None:
    """Write a JSON 413 naming the limit in megabytes."""
    body = json.dumps(
        {"detail": f"Request body exceeds the {limit // (1024 * 1024)} MB limit."}
    ).encode()
    await send(
        {
            "type": "http.response.start",
            "status": 413,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})
