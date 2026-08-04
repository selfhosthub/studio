# api/app/application/services/catalog_merge_service.py

"""The single sanctioned cross-org seam for marketplace catalog reads.

`merge_with_marketplace()` is the ONE place the cross-org RLS boundary is
crossed to surface a super-org's *managed* catalog packages (workflows the
super-admin flipped to public/staging) into another org's marketplace listing.

SECURITY BOUNDARY: row-level security is bypassed here (a service-account
session satisfies the `*_service_bypass` policy), so the visibility filter in
this function *is* tenant isolation - a bug here is a cross-org data leak with
the same blast radius as a missing authorization check. It is covered by
negative authz tests (an org without the staging flag must never receive
staging packages; nobody but the super-org sees private). A pre-commit
grep-guard enforces that no other call site invokes the service-bypass on the
workflows/prompts/comfyui tables for catalog reads.
"""

from typing import List
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.dtos.catalog_dto import CatalogEntry, CatalogOrigin
from app.domain.common.value_objects import Visibility
from app.domain.provider.models import PackageType
from app.infrastructure.persistence.models import (
    ComfyUIWorkflowModel,
    OrganizationModel,
    ProviderModel,
    PromptModel,
    WorkflowModel,
)


def _semver_key(version: str) -> tuple:
    """Coarse semver sort key: '1.2.3' -> (1, 2, 3). Non-numeric parts sort as
    0. Good enough to pick the highest version for catalog display."""
    key = []
    for part in (version or "0").split("."):
        try:
            key.append(int(part))
        except ValueError:
            key.append(0)
    return tuple(key)


async def caller_is_staging(session: AsyncSession, org_id: UUID) -> bool:
    """Return the caller org's staging-tenant flag."""
    row = (
        await session.execute(
            select(OrganizationModel.is_staging).where(
                OrganizationModel.id == org_id
            )
        )
    ).scalar_one_or_none()
    return bool(row)


def _allowed_visibilities(caller_is_staging: bool) -> List[Visibility]:
    """The visibility labels a caller org is entitled to see in the merged
    catalog. Public is universal; staging is gated on the org's staging flag.
    Private is never returned to anyone but the super-org's own management view
    (which does not go through this cross-org merge)."""
    allowed = [Visibility.PUBLIC]
    if caller_is_staging:
        allowed.append(Visibility.STAGING)
    return allowed


def _workflow_to_entry(model: WorkflowModel) -> CatalogEntry:
    return CatalogEntry(
        id=model.slug,
        type=PackageType.WORKFLOW,
        origin=CatalogOrigin.MANAGED,
        install_ref=str(model.id),
        visibility=model.visibility,
        name=model.name,
        description=model.description,
    )


async def merge_with_marketplace(
    bypass_session: AsyncSession,
    *,
    system_org_id: UUID,
    caller_org_id: UUID,
    caller_is_staging: bool,
) -> List[CatalogEntry]:
    """Return the super-org's managed workflows the caller is entitled to see.

    `bypass_session` MUST be a service-account session (RLS-bypassing); this is
    the only function permitted to use it for a cross-org catalog read.

    The caller's own org never appears as a "managed" marketplace entry to
    itself - if the caller *is* the super-org it manages these directly and
    sees them through its normal (RLS-scoped) management view, not here.
    """
    if caller_org_id == system_org_id:
        # The super-org manages these directly; nothing to merge in for itself.
        return []

    allowed = _allowed_visibilities(caller_is_staging)
    result = await bypass_session.execute(
        select(WorkflowModel).where(
            WorkflowModel.organization_id == system_org_id,
            WorkflowModel.visibility.in_(allowed),
        )
    )
    return [_workflow_to_entry(row) for row in result.scalars().all()]


def _prompt_to_entry(model: PromptModel) -> CatalogEntry:
    return CatalogEntry(
        id=model.slug,
        type=PackageType.PROMPT,
        origin=CatalogOrigin.MANAGED,
        install_ref=str(model.id),
        visibility=model.visibility,
        name=model.name,
        description=model.description,
    )


async def merge_prompts_with_marketplace(
    bypass_session: AsyncSession,
    *,
    system_org_id: UUID,
    caller_org_id: UUID,
    caller_is_staging: bool,
) -> List[CatalogEntry]:
    """Prompt counterpart of :func:`merge_with_marketplace`. Same cross-org
    seam and visibility-as-tenant-isolation contract; returns the super-org's
    managed prompts the caller is entitled to see."""
    if caller_org_id == system_org_id:
        return []

    allowed = _allowed_visibilities(caller_is_staging)
    result = await bypass_session.execute(
        select(PromptModel).where(
            PromptModel.organization_id == system_org_id,
            PromptModel.visibility.in_(allowed),
        )
    )
    return [_prompt_to_entry(row) for row in result.scalars().all()]


def _comfyui_to_entry(model: ComfyUIWorkflowModel) -> CatalogEntry:
    return CatalogEntry(
        id=model.slug,
        type=PackageType.COMFYUI,
        origin=CatalogOrigin.MANAGED,
        install_ref=str(model.id),
        visibility=model.visibility,
        name=model.name,
        description=model.description,
        category=model.category,
        version=model.version,
    )


async def merge_comfyui_with_marketplace(
    session: AsyncSession,
    *,
    caller_is_staging: bool,
    include_private: bool = False,
) -> List[CatalogEntry]:
    """ComfyUI counterpart. ComfyUI is a GLOBAL catalog table (no
    organization_id, not RLS-protected) - the super-org publishes by flipping a
    catalog row's visibility, so there is no org scoping and no cross-org
    bypass. The visibility filter is still the entitlement gate: public reaches
    all orgs, staging only staging organizations, private never surfaces here
    unless *include_private* (the super-admin custom view managing unpublished
    uploads). Only the highest-semver active row per slug is returned."""
    allowed = list(_allowed_visibilities(caller_is_staging))
    if include_private:
        allowed.append(Visibility.PRIVATE)
    result = await session.execute(
        select(ComfyUIWorkflowModel).where(
            ComfyUIWorkflowModel.is_active.is_(True),
            ComfyUIWorkflowModel.visibility.in_(allowed),
        )
    )
    by_slug: dict[str, CatalogEntry] = {}
    for row in result.scalars().all():
        existing = by_slug.get(row.slug)
        if existing is None or _semver_key(row.version) > _semver_key(
            existing.version or "0"
        ):
            by_slug[row.slug] = _comfyui_to_entry(row)
    return list(by_slug.values())


def _provider_to_entry(model: ProviderModel) -> CatalogEntry:
    return CatalogEntry(
        id=model.slug,
        type=PackageType.PROVIDER,
        origin=CatalogOrigin.MANAGED,
        install_ref=str(model.id),
        visibility=model.visibility,
        operational_status=model.operational_status,
        name=model.name,
        description=model.description,
        version=model.version,
        provider_id=str(model.id),
    )


async def merge_providers_with_marketplace(
    session: AsyncSession,
    *,
    caller_is_staging: bool,
) -> List[CatalogEntry]:
    """Provider counterpart. Providers are a GLOBAL catalog table (no
    organization_id, not RLS-protected) - the same shape as comfyui: the
    super-org publishes by flipping a catalog row's visibility, so there is no
    org scoping and no cross-org bypass. The visibility filter is the
    entitlement gate: public reaches all orgs, staging only staging organizations,
    private never surfaces here. Unlike the copy-install types, providers WIRE
    ``operational_status`` - it is carried through on each entry so the
    marketplace can render installed-vs-deactivated. Only the highest-semver row
    per slug is returned (latest published)."""
    allowed = _allowed_visibilities(caller_is_staging)
    result = await session.execute(
        select(ProviderModel).where(ProviderModel.visibility.in_(allowed))
    )
    by_slug: dict[str, CatalogEntry] = {}
    for row in result.scalars().all():
        existing = by_slug.get(row.slug)
        if existing is None or _semver_key(row.version) > _semver_key(
            existing.version or "0"
        ):
            by_slug[row.slug] = _provider_to_entry(row)
    return list(by_slug.values())
