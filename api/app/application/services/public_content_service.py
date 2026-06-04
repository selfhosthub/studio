# api/app/application/services/public_content_service.py

"""Application-layer facade for unauthenticated public content endpoints."""

import logging
from typing import Any, Dict, List, Optional

from app.domain.organization.repository import OrganizationRepository, UserRepository
from app.domain.site_content.repository import SiteContentRepository

logger = logging.getLogger(__name__)


class PublicContentService:
    """Service for public (unauthenticated) content queries."""

    def __init__(
        self,
        organization_repo: OrganizationRepository,
        user_repo: UserRepository,
        site_content_repo: SiteContentRepository,
    ) -> None:
        self._org_repo = organization_repo
        self._user_repo = user_repo
        self._site_content_repo = site_content_repo

    # ------------------------------------------------------------------
    # Branding
    # ------------------------------------------------------------------

    async def get_branding(self) -> Dict[str, Any]:
        """Return system org branding dict. Empty dict if system org missing."""
        org = await self._org_repo.get_by_slug("system")
        if not org:
            return {}

        branding = org.settings.get("branding", {}) if org.settings else {}

        return {
            "company_name": branding.get("company_name", ""),
            "short_name": branding.get("short_name", ""),
            "logo_url": branding.get("logo_url"),
            "primary_color": branding.get("primary_color", "#3B82F6"),
            "secondary_color": branding.get("secondary_color", "#10B981"),
            "accent_color": branding.get("accent_color", "#F59E0B"),
            "tagline": branding.get("tagline"),
            "hero_gradient_start": branding.get("hero_gradient_start"),
            "hero_gradient_end": branding.get("hero_gradient_end"),
            "header_background": branding.get("header_background"),
            "header_text": branding.get("header_text"),
            "section_background": branding.get("section_background"),
            "organization_id": org.id,
            "organization_slug": org.slug,
        }

    # ------------------------------------------------------------------
    # Team
    # ------------------------------------------------------------------

    async def get_public_team(self) -> List[Dict[str, Any]]:
        """Return list of public, active team members."""
        users = await self._user_repo.list_public_team()
        return [
            {
                "id": user.id,
                "first_name": user.first_name or "",
                "last_name": user.last_name or "",
                "role": user.role,
                "bio": user.bio,
                "avatar_url": user.avatar_url,
            }
            for user in users
        ]

    # ------------------------------------------------------------------
    # Site content helpers
    # ------------------------------------------------------------------

    async def get_site_content(self, page_id: str) -> Dict[str, Any]:
        """Return content dict for a page. Empty dict if not configured."""
        content = await self._site_content_repo.get_by_page_id(page_id)
        if not content:
            return {"page_id": page_id, "content": {}}
        return {"page_id": content.page_id, "content": content.content}

    async def get_contact_info(self) -> Dict[str, Optional[str]]:
        """Return contact info from the 'contact' site content page."""
        content = await self._site_content_repo.get_by_page_id("contact")
        if not content:
            return {"email": None, "phone": None, "address": None}
        return {
            "email": content.content.get("email"),
            "phone": content.content.get("phone"),
            "address": content.content.get("address"),
        }

    async def get_page_visibility(self) -> Dict[str, bool]:
        """Return page visibility settings from the 'settings' page."""
        content = await self._site_content_repo.get_by_page_id("settings")
        defaults = {
            "about": True,
            "compliance": True,
            "contact": True,
            "docs": True,
            "privacy": True,
            "support": True,
            "terms": True,
        }
        if not content or "page_visibility" not in (content.content or {}):
            return defaults

        visibility = content.content.get("page_visibility", {})
        return {k: visibility.get(k, v) for k, v in defaults.items()}

    async def get_disclosures(self) -> List[Dict[str, Any]]:
        """Return enabled compliance disclosures for the public page."""
        content = await self._site_content_repo.get_by_page_id("settings")
        if not content or "disclosures" not in (content.content or {}):
            return []
        disclosures = content.content.get("disclosures", [])
        return [
            {"key": d["key"], "title": d["title"], "content": d["content"]}
            for d in disclosures
            if d.get("enabled", False)
        ]

    async def get_compliance_settings(self) -> Dict[str, Any]:
        """Return ROSCA/compliance settings from the 'settings' page."""
        content = await self._site_content_repo.get_by_page_id("settings")
        if not content or "compliance" not in (content.content or {}):
            return {}
        return content.content.get("compliance", {})

    async def get_allow_registration(self) -> bool:
        """Check whether new-user registration is enabled. Defaults to False if not configured."""
        try:
            content = await self._site_content_repo.get_by_page_id("settings")
            if not content or "site_settings" not in (content.content or {}):
                return False
            return content.content.get("site_settings", {}).get(
                "allow_registration", False
            )
        except Exception as e:
            logger.error(f"Error checking registration settings: {e}")
            return False
