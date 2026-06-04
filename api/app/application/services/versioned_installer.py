# api/app/application/services/versioned_installer.py

"""Shared versioned-install helper for catalog runtime tables.

The cross-cutting concern of every catalog installer (providers,
comfyui workflows, future types) is the same:

  1. Validate input (optional jsonschema check).
  2. Compute the deterministic UUID from `(slug, version)`.
  3. Compute a content hash (source_hash) for noop/overwrite distinction.
  4. Look up by id; classify as noop / overwrite / insert.
  5. Apply the per-type field-mapping into the row (insert or update).
  6. Log overwrites with both hash prefixes so accidental version-stomping
     during reseed loops is visible without forcing a 409 / version-bump.

Per-type concerns - extracting catalog content into model fields,
ancillary writes (provider services, manifest fields, etc.) - stay in
the per-type installer. The helper handles only the cross-cutting
concerns.

Used by ProviderInstaller and the ComfyUI workflow installer; future
catalog types (prompts, workflows once they become slug-keyed catalog
tables, etc.) follow the same pattern.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Any, Awaitable, Callable, Optional, Type, TypeVar

from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.services.package_version_service import PackageVersionService

logger = logging.getLogger(__name__)


class Decision(str, Enum):
    """Outcome of a versioned install attempt."""

    INSERT = "insert"
    OVERWRITE = "overwrite"
    NOOP = "noop"


T = TypeVar("T")  # the SQLAlchemy model class


@dataclass
class InstallOutcome:
    """Result of `install_versioned` - what happened, and the resulting row."""

    decision: Decision
    row_id: uuid.UUID
    source_hash: str


async def install_versioned(
    session: AsyncSession,
    model_cls: Type[Any],
    type_name: str,
    content: dict[str, Any],
    apply_content: Callable[[Any, dict[str, Any]], None],
    *,
    validator: Optional[Callable[[dict[str, Any]], None]] = None,
    extra_insert_fields: Optional[dict[str, Any]] = None,
) -> InstallOutcome:
    """Install a versioned catalog row from unified-format content.

    Raises `KeyError` if content is missing `slug` or `version` - no silent defaulting.
    """
    if validator is not None:
        validator(content)

    # Fail loud on missing required fields - no defaulting `version` to "1.0.0".
    slug = content["slug"]
    version = content["version"]

    row_id = uuid.uuid5(uuid.NAMESPACE_DNS, f"{type_name}.{slug}@{version}")
    new_hash = PackageVersionService.compute_source_hash(content)

    existing = await session.get(model_cls, row_id)

    if existing is not None:
        old_hash = getattr(existing, "source_hash", None) or ""
        if old_hash == new_hash:
            return InstallOutcome(Decision.NOOP, row_id, new_hash)

        # Hash mismatch: same (slug, version) is being re-installed with
        # different content. Pre-MVP we silently overwrite, but log the
        # delta so accidental version-stomping during reseed loops is
        # visible. Replace with a 409 once external uploaders exist.
        logger.info(
            f"versioned_install: overwrite {type_name} {slug}@{version} "
            f"(hash {old_hash[:8]} → {new_hash[:8]})"
        )
        existing.version = version
        existing.slug = slug
        apply_content(existing, content)
        existing.source_hash = new_hash
        await session.flush()
        return InstallOutcome(Decision.OVERWRITE, row_id, new_hash)

    # Insert path.
    init_kwargs: dict[str, Any] = {
        "id": row_id,
        "slug": slug,
        "version": version,
        "source_hash": new_hash,
    }
    if extra_insert_fields:
        init_kwargs.update(extra_insert_fields)
    new_row = model_cls(**init_kwargs)
    apply_content(new_row, content)
    session.add(new_row)
    await session.flush()
    return InstallOutcome(Decision.INSERT, row_id, new_hash)


AsyncCallable = Callable[..., Awaitable[Any]]
