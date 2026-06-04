# api/app/presentation/api/workflows_marketplace.py

"""
API endpoints for the workflows marketplace.

Workflows are installable pipeline definitions (with steps) from the catalog.
The catalog is stored in the database, fetched from remote sources (GitHub) or
uploaded manually.
"""

import json
import logging
import uuid
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.services.catalog_merge_service import merge_with_marketplace
from app.domain.common.json_serialization import deserialize_steps
from app.infrastructure.persistence.models import (
    OrganizationModel,
    WorkflowModel,
    WorkflowVersionModel,
)
from app.presentation.api.dependencies import (
    get_db_session_service,
    CurrentUser,
    get_db_session,
    get_effective_org_id,
    get_marketplace_catalog_repository,
    get_organization_secret_repository,
    get_provider_repository,
    get_workflow_service,
    require_admin,
    require_super_admin,
)
from app.domain.organization_secret.repository import OrganizationSecretRepository
from app.presentation.api.marketplace import get_entitlement_token
from app.application.dtos.workflow_dto import WorkflowCreate
from app.application.services.workflow_service import WorkflowService
from app.domain.provider.repository import ProviderRepository
from app.domain.provider.models import CatalogType, PackageType
from app.infrastructure.repositories.marketplace_catalog_repository import (
    SQLAlchemyMarketplaceCatalogRepository,
)
from app.infrastructure.services.package_version_service import PackageVersionService
from app.domain.common.value_objects import PromptSource
from app.infrastructure.persistence.models import PromptModel
from app.config import catalog as cat_config
from app.config.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Workflows Marketplace"])


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class MarketplaceWorkflow(BaseModel):
    """A workflow in the marketplace catalog."""

    id: str
    display_name: str
    version: str
    tier: str  # "basic" | "plus"
    category: str
    description: str
    requires: List[str] = []
    requires_prompts: List[str] = []
    author: str
    download_url: Optional[str] = None
    path: Optional[str] = None
    # Catalog-reference vs super-org-managed. "managed" entries come from the
    # cross-org merge; visibility is meaningful only for those.
    origin: str = "catalog-reference"
    visibility: Optional[str] = None
    # Computed fields
    requirements_met: bool = True
    missing_packages: List[str] = []
    missing_prompts: List[str] = []


class WorkflowsCatalogResponse(BaseModel):
    """Response for GET /catalog."""

    version: str
    workflows: List[MarketplaceWorkflow]
    filter_options: Dict[str, List[str]]
    warnings: List[str] = []


class RemoteWorkflowEntry(BaseModel):
    """A workflow entry from the remote/local catalog JSON."""

    id: str
    display_name: str
    version: str
    tier: str
    category: str
    description: str
    requires: List[str] = []
    prompts: List[Dict[str, Any]] = []
    author: str
    download_url: Optional[str] = None
    path: Optional[str] = None


class RemoteWorkflowsCatalog(BaseModel):
    """Raw catalog shape from remote / local JSON file."""

    version: str
    workflows: List[RemoteWorkflowEntry] = []


class InstallResponse(BaseModel):
    """Response from install endpoint."""

    success: bool
    workflow_id: Optional[str] = None
    workflow_name: Optional[str] = None
    message: str
    missing_packages: List[str] = []
    missing_prompts: List[str] = []
    already_installed: bool = False


class InstalledWorkflowInfo(BaseModel):
    """Info about an installed marketplace workflow."""

    marketplace_id: str
    workflow_id: str  # Local DB UUID
    name: str


class InstalledWorkflowsResponse(BaseModel):
    """Response for GET /installed."""

    installed_ids: List[str]
    installed_workflows: List[InstalledWorkflowInfo] = []


class CatalogUploadResponse(BaseModel):
    """Response from catalog upload."""

    success: bool
    version: str
    workflow_count: int
    message: str


# ---------------------------------------------------------------------------
# Catalog loading helpers
# ---------------------------------------------------------------------------


async def fetch_remote_workflows_catalog(
    token: Optional[str] = None,
) -> Optional[RemoteWorkflowsCatalog]:
    """Fetch workflows catalog from basic catalog (+ plus catalog if token), merge."""
    data = await cat_config.fetch_and_merge(
        cat_config.WORKFLOWS, "workflows", token=token
    )
    if data:
        return RemoteWorkflowsCatalog(**data)
    return None


async def get_catalog_from_database(
    catalog_repo: SQLAlchemyMarketplaceCatalogRepository,
) -> Optional[RemoteWorkflowsCatalog]:
    """Get the active workflows catalog from the database."""
    catalog = await catalog_repo.get_active(CatalogType.WORKFLOWS)
    if catalog and catalog.catalog_data:
        try:
            return RemoteWorkflowsCatalog(**catalog.catalog_data)
        except Exception as e:
            logger.warning(f"Failed to parse workflows catalog data from database: {e}")
            return None
    return None


async def refresh_catalog_from_remote(
    catalog_repo: SQLAlchemyMarketplaceCatalogRepository,
    token: Optional[str] = None,
) -> Optional[RemoteWorkflowsCatalog]:
    """Fetch workflows catalog from remote and store in database."""
    remote_catalog = await fetch_remote_workflows_catalog(token=token)
    source_url = cat_config.build_url(cat_config.REPO_BASIC, cat_config.WORKFLOWS)

    if remote_catalog:
        await catalog_repo.upsert_active(
            catalog_type=CatalogType.WORKFLOWS,
            catalog_data=remote_catalog.model_dump(),
            source_url=source_url,
        )
        logger.info(
            f"Refreshed workflows catalog from {source_url}: "
            f"v{remote_catalog.version}, {len(remote_catalog.workflows)} entries"
        )
        return remote_catalog
    else:
        await catalog_repo.set_fetch_error(
            catalog_type=CatalogType.WORKFLOWS,
            error_message=f"Failed to fetch catalog from {source_url}",
        )
        return None


async def get_installed_package_ids(provider_repo: ProviderRepository) -> set[str]:
    """Get set of installed package IDs from database."""
    db_providers = await provider_repo.list_all(
        skip=0, limit=settings.DEFAULT_FETCH_LIMIT
    )
    return {p.slug for p in db_providers}


def extract_prompt_slugs(entry_or_data: Dict[str, Any]) -> List[str]:
    """Pull `slug` (formerly `marketplace_slug`) values out of the catalog `prompts` array."""
    prompts = entry_or_data.get("prompts", [])
    if not isinstance(prompts, list):
        return []
    out: List[str] = []
    for p in prompts:
        if isinstance(p, dict):
            slug = p.get("slug") or p.get("marketplace_slug")
            if isinstance(slug, str) and slug:
                out.append(slug)
    return out


async def get_installed_prompt_slugs_for_org(
    db: AsyncSession, org_id: uuid.UUID
) -> set[str]:
    """Namespaced slugs of marketplace-sourced prompts active in the given org."""
    await db.execute(text("SET LOCAL app.is_service_account = 'true'"))
    rows = await db.execute(
        select(PromptModel.slug).where(
            PromptModel.organization_id == org_id,
            PromptModel.source == PromptSource.MARKETPLACE,
        )
    )
    return {row[0] for row in rows.all() if row[0]}


async def get_platform_installed_prompt_slugs(db: AsyncSession) -> set[str]:
    """Marketplace slugs of prompts the super-admin has platform-installed via package_versions."""
    active = await PackageVersionService.list_active(db, PackageType.PROMPT)
    return {pv.slug for pv in active}


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/catalog", response_model=WorkflowsCatalogResponse)
async def get_workflows_catalog(
    category: Optional[str] = Query(None, description="Filter by category"),
    tier: Optional[str] = Query(None, description="Filter by tier: basic, plus"),
    current_user: CurrentUser = Depends(require_admin),
    provider_repo: ProviderRepository = Depends(get_provider_repository),
    db: AsyncSession = Depends(get_db_session),
    bypass_db: AsyncSession = Depends(get_db_session_service),
    catalog_repo: SQLAlchemyMarketplaceCatalogRepository = Depends(
        get_marketplace_catalog_repository
    ),
) -> WorkflowsCatalogResponse:
    """
    Browse the workflows marketplace catalog.

    Super-admin: sees the full catalog (everything available to install),
    loaded from the database-cached catalog with auto-refresh from remote.

    Org admin: sees only workflows the super-admin has platform-installed,
    read directly from package_versions - no catalog load, no remote fetch.
    """
    is_super_admin = current_user.get("role") == "super_admin"

    if not is_super_admin:
        org_id = uuid.UUID(get_effective_org_id(None, current_user))
        return await _org_admin_catalog_workflows(
            db, bypass_db, provider_repo, category, tier, org_id
        )

    return await _super_admin_catalog_workflows(
        db,
        catalog_repo,
        provider_repo,
        category,
        tier,
    )


async def _resolve_system_org_and_staging(
    db: AsyncSession, caller_org_id: uuid.UUID
) -> tuple[Optional[uuid.UUID], bool]:
    """Return (system_org_id, caller_is_staging). The organizations table
    is not RLS-protected, so the plain session reads it. The system org is the
    one flagged is_system in its settings."""
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


async def _org_admin_catalog_workflows(
    db: AsyncSession,
    bypass_db: AsyncSession,
    provider_repo: ProviderRepository,
    category: Optional[str],
    tier: Optional[str],
    org_id: uuid.UUID,
) -> WorkflowsCatalogResponse:
    """Org-admin catalog: platform-installed workflows (package_versions) plus
    the super-org's managed workflows the caller is entitled to see (the
    cross-org merge)."""
    active = await PackageVersionService.list_active(db, PackageType.WORKFLOW)

    installed_ids = await get_installed_package_ids(provider_repo)
    installed_prompt_slugs = await get_installed_prompt_slugs_for_org(db, org_id)

    workflows: List[MarketplaceWorkflow] = []
    categories_set: set[str] = set()
    tiers_set: set[str] = set()

    for pv in active:
        entry = pv.json_content.get("catalog_entry", {})
        workflow_data = pv.json_content.get("workflow_data", {})
        requires = entry.get("requires", [])
        missing = [req for req in requires if req not in installed_ids]

        prompt_slugs = extract_prompt_slugs(workflow_data) or extract_prompt_slugs(
            entry
        )
        missing_prompts = [s for s in prompt_slugs if s not in installed_prompt_slugs]

        wf_tier = entry.get("tier", "basic")
        wf_category = entry.get("category", "")
        categories_set.add(wf_category)
        tiers_set.add(wf_tier)

        workflows.append(
            MarketplaceWorkflow(
                id=pv.slug,
                display_name=entry.get("display_name", pv.slug),
                version=entry.get("version", pv.version),
                tier=wf_tier,
                category=wf_category,
                description=entry.get("description", ""),
                requires=requires,
                requires_prompts=prompt_slugs,
                author=entry.get("author", ""),
                requirements_met=len(missing) == 0 and len(missing_prompts) == 0,
                missing_packages=missing,
                missing_prompts=missing_prompts,
            )
        )

    # Fold in the super-org's managed workflows the caller is entitled to see.
    # The cross-org read and the visibility filter live entirely inside
    # merge_with_marketplace - this is the only catalog call site that touches
    # the service-bypass session.
    seen_ids = {w.id for w in workflows}
    system_org_id, caller_is_staging = await _resolve_system_org_and_staging(db, org_id)
    if system_org_id is not None:
        for entry in await merge_with_marketplace(
            bypass_db,
            system_org_id=system_org_id,
            caller_org_id=org_id,
            caller_is_staging=caller_is_staging,
        ):
            if entry.id in seen_ids:
                continue
            seen_ids.add(entry.id)
            categories_set.add(entry.category or "")
            workflows.append(
                MarketplaceWorkflow(
                    id=entry.id,
                    display_name=entry.name,
                    version=entry.version or "1.0.0",
                    tier="basic",
                    category=entry.category or "",
                    description=entry.description or "",
                    author="",
                    origin="managed",
                    visibility=(entry.visibility.value if entry.visibility else None),
                    requirements_met=True,
                )
            )

    if tier:
        workflows = [w for w in workflows if w.tier == tier]
    if category:
        workflows = [w for w in workflows if w.category == category]

    return WorkflowsCatalogResponse(
        version=active[0].version if active else "1.0.0",
        workflows=workflows,
        filter_options={
            "tier": sorted(tiers_set) if tiers_set else ["basic", "plus"],
            "category": sorted(categories_set) if categories_set else [],
        },
    )


async def _super_admin_catalog_workflows(
    db: AsyncSession,
    catalog_repo: SQLAlchemyMarketplaceCatalogRepository,
    provider_repo: ProviderRepository,
    category: Optional[str],
    tier: Optional[str],
) -> WorkflowsCatalogResponse:
    """Super-admin catalog: full catalog from database, auto-refresh if stale."""
    installed_ids = await get_installed_package_ids(provider_repo)
    installed_prompt_slugs = await get_platform_installed_prompt_slugs(db)
    warnings: List[str] = []

    # Auto-refresh if stale (basic catalog only - no token on GET)
    db_catalog_record = await catalog_repo.get_active(CatalogType.WORKFLOWS)
    if cat_config.is_stale(db_catalog_record.fetched_at if db_catalog_record else None):
        try:
            result = await refresh_catalog_from_remote(catalog_repo)
            if result is None:
                warnings.append(
                    "Workflows catalog refresh returned no data. Using cached catalog."
                )
        except Exception as e:
            logger.warning(f"Auto-refresh of workflows catalog failed: {e}")
            warnings.append(
                f"Workflows catalog auto-refresh failed: {e}. Using cached data."
            )

    catalog = await get_catalog_from_database(catalog_repo)

    if not catalog:
        warnings.append("No catalog data available. Run seed or refresh catalog.")
        return WorkflowsCatalogResponse(
            version="1.0.0",
            workflows=[],
            filter_options={"tier": ["basic", "plus"], "category": []},
            warnings=warnings,
        )

    workflows: List[MarketplaceWorkflow] = []
    categories_set: set[str] = set()
    tiers_set: set[str] = set()

    for wf in catalog.workflows:
        missing = [req for req in wf.requires if req not in installed_ids]
        prompt_slugs = extract_prompt_slugs(wf.model_dump())
        missing_prompts = [s for s in prompt_slugs if s not in installed_prompt_slugs]
        requirements_met = len(missing) == 0 and len(missing_prompts) == 0

        categories_set.add(wf.category)
        tiers_set.add(wf.tier)

        workflows.append(
            MarketplaceWorkflow(
                id=wf.id,
                display_name=wf.display_name,
                version=wf.version,
                tier=wf.tier,
                category=wf.category,
                description=wf.description,
                requires=wf.requires,
                requires_prompts=prompt_slugs,
                author=wf.author,
                download_url=wf.download_url,
                path=wf.path,
                requirements_met=requirements_met,
                missing_packages=missing,
                missing_prompts=missing_prompts,
            )
        )

    # Apply filters
    if tier:
        workflows = [w for w in workflows if w.tier == tier]
    if category:
        workflows = [w for w in workflows if w.category == category]

    filter_options = {
        "tier": sorted(list(tiers_set)) if tiers_set else ["basic", "plus"],
        "category": sorted(list(categories_set)) if categories_set else [],
    }

    return WorkflowsCatalogResponse(
        version=catalog.version,
        workflows=workflows,
        filter_options=filter_options,
        warnings=warnings,
    )


@router.get("/installed", response_model=InstalledWorkflowsResponse)
async def get_installed_workflows(
    current_user: CurrentUser = Depends(require_admin),
    service: WorkflowService = Depends(get_workflow_service),
    db: AsyncSession = Depends(get_db_session),
) -> InstalledWorkflowsResponse:
    """
    List marketplace workflow IDs that have been installed.

    Super-admin: returns platform-installed workflows (from package_versions).
    Org admin: returns workflows copied into their organization.
    """
    is_super_admin = current_user.get("role") == "super_admin"

    installed_ids: List[str] = []
    installed_workflows: List[InstalledWorkflowInfo] = []

    if is_super_admin:
        # Platform view: what's installed on this server
        active = await PackageVersionService.list_active(db, PackageType.WORKFLOW)
        for pv in active:
            catalog_entry = pv.json_content.get("catalog_entry", {})
            installed_ids.append(pv.slug)
            installed_workflows.append(
                InstalledWorkflowInfo(
                    marketplace_id=pv.slug,
                    workflow_id=pv.slug,
                    name=catalog_entry.get("display_name", pv.slug),
                )
            )
    else:
        # Org view: what's copied into this org
        effective_org_id = get_effective_org_id(None, current_user)
        org_uuid = uuid.UUID(effective_org_id)

        workflows = await service.workflow_repository.list_organization_workflows(
            org_uuid, skip=0, limit=settings.DEFAULT_FETCH_LIMIT
        )

        for wf in workflows:
            if wf.client_metadata:
                marketplace_id = wf.client_metadata.get("marketplace_id")
                if marketplace_id:
                    installed_ids.append(marketplace_id)
                    installed_workflows.append(
                        InstalledWorkflowInfo(
                            marketplace_id=marketplace_id,
                            workflow_id=str(wf.id),
                            name=wf.name,
                        )
                    )

    return InstalledWorkflowsResponse(
        installed_ids=installed_ids,
        installed_workflows=installed_workflows,
    )


@router.post("/install/{namespace}/{slug}", response_model=InstallResponse)
async def install_workflow(
    namespace: str,
    slug: str,
    force: bool = False,
    current_user: CurrentUser = Depends(require_admin),
    service: WorkflowService = Depends(get_workflow_service),
    db: AsyncSession = Depends(get_db_session),
    bypass_db: AsyncSession = Depends(get_db_session_service),
    provider_repo: ProviderRepository = Depends(get_provider_repository),
    secret_repo: OrganizationSecretRepository = Depends(
        get_organization_secret_repository
    ),
    catalog_repo: SQLAlchemyMarketplaceCatalogRepository = Depends(
        get_marketplace_catalog_repository
    ),
) -> InstallResponse:
    """Install a workflow from the marketplace catalog.

    Super-admin: looks up the catalog entry, downloads the workflow JSON,
    and records the install in package_versions.

    Org admin: copies a platform-installed workflow into their organization
    directly from package_versions - no catalog lookup, no download.

    Idempotent by default - if already installed, returns already_installed: true.
    Pass force=true to make an additional copy with a '(copy N)' display-name
    suffix so users can keep the original alongside an edited copy.
    """
    workflow_id = f"{namespace}/{slug}"
    is_super_admin = current_user.get("role") == "super_admin"
    effective_org_id = get_effective_org_id(None, current_user)
    user_uuid = uuid.UUID(current_user["id"])

    if not is_super_admin:
        return await _org_copy_workflow(
            workflow_id,
            effective_org_id,
            user_uuid,
            db,
            bypass_db,
            service,
            provider_repo,
            current_user,
            force=force,
        )

    # Super-admin path: catalog lookup + download
    catalog = await get_catalog_from_database(catalog_repo)
    if not catalog:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Marketplace catalog not available",
        )

    entry: Optional[RemoteWorkflowEntry] = None
    for wf in catalog.workflows:
        if wf.id == workflow_id:
            entry = wf
            break

    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow '{workflow_id}' not found in catalog",
        )

    # Token check for plus-tier workflows
    if entry.tier == "plus":
        token = await get_entitlement_token(effective_org_id, secret_repo)
        if not token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="ENTITLEMENT_TOKEN not configured. Add it via Settings > Secrets.",
            )

    return await _platform_install_workflow(
        workflow_id,
        entry,
        effective_org_id,
        user_uuid,
        db,
        secret_repo,
        current_user,
    )


async def _platform_install_workflow(
    workflow_id: str,
    entry: "RemoteWorkflowEntry",
    effective_org_id: str,
    user_uuid: uuid.UUID,
    db: AsyncSession,
    secret_repo: OrganizationSecretRepository,
    current_user: CurrentUser,
) -> InstallResponse:
    """Super-admin platform install: record in package_versions only."""
    # Idempotent check against package_versions
    active = await PackageVersionService.list_active(db, PackageType.WORKFLOW)
    for pv in active:
        if pv.slug == workflow_id:
            return InstallResponse(
                success=True,
                workflow_id=workflow_id,
                workflow_name=entry.display_name,
                message="Workflow already installed on platform",
                already_installed=True,
            )

    # Load workflow data
    workflow_data = await _load_workflow_data(
        entry,
        effective_org_id,
        secret_repo,
    )

    # Record platform install in package_versions
    pv_json_content = {
        "catalog_entry": {
            "id": workflow_id,
            "display_name": entry.display_name,
            "version": entry.version,
            "tier": entry.tier,
            "category": entry.category,
            "description": entry.description,
            "requires": entry.requires,
            "author": entry.author,
        },
        "workflow_data": workflow_data,
    }
    pv_source_hash = PackageVersionService.compute_source_hash(pv_json_content)
    await PackageVersionService.record_version(
        session=db,
        package_type=PackageType.WORKFLOW,
        slug=workflow_id,
        version=entry.version,
        json_content=pv_json_content,
        source_hash=pv_source_hash,
        created_by=user_uuid,
        allow_reserved=True,
    )

    logger.info(
        f"Platform-installed workflow '{workflow_id}' "
        f"by {current_user.get('username')}"
    )

    return InstallResponse(
        success=True,
        workflow_id=workflow_id,
        workflow_name=entry.display_name,
        message="Workflow installed to platform",
    )


async def _load_managed_workflow_source(
    db: AsyncSession,
    bypass_db: AsyncSession,
    workflow_id: str,
    org_uuid: uuid.UUID,
) -> Optional[tuple[Dict[str, Any], Dict[str, Any], str]]:
    """Entitlement-checked load of a published super-org (managed) workflow,
    returned in the same (catalog_entry, workflow_data, version) shape the
    package_versions copy path consumes.

    Security: entitlement is RE-CHECKED here through merge_with_marketplace -
    the slug must be in the caller's entitled managed set, so a private (or a
    staging slug the caller isn't a staging organization for) is not installable even
    if its slug is guessed. Returns None when not entitled / not found.

    Steps live in the latest workflow_versions row (not WorkflowModel.steps);
    both reads use the RLS-bypassing session since the source is the super-org's.
    """
    system_org_id, caller_is_staging = await _resolve_system_org_and_staging(
        db, org_uuid
    )
    if system_org_id is None:
        return None

    entitled = await merge_with_marketplace(
        bypass_db,
        system_org_id=system_org_id,
        caller_org_id=org_uuid,
        caller_is_staging=caller_is_staging,
    )
    match = next((e for e in entitled if e.id == workflow_id), None)
    if match is None:
        return None

    wf_id = uuid.UUID(match.install_ref)
    wf_row = (
        await bypass_db.execute(select(WorkflowModel).where(WorkflowModel.id == wf_id))
    ).scalar_one_or_none()
    if wf_row is None:
        return None

    latest = (
        await bypass_db.execute(
            select(WorkflowVersionModel)
            .where(WorkflowVersionModel.workflow_id == wf_id)
            .order_by(WorkflowVersionModel.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    # Version rows store serialized domain steps (enum NAMEs); re-dump them to
    # the portable value form the copy path expects (same shape as export).
    step_objs = deserialize_steps((latest.steps if latest else None) or {})
    steps = {sid: sc.model_dump(mode="json") for sid, sc in step_objs.items()}
    trigger_schema = latest.trigger_input_schema if latest else None
    version = latest.version if latest else "1.0.0"
    trigger_type = (
        wf_row.trigger_type.value
        if hasattr(wf_row.trigger_type, "value")
        else wf_row.trigger_type
    )

    catalog_entry: Dict[str, Any] = {
        "display_name": wf_row.name,
        "description": wf_row.description or "",
        "version": version,
        "author": "",
        "tier": "basic",
        "category": "",
        "requires": [],
    }
    workflow_data: Dict[str, Any] = {
        "steps": steps,
        "trigger_type": trigger_type,
        "trigger_input_schema": trigger_schema,
        "description": wf_row.description or "",
        "client_metadata": wf_row.client_metadata or {},
    }
    return catalog_entry, workflow_data, version


async def _org_copy_workflow(
    workflow_id: str,
    effective_org_id: str,
    user_uuid: uuid.UUID,
    db: AsyncSession,
    bypass_db: AsyncSession,
    service: WorkflowService,
    provider_repo: ProviderRepository,
    current_user: CurrentUser,
    force: bool = False,
) -> InstallResponse:
    """Org admin copy: create org-scoped workflow from package_versions data.

    Reads everything from the platform-installed package version - no catalog
    lookup, no remote download, no secret_repo needed.

    When force=True, bypasses idempotency and creates an additional copy with
    a '(copy N)' display-name suffix so the user can keep the original
    alongside an edited copy.
    """
    org_uuid = uuid.UUID(effective_org_id)

    # Source resolution: a platform-installed package_versions entry, or - when
    # none exists - a published super-org managed workflow (entitlement
    # re-checked inside the loader). Both produce the same
    # (catalog_entry, workflow_data, version) shape.
    platform_pv = await PackageVersionService.get_active_by_slug(
        db,
        PackageType.WORKFLOW,
        workflow_id,
    )
    if platform_pv:
        source_catalog_entry = platform_pv.json_content.get("catalog_entry", {})
        source_workflow_data = platform_pv.json_content.get("workflow_data", {})
        source_version = platform_pv.version
    else:
        managed = await _load_managed_workflow_source(
            db, bypass_db, workflow_id, org_uuid
        )
        if managed is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Workflow not available. Ask your administrator to install it first.",
            )
        source_catalog_entry, source_workflow_data, source_version = managed

    # Tally existing copies of this marketplace workflow in the org.
    # Without force, this drives the idempotent return. With force, it gives
    # the next '(copy N)' index for display-name disambiguation.
    existing_workflows = await service.workflow_repository.list_organization_workflows(
        org_uuid, skip=0, limit=settings.DEFAULT_FETCH_LIMIT
    )
    existing_copies = [
        w
        for w in existing_workflows
        if w.client_metadata and w.client_metadata.get("marketplace_id") == workflow_id
    ]
    if existing_copies and not force:
        existing = existing_copies[0]
        return InstallResponse(
            success=True,
            workflow_id=str(existing.id),
            workflow_name=existing.name,
            message="Workflow already copied to organization",
            already_installed=True,
        )

    # Source data resolved above (package_versions or managed live row).
    catalog_entry = source_catalog_entry
    workflow_data = source_workflow_data
    requires = catalog_entry.get("requires", [])

    # Get installed package IDs for requirement warning
    installed_ids = await get_installed_package_ids(provider_repo)
    missing = [req for req in requires if req not in installed_ids]

    required_prompt_slugs = extract_prompt_slugs(workflow_data) or extract_prompt_slugs(
        catalog_entry
    )
    installed_prompt_slugs = await get_installed_prompt_slugs_for_org(db, org_uuid)
    missing_prompts = [
        s for s in required_prompt_slugs if s not in installed_prompt_slugs
    ]

    # Build slug → UUID map for provider resolution
    db_providers = await provider_repo.list_all(
        skip=0, limit=settings.DEFAULT_FETCH_LIMIT
    )
    slug_to_uuid: Dict[str, str] = {p.slug: str(p.id) for p in db_providers}

    # Build slug → UUID map for prompt resolution
    # Prompts are RLS-protected; elevate to service account for this query
    await db.execute(text("SET LOCAL app.is_service_account = 'true'"))
    prompt_result = await db.execute(
        select(PromptModel.slug, PromptModel.id).where(
            PromptModel.organization_id == org_uuid,
            PromptModel.source != PromptSource.UNINSTALLED,
        )
    )
    prompt_slug_to_uuid: Dict[str, str] = {
        row[0]: str(row[1]) for row in prompt_result.all()
    }

    # Parse steps - move service routing fields from job to step level
    # and resolve provider slugs to UUIDs and prompt slugs to prompt IDs
    steps: Dict[str, Any] = {}
    if "steps" in workflow_data and isinstance(workflow_data["steps"], dict):
        for step_id, step_data in workflow_data["steps"].items():
            try:
                step_data = dict(step_data)
                if "job" in step_data and isinstance(step_data["job"], dict):
                    step_data["job"] = dict(step_data["job"])
                    job = step_data["job"]

                    # Resolve provider_id slug → UUID
                    provider_slug = job.get("provider_id", "")
                    if provider_slug and provider_slug in slug_to_uuid:
                        job["provider_id"] = slug_to_uuid[provider_slug]

                    # Resolve credential_provider_id slug → UUID
                    cred_provider_slug = job.get("credential_provider_id", "")
                    if cred_provider_slug and cred_provider_slug in slug_to_uuid:
                        job["credential_provider_id"] = slug_to_uuid[cred_provider_slug]

                    for field in ("service_type", "provider_id", "service_id"):
                        if field in step_data["job"] and field not in step_data:
                            step_data[field] = step_data["job"].pop(field)
                # Resolve promptSlug → promptId in input_mappings
                input_mappings = step_data.get("input_mappings", {})
                if isinstance(input_mappings, dict):
                    for mapping in input_mappings.values():
                        if not isinstance(mapping, dict):
                            continue
                        prompt_slug = mapping.get("promptSlug")
                        if prompt_slug and prompt_slug in prompt_slug_to_uuid:
                            mapping["promptId"] = prompt_slug_to_uuid[prompt_slug]
                            del mapping["promptSlug"]

                steps[step_id] = step_data
            except Exception as e:
                logger.warning(f"Failed to parse step {step_id}: {e}")

    # Build client_metadata from package_versions data
    merged_metadata = dict(workflow_data.get("client_metadata", {}))
    if "prompts" in workflow_data:
        merged_metadata["prompts"] = workflow_data["prompts"]
    merged_metadata.update(
        {
            "marketplace_id": workflow_id,
            "marketplace_version": catalog_entry.get("version", source_version),
            "marketplace_author": catalog_entry.get("author", ""),
            "marketplace_tier": catalog_entry.get("tier", "basic"),
            "marketplace_category": catalog_entry.get("category", ""),
        }
    )

    # Create the workflow in the org
    workflow_name = catalog_entry.get("display_name", workflow_id)
    if force and existing_copies:
        # First existing copy is "Foo", next forced copy becomes "Foo (copy 2)", etc.
        workflow_name = f"{workflow_name} (copy {len(existing_copies) + 1})"

    command = WorkflowCreate(
        name=workflow_name,
        description=workflow_data.get(
            "description", catalog_entry.get("description", "")
        ),
        organization_id=org_uuid,
        created_by=user_uuid,
        steps=steps,
        trigger_type=workflow_data.get("trigger_type"),
        trigger_input_schema=workflow_data.get("trigger_input_schema"),
        client_metadata=merged_metadata,
        scope="organization",
    )

    try:
        result = await service.create_workflow(command)
    except Exception as e:
        logger.error(f"Failed to copy workflow '{workflow_id}' to org: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to copy workflow to organization",
        )

    logger.info(
        f"Copied workflow '{workflow_id}' as '{workflow_name}' "
        f"(id={result.id}) to org {effective_org_id} "
        f"by {current_user.get('username')}"
    )

    warning_parts: List[str] = []
    if missing:
        warning_parts.append(f"missing providers: {', '.join(missing)}")
    if missing_prompts:
        warning_parts.append(f"missing prompts: {', '.join(missing_prompts)}")
    message = "Workflow copied to organization"
    if warning_parts:
        message += f" (warning: {'; '.join(warning_parts)})"

    return InstallResponse(
        success=True,
        workflow_id=str(result.id),
        workflow_name=workflow_name,
        message=message,
        missing_packages=missing,
        missing_prompts=missing_prompts,
    )


async def _load_workflow_data(
    entry: "RemoteWorkflowEntry",
    effective_org_id: str,
    secret_repo: OrganizationSecretRepository,
) -> Dict[str, Any]:
    """Load workflow JSON from local path or download URL."""
    workflow_data = None

    if not entry.download_url and not entry.path:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Workflow has no download URL or local path",
        )

    # Try local path first - pick the right source based on tier
    if entry.path:
        from app.config.sources import (
            is_remote,
            local_path as _local_path,
            source_for_tier,
        )

        source = source_for_tier(entry.tier)
        if not is_remote(source):
            local_wf_path = _local_path(source, "/app", entry.path)
            if local_wf_path.exists():
                try:
                    workflow_data = json.loads(
                        local_wf_path.read_text(encoding="utf-8")
                    )
                except Exception as e:
                    logger.warning(
                        f"Failed to load local workflow from {local_wf_path}: {e}"
                    )

    # Fall back to download URL
    if workflow_data is None and entry.download_url:
        headers = {}
        if entry.tier == "plus":
            token = await get_entitlement_token(effective_org_id, secret_repo)
            if token:
                headers["Authorization"] = f"token {token}"

        try:
            async with httpx.AsyncClient(
                timeout=settings.MARKETPLACE_DOWNLOAD_TIMEOUT
            ) as client:
                response = await client.get(entry.download_url, headers=headers)
                response.raise_for_status()
                workflow_data = response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authentication failed. Check your ENTITLEMENT_TOKEN.",
                )
            elif e.response.status_code == 404:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Workflow file not found at the specified URL.",
                )
            logger.error(f"Failed to download workflow from {entry.download_url}: {e}")
            raise HTTPException(status_code=502, detail="Failed to download workflow")
        except Exception as e:
            logger.error(f"Failed to download workflow from {entry.download_url}: {e}")
            raise HTTPException(status_code=502, detail="Failed to download workflow")

    if workflow_data is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not load workflow from any source",
        )

    return workflow_data


@router.post("/uninstall/{namespace}/{slug}", status_code=status.HTTP_200_OK)
async def uninstall_workflow(
    namespace: str,
    slug: str,
    current_user: CurrentUser = Depends(require_admin),
    service: WorkflowService = Depends(get_workflow_service),
    db: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Uninstall a marketplace workflow.

    Super-admin: removes from platform (package_versions). Org copies are
    unaffected since they are independent copies.

    Org admin: removes the workflow copy from their organization.
    """
    workflow_id = f"{namespace}/{slug}"
    is_super_admin = current_user.get("role") == "super_admin"

    if is_super_admin:
        # Platform uninstall - remove from package_versions
        active = await PackageVersionService.list_active(db, PackageType.WORKFLOW)
        for pv in active:
            if pv.slug == workflow_id:
                await PackageVersionService.soft_delete(
                    db, PackageType.WORKFLOW, workflow_id
                )
                catalog_entry = pv.json_content.get("catalog_entry", {})
                name = catalog_entry.get("display_name", workflow_id)
                logger.info(
                    f"Platform-uninstalled workflow '{workflow_id}' "
                    f"by {current_user.get('username')}"
                )
                return {
                    "success": True,
                    "message": f"Workflow '{name}' removed from platform",
                }

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow '{workflow_id}' is not installed on the platform",
        )

    # Org uninstall - delete the org's workflow copy
    effective_org_id = get_effective_org_id(None, current_user)
    org_uuid = uuid.UUID(effective_org_id)

    workflows = await service.workflow_repository.list_organization_workflows(
        org_uuid, skip=0, limit=settings.DEFAULT_FETCH_LIMIT
    )

    for wf in workflows:
        if (
            wf.client_metadata
            and wf.client_metadata.get("marketplace_id") == workflow_id
        ):
            await service.workflow_repository.delete(wf.id)
            logger.info(
                f"Removed workflow copy '{workflow_id}' "
                f"(id={wf.id}) from org {effective_org_id}"
            )
            return {"success": True, "message": f"Workflow '{wf.name}' removed"}

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Workflow '{workflow_id}' is not installed in your organization",
    )


@router.post(
    "/catalog/upload",
    response_model=CatalogUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_workflows_catalog(
    file: UploadFile = File(..., description="workflows-catalog.json file"),
    _current_user: CurrentUser = Depends(require_super_admin),
    catalog_repo: SQLAlchemyMarketplaceCatalogRepository = Depends(
        get_marketplace_catalog_repository
    ),
) -> CatalogUploadResponse:
    """
    Upload a workflows catalog file. Super admin only.
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
        logger.error(f"Failed to read uploaded workflows catalog file: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to read file",
        )

    # Validate catalog structure
    try:
        catalog = RemoteWorkflowsCatalog(**data)
    except Exception as e:
        logger.error(f"Invalid workflows catalog format: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid catalog format",
        )

    # Store in database
    await catalog_repo.upsert_active(
        catalog_type=CatalogType.WORKFLOWS,
        catalog_data=data,
        source_url=None,  # Manual upload
        source_tag=None,
    )

    entry_count = len(catalog.workflows)
    logger.info(
        f"Uploaded workflows catalog v{catalog.version} with {entry_count} workflows"
    )

    return CatalogUploadResponse(
        success=True,
        version=catalog.version,
        workflow_count=entry_count,
        message=f"Workflows catalog uploaded successfully with {entry_count} workflows",
    )


@router.post("/catalog/refresh", response_model=CatalogUploadResponse)
async def refresh_workflows_catalog(
    current_user: CurrentUser = Depends(require_super_admin),
    secret_repo: OrganizationSecretRepository = Depends(
        get_organization_secret_repository
    ),
    catalog_repo: SQLAlchemyMarketplaceCatalogRepository = Depends(
        get_marketplace_catalog_repository
    ),
) -> CatalogUploadResponse:
    """
    Re-fetch the workflows catalog from basic catalog (+ plus catalog if token) and store in database.
    """
    org_id = current_user["org_id"]
    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Organization ID is required",
        )
    token = await get_entitlement_token(org_id, secret_repo)

    remote = await refresh_catalog_from_remote(catalog_repo, token=token)
    if not remote:
        source_url = cat_config.build_url(cat_config.REPO_BASIC, cat_config.WORKFLOWS)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to fetch catalog from {source_url}",
        )

    entry_count = len(remote.workflows)

    # Sync docs alongside catalog refresh
    from app.config.docs_sync import sync_docs_on_refresh

    await sync_docs_on_refresh()

    return CatalogUploadResponse(
        success=True,
        version=remote.version,
        workflow_count=entry_count,
        message=f"Catalog refreshed: {entry_count} workflows (v{remote.version})",
    )
