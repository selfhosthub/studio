# api/app/application/services/comfyui_service_builder.py

"""Maintains comfyui provider services' dynamic surface (ST114, re-ruled 2026-08-03).

The service is a parameter contract owned by the provider definition; packages
conform to it (validated at upload). The builder maintains only the dynamic
parts: the `package` (workflow) enum and queue metadata. Per-package parameter
bounds remain enforced worker-side against the manifest.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.common.value_objects import Visibility
from app.domain.provider.models import PackageType
from app.infrastructure.persistence.models import (
    ComfyUIWorkflowModel,
    ProviderServiceModel,
)
from app.infrastructure.services.package_version_service import PackageVersionService

logger = logging.getLogger(__name__)


def _active_manifests(rows: List[ComfyUIWorkflowModel]) -> List[Dict[str, Any]]:
    """Highest-version manifest-bearing package per slug."""
    best: Dict[str, Tuple[Tuple[int, ...], Dict[str, Any]]] = {}
    for row in rows:
        content = row.json_content or {}
        if not content.get("service") or not content.get("parameters"):
            continue
        try:
            key = tuple(int(p) for p in (row.version or "0").split("."))
        except ValueError:
            key = (0,)
        current = best.get(row.slug)
        if current is None or key > current[0]:
            best[row.slug] = (key, content)
    return [content for _, content in best.values()]


PACKAGE_REF_SEP = "::"


def package_ref(slug: str, model_id: Optional[str]) -> str:
    """Encode one selectable workflow entry: package slug, optionally a model
    variant. The parameter key is `package` (title: Workflow); the existing
    `workflow` key stays the inline-graph escape hatch."""
    return f"{slug}{PACKAGE_REF_SEP}{model_id}" if model_id else slug


def parse_package_ref(value: str) -> Tuple[str, Optional[str]]:
    """(package slug, model id or None) from a package parameter value."""
    if PACKAGE_REF_SEP in value:
        slug, model_id = value.split(PACKAGE_REF_SEP, 1)
        return slug, model_id or None
    return value, None


def _build_package_property(
    packages: List[Dict[str, Any]], existing: Optional[Dict[str, Any]]
) -> Optional[Dict[str, Any]]:
    """One flattened dropdown: each package's model variants are entries of
    the same workflow, single- or no-model packages get one entry."""
    ids: List[str] = []
    labels: List[str] = []
    default: Optional[str] = None
    for package in sorted(packages, key=lambda p: p.get("slug", "")):
        slug = package.get("slug", "")
        name = package.get("name", slug)
        models = package.get("models", [])
        if not models:
            ids.append(package_ref(slug, None))
            labels.append(name)
            continue
        for model in models:
            value = package_ref(slug, model["id"])
            ids.append(value)
            if len(models) == 1:
                labels.append(name)
            else:
                labels.append(f"{name} ({model.get('label', model['id'])})")
            if model.get("default"):
                default = value
    if not ids:
        return None
    prop: Dict[str, Any] = dict(
        existing or {"title": "Workflow", "ui": {"section": "basic", "order": 0.1}}
    )
    prop["type"] = "string"
    prop["enum"] = ids
    prop["enumNames"] = labels
    if default:
        prop["default"] = default
    elif "default" in prop and prop["default"] not in ids:
        del prop["default"]
    return prop


def build_parameter_schema(
    packages: List[Dict[str, Any]], existing_schema: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    """The service's contract with the workflow dropdown maintained.

    The service is a parameter contract (ruling 2026-08-03): the provider's
    service definition owns the parameters and packages conform, validated at
    upload. The builder's only dynamic output is the `package` enum. The
    retired `model` property is stripped from stored rows on rebuild.
    """
    schema = dict(existing_schema or {})
    schema.setdefault("type", "object")
    schema.setdefault("required", [])
    properties = dict(schema.get("properties", {}))
    properties.pop("model", None)

    package_prop = _build_package_property(packages, properties.get("package"))
    if package_prop:
        properties["package"] = package_prop
    else:
        properties.pop("package", None)

    schema["properties"] = properties
    schema["required"] = [r for r in schema["required"] if r != "model"]
    return schema


async def _reconcile_catalog_visibility(
    session: AsyncSession, rows: List[ComfyUIWorkflowModel]
) -> None:
    """Stamp catalog installs public; uploads stay as published.

    Installed rows predate visibility stamping (model default is private).
    Catalog packages are public content by provenance; uploads are the rows
    whose ledger entry carries catalog_entry.uploaded and keep their gate.
    Idempotent, runs on every rebuild, covers fresh installs in-request.
    """
    private_rows = [r for r in rows if r.visibility == Visibility.PRIVATE]
    if not private_rows:
        return
    pvs = await PackageVersionService.list_active(session, PackageType.COMFYUI)
    uploaded_slugs = {
        pv.slug
        for pv in pvs
        if (pv.json_content or {}).get("catalog_entry", {}).get("uploaded")
    }
    changed = False
    for row in private_rows:
        if row.slug not in uploaded_slugs:
            row.visibility = Visibility.PUBLIC
            changed = True
    if changed:
        await session.flush()


async def rebuild_comfyui_services(session: AsyncSession) -> List[str]:
    """Refresh provider service rows from installed package manifests.

    Returns the service_ids updated. A manifest service with no matching
    provider service row is logged and skipped: the provider shell owns
    service existence, manifests own the contract.
    """
    result = await session.execute(
        select(ComfyUIWorkflowModel).where(ComfyUIWorkflowModel.is_active.is_(True))
    )
    rows_all = list(result.scalars())
    await _reconcile_catalog_visibility(session, rows_all)
    # The publish gate reaches the dropdown: only staging/public packages are
    # selectable. A private row is an unpublished upload (catalog installs are
    # stamped public at install; _reconcile_catalog_visibility self-heals
    # pre-stamp rows).
    selectable = [
        r
        for r in rows_all
        if r.visibility in (Visibility.PUBLIC, Visibility.STAGING)
    ]
    manifests = _active_manifests(selectable)

    by_service: Dict[str, List[Dict[str, Any]]] = {}
    for content in manifests:
        by_service.setdefault(content["service"]["id"], []).append(content)

    updated: List[str] = []
    for service_id, packages in by_service.items():
        rows = (
            (
                await session.execute(
                    select(ProviderServiceModel).where(
                        ProviderServiceModel.service_id.like(f"%.{service_id}")
                    )
                )
            )
            .scalars()
            .all()
        )
        if not rows:
            logger.warning(
                f"No provider service row matches manifest service '{service_id}'"
            )
            continue
        queue = packages[0]["service"]["queue"]
        style_presets = any(
            p.get("capabilities", {}).get("style_presets") for p in packages
        )
        for row in rows:
            row.parameter_schema = build_parameter_schema(
                packages, row.parameter_schema
            )
            metadata = dict(row.client_metadata or {})
            metadata["queue"] = queue
            metadata["supports_image_presets"] = style_presets
            row.client_metadata = metadata
            updated.append(row.service_id)
    if updated:
        await session.flush()
        logger.info(f"Rebuilt comfyui services from manifests: {sorted(updated)}")
    return updated
