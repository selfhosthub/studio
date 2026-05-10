# api/app/infrastructure/messaging/pg_notify.py

"""Helpers for publishing pg_notify messages to the four WebSocket channels."""

import json
import logging
from collections.abc import Mapping
from typing import Any
from uuid import UUID

from sqlalchemy import text

from app.infrastructure.messaging.pg_broadcaster import (
    CHANNEL_GLOBAL,
    CHANNEL_INST,
    CHANNEL_ORG,
    CHANNEL_USER,
)
from app.infrastructure.persistence.database import db
from app.presentation.websockets.manager import CustomJSONEncoder

logger = logging.getLogger(__name__)


async def _notify(channel: str, payload: Mapping[str, Any]) -> None:
    try:
        async with db.get_session_factory()() as session:
            await session.execute(
                text("SELECT pg_notify(:channel, :payload)"),
                {"channel": channel, "payload": json.dumps(dict(payload), cls=CustomJSONEncoder)},
            )
            await session.commit()
    except Exception as e:
        logger.error(f"pg_notify failed on channel {channel}: {e}")


async def notify_organization(org_id: UUID, message: Mapping[str, Any]) -> None:
    await _notify(CHANNEL_ORG, {**message, "_target_id": str(org_id)})


async def notify_instance(inst_id: UUID, message: Mapping[str, Any]) -> None:
    await _notify(CHANNEL_INST, {**message, "_target_id": str(inst_id)})


async def notify_user(user_id: UUID, message: Mapping[str, Any]) -> None:
    await _notify(CHANNEL_USER, {**message, "_target_id": str(user_id)})


async def notify_global(message: Mapping[str, Any]) -> None:
    await _notify(CHANNEL_GLOBAL, message)
