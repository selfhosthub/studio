# api/app/application/services/package_management_service.py

"""Application-layer facade for package and provider DB queries."""

import logging
import re
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.provider.models import PackageType, ProviderStatus
from app.infrastructure.persistence.models import (
    PackageVersionModel,
    ProviderCredentialModel,
    ProviderModel,
    ProviderServiceModel,
)

logger = logging.getLogger(__name__)


class PackageManagementService:
    """Application service for package / provider DB operations."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Guard helpers
    # ------------------------------------------------------------------

    async def guard_marketplace_overwrite(self, slug: str) -> None:
        """Reject if a marketplace (non-custom) provider with this slug exists.

        Raises ValueError with a user-facing message if overwrite is blocked.
        """
        result = await self._session.execute(
            select(ProviderModel.provider_type).where(ProviderModel.slug == slug)
        )
        provider_type = result.scalar_one_or_none()
        if provider_type and str(provider_type).lower() != "custom":
            raise ValueError(
                f"Cannot overwrite marketplace provider '{slug}'. "
                "Marketplace providers can only be updated through the marketplace."
            )

    # ------------------------------------------------------------------
    # Listing
    # ------------------------------------------------------------------

    async def list_installed_packages(
        self, package_type: Optional[PackageType] = None
    ) -> List[Dict[str, Any]]:
        """Return list of active installed packages."""
        query = select(PackageVersionModel).where(
            PackageVersionModel.is_active.is_(True),
        )
        if package_type:
            query = query.where(PackageVersionModel.package_type == package_type)

        result = await self._session.execute(query)
        packages = []
        for pv in result.scalars().all():
            # Provider snapshots are flat unified content (no
            # `manifest`/`provider`/`adapter_config` envelope). Other catalog
            # types still wrap content under `catalog_entry`. Resolve which
            # we're looking at by package type.
            catalog_entry = pv.json_content.get("catalog_entry", {})
            if pv.package_type == PackageType.PROVIDER:
                display_source = pv.json_content
                services_preview = pv.json_content.get("services_preview", [])
            else:
                manifest = pv.json_content.get("manifest", {})
                display_source = catalog_entry if catalog_entry else manifest
                services_preview = manifest.get("services_preview", [])
            packages.append(
                {
                    "slug": pv.slug,
                    "package_type": pv.package_type.value,
                    "name": display_source.get("display_name")
                    or display_source.get("name")
                    or pv.slug,
                    "display_name": display_source.get("display_name")
                    or display_source.get("name"),
                    "version": pv.version,
                    "description": display_source.get("description"),
                    "category": display_source.get("category"),
                    "source": pv.source,
                    "is_active": pv.is_active,
                    "created_at": (
                        pv.created_at.isoformat() if pv.created_at else None
                    ),
                    "services_preview": services_preview,
                }
            )
        return packages

    # ------------------------------------------------------------------
    # Usage
    # ------------------------------------------------------------------

    async def get_provider_usage(
        self, provider_id: str
    ) -> Dict[str, Any]:
        """Check how many workflows use a provider (scans steps JSON)."""
        try:
            validated_uuid = UUID(str(provider_id))
            provider_id_str = str(validated_uuid)
        except ValueError:
            return {
                "workflow_count": 0,
                "blueprint_count": 0,
                "affected_orgs": [],
                "details": [],
            }

        escaped_id = re.sub(r"([%_\\])", r"\\\1", provider_id_str)

        result = await self._session.execute(
            text(
                """
                SELECT w.id, w.name, o.name as org_name, o.slug as org_slug
                FROM workflows w
                JOIN organizations o ON w.organization_id = o.id
                WHERE w.steps::text LIKE :pattern
            """
            ),
            {"pattern": f'%"provider_id": "{escaped_id}"%'},
        )
        workflow_rows = result.fetchall()

        affected_orgs: set[str] = set()
        details: List[Dict[str, Any]] = []
        for row in workflow_rows:
            affected_orgs.add(row.org_name)
            details.append(
                {
                    "type": "workflow",
                    "id": str(row.id),
                    "name": row.name,
                    "org_name": row.org_name,
                    "org_slug": row.org_slug,
                }
            )

        return {
            "workflow_count": len(workflow_rows),
            "blueprint_count": 0,
            "affected_orgs": list(affected_orgs),
            "details": details,
        }

    # ------------------------------------------------------------------
    # Slug resolution
    # ------------------------------------------------------------------

    async def resolve_provider_slug(self, package_name: str) -> str:
        """Resolve provider slug from package name using the database."""
        result = await self._session.execute(
            select(ProviderModel.slug).where(
                ProviderModel.slug == package_name,
                ProviderModel.status == ProviderStatus.ACTIVE,
            )
        )
        slug = result.scalar_one_or_none()
        if slug:
            return slug

        pv_result = await self._session.execute(
            select(PackageVersionModel.slug).where(
                PackageVersionModel.package_type == PackageType.PROVIDER,
                PackageVersionModel.is_active.is_(True),
                PackageVersionModel.json_content["slug"].astext
                == package_name,
            )
        )
        slug = pv_result.scalar_one_or_none()
        return slug or package_name

    # ------------------------------------------------------------------
    # Provider lookup
    # ------------------------------------------------------------------

    async def get_provider_id_by_slug(self, slug: str) -> Optional[str]:
        """Return provider UUID as string, or None."""
        result = await self._session.execute(
            select(ProviderModel.id).where(ProviderModel.slug == slug)
        )
        provider_id = result.scalar_one_or_none()
        return str(provider_id) if provider_id else None

    async def get_provider_by_slug(self, slug: str) -> Optional[Dict[str, Any]]:
        """Return provider row as dict, or None."""
        result = await self._session.execute(
            select(ProviderModel).where(ProviderModel.slug == slug)
        )
        provider = result.scalar_one_or_none()
        if not provider:
            return None
        return {
            "id": provider.id,
            "name": provider.name,
            "slug": provider.slug,
            "status": provider.status,
            "version": provider.version,
        }

    # ------------------------------------------------------------------
    # Uninstall (soft-delete)
    # ------------------------------------------------------------------

    async def soft_delete_provider(
        self, provider_id: UUID, provider_slug: str
    ) -> Optional[str]:
        """Soft-delete provider: deactivate credentials, services, provider, package_version.

        Returns the provider display_name (for adapter unregistration), or None.
        """
        # Get display name
        result = await self._session.execute(
            select(ProviderModel.name).where(ProviderModel.id == provider_id)
        )
        display_name = result.scalar_one_or_none()

        await self._session.execute(
            update(ProviderCredentialModel)
            .where(ProviderCredentialModel.provider_id == provider_id)
            .values(is_active=False)
        )

        await self._session.execute(
            update(ProviderServiceModel)
            .where(ProviderServiceModel.provider_id == provider_id)
            .values(is_active=False)
        )

        await self._session.execute(
            update(ProviderModel)
            .where(ProviderModel.id == provider_id)
            .values(status=ProviderStatus.INACTIVE)
        )

        await self._session.execute(
            update(PackageVersionModel)
            .where(
                PackageVersionModel.slug == provider_slug,
                PackageVersionModel.package_type == PackageType.PROVIDER,
            )
            .values(is_active=False)
        )

        await self._session.commit()
        logger.info(f"Soft-deleted provider '{provider_slug}' from database")
        return display_name

    # ------------------------------------------------------------------
    # Reinstall (reactivate)
    # ------------------------------------------------------------------

    async def reactivate_provider(
        self, provider_id: UUID, provider_slug: str
    ) -> List[str]:
        """Reactivate a soft-deleted provider.

        Returns list of reactivated service_ids.
        """
        await self._session.execute(
            update(ProviderModel)
            .where(ProviderModel.id == provider_id)
            .values(status=ProviderStatus.ACTIVE)
        )

        await self._session.execute(
            update(ProviderServiceModel)
            .where(ProviderServiceModel.provider_id == provider_id)
            .values(is_active=True)
        )

        await self._session.execute(
            update(ProviderCredentialModel)
            .where(ProviderCredentialModel.provider_id == provider_id)
            .values(is_active=True)
        )

        await self._session.execute(
            update(PackageVersionModel)
            .where(
                PackageVersionModel.slug == provider_slug,
                PackageVersionModel.package_type == PackageType.PROVIDER,
            )
            .values(is_active=True)
        )

        await self._session.commit()

        svc_result = await self._session.execute(
            select(ProviderServiceModel.service_id).where(
                ProviderServiceModel.provider_id == provider_id,
                ProviderServiceModel.is_active.is_(True),
            )
        )
        services = [row[0] for row in svc_result.all()]

        logger.info(f"Reinstalled provider '{provider_slug}' from database")
        return services

    # ------------------------------------------------------------------
    # Version history
    # ------------------------------------------------------------------

    async def list_package_versions(
        self, slug: str, package_type: PackageType
    ) -> List[Dict[str, Any]]:
        """Return version history for a package, newest first."""
        result = await self._session.execute(
            select(PackageVersionModel)
            .where(
                PackageVersionModel.slug == slug,
                PackageVersionModel.package_type == package_type,
            )
            .order_by(PackageVersionModel.created_at.desc())
        )
        versions = result.scalars().all()
        return [
            {
                "version": v.version,
                "source": v.source,
                "source_hash": v.source_hash,
                "is_active": v.is_active,
                "created_at": (
                    v.created_at.isoformat() if v.created_at else None
                ),
            }
            for v in versions
        ]

    # ------------------------------------------------------------------
    # Catalog install helpers
    # ------------------------------------------------------------------

    async def get_active_provider_slugs(self) -> set[str]:
        """Return set of slugs for currently active providers."""
        result = await self._session.execute(
            select(ProviderModel.slug).where(
                ProviderModel.status == ProviderStatus.ACTIVE
            )
        )
        return {row[0] for row in result.all()}
