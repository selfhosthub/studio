# api/app/presentation/api/comfyui_packages_internal.py

"""Internal worker endpoints: ComfyUI package catalog sync (ST126)."""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.services.comfyui_catalog_hash import (
    catalog_hash_for,
    list_active_packages,
    version_key,
)
from app.infrastructure.persistence.models import ComfyUIWorkflowModel
from app.presentation.api.dependencies import (
    get_db_session_service,
    verify_worker_secret,
)
from app.presentation.api.worker_jobs import verify_worker_jwt

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal", tags=["ComfyUI Packages Internal"])


# --- Response Models ---


class PackageListEntry(BaseModel):
    """Catalog listing entry for one package."""

    slug: str
    version: str
    source_hash: str


class PackageListResponse(BaseModel):
    """Catalog listing: hash plus per-package sync metadata."""

    catalog_hash: str
    packages: List[PackageListEntry]


class PackageDetailResponse(BaseModel):
    """Full package content for one slug."""

    package: Dict[str, Any]


# --- Endpoints ---


@router.get("/comfyui/packages", response_model=PackageListResponse)
async def list_comfyui_packages(
    authorization: Optional[str] = Header(None, alias="Authorization"),
    _: None = Depends(verify_worker_secret),
    session: AsyncSession = Depends(get_db_session_service),
) -> PackageListResponse:
    """
    List active catalog packages (highest version per slug) for worker sync.

    Authentication:
    - Requires Authorization: Bearer <token> header (JWT from registration/heartbeat)
    - Also requires X-Worker-Secret header for transport security
    """
    verify_worker_jwt(authorization)

    packages = await list_active_packages(session)
    return PackageListResponse(
        catalog_hash=catalog_hash_for(packages),
        packages=[
            PackageListEntry(slug=slug, version=version, source_hash=source_hash)
            for slug, version, source_hash in packages
        ],
    )


@router.get("/comfyui/packages/{ns}/{slug}", response_model=PackageDetailResponse)
async def get_comfyui_package(
    ns: str,
    slug: str,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    _: None = Depends(verify_worker_secret),
    session: AsyncSession = Depends(get_db_session_service),
) -> PackageDetailResponse:
    """
    Full json_content of the active highest-version package for 'ns/slug'.

    Authentication matches the listing endpoint (worker secret + JWT).

    Returns:
        - 200 with package content
        - 404 if no active row exists for the slug
    """
    verify_worker_jwt(authorization)

    full_slug = f"{ns}/{slug}"
    result = await session.execute(
        select(
            ComfyUIWorkflowModel.version,
            ComfyUIWorkflowModel.json_content,
        )
        .where(ComfyUIWorkflowModel.slug == full_slug)
        .where(ComfyUIWorkflowModel.is_active.is_(True))
    )
    rows = result.all()
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Package '{full_slug}' not found",
        )

    _, json_content = max(rows, key=lambda row: version_key(row[0]))
    return PackageDetailResponse(package=json_content)
