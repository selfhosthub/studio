# api/app/infrastructure/services/package_version_service.py

"""Records, queries, and manages package version snapshots across all catalog types."""

import hashlib
import json
import logging
import uuid
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.provider.models import PackageType
from app.infrastructure.persistence.models import PackageVersionModel

logger = logging.getLogger(__name__)

# Namespaces reserved for first-party Self-Host Studio packages. Only callers
# that pass `allow_reserved=True` (the first-party publish/install paths) may
# write rows under these prefixes. Everything else gets `custom/`.
RESERVED_NAMESPACES: frozenset[str] = frozenset({"shs"})
NEUTRAL_NAMESPACE: str = "custom"


def slug_is_reserved(slug: str) -> bool:
    """True if the slug's namespace prefix is reserved for first-party content."""
    return "/" in slug and slug.split("/", 1)[0] in RESERVED_NAMESPACES


class ReservedNamespaceError(ValueError):
    """Raised when a non-marketplace writer attempts a reserved-namespace slug.

    Why: `shs/*` denotes first-party origin (Self-Host Studio). A local upload
    or import reaching that namespace would mis-attribute third-party content
    as official. The trust boundary is the API, not the UI — enforce here.
    """


class PackageVersionService:
    """Records and queries package version snapshots across all catalog types."""

    @staticmethod
    def compute_source_hash(content: dict[str, Any]) -> str:
        """Compute SHA-256 hash of normalized JSON content."""
        normalized = json.dumps(content, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(normalized.encode()).hexdigest()

    @staticmethod
    def _ensure_namespaced(
        slug: str,
        *,
        allow_reserved: bool = False,
    ) -> str:
        """Ensure slug has a namespace prefix to satisfy ck_package_versions_slug_namespaced.

        Storage requires `<namespace>/<slug>`. Reserved namespaces (e.g. `shs/`)
        may only be written when `allow_reserved=True` — a first-party
        authorization decision made by the caller, not inferred from
        provenance. Bare slugs always default to `custom/`; `shs/` is never
        inferred. (ST248)
        """
        if "/" in slug:
            prefix = slug.split("/", 1)[0]
            if prefix in RESERVED_NAMESPACES and not allow_reserved:
                raise ReservedNamespaceError(
                    f"Namespace '{prefix}/' is reserved for first-party packages"
                )
            return slug
        return f"{NEUTRAL_NAMESPACE}/{slug}"

    @staticmethod
    async def record_version(
        session: AsyncSession,
        package_type: PackageType,
        slug: str,
        version: str,
        json_content: dict[str, Any],
        source_hash: str,
        created_by: uuid.UUID,
        *,
        allow_reserved: bool = False,
    ) -> PackageVersionModel:
        """Deactivate previous active versions, insert new active version.

        Returns the newly created PackageVersionModel.
        """
        slug = PackageVersionService._ensure_namespaced(
            slug, allow_reserved=allow_reserved
        )
        # Deactivate previous active versions for this slug+type
        result = await session.execute(
            select(PackageVersionModel).where(
                PackageVersionModel.slug == slug,
                PackageVersionModel.package_type == package_type,
                PackageVersionModel.is_active.is_(True),
            )
        )
        for old_version in result.scalars().all():
            old_version.is_active = False

        # Reuse an existing row for this exact version if one exists. The unique
        # constraint uix_package_versions_slug_type_version is on (slug,
        # package_type, version) regardless of is_active, so a prior install of
        # this version that was soft-deleted (uninstall) must be reactivated and
        # refreshed in place - re-inserting would violate the constraint.
        existing_result = await session.execute(
            select(PackageVersionModel).where(
                PackageVersionModel.slug == slug,
                PackageVersionModel.package_type == package_type,
                PackageVersionModel.version == version,
            )
        )
        existing = existing_result.scalar_one_or_none()
        if existing is not None:
            existing.json_content = json_content
            existing.source_hash = source_hash
            existing.is_active = True
            existing.created_by = created_by
            await session.commit()
            return existing

        # Insert new active version
        pv = PackageVersionModel(
            package_type=package_type,
            slug=slug,
            version=version,
            json_content=json_content,
            source_hash=source_hash,
            is_active=True,
            created_by=created_by,
        )
        session.add(pv)
        await session.commit()
        return pv

    @staticmethod
    async def soft_delete(
        session: AsyncSession,
        package_type: PackageType,
        slug: str,
    ) -> bool:
        """Set is_active=False on all active versions for slug+type.

        Returns True if any versions were deactivated.
        """
        slug = PackageVersionService._ensure_namespaced(slug, allow_reserved=True)
        result = await session.execute(
            select(PackageVersionModel).where(
                PackageVersionModel.slug == slug,
                PackageVersionModel.package_type == package_type,
                PackageVersionModel.is_active.is_(True),
            )
        )
        versions = result.scalars().all()
        for v in versions:
            v.is_active = False
        await session.commit()
        return len(versions) > 0

    @staticmethod
    async def reactivate(
        session: AsyncSession,
        package_type: PackageType,
        slug: str,
    ) -> bool:
        """Set is_active=True on the most recent version for slug+type.

        Returns True if a version was reactivated.
        """
        slug = PackageVersionService._ensure_namespaced(slug, allow_reserved=True)
        result = await session.execute(
            select(PackageVersionModel)
            .where(
                PackageVersionModel.slug == slug,
                PackageVersionModel.package_type == package_type,
            )
            .order_by(PackageVersionModel.created_at.desc())
            .limit(1)
        )
        latest = result.scalar_one_or_none()
        if latest:
            latest.is_active = True
            await session.commit()
            return True
        return False

    @staticmethod
    async def get_active_by_slug(
        session: AsyncSession,
        package_type: PackageType,
        slug: str,
    ) -> Optional[PackageVersionModel]:
        """Get the active package version for a specific slug+type, or None."""
        slug = PackageVersionService._ensure_namespaced(slug, allow_reserved=True)
        result = await session.execute(
            select(PackageVersionModel).where(
                PackageVersionModel.slug == slug,
                PackageVersionModel.package_type == package_type,
                PackageVersionModel.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_active(
        session: AsyncSession,
        package_type: Optional[PackageType] = None,
    ) -> list[PackageVersionModel]:
        """List active package versions, optionally filtered by type."""
        query = select(PackageVersionModel).where(
            PackageVersionModel.is_active.is_(True),
        )
        if package_type is not None:
            query = query.where(PackageVersionModel.package_type == package_type)
        result = await session.execute(query)
        return list(result.scalars().all())

    @staticmethod
    async def list_versions(
        session: AsyncSession,
        package_type: PackageType,
        slug: str,
    ) -> list[PackageVersionModel]:
        """All versions for a slug+type, newest first."""
        slug = PackageVersionService._ensure_namespaced(slug, allow_reserved=True)
        result = await session.execute(
            select(PackageVersionModel)
            .where(
                PackageVersionModel.slug == slug,
                PackageVersionModel.package_type == package_type,
            )
            .order_by(PackageVersionModel.created_at.desc())
        )
        return list(result.scalars().all())
