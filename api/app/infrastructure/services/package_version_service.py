# api/app/infrastructure/services/package_version_service.py

"""Records, queries, and manages package version snapshots across all catalog types."""

import hashlib
import json
import logging
import uuid
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.provider.models import PackageSource, PackageType
from app.infrastructure.persistence.models import PackageVersionModel

logger = logging.getLogger(__name__)


class PackageVersionService:
    """Records and queries package version snapshots across all catalog types."""

    @staticmethod
    def compute_source_hash(content: dict[str, Any]) -> str:
        """Compute SHA-256 hash of normalized JSON content."""
        normalized = json.dumps(content, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(normalized.encode()).hexdigest()

    @staticmethod
    async def record_version(
        session: AsyncSession,
        package_type: PackageType,
        slug: str,
        version: str,
        json_content: dict[str, Any],
        source_hash: str,
        created_by: uuid.UUID,
        source: PackageSource = PackageSource.MARKETPLACE,
    ) -> PackageVersionModel:
        """Deactivate previous active versions, insert new active version.

        Returns the newly created PackageVersionModel.
        """
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

        # Insert new active version
        pv = PackageVersionModel(
            package_type=package_type,
            slug=slug,
            version=version,
            json_content=json_content,
            source_hash=source_hash,
            is_active=True,
            source=source,
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
        result = await session.execute(
            select(PackageVersionModel)
            .where(
                PackageVersionModel.slug == slug,
                PackageVersionModel.package_type == package_type,
            )
            .order_by(PackageVersionModel.created_at.desc())
        )
        return list(result.scalars().all())
