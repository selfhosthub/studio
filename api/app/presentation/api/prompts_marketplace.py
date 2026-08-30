# api/app/presentation/api/prompts_marketplace.py

"""
API endpoints for the prompts marketplace.

Prompts are small (chunks + variables), so catalog data is embedded
inline - no download URLs needed.  The catalog is stored in the database,
fetched from remote sources (GitHub) or uploaded manually.
"""

import json
import logging
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel

from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import select

from app.application.services.catalog_merge_service import (
    merge_prompts_with_marketplace,
)
from app.config.sources import DEFAULT_TIER, VALID_TIERS
from app.infrastructure.persistence.models import OrganizationModel, PromptModel
from app.presentation.api.dependencies import (
    CurrentUser,
    get_db_session,
    get_db_session_rls,
    get_db_session_service,
    get_marketplace_catalog_repository,
    get_organization_secret_repository,
    get_prompt_repository,
    require_admin,
    require_super_admin,
)
from app.domain.organization_secret.repository import OrganizationSecretRepository
from app.presentation.api.marketplace import get_entitlement_token
from app.domain.prompt.models import (
    Prompt,
    PromptChunk,
    PromptSource,
    PromptVariable,
)
from app.domain.prompt.repository import PromptRepository
from app.infrastructure.repositories.marketplace_catalog_repository import (
    SQLAlchemyMarketplaceCatalogRepository,
)
from app.infrastructure.services.package_version_service import PackageVersionService
from app.domain.provider.models import CatalogType, PackageType
from app.config import catalog as cat_config

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Prompts Marketplace"])


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class CatalogChunk(BaseModel):
    """A chunk entry inside the catalog JSON."""

    text: str
    variable: Optional[str] = None
    order: int = 0
    role: Optional[str] = None


class CatalogVariable(BaseModel):
    """A variable entry inside the catalog JSON."""

    name: str
    label: str
    type: str = "string"
    options: Optional[List[str]] = None
    option_labels: Optional[List[str]] = None
    default: Optional[str] = None
    required: bool = False


class MarketplacePrompt(BaseModel):
    """A prompt entry from the marketplace catalog."""

    id: str  # slug, e.g. "shs-news-narrator"
    display_name: str
    version: str
    tier: str  # "community" | "plus"
    category: str
    description: str
    author: str
    chunks: List[CatalogChunk] = []
    variables: List[CatalogVariable] = []
    # Per-item file location; full chunks/variables fetched on demand.
    path: Optional[str] = None
    # Catalog-reference vs super-org-managed (cross-org merge); visibility
    # meaningful only for managed entries.
    origin: str = "catalog-reference"
    visibility: Optional[str] = None


class RemoteCatalog(BaseModel):
    """Raw catalog shape from remote / local JSON file."""

    model_config = {"populate_by_name": True}

    version: str
    prompts: List[MarketplacePrompt]


class PromptsCatalogResponse(BaseModel):
    """Response for GET /catalog."""

    version: str
    prompts: List[MarketplacePrompt]
    filter_options: Dict[str, List[str]]
    warnings: List[str] = []


class InstallResponse(BaseModel):
    """Response from install endpoint."""

    success: bool
    prompt_id: Optional[str] = None
    prompt_name: Optional[str] = None
    message: str
    already_installed: bool = False


class InstalledPromptInfo(BaseModel):
    """Info about one installed marketplace prompt."""

    marketplace_id: str
    prompt_id: str  # Local DB UUID
    name: str
    category: str


class InstalledPromptsResponse(BaseModel):
    """Response for GET /installed."""

    installed_ids: List[str]
    installed_prompts: List[InstalledPromptInfo] = []


class CatalogUploadResponse(BaseModel):
    """Response from catalog upload."""

    success: bool
    version: str
    prompt_count: int
    message: str


# ---------------------------------------------------------------------------
# Catalog loading helpers
# ---------------------------------------------------------------------------


async def fetch_remote_catalog(token: Optional[str] = None) -> Optional[RemoteCatalog]:
    """Fetch prompts catalog from community catalog (+ plus catalog if token), merge."""
    data = await cat_config.fetch_and_merge(cat_config.PROMPTS, "prompts", token=token)
    if data:
        return RemoteCatalog(**data)
    return None


async def get_catalog_from_database(
    catalog_repo: SQLAlchemyMarketplaceCatalogRepository,
) -> Optional[RemoteCatalog]:
    """Get the active prompts catalog from the database."""
    catalog = await catalog_repo.get_active(CatalogType.PROMPTS)
    if catalog and catalog.catalog_data:
        try:
            return RemoteCatalog(**catalog.catalog_data)
        except Exception as e:
            logger.warning(f"Failed to parse prompts catalog data from database: {e}")
            return None
    return None


async def refresh_catalog_from_remote(
    catalog_repo: SQLAlchemyMarketplaceCatalogRepository,
    token: Optional[str] = None,
) -> Optional[RemoteCatalog]:
    """Fetch prompts catalog from remote and store in database."""
    remote_catalog = await fetch_remote_catalog(token=token)
    source_url = cat_config.build_url(cat_config.REPO_COMMUNITY, cat_config.PROMPTS)

    if remote_catalog:
        await catalog_repo.upsert_active(
            catalog_type=CatalogType.PROMPTS,
            catalog_data=remote_catalog.model_dump(),
            source_url=source_url,
        )
        logger.info(
            f"Refreshed prompts catalog from {source_url}: "
            f"v{remote_catalog.version}, {len(remote_catalog.prompts)} entries"
        )
        return remote_catalog
    else:
        await catalog_repo.set_fetch_error(
            catalog_type=CatalogType.PROMPTS,
            error_message=f"Failed to fetch catalog from {source_url}",
        )
        return None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/catalog", response_model=PromptsCatalogResponse)
async def get_prompts_catalog(
    category: Optional[str] = Query(None, description="Filter by category"),
    tier: Optional[str] = Query(None, description="Filter by tier: community, plus"),
    current_user: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
    bypass_db: AsyncSession = Depends(get_db_session_service),
    catalog_repo: SQLAlchemyMarketplaceCatalogRepository = Depends(
        get_marketplace_catalog_repository
    ),
) -> PromptsCatalogResponse:
    """
    Browse the prompts marketplace catalog.

    Super-admin: sees the full catalog (everything available to install),
    loaded from the database-cached catalog with auto-refresh from remote.

    Org admin: platform-installed prompts (package_versions) plus the super-org's
    managed prompts the org is entitled to see (the cross-org merge).
    """
    is_super_admin = current_user.get("role") == "super_admin"

    if not is_super_admin:
        org_id = uuid.UUID(current_user["org_id"])
        return await _org_admin_catalog_prompts(db, bypass_db, category, tier, org_id)

    return await _super_admin_catalog_prompts(db, catalog_repo, category, tier)


async def _resolve_system_org_and_staging(
    db: AsyncSession, caller_org_id: uuid.UUID
) -> tuple[Optional[uuid.UUID], bool]:
    """(system_org_id, caller_is_staging). organizations is not
    RLS-protected, so the plain session reads it."""
    rows = (
        await db.execute(
            select(
                OrganizationModel.id,
                OrganizationModel.settings,
                OrganizationModel.is_staging,
            )
        )
    ).all()
    system_org_id: Optional[uuid.UUID] = None
    caller_is_staging = False
    for org_uuid, settings_json, is_staging in rows:
        if (settings_json or {}).get("is_system"):
            system_org_id = org_uuid
        if org_uuid == caller_org_id:
            caller_is_staging = bool(is_staging)
    return system_org_id, caller_is_staging


async def _org_admin_catalog_prompts(
    db: AsyncSession,
    bypass_db: AsyncSession,
    category: Optional[str],
    tier: Optional[str],
    org_id: uuid.UUID,
) -> PromptsCatalogResponse:
    """Org-admin catalog: platform-installed prompts (package_versions) plus the
    super-org's managed prompts the caller is entitled to see (cross-org merge)."""
    active = await PackageVersionService.list_active(db, PackageType.PROMPT)

    prompts: List[MarketplacePrompt] = []
    for pv in active:
        entry = pv.json_content.get("catalog_entry", {})
        chunks_data = pv.json_content.get("chunks", [])
        variables_data = pv.json_content.get("variables", [])

        prompts.append(
            MarketplacePrompt(
                id=pv.slug,
                display_name=entry.get("display_name", pv.slug),
                version=entry.get("version", pv.version),
                tier=entry.get("tier", DEFAULT_TIER),
                category=entry.get("category", ""),
                description=entry.get("description", ""),
                author=entry.get("author", ""),
                chunks=[CatalogChunk(**c) for c in chunks_data],
                variables=[CatalogVariable(**v) for v in variables_data],
            )
        )

    # Fold in the super-org's managed prompts the caller is entitled to see.
    seen_ids = {p.id for p in prompts}
    system_org_id, caller_is_staging = await _resolve_system_org_and_staging(db, org_id)
    if system_org_id is not None:
        for cat_entry in await merge_prompts_with_marketplace(
            bypass_db,
            system_org_id=system_org_id,
            caller_org_id=org_id,
            caller_is_staging=caller_is_staging,
        ):
            if cat_entry.id in seen_ids:
                continue
            seen_ids.add(cat_entry.id)
            prompts.append(
                MarketplacePrompt(
                    id=cat_entry.id,
                    display_name=cat_entry.name,
                    version=cat_entry.version or "1.0.0",
                    tier=DEFAULT_TIER,
                    category=cat_entry.category or "",
                    description=cat_entry.description or "",
                    author="",
                    origin="managed",
                    visibility=(
                        cat_entry.visibility.value if cat_entry.visibility else None
                    ),
                )
            )

    if tier:
        prompts = [p for p in prompts if p.tier == tier]
    if category:
        prompts = [p for p in prompts if p.category == category]

    categories = sorted({p.category for p in prompts})
    tiers = sorted({p.tier for p in prompts})

    return PromptsCatalogResponse(
        version=active[0].version if active else "1.0.0",
        prompts=prompts,
        filter_options={
            "tier": tiers if tiers else list(VALID_TIERS),
            "category": categories,
        },
    )


async def _super_admin_catalog_prompts(
    db: AsyncSession,
    catalog_repo: SQLAlchemyMarketplaceCatalogRepository,
    category: Optional[str],
    tier: Optional[str],
) -> PromptsCatalogResponse:
    """Super-admin catalog: full catalog from database, auto-refresh if stale."""
    warnings: List[str] = []

    # Auto-refresh if stale (community catalog only - no token on GET)
    db_catalog_record = await catalog_repo.get_active(CatalogType.PROMPTS)
    if cat_config.is_stale(db_catalog_record.fetched_at if db_catalog_record else None):
        try:
            result = await refresh_catalog_from_remote(catalog_repo)
            if result is None:
                warnings.append(
                    "Prompts catalog refresh returned no data. Using cached catalog."
                )
        except Exception as e:
            logger.warning(f"Auto-refresh of prompts catalog failed: {e}")
            warnings.append(
                f"Prompts catalog auto-refresh failed: {e}. Using cached data."
            )

    catalog = await get_catalog_from_database(catalog_repo)

    if not catalog:
        warnings.append("No catalog data available. Run seed or refresh catalog.")
        return PromptsCatalogResponse(
            version="1.0.0",
            prompts=[],
            filter_options={"tier": list(VALID_TIERS), "category": []},
            warnings=warnings,
        )

    prompts = list(catalog.prompts)

    if tier:
        prompts = [p for p in prompts if p.tier == tier]
    if category:
        prompts = [p for p in prompts if p.category == category]

    categories = sorted({p.category for p in prompts})
    tiers = sorted({p.tier for p in prompts})

    return PromptsCatalogResponse(
        version=catalog.version,
        prompts=prompts,
        filter_options={
            "tier": tiers if tiers else list(VALID_TIERS),
            "category": categories,
        },
        warnings=warnings,
    )


@router.get("/catalog/{namespace}/{slug}", response_model=MarketplacePrompt)
async def get_prompt_detail(
    namespace: str,
    slug: str,
    current_user: CurrentUser = Depends(require_super_admin),
    secret_repo: OrganizationSecretRepository = Depends(
        get_organization_secret_repository
    ),
    catalog_repo: SQLAlchemyMarketplaceCatalogRepository = Depends(
        get_marketplace_catalog_repository
    ),
) -> MarketplacePrompt:
    """Full pre-install detail for one catalog prompt (super-admin).

    The catalog list ships metadata only; chunks/variables live in a per-item
    file fetched here on demand so the list stays lean at hundreds of prompts.
    """
    prompt_slug = f"{namespace}/{slug}"
    catalog = await get_catalog_from_database(catalog_repo)
    if not catalog:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Marketplace catalog not available",
        )

    entry = next((p for p in catalog.prompts if p.id == prompt_slug), None)
    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Prompt '{prompt_slug}' not found in catalog",
        )

    # Already inline (managed prompts, or catalogs that embed content)? Return.
    if entry.chunks or entry.variables or not entry.path:
        return entry

    token = await get_entitlement_token(current_user["org_id"], secret_repo)
    data = await cat_config.fetch_item_file(entry.path, tier=entry.tier, token=token)
    if not data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Prompt detail for '{prompt_slug}' could not be fetched",
        )

    return entry.model_copy(
        update={
            "chunks": [CatalogChunk(**c) for c in data.get("chunks", [])],
            "variables": [CatalogVariable(**v) for v in data.get("variables", [])],
        }
    )


@router.get("/installed", response_model=InstalledPromptsResponse)
async def get_installed_prompts(
    current_user: CurrentUser = Depends(require_admin),
    prompt_repo: PromptRepository = Depends(get_prompt_repository),
    db: AsyncSession = Depends(get_db_session),
) -> InstalledPromptsResponse:
    """
    List marketplace prompts that are installed.

    Super-admin: returns platform-installed prompts (from package_versions).
    Org admin: returns prompts copied into their organization.
    """
    is_super = current_user.get("role") == "super_admin"

    installed_ids: List[str] = []
    installed_prompts: List[InstalledPromptInfo] = []

    if is_super:
        # Platform view: what's installed on this server
        active = await PackageVersionService.list_active(db, PackageType.PROMPT)
        for pv in active:
            catalog_entry = pv.json_content.get("catalog_entry", {})
            installed_ids.append(pv.slug)
            installed_prompts.append(
                InstalledPromptInfo(
                    marketplace_id=pv.slug,
                    prompt_id=pv.slug,
                    name=catalog_entry.get("display_name", pv.slug),
                    category=catalog_entry.get("category", ""),
                )
            )

        # Also include custom prompts (source="super_admin") so the
        # super-admin gets a "Remove" button to pull them from the catalog.
        seen_slugs = {pv.slug for pv in active}
        super_admin_prompts = await prompt_repo.list_by_source(PromptSource.SUPER_ADMIN)
        for p in super_admin_prompts:
            tid = str(p.id)
            if tid not in seen_slugs:
                seen_slugs.add(tid)
                installed_ids.append(tid)
                installed_prompts.append(
                    InstalledPromptInfo(
                        marketplace_id=tid,
                        prompt_id=tid,
                        name=p.name,
                        category=p.category or "",
                    )
                )
    else:
        # Org view: what's copied into this org
        org_id = current_user["org_id"]

        all_prompts = await prompt_repo.list_by_organization(
            organization_id=uuid.UUID(org_id),
            enabled_only=False,
        )

        for p in all_prompts:
            if p.source == PromptSource.MARKETPLACE:
                installed_ids.append(p.slug)
                installed_prompts.append(
                    InstalledPromptInfo(
                        marketplace_id=p.slug,
                        prompt_id=str(p.id),
                        name=p.name,
                        category=p.category,
                    )
                )

    return InstalledPromptsResponse(
        installed_ids=installed_ids,
        installed_prompts=installed_prompts,
    )


@router.post("/install/{namespace}/{slug}", response_model=InstallResponse)
async def install_prompt(
    namespace: str,
    slug: str,
    force: bool = False,
    current_user: CurrentUser = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session_rls),
    db: AsyncSession = Depends(get_db_session),
    bypass_db: AsyncSession = Depends(get_db_session_service),
    prompt_repo: PromptRepository = Depends(get_prompt_repository),
    secret_repo: OrganizationSecretRepository = Depends(
        get_organization_secret_repository
    ),
    catalog_repo: SQLAlchemyMarketplaceCatalogRepository = Depends(
        get_marketplace_catalog_repository
    ),
) -> InstallResponse:
    prompt_slug = f"{namespace}/{slug}"
    """
    Install a prompt from the marketplace catalog.

    Super-admin: looks up the catalog entry and records the install in
    package_versions (no download needed - prompts are inline).

    Org admin: copies a platform-installed prompt into their organization
    directly from package_versions - no catalog lookup, no secret_repo.

    Idempotent by default - if already installed, returns already_installed: true.
    Pass force=true to make an additional copy with a unique slug suffix
    (e.g. shs/foo-copy-2) so users can keep the original alongside an edited copy.
    """
    is_super_admin = current_user.get("role") == "super_admin"
    org_id = current_user["org_id"]

    if not is_super_admin:
        return await _org_copy_prompt(
            prompt_slug,
            org_id,
            db,
            bypass_db,
            prompt_repo,
            current_user,
            force=force,
        )

    # Super-admin path: catalog lookup + platform install
    catalog = await get_catalog_from_database(catalog_repo)
    if not catalog:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Marketplace catalog not available",
        )

    entry: Optional[MarketplacePrompt] = None
    for p in catalog.prompts:
        if p.id == prompt_slug:
            entry = p
            break

    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Prompt '{prompt_slug}' not found in catalog",
        )

    # Token check for plus-tier prompts
    token: Optional[str] = None
    if entry.tier == "plus":
        token = await get_entitlement_token(org_id, secret_repo)
        if not token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="ENTITLEMENT_TOKEN not configured. Add it via Settings > Secrets.",
            )

    # List ships metadata only; hydrate chunks/variables from the per-item file
    # before recording, or package_versions stores an empty prompt.
    if not entry.chunks and not entry.variables and entry.path:
        if token is None:
            token = await get_entitlement_token(org_id, secret_repo)
        data = await cat_config.fetch_item_file(
            entry.path, tier=entry.tier, token=token
        )
        if not data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Prompt detail for '{prompt_slug}' could not be fetched",
            )
        entry = entry.model_copy(
            update={
                "chunks": [CatalogChunk(**c) for c in data.get("chunks", [])],
                "variables": [CatalogVariable(**v) for v in data.get("variables", [])],
            }
        )

    # Platform install: record in package_versions only
    active = await PackageVersionService.list_active(db, PackageType.PROMPT)
    for pv in active:
        if pv.slug == prompt_slug:
            return InstallResponse(
                success=True,
                prompt_id=prompt_slug,
                prompt_name=entry.display_name,
                message="Prompt already installed on platform",
                already_installed=True,
            )

    pv_json_content = {
        "catalog_entry": {
            "id": entry.id,
            "display_name": entry.display_name,
            "version": entry.version,
            "tier": entry.tier,
            "category": entry.category,
            "description": entry.description,
            "author": entry.author,
        },
        "chunks": [c.model_dump() for c in entry.chunks],
        "variables": [v.model_dump() for v in entry.variables],
    }
    pv_source_hash = PackageVersionService.compute_source_hash(pv_json_content)
    await PackageVersionService.record_version(
        session=db,
        package_type=PackageType.PROMPT,
        slug=entry.id,
        version=entry.version,
        json_content=pv_json_content,
        source_hash=pv_source_hash,
        created_by=uuid.UUID(current_user["id"]),
        allow_reserved=True,
    )

    logger.info(
        f"Platform-installed prompt '{prompt_slug}' "
        f"by {current_user.get('username')}"
    )

    return InstallResponse(
        success=True,
        prompt_id=prompt_slug,
        prompt_name=entry.display_name,
        message="Prompt installed to platform",
    )


async def _load_managed_prompt_source(
    db: AsyncSession,
    bypass_db: AsyncSession,
    prompt_slug: str,
    org_uuid: uuid.UUID,
):
    """Entitlement-checked load of a published super-org (managed) prompt as
    (catalog_entry, chunks_data, variables_data) - the same shape the
    package_versions copy path consumes. Returns None if not entitled / found.
    Entitlement is RE-CHECKED via merge_prompts_with_marketplace (the slug must
    be in the caller's entitled managed set). Prompt chunks/variables live on
    the row directly, so a single RLS-bypassing read suffices."""
    system_org_id, caller_is_staging = await _resolve_system_org_and_staging(
        db, org_uuid
    )
    if system_org_id is None:
        return None
    entitled = await merge_prompts_with_marketplace(
        bypass_db,
        system_org_id=system_org_id,
        caller_org_id=org_uuid,
        caller_is_staging=caller_is_staging,
    )
    match = next((e for e in entitled if e.id == prompt_slug), None)
    if match is None:
        return None
    row = (
        await bypass_db.execute(
            select(PromptModel).where(PromptModel.id == uuid.UUID(match.install_ref))
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    catalog_entry = {
        "display_name": row.name,
        "description": row.description or "",
        "version": "1.0.0",
        "tier": "community",
        "category": row.category or "",
        "author": "",
    }
    return catalog_entry, list(row.chunks or []), list(row.variables or [])


async def _org_copy_prompt(
    prompt_slug: str,
    org_id: str,
    db: AsyncSession,
    bypass_db: AsyncSession,
    prompt_repo: PromptRepository,
    current_user: CurrentUser,
    force: bool = False,
) -> InstallResponse:
    """Org admin copy: create org prompt from package_versions OR a published
    super-org managed prompt (entitlement re-checked in the loader).

    When force=True, bypasses idempotency and creates an additional copy with
    a `-copy-N` slug suffix (and display-name suffix) so the user can keep
    the original alongside an edited copy.
    """
    # Source: platform-installed package_versions, or a managed super-org prompt.
    platform_pv = await PackageVersionService.get_active_by_slug(
        db,
        PackageType.PROMPT,
        prompt_slug,
    )
    if platform_pv:
        src_catalog_entry = platform_pv.json_content.get("catalog_entry", {})
        src_chunks_data = platform_pv.json_content.get("chunks", [])
        src_variables_data = platform_pv.json_content.get("variables", [])
    else:
        managed = await _load_managed_prompt_source(
            db, bypass_db, prompt_slug, uuid.UUID(org_id)
        )
        if managed is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Prompt not available. Ask your administrator to install it first.",
            )
        src_catalog_entry, src_chunks_data, src_variables_data = managed

    # Idempotent check - also handles re-install of soft-deleted prompts.
    # Skipped when force=True so the user can deliberately make another copy.
    if not force:
        existing = await prompt_repo.get_by_slug(
            slug=prompt_slug,
            organization_id=uuid.UUID(org_id),
        )
        if existing:
            if existing.source == PromptSource.UNINSTALLED:
                await prompt_repo.reactivate_marketplace(existing.id)
                logger.info(
                    f"Re-installed prompt '{prompt_slug}' "
                    f"(id={existing.id}) for org {org_id}"
                )
                return InstallResponse(
                    success=True,
                    prompt_id=str(existing.id),
                    prompt_name=existing.name,
                    message="Prompt re-installed successfully",
                )
            return InstallResponse(
                success=True,
                prompt_id=str(existing.id),
                prompt_name=existing.name,
                message="Prompt already installed",
                already_installed=True,
            )

    # Source data resolved above (package_versions or managed live row).
    catalog_entry = src_catalog_entry
    chunks_data = src_chunks_data
    variables_data = src_variables_data

    chunks = [
        PromptChunk(
            text=c.get("text", ""),
            variable=c.get("variable"),
            order=c.get("order", 0),
            role=c.get("role"),
        )
        for c in chunks_data
    ]
    variables = [
        PromptVariable(
            name=v.get("name", ""),
            label=v.get("label", ""),
            type=v.get("type", "string"),
            options=v.get("options"),
            option_labels=v.get("option_labels"),
            default=v.get("default"),
            required=bool(v.get("required", False)),
        )
        for v in variables_data
    ]

    display_name = catalog_entry.get("display_name", prompt_slug)
    # slug must be namespaced to satisfy ck_prompt_slug_namespaced. Catalog ids
    # are always namespaced - a flat slug is a bad request, not silently
    # prefixed with a guessed `shs/` namespace.
    if "/" not in prompt_slug:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Prompt slug must be namespaced (e.g. 'shs/{prompt_slug}'); "
                f"got '{prompt_slug}'"
            ),
        )
    namespaced_slug = prompt_slug

    if force:
        # Find the next available `-copy-N` suffix within the org.
        org_prompts = await prompt_repo.list_by_organization(
            organization_id=uuid.UUID(org_id),
            enabled_only=False,
        )
        taken = {p.slug for p in org_prompts}
        n = 2
        while f"{namespaced_slug}-copy-{n}" in taken:
            n += 1
        namespaced_slug = f"{namespaced_slug}-copy-{n}"
        display_name = f"{display_name} (copy {n})"

    new_prompt = Prompt.create(
        organization_id=uuid.UUID(org_id),
        name=display_name,
        slug=namespaced_slug,
        description=catalog_entry.get("description", ""),
        category=catalog_entry.get("category", ""),
        chunks=chunks,
        variables=variables,
        source=PromptSource.MARKETPLACE,
    )

    saved = await prompt_repo.create(new_prompt)

    logger.info(
        f"Copied prompt '{prompt_slug}' as '{display_name}' "
        f"(id={saved.id}) to org {org_id}"
    )

    return InstallResponse(
        success=True,
        prompt_id=str(saved.id),
        prompt_name=saved.name,
        message="Prompt copied to organization",
    )


@router.post("/uninstall/{namespace}/{slug}", status_code=status.HTTP_200_OK)
async def uninstall_prompt(
    namespace: str,
    slug: str,
    current_user: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
    prompt_repo: PromptRepository = Depends(get_prompt_repository),
) -> Dict[str, Any]:
    prompt_slug = f"{namespace}/{slug}"
    """
    Uninstall a marketplace prompt.

    Super-admin: removes from platform (package_versions). Org copies are
    unaffected since they are independent copies.

    Org admin: soft-deletes the prompt copy from their organization.
    """
    org_id = current_user["org_id"]
    is_super = current_user.get("role") == "super_admin"

    if is_super:
        # Platform uninstall - remove from package_versions
        active = await PackageVersionService.list_active(db, PackageType.PROMPT)
        for pv in active:
            if pv.slug == prompt_slug:
                await PackageVersionService.soft_delete(
                    db, PackageType.PROMPT, prompt_slug
                )
                catalog_entry = pv.json_content.get("catalog_entry", {})
                name = catalog_entry.get("display_name", prompt_slug)
                logger.info(
                    f"Platform-uninstalled prompt '{prompt_slug}' "
                    f"by {current_user.get('username')}"
                )
                return {
                    "success": True,
                    "message": f"Prompt '{name}' removed from platform",
                }

        # Super-admin removing a custom prompt from the marketplace catalog.
        # Custom prompts use the source prompt's UUID as the slug part of the
        # namespaced id (e.g. `shs/<uuid>`); accept either form here.
        slug_part = prompt_slug.split("/", 1)[-1]
        try:
            source_id = uuid.UUID(slug_part)
        except ValueError:
            source_id = None

        if source_id:
            source = await prompt_repo.get_by_id(source_id)
            if source and source.source == PromptSource.SUPER_ADMIN:
                await prompt_repo.delete(source_id)
                logger.info(
                    f"Super-admin removed custom prompt '{source.name}' "
                    f"(id={source_id}) from marketplace catalog"
                )
                return {
                    "success": True,
                    "message": f"Prompt '{source.name}' removed from marketplace",
                }

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Prompt '{prompt_slug}' is not installed on the platform",
        )

    # Org uninstall - soft-delete the org's prompt copy
    existing = await prompt_repo.get_by_slug(
        slug=prompt_slug,
        organization_id=uuid.UUID(org_id),
    )

    if existing:
        await prompt_repo.soft_delete_marketplace(existing.id)
        logger.info(
            f"Removed prompt copy '{prompt_slug}' (id={existing.id}) "
            f"from org {org_id}"
        )
        return {"success": True, "message": f"Prompt '{existing.name}' removed"}

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Prompt '{prompt_slug}' is not installed in your organization",
    )


@router.post(
    "/catalog/upload",
    response_model=CatalogUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_prompts_catalog(
    file: UploadFile = File(..., description="prompts-catalog.json file"),
    _current_user: CurrentUser = Depends(require_super_admin),
    catalog_repo: SQLAlchemyMarketplaceCatalogRepository = Depends(
        get_marketplace_catalog_repository
    ),
) -> CatalogUploadResponse:
    """
    Upload a new prompts catalog file.  Super admin only.
    """
    if not file.filename or not file.filename.endswith(".json"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be a .json file",
        )

    try:
        content = await file.read()
        data = json.loads(content.decode("utf-8"))
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON format",
        )
    except Exception as e:
        logger.error(f"Failed to read uploaded prompts catalog file: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to read file",
        )

    # Validate catalog structure
    try:
        catalog = RemoteCatalog(**data)
    except Exception as e:
        logger.error(f"Invalid prompts catalog format: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid catalog format",
        )

    # Store in database
    await catalog_repo.upsert_active(
        catalog_type=CatalogType.PROMPTS,
        catalog_data=data,
        source_url=None,  # Manual upload
        source_tag=None,
    )

    logger.info(
        f"Uploaded prompts catalog v{catalog.version} "
        f"with {len(catalog.prompts)} prompts"
    )

    return CatalogUploadResponse(
        success=True,
        version=catalog.version,
        prompt_count=len(catalog.prompts),
        message=(
            f"Prompts catalog uploaded successfully "
            f"with {len(catalog.prompts)} prompts"
        ),
    )


@router.post("/catalog/refresh", response_model=CatalogUploadResponse)
async def refresh_prompts_catalog(
    current_user: CurrentUser = Depends(require_super_admin),
    secret_repo: OrganizationSecretRepository = Depends(
        get_organization_secret_repository
    ),
    catalog_repo: SQLAlchemyMarketplaceCatalogRepository = Depends(
        get_marketplace_catalog_repository
    ),
) -> CatalogUploadResponse:
    """
    Re-fetch the prompts catalog from community catalog (+ plus catalog if token) and store in database.
    """
    org_id = current_user["org_id"]
    if not org_id:
        raise HTTPException(status_code=400, detail="User has no organization")
    token = await get_entitlement_token(org_id, secret_repo)

    remote = await refresh_catalog_from_remote(catalog_repo, token=token)
    if not remote:
        source_url = cat_config.build_url(cat_config.REPO_COMMUNITY, cat_config.PROMPTS)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to fetch catalog from {source_url}",
        )

    # Sync docs alongside catalog refresh
    from app.config.docs_sync import sync_docs_on_refresh

    await sync_docs_on_refresh()

    return CatalogUploadResponse(
        success=True,
        version=remote.version,
        prompt_count=len(remote.prompts),
        message=f"Catalog refreshed: {len(remote.prompts)} prompts (v{remote.version})",
    )
