# api/app/presentation/api/marketplace.py

"""
API endpoints for the provider marketplace.

The marketplace catalog is stored in the database, fetched from remote sources
(GitHub) or uploaded manually. Catalog is merged with installed packages
to determine installation status.
"""

import json
import logging
import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel

from app.config import catalog as cat_config
from app.config.settings import settings

from app.domain.provider.models import CatalogType, ProviderStatus
from app.domain.provider.repository import ProviderRepository
from app.domain.organization_secret.repository import OrganizationSecretRepository
from app.infrastructure.persistence.models import PackageVersionModel
from app.infrastructure.repositories.marketplace_catalog_repository import (
    SQLAlchemyMarketplaceCatalogRepository,
)
from app.presentation.api.dependencies import (
    CurrentUser,
    get_active_provider_package_versions,
    get_current_user,
    get_marketplace_catalog_repository,
    get_organization_secret_repository,
    get_provider_repository,
    require_super_admin,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Marketplace"])


class PackageTier(str, Enum):
    """Package tier levels."""

    BASIC = "basic"
    PLUS = "plus"


class PackageStatus(str, Enum):
    """Package installation status."""

    INSTALLED = "installed"
    DEACTIVATED = "deactivated"
    AVAILABLE = "available"


class PackageVersion(BaseModel):
    """A version entry for a package (used for version history and rollback)."""

    version: str
    download_url: str
    release_date: Optional[str] = None
    changelog: Optional[str] = None  # Brief description of changes in this version


class MarketplacePackage(BaseModel):
    id: str  # Package name/slug (e.g., "core")
    provider_id: Optional[str] = (
        None  # Provider UUID (for linking to provider detail page)
    )
    display_name: str
    tier: str  # "basic" | "plus"
    category: str
    description: str
    services_preview: List[str]
    requires: List[str] = []
    credential_provider: Optional[str] = None
    status: str  # "installed" | "deactivated" | "available"
    installed: bool = False
    # Remote download fields
    version: Optional[str] = None
    download_url: Optional[str] = None  # URL to download specific version
    latest_url: Optional[str] = None  # URL to download latest version
    path: Optional[str] = None  # Local path for directory-based install
    # Version history and bug reporting
    versions: List[PackageVersion] = []  # Available versions for rollback
    bug_report_url: Optional[str] = None  # URL for reporting bugs
    installed_version: Optional[str] = None  # Currently installed version


class MarketplaceCatalog(BaseModel):
    version: str
    packages: List[MarketplacePackage]
    # Filter options for UI dropdowns
    filter_options: Dict[str, List[str]]
    warnings: List[str] = []


class RemoteCatalogPackage(BaseModel):
    """Package entry from remote catalog (before status is determined)."""

    id: str
    display_name: str
    tier: str
    category: str
    description: str
    services_preview: List[str] = []
    requires: List[str] = []
    credential_provider: Optional[str] = None
    # Remote download fields
    version: Optional[str] = None
    download_url: Optional[str] = None  # URL to download specific version
    latest_url: Optional[str] = None  # URL to download latest version
    path: Optional[str] = (
        None  # Local path relative to the catalog source root (e.g., "core")
    )
    # Version history and bug reporting
    versions: List[PackageVersion] = []  # Available versions for rollback
    bug_report_url: Optional[str] = None  # URL for reporting bugs


class RemoteCatalog(BaseModel):
    version: str
    packages: List[RemoteCatalogPackage]


async def fetch_catalog_from_remote(
    token: Optional[str] = None,
) -> Optional[RemoteCatalog]:
    """Fetch providers catalog from basic catalog (+ plus catalog if token), merge."""
    data = await cat_config.fetch_and_merge(
        cat_config.PROVIDERS, "packages", token=token
    )
    if data:
        return RemoteCatalog(**data)
    return None


def get_catalog_from_local_file(
    catalog_type: CatalogType = CatalogType.PROVIDERS,
) -> Optional[RemoteCatalog]:
    """Get catalog from local file on disk (fallback for when remote + DB are empty)."""
    from app.config.sources import COMMUNITY_SOURCE, is_remote, local_path

    if is_remote(COMMUNITY_SOURCE):
        return None

    catalog_files = {
        CatalogType.PROVIDERS: cat_config.PROVIDERS,
    }
    filename = catalog_files.get(catalog_type)
    if not filename:
        return None

    catalog_path = local_path(COMMUNITY_SOURCE, "/app", filename)
    if not catalog_path.exists():
        return None

    try:
        with open(catalog_path) as f:
            data = json.load(f)
        return RemoteCatalog(**data)
    except Exception as e:
        logger.warning(f"Failed to read local catalog from {catalog_path}: {e}")
        return None


async def get_catalog_from_database(
    catalog_repo: SQLAlchemyMarketplaceCatalogRepository,
    catalog_type: CatalogType = CatalogType.PROVIDERS,
) -> Optional[RemoteCatalog]:
    """Get the active catalog from the database.

    The catalog is populated via /catalog/upload (seeder) or /catalog/refresh (remote).
    The database is authoritative.
    """
    catalog = await catalog_repo.get_active(catalog_type)

    if catalog and catalog.catalog_data:
        try:
            return RemoteCatalog(**catalog.catalog_data)
        except Exception as e:
            logger.warning(f"Failed to parse catalog data from database: {e}")
            return None
    return None


async def refresh_catalog_from_remote(
    catalog_repo: SQLAlchemyMarketplaceCatalogRepository,
    catalog_type: CatalogType = CatalogType.PROVIDERS,
    token: Optional[str] = None,
) -> Optional[RemoteCatalog]:
    """Fetch catalog from basic catalog (+ plus catalog if token) and store in database."""
    remote_catalog = await fetch_catalog_from_remote(token=token)
    source_url = cat_config.build_url(cat_config.REPO_BASIC, cat_config.PROVIDERS)

    if remote_catalog:
        # Don't overwrite a good DB catalog with an empty remote response
        existing = await catalog_repo.get_active(catalog_type)
        existing_count = 0
        if existing and existing.catalog_data:
            existing_count = len(existing.catalog_data.get("packages", []))

        if len(remote_catalog.packages) == 0 and existing_count > 0:
            logger.info(
                f"Remote {catalog_type.value} catalog returned 0 packages, "
                f"keeping existing catalog with {existing_count} packages"
            )
            return None

        await catalog_repo.upsert_active(
            catalog_type=catalog_type,
            catalog_data=remote_catalog.model_dump(),
            source_url=source_url,
        )
        logger.info(
            f"Refreshed {catalog_type.value} catalog from {source_url}: "
            f"v{remote_catalog.version}, {len(remote_catalog.packages)} packages"
        )
        return remote_catalog
    else:
        await catalog_repo.set_fetch_error(
            catalog_type=catalog_type,
            error_message=f"Failed to fetch catalog from {source_url}",
        )
        return None


@router.get("/catalog", response_model=MarketplaceCatalog)
async def get_catalog(
    status: Optional[str] = Query(
        None, description="Filter by status: installed, available"
    ),
    tier: Optional[str] = Query(None, description="Filter by tier: basic, plus"),
    category: Optional[str] = Query(None, description="Filter by category"),
    provider_repo: ProviderRepository = Depends(get_provider_repository),
    catalog_repo: SQLAlchemyMarketplaceCatalogRepository = Depends(
        get_marketplace_catalog_repository
    ),
    active_provider_pvs: list[PackageVersionModel] = Depends(
        get_active_provider_package_versions
    ),
    _current_user: CurrentUser = Depends(get_current_user),
) -> MarketplaceCatalog:
    """
    Get the marketplace catalog.

    Fetches available packages from database catalog,
    then merges with installed packages to determine status.

    Filter parameters:
    - status: installed | available
    - tier: basic | plus
    - category: core, ai, etc.
    """
    all_packages: Dict[str, MarketplacePackage] = {}
    categories_set: set[str] = set()
    warnings: List[str] = []

    # Auto-refresh if stale (only basic catalog - no token on GET)
    db_catalog_record = await catalog_repo.get_active(CatalogType.PROVIDERS)
    if cat_config.is_stale(db_catalog_record.fetched_at if db_catalog_record else None):
        try:
            result = await refresh_catalog_from_remote(
                catalog_repo, CatalogType.PROVIDERS
            )
            if result is None:
                warnings.append(
                    "Catalog refresh returned no data. Using cached catalog."
                )
        except Exception as e:
            logger.warning(f"Auto-refresh of providers catalog failed: {e}")
            warnings.append(f"Catalog auto-refresh failed: {e}. Using cached data.")

    # Build a lookup map of provider slug -> provider info from database
    # The database is the source of truth for installed providers
    db_providers = await provider_repo.list_all(
        skip=0, limit=settings.DEFAULT_FETCH_LIMIT, status=ProviderStatus.ACTIVE
    )
    slug_to_uuid: Dict[str, str] = {p.slug: str(p.id) for p in db_providers}

    # Installed packages are those in the database
    installed_ids = set(slug_to_uuid.keys())

    # Also find deactivated (INACTIVE) providers for UI status distinction
    inactive_providers = await provider_repo.list_all(
        skip=0, limit=settings.DEFAULT_FETCH_LIMIT, status=ProviderStatus.INACTIVE
    )
    deactivated_ids = {p.slug for p in inactive_providers}
    deactivated_uuid: Dict[str, str] = {p.slug: str(p.id) for p in inactive_providers}

    # 1. Get catalog from database
    remote_catalog = await get_catalog_from_database(
        catalog_repo, CatalogType.PROVIDERS
    )

    # 2. Add packages from catalog
    if remote_catalog:
        for pkg in remote_catalog.packages:
            is_installed = pkg.id in installed_ids
            categories_set.add(pkg.category)

            pkg_status = (
                "installed"
                if is_installed
                else "deactivated" if pkg.id in deactivated_ids else "available"
            )
            pkg_provider_id = slug_to_uuid.get(pkg.id) or deactivated_uuid.get(pkg.id)

            all_packages[pkg.id] = MarketplacePackage(
                id=pkg.id,
                provider_id=pkg_provider_id,
                display_name=pkg.display_name,
                tier=pkg.tier,
                category=pkg.category,
                description=pkg.description,
                services_preview=pkg.services_preview,
                requires=pkg.requires,
                credential_provider=pkg.credential_provider,
                status=pkg_status,
                installed=is_installed,
                version=pkg.version,
                download_url=pkg.download_url,
                latest_url=pkg.latest_url,
                path=pkg.path,
                versions=pkg.versions,
                bug_report_url=pkg.bug_report_url,
            )

    # 3. Add/update with installed packages from database (in case they're not in catalog)
    for provider in db_providers:
        pkg_id = provider.slug
        # tier/category: prefer catalog (refreshable) over client_metadata (install-time snapshot)
        metadata = provider.client_metadata or {}
        catalog_pkg = all_packages.get(pkg_id)
        pkg_tier = (catalog_pkg.tier if catalog_pkg else None) or metadata.get(
            "tier", "basic"
        )
        pkg_category = (catalog_pkg.category if catalog_pkg else None) or metadata.get(
            "category", "custom"
        )
        categories_set.add(pkg_category)

        # Get the installed version from the version column
        installed_ver = provider.version or metadata.get("package_version", "1.0.0")

        # Always mark installed packages as installed (override catalog status)
        all_packages[pkg_id] = MarketplacePackage(
            id=pkg_id,
            provider_id=str(provider.id),
            display_name=provider.name,
            tier=pkg_tier,
            category=pkg_category,
            description=provider.description or "",
            services_preview=metadata.get("services_preview", []),
            requires=metadata.get("requires", []),
            credential_provider=metadata.get("credential_provider"),
            status="installed",
            installed=True,
            version=(
                catalog_pkg.version if catalog_pkg else installed_ver
            ),  # Latest available version
            installed_version=installed_ver,  # Currently installed version
            # Preserve catalog fields for reinstall after uninstall
            path=catalog_pkg.path if catalog_pkg else None,
            download_url=catalog_pkg.download_url if catalog_pkg else None,
            latest_url=catalog_pkg.latest_url if catalog_pkg else None,
            versions=catalog_pkg.versions if catalog_pkg else [],
            bug_report_url=catalog_pkg.bug_report_url if catalog_pkg else None,
        )

    # 4. Add packages from package_versions not already in catalog or DB providers
    # This catches packages installed from local path or URL that aren't in the marketplace catalog
    for pv in active_provider_pvs:
        pkg_slug = pv.slug
        if pkg_slug in all_packages:
            continue  # Already in catalog or DB providers

        # Snapshot is the unified provider file content directly,
        # not wrapped under {manifest, provider, adapter_config} keys.
        provider_data = pv.json_content
        is_installed = pkg_slug in installed_ids
        pkg_category = provider_data.get("category", "custom")
        categories_set.add(pkg_category)

        pv_status = (
            "installed"
            if is_installed
            else "deactivated" if pkg_slug in deactivated_ids else "available"
        )
        pv_provider_id = slug_to_uuid.get(pkg_slug) or deactivated_uuid.get(pkg_slug)

        all_packages[pkg_slug] = MarketplacePackage(
            id=pkg_slug,
            provider_id=pv_provider_id,
            display_name=provider_data.get("name", pkg_slug),
            tier=provider_data.get("tier", "basic"),
            category=pkg_category,
            description=provider_data.get("description", ""),
            services_preview=provider_data.get("services_preview", []),
            requires=provider_data.get("requires", []),
            credential_provider=provider_data.get("credential_provider"),
            status=pv_status,
            installed=is_installed,
            path=pkg_slug,
        )

    # Convert to list
    packages_list = list(all_packages.values())

    # Apply filters
    if status:
        packages_list = [p for p in packages_list if p.status == status]
    if tier:
        packages_list = [p for p in packages_list if p.tier == tier]
    if category:
        packages_list = [p for p in packages_list if p.category == category]

    # Build filter options for UI dropdowns
    filter_options = {
        "status": [s.value for s in PackageStatus],
        "tier": [t.value for t in PackageTier],
        "category": sorted(list(categories_set)) if categories_set else [],
    }

    # Get catalog version from database
    db_catalog = await catalog_repo.get_active(CatalogType.PROVIDERS)
    catalog_version = db_catalog.version if db_catalog else "1.0.0"

    return MarketplaceCatalog(
        version=catalog_version or "1.0.0",
        packages=packages_list,
        filter_options=filter_options,
        warnings=warnings,
    )


@router.get("/packages/{package_id}", response_model=MarketplacePackage)
async def get_package(
    package_id: str,
    provider_repo: ProviderRepository = Depends(get_provider_repository),
    catalog_repo: SQLAlchemyMarketplaceCatalogRepository = Depends(
        get_marketplace_catalog_repository
    ),
    _current_user: CurrentUser = Depends(get_current_user),
) -> MarketplacePackage:
    """
    Get details for a specific package.

    First checks installed packages in database, then falls back to catalog.
    """
    # Check installed packages in database first
    db_providers = await provider_repo.list_all(
        skip=0, limit=settings.DEFAULT_FETCH_LIMIT, status=ProviderStatus.ACTIVE
    )
    provider = next((p for p in db_providers if p.slug == package_id), None)

    if provider:
        # Check catalog for download URLs
        catalog = await get_catalog_from_database(catalog_repo, CatalogType.PROVIDERS)

        catalog_pkg = None
        if catalog:
            for pkg in catalog.packages:
                if pkg.id == package_id:
                    catalog_pkg = pkg
                    break

        # tier/category: prefer catalog (refreshable) over client_metadata (install-time snapshot)
        metadata = provider.client_metadata or {}
        installed_ver = metadata.get("package_version", "1.0.0")
        return MarketplacePackage(
            id=provider.slug,
            provider_id=str(provider.id),
            display_name=provider.name,
            tier=(catalog_pkg.tier if catalog_pkg else None)
            or metadata.get("tier", "basic"),
            category=(catalog_pkg.category if catalog_pkg else None)
            or metadata.get("category", "custom"),
            description=provider.description or "",
            services_preview=metadata.get("services_preview", []),
            requires=metadata.get("requires", []),
            credential_provider=metadata.get("credential_provider"),
            status="installed",
            installed=True,
            version=catalog_pkg.version if catalog_pkg else installed_ver,
            installed_version=installed_ver,
            download_url=catalog_pkg.download_url if catalog_pkg else None,
            latest_url=catalog_pkg.latest_url if catalog_pkg else None,
            versions=catalog_pkg.versions if catalog_pkg else [],
            bug_report_url=catalog_pkg.bug_report_url if catalog_pkg else None,
        )

    # Check catalog for available (not installed) package
    catalog = await get_catalog_from_database(catalog_repo, CatalogType.PROVIDERS)

    if catalog:
        for pkg in catalog.packages:
            if pkg.id == package_id:
                return MarketplacePackage(
                    id=pkg.id,
                    provider_id=None,
                    display_name=pkg.display_name,
                    tier=pkg.tier,
                    category=pkg.category,
                    description=pkg.description,
                    services_preview=pkg.services_preview,
                    requires=pkg.requires,
                    credential_provider=pkg.credential_provider,
                    status="available",
                    installed=False,
                    version=pkg.version,
                    download_url=pkg.download_url,
                    latest_url=pkg.latest_url,
                    versions=pkg.versions,
                    bug_report_url=pkg.bug_report_url,
                )

    raise HTTPException(status_code=404, detail=f"Package '{package_id}' not found")


class CatalogUploadResponse(BaseModel):
    """Response from catalog upload."""

    success: bool
    version: str
    package_count: int
    message: str


@router.post(
    "/catalog/upload",
    response_model=CatalogUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload marketplace catalog",
    description="Upload a new marketplace-catalog.json file. Only super_admin can upload.",
)
async def upload_catalog(
    file: UploadFile = File(..., description="marketplace-catalog.json file"),
    catalog_repo: SQLAlchemyMarketplaceCatalogRepository = Depends(
        get_marketplace_catalog_repository
    ),
    _current_user: CurrentUser = Depends(require_super_admin),
) -> CatalogUploadResponse:
    """
    Upload a new marketplace catalog file (manual upload fallback).

    The file must be valid JSON with the structure:
    {
        "version": "1.0.0",
        "packages": [
            {
                "id": "package-id",
                "display_name": "Package Name",
                "tier": "basic" | "plus",
                "category": "core" | "ai" | etc.,
                "description": "...",
                "services_preview": ["Service 1", "Service 2"]
            }
        ]
    }
    """
    # Validate file type
    if not file.filename or not file.filename.endswith(".json"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="File must be a .json file"
        )

    try:
        content = await file.read()
        data = json.loads(content.decode("utf-8"))
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON format"
        )
    except Exception as e:
        logger.error(f"Failed to read uploaded marketplace catalog file: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to read file",
        )

    # Validate catalog structure
    try:
        catalog = RemoteCatalog(**data)
    except Exception as e:
        logger.error(f"Invalid marketplace catalog format: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid catalog format",
        )

    # Store in database
    await catalog_repo.upsert_active(
        catalog_type=CatalogType.PROVIDERS,
        catalog_data=data,
        source_url=None,  # Manual upload
        source_tag=None,
    )

    logger.info(
        f"Uploaded marketplace catalog v{catalog.version} with {len(catalog.packages)} packages"
    )

    return CatalogUploadResponse(
        success=True,
        version=catalog.version,
        package_count=len(catalog.packages),
        message=f"Catalog uploaded successfully with {len(catalog.packages)} packages",
    )


class CatalogRefreshResponse(BaseModel):
    """Response from catalog refresh."""

    success: bool
    version: Optional[str] = None
    package_count: int = 0
    source_url: str
    message: str


@router.post(
    "/catalog/refresh",
    response_model=CatalogRefreshResponse,
    summary="Refresh catalog from remote",
    description="Fetch the latest catalog from basic catalog (+ plus catalog if token) and store in database. Super admin only.",
)
async def refresh_catalog(
    catalog_repo: SQLAlchemyMarketplaceCatalogRepository = Depends(
        get_marketplace_catalog_repository
    ),
    current_user: CurrentUser = Depends(require_super_admin),
    secret_repo: OrganizationSecretRepository = Depends(
        get_organization_secret_repository
    ),
) -> CatalogRefreshResponse:
    """
    Refresh the marketplace catalog from remote source.

    Fetches from basic catalog and plus catalog (, if ENTITLEMENT_TOKEN
    is configured) and stores the merged result in the database.
    """
    org_id = current_user["org_id"]
    if not org_id:
        raise HTTPException(status_code=400, detail="User has no organization")
    token = await get_entitlement_token(org_id, secret_repo)
    source_url = cat_config.build_url(cat_config.REPO_BASIC, cat_config.PROVIDERS)

    catalog = await refresh_catalog_from_remote(
        catalog_repo=catalog_repo,
        catalog_type=CatalogType.PROVIDERS,
        token=token,
    )

    if catalog:
        # Sync docs alongside catalog refresh
        from app.config.docs_sync import sync_docs_on_refresh

        await sync_docs_on_refresh()

        return CatalogRefreshResponse(
            success=True,
            version=catalog.version,
            package_count=len(catalog.packages),
            source_url=source_url,
            message=f"Catalog refreshed successfully: v{catalog.version} with {len(catalog.packages)} packages",
        )

    # Remote unavailable - fall back to local catalog file
    local_catalog = get_catalog_from_local_file(CatalogType.PROVIDERS)
    if local_catalog:
        logger.info(
            f"Remote catalog unavailable, using local file: "
            f"v{local_catalog.version}, {len(local_catalog.packages)} packages"
        )
        return CatalogRefreshResponse(
            success=True,
            version=local_catalog.version,
            package_count=len(local_catalog.packages),
            source_url="local",
            message=f"Remote catalog unavailable. Using local catalog: v{local_catalog.version} with {len(local_catalog.packages)} packages",
        )

    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail=f"Failed to fetch catalog from {source_url} and no local catalog found",
    )


@router.get(
    "/catalog/raw",
    summary="Get raw catalog file",
    description="Get the raw marketplace-catalog.json content from database.",
)
async def get_raw_catalog(
    catalog_repo: SQLAlchemyMarketplaceCatalogRepository = Depends(
        get_marketplace_catalog_repository
    ),
    _current_user: CurrentUser = Depends(require_super_admin),
) -> Dict[str, Any]:
    """
    Get the raw catalog JSON from database.

    Returns the contents of the active catalog as-is.
    """
    catalog = await get_catalog_from_database(catalog_repo, CatalogType.PROVIDERS)
    if not catalog:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No catalog found. Use /catalog/refresh to fetch from remote or /catalog/upload to upload manually.",
        )

    # Get metadata from database
    db_catalog = await catalog_repo.get_active(CatalogType.PROVIDERS)

    return {
        "version": catalog.version,
        "packages": [pkg.model_dump() for pkg in catalog.packages],
        "metadata": {
            "source_url": db_catalog.source_url if db_catalog else None,
            "source_tag": db_catalog.source_tag if db_catalog else None,
            "fetched_at": (
                db_catalog.fetched_at.isoformat()
                if db_catalog and db_catalog.fetched_at
                else None
            ),
            "fetch_error": db_catalog.fetch_error if db_catalog else None,
        },
    }


class TokenStatus(BaseModel):
    """Token configuration status."""

    configured: bool


async def get_entitlement_token(
    org_id: str, secret_repo: OrganizationSecretRepository
) -> Optional[str]:
    """Get ENTITLEMENT_TOKEN from organization secrets. Returns None if not configured, inactive, or expired."""
    secret = await secret_repo.get_by_name(
        name="ENTITLEMENT_TOKEN",
        organization_id=uuid.UUID(org_id),
    )

    if secret and secret.is_active:
        # Check expiration
        if secret.expires_at and secret.expires_at < datetime.now(UTC):
            logger.info(f"ENTITLEMENT_TOKEN expired at {secret.expires_at}")
            return None
        # secret_data is already decrypted by the repository
        return secret.secret_data.get("token") or secret.secret_data.get("api_key")

    return None


@router.get(
    "/token-status",
    response_model=TokenStatus,
    summary="Check entitlement token status",
    description="Check if ENTITLEMENT_TOKEN is configured for accessing private packages.",
)
async def get_token_status(
    current_user: CurrentUser = Depends(get_current_user),
    secret_repo: OrganizationSecretRepository = Depends(
        get_organization_secret_repository
    ),
) -> TokenStatus:
    """
    Check if entitlement token is configured.

    Checks organization secrets for ENTITLEMENT_TOKEN.
    Token must be active and have a non-empty value.

    This is used by the UI to determine whether to show "Install" button
    for packages that require authentication.
    """
    org_id = current_user.get("org_id")
    if not org_id:
        return TokenStatus(configured=False)
    token = await get_entitlement_token(org_id, secret_repo)
    return TokenStatus(configured=bool(token))
