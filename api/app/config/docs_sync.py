# api/app/config/docs_sync.py

"""Fetch and sync documentation from the community source to DOCS_PATH."""

import json
import logging
import os
import shutil
from pathlib import Path
from typing import Optional

import httpx

from app.config.settings import settings
from app.config.sources import COMMUNITY_SOURCE, build_url, is_remote, local_path

logger = logging.getLogger(__name__)

DOCS_PATH: str = settings.DOCS_PATH


async def check_source_reachable() -> bool:
    """HEAD on the catalog for remote, dir exists for local."""
    if is_remote(COMMUNITY_SOURCE):
        try:
            url = build_url(COMMUNITY_SOURCE, "docs-catalog.json")
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.head(url)
                return resp.status_code < 400
        except Exception as e:
            logger.warning(f"Community source unreachable: {e}")
            return False
    else:
        return local_path(COMMUNITY_SOURCE, "/app").exists()


async def _fetch_text(url: str, timeout: float = 10.0) -> Optional[str]:
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.text
    except Exception as e:
        logger.warning(f"Failed to fetch {url}: {e}")
        return None


async def _fetch_json(url: str, timeout: float = 10.0) -> Optional[dict]:
    text = await _fetch_text(url, timeout)
    if text is None:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        logger.warning(f"Invalid JSON from {url}: {e}")
        return None


def _ensure_docs_dir() -> Path:
    docs = Path(DOCS_PATH)
    docs.mkdir(parents=True, exist_ok=True)
    return docs


def _write_doc(relative_path: str, content: str) -> bool:
    docs = _ensure_docs_dir()
    target = docs / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        target.write_text(content, encoding="utf-8")
        return True
    except Exception as e:
        logger.warning(f"Failed to write {target}: {e}")
        return False


def _write_catalog(catalog: dict) -> bool:
    docs = _ensure_docs_dir()
    target = docs / "docs-catalog.json"
    try:
        with open(target, "w", encoding="utf-8") as f:
            json.dump(catalog, f, indent=2)
            f.write("\n")
        return True
    except Exception as e:
        logger.warning(f"Failed to write docs-catalog.json: {e}")
        return False


async def _sync_remote() -> bool:
    catalog = await _fetch_json(build_url(COMMUNITY_SOURCE, "docs-catalog.json"))
    if not catalog:
        logger.warning("Could not fetch docs-catalog.json from remote")
        return False

    fetched = 0
    failed = 0

    for doc_id, doc_info in catalog.get("docs", {}).items():
        filename = doc_info.get("file", f"{doc_id}.md")
        url = build_url(COMMUNITY_SOURCE, "docs", filename)
        content = await _fetch_text(url)
        if content:
            _write_doc(filename, content)
            fetched += 1
        else:
            failed += 1

    for provider in catalog.get("providers", []):
        filename = provider.get("file", "")
        if not filename:
            continue
        url = build_url(COMMUNITY_SOURCE, "docs", filename)
        content = await _fetch_text(url)
        if content:
            _write_doc(filename, content)
            fetched += 1
        else:
            failed += 1

    for workflow in catalog.get("workflows", []):
        slug = workflow.get("id", "")
        if not slug:
            continue
        filename = f"workflows/{slug}.md"
        url = build_url(COMMUNITY_SOURCE, "docs", filename)
        content = await _fetch_text(url)
        if content:
            _write_doc(filename, content)
            fetched += 1
        else:
            failed += 1

    _write_catalog(catalog)

    logger.info(f"Docs synced from remote: {fetched} fetched, {failed} failed")
    return fetched > 0


def _sync_local(repo_root: str = "/app") -> bool:
    source = local_path(COMMUNITY_SOURCE, repo_root, "docs")
    if not source.exists():
        logger.warning(f"{COMMUNITY_SOURCE}/docs not found (normal in Docker)")
        return False

    target = Path(DOCS_PATH)

    # rmtree fails on bind-mounted dirs - clear contents instead
    if target.exists():
        for child in target.iterdir():
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
    else:
        target.mkdir(parents=True, exist_ok=True)
    shutil.copytree(str(source), str(target), dirs_exist_ok=True)

    catalog_src = local_path(COMMUNITY_SOURCE, repo_root, "docs-catalog.json")
    if catalog_src.exists():
        with open(catalog_src, "r", encoding="utf-8") as f:
            catalog = json.load(f)

        providers_dir = source / "providers"
        providers = []
        if providers_dir.is_dir():
            for md_file in sorted(os.listdir(providers_dir)):
                if not md_file.endswith(".md") or md_file == "index.md":
                    continue
                slug = md_file[:-3]
                title = slug.replace("-", " ").title() + " Provider"
                description = ""
                md_path = providers_dir / md_file
                with open(md_path, "r", encoding="utf-8") as mf:
                    for i, line in enumerate(mf):
                        stripped = line.strip()
                        if i == 0 and stripped.startswith("# "):
                            title = stripped[2:].strip()
                        elif i > 0 and stripped and not stripped.startswith("#"):
                            description = stripped
                            break
                providers.append(
                    {
                        "id": slug,
                        "title": title,
                        "description": description,
                        "file": f"providers/{slug}.md",
                        "icon": "box",
                        "public": True,
                    }
                )

        catalog["providers"] = providers
        _write_catalog(catalog)
        logger.info(
            f"Docs synced from {COMMUNITY_SOURCE}: {len(providers)} provider docs"
        )

    return True


async def sync_docs(repo_root: str = "/app") -> bool:
    """Download docs-catalog, help files, and provider docs to DOCS_PATH."""
    if is_remote(COMMUNITY_SOURCE):
        return await _sync_remote()
    else:
        return _sync_local(repo_root)


async def sync_docs_on_boot(repo_root: str = "/app") -> bool:
    """Sync docs during API startup. Caller surfaces unreachable to the UI."""
    reachable = await check_source_reachable()
    if not reachable:
        logger.warning(
            f"SHS_COMMUNITY_SOURCE ({COMMUNITY_SOURCE}) is not reachable. "
            "Docs will not be available until the source is reachable and a catalog refresh is triggered."
        )
        return False

    result = await sync_docs(repo_root)
    if result:
        logger.info("Docs loaded successfully on boot")
    else:
        logger.warning("Docs sync returned no results on boot")
    return result


async def sync_docs_on_refresh(repo_root: str = "/app") -> bool:
    """Catalog refresh sync; silent failure."""
    try:
        return await sync_docs(repo_root)
    except Exception as e:
        logger.warning(f"Docs refresh failed: {e}")
        return False
