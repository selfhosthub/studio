# api/app/infrastructure/auth/websocket_auth.py

"""WebSocket auth - token extraction via Sec-WebSocket-Protocol header."""

from typing import Optional

from fastapi import WebSocket


def extract_subprotocol_from_websocket(websocket: WebSocket) -> Optional[str]:
    """Return the `Bearer.{token}` sub-protocol so the handshake can echo it back.

    RFC 6455: if the client proposes sub-protocols, the server must select one.
    """
    protocols = websocket.headers.get("sec-websocket-protocol", "")

    if protocols:
        for protocol in protocols.split(","):
            protocol = protocol.strip()
            if protocol.startswith("Bearer."):
                return protocol

    return None


def extract_token_from_websocket(websocket: WebSocket) -> Optional[str]:
    """Extract a JWT from a WebSocket handshake.

    Prefers the Sec-WebSocket-Protocol header (Bearer.<token>). Falls back to the
    ?token= query param (DEPRECATED - leaks into logs/history) with a warning.
    """
    import logging

    logger = logging.getLogger(__name__)

    protocols = websocket.headers.get("sec-websocket-protocol", "")

    if protocols:
        for protocol in protocols.split(","):
            protocol = protocol.strip()
            if protocol.startswith("Bearer."):
                token = protocol[7:]
                logger.debug("Token extracted from Sec-WebSocket-Protocol header")
                return token

    token_from_query = websocket.query_params.get("token")

    if token_from_query:
        logger.warning(
            "WebSocket token passed via query parameter (DEPRECATED). "
            "Please migrate to Sec-WebSocket-Protocol header. "
            "See documentation for details."
        )
        return token_from_query

    logger.debug("No authentication token found in WebSocket connection")
    return None
