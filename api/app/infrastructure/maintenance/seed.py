# api/app/infrastructure/maintenance/seed.py

"""Seed the system_settings maintenance row on first startup."""

import json
import logging
from datetime import UTC, datetime

from sqlalchemy import text

from app.config.settings import settings
from app.infrastructure.persistence.database import db

logger = logging.getLogger(__name__)

_MAINTENANCE_KEY = "maintenance"


async def seed_maintenance_row() -> None:
    """Insert default maintenance row if absent. ON CONFLICT DO NOTHING - never clobbers admin changes."""
    initial_value = {
        "maintenance_mode": settings.MAINTENANCE_MODE,
        "warning_mode": False,
        "warning_until": None,
        "reason": (
            "Maintenance mode enabled via environment"
            if settings.MAINTENANCE_MODE
            else None
        ),
        "started_at": (
            datetime.now(UTC).isoformat() if settings.MAINTENANCE_MODE else None
        ),
    }

    async with db.get_session_factory()() as session:
        await session.execute(
            text(
                "INSERT INTO system_settings (key, value, updated_at) "
                "VALUES (:key, CAST(:value AS jsonb), :updated_at) "
                "ON CONFLICT (key) DO NOTHING"
            ),
            {
                "key": _MAINTENANCE_KEY,
                "value": json.dumps(initial_value),
                "updated_at": datetime.now(UTC),
            },
        )
        await session.commit()
