# api/app/config/docs_sync.py

"""Sync documentation from marketplace sources into the documentation table.

User and workflow docs come from the community source's docs-catalog.json
(boot, catalog refresh, seeding). Provider docs follow the provider install
lifecycle: fetched from the provider's tier source on install/reinstall,
flagged inactive on uninstall. Boot/refresh also re-fetches provider docs
for currently installed providers so content stays fresh across upgrades.

Sync is gated on the docs-catalog version (stored as a CatalogType.DOCS row in
marketplace_catalogs): an unchanged version skips remote file fetches for docs
already present, so a no-change reboot hits the remote once for the manifest
instead of re-pulling every file. A version bump re-fetches everything; missing
slugs are always backfilled regardless of version.
"""

import json
import logging
import re
from datetime import UTC, datetime
from typing import Optional, Tuple
from uuid import uuid4

import httpx

from app.config.sources import (
    COMMUNITY_SOURCE,
    DEFAULT_TIER,
    build_url,
    is_remote,
    local_path,
    source_for_tier,
)
from app.domain.common.value_objects import OperationalStatus
from app.domain.documentation.models import DocType, DocVisibility
from app.infrastructure.repositories.documentation_repository import (
    SQLAlchemyDocumentationRepository,
)

logger = logging.getLogger(__name__)

# Defense-in-depth even though docs no longer touch the filesystem: a slug is
# lowercase alphanumerics with '/', '-', '_' separators (e.g. 'shs/openai').
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9/_-]*$")


def _valid_slug(slug: str) -> bool:
    return bool(slug) and bool(_SLUG_RE.match(slug)) and ".." not in slug


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
    except ValueError as e:
        logger.warning(f"Invalid JSON from {url}: {e}")
        return None


def _read_local_text(source: str, repo_root: str, *parts: str) -> Optional[str]:
    path = local_path(source, repo_root, *parts)
    if not path.exists():
        logger.warning(f"Doc file not found: {path}")
        return None
    try:
        return path.read_text(encoding="utf-8")
    except Exception as e:
        logger.warning(f"Failed to read {path}: {e}")
        return None


async def _load_catalog(repo_root: str) -> Optional[dict]:
    """Load docs-catalog.json from the community source (remote or local)."""
    if is_remote(COMMUNITY_SOURCE):
        return await _fetch_json(build_url(COMMUNITY_SOURCE, "docs-catalog.json"))
    text = _read_local_text(COMMUNITY_SOURCE, repo_root, "docs-catalog.json")
    if text is None:
        return None
    try:
        return json.loads(text)
    except ValueError as e:
        logger.warning(f"Invalid docs-catalog.json in {COMMUNITY_SOURCE}: {e}")
        return None


async def _get_doc_text(
    relative_path: str, tier: str, repo_root: str
) -> Optional[str]:
    """Fetch a doc file (path relative to the source's docs/ dir) from a tier source."""
    source = source_for_tier(tier)
    if is_remote(source):
        return await _fetch_text(build_url(source, "docs", relative_path))
    return _read_local_text(source, repo_root, "docs", *relative_path.split("/"))


def _extract_meta(content: str, slug: str) -> Tuple[str, str]:
    """Title from the first '# ' heading, description from the first body paragraph."""
    title = slug.split("/")[-1].replace("-", " ").title()
    description = ""
    for i, line in enumerate(content.splitlines()):
        stripped = line.strip()
        if i == 0 and stripped.startswith("# "):
            title = stripped[2:].strip()
        elif i > 0 and stripped and not stripped.startswith("#"):
            description = stripped
            break
    return title, description


def _user_visibility(doc_id: str, public: bool) -> DocVisibility:
    if public:
        return DocVisibility.PUBLIC
    if doc_id == "super-admin":
        return DocVisibility.SUPER_ADMIN
    return DocVisibility.ADMIN


def _session_scope(session=None):
    """Yield (session, owns) - open one from the app factory when not given."""
    if session is not None:
        return session, False
    from app.infrastructure.persistence.database import db

    return db.get_session_factory()(), True


async def _get_synced_catalog_version(session) -> Optional[str]:
    """The docs-catalog version recorded by the last successful sync, if any."""
    from sqlalchemy import select

    from app.domain.provider.models import CatalogType
    from app.infrastructure.persistence.models import MarketplaceCatalogModel

    result = await session.execute(
        select(MarketplaceCatalogModel.version).where(
            MarketplaceCatalogModel.catalog_type == CatalogType.DOCS,
            MarketplaceCatalogModel.is_active.is_(True),
        )
    )
    return result.scalars().first()


async def _record_catalog_version(session, version, catalog) -> None:
    """Upsert the active docs-catalog row (version gate). Flush only; caller commits."""
    from sqlalchemy import select

    from app.domain.provider.models import CatalogType
    from app.infrastructure.persistence.models import MarketplaceCatalogModel

    result = await session.execute(
        select(MarketplaceCatalogModel).where(
            MarketplaceCatalogModel.catalog_type == CatalogType.DOCS,
            MarketplaceCatalogModel.is_active.is_(True),
        )
    )
    model = result.scalars().first()
    now = datetime.now(UTC)
    if model:
        model.version = version
        model.catalog_data = catalog
        model.fetched_at = now
        model.updated_at = now
    else:
        session.add(
            MarketplaceCatalogModel(
                id=uuid4(),
                catalog_type=CatalogType.DOCS,
                catalog_data=catalog,
                version=version,
                is_active=True,
                fetched_at=now,
            )
        )
    await session.flush()


async def _resolve_provider_tier(session, slug: str) -> str:
    """Tier from the installed provider's client_metadata, else community."""
    from sqlalchemy import select

    from app.infrastructure.persistence.models import ProviderModel

    result = await session.execute(
        select(ProviderModel.client_metadata).where(ProviderModel.slug == slug)
    )
    metadata = result.scalars().first() or {}
    return metadata.get("tier") or DEFAULT_TIER


async def _upsert_provider_doc(
    session, slug: str, tier: str, repo_root: str
) -> bool:
    """Fetch docs/providers/<slug>.md from the tier source and upsert it active."""
    if not _valid_slug(slug):
        logger.warning(f"Refusing provider doc sync for invalid slug: {slug!r}")
        return False
    if tier not in ("community", "plus"):
        tier = DEFAULT_TIER
    content = await _get_doc_text(f"providers/{slug}.md", tier, repo_root)
    if content is None:
        return False
    title, description = _extract_meta(content, slug)
    repo = SQLAlchemyDocumentationRepository(session)
    await repo.upsert(
        slug,
        DocType.PROVIDER,
        title=title,
        description=description,
        icon="box",
        content=content,
        visibility=DocVisibility.PUBLIC,
        source_tier=tier,
        active=True,
    )
    return True


async def _sync_with_session(session, repo_root: str, force: bool = False) -> int:
    """Reconcile docs against the catalog: download only missing or down-rev files.

    Skips remote fetches when the catalog version is unchanged and the doc is
    already present, so a server reboot with no upstream change touches the
    remote once (the catalog manifest) instead of re-pulling every file. A
    version bump forces a full re-fetch; missing slugs are always backfilled.
    A manual refresh passes force=True to re-pull every doc regardless of version.
    Returns the count of catalog docs now present (fetched + already-current).
    """
    catalog = await _load_catalog(repo_root)
    if not catalog:
        logger.warning("Could not load docs-catalog.json from community source")
        return 0

    repo = SQLAlchemyDocumentationRepository(session)
    remote_version = catalog.get("version")
    stored_version = await _get_synced_catalog_version(session)
    version_changed = (
        force or stored_version is None or remote_version != stored_version
    )
    present = {
        DocType.USER: {d.slug for d in await repo.list_by_type(DocType.USER)},
        DocType.WORKFLOW: {d.slug for d in await repo.list_by_type(DocType.WORKFLOW)},
        DocType.PROVIDER: {d.slug for d in await repo.list_by_type(DocType.PROVIDER)},
    }
    fetched = 0
    skipped = 0
    failed = 0

    for doc_id, doc_info in catalog.get("docs", {}).items():
        if not _valid_slug(doc_id):
            logger.warning(f"Skipping user doc with invalid slug: {doc_id!r}")
            continue
        if not version_changed and doc_id in present[DocType.USER]:
            skipped += 1
            continue
        filename = doc_info.get("file", f"{doc_id}.md")
        content = await _get_doc_text(filename, DEFAULT_TIER, repo_root)
        if content is None:
            failed += 1
            continue
        await repo.upsert(
            doc_id,
            DocType.USER,
            title=doc_info.get("title", doc_id.title()),
            description=doc_info.get("description", ""),
            icon=doc_info.get("icon", "book"),
            content=content,
            visibility=_user_visibility(doc_id, doc_info.get("public", False)),
            source_tier=DEFAULT_TIER,
            active=True,
        )
        fetched += 1

    for workflow in catalog.get("workflows", []):
        slug = workflow.get("id", "")
        if not _valid_slug(slug):
            logger.warning(f"Skipping workflow doc with invalid slug: {slug!r}")
            continue
        if not version_changed and slug in present[DocType.WORKFLOW]:
            skipped += 1
            continue
        # Doc files mirror the namespaced id at docs/workflows/<namespace>/<slug>.md.
        filename = workflow.get("file", f"workflows/{slug}.md")
        content = await _get_doc_text(filename, DEFAULT_TIER, repo_root)
        if content is None:
            failed += 1
            continue
        await repo.upsert(
            slug,
            DocType.WORKFLOW,
            title=workflow.get("title", slug.title()),
            description=workflow.get("description", ""),
            icon=workflow.get("icon", "box"),
            content=content,
            visibility=(
                DocVisibility.PUBLIC
                if workflow.get("public", True)
                else DocVisibility.ADMIN
            ),
            source_tier=DEFAULT_TIER,
            active=True,
        )
        fetched += 1

    # Refresh provider docs for installed, active providers. Install-time sync
    # covers new installs; this keeps content fresh and backfills deployments
    # that installed providers before docs moved to the database.
    from sqlalchemy import select

    from app.infrastructure.persistence.models import ProviderModel

    result = await session.execute(
        select(ProviderModel.slug, ProviderModel.client_metadata).where(
            ProviderModel.operational_status == OperationalStatus.ACTIVE
        )
    )
    # Multiple rows per slug exist (one per installed version) - sync each slug once.
    seen: dict[str, str] = {}
    for slug, metadata in result.all():
        seen.setdefault(slug, (metadata or {}).get("tier") or DEFAULT_TIER)
    for slug, tier in seen.items():
        if not version_changed and slug in present[DocType.PROVIDER]:
            skipped += 1
            continue
        if await _upsert_provider_doc(session, slug, tier, repo_root):
            fetched += 1
        else:
            failed += 1

    await _record_catalog_version(session, remote_version, catalog)
    logger.info(
        f"Docs synced to database: {fetched} fetched, {skipped} current, {failed} failed"
    )
    return fetched + skipped


async def sync_docs(
    repo_root: str = "/app", session=None, force: bool = False
) -> bool:
    """Sync the docs catalog into the documentation table.

    With a caller-provided session (seeder), flushes only - the caller owns
    the transaction. Otherwise opens an app session and commits. force=True
    bypasses the version gate and re-pulls every doc (manual refresh).
    """
    db_session, owns = _session_scope(session)
    if not owns:
        return await _sync_with_session(db_session, repo_root, force) > 0
    async with db_session as s:
        fetched = await _sync_with_session(s, repo_root, force)
        await s.commit()
    return fetched > 0


async def sync_provider_doc(
    slug: str, tier: Optional[str] = None, repo_root: str = "/app"
) -> bool:
    """Fetch and upsert one provider's doc after install/reinstall. Best-effort."""
    try:
        from app.infrastructure.persistence.database import db

        async with db.get_session_factory()() as session:
            if tier is None:
                tier = await _resolve_provider_tier(session, slug)
            ok = await _upsert_provider_doc(session, slug, tier, repo_root)
            await session.commit()
            return ok
    except Exception as e:
        logger.warning(f"Provider doc sync failed for {slug}: {e}")
        return False


async def deactivate_provider_doc(slug: str) -> bool:
    """Flag a provider's doc inactive on uninstall. Best-effort."""
    try:
        from app.infrastructure.persistence.database import db

        async with db.get_session_factory()() as session:
            repo = SQLAlchemyDocumentationRepository(session)
            ok = await repo.set_active(slug, DocType.PROVIDER, False)
            await session.commit()
            return ok
    except Exception as e:
        logger.warning(f"Provider doc deactivation failed for {slug}: {e}")
        return False


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
    """Catalog refresh sync; silent failure. Manual refresh bypasses the version gate."""
    try:
        return await sync_docs(repo_root, force=True)
    except Exception as e:
        logger.warning(f"Docs refresh failed: {e}")
        return False
