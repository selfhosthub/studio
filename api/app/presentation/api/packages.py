# api/app/presentation/api/packages.py

"""
Package Upload API

Upload and install provider packages via zip file or URL.
"""

import json
import logging
import re as regex_module
import tempfile
import uuid
from pathlib import Path
from typing import Any, Dict


from app.application.services.package_management_service import PackageManagementService
from app.domain.provider.models import PackageSource, PackageType, ProviderStatus


def validate_safe_package_name(name: str) -> str:
    """
    Validate that a package name is safe for use in filesystem paths.

    Prevents path traversal attacks by rejecting names containing:
    - Path separators (/, \\)
    - Parent directory references (..)
    - Null bytes
    """
    from fastapi import HTTPException, status

    if not name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid package name: cannot be empty",
        )

    # Check for path traversal patterns
    if ".." in name or "/" in name or "\\" in name or "\x00" in name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid package name: contains illegal characters",
        )

    # Only allow safe characters: alphanumeric, dash, underscore, and dot (not at edges)
    if not regex_module.match(
        r"^[a-zA-Z0-9][a-zA-Z0-9._-]*[a-zA-Z0-9]$|^[a-zA-Z0-9]$", name
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid package name: must contain only alphanumeric characters, dashes, underscores, and dots",
        )

    return name


import httpx
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, HttpUrl
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.errors import safe_error_message
from app.infrastructure.persistence.database import get_db_session
from app.infrastructure.provider_installer import ProviderInstaller
from app.infrastructure.adapters.provider_loader import register_single_provider
from app.domain.organization_secret.repository import OrganizationSecretRepository
from app.infrastructure.repositories.marketplace_catalog_repository import (
    SQLAlchemyMarketplaceCatalogRepository,
)
from app.presentation.api.dependencies import (
    get_adapter_registry,
    get_marketplace_catalog_repository,
    get_organization_secret_repository,
    get_package_management_service,
    require_super_admin,
)
from app.presentation.api.marketplace import (
    get_catalog_from_database,
    get_entitlement_token,
)
from app.config.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter()


class PackageInstallResponse(BaseModel):
    success: bool
    package_name: str
    version: str
    provider_name: str
    provider_id: str
    services_installed: list[str]
    error: str | None = None


class PackageListResponse(BaseModel):
    packages: list[dict[str, Any]]


@router.post(
    "/upload",
    response_model=PackageInstallResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload and install a provider",
    description="Upload a single JSON file describing a unified provider. The file will be parsed, validated, and installed.",
)
async def upload_package(
    file: UploadFile = File(..., description="Unified provider JSON file"),
    current_user: Dict[str, Any] = Depends(require_super_admin),
    session: AsyncSession = Depends(get_db_session),
    pkg_service: PackageManagementService = Depends(get_package_management_service),
) -> PackageInstallResponse:
    """
    Upload and install a provider from the unified single-file format.

    The JSON file must contain at minimum: slug, version, name, description,
    provider_type, category, and a services map. See the unified provider
    schema (studio-cat/schemas/provider.schema.json) for the full shape.

    Only super_admin can upload providers.
    """
    if not file.filename or not file.filename.endswith(".json"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be a .json file",
        )

    # Save the uploaded JSON to a temp file. We pass the path (not the content)
    # to install_from_path so the installer's source-of-truth abstraction
    # (file → JSON → DB) is preserved.
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        try:
            content = await file.read()
            provider_data = json.loads(content)
        except json.JSONDecodeError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Uploaded file is not valid JSON (line {e.lineno}, column {e.colno}).",
            )

        provider_slug = provider_data.get("slug")
        if not provider_slug:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Provider file must contain 'slug' field",
            )
        validate_safe_package_name(provider_slug)

        package_name = provider_slug
        version = provider_data.get("version", "")

        json_path = temp_path / f"{provider_slug}.json"
        json_path.write_bytes(content)

        # Short-circuit: if provider exists as INACTIVE, just reactivate
        existing = await pkg_service.get_provider_by_slug(provider_slug)
        if existing and existing["status"] == ProviderStatus.INACTIVE:
            provider_id = existing["id"]
            services = await pkg_service.reactivate_provider(provider_id, provider_slug)
            try:
                registry = get_adapter_registry()
                await register_single_provider(session, registry, provider_id)
            except Exception as e:
                logger.warning(f"Could not register adapter after reactivation: {e}")
            return PackageInstallResponse(
                success=True,
                package_name=package_name,
                version=version,
                provider_name=existing["name"],
                provider_id=str(provider_id),
                services_installed=services,
            )

        # Uploads append on new (slug, version), idempotent on same
        # (slug, version) with matching content hash. Origin is tracked via
        # PackageSource; no need to brand uploaded providers as CUSTOM
        # provider_type.
        try:
            installer = ProviderInstaller()
            result = await installer.install_from_path(
                json_path,
                session,
                uuid.UUID(current_user["id"]),
                source=PackageSource.LOCAL,
            )

            if not result.success:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Installation failed: {result.error}",
                )

            await session.commit()

            # Register adapter in global registry (so it's available immediately without restart)
            try:
                registry = get_adapter_registry()
                await register_single_provider(session, registry, result.provider_id)
                logger.info(
                    f"Registered adapter for {result.provider_name} after install"
                )
            except Exception as e:
                # Log but don't fail - adapter can be loaded on next restart
                logger.warning(f"Could not register adapter immediately: {e}")

            return PackageInstallResponse(
                success=True,
                package_name=result.package_name,
                version=result.version,
                provider_name=result.provider_name,
                provider_id=str(result.provider_id),
                services_installed=result.services_installed,
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to install package: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Installation failed",
            )


class InstallFromUrlRequest(BaseModel):
    """Request to install package from URL."""

    url: HttpUrl
    use_token: bool = False  # Whether to use ENTITLEMENT_TOKEN for auth


@router.post(
    "/install-from-url",
    response_model=PackageInstallResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Install package from URL",
    description="Download and install a provider package from a URL. For private repos, set use_token=true.",
)
async def install_from_url(
    request: InstallFromUrlRequest,
    current_user: Dict[str, Any] = Depends(require_super_admin),
    session: AsyncSession = Depends(get_db_session),
    secret_repo: OrganizationSecretRepository = Depends(
        get_organization_secret_repository
    ),
    pkg_service: PackageManagementService = Depends(get_package_management_service),
) -> PackageInstallResponse:
    """
    Install a provider package from a remote URL.

    Downloads the zip file from the URL and installs it.
    If use_token is true, uses ENTITLEMENT_TOKEN from organization secrets for authentication.

    Only super_admin can install packages.
    """
    headers = {}
    token = None
    if request.use_token:
        token = await get_entitlement_token(current_user["org_id"], secret_repo)
        if not token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="ENTITLEMENT_TOKEN not configured. Add it via Settings > Secrets.",
            )
        # GitHub token auth
        headers["Authorization"] = f"token {token}"

    # Detect GitHub URLs and set appropriate headers
    url_str = str(request.url)
    download_url = url_str

    # For private repo release assets, we need to use the API to find the asset ID
    # browser_download_url doesn't work with token auth for private repos
    if token and "github.com" in url_str and "/releases/download/" in url_str:
        # Parse: https://github.com/owner/repo/releases/download/tag/filename
        # Convert to API call to get asset URL
        import re

        match = re.match(
            r"https://github\.com/([^/]+)/([^/]+)/releases/download/([^/]+)/(.+)",
            url_str,
        )
        if match:
            owner, repo, tag, filename = match.groups()
            logger.info(
                f"Looking up release asset: owner={owner}, repo={repo}, tag={tag}, filename={filename}"
            )
            # First, get the release to find the asset ID
            api_url = f"https://api.github.com/repos/{owner}/{repo}/releases/tags/{tag}"
            try:
                async with httpx.AsyncClient(
                    timeout=settings.MARKETPLACE_DOWNLOAD_TIMEOUT
                ) as client:
                    resp = await client.get(
                        api_url,
                        headers={
                            "Authorization": f"token {token}",
                            "Accept": "application/vnd.github+json",
                        },
                    )
                    logger.info(f"GitHub API response: {resp.status_code}")
                    if resp.status_code == 200:
                        release_data = resp.json()
                        assets = release_data.get("assets", [])
                        logger.info(f"Found {len(assets)} assets in release")
                        for asset in assets:
                            logger.info(f"Asset: {asset.get('name')}")
                            if asset.get("name") == filename:
                                # Use the API asset URL which works with token auth
                                download_url = asset.get("url")
                                logger.info(f"Resolved asset URL: {download_url}")
                                break
                    else:
                        logger.warning(
                            f"GitHub API error: {resp.status_code} - {resp.text}"
                        )
            except Exception as e:
                logger.warning(f"Failed to resolve asset URL via API: {e}")

    # Set Accept header based on URL type
    if "api.github.com" in download_url:
        # For GitHub API asset downloads, request octet-stream to get binary
        headers["Accept"] = "application/octet-stream"
    elif "github.com" in download_url and "/releases/" in download_url:
        headers["Accept"] = "application/octet-stream"

    # Create temp directory for the downloaded provider JSON
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        try:
            logger.info(f"Downloading provider from: {download_url}")
            async with httpx.AsyncClient(
                timeout=settings.PACKAGE_DOWNLOAD_TIMEOUT, follow_redirects=True
            ) as client:
                response = await client.get(download_url, headers=headers)
                response.raise_for_status()
                content = response.content
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authentication failed. Check your ENTITLEMENT_TOKEN.",
                )
            elif e.response.status_code == 404:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Provider not found at the specified URL.",
                )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Failed to download provider",
            )
        except Exception as e:
            logger.error(f"Failed to download provider from {request.url}: {e}")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Failed to download provider",
            )

        # Parse the unified provider JSON.
        try:
            provider_data = json.loads(content)
        except json.JSONDecodeError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Downloaded file is not valid JSON (line {e.lineno}, column {e.colno}).",
            )

        provider_slug = provider_data.get("slug")
        if not provider_slug:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Provider file must contain 'slug' field",
            )
        validate_safe_package_name(provider_slug)

        package_name = provider_slug
        version = provider_data.get("version", "")

        json_path = temp_path / f"{provider_slug}.json"
        json_path.write_bytes(content)

        # Short-circuit: if provider exists as INACTIVE, just reactivate
        existing = await pkg_service.get_provider_by_slug(provider_slug)
        if existing and existing["status"] == ProviderStatus.INACTIVE:
            provider_id = existing["id"]
            services = await pkg_service.reactivate_provider(provider_id, provider_slug)
            try:
                registry = get_adapter_registry()
                await register_single_provider(session, registry, provider_id)
            except Exception as e:
                logger.warning(f"Could not register adapter after reactivation: {e}")
            return PackageInstallResponse(
                success=True,
                package_name=package_name,
                version=version,
                provider_name=existing["name"],
                provider_id=str(provider_id),
                services_installed=services,
            )

        try:
            installer = ProviderInstaller()
            pkg_source = (
                PackageSource.MARKETPLACE if request.use_token else PackageSource.LOCAL
            )
            result = await installer.install_from_path(
                json_path,
                session,
                uuid.UUID(current_user["id"]),
                source=pkg_source,
            )

            if not result.success:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Installation failed: {result.error}",
                )

            await session.commit()

            logger.info(
                f"Installed package {result.package_name} v{result.version} from URL"
            )

            # Register adapter in global registry (so it's available immediately without restart)
            try:
                registry = get_adapter_registry()
                await register_single_provider(session, registry, result.provider_id)
                logger.info(
                    f"Registered adapter for {result.provider_name} after URL install"
                )
            except Exception as e:
                # Log but don't fail - adapter can be loaded on next restart
                logger.warning(f"Could not register adapter immediately: {e}")

            return PackageInstallResponse(
                success=True,
                package_name=result.package_name,
                version=result.version,
                provider_name=result.provider_name,
                provider_id=str(result.provider_id),
                services_installed=result.services_installed,
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to install package: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Installation failed",
            )


class InstallFromPathRequest(BaseModel):
    """Request to install package from local providers directory."""

    package_id: str  # Directory name in providers/ (e.g., "core", "openai")
    use_token: bool = False  # Whether to use ENTITLEMENT_TOKEN for auth


@router.post(
    "/install-from-path",
    response_model=PackageInstallResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Install package from local path",
    description="Install a provider package from the local providers directory. Super admin only.",
)
async def install_from_path(
    request: InstallFromPathRequest,
    current_user: Dict[str, Any] = Depends(require_super_admin),
    session: AsyncSession = Depends(get_db_session),
    catalog_repo: SQLAlchemyMarketplaceCatalogRepository = Depends(
        get_marketplace_catalog_repository
    ),
    secret_repo: OrganizationSecretRepository = Depends(
        get_organization_secret_repository
    ),
    pkg_service: PackageManagementService = Depends(get_package_management_service),
) -> PackageInstallResponse:
    """
    Install a provider package from local source or remote catalog.

    If the provider already exists as INACTIVE (previously uninstalled),
    reactivates it instead of doing a full install. This preserves org
    credentials and avoids unnecessary file I/O.

    In dev: copies from local providers directory.
    In prod: downloads from catalog download_url when local source unavailable.
    """
    # Validate package name to prevent path traversal
    validate_safe_package_name(request.package_id)

    # Short-circuit: if provider exists as INACTIVE, just reactivate
    existing = await pkg_service.get_provider_by_slug(request.package_id)
    if existing and existing["status"] == ProviderStatus.INACTIVE:
        provider_id = existing["id"]
        services = await pkg_service.reactivate_provider(
            provider_id, request.package_id
        )
        try:
            registry = get_adapter_registry()
            await register_single_provider(session, registry, provider_id)
        except Exception as e:
            logger.warning(f"Could not register adapter after reactivation: {e}")
        return PackageInstallResponse(
            success=True,
            package_name=request.package_id,
            version=existing.get("version", ""),
            provider_name=existing["name"],
            provider_id=str(provider_id),
            services_installed=services,
        )

    # Resolve tier from catalog so we look in the right source directory
    from app.domain.provider.models import CatalogType

    catalog = await get_catalog_from_database(catalog_repo, CatalogType.PROVIDERS)
    tier = "basic"
    download_url = None
    if catalog:
        for pkg in catalog.packages:
            if pkg.id == request.package_id:
                tier = pkg.tier
                download_url = pkg.download_url
                break

    # Try local source first - pick the right directory based on tier.
    # Providers are flat <slug>.json files at the source root,
    # not directories with manifest+provider+adapter-config triplets.
    source_dir = _providers_source_for_tier(tier)
    install_path: Path | None = None
    if source_dir is not None:
        candidate = source_dir / f"{request.package_id}.json"
        if candidate.exists():
            install_path = candidate

    # If no local source, fall back to remote download into a temp dir
    if install_path is None:
        if not download_url:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Provider '{request.package_id}' not found locally or in catalog",
            )

        token = None
        if tier == "plus" or request.use_token:
            token = await get_entitlement_token(current_user["org_id"], secret_repo)

        return await _download_and_install_provider(
            request.package_id,
            download_url,
            token,
            session,
            current_user,
        )

    # Local source path - install directly from the .json file
    return await _install_from_directory(
        install_path,
        session,
        current_user,
        source=PackageSource.LOCAL,
    )


async def _install_from_directory(
    package_path: Path,
    session: AsyncSession,
    current_user: Dict[str, Any],
    source: PackageSource,
) -> PackageInstallResponse:
    """Install a provider from a directory and register the adapter."""
    try:
        installer = ProviderInstaller()
        result = await installer.install_from_path(
            package_path,
            session,
            uuid.UUID(current_user["id"]),
            source=source,
        )

        if not result.success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Installation failed: {result.error}",
            )

        await session.commit()

        logger.info(
            f"Installed package {result.package_name} v{result.version} from {package_path}"
        )

        try:
            registry = get_adapter_registry()
            await register_single_provider(session, registry, result.provider_id)
            logger.info(f"Registered adapter for {result.provider_name} after install")
        except Exception as e:
            logger.warning(f"Could not register adapter immediately: {e}")

        return PackageInstallResponse(
            success=True,
            package_name=result.package_name,
            version=result.version,
            provider_name=result.provider_name,
            provider_id=str(result.provider_id),
            services_installed=result.services_installed,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to install package from {package_path}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Installation failed",
        )


async def _download_and_install_provider(
    package_id: str,
    download_url: str,
    token: str | None,
    session: AsyncSession,
    current_user: Dict[str, Any],
) -> PackageInstallResponse:
    """Download a unified provider JSON to a temp file and install from there."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir) / f"{package_id}.json"
        await download_provider_package(download_url, tmp_path, token)
        return await _install_from_directory(
            tmp_path,
            session,
            current_user,
            source=PackageSource.MARKETPLACE,
        )


@router.get(
    "/installed",
    response_model=PackageListResponse,
    summary="List installed packages",
    description="List installed packages. Filter by package_type or return all types.",
)
async def list_installed_packages(
    package_type: str | None = Query(
        None,
        description="Filter by type: provider, workflow, blueprint, comfyui, prompt. Default: all types.",
    ),
    current_user: Dict[str, Any] = Depends(require_super_admin),
    pkg_service: PackageManagementService = Depends(get_package_management_service),
) -> PackageListResponse:
    """
    List installed packages from the package_versions table.

    Supports all 5 catalog types. Without a filter, returns all types.
    """
    pt = None
    if package_type:
        try:
            pt = PackageType(package_type)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid package_type '{package_type}'. "
                f"Valid values: {', '.join(t.value for t in PackageType)}",
            )

    packages = await pkg_service.list_installed_packages(package_type=pt)
    return PackageListResponse(packages=packages)


class PackageUsageInfo(BaseModel):
    """Information about package usage across workflows."""

    package_name: str
    provider_slug: str | None
    provider_id: str | None
    workflow_count: int
    blueprint_count: int
    affected_orgs: list[str]  # Organization names
    details: list[dict[str, Any]]  # Workflow/blueprint names and org info


@router.get(
    "/{package_name}/usage",
    response_model=PackageUsageInfo,
    summary="Check package usage",
    description="Check how many workflows and blueprints use this package's provider.",
)
async def check_package_usage(
    package_name: str,
    current_user: Dict[str, Any] = Depends(require_super_admin),
    pkg_service: PackageManagementService = Depends(get_package_management_service),
) -> PackageUsageInfo:
    """
    Check package usage before uninstalling.

    Returns information about workflows and blueprints that use this provider.
    """
    # Validate package name to prevent path traversal
    validate_safe_package_name(package_name)

    # Resolve provider slug from DB
    provider_slug = await pkg_service.resolve_provider_slug(package_name)

    # Get provider ID and usage
    provider_id = await pkg_service.get_provider_id_by_slug(provider_slug)

    if not provider_id:
        return PackageUsageInfo(
            package_name=package_name,
            provider_slug=provider_slug,
            provider_id=None,
            workflow_count=0,
            blueprint_count=0,
            affected_orgs=[],
            details=[],
        )

    usage = await pkg_service.get_provider_usage(provider_id)

    return PackageUsageInfo(
        package_name=package_name,
        provider_slug=provider_slug,
        provider_id=provider_id,
        workflow_count=usage["workflow_count"],
        blueprint_count=usage["blueprint_count"],
        affected_orgs=usage["affected_orgs"],
        details=usage["details"],
    )


class UninstallResponse(BaseModel):
    """Response from package uninstall."""

    success: bool
    message: str
    workflows_affected: int
    blueprints_affected: int


@router.delete(
    "/{package_name}",
    response_model=UninstallResponse,
    summary="Uninstall a package",
    description="Remove a provider package from the filesystem and database.",
)
async def uninstall_package(
    package_name: str,
    force: bool = False,
    current_user: Dict[str, Any] = Depends(require_super_admin),
    pkg_service: PackageManagementService = Depends(get_package_management_service),
) -> UninstallResponse:
    """
    Uninstall a provider package.

    Removes the package directory AND the provider/services from the database.

    If workflows or blueprints use this provider:
    - Without force=true: Returns error with usage count
    - With force=true: Uninstalls anyway (workflows will be broken)
    """
    # Validate package name to prevent path traversal
    validate_safe_package_name(package_name)

    # Resolve provider slug from DB
    provider_slug = await pkg_service.resolve_provider_slug(package_name)

    workflows_affected = 0
    blueprints_affected = 0

    # Delete from database
    if provider_slug:
        try:
            provider = await pkg_service.get_provider_by_slug(provider_slug)
            provider_id = provider["id"] if provider else None

            if provider_id:
                # Check usage before uninstalling
                usage = await pkg_service.get_provider_usage(str(provider_id))
                workflows_affected = usage["workflow_count"]
                blueprints_affected = usage["blueprint_count"]

                if (workflows_affected > 0 or blueprints_affected > 0) and not force:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail={
                            "message": f"Package is in use by {workflows_affected} workflow(s) and {blueprints_affected} blueprint(s). Use force=true to uninstall anyway.",
                            "workflows_affected": workflows_affected,
                            "blueprints_affected": blueprints_affected,
                            "affected_orgs": usage["affected_orgs"],
                        },
                    )

                # Soft-delete: deactivate instead of deleting.
                # Credentials preserved so reinstall restores API keys
                display_name = await pkg_service.soft_delete_provider(
                    provider_id, provider_slug
                )

                # Unregister adapter from in-memory registry
                # Registry keys use display name (e.g. "Airtable"), not slug ("airtable")
                try:
                    registry = get_adapter_registry()
                    registry.unregister_adapter(display_name or provider_slug)
                except Exception as e:
                    logger.warning(f"Could not unregister adapter: {e}")

        except HTTPException:
            raise  # Re-raise HTTP exceptions
        except Exception as e:
            logger.error(f"Failed to soft-delete provider from database: {e}")

    message = f"Package '{package_name}' uninstalled successfully"
    if workflows_affected > 0 or blueprints_affected > 0:
        message += f" (WARNING: {workflows_affected} workflow(s) and {blueprints_affected} blueprint(s) may be broken)"

    return UninstallResponse(
        success=True,
        message=message,
        workflows_affected=workflows_affected,
        blueprints_affected=blueprints_affected,
    )


@router.post(
    "/{package_name}/reinstall",
    response_model=PackageInstallResponse,
    summary="Reinstall a soft-deleted package",
    description="Reactivates a previously uninstalled package from the database. "
    "Restores the provider, services, and credentials without downloading or reading from disk.",
)
async def reinstall_package(
    package_name: str,
    current_user: Dict[str, Any] = Depends(require_super_admin),
    session: AsyncSession = Depends(get_db_session),
    pkg_service: PackageManagementService = Depends(get_package_management_service),
) -> PackageInstallResponse:
    """
    Reinstall a previously uninstalled (soft-deleted) package.

    Reactivates the provider, services, credentials, and package version
    rows from the database. No disk or network access needed.
    """
    validate_safe_package_name(package_name)

    # Find the provider by slug (may be INACTIVE)
    provider = await pkg_service.get_provider_by_slug(package_name)

    if not provider:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No package found with slug '{package_name}'. Use the install endpoint for new packages.",
        )

    if provider["status"] == ProviderStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Package '{package_name}' is already installed.",
        )

    # Reactivate provider, services, credentials, and package version
    services = await pkg_service.reactivate_provider(provider["id"], package_name)

    # Register adapter in in-memory registry (needs session for provider loader)
    try:
        registry = get_adapter_registry()
        await register_single_provider(session, registry, provider["id"])
        logger.info(f"Registered adapter for {provider['name']} after reinstall")
    except Exception as e:
        logger.warning(f"Could not register adapter after reinstall: {e}")

    logger.info(f"Reinstalled provider '{package_name}' from database")

    return PackageInstallResponse(
        success=True,
        package_name=package_name,
        version=provider["version"] or "1.0.0",
        provider_name=provider["name"],
        provider_id=str(provider["id"]),
        services_installed=services,
    )


@router.get(
    "/{slug}/versions",
    summary="List package version history",
    description="Returns all recorded versions for a package, newest first.",
)
async def list_package_versions(
    slug: str,
    package_type: str = Query(
        "provider",
        description="Package type: provider, workflow, blueprint, comfyui, prompt.",
    ),
    current_user: Dict[str, Any] = Depends(require_super_admin),
    pkg_service: PackageManagementService = Depends(get_package_management_service),
) -> Dict[str, Any]:
    """List all recorded versions for a package."""
    try:
        pt = PackageType(package_type)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid package_type '{package_type}'. "
            f"Valid values: {', '.join(t.value for t in PackageType)}",
        )

    versions = await pkg_service.list_package_versions(slug, pt)

    if not versions:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No version history found for {package_type} package '{slug}'.",
        )

    return {
        "slug": slug,
        "package_type": package_type,
        "versions": versions,
    }


class RefreshResponse(BaseModel):
    """Response from package refresh."""

    success: bool
    package_name: str
    provider_name: str
    services_updated: list[str]
    message: str


# Source directories for provider packages - community vs plus tier
from app.config.sources import (
    COMMUNITY_SOURCE,
    PLUS_SOURCE,
    PROVIDERS_DIRECTORY,
    is_remote,
    local_path as _local_path,
)

PROVIDERS_SOURCE_DIR: Path | None = (
    _local_path(COMMUNITY_SOURCE, "/app", PROVIDERS_DIRECTORY)
    if not is_remote(COMMUNITY_SOURCE)
    else None  # remote prod: download only, no local source
)

PLUS_PROVIDERS_SOURCE_DIR: Path | None = (
    _local_path(PLUS_SOURCE, "/app", PROVIDERS_DIRECTORY)
    if not is_remote(PLUS_SOURCE)
    else None  # remote prod: download only
)


def _providers_source_for_tier(tier: str) -> Path | None:
    """Return the local source directory for a provider package based on tier.

    Returns None when the relevant source is remote-only (no local mount),
    in which case callers must fall through to the catalog download_url.
    """
    if tier in ("advanced", "plus") and PLUS_PROVIDERS_SOURCE_DIR is not None:
        return PLUS_PROVIDERS_SOURCE_DIR
    return PROVIDERS_SOURCE_DIR


async def download_provider_package(
    download_url: str, dest_path: Path, token: str | None = None
) -> None:
    """Download a unified provider JSON file from a remote URL to *dest_path*.

    Providers are distributed as a single .json file. *dest_path* receives
    the file directly (not a directory of three files).
    """
    headers: dict[str, str] = {}
    if token:
        headers["Authorization"] = f"token {token}"

    logger.info(f"Downloading provider from {download_url}")
    async with httpx.AsyncClient(
        timeout=settings.MARKETPLACE_DOWNLOAD_TIMEOUT, follow_redirects=True
    ) as client:
        try:
            resp = await client.get(download_url, headers=headers)
            resp.raise_for_status()
            dest_path.write_bytes(resp.content)
        except httpx.HTTPStatusError as e:
            raise HTTPException(
                status_code=502,
                detail=f"Failed to download provider from upstream (HTTP {e.response.status_code}).",
            )
        except Exception as e:
            logger.exception("Provider download failed")
            raise HTTPException(
                status_code=502,
                detail=f"Failed to download provider: {safe_error_message(e)}",
            )


@router.post(
    "/{package_name}/refresh",
    response_model=RefreshResponse,
    summary="Refresh provider from package",
    description="Re-sync provider and services from the unified provider file to the database. Use after editing the provider definition.",
)
async def refresh_package(
    package_name: str,
    current_user: Dict[str, Any] = Depends(require_super_admin),
    session: AsyncSession = Depends(get_db_session),
) -> RefreshResponse:
    """
    Refresh a provider from its package definition.

    Reads the unified <slug>.json from the providers source directory and
    updates the database. Useful when the provider definition has been
    modified during development.

    Looks for packages in:
    1. PROVIDERS_SOURCE_DIR (community source mount)
    2. PLUS_PROVIDERS_SOURCE_DIR (plus source mount)
    """
    # Validate package name to prevent path traversal
    validate_safe_package_name(package_name)

    # Providers are flat <slug>.json files. Try community source, then plus source.
    package_path: Path | None = None
    if PROVIDERS_SOURCE_DIR is not None:
        candidate = PROVIDERS_SOURCE_DIR / f"{package_name}.json"
        if candidate.exists():
            package_path = candidate
    if package_path is None and PLUS_PROVIDERS_SOURCE_DIR is not None:
        candidate = PLUS_PROVIDERS_SOURCE_DIR / f"{package_name}.json"
        if candidate.exists():
            package_path = candidate

    if package_path is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Provider '{package_name}' not found in any providers source directory",
        )

    try:
        installer = ProviderInstaller()
        result = await installer.install_from_path(
            package_path,
            session,
            uuid.UUID(current_user["id"]),
            source=PackageSource.LOCAL,
        )

        if not result.success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Refresh failed: {result.error}",
            )

        await session.commit()

        logger.info(f"Refreshed package {result.package_name} v{result.version}")

        # Register adapter in global registry
        try:
            registry = get_adapter_registry()
            await register_single_provider(session, registry, result.provider_id)
            logger.info(
                f"Re-registered adapter for {result.provider_name} after refresh"
            )
        except Exception as e:
            logger.warning(f"Could not re-register adapter immediately: {e}")

        return RefreshResponse(
            success=True,
            package_name=result.package_name,
            provider_name=result.provider_name,
            services_updated=result.services_installed,
            message=f"Provider '{result.provider_name}' refreshed with {len(result.services_installed)} services",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to refresh package {package_name}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Refresh failed",
        )


class InstallAllFromCatalogResponse(BaseModel):
    """Response from installing all packages from the marketplace catalog."""

    success: bool
    installed: list[str]
    skipped: list[str]
    failed: list[dict[str, str]]
    validation: dict[str, Any]
    message: str


@router.post(
    "/install-all-from-catalog",
    response_model=InstallAllFromCatalogResponse,
    summary="Install all packages from marketplace catalog",
    description="Reads the active catalog from the database and installs each entry. "
    "Downloads from remote when local source is unavailable. Super admin only.",
)
async def install_all_from_catalog(
    current_user: Dict[str, Any] = Depends(require_super_admin),
    session: AsyncSession = Depends(get_db_session),
    pkg_service: PackageManagementService = Depends(get_package_management_service),
    catalog_repo: SQLAlchemyMarketplaceCatalogRepository = Depends(
        get_marketplace_catalog_repository
    ),
    secret_repo: OrganizationSecretRepository = Depends(
        get_organization_secret_repository
    ),
) -> InstallAllFromCatalogResponse:
    """
    Install all provider packages listed in the marketplace catalog.

    Reads the active catalog from the database, then for each entry:
    1. Skips if the provider is already installed (active in DB)
    2. Copies from local source directory, or downloads from download_url
    3. Installs via ProviderInstaller and registers the adapter
    """
    from app.domain.provider.models import CatalogType

    # 1. Read active catalog from DB
    catalog = await get_catalog_from_database(catalog_repo, CatalogType.PROVIDERS)
    if not catalog:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active catalog found. Upload the marketplace catalog first "
            "via POST /marketplace/catalog/upload.",
        )

    # 2. Get currently installed (active) providers
    installed_slugs = await pkg_service.get_active_provider_slugs()

    installed = []
    skipped = []
    failed = []

    # 3. Install each catalog entry
    for package in catalog.packages:
        package_id = package.id

        # Skip already-installed
        if package_id in installed_slugs:
            skipped.append(package_id)
            continue

        try:
            validate_safe_package_name(package_id)
        except HTTPException as e:
            failed.append({"package": package_id, "error": e.detail})
            continue

        # Providers are flat <slug>.json files. Resolve local source first.
        source_dir = _providers_source_for_tier(package.tier)
        local_source_path: Path | None = None
        if source_dir is not None:
            candidate = source_dir / f"{package.path or package_id}.json"
            if candidate.exists():
                local_source_path = candidate

        try:
            installer = ProviderInstaller()
            if local_source_path is not None:
                # Install directly from the local source mount
                install_result = await installer.install_from_path(
                    local_source_path,
                    session,
                    uuid.UUID(current_user["id"]),
                    source=PackageSource.LOCAL,
                )
            elif package.download_url:
                # Download to a temp file and install from there
                token = None
                if package.tier == "plus":
                    token = await get_entitlement_token(
                        current_user["org_id"], secret_repo
                    )
                with tempfile.TemporaryDirectory() as tmpdir:
                    tmp_path = Path(tmpdir) / f"{package_id}.json"
                    await download_provider_package(
                        package.download_url,
                        tmp_path,
                        token,
                    )
                    install_result = await installer.install_from_path(
                        tmp_path,
                        session,
                        uuid.UUID(current_user["id"]),
                        source=PackageSource.MARKETPLACE,
                    )
            else:
                failed.append(
                    {
                        "package": package_id,
                        "error": "No local source and no download_url in catalog",
                    }
                )
                continue

            if not install_result.success:
                failed.append(
                    {
                        "package": package_id,
                        "error": install_result.error or "Unknown error",
                    }
                )
                continue

            await session.commit()
            installed.append(package_id)
            logger.info(
                f"Installed {package_id} v{install_result.version} "
                f"({install_result.services_installed and len(install_result.services_installed) or 0} services)"
            )

            try:
                registry = get_adapter_registry()
                await register_single_provider(
                    session, registry, install_result.provider_id
                )
            except Exception as e:
                logger.warning(f"Could not register adapter for {package_id}: {e}")

        except HTTPException as e:
            failed.append({"package": package_id, "error": e.detail})
        except Exception as e:
            failed.append({"package": package_id, "error": str(e)})
            logger.error(f"Failed to install {package_id} from catalog: {e}")

    # 4. Validation: compare active providers vs catalog entries
    final_installed = await pkg_service.get_active_provider_slugs()
    catalog_ids = {p.id for p in catalog.packages}

    validation = {
        "in_db_not_in_catalog": sorted(final_installed - catalog_ids),
        "in_catalog_not_in_db": sorted(catalog_ids - final_installed),
    }

    total = len(installed)
    return InstallAllFromCatalogResponse(
        success=len(failed) == 0,
        installed=installed,
        skipped=skipped,
        failed=failed,
        validation=validation,
        message=f"Installed {total} packages from catalog"
        + (f", {len(skipped)} skipped" if skipped else "")
        + (f", {len(failed)} failed" if failed else ""),
    )
