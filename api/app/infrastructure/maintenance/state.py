# api/app/infrastructure/maintenance/state.py

"""Postgres-backed maintenance state. Replaces the in-process dataclass so all API instances share the same flag."""

import json
import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Optional

from sqlalchemy import text

from app.infrastructure.persistence.database import db

logger = logging.getLogger(__name__)

_MAINTENANCE_KEY = "maintenance"

# TTL cache: avoid a DB round-trip on every HTTP request.
# Any instance that writes also invalidates its own cache immediately.
_cache: Optional["MaintenanceStatusResponse"] = None
_cache_fetched_at: float = 0.0
_CACHE_TTL_SECONDS = 5.0


@dataclass
class MaintenanceStatusResponse:
    maintenance_mode: bool
    warning_mode: bool = False
    warning_until: Optional[str] = None
    reason: Optional[str] = None
    started_at: Optional[str] = None


def _invalidate_cache() -> None:
    global _cache_fetched_at
    _cache_fetched_at = 0.0


async def _read_row() -> dict:
    """Read the maintenance row from system_settings. Returns empty-off state if missing."""
    async with db.get_session_factory()() as session:
        result = await session.execute(
            text("SELECT value FROM system_settings WHERE key = :key"),
            {"key": _MAINTENANCE_KEY},
        )
        row = result.fetchone()
    if row is None:
        return {
            "maintenance_mode": False,
            "warning_mode": False,
            "warning_until": None,
            "reason": None,
            "started_at": None,
        }
    return dict(row[0])


async def _write_row(value: dict) -> None:
    """Upsert the maintenance row."""
    async with db.get_session_factory()() as session:
        await session.execute(
            text(
                "INSERT INTO system_settings (key, value, updated_at) "
                "VALUES (:key, CAST(:value AS jsonb), :updated_at) "
                "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = EXCLUDED.updated_at"
            ),
            {
                "key": _MAINTENANCE_KEY,
                "value": json.dumps(value),
                "updated_at": datetime.now(UTC),
            },
        )
        await session.commit()


def _row_to_response(row: dict) -> "MaintenanceStatusResponse":
    return MaintenanceStatusResponse(
        maintenance_mode=row.get("maintenance_mode", False),
        warning_mode=row.get("warning_mode", False) and not row.get("maintenance_mode", False),
        warning_until=row.get("warning_until"),
        reason=row.get("reason"),
        started_at=row.get("started_at"),
    )


async def get_maintenance_status() -> MaintenanceStatusResponse:
    """Return maintenance status, using a 5s TTL cache to avoid per-request DB hits."""
    global _cache, _cache_fetched_at

    now = time.monotonic()
    if _cache is not None and (now - _cache_fetched_at) < _CACHE_TTL_SECONDS:
        return _cache

    row = await _read_row()

    # Auto-promote warning → maintenance if warning_until has elapsed
    if row.get("warning_mode") and row.get("warning_until"):
        warning_until = datetime.fromisoformat(row["warning_until"])
        if datetime.now(UTC) >= warning_until:
            row["maintenance_mode"] = True
            row["started_at"] = datetime.now(UTC).isoformat()
            row["warning_mode"] = False
            row["warning_until"] = None
            await _write_row(row)
            logger.info(f"Maintenance mode auto-activated after warning period. Reason: {row.get('reason')}")

    response = _row_to_response(row)
    _cache = response
    _cache_fetched_at = time.monotonic()
    return response


async def set_maintenance_mode(enabled: bool, reason: Optional[str] = None) -> bool:
    row = await _read_row()
    if enabled:
        row["maintenance_mode"] = True
        row["reason"] = reason or "Scheduled maintenance"
        row["started_at"] = datetime.now(UTC).isoformat()
        row["warning_mode"] = False
        row["warning_until"] = None
    else:
        row["maintenance_mode"] = False
        row["reason"] = None
        row["started_at"] = None
        row["warning_mode"] = False
        row["warning_until"] = None
    await _write_row(row)
    _invalidate_cache()
    return True


async def set_maintenance_warning(minutes: int, reason: Optional[str] = None) -> bool:
    """Schedule a warning countdown that auto-promotes to maintenance once it expires."""
    row = await _read_row()
    row["warning_mode"] = True
    row["warning_until"] = (datetime.now(UTC) + timedelta(minutes=minutes)).isoformat()
    row["reason"] = reason or "Scheduled maintenance"
    await _write_row(row)
    _invalidate_cache()
    return True
