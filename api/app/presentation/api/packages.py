# api/app/presentation/api/packages.py

"""
Package Upload API

Upload and install provider packages via zip file or URL.
"""

import ipaddress
import json
import logging
import socket
import uuid
from typing import Any, Dict
from urllib.parse import urlparse


from app.application.services.package_management_service import PackageManagementService
from app.domain.common.value_objects import OperationalStatus, Visibility
from app.domain.provider.models import PackageType
from app.infrastructure.services.package_version_service import slug_is_reserved


import httpx
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, HttpUrl
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.docs_sync import deactivate_provider_doc, sync_provider_doc
from app.infrastructure.errors import safe_error_message
from app.infrastructure.persistence.database import get_db_session
from app.infrastructure.provider_installer import ProviderInstaller
from app.infrastructure.adapters.provider_loader import register_single_provider
from app.domain.organization_secret.repository import OrganizationSecretRepository
from app.infrastructure.repositories.marketplace_catalog_repository import (
    SQLAlchemyMarketplaceCatalogRepository,
)
from app.presentation.api.dependencies import (
    NamespacedId,
    get_adapter_registry,
    get_marketplace_catalog_repository,
    get_organization_secret_repository,
    get_package_management_service,
    require_super_admin,
    validate_safe_package_name,
)
from app.presentation.api.marketplace import (
    get_catalog_from_database,
    get_entitlement_token,
)
from app.config.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter()


# SSRF guard for install_from_url: resolve the admin-supplied host, reject any
# non-public resolved IP, and pin the connection to a validated IP (keeping the
# hostname for SNI/cert) so a DNS rebind can't swap it to an internal target
# between check and connect.


def _is_blocked_ip(ip: "ipaddress.IPv4Address | ipaddress.IPv6Address") -> bool:
    """True if the IP is private, loopback, link-local, reserved, multicast, or unspecified."""
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def _resolve_public_ip(host: str, port: int) -> str:
    """Resolve host and return a validated IP, or raise HTTPException(400) if any resolved IP is non-public."""
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Download URL host could not be resolved.",
        )
    addrs = [ipaddress.ip_address(info[4][0]) for info in infos]
    if not addrs or any(_is_blocked_ip(ip) for ip in addrs):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Download URL host is not permitted.",
        )
    return str(addrs[0])


class _PinnedPublicIPTransport(httpx.AsyncHTTPTransport):
    """httpx transport that pins each request (and redirect hop) to a validated public IP."""

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        host = request.url.host
        port = request.url.port or 443
        pinned = _resolve_public_ip(host, port)
        # Connect to the pinned IP; keep Host header + SNI on the hostname.
        request.extensions = {**request.extensions, "sni_hostname": host}
        request.url = request.url.copy_with(host=pinned)
        request.headers["Host"] = host
        return await super().handle_async_request(request)


def _validate_download_scheme(url: str) -> None:
    """Raise HTTPException(400) unless url is https with a host."""
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Download URL must be an https URL with a host.",
        )


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

    # Short-circuit: if provider exists as INACTIVE, just reactivate
    existing = await pkg_service.get_provider_by_slug(provider_slug)
    if existing and existing["status"] == OperationalStatus.INACTIVE:
        provider_id = existing["id"]
        services = await pkg_service.reactivate_provider(provider_id, provider_slug)
        try:
            registry = get_adapter_registry()
            await register_single_provider(session, registry, provider_id)
        except Exception as e:
            logger.warning(f"Could not register adapter after reactivation: {e}")
        await sync_provider_doc(provider_slug)
        return PackageInstallResponse(
            success=True,
            package_name=package_name,
            version=version,
            provider_name=existing["name"],
            provider_id=str(provider_id),
            services_installed=services,
        )

    # Reserved-prefix slugs (`shs/*`) are assumed first-party and land
    # PUBLIC; non-reserved slugs are super-admin custom content and land
    # PRIVATE so the super-admin can ramp via the Custom view. On upgrade
    # of an existing row, visibility is preserved (set on insert only).
    is_reserved = slug_is_reserved(provider_slug)
    visibility_on_insert = Visibility.PUBLIC if is_reserved else Visibility.PRIVATE
    try:
        installer = ProviderInstaller()
        result = await installer.install_from_data(
            provider_data,
            session,
            uuid.UUID(current_user["id"]),
            allow_reserved=is_reserved,
            visibility_on_insert=visibility_on_insert,
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
            logger.info(f"Registered adapter for {result.provider_name} after install")
        except Exception as e:
            # Log but don't fail - adapter can be loaded on next restart
            logger.warning(f"Could not register adapter immediately: {e}")

        await sync_provider_doc(provider_slug, tier=provider_data.get("tier"))

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
    _validate_download_scheme(url_str)
    download_url = url_str

    # For private repo release assets, we need to use the API to find the asset ID
    # browser_download_url doesn't work with token auth for private repos
    if token and urlparse(url_str).hostname == "github.com" and "/releases/download/" in url_str:
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
                    timeout=settings.MARKETPLACE_DOWNLOAD_TIMEOUT,
                    transport=_PinnedPublicIPTransport(),
                ) as client:
                    resp = await client.get(  # codeql[py/partial-ssrf]
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
    _download_host = urlparse(download_url).hostname
    if _download_host == "api.github.com":
        headers["Accept"] = "application/octet-stream"
    elif _download_host == "github.com" and "/releases/" in download_url:
        headers["Accept"] = "application/octet-stream"

    # download_url may have been reassigned to a resolved asset URL; scheme-check
    # it, then let the pinned transport validate the host at connect time (and on
    # every redirect hop).
    _validate_download_scheme(download_url)
    try:
        logger.info(f"Downloading provider from: {download_url}")
        async with httpx.AsyncClient(
            timeout=settings.PACKAGE_DOWNLOAD_TIMEOUT,
            follow_redirects=True,
            transport=_PinnedPublicIPTransport(),
        ) as client:
            response = await client.get(download_url, headers=headers)  # codeql[py/partial-ssrf]
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

    # Short-circuit: if provider exists as INACTIVE, just reactivate
    existing = await pkg_service.get_provider_by_slug(provider_slug)
    if existing and existing["status"] == OperationalStatus.INACTIVE:
        provider_id = existing["id"]
        services = await pkg_service.reactivate_provider(provider_id, provider_slug)
        try:
            registry = get_adapter_registry()
            await register_single_provider(session, registry, provider_id)
        except Exception as e:
            logger.warning(f"Could not register adapter after reactivation: {e}")
        await sync_provider_doc(provider_slug)
        return PackageInstallResponse(
            success=True,
            package_name=package_name,
            version=version,
            provider_name=existing["name"],
            provider_id=str(provider_id),
            services_installed=services,
        )

    is_reserved = slug_is_reserved(provider_slug)
    visibility_on_insert = Visibility.PUBLIC if is_reserved else Visibility.PRIVATE
    try:
        installer = ProviderInstaller()
        result = await installer.install_from_data(
            provider_data,
            session,
            uuid.UUID(current_user["id"]),
            allow_reserved=is_reserved,
            visibility_on_insert=visibility_on_insert,
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

        await sync_provider_doc(provider_slug, tier=provider_data.get("tier"))

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
    "/{namespace}/{slug}/usage",
    response_model=PackageUsageInfo,
    summary="Check package usage",
    description="Check how many workflows and blueprints use this package's provider.",
)
async def check_package_usage(
    package_name: NamespacedId,
    current_user: Dict[str, Any] = Depends(require_super_admin),
    pkg_service: PackageManagementService = Depends(get_package_management_service),
) -> PackageUsageInfo:
    """
    Check package usage before uninstalling.

    Returns information about workflows and blueprints that use this provider.
    """
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
    "/{namespace}/{slug}",
    response_model=UninstallResponse,
    summary="Uninstall a package",
    description="Remove a provider package from the filesystem and database.",
)
async def uninstall_package(
    package_name: NamespacedId,
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

                await deactivate_provider_doc(provider_slug)

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
    "/{namespace}/{slug}/reinstall",
    response_model=PackageInstallResponse,
    summary="Reinstall a soft-deleted package",
    description="Reactivates a previously uninstalled package from the database. "
    "Restores the provider, services, and credentials without downloading or reading from disk.",
)
async def reinstall_package(
    package_name: NamespacedId,
    current_user: Dict[str, Any] = Depends(require_super_admin),
    session: AsyncSession = Depends(get_db_session),
    pkg_service: PackageManagementService = Depends(get_package_management_service),
) -> PackageInstallResponse:
    """
    Reinstall a previously uninstalled (soft-deleted) package.

    Reactivates the provider, services, credentials, and package version
    rows from the database. No disk or network access needed.
    """

    # Find the provider by slug (may be INACTIVE)
    provider = await pkg_service.get_provider_by_slug(package_name)

    if not provider:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No package found with slug '{package_name}'. Use the install endpoint for new packages.",
        )

    if provider["status"] == OperationalStatus.ACTIVE:
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

    await sync_provider_doc(package_name)

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
    "/{namespace}/{slug}/versions",
    summary="List package version history",
    description="Returns all recorded versions for a package, newest first.",
)
async def list_package_versions(
    package_slug: NamespacedId,
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

    versions = await pkg_service.list_package_versions(package_slug, pt)

    if not versions:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No version history found for {package_type} package '{package_slug}'.",
        )

    return {
        "slug": package_slug,
        "package_type": package_type,
        "versions": versions,
    }


async def download_provider_package(
    download_url: str, token: str | None = None
) -> dict[str, Any]:
    """Download a unified provider JSON from a remote URL and return the parsed dict.

    Providers are distributed as a single .json file; the content is parsed in
    memory and installed via ProviderInstaller.install_from_data - no temp file.
    """
    headers: dict[str, str] = {}
    if token:
        headers["Authorization"] = f"token {token}"

    logger.info(f"Downloading provider from {download_url}")
    _validate_download_scheme(download_url)
    async with httpx.AsyncClient(
        timeout=settings.MARKETPLACE_DOWNLOAD_TIMEOUT,
        follow_redirects=True,
        transport=_PinnedPublicIPTransport(),
    ) as client:
        try:
            resp = await client.get(download_url, headers=headers)
            resp.raise_for_status()
            content = resp.content
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

    try:
        return json.loads(content)
    except json.JSONDecodeError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Downloaded file is not valid JSON (line {e.lineno}, column {e.colno}).",
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
    description="Reads the active catalog from the database and installs each entry "
    "from its download_url. Super admin only.",
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
    2. Downloads the unified JSON from the catalog download_url
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

        try:
            installer = ProviderInstaller()
            if package.download_url:
                # Download the unified JSON and install from the parsed dict.
                token = None
                if package.tier == "plus":
                    token = await get_entitlement_token(
                        current_user["org_id"], secret_repo
                    )
                provider_data = await download_provider_package(
                    package.download_url, token
                )
                install_result = await installer.install_from_data(
                    provider_data,
                    session,
                    uuid.UUID(current_user["id"]),
                    allow_reserved=True,
                )
            else:
                failed.append(
                    {
                        "package": package_id,
                        "error": "No download_url in catalog",
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

            await sync_provider_doc(package_id, tier=package.tier)

        except HTTPException as e:
            failed.append({"package": package_id, "error": e.detail})
        except Exception as e:
            failed.append({"package": package_id, "error": safe_error_message(e)})
            logger.exception(f"Failed to install {package_id} from catalog")

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
