# workers/studio_workers/engines/comfyui/package_store.py

"""Disk-cached catalog packages synced from the API (ST126).

Sync pulls the package list from /api/v1/internal/comfyui/packages,
fetches changed packages, and rebuilds the (service_id, model) registry
the handler resolves jobs against. Any sync failure leaves the previous
cache in effect.
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from studio_workers.settings import settings as worker_settings
from studio_workers.utils.cf_access import cf_access_headers

from .manifest import PackageManifest
from .settings import settings as comfyui_settings

logger = logging.getLogger(__name__)


def _default_cache_dir() -> Path:
    configured = comfyui_settings.COMFYUI_PACKAGE_CACHE_DIR
    if configured:
        return Path(configured)
    return Path.home() / ".cache" / "studio-workers" / "comfyui-packages"


class ComfyUIPackageStore:
    """Local mirror of active catalog packages plus the manifest registry."""

    def __init__(self, cache_dir: Optional[Path] = None):
        self.cache_dir = cache_dir or _default_cache_dir()
        self._lock = threading.Lock()
        self.catalog_hash: Optional[str] = None
        # (service_id, model_id or None) is resolved through these:
        self._by_service: Dict[str, List[PackageManifest]] = {}

    # -- local cache ------------------------------------------------------

    def _index_path(self) -> Path:
        return self.cache_dir / "index.json"

    def _package_path(self, slug: str) -> Path:
        return self.cache_dir / (slug.replace("/", "__") + ".json")

    def load_cached(self) -> int:
        """Load packages from disk into the registry; returns count loaded."""
        index_path = self._index_path()
        if not index_path.exists():
            return 0
        try:
            index = json.loads(index_path.read_text())
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning(f"ComfyUI package index unreadable: {exc}")
            return 0
        manifests = []
        for slug in index.get("packages", {}):
            path = self._package_path(slug)
            try:
                manifest = PackageManifest.from_package(
                    json.loads(path.read_text())
                )
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning(f"Cached package {slug} unreadable: {exc}")
                continue
            if manifest:
                manifests.append(manifest)
        with self._lock:
            self.catalog_hash = index.get("catalog_hash")
            self._rebuild_registry(manifests)
        return len(manifests)

    def _rebuild_registry(self, manifests: List[PackageManifest]) -> None:
        by_service: Dict[str, List[PackageManifest]] = {}
        for m in manifests:
            by_service.setdefault(m.service_id, []).append(m)
        self._by_service = by_service

    # -- resolution -------------------------------------------------------

    def resolve(
        self,
        service_id: str,
        slug: Optional[str] = None,
    ) -> Optional[PackageManifest]:
        """Manifest serving (service_id, slug); None when nothing matches.

        *slug* is the package reference (the workflow the user selected) and
        wins outright; without one the service's default package serves.
        """
        with self._lock:
            candidates = self._by_service.get(service_id, [])
            if not candidates:
                return None
            if slug:
                for m in candidates:
                    if m.slug == slug:
                        return m
                return None
            for m in candidates:
                if m.default_model:
                    return m
            # single-package services without models (e.g. imgedit)
            if len(candidates) == 1 and not candidates[0].models:
                return candidates[0]
            return None

    # -- sync -------------------------------------------------------------

    def sync(self, token_getter=None) -> bool:
        """Pull the package list and changed packages; returns True on success."""
        base = worker_settings.API_BASE_URL.rstrip("/")
        headers = {
            "X-Worker-Secret": worker_settings.WORKER_SHARED_SECRET,
            **cf_access_headers(),
        }
        if token_getter:
            token = token_getter()
            if token:
                headers["Authorization"] = f"Bearer {token}"
        try:
            with httpx.Client(
                timeout=worker_settings.HTTP_INTERNAL_TIMEOUT_S,
                headers=headers,
            ) as client:
                resp = client.get(f"{base}/api/v1/internal/comfyui/packages")
                resp.raise_for_status()
                listing = resp.json()
                remote = {p["slug"]: p for p in listing.get("packages", [])}

                index = {}
                if self._index_path().exists():
                    try:
                        index = json.loads(self._index_path().read_text())
                    except (json.JSONDecodeError, OSError):
                        index = {}
                local = index.get("packages", {})

                self.cache_dir.mkdir(parents=True, exist_ok=True)
                for slug, entry in remote.items():
                    cached = local.get(slug)
                    if cached and cached.get("source_hash") == entry.get(
                        "source_hash"
                    ):
                        continue
                    ns, name = slug.split("/", 1)
                    detail = client.get(
                        f"{base}/api/v1/internal/comfyui/packages/{ns}/{name}"
                    )
                    detail.raise_for_status()
                    self._package_path(slug).write_text(
                        json.dumps(detail.json()["package"])
                    )
                    logger.info(f"Synced comfyui package {slug}")
                for slug in set(local) - set(remote):
                    self._package_path(slug).unlink(missing_ok=True)
                    logger.info(f"Removed comfyui package {slug}")

                new_index = {
                    "catalog_hash": listing.get("catalog_hash"),
                    "packages": {
                        slug: {
                            "version": e.get("version"),
                            "source_hash": e.get("source_hash"),
                        }
                        for slug, e in remote.items()
                    },
                }
                self._index_path().write_text(json.dumps(new_index, indent=1))
        except (httpx.HTTPError, OSError, KeyError, ValueError) as exc:
            logger.warning(f"ComfyUI package sync failed: {exc}")
            return False

        self.load_cached()
        logger.info(
            f"ComfyUI package sync complete: {len(remote)} packages, "
            f"catalog {listing.get('catalog_hash', '')[:12]}"
        )
        return True
