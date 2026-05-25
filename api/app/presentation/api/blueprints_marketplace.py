# api/app/presentation/api/blueprints_marketplace.py

"""
API endpoints for the workflow blueprints marketplace.

Blueprints are workflow definitions that can be imported to create new workflows.
The catalog is stored in the database, fetched from remote sources (GitHub) or
uploaded manually.
"""

import json
import logging
import uuid
from typing import Dict, List, Optional

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.blueprint.repository import BlueprintRepository
from app.domain.organization_secret.repository import OrganizationSecretRepository
from app.domain.provider.models import CatalogType, PackageSource, PackageType
from app.presentation.api.dependencies import (
    get_blueprint_repository,
    get_marketplace_catalog_repository,
    get_organization_secret_repository,
    require_admin,
    require_super_admin,
    get_db_session,
    get_provider_repository,
)
from app.presentation.api.marketplace import get_entitlement_token
from app.domain.blueprint.models import Blueprint, BlueprintCategory, BlueprintStatus
from app.domain.provider.repository import ProviderRepository
from app.domain.common.value_objects import StepConfig
from app.infrastructure.repositories.marketplace_catalog_repository import (
    SQLAlchemyMarketplaceCatalogRepository,
)
from app.infrastructure.services.package_version_service import PackageVersionService
from app.config import catalog as cat_config
from app.config.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Blueprints Marketplace"])


class MarketplaceBlueprint(BaseModel):
    id: str
    display_name: str
    version: str
    tier: str  # "basic" | "plus"
    category: str
    description: str
    requires: List[str] = []  # Package IDs required
    author: str
    download_url: Optional[str] = None
    # Computed fields
    requirements_met: bool = True
    missing_packages: List[str] = []


class BlueprintsCatalog(BaseModel):
    version: str
    blueprints: List[MarketplaceBlueprint]
    filter_options: Dict[str, List[str]]
    warnings: List[str] = []


class RemoteBlueprint(BaseModel):
    """Blueprint entry from remote catalog."""

    id: str
    display_name: str
    version: str
    tier: str
    category: str
    description: str
    requires: List[str] = []
    author: str
    download_url: Optional[str] = None
    path: Optional[str] = None  # Local file path relative to the catalog source root


class RemoteBlueprintsCatalog(BaseModel):
    """Remote catalog format for marketplace-importable items.

    Accepts "blueprints", "workflows", or "templates" keys.
    Basic catalog uses "blueprints"; legacy catalogs use "templates".
    """

    version: str
    blueprints: List[RemoteBlueprint] = []
    workflows: List[RemoteBlueprint] = []
    templates: List[RemoteBlueprint] = []

    @property
    def entries(self) -> List[RemoteBlueprint]:
        return self.blueprints or self.workflows or self.templates


async def fetch_remote_blueprints_catalog(
    token: Optional[str] = None,
) -> Optional[RemoteBlueprintsCatalog]:
    """Fetch blueprints catalog from basic catalog (+ plus catalog if token), merge."""
    data = await cat_config.fetch_and_merge(
        cat_config.BLUEPRINTS, "blueprints", token=token
    )
    if data:
        return RemoteBlueprintsCatalog(**data)
    return None


async def get_catalog_from_database(
    catalog_repo: SQLAlchemyMarketplaceCatalogRepository,
) -> Optional[RemoteBlueprintsCatalog]:
    catalog = await catalog_repo.get_active(CatalogType.BLUEPRINTS)
    if catalog and catalog.catalog_data:
        try:
            return RemoteBlueprintsCatalog(**catalog.catalog_data)
        except Exception as e:
            logger.warning(
                f"Failed to parse blueprints catalog data from database: {e}"
            )
            return None
    return None


async def refresh_catalog_from_remote(
    catalog_repo: SQLAlchemyMarketplaceCatalogRepository,
    token: Optional[str] = None,
) -> Optional[RemoteBlueprintsCatalog]:
    """Fetch blueprints catalog from remote and store in database."""
    remote_catalog = await fetch_remote_blueprints_catalog(token=token)
    source_url = cat_config.build_url(cat_config.REPO_BASIC, cat_config.BLUEPRINTS)

    if remote_catalog:
        await catalog_repo.upsert_active(
            catalog_type=CatalogType.BLUEPRINTS,
            catalog_data=remote_catalog.model_dump(),
            source_url=source_url,
        )
        logger.info(
            f"Refreshed blueprints catalog from {source_url}: "
            f"v{remote_catalog.version}, {len(remote_catalog.entries)} entries"
        )
        return remote_catalog
    else:
        await catalog_repo.set_fetch_error(
            catalog_type=CatalogType.BLUEPRINTS,
            error_message=f"Failed to fetch catalog from {source_url}",
        )
        return None


async def get_installed_package_ids(provider_repo: ProviderRepository) -> set[str]:
    db_providers = await provider_repo.list_all(
        skip=0, limit=settings.DEFAULT_FETCH_LIMIT
    )
    return {p.slug for p in db_providers}


@router.get("/catalog", response_model=BlueprintsCatalog)
async def get_blueprints_catalog(
    category: Optional[str] = Query(None, description="Filter by category"),
    tier: Optional[str] = Query(None, description="Filter by tier: basic, plus"),
    current_user: Dict[str, str] = Depends(require_admin),
    provider_repo: ProviderRepository = Depends(get_provider_repository),
    catalog_repo: SQLAlchemyMarketplaceCatalogRepository = Depends(
        get_marketplace_catalog_repository
    ),
) -> BlueprintsCatalog:
    """
    Get the blueprints marketplace catalog.

    Fetches available blueprints from remote catalog (or local fallback),
    then checks which required packages are installed.

    Access control:
    - super_admin: sees all blueprints (basic + plus)
    - admin: sees basic blueprints + plus blueprints only if requirements met

    Filter parameters:
    - tier: basic | plus
    - category: core, ai, etc.
    """
    # Get set of installed package IDs from database
    installed_ids = await get_installed_package_ids(provider_repo)
    warnings: List[str] = []

    # Auto-refresh if stale (basic catalog only - no token on GET)
    db_catalog_record = await catalog_repo.get_active(CatalogType.BLUEPRINTS)
    if cat_config.is_stale(db_catalog_record.fetched_at if db_catalog_record else None):
        try:
            result = await refresh_catalog_from_remote(catalog_repo)
            if result is None:
                warnings.append(
                    "Blueprints catalog refresh returned no data. Using cached catalog."
                )
        except Exception as e:
            logger.warning(f"Auto-refresh of blueprints catalog failed: {e}")
            warnings.append(
                f"Blueprints catalog auto-refresh failed: {e}. Using cached data."
            )

    # Read from database catalog
    remote_catalog = await get_catalog_from_database(catalog_repo)

    if not remote_catalog:
        warnings.append("No catalog data available. Run seed or refresh catalog.")
        return BlueprintsCatalog(
            version="1.0.0",
            blueprints=[],
            filter_options={"tier": ["basic", "plus"], "category": []},
            warnings=warnings,
        )

    blueprints: List[MarketplaceBlueprint] = []
    categories_set: set[str] = set()
    tiers_set: set[str] = set()

    for entry in remote_catalog.entries:
        # Check which required packages are missing
        missing = [req for req in entry.requires if req not in installed_ids]
        requirements_met = len(missing) == 0

        categories_set.add(entry.category)
        tiers_set.add(entry.tier)

        blueprints.append(
            MarketplaceBlueprint(
                id=entry.id,
                display_name=entry.display_name,
                version=entry.version,
                tier=entry.tier,
                category=entry.category,
                description=entry.description,
                requires=entry.requires,
                author=entry.author,
                download_url=entry.download_url,
                requirements_met=requirements_met,
                missing_packages=missing,
            )
        )

    # Apply filters
    if tier:
        blueprints = [b for b in blueprints if b.tier == tier]
    if category:
        blueprints = [b for b in blueprints if b.category == category]

    # Build filter options
    filter_options = {
        "tier": sorted(list(tiers_set)) if tiers_set else ["basic", "plus"],
        "category": sorted(list(categories_set)) if categories_set else [],
    }

    return BlueprintsCatalog(
        version=remote_catalog.version,
        blueprints=blueprints,
        filter_options=filter_options,
        warnings=warnings,
    )


@router.get("/blueprints/{blueprint_id}", response_model=MarketplaceBlueprint)
async def get_blueprint(
    blueprint_id: str,
    current_user: Dict[str, str] = Depends(require_admin),
    provider_repo: ProviderRepository = Depends(get_provider_repository),
    catalog_repo: SQLAlchemyMarketplaceCatalogRepository = Depends(
        get_marketplace_catalog_repository
    ),
) -> MarketplaceBlueprint:
    """
    Get details for a specific blueprint.

    Access control:
    - super_admin: can view any blueprint
    - admin: can only view basic blueprints, or plus blueprints if requirements met
    """
    # Get set of installed package IDs from database
    installed_ids = await get_installed_package_ids(provider_repo)

    # Read from database catalog
    remote_catalog = await get_catalog_from_database(catalog_repo)

    if not remote_catalog:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Blueprint '{blueprint_id}' not found",
        )

    for entry in remote_catalog.entries:
        if entry.id == blueprint_id:
            missing = [req for req in entry.requires if req not in installed_ids]
            requirements_met = len(missing) == 0

            return MarketplaceBlueprint(
                id=entry.id,
                display_name=entry.display_name,
                version=entry.version,
                tier=entry.tier,
                category=entry.category,
                description=entry.description,
                requires=entry.requires,
                author=entry.author,
                download_url=entry.download_url,
                requirements_met=requirements_met,
                missing_packages=missing,
            )

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Blueprint '{blueprint_id}' not found",
    )


class InstalledBlueprintInfo(BaseModel):
    marketplace_id: str
    blueprint_id: str  # Local database ID for uninstall
    name: str


class InstalledBlueprintsResponse(BaseModel):
    installed_ids: List[str]  # For backward compatibility
    installed_blueprints: List[InstalledBlueprintInfo] = (
        []
    )  # Full info including local IDs


@router.get("/installed", response_model=InstalledBlueprintsResponse)
async def get_installed_blueprints(
    current_user: Dict[str, str] = Depends(require_admin),
    blueprint_repo: BlueprintRepository = Depends(get_blueprint_repository),
) -> InstalledBlueprintsResponse:
    """
    Get list of marketplace blueprint IDs that have been installed.

    Queries the database for blueprints with marketplace_id in their client_metadata.
    Returns both the marketplace IDs and full blueprint info including local database IDs (for uninstall functionality).
    """
    # Query org blueprints and filter for marketplace_id in Python
    org_id = uuid.UUID(current_user["org_id"])
    db_blueprints = await blueprint_repo.list_by_organization(
        organization_id=org_id, skip=0, limit=settings.DEFAULT_FETCH_LIMIT
    )

    # Extract marketplace IDs and build full info list
    installed_ids = []
    installed_blueprints = []
    for bp in db_blueprints:
        # Check if this blueprint came from marketplace
        if bp.client_metadata:
            marketplace_id = bp.client_metadata.get("marketplace_id")
            if marketplace_id:
                installed_ids.append(marketplace_id)
                installed_blueprints.append(
                    InstalledBlueprintInfo(
                        marketplace_id=marketplace_id,
                        blueprint_id=str(bp.id),
                        name=bp.name,
                    )
                )

    return InstalledBlueprintsResponse(
        installed_ids=installed_ids,
        installed_blueprints=installed_blueprints,
    )


class BlueprintImportResponse(BaseModel):
    success: bool
    workflow_id: str
    workflow_name: str
    message: str
    missing_packages: List[str] = []


class BlueprintImportRequest(BaseModel):
    name: Optional[str] = None  # Optional custom name for the workflow


@router.post("/import/{blueprint_id}", response_model=BlueprintImportResponse)
async def import_blueprint(
    blueprint_id: str,
    request: Optional[BlueprintImportRequest] = None,
    current_user: Dict[str, str] = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
    provider_repo: ProviderRepository = Depends(get_provider_repository),
    secret_repo: OrganizationSecretRepository = Depends(
        get_organization_secret_repository
    ),
    blueprint_repo: BlueprintRepository = Depends(get_blueprint_repository),
    catalog_repo: SQLAlchemyMarketplaceCatalogRepository = Depends(
        get_marketplace_catalog_repository
    ),
) -> BlueprintImportResponse:
    """
    Import a workflow blueprint from the marketplace.

    Downloads the blueprint JSON and creates a new blueprint from it.
    Once imported, the blueprint appears in the Organization tab for all users.
    Warns if required packages are not installed.
    Supports token authentication for plus-tier blueprints.

    Admin and super_admin can import from the marketplace.
    """
    # Get set of installed package IDs
    installed_ids = await get_installed_package_ids(provider_repo)

    # Read from database catalog
    remote_catalog = await get_catalog_from_database(catalog_repo)

    if not remote_catalog:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Blueprint '{blueprint_id}' not found",
        )

    # Find the blueprint
    catalog_entry = None
    for entry in remote_catalog.entries:
        if entry.id == blueprint_id:
            catalog_entry = entry
            break

    if not catalog_entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Blueprint '{blueprint_id}' not found",
        )

    if not catalog_entry.download_url and not catalog_entry.path:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Blueprint has no download URL or local path",
        )

    # Check for missing packages
    missing = [req for req in catalog_entry.requires if req not in installed_ids]

    blueprint_data = None

    # Try local path first (faster, no network) - pick the right source based on tier
    if catalog_entry.path:
        from app.config.sources import (
            is_remote,
            local_path as _local_path,
            source_for_tier,
        )

        source = source_for_tier(catalog_entry.tier)
        if not is_remote(source):
            local_bp_path = _local_path(source, "/app", catalog_entry.path)
            if local_bp_path.exists():
                try:
                    blueprint_data = json.loads(
                        local_bp_path.read_text(encoding="utf-8")
                    )
                except Exception as e:
                    logger.warning(
                        f"Failed to load local blueprint from {local_bp_path}: {e}"
                    )

    # Fall back to download URL
    if blueprint_data is None and catalog_entry.download_url:
        # Set up headers for download
        headers = {}
        if catalog_entry.tier == "plus":
            token = await get_entitlement_token(current_user["org_id"], secret_repo)
            if not token:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="ENTITLEMENT_TOKEN not configured. Add it via Settings > Secrets.",
                )
            headers["Authorization"] = f"token {token}"

        try:
            async with httpx.AsyncClient(
                timeout=settings.MARKETPLACE_DOWNLOAD_TIMEOUT
            ) as client:
                response = await client.get(catalog_entry.download_url, headers=headers)
                response.raise_for_status()
                blueprint_data = response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authentication failed. Check your ENTITLEMENT_TOKEN.",
                )
            elif e.response.status_code == 404:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Blueprint file not found at the specified URL.",
                )
            logger.error(
                f"Failed to download blueprint from {catalog_entry.download_url}: {e}"
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Failed to download blueprint",
            )
        except Exception as e:
            logger.error(
                f"Failed to download blueprint from {catalog_entry.download_url}: {e}"
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Failed to download blueprint",
            )

    if blueprint_data is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not load blueprint from any source",
        )

    # Generate blueprint name
    blueprint_name = (
        request.name if request and request.name else catalog_entry.display_name
    )

    # Get the org ID from the current user
    org_id = uuid.UUID(current_user["org_id"])
    user_id = uuid.UUID(current_user["id"])

    # Parse steps from blueprint data
    # Catalog JSON puts service routing fields inside the job object as string slugs.
    # StepConfig/JobConfig expects provider_id as UUID, so move them to step level
    # (where extra="allow" accepts them).
    steps: Dict[str, StepConfig] = {}
    if "steps" in blueprint_data and isinstance(blueprint_data["steps"], dict):
        for step_id, step_data in blueprint_data["steps"].items():
            try:
                step_data = dict(step_data)  # Don't mutate original
                if "job" in step_data and isinstance(step_data["job"], dict):
                    step_data["job"] = dict(step_data["job"])
                    for field in ("service_type", "provider_id", "service_id"):
                        if field in step_data["job"] and field not in step_data:
                            step_data[field] = step_data["job"].pop(field)
                steps[step_id] = StepConfig(**step_data)
            except Exception as e:
                logger.warning(f"Failed to parse step {step_id}: {e}")

    # Build client_metadata: preserve blueprint's experience_config and prompts,
    # then add marketplace tracking fields
    merged_metadata = dict(blueprint_data.get("client_metadata", {}))
    if "prompts" in blueprint_data:
        merged_metadata["prompts"] = blueprint_data["prompts"]
    merged_metadata.update(
        {
            "marketplace_id": blueprint_id,
            "marketplace_version": catalog_entry.version,
            "marketplace_author": catalog_entry.author,
            "marketplace_tier": catalog_entry.tier,
            "marketplace_category": catalog_entry.category,
        }
    )

    # Create the blueprint entity
    new_blueprint = Blueprint.create(
        name=blueprint_name,
        organization_id=org_id,
        created_by=user_id,
        description=blueprint_data.get("description", catalog_entry.description),
        category=BlueprintCategory.GENERAL,  # Default category
        tags=[
            catalog_entry.tier,
            catalog_entry.category,
        ],  # Use marketplace tier/category as tags
        client_metadata=merged_metadata,
        steps=steps,
    )

    new_blueprint.status = BlueprintStatus.PUBLISHED

    # Save to database
    saved_blueprint = await blueprint_repo.create(new_blueprint)

    # Record package version snapshot for DB-authoritative storage
    pv_json_content = {
        "catalog_entry": {
            "id": blueprint_id,
            "display_name": catalog_entry.display_name,
            "version": catalog_entry.version,
            "tier": catalog_entry.tier,
            "category": catalog_entry.category,
            "description": catalog_entry.description,
            "requires": catalog_entry.requires,
            "author": catalog_entry.author,
        },
        "blueprint_data": blueprint_data,
        "local_blueprint_id": str(saved_blueprint.id),
    }
    pv_source_hash = PackageVersionService.compute_source_hash(pv_json_content)
    await PackageVersionService.record_version(
        session=db,
        package_type=PackageType.BLUEPRINT,
        slug=blueprint_id,
        version=catalog_entry.version,
        json_content=pv_json_content,
        source_hash=pv_source_hash,
        created_by=user_id,
        source=PackageSource.MARKETPLACE,
    )

    logger.info(
        f"Imported blueprint '{blueprint_id}' as '{blueprint_name}' (id={saved_blueprint.id}) by user {current_user.get('username')}"
    )

    return BlueprintImportResponse(
        success=True,
        workflow_id=str(saved_blueprint.id),
        workflow_name=blueprint_name,
        message="Blueprint imported successfully"
        + (f" (warning: missing packages: {', '.join(missing)})" if missing else ""),
        missing_packages=missing,
    )


class CatalogUploadResponse(BaseModel):
    success: bool
    version: str
    blueprint_count: int
    message: str


@router.post(
    "/catalog/upload",
    response_model=CatalogUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload blueprints catalog",
    description="Upload a blueprints-catalog.json file. Only super_admin can upload.",
)
async def upload_blueprints_catalog(
    file: UploadFile = File(..., description="blueprints-catalog.json file"),
    _current_user: Dict[str, str] = Depends(require_super_admin),
    catalog_repo: SQLAlchemyMarketplaceCatalogRepository = Depends(
        get_marketplace_catalog_repository
    ),
) -> CatalogUploadResponse:
    """
    Upload a blueprints catalog file.

    The file must be valid JSON with the structure:
    {
        "version": "1.0.0",
        "blueprints": [
            {
                "id": "blueprint-id",
                "display_name": "Blueprint Name",
                "version": "1.0.0",
                "tier": "basic" | "plus",
                "category": "core" | "ai" | etc.,
                "description": "...",
                "requires": ["core"],
                "author": "SelfHostHub",
                "download_url": "https://..."
            }
        ]
    }

    Also accepts "templates" or "workflows" keys for backward compatibility.
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
        logger.error(f"Failed to read uploaded blueprints catalog file: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to read file",
        )

    # Validate catalog structure
    try:
        catalog = RemoteBlueprintsCatalog(**data)
    except Exception as e:
        logger.error(f"Invalid blueprints catalog format: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid catalog format",
        )

    # Store in database
    await catalog_repo.upsert_active(
        catalog_type=CatalogType.BLUEPRINTS,
        catalog_data=data,
        source_url=None,  # Manual upload
        source_tag=None,
    )

    entry_count = len(catalog.entries)
    logger.info(
        f"Uploaded blueprints catalog v{catalog.version} with {entry_count} blueprints"
    )

    return CatalogUploadResponse(
        success=True,
        version=catalog.version,
        blueprint_count=entry_count,
        message=f"Blueprints catalog uploaded successfully with {entry_count} blueprints",
    )


@router.post("/catalog/refresh", response_model=CatalogUploadResponse)
async def refresh_blueprints_catalog(
    current_user: Dict[str, str] = Depends(require_super_admin),
    secret_repo: OrganizationSecretRepository = Depends(
        get_organization_secret_repository
    ),
    catalog_repo: SQLAlchemyMarketplaceCatalogRepository = Depends(
        get_marketplace_catalog_repository
    ),
) -> CatalogUploadResponse:
    """
    Re-fetch the blueprints catalog from basic catalog (+ plus catalog if token) and store in database.
    """
    token = await get_entitlement_token(current_user["org_id"], secret_repo)

    remote = await refresh_catalog_from_remote(catalog_repo, token=token)
    if not remote:
        source_url = cat_config.build_url(cat_config.REPO_BASIC, cat_config.BLUEPRINTS)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to fetch catalog from {source_url}",
        )

    entry_count = len(remote.entries)

    # Sync docs alongside catalog refresh
    try:
        from app.config.docs_sync import sync_docs_on_refresh

        await sync_docs_on_refresh()
    except Exception as e:
        logger.warning(f"Docs sync during catalog refresh failed: {e}")

    return CatalogUploadResponse(
        success=True,
        version=remote.version,
        blueprint_count=entry_count,
        message=f"Catalog refreshed: {entry_count} blueprints (v{remote.version})",
    )
