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

from app.presentation.api.dependencies import (
    CurrentUser,
    get_db_session,
    get_db_session_rls,
    get_effective_org_id,
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
from app.domain.provider.models import PackageSource
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
    default: Optional[str] = None
    required: bool = False


class MarketplacePrompt(BaseModel):
    """A prompt entry from the marketplace catalog."""

    id: str  # slug, e.g. "shs-news-narrator"
    display_name: str
    version: str
    tier: str  # "basic" | "plus"
    category: str
    description: str
    author: str
    chunks: List[CatalogChunk] = []
    variables: List[CatalogVariable] = []


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
    """Fetch prompts catalog from basic catalog (+ plus catalog if token), merge."""
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
    source_url = cat_config.build_url(cat_config.REPO_BASIC, cat_config.PROMPTS)

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
    tier: Optional[str] = Query(None, description="Filter by tier: basic, plus"),
    current_user: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
    catalog_repo: SQLAlchemyMarketplaceCatalogRepository = Depends(
        get_marketplace_catalog_repository
    ),
) -> PromptsCatalogResponse:
    """
    Browse the prompts marketplace catalog.

    Super-admin: sees the full catalog (everything available to install),
    loaded from the database-cached catalog with auto-refresh from remote.

    Org admin: sees only prompts the super-admin has platform-installed,
    read directly from package_versions - no catalog load, no remote fetch.
    """
    is_super_admin = current_user.get("role") == "super_admin"

    if not is_super_admin:
        return await _org_admin_catalog_prompts(db, category, tier)

    return await _super_admin_catalog_prompts(db, catalog_repo, category, tier)


async def _org_admin_catalog_prompts(
    db: AsyncSession,
    category: Optional[str],
    tier: Optional[str],
) -> PromptsCatalogResponse:
    """Org-admin catalog: read platform-installed prompts from package_versions."""
    active = await PackageVersionService.list_active(db, PackageType.PROMPT)

    if not active:
        return PromptsCatalogResponse(
            version="1.0.0",
            prompts=[],
            filter_options={"tier": ["basic", "plus"], "category": []},
        )

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
                tier=entry.get("tier", "basic"),
                category=entry.get("category", ""),
                description=entry.get("description", ""),
                author=entry.get("author", ""),
                chunks=[CatalogChunk(**c) for c in chunks_data],
                variables=[CatalogVariable(**v) for v in variables_data],
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
            "tier": tiers if tiers else ["basic", "plus"],
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

    # Auto-refresh if stale (basic catalog only - no token on GET)
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
            filter_options={"tier": ["basic", "plus"], "category": []},
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
            "tier": tiers if tiers else ["basic", "plus"],
            "category": categories,
        },
        warnings=warnings,
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
        org_id = get_effective_org_id(None, current_user)

        all_prompts = await prompt_repo.list_by_organization(
            organization_id=uuid.UUID(org_id),
            enabled_only=False,
        )

        for p in all_prompts:
            if p.source == PromptSource.MARKETPLACE and p.marketplace_slug:
                installed_ids.append(p.marketplace_slug)
                installed_prompts.append(
                    InstalledPromptInfo(
                        marketplace_id=p.marketplace_slug,
                        prompt_id=str(p.id),
                        name=p.name,
                        category=p.category,
                    )
                )

    return InstalledPromptsResponse(
        installed_ids=installed_ids,
        installed_prompts=installed_prompts,
    )


@router.post("/install/{prompt_slug}", response_model=InstallResponse)
async def install_prompt(
    prompt_slug: str,
    current_user: CurrentUser = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session_rls),
    db: AsyncSession = Depends(get_db_session),
    prompt_repo: PromptRepository = Depends(get_prompt_repository),
    secret_repo: OrganizationSecretRepository = Depends(
        get_organization_secret_repository
    ),
    catalog_repo: SQLAlchemyMarketplaceCatalogRepository = Depends(
        get_marketplace_catalog_repository
    ),
) -> InstallResponse:
    """
    Install a prompt from the marketplace catalog.

    Super-admin: looks up the catalog entry and records the install in
    package_versions (no download needed - prompts are inline).

    Org admin: copies a platform-installed prompt into their organization
    directly from package_versions - no catalog lookup, no secret_repo.

    Idempotent - if already installed, returns already_installed: true.
    """
    is_super_admin = current_user.get("role") == "super_admin"
    org_id = get_effective_org_id(None, current_user)

    if not is_super_admin:
        return await _org_copy_prompt(
            prompt_slug,
            org_id,
            db,
            prompt_repo,
            current_user,
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
    if entry.tier == "plus":
        token = await get_entitlement_token(org_id, secret_repo)
        if not token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="ENTITLEMENT_TOKEN not configured. Add it via Settings > Secrets.",
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
        source=PackageSource.MARKETPLACE,
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


async def _org_copy_prompt(
    prompt_slug: str,
    org_id: str,
    db: AsyncSession,
    prompt_repo: PromptRepository,
    current_user: CurrentUser,
) -> InstallResponse:
    """Org admin copy: create org prompt from package_versions data.

    Reads everything from the platform-installed package version - no catalog
    lookup, no secret_repo needed.
    """
    # Look up platform-installed package version
    platform_pv = await PackageVersionService.get_active_by_slug(
        db,
        PackageType.PROMPT,
        prompt_slug,
    )
    if not platform_pv:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Prompt not available. Ask your administrator to install it first.",
        )

    # Idempotent check - also handles re-install of soft-deleted prompts
    existing = await prompt_repo.get_by_marketplace_slug(
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

    # Read all data from package_versions - no catalog needed
    catalog_entry = platform_pv.json_content.get("catalog_entry", {})
    chunks_data = platform_pv.json_content.get("chunks", [])
    variables_data = platform_pv.json_content.get("variables", [])

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
    new_prompt = Prompt.create(
        organization_id=uuid.UUID(org_id),
        name=display_name,
        description=catalog_entry.get("description", ""),
        category=catalog_entry.get("category", ""),
        chunks=chunks,
        variables=variables,
        source=PromptSource.MARKETPLACE,
        marketplace_slug=prompt_slug,
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


@router.post("/uninstall/{prompt_slug}", status_code=status.HTTP_200_OK)
async def uninstall_prompt(
    prompt_slug: str,
    current_user: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
    prompt_repo: PromptRepository = Depends(get_prompt_repository),
) -> Dict[str, Any]:
    """
    Uninstall a marketplace prompt.

    Super-admin: removes from platform (package_versions). Org copies are
    unaffected since they are independent copies.

    Org admin: soft-deletes the prompt copy from their organization.
    """
    org_id = get_effective_org_id(None, current_user)
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

        # Super-admin removing a custom prompt from the marketplace catalog
        try:
            source_id = uuid.UUID(prompt_slug)
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
    existing = await prompt_repo.get_by_marketplace_slug(
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


@router.get("/custom-catalog", response_model=PromptsCatalogResponse)
async def get_custom_catalog(
    category: Optional[str] = Query(None, description="Filter by category"),
    current_user: CurrentUser = Depends(require_admin),
    prompt_repo: PromptRepository = Depends(get_prompt_repository),
) -> PromptsCatalogResponse:
    """
    Browse custom prompts created by the super admin.

    Returns super_admin prompts formatted as marketplace catalog entries
    so org admins can install them alongside marketplace prompts.
    """
    custom_prompts = await prompt_repo.list_by_source(PromptSource.SUPER_ADMIN)

    if category:
        custom_prompts = [p for p in custom_prompts if p.category == category]

    # Convert domain prompts to marketplace catalog format
    catalog_entries = [
        MarketplacePrompt(
            id=str(p.id),
            display_name=p.name,
            version="1.0.0",
            tier="basic",
            category=p.category,
            description=p.description or "",
            author="Super Admin",
            chunks=[
                CatalogChunk(
                    text=c.text, variable=c.variable, order=c.order, role=c.role
                )
                for c in p.chunks
            ],
            variables=[
                CatalogVariable(
                    name=v.name,
                    label=v.label,
                    type=v.type,
                    options=v.options,
                    default=v.default,
                    required=v.required,
                )
                for v in p.variables
            ],
        )
        for p in custom_prompts
    ]

    all_categories = sorted({p.category for p in custom_prompts})

    return PromptsCatalogResponse(
        version="1.0.0",
        prompts=catalog_entries,
        filter_options={
            "tier": ["basic"],
            "category": all_categories,
        },
    )


@router.post("/install-custom/{prompt_id}", response_model=InstallResponse)
async def install_custom_prompt(
    prompt_id: str,
    current_user: CurrentUser = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session_rls),
    prompt_repo: PromptRepository = Depends(get_prompt_repository),
) -> InstallResponse:
    """
    Install a super-admin custom prompt into the current organization.

    Copies the prompt data. Idempotent - uses the source prompt ID as
    the marketplace_slug to prevent duplicates.
    """
    org_id = get_effective_org_id(None, current_user)

    # Look up the source prompt
    source_prompt = await prompt_repo.get_by_id(uuid.UUID(prompt_id))
    if not source_prompt or source_prompt.source != PromptSource.SUPER_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Custom prompt '{prompt_id}' not found",
        )

    # Idempotent check - use source prompt ID as marketplace_slug
    existing = await prompt_repo.get_by_marketplace_slug(
        slug=prompt_id,
        organization_id=uuid.UUID(org_id),
    )
    if existing:
        if existing.source == PromptSource.UNINSTALLED:
            await prompt_repo.reactivate_marketplace(existing.id)
            await PackageVersionService.reactivate(
                session, PackageType.PROMPT, prompt_id
            )
            logger.info(
                f"Re-installed custom prompt '{prompt_id}' "
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

    # Copy prompt to the org
    new_prompt = Prompt.create(
        organization_id=uuid.UUID(org_id),
        name=source_prompt.name,
        description=source_prompt.description,
        category=source_prompt.category,
        chunks=list(source_prompt.chunks),
        variables=list(source_prompt.variables),
        source=PromptSource.MARKETPLACE,
        marketplace_slug=prompt_id,
    )

    saved = await prompt_repo.create(new_prompt)

    # Record package version snapshot
    pv_json_content = {
        "catalog_entry": {
            "id": prompt_id,
            "display_name": source_prompt.name,
            "version": "1.0.0",
            "tier": "basic",
            "category": source_prompt.category,
            "description": source_prompt.description or "",
            "author": "Super Admin",
        },
        "chunks": [
            {"text": c.text, "variable": c.variable, "order": c.order, "role": c.role}
            for c in source_prompt.chunks
        ],
        "variables": [
            {
                "name": v.name,
                "label": v.label,
                "type": v.type,
                "options": v.options,
                "default": v.default,
                "required": v.required,
            }
            for v in source_prompt.variables
        ],
        "local_prompt_id": str(saved.id),
    }
    pv_source_hash = PackageVersionService.compute_source_hash(pv_json_content)
    await PackageVersionService.record_version(
        session=session,
        package_type=PackageType.PROMPT,
        slug=prompt_id,
        version="1.0.0",
        json_content=pv_json_content,
        source_hash=pv_source_hash,
        created_by=uuid.UUID(current_user["id"]),
        source=PackageSource.SUPER_ADMIN,
    )

    logger.info(
        f"Installed custom prompt '{prompt_id}' as '{saved.name}' "
        f"(id={saved.id}) for org {org_id}"
    )

    return InstallResponse(
        success=True,
        prompt_id=str(saved.id),
        prompt_name=saved.name,
        message="Prompt installed successfully",
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
    Re-fetch the prompts catalog from basic catalog (+ plus catalog if token) and store in database.
    """
    org_id = current_user["org_id"]
    if not org_id:
        raise HTTPException(status_code=400, detail="User has no organization")
    token = await get_entitlement_token(org_id, secret_repo)

    remote = await refresh_catalog_from_remote(catalog_repo, token=token)
    if not remote:
        source_url = cat_config.build_url(cat_config.REPO_BASIC, cat_config.PROMPTS)
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
