# api/app/presentation/api/docs.py

"""Documentation API endpoints. Serves docs from the documentation table.

Content is synced from the marketplace sources (community/plus) at boot,
catalog refresh, and provider install - see app/config/docs_sync.py. No
filesystem reads.
"""

import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.domain.documentation.models import Documentation, DocType, DocVisibility
from app.domain.documentation.repository import DocumentationRepository
from app.presentation.api.dependencies import (
    CurrentUser,
    get_documentation_repository,
    require_admin,
    require_super_admin,
)

logger = logging.getLogger(__name__)

router = APIRouter()


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


def _to_doc_info(doc: Documentation) -> DocInfo:
    return DocInfo(
        id=doc.slug,
        title=doc.title,
        description=doc.description,
        icon=doc.icon,
        public=doc.visibility == DocVisibility.PUBLIC,
    )


def _latest_updated_at(docs: List[Documentation]) -> str:
    timestamps = [d.updated_at or d.created_at for d in docs]
    timestamps = [t for t in timestamps if t is not None]
    return max(timestamps).isoformat() if timestamps else ""


def _docs_unavailable() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Documentation not available. Please contact your administrator.",
    )


@router.get("/catalog", response_model=DocsManifest)
async def get_docs_catalog(
    repo: DocumentationRepository = Depends(get_documentation_repository),
) -> DocsManifest:
    """Public catalog: only public user docs are returned."""
    docs = await repo.list_by_type(DocType.USER)
    if not docs:
        raise _docs_unavailable()

    public_docs = [d for d in docs if d.visibility == DocVisibility.PUBLIC]
    return DocsManifest(
        version="1.0.0",
        updated_at=_latest_updated_at(docs),
        docs=[_to_doc_info(d) for d in public_docs],
    )


@router.get("/catalog/full", response_model=DocsManifest)
async def get_docs_catalog_full(
    user: "CurrentUser" = Depends(require_admin),
    repo: DocumentationRepository = Depends(get_documentation_repository),
) -> DocsManifest:
    """Role-filtered catalog: admin sees public+admin, super_admin sees everything."""
    docs = await repo.list_by_type(DocType.USER)
    if not docs:
        raise _docs_unavailable()

    is_super_admin = user.get("role") == "super_admin"
    visible = [
        d
        for d in docs
        if d.visibility != DocVisibility.SUPER_ADMIN or is_super_admin
    ]
    return DocsManifest(
        version="1.0.0",
        updated_at=_latest_updated_at(docs),
        docs=[_to_doc_info(d) for d in visible],
    )


@router.get("/providers", response_model=ProviderDocsList)
async def get_provider_docs_list(
    repo: DocumentationRepository = Depends(get_documentation_repository),
) -> ProviderDocsList:
    """Public list of docs for installed providers."""
    docs = await repo.list_by_type(DocType.PROVIDER)
    return ProviderDocsList(
        providers=[
            ProviderDocInfo(
                id=d.slug,
                title=d.title,
                description=d.description,
                icon=d.icon,
                public=d.visibility == DocVisibility.PUBLIC,
            )
            for d in docs
        ]
    )


@router.get("/providers/{slug:path}", response_model=DocContent)
async def get_provider_doc_content(
    slug: str,
    repo: DocumentationRepository = Depends(get_documentation_repository),
) -> DocContent:
    """Public; slug is namespaced (e.g. shs/openai). 404 when not installed."""
    doc = await repo.get(slug, DocType.PROVIDER)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Provider documentation '{slug}' not found.",
        )
    return DocContent(id=doc.slug, title=doc.title, content=doc.content)


@router.get("/workflows/{slug:path}", response_model=DocContent)
async def get_workflow_doc_content(
    slug: str,
    repo: DocumentationRepository = Depends(get_documentation_repository),
) -> DocContent:
    """Public; slug is namespaced (e.g. shs/item-groups)."""
    doc = await repo.get(slug, DocType.WORKFLOW)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow documentation '{slug}' not found.",
        )
    return DocContent(id=doc.slug, title=doc.title, content=doc.content)


@router.get("/{doc_id}", response_model=DocContent)
async def get_doc_content(
    doc_id: str,
    repo: DocumentationRepository = Depends(get_documentation_repository),
) -> DocContent:
    """Public docs only; non-public IDs return 403. Use /admin/content or /super-admin/content for those."""
    doc = await repo.get(doc_id, DocType.USER)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Documentation '{doc_id}' not found.",
        )
    if doc.visibility != DocVisibility.PUBLIC:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This documentation requires authentication.",
        )
    return DocContent(id=doc.slug, title=doc.title, content=doc.content)


@router.get("/admin/content", response_model=DocContent)
async def get_admin_doc(
    user: "CurrentUser" = Depends(require_admin),
    repo: DocumentationRepository = Depends(get_documentation_repository),
) -> DocContent:
    """Admin guide. Requires admin or super-admin."""
    doc = await repo.get("admin", DocType.USER)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Admin documentation not found.",
        )
    return DocContent(id=doc.slug, title=doc.title, content=doc.content)


@router.get("/super-admin/content", response_model=DocContent)
async def get_super_admin_doc(
    user: "CurrentUser" = Depends(require_super_admin),
    repo: DocumentationRepository = Depends(get_documentation_repository),
) -> DocContent:
    """Super-admin only. Deployment and infrastructure documentation."""
    doc = await repo.get("super-admin", DocType.USER)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Super admin documentation not found.",
        )
    return DocContent(id=doc.slug, title=doc.title, content=doc.content)
