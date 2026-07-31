# api/app/application/services/comfyui_catalog_hash.py

"""Catalog hash helpers for worker-facing ComfyUI package sync (ST126)."""

import hashlib
import json
import re
import time
from typing import Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.persistence.models import ComfyUIWorkflowModel


def version_key(version: str) -> Tuple[int, ...]:
    """Sort key for semver-ish version strings ('1.2.3' -> (1, 2, 3))."""
    parts = []
    for part in version.split("."):
        match = re.match(r"\d+", part)
        parts.append(int(match.group()) if match else 0)
    return tuple(parts)


def content_hash(json_content: Dict) -> str:
    """SHA-256 of canonical JSON content."""
    normalized = json.dumps(json_content, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(normalized.encode()).hexdigest()


def catalog_hash_for(packages: List[Tuple[str, str, str]]) -> str:
    """SHA-256 over sorted 'slug@version:source_hash' lines."""
    lines = sorted(f"{slug}@{version}:{source_hash}" for slug, version, source_hash in packages)
    return hashlib.sha256("\n".join(lines).encode()).hexdigest()


async def list_active_packages(
    session: AsyncSession,
) -> List[Tuple[str, str, str]]:
    """(slug, version, source_hash) for the highest active version of each slug."""
    result = await session.execute(
        select(
            ComfyUIWorkflowModel.slug,
            ComfyUIWorkflowModel.version,
            ComfyUIWorkflowModel.source_hash,
            ComfyUIWorkflowModel.json_content,
        ).where(ComfyUIWorkflowModel.is_active.is_(True))
    )
    best: Dict[str, Tuple[str, Optional[str], Dict]] = {}
    for slug, version, source_hash, json_content in result.all():
        current = best.get(slug)
        if current is None or version_key(version) > version_key(current[0]):
            best[slug] = (version, source_hash, json_content)
    return [
        (slug, version, source_hash or content_hash(json_content))
        for slug, (version, source_hash, json_content) in sorted(best.items())
    ]


async def compute_catalog_hash(session: AsyncSession) -> Optional[str]:
    """Catalog hash over active packages; None when no active packages."""
    packages = await list_active_packages(session)
    if not packages:
        return None
    return catalog_hash_for(packages)


_CACHE_TTL_S = 30.0
_cache_value: Optional[str] = None
_cache_expires_at: float = 0.0


async def cached_catalog_hash(session: AsyncSession) -> Optional[str]:
    """compute_catalog_hash behind a module-level 30 second TTL cache."""
    global _cache_value, _cache_expires_at
    now = time.monotonic()
    if now < _cache_expires_at:
        return _cache_value
    _cache_value = await compute_catalog_hash(session)
    _cache_expires_at = now + _CACHE_TTL_S
    return _cache_value
