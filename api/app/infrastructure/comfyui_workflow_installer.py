# api/app/infrastructure/comfyui_workflow_installer.py

"""ComfyUI workflow catalog installer. Validates against the workflow schema at install time."""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import jsonschema
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.services.versioned_installer import (
    Decision,
    InstallOutcome,
    install_versioned,
)
from app.infrastructure.errors import safe_error_message
from app.infrastructure.persistence.models import ComfyUIWorkflowModel

logger = logging.getLogger(__name__)

# Schema path candidates. Source of truth lives in studio-cat;
# deploy mirrors to studio-community. The two layouts we run under:
#   - Docker:  studio-cat mounted at /app/studio-cat  (api root = /app)
#   - Host:    studio-cat at <monorepo>/studio-cat    (api root = <monorepo>/api)
# The api package root is parents[2]; studio-cat sits beside it (Docker)
# or one level above it (host).
_API_ROOT = Path(__file__).resolve().parents[2]
_SCHEMA_REL = Path("studio-cat") / "schemas" / "comfyui-workflow.schema.json"
_SCHEMA_CANDIDATES = (
    _API_ROOT / _SCHEMA_REL,           # Docker: /app/studio-cat/...
    _API_ROOT.parent / _SCHEMA_REL,    # Host:   <monorepo>/studio-cat/...
)


def _load_schema() -> dict[str, Any]:
    for candidate in _SCHEMA_CANDIDATES:
        if candidate.exists():
            return json.loads(candidate.read_text())
    raise FileNotFoundError(
        "ComfyUI workflow schema not found. Tried: "
        + ", ".join(str(c) for c in _SCHEMA_CANDIDATES)
        + ". Studio-cat checkout / submodule may be missing."
    )


_SCHEMA: Optional[dict[str, Any]] = None


def _get_schema() -> dict[str, Any]:
    global _SCHEMA
    if _SCHEMA is None:
        _SCHEMA = _load_schema()
    return _SCHEMA


def _validate(content: dict[str, Any]) -> None:
    """Raise `jsonschema.ValidationError` if `content` fails schema validation."""
    jsonschema.validate(instance=content, schema=_get_schema())


@dataclass
class ComfyUIInstallResult:
    """Result of a ComfyUI workflow install."""

    slug: str
    version: str
    workflow_id: uuid.UUID
    decision: Decision
    success: bool = True
    error: Optional[str] = None
    services_installed: list[str] = field(default_factory=list)


class ComfyUIWorkflowInstaller:
    """Installs ComfyUI workflow packages into the catalog."""

    async def install_from_data(
        self,
        content: dict[str, Any],
        session: AsyncSession,
        created_by: uuid.UUID,
        *,
        slug_hint: str | None = None,
    ) -> ComfyUIInstallResult:
        """Install a ComfyUI workflow from an already-parsed unified dict.

        The shared core behind the upload route and the seeder - validate +
        persist with no file coupling. `slug_hint` supplies a fallback slug
        (e.g. the source filename stem) when the dict omits one.
        """
        # If slug is missing, derive from the hint (matches the providers
        # convention). Write back so the schema validation sees a slug, and
        # the helper picks it up.
        slug = content.get("slug") or slug_hint or "unknown"
        content["slug"] = slug

        try:
            _validate(content)
        except jsonschema.ValidationError as e:
            return ComfyUIInstallResult(
                slug=slug,
                version=content.get("version", ""),
                workflow_id=uuid.uuid4(),
                decision=Decision.NOOP,
                success=False,
                error=f"Schema validation failed: {e.message}",
            )

        version = content["version"]

        def apply_workflow_content(
            row: ComfyUIWorkflowModel, data: dict[str, Any]
        ) -> None:
            row.name = data["name"]
            row.description = data.get("description")
            row.category = data.get("category")
            row.author = data.get("author")
            row.json_content = data
            row.is_active = True

        try:
            outcome: InstallOutcome = await install_versioned(
                session,
                ComfyUIWorkflowModel,
                type_name="comfyui_workflow",
                content=content,
                apply_content=apply_workflow_content,
                extra_insert_fields={"created_by": created_by},
            )
        except Exception as e:
            logger.exception(f"ComfyUI workflow install failed for {slug}@{version}")
            return ComfyUIInstallResult(
                slug=slug,
                version=version,
                workflow_id=uuid.uuid4(),
                decision=Decision.NOOP,
                success=False,
                error=safe_error_message(e),
            )

        logger.info(
            f"ComfyUI workflow install: {slug}@{version} → {outcome.decision.value}"
        )
        return ComfyUIInstallResult(
            slug=slug,
            version=version,
            workflow_id=outcome.row_id,
            decision=outcome.decision,
            success=True,
        )
