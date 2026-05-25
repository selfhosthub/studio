# api/app/infrastructure/messaging/pg_broadcaster.py

"""Postgres LISTEN/NOTIFY broadcaster.

Holds one long-lived asyncpg connection (outside the SA pool) and dispatches
incoming notifications to the local ConnectionManager. Any API instance can
publish a WebSocket event via pg_notify(); all instances receive it and push
to their local connected clients.

Static channel strategy - 4 fixed channel names, target ID carried in the
JSON payload under a "_target_id" key:
  Channel         Payload key    ConnectionManager method
  ──────────────────────────────────────────────────────
  ws_org          _target_id     broadcast_to_organization(UUID, msg)
  ws_inst         _target_id     broadcast_to_instance(UUID, msg)
  ws_user         _target_id     broadcast_to_user(UUID, msg)
  ws_global       (none)         broadcast(msg)

Publishers strip "_target_id" before delivering to clients.
"""

import asyncio
import json
import logging
from typing import TYPE_CHECKING, Any
from uuid import UUID

import asyncpg

from app.infrastructure.persistence.database import DATABASE_URL

if TYPE_CHECKING:
    from app.presentation.websockets.manager import ConnectionManager

logger = logging.getLogger(__name__)

CHANNEL_ORG = "ws_org"
CHANNEL_INST = "ws_inst"
CHANNEL_USER = "ws_user"
CHANNEL_GLOBAL = "ws_global"

ALL_CHANNELS = (CHANNEL_ORG, CHANNEL_INST, CHANNEL_USER, CHANNEL_GLOBAL)

_RECONNECT_BASE = 1.0
_RECONNECT_MAX = 30.0


def _raw_dsn(url: str) -> str:
    """Strip SQLAlchemy driver prefix so asyncpg can use it."""
    return url.replace("postgresql+asyncpg://", "postgresql://").split("?")[0]


class PgBroadcaster:
    """Long-lived LISTEN connection that fans pg_notify payloads to the local ConnectionManager."""

    def __init__(self, manager: "ConnectionManager") -> None:
        self._manager = manager
        self._conn: asyncpg.Connection | None = None
        self._task: asyncio.Task | None = None
        self._stopping = False

    async def start(self) -> None:
        self._stopping = False
        self._task = asyncio.create_task(self._run(), name="pg_broadcaster")
        logger.info("PgBroadcaster started")

    async def stop(self) -> None:
        self._stopping = True
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self._conn and not self._conn.is_closed():
            await self._conn.close()
        self._conn = None
        logger.info("PgBroadcaster stopped")

    async def _run(self) -> None:
        delay = _RECONNECT_BASE
        while not self._stopping:
            try:
                await self._connect_and_listen()
                delay = _RECONNECT_BASE
            except asyncio.CancelledError:
                break
            except Exception as e:
                if self._stopping:
                    break
                logger.warning(
                    f"PgBroadcaster disconnected ({e}). Reconnecting in {delay:.0f}s"
                )
                await asyncio.sleep(delay)
                delay = min(delay * 2, _RECONNECT_MAX)

    async def _connect_and_listen(self) -> None:
        dsn = _raw_dsn(DATABASE_URL)
        conn = await asyncpg.connect(dsn)
        self._conn = conn
        logger.info("PgBroadcaster: connected, registering LISTEN channels")

        # Must re-register after every reconnect - asyncpg drops LISTEN on disconnect
        for channel in ALL_CHANNELS:
            await conn.add_listener(channel, self._on_notification)

        try:
            while not self._stopping and not conn.is_closed():
                await asyncio.sleep(1)
        finally:
            if not conn.is_closed():
                await conn.close()
            self._conn = None

    def _on_notification(self, conn: Any, pid: int, channel: str, payload: str) -> None:
        """asyncpg callback - schedule async fan-out on the event loop."""
        asyncio.get_event_loop().create_task(
            self._fan_out(channel, payload),
            name=f"pg_fan_out_{channel}",
        )

    async def _fan_out(self, channel: str, raw_payload: str) -> None:
        try:
            envelope = json.loads(raw_payload)
        except json.JSONDecodeError:
            logger.warning(
                f"PgBroadcaster: invalid JSON on channel {channel}: {raw_payload[:80]}"
            )
            return

        # Strip routing key before delivering to clients
        target_id_str = envelope.pop("_target_id", None)
        message = envelope

        try:
            if channel == CHANNEL_GLOBAL:
                await self._manager.broadcast(message)
            elif channel == CHANNEL_ORG and target_id_str:
                await self._manager.broadcast_to_organization(
                    UUID(target_id_str), message
                )
            elif channel == CHANNEL_INST and target_id_str:
                await self._manager.broadcast_to_instance(UUID(target_id_str), message)
            elif channel == CHANNEL_USER and target_id_str:
                await self._manager.broadcast_to_user(UUID(target_id_str), message)
            else:
                logger.debug(
                    f"PgBroadcaster: unhandled channel={channel} target_id={target_id_str}"
                )
        except Exception as e:
            logger.error(f"PgBroadcaster fan-out error on {channel}: {e}")
