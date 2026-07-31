# api/app/config/catalog.py

"""Catalog URL construction, fetch+merge, and cache TTL."""

import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Optional

import httpx

from app.config.settings import settings
from app.config.sources import (
    COMMUNITY_SOURCE,
    PLUS_SOURCE,
    build_url as _sources_build_url,
    is_remote,
    local_path,
    source_for_tier,
)

logger = logging.getLogger(__name__)

CATALOG_CACHE_HOURS: int = settings.CATALOG_CACHE_HOURS

# Catalog filenames - identical across both sources
PROVIDERS = "providers-catalog.json"
WORKFLOWS = "workflows-catalog.json"
PROMPTS = "prompts-catalog.json"
COMFYUI = "comfyui-catalog.json"

REPO_COMMUNITY = COMMUNITY_SOURCE
REPO_PLUS = PLUS_SOURCE


def build_url(source: str, catalog_name: str) -> str:
    """URL for remote source, descriptive path for local source."""
    if is_remote(source):
        return _sources_build_url(source, catalog_name)
    return f"{source}/{catalog_name}"


async def _fetch_one(url: str, token: Optional[str] = None) -> Optional[dict]:
    headers = {}
    if token:
        headers["Authorization"] = f"token {token}"
    try:
        async with httpx.AsyncClient(
            timeout=settings.MARKETPLACE_CATALOG_TIMEOUT
        ) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            return response.json()
    except Exception as e:
        logger.warning(f"Failed to fetch catalog from {url}: {e}")
        return None


def _read_local(source: str, catalog_name: str) -> Optional[dict]:
    path = local_path(source, "/app", catalog_name)
    if not path.exists():
        logger.warning(f"Failed to fetch catalog from {source}/{catalog_name}")
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"Failed to read catalog from {path}: {e}")
        return None


async def fetch_and_merge(
    catalog_name: str,
    list_key: str,
    token: Optional[str] = None,
) -> Optional[dict]:
    """Fetch catalog from the community source.

    Catalog JSON contains entries for every tier; the plus source holds only
    installable package files. Tier-gated access is enforced at install time,
    so token is unused here (retained for API compatibility).
    """
    if is_remote(COMMUNITY_SOURCE):
        url = build_url(COMMUNITY_SOURCE, catalog_name)
        data = await _fetch_one(url)
    else:
        data = _read_local(COMMUNITY_SOURCE, catalog_name)

    if not data:
        return None

    return {"version": data.get("version", "1.0.0"), list_key: data.get(list_key, [])}


async def fetch_item_file(
    item_path: str,
    tier: str = "community",
    token: Optional[str] = None,
) -> Optional[dict]:
    """Fetch a single per-item detail file (e.g. ``prompts/shs/foo.json``).

    Catalog list responses stay lean; full prompt chunks / workflow steps live
    in per-item files fetched on demand. Community-tier items come from the
    community source, plus from the plus source (with token).
    """
    source = source_for_tier(tier)
    parts = item_path.strip("/").split("/")
    if is_remote(source):
        url = build_url(source, item_path)
        auth = token if tier == "plus" else None
        return await _fetch_one(url, token=auth)
    path = local_path(source, "/app", *parts)
    if not path.exists():
        logger.warning(f"Item file not found: {source}/{item_path}")
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"Failed to read item file from {path}: {e}")
        return None


def is_stale(cache_time: Optional[datetime]) -> bool:
    if cache_time is None:
        return True
    return datetime.now(UTC) - cache_time > timedelta(hours=CATALOG_CACHE_HOURS)


def is_file_stale(path: Path) -> bool:
    if not path.exists():
        return True
    mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
    return is_stale(mtime)
