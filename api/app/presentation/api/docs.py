# api/app/presentation/api/docs.py

"""Documentation API endpoints. Serves docs from filesystem; super-admins can refresh."""

import json
import logging
import os
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.config.settings import settings
from app.presentation.api.dependencies import CurrentUser, require_admin, require_super_admin

logger = logging.getLogger(__name__)

router = APIRouter()

DOCS_PATH = settings.DOCS_PATH


class DocInfo(BaseModel):
    id: str
    title: str
    description: str
    icon: str
    public: bool


class DocsManifest(BaseModel):
    version: str
    updated_at: str
    docs: List[DocInfo]


class DocContent(BaseModel):
    id: str
    title: str
    content: str


class ProviderDocInfo(BaseModel):
    id: str
    title: str
    description: str
    icon: str
    public: bool


class ProviderDocsList(BaseModel):
    providers: List[ProviderDocInfo]


def _get_catalog_path() -> str:
    return os.path.join(DOCS_PATH, "docs-catalog.json")


def _get_doc_path(doc_id: str) -> str:
    return os.path.join(DOCS_PATH, f"{doc_id}.md")


def _load_catalog() -> Optional[Dict[str, Any]]:
    catalog_path = _get_catalog_path()
    if not os.path.exists(catalog_path):
        logger.warning(f"Docs catalog not found at {catalog_path}")
        return None

    try:
        with open(catalog_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading docs catalog: {e}")
        return None


def _load_doc_content(doc_id: str) -> Optional[str]:
    doc_path = _get_doc_path(doc_id)
    if not os.path.exists(doc_path):
        logger.warning(f"Doc file not found at {doc_path}")
        return None

    try:
        with open(doc_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        logger.error(f"Error loading doc content for {doc_id}: {e}")
        return None


@router.get("/catalog", response_model=DocsManifest)
async def get_docs_catalog() -> DocsManifest:
    """Public catalog: only docs marked public=True are returned."""
    manifest = _load_catalog()

    if not manifest:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Documentation not available. Please contact your administrator.",
        )

    docs_list = []
    for doc_id, doc_info in manifest.get("docs", {}).items():
        if doc_info.get("public", False):
            docs_list.append(
                DocInfo(
                    id=doc_id,
                    title=doc_info.get("title", doc_id.title()),
                    description=doc_info.get("description", ""),
                    icon=doc_info.get("icon", "book"),
                    public=True,
                )
            )

    return DocsManifest(
        version=manifest.get("version", "0.0.0"),
        updated_at=manifest.get("updated_at", ""),
        docs=docs_list,
    )


@router.get("/catalog/full", response_model=DocsManifest)
async def get_docs_catalog_full(
    user: "CurrentUser" = Depends(require_admin),
) -> DocsManifest:
    """Role-filtered catalog: admin sees public+admin, super_admin sees everything."""
    manifest = _load_catalog()

    if not manifest:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Documentation not available. Please contact your administrator.",
        )

    is_super_admin = user.get("role") == "super_admin"

    docs_list = []
    for doc_id, doc_info in manifest.get("docs", {}).items():
        is_public = doc_info.get("public", False)
        if is_public or (doc_id == "super-admin" and is_super_admin) or doc_id == "admin":
            docs_list.append(
                DocInfo(
                    id=doc_id,
                    title=doc_info.get("title", doc_id.title()),
                    description=doc_info.get("description", ""),
                    icon=doc_info.get("icon", "book"),
                    public=is_public,
                )
            )

    return DocsManifest(
        version=manifest.get("version", "0.0.0"),
        updated_at=manifest.get("updated_at", ""),
        docs=docs_list,
    )


@router.get("/providers", response_model=ProviderDocsList)
async def get_provider_docs_list() -> ProviderDocsList:
    """Public list of provider docs from catalog.providers."""
    catalog = _load_catalog()

    if not catalog:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Documentation not available. Please contact your administrator.",
        )

    providers_data = catalog.get("providers", [])
    providers = [
        ProviderDocInfo(
            id=p.get("id", ""),
            title=p.get("title", ""),
            description=p.get("description", ""),
            icon=p.get("icon", "box"),
            public=p.get("public", True),
        )
        for p in providers_data
    ]

    return ProviderDocsList(providers=providers)


@router.get("/providers/{slug}", response_model=DocContent)
async def get_provider_doc_content(slug: str) -> DocContent:
    """Public; reads docs/providers/{slug}.md."""
    catalog = _load_catalog()

    if not catalog:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Documentation not available. Please contact your administrator.",
        )

    providers_data = catalog.get("providers", [])
    provider_info = next((p for p in providers_data if p.get("id") == slug), None)

    if not provider_info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Provider documentation '{slug}' not found.",
        )

    provider_path = os.path.join(DOCS_PATH, "providers", f"{slug}.md")
    if not os.path.exists(provider_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Provider documentation content for '{slug}' not found.",
        )

    try:
        with open(provider_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        logger.error(f"Error loading provider doc for {slug}: {e}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Provider documentation content for '{slug}' not found.",
        )

    return DocContent(
        id=slug,
        title=provider_info.get("title", slug.title()),
        content=content,
    )


@router.get("/workflows/{slug}", response_model=DocContent)
async def get_workflow_doc_content(slug: str) -> DocContent:
    """Public; reads docs/workflows/{slug}.md."""
    catalog = _load_catalog()

    if not catalog:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Documentation not available. Please contact your administrator.",
        )

    workflows_data = catalog.get("workflows", [])
    workflow_info = next((w for w in workflows_data if w.get("id") == slug), None)

    if not workflow_info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow documentation '{slug}' not found.",
        )

    workflow_path = os.path.join(DOCS_PATH, "workflows", f"{slug}.md")
    if not os.path.exists(workflow_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow documentation content for '{slug}' not found.",
        )

    try:
        with open(workflow_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        logger.error(f"Error loading workflow doc for {slug}: {e}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow documentation content for '{slug}' not found.",
        )

    return DocContent(
        id=slug,
        title=workflow_info.get("title", slug.title()),
        content=content,
    )


@router.get("/{doc_id}", response_model=DocContent)
async def get_doc_content(doc_id: str) -> DocContent:
    """Public docs only; non-public IDs return 403. Use /admin/content or /super-admin/content for those."""
    manifest = _load_catalog()
    if not manifest:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Documentation not available.")

    docs = manifest.get("docs", {})
    if doc_id not in docs:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Documentation '{doc_id}' not found."
        )

    doc_info = docs[doc_id]
    if not doc_info.get("public", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="This documentation requires authentication."
        )

    content = _load_doc_content(doc_id)
    if not content:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Documentation content for '{doc_id}' not found."
        )

    return DocContent(
        id=doc_id,
        title=doc_info.get("title", doc_id.title()),
        content=content,
    )


@router.get("/admin/content", response_model=DocContent)
async def get_admin_doc(
    user: "CurrentUser" = Depends(require_admin),
) -> DocContent:
    """Admin guide. Requires admin or super-admin."""
    manifest = _load_catalog()
    if not manifest:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Documentation not available.")

    docs = manifest.get("docs", {})
    if "admin" not in docs:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Admin documentation not found.")

    content = _load_doc_content("admin")
    if not content:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Admin documentation content not found."
        )

    doc_info = docs["admin"]
    return DocContent(
        id="admin",
        title=doc_info.get("title", "Admin Guide"),
        content=content,
    )


@router.get("/super-admin/content", response_model=DocContent)
async def get_super_admin_doc(
    user: "CurrentUser" = Depends(require_super_admin),
) -> DocContent:
    """Super-admin only. Deployment and infrastructure documentation."""
    manifest = _load_catalog()
    if not manifest:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Documentation not available.")

    docs = manifest.get("docs", {})
    if "super-admin" not in docs:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Super admin documentation not found.")

    content = _load_doc_content("super-admin")
    if not content:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Super admin documentation content not found."
        )

    doc_info = docs["super-admin"]
    return DocContent(
        id="super-admin",
        title=doc_info.get("title", "Super Admin Guide"),
        content=content,
    )
