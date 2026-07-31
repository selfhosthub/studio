# api/app/application/services/comfyui_service_builder.py

"""Builds provider service definitions from comfyui package manifests (ST114).

The manifest is authoritative for the contract: which parameters exist, their
types, bounds, defaults and options, the model enum, and the queue. Existing
row properties keep their presentation fields (title, description, ui) where
the manifest does not override them.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.persistence.models import (
    ComfyUIWorkflowModel,
    ProviderServiceModel,
)

logger = logging.getLogger(__name__)

_TYPE_MAP = {
    "string": "string",
    "integer": "integer",
    "float": "number",
    "boolean": "boolean",
    "enum": "string",
    "array": "array",
}


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


def _option_pairs(spec: Dict[str, Any]) -> Tuple[List[Any], Optional[List[str]]]:
    values, labels = [], []
    labeled = False
    for opt in spec.get("options", []):
        if isinstance(opt, dict):
            values.append(opt["value"])
            labels.append(opt["label"])
            labeled = True
        else:
            values.append(opt)
            labels.append(str(opt))
    return values, (labels if labeled else None)


def _build_property(
    name: str, spec: Dict[str, Any], existing: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    """Manifest facts overlaid on the existing property's presentation."""
    prop = dict(existing or {})
    prop["type"] = _TYPE_MAP.get(spec.get("type", "string"), "string")
    if "default" in spec:
        prop["default"] = spec["default"]
    if "min" in spec:
        prop["minimum"] = spec["min"]
    if "max" in spec:
        prop["maximum"] = spec["max"]
    if "title" in spec:
        prop["title"] = spec["title"]
    if spec.get("type") == "enum":
        values, labels = _option_pairs(spec)
        prop["enum"] = values
        if labels:
            prop["enumNames"] = labels
        elif "enumNames" in prop and len(prop["enumNames"]) != len(values):
            del prop["enumNames"]
    if spec.get("type") == "array" and "items" not in prop:
        prop["items"] = {"type": "string"}
    ui = dict(prop.get("ui") or {})
    for key, value in (spec.get("ui") or {}).items():
        ui.setdefault(key, value)
    if spec.get("when") and "visibleWhen" not in ui:
        ui["visibleWhen"] = {
            "field": spec["when"],
            "condition": "equals",
            "value": True,
        }
    if ui:
        prop["ui"] = ui
    return prop


def _build_model_property(
    packages: List[Dict[str, Any]], existing: Optional[Dict[str, Any]]
) -> Optional[Dict[str, Any]]:
    ids: List[str] = []
    labels: List[str] = []
    default: Optional[str] = None
    for package in sorted(packages, key=lambda p: p.get("slug", "")):
        for model in package.get("models", []):
            ids.append(model["id"])
            labels.append(model.get("label", model["id"]))
            if model.get("default"):
                default = model["id"]
    if not ids:
        return None
    prop: Dict[str, Any] = dict(
        existing or {"title": "Model", "ui": {"section": "basic", "order": 0.1}}
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
    """Assemble one service's parameter_schema from its packages' manifests."""
    existing_props = (existing_schema or {}).get("properties", {})
    properties: Dict[str, Any] = {}

    model_prop = _build_model_property(packages, existing_props.get("model"))
    if model_prop:
        properties["model"] = model_prop

    required: List[str] = []
    for package in sorted(packages, key=lambda p: p.get("slug", "")):
        for name, spec in package.get("parameters", {}).items():
            if name not in properties:
                properties[name] = _build_property(
                    name, spec, existing_props.get(name)
                )
            if spec.get("required") and name not in required:
                required.append(name)

    return {"type": "object", "required": required, "properties": properties}


async def rebuild_comfyui_services(session: AsyncSession) -> List[str]:
    """Refresh provider service rows from installed package manifests.

    Returns the service_ids updated. A manifest service with no matching
    provider service row is logged and skipped: the provider shell owns
    service existence, manifests own the contract.
    """
    result = await session.execute(
        select(ComfyUIWorkflowModel).where(ComfyUIWorkflowModel.is_active.is_(True))
    )
    manifests = _active_manifests(list(result.scalars()))

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
