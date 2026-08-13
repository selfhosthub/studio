# api/app/presentation/api/comfyui_marketplace.py

"""
API endpoints for the ComfyUI workflows marketplace.

ComfyUI workflows are installable ComfyUI API-format workflow definitions.
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

from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import select

from app.application.services.audit_service import AuditService
from app.config.sources import DEFAULT_TIER, VALID_TIERS
from app.application.services.catalog_merge_service import (
    merge_comfyui_with_marketplace,
)
from app.domain.audit.models import (
    AuditAction,
    AuditActorType,
    AuditCategory,
    ResourceType,
)
from app.domain.common.value_objects import Visibility
from app.infrastructure.persistence.models import (
    ComfyUIWorkflowModel,
    OrganizationModel,
    ProviderServiceModel,
)
from app.presentation.api.dependencies import (
    CurrentUser,
    get_audit_service,
    get_db_session,
    get_marketplace_catalog_repository,
    get_provider_repository,
    require_admin,
    require_super_admin,
    validate_safe_package_name,
)
from app.application.services.versioned_installer import VersionConflictError
from app.application.services.comfyui_service_builder import (
    rebuild_comfyui_services,
)
from app.infrastructure.comfyui_workflow_installer import ComfyUIWorkflowInstaller
from app.domain.provider.repository import ProviderRepository
from app.domain.provider.models import CatalogType, PackageType
from app.infrastructure.repositories.marketplace_catalog_repository import (
    SQLAlchemyMarketplaceCatalogRepository,
)
from app.infrastructure.services.package_version_service import PackageVersionService
from app.config import catalog as cat_config
from app.config.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ComfyUI Marketplace"])


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class MarketplaceComfyUI(BaseModel):
    """A ComfyUI workflow in the marketplace catalog."""

    id: str
    display_name: str
    version: str
    tier: str  # "community" | "plus"
    category: str
    description: str
    requires: List[str] = []
    author: str
    download_url: Optional[str] = None
    path: Optional[str] = None
    status: Optional[str] = None
    # Catalog-reference vs super-org-managed (visibility merge).
    origin: str = "catalog-reference"
    visibility: Optional[str] = None
    # Computed fields
    requirements_met: bool = True
    missing_packages: List[str] = []


class ComfyUICatalogResponse(BaseModel):
    """Response for GET /catalog."""

    version: str
    comfyui: List[MarketplaceComfyUI]
    filter_options: Dict[str, List[str]]
    warnings: List[str] = []


class ComfyUIDetailResponse(MarketplaceComfyUI):
    """Response for GET /catalog/{namespace}/{slug}."""

    workflow: Optional[dict] = None
    installed: bool = False


class RemoteComfyUIEntry(BaseModel):
    """A ComfyUI workflow entry from the remote/local catalog JSON."""

    id: str
    display_name: str
    version: str
    tier: str
    category: str
    description: str
    requires: List[str] = []
    author: str
    download_url: Optional[str] = None
    path: Optional[str] = None
    status: Optional[str] = None


class RemoteComfyUICatalog(BaseModel):
    """Raw catalog shape from remote / local JSON file."""

    version: str
    comfyui: List[RemoteComfyUIEntry] = []


class InstallResponse(BaseModel):
    """Response from install endpoint."""

    success: bool
    workflow_id: Optional[str] = None
    workflow_name: Optional[str] = None
    message: str
    missing_packages: List[str] = []
    already_installed: bool = False


class InstalledComfyUIInfo(BaseModel):
    """Info about an installed marketplace ComfyUI workflow."""

    marketplace_id: str
    workflow_id: str  # Local DB UUID
    name: str


class InstalledComfyUIResponse(BaseModel):
    """Response for GET /installed."""

    installed_ids: List[str]
    installed_workflows: List[InstalledComfyUIInfo] = []


class CatalogUploadResponse(BaseModel):
    """Response from catalog upload."""

    success: bool
    version: str
    workflow_count: int
    message: str


# ---------------------------------------------------------------------------
# Catalog loading helpers
# ---------------------------------------------------------------------------


async def fetch_remote_comfyui_catalog() -> Optional[RemoteComfyUICatalog]:
    """Fetch ComfyUI catalog from the community catalog source."""
    data = await cat_config.fetch_and_merge(cat_config.COMFYUI, "comfyui", token=None)
    if data:
        return RemoteComfyUICatalog(**data)
    return None


async def get_catalog_from_database(
    catalog_repo: SQLAlchemyMarketplaceCatalogRepository,
) -> Optional[RemoteComfyUICatalog]:
    """Get the active ComfyUI catalog from the database."""
    catalog = await catalog_repo.get_active(CatalogType.COMFYUI)
    if catalog and catalog.catalog_data:
        try:
            return RemoteComfyUICatalog(**catalog.catalog_data)
        except Exception as e:
            logger.warning(f"Failed to parse ComfyUI catalog data from database: {e}")
            return None
    return None


async def refresh_catalog_from_remote(
    catalog_repo: SQLAlchemyMarketplaceCatalogRepository,
) -> Optional[RemoteComfyUICatalog]:
    """Fetch ComfyUI catalog from remote and store in database."""
    remote_catalog = await fetch_remote_comfyui_catalog()
    source_url = cat_config.build_url(cat_config.REPO_COMMUNITY, cat_config.COMFYUI)

    if remote_catalog:
        await catalog_repo.upsert_active(
            catalog_type=CatalogType.COMFYUI,
            catalog_data=remote_catalog.model_dump(),
            source_url=source_url,
        )
        logger.info(
            f"Refreshed ComfyUI catalog from {source_url}: "
            f"v{remote_catalog.version}, {len(remote_catalog.comfyui)} entries"
        )
        return remote_catalog
    else:
        await catalog_repo.set_fetch_error(
            catalog_type=CatalogType.COMFYUI,
            error_message=f"Failed to fetch catalog from {source_url}",
        )
        return None


async def get_installed_package_ids(provider_repo: ProviderRepository) -> set[str]:
    """Get set of installed package IDs from database."""
    db_providers = await provider_repo.list_all(
        skip=0, limit=settings.DEFAULT_FETCH_LIMIT
    )
    return {p.slug for p in db_providers}


def _load_local_workflow(entry: RemoteComfyUIEntry) -> Optional[Dict[str, Any]]:
    """Load the workflow package JSON from the local source tree, if present."""
    from app.config.sources import (
        is_remote,
        local_path as _local_path,
        source_for_tier,
    )

    source = source_for_tier(entry.tier)
    if is_remote(source) or not entry.path:
        return None
    local_comfyui_path = _local_path(source, "/app", entry.path)
    if not local_comfyui_path.exists():
        return None
    try:
        return json.loads(local_comfyui_path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning(
            f"Failed to load local ComfyUI workflow from {local_comfyui_path}: {e}"
        )
        return None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


async def _caller_is_staging(db: AsyncSession, org_id: uuid.UUID) -> bool:
    """Caller org's staging-tenant flag (organizations is not RLS-protected)."""
    row = (
        await db.execute(
            select(OrganizationModel.is_staging).where(
                OrganizationModel.id == org_id
            )
        )
    ).scalar_one_or_none()
    return bool(row)


class ComfyUIVisibilityUpdate(BaseModel):
    visibility: Visibility


@router.post("/{namespace}/{slug}/visibility")
async def set_comfyui_visibility(
    payload: ComfyUIVisibilityUpdate,
    namespace: str,
    slug: str,
    user: CurrentUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db_session),
    audit_service: AuditService = Depends(get_audit_service),
) -> Dict[str, Any]:
    """super_admin-only: set a ComfyUI catalog package's cross-org visibility
    (private | staging | public). Applies to every version row of the slug
    (the package is published as a whole). Audited."""
    full_slug = f"{namespace}/{slug}"
    rows = (
        (
            await db.execute(
                select(ComfyUIWorkflowModel).where(
                    ComfyUIWorkflowModel.slug == full_slug
                )
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"ComfyUI workflow {full_slug} not found",
        )

    old_visibility = rows[0].visibility
    for row in rows:
        row.visibility = payload.visibility

    # Visibility gates the workflow enum, so the flip must rebuild services.
    updated_services = await rebuild_comfyui_services(db)
    await db.commit()

    actor_org = user.get("org_id")
    await audit_service.log_event(
        actor_id=uuid.UUID(str(user.get("id"))),
        actor_type=AuditActorType(user.get("role") or "user"),
        action=AuditAction.UPDATE,
        resource_type=ResourceType.PACKAGE,
        resource_id=rows[0].id,
        resource_name=rows[0].name,
        organization_id=uuid.UUID(actor_org) if actor_org else None,
        category=AuditCategory.CONFIGURATION,
        changes={
            "visibility": {
                "old": getattr(old_visibility, "value", str(old_visibility)),
                "new": payload.visibility.value,
            }
        },
    )
    return {
        "success": True,
        "slug": full_slug,
        "visibility": payload.visibility.value,
        "updated_versions": len(rows),
        "services_rebuilt": sorted(updated_services),
    }


@router.get("/catalog", response_model=ComfyUICatalogResponse)
async def get_comfyui_catalog(
    category: Optional[str] = Query(None, description="Filter by category"),
    tier: Optional[str] = Query(None, description="Filter by tier: community, plus"),
    include_private: bool = Query(
        False,
        description="Include private managed rows (unpublished uploads); the custom view",
    ),
    current_user: CurrentUser = Depends(require_super_admin),
    provider_repo: ProviderRepository = Depends(get_provider_repository),
    db: AsyncSession = Depends(get_db_session),
    catalog_repo: SQLAlchemyMarketplaceCatalogRepository = Depends(
        get_marketplace_catalog_repository
    ),
) -> ComfyUICatalogResponse:
    """
    Browse the ComfyUI workflows marketplace catalog.

    Returns the remote/catalog-reference ComfyUI workflows plus the super-org's
    managed (visibility-published) ones the caller is entitled to see.
    Admin and super_admin only.
    """
    installed_ids = await get_installed_package_ids(provider_repo)
    warnings: List[str] = []

    # Auto-refresh if stale
    db_catalog_record = await catalog_repo.get_active(CatalogType.COMFYUI)
    if cat_config.is_stale(db_catalog_record.fetched_at if db_catalog_record else None):
        try:
            result = await refresh_catalog_from_remote(catalog_repo)
            if result is None:
                warnings.append(
                    "ComfyUI catalog refresh returned no data. Using cached catalog."
                )
        except Exception as e:
            logger.warning(f"Auto-refresh of ComfyUI catalog failed: {e}")
            warnings.append(
                f"ComfyUI catalog auto-refresh failed: {e}. Using cached data."
            )

    catalog = await get_catalog_from_database(catalog_repo)

    workflows: List[MarketplaceComfyUI] = []
    categories_set: set[str] = set()
    tiers_set: set[str] = set()

    if not catalog:
        warnings.append("No catalog data available. Run seed or refresh catalog.")
    else:
        for wf in catalog.comfyui:
            missing = [req for req in wf.requires if req not in installed_ids]
            requirements_met = len(missing) == 0

            categories_set.add(wf.category)
            tiers_set.add(wf.tier)

            workflows.append(
                MarketplaceComfyUI(
                    id=wf.id,
                    display_name=wf.display_name,
                    version=wf.version,
                    tier=wf.tier,
                    category=wf.category,
                    description=wf.description,
                    requires=wf.requires,
                    author=wf.author,
                    download_url=wf.download_url,
                    path=wf.path,
                    status=wf.status,
                    requirements_met=requirements_met,
                    missing_packages=missing,
                )
            )

    # Fold in the super-org's managed (visibility-published) comfyui workflows
    # the caller is entitled to see. ComfyUI is a global catalog (not
    # org-scoped), so the visibility filter alone is the entitlement gate.
    seen_ids = {w.id for w in workflows}
    caller_org_id = uuid.UUID(current_user["org_id"])
    caller_staging = await _caller_is_staging(db, caller_org_id)
    merged_comfyui = await merge_comfyui_with_marketplace(
        db, caller_is_staging=caller_staging, include_private=include_private
    )
    for entry in merged_comfyui:
        if entry.id in seen_ids:
            continue
        seen_ids.add(entry.id)
        categories_set.add(entry.category or "")
        workflows.append(
            MarketplaceComfyUI(
                id=entry.id,
                display_name=entry.name,
                version=entry.version or "1.0.0",
                tier=DEFAULT_TIER,
                category=entry.category or "",
                description=entry.description or "",
                author="",
                origin="managed",
                visibility=entry.visibility.value if entry.visibility else None,
                requirements_met=True,
            )
        )

    if tier:
        workflows = [w for w in workflows if w.tier == tier]
    if category:
        workflows = [w for w in workflows if w.category == category]

    filter_options = {
        "tier": sorted(list(tiers_set)) if tiers_set else list(VALID_TIERS),
        "category": sorted(list(categories_set)) if categories_set else [],
    }

    return ComfyUICatalogResponse(
        version=catalog.version if catalog else "1.0.0",
        comfyui=workflows,
        filter_options=filter_options,
        warnings=warnings,
    )


@router.get("/catalog/{namespace}/{slug}", response_model=ComfyUIDetailResponse)
async def get_comfyui_detail(
    namespace: str,
    slug: str,
    current_user: CurrentUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db_session),
    provider_repo: ProviderRepository = Depends(get_provider_repository),
    catalog_repo: SQLAlchemyMarketplaceCatalogRepository = Depends(
        get_marketplace_catalog_repository
    ),
) -> ComfyUIDetailResponse:
    """Full pre-install detail for one catalog ComfyUI workflow (super-admin).

    The catalog list ships metadata only; the full package JSON (metadata
    envelope + graph) is loaded here on demand. If it cannot be fetched,
    the metadata is returned with workflow=None.
    """
    comfyui_id = f"{namespace}/{slug}"

    # Managed rows (uploads, visibility-published packages) live in the DB,
    # not the catalog JSON; resolve them first so their detail modal works.
    from app.application.services.catalog_merge_service import _semver_key

    managed_rows = (
        (
            await db.execute(
                select(ComfyUIWorkflowModel).where(
                    ComfyUIWorkflowModel.slug == comfyui_id,
                    ComfyUIWorkflowModel.is_active.is_(True),
                )
            )
        )
        .scalars()
        .all()
    )
    managed = max(managed_rows, key=lambda r: _semver_key(r.version), default=None)
    if managed is not None:
        active = await PackageVersionService.list_active(db, PackageType.COMFYUI)
        return ComfyUIDetailResponse(
            id=comfyui_id,
            display_name=managed.name,
            version=managed.version,
            tier=DEFAULT_TIER,
            category=managed.category or "",
            description=managed.description or "",
            author=managed.author or "",
            origin="managed",
            visibility=managed.visibility.value if managed.visibility else None,
            requirements_met=True,
            installed=any(pv.slug == comfyui_id for pv in active),
            workflow=managed.json_content,
        )

    catalog = await get_catalog_from_database(catalog_repo)
    if not catalog:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="ComfyUI marketplace catalog not available",
        )

    entry = next((wf for wf in catalog.comfyui if wf.id == comfyui_id), None)
    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"ComfyUI workflow '{comfyui_id}' not found in catalog",
        )

    installed_ids = await get_installed_package_ids(provider_repo)
    missing = [req for req in entry.requires if req not in installed_ids]

    active = await PackageVersionService.list_active(db, PackageType.COMFYUI)
    installed = any(pv.slug == comfyui_id for pv in active)

    workflow_data: Optional[Dict[str, Any]] = None
    if entry.path:
        workflow_data = _load_local_workflow(entry)

    if workflow_data is None and entry.download_url:
        try:
            async with httpx.AsyncClient(
                timeout=settings.MARKETPLACE_DOWNLOAD_TIMEOUT
            ) as client:
                response = await client.get(entry.download_url)
                response.raise_for_status()
                workflow_data = response.json()
        except Exception as e:
            logger.warning(
                f"Failed to download ComfyUI workflow from {entry.download_url}: {e}"
            )

    return ComfyUIDetailResponse(
        id=entry.id,
        display_name=entry.display_name,
        version=entry.version,
        tier=entry.tier,
        category=entry.category,
        description=entry.description,
        requires=entry.requires,
        author=entry.author,
        download_url=entry.download_url,
        path=entry.path,
        status=entry.status,
        requirements_met=len(missing) == 0,
        missing_packages=missing,
        workflow=workflow_data,
        installed=installed,
    )


@router.get("/installed", response_model=InstalledComfyUIResponse)
async def get_installed_comfyui(
    current_user: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
) -> InstalledComfyUIResponse:
    """
    List ComfyUI workflows installed from the marketplace.

    Reads from package_versions table (DB-authoritative).
    """
    active = await PackageVersionService.list_active(db, PackageType.COMFYUI)

    installed_ids: List[str] = []
    installed_workflows: List[InstalledComfyUIInfo] = []

    for pv in active:
        installed_ids.append(pv.slug)
        catalog_entry = pv.json_content.get("catalog_entry", {})
        installed_workflows.append(
            InstalledComfyUIInfo(
                marketplace_id=pv.slug,
                workflow_id=pv.json_content.get("local_workflow_id", ""),
                name=catalog_entry.get("display_name", pv.slug),
            )
        )

    return InstalledComfyUIResponse(
        installed_ids=installed_ids,
        installed_workflows=installed_workflows,
    )


async def _service_conformance_violation(
    db: AsyncSession, workflow_data: Dict[str, Any]
) -> Optional[str]:
    """None when the package fits its service's parameter contract.

    The service is a parameter contract (ruling 2026-08-03): a joining
    package may declare a subset of the contract's parameters, must cover the
    contract's required ones, and may not invent its own. Declared parameter
    types must agree with the contract's, and package options must stay
    inside a contract enum. Packages without a service block never join a
    service and are exempt.
    """
    service_id = (workflow_data.get("service") or {}).get("id")
    params = workflow_data.get("parameters") or {}
    if not service_id:
        return None
    rows = (
        (
            await db.execute(
                select(ProviderServiceModel).where(
                    ProviderServiceModel.service_id.like(f"%.{service_id}")
                )
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        return None
    if len(rows) > 1:
        candidates = ", ".join(r.service_id for r in rows)
        logger.warning(
            f"service id '{service_id}' matches multiple services "
            f"({candidates}); using '{rows[0].service_id}'"
        )
    contract = rows[0].parameter_schema or {}
    contract_properties = contract.get("properties") or {}
    contract_props = set(contract_properties.keys()) - {"package"}
    extra = sorted(set(params.keys()) - contract_props)
    if extra:
        return (
            f"parameters not in service '{service_id}' contract: {', '.join(extra)}. "
            "A different parameter set is a new service: fork the provider."
        )
    missing_required = sorted(
        r for r in contract.get("required", []) if r != "package" and r not in params
    )
    if missing_required:
        return (
            f"service '{service_id}' requires parameters the package does not "
            f"declare: {', '.join(missing_required)}"
        )
    # (package type, contract type) pairs accepted as narrowings.
    narrowings = {("enum", "string"), ("float", "number"), ("integer", "number")}
    for name, spec in params.items():
        if not isinstance(spec, dict):
            continue
        contract_prop = contract_properties.get(name) or {}
        pkg_type = spec.get("type")
        contract_type = contract_prop.get("type")
        if (
            pkg_type
            and contract_type
            and pkg_type != contract_type
            and (pkg_type, contract_type) not in narrowings
        ):
            return (
                f"parameter '{name}' type '{pkg_type}' does not match service "
                f"'{service_id}' contract type '{contract_type}'"
            )
        contract_enum = contract_prop.get("enum")
        if contract_enum:
            option_values = [
                o.get("value") if isinstance(o, dict) else o
                for o in spec.get("options") or []
            ]
            outside = [v for v in option_values if v not in contract_enum]
            if outside:
                return (
                    f"parameter '{name}' options not in service '{service_id}' "
                    f"contract enum: {', '.join(str(v) for v in outside)}"
                )
    return None


@router.post(
    "/upload",
    response_model=InstallResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload and install a ComfyUI package",
    description="Upload a single-file ComfyUI package (graph + manifest). "
    "Schema-validated; a bare graph is rejected. Lands private; publish via "
    "the visibility endpoint.",
)
async def upload_comfyui_package(
    file: UploadFile = File(..., description="Single-file ComfyUI package JSON"),
    current_user: CurrentUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db_session),
) -> InstallResponse:
    """Upload a ComfyUI package: same installer as marketplace install, the
    file is the payload. Re-uploading an existing slug@version with different
    content is a 409; bump the version instead."""
    if not file.filename or not file.filename.endswith(".json"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be a .json file",
        )
    try:
        raw = await file.read()
        workflow_data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Uploaded file is not valid JSON (line {e.lineno}, column {e.colno}).",
        )
    if not isinstance(workflow_data, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file must be a JSON object (single-file ComfyUI package).",
        )

    slug = workflow_data.get("slug")
    if not slug:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Package must contain a 'slug' field (a bare graph is not a package).",
        )
    validate_safe_package_name(slug)
    user_uuid = uuid.UUID(current_user["id"])

    violation = await _service_conformance_violation(db, workflow_data)
    if violation:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Package does not conform: {violation}",
        )

    installer = ComfyUIWorkflowInstaller()
    try:
        install_result = await installer.install_from_data(
            workflow_data, db, user_uuid, on_conflict="error"
        )
    except VersionConflictError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"'{e.slug}@{e.version}' already exists with different content; "
            "bump the package version.",
        )
    if not install_result.success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid ComfyUI package: {install_result.error}",
        )

    workflow_name = workflow_data.get("name", slug)
    pv_json_content = {
        "catalog_entry": {
            "id": slug,
            "display_name": workflow_name,
            "version": install_result.version,
            "tier": DEFAULT_TIER,
            "category": workflow_data.get("category"),
            "description": workflow_data.get("description"),
            "requires": [],
            "author": workflow_data.get("author"),
            "uploaded": True,
        },
        "workflow_data": workflow_data,
        "local_workflow_id": str(install_result.workflow_id),
    }
    await PackageVersionService.record_version(
        session=db,
        package_type=PackageType.COMFYUI,
        slug=slug,
        version=install_result.version,
        json_content=pv_json_content,
        source_hash=PackageVersionService.compute_source_hash(pv_json_content),
        created_by=user_uuid,
        allow_reserved=True,
    )

    updated_services = await rebuild_comfyui_services(db)
    await db.commit()

    logger.info(
        f"Uploaded ComfyUI package '{slug}@{install_result.version}' "
        f"(id={install_result.workflow_id}) by user {current_user.get('username')}; "
        f"services rebuilt: {sorted(updated_services)}"
    )
    return InstallResponse(
        success=True,
        workflow_id=str(install_result.workflow_id),
        workflow_name=workflow_name,
        message="ComfyUI package uploaded and installed (private; publish via visibility).",
    )


@router.post("/install/{namespace}/{slug}", response_model=InstallResponse)
async def install_comfyui(
    namespace: str,
    slug: str,
    current_user: CurrentUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db_session),
    provider_repo: ProviderRepository = Depends(get_provider_repository),
    catalog_repo: SQLAlchemyMarketplaceCatalogRepository = Depends(
        get_marketplace_catalog_repository
    ),
) -> InstallResponse:
    """Install a ComfyUI workflow from the marketplace catalog.

    Downloads the ComfyUI workflow JSON and creates a new organization-scope workflow.
    Idempotent - if already installed, returns already_installed: true.
    """
    comfyui_id = f"{namespace}/{slug}"
    user_uuid = uuid.UUID(current_user["id"])

    installed_ids = await get_installed_package_ids(provider_repo)

    catalog = await get_catalog_from_database(catalog_repo)
    if not catalog:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="ComfyUI marketplace catalog not available",
        )

    entry: Optional[RemoteComfyUIEntry] = None
    for wf in catalog.comfyui:
        if wf.id == comfyui_id:
            entry = wf
            break

    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"ComfyUI workflow '{comfyui_id}' not found in catalog",
        )

    # Idempotent check via package_versions
    existing_active = await PackageVersionService.list_active(db, PackageType.COMFYUI)
    for pv in existing_active:
        if pv.slug == comfyui_id:
            return InstallResponse(
                success=True,
                workflow_id=pv.json_content.get("local_workflow_id"),
                workflow_name=entry.display_name,
                message="ComfyUI workflow already installed",
                already_installed=True,
            )

    missing = [req for req in entry.requires if req not in installed_ids]

    if not entry.download_url and not entry.path:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ComfyUI workflow has no download URL or local path",
        )

    # Load workflow data
    workflow_data = None

    if entry.path:
        workflow_data = _load_local_workflow(entry)

    if workflow_data is None and entry.download_url:
        try:
            async with httpx.AsyncClient(
                timeout=settings.MARKETPLACE_DOWNLOAD_TIMEOUT
            ) as client:
                response = await client.get(entry.download_url)
                response.raise_for_status()
                workflow_data = response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authentication failed while downloading ComfyUI workflow.",
                )
            elif e.response.status_code == 404:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="ComfyUI workflow file not found at the specified URL.",
                )
            logger.error(
                f"Failed to download ComfyUI workflow from {entry.download_url}: {e}"
            )
            raise HTTPException(
                status_code=502, detail="Failed to download ComfyUI workflow"
            )
        except Exception as e:
            logger.error(
                f"Failed to download ComfyUI workflow from {entry.download_url}: {e}"
            )
            raise HTTPException(
                status_code=502, detail="Failed to download ComfyUI workflow"
            )

    if workflow_data is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not load ComfyUI workflow from any source",
        )

    # A ComfyUI package is a graph package, not a step workflow: install it
    # into comfyui_workflows (schema-validated) and rebuild the manifest-owned
    # provider services, mirroring the seeder path.
    installer = ComfyUIWorkflowInstaller()
    install_result = await installer.install_from_data(
        workflow_data, db, user_uuid, slug_hint=comfyui_id
    )
    if not install_result.success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid ComfyUI package: {install_result.error}",
        )

    workflow_name = entry.display_name

    # Record package version snapshot
    pv_json_content = {
        "catalog_entry": {
            "id": comfyui_id,
            "display_name": entry.display_name,
            "version": entry.version,
            "tier": entry.tier,
            "category": entry.category,
            "description": entry.description,
            "requires": entry.requires,
            "author": entry.author,
        },
        "workflow_data": workflow_data,
        "local_workflow_id": str(install_result.workflow_id),
    }
    pv_source_hash = PackageVersionService.compute_source_hash(pv_json_content)
    await PackageVersionService.record_version(
        session=db,
        package_type=PackageType.COMFYUI,
        slug=comfyui_id,
        version=install_result.version,
        json_content=pv_json_content,
        source_hash=pv_source_hash,
        created_by=user_uuid,
        allow_reserved=True,
    )

    updated_services = await rebuild_comfyui_services(db)
    await db.commit()

    logger.info(
        f"Installed ComfyUI package '{comfyui_id}' as '{workflow_name}' "
        f"(id={install_result.workflow_id}) by user {current_user.get('username')}; "
        f"services rebuilt: {sorted(updated_services)}"
    )

    return InstallResponse(
        success=True,
        workflow_id=str(install_result.workflow_id),
        workflow_name=workflow_name,
        message="ComfyUI workflow installed successfully"
        + (f" (warning: missing packages: {', '.join(missing)})" if missing else ""),
        missing_packages=missing,
    )


@router.post("/uninstall/{namespace}/{slug}", status_code=status.HTTP_200_OK)
async def uninstall_comfyui(
    namespace: str,
    slug: str,
    current_user: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Uninstall a marketplace ComfyUI workflow.

    Catalog installs soft-delete (the catalog remains their source of truth).
    Uploads hard-delete: nothing backs them, and a tombstone row only causes
    ghost conflicts on a later re-upload.
    """
    comfyui_id = f"{namespace}/{slug}"

    result = await db.execute(
        select(ComfyUIWorkflowModel).where(
            ComfyUIWorkflowModel.slug == comfyui_id,
            ComfyUIWorkflowModel.is_active.is_(True),
        )
    )
    rows = list(result.scalars())
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"ComfyUI workflow '{comfyui_id}' is not installed",
        )

    name = rows[0].name

    # The upload endpoint stamps its ledger entries; that marker decides
    # hard-delete vs soft-delete.
    active_pvs = await PackageVersionService.list_active(db, PackageType.COMFYUI)
    uploaded = any(
        pv.slug == comfyui_id
        and pv.json_content.get("catalog_entry", {}).get("uploaded")
        for pv in active_pvs
    )

    if uploaded:
        for row in rows:
            await db.delete(row)
        await PackageVersionService.hard_delete(db, PackageType.COMFYUI, comfyui_id)
    else:
        for row in rows:
            row.is_active = False
        await PackageVersionService.soft_delete(db, PackageType.COMFYUI, comfyui_id)
    updated_services = await rebuild_comfyui_services(db)
    await db.commit()

    logger.info(
        f"Uninstalled ComfyUI package '{comfyui_id}' "
        f"({'hard-deleted upload' if uploaded else 'soft-deleted'}); "
        f"services rebuilt: {sorted(updated_services)}"
    )
    return {
        "success": True,
        "message": f"ComfyUI workflow '{name}' uninstalled",
    }


@router.post(
    "/catalog/upload",
    response_model=CatalogUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_comfyui_catalog(
    file: UploadFile = File(..., description="comfyui-catalog.json file"),
    _current_user: CurrentUser = Depends(require_super_admin),
    catalog_repo: SQLAlchemyMarketplaceCatalogRepository = Depends(
        get_marketplace_catalog_repository
    ),
) -> CatalogUploadResponse:
    """
    Upload a ComfyUI catalog file. Super admin only.
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
        logger.error(f"Failed to read uploaded ComfyUI catalog file: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to read file",
        )

    try:
        catalog = RemoteComfyUICatalog(**data)
    except Exception as e:
        logger.error(f"Invalid ComfyUI catalog format: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid catalog format",
        )

    # Store in database
    await catalog_repo.upsert_active(
        catalog_type=CatalogType.COMFYUI,
        catalog_data=data,
        source_url=None,  # Manual upload
        source_tag=None,
    )

    entry_count = len(catalog.comfyui)
    logger.info(
        f"Uploaded ComfyUI catalog v{catalog.version} with {entry_count} workflows"
    )

    return CatalogUploadResponse(
        success=True,
        version=catalog.version,
        workflow_count=entry_count,
        message=f"ComfyUI catalog uploaded successfully with {entry_count} workflows",
    )


@router.post("/catalog/refresh", response_model=CatalogUploadResponse)
async def refresh_comfyui_catalog(
    _current_user: CurrentUser = Depends(require_super_admin),
    catalog_repo: SQLAlchemyMarketplaceCatalogRepository = Depends(
        get_marketplace_catalog_repository
    ),
) -> CatalogUploadResponse:
    """
    Re-fetch the ComfyUI catalog from the community catalog and store in database.
    """
    remote = await refresh_catalog_from_remote(catalog_repo)
    if not remote:
        source_url = cat_config.build_url(cat_config.REPO_COMMUNITY, cat_config.COMFYUI)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to fetch catalog from {source_url}",
        )

    entry_count = len(remote.comfyui)

    # Sync docs alongside catalog refresh
    from app.config.docs_sync import sync_docs_on_refresh

    await sync_docs_on_refresh()

    return CatalogUploadResponse(
        success=True,
        version=remote.version,
        workflow_count=entry_count,
        message=f"Catalog refreshed: {entry_count} ComfyUI workflows (v{remote.version})",
    )
