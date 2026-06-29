# api/app/presentation/api/site_content.py

"""
Site Content Management API endpoints (super-admin only).

These endpoints allow super-admins to manage public page content including
testimonials, terms, privacy policy, about page content, and contact info.
"""

import logging
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, status
from pydantic import BaseModel

from app.application.services.site_content_service import SiteContentService
from app.domain.common.exceptions import EntityNotFoundError
from app.presentation.api.dependencies import (
    get_site_content_service,
    require_super_admin,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================================================
# Request/Response Models
# ============================================================================


class SiteContentResponse(BaseModel):
    id: UUID
    page_id: str
    content: Dict[str, Any]
    updated_at: datetime


class SiteContentUpdateRequest(BaseModel):
    content: Dict[str, Any]


class SiteContentListResponse(BaseModel):
    items: List[SiteContentResponse]


class TestimonialItem(BaseModel):
    __test__ = False  # Prevent pytest collection

    name: str
    title: str
    feedback: str
    avatar_url: Optional[str] = None


class TestimonialsUpdateRequest(BaseModel):
    __test__ = False  # Prevent pytest collection

    testimonials: List[TestimonialItem]


class FeatureBlockItem(BaseModel):
    """Model for a single feature block on the home page."""

    id: str
    title: str
    description: str
    thumbnail: Optional[str] = None  # Optional image URL
    media_type: str = "image"  # "image" or "video"
    workflow_id: Optional[str] = None  # Future: link to workflow
    sort_order: int = 0
    icon: Optional[str] = None  # Lucide icon name (e.g., "workflow", "brain")
    visible: bool = True  # Whether to show on the homepage


class FeaturesUpdateRequest(BaseModel):
    features: List[FeatureBlockItem]


class HeroUpdateRequest(BaseModel):
    visible: bool = True
    headline: Optional[str] = None
    subtext: Optional[str] = None
    cta_text: Optional[str] = None
    cta_link: Optional[str] = None


class RegistrationSettingsUpdateRequest(BaseModel):
    allow_registration: bool = True


class TermsPrivacyUpdateRequest(BaseModel):
    content: str  # Markdown content
    last_updated: Optional[str] = None


class ContactInfoUpdateRequest(BaseModel):
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None


class AboutStoryUpdateRequest(BaseModel):
    title: Optional[str] = None
    subtitle: Optional[str] = None
    story: str  # Markdown content


class ComplianceSettingsUpdateRequest(BaseModel):
    """Request model for updating compliance/ROSCA settings.

    These settings control subscription disclosure text shown to users
    before they commit to a recurring subscription.

    Supported placeholders in text fields:
    - {trial_days}: Number of trial days
    - {trial_end_date}: Formatted trial end date
    - {price}: Formatted price (e.g., "$29.99")
    - {interval}: Billing interval (e.g., "month", "year")
    - {plan_name}: Name of the selected plan
    """

    # Whether ROSCA compliance mode is enabled
    rosca_enabled: bool = False

    # Trial disclosure template
    trial_disclosure: str = (
        "After your {trial_days}-day free trial ends on {trial_end_date}, "
        "you will be automatically charged {price} every {interval} until you cancel."
    )

    # Non-trial recurring disclosure template
    recurring_disclosure: str = (
        "You will be charged {price} today and automatically every {interval} until you cancel."
    )

    # One-time payment disclosure
    one_time_disclosure: str = (
        "This is a one-time payment of {price}. No recurring charges."
    )

    # Cancellation instructions
    cancellation_instructions: str = (
        "You can cancel anytime from your account Settings → Billing page. "
        "Your access continues until the end of your billing period."
    )

    # Consent checkbox text for recurring subscriptions
    consent_checkbox_text: str = (
        "I understand this is a recurring subscription and I will be charged "
        "{price} every {interval} until I cancel."
    )

    # Registration page disclosure (shown when plan is pre-selected)
    registration_disclosure: str = (
        "By creating an account with the {plan_name} plan, you agree to be charged "
        "{price}/{interval} after any applicable trial period. "
        "You can cancel anytime from your account settings."
    )


class DisclosureItem(BaseModel):
    """A single compliance disclosure block."""

    key: str  # Unique identifier (e.g., "twilio_sms")
    title: str  # Display title (e.g., "SMS/Messaging Consent")
    enabled: bool = False
    content: str  # Markdown content


class DisclosuresUpdateRequest(BaseModel):
    """Request model for updating compliance disclosures.

    Each disclosure is a togglable block of pre-defined (but editable)
    compliance text that renders on the public /compliance page.
    """

    disclosures: list[DisclosureItem]


class PageVisibilityUpdateRequest(BaseModel):
    """Request model for updating page visibility settings.

    All public pages except home, login, and register can be toggled.
    """

    about: bool = True
    blueprints: bool = False
    compliance: bool = True
    contact: bool = True
    docs: bool = True
    pricing: bool = True
    privacy: bool = True
    support: bool = True
    terms: bool = True


# ============================================================================
# Admin Endpoints
# ============================================================================


@router.get("/", response_model=SiteContentListResponse)
async def list_site_content(
    user: Dict[str, Any] = Depends(require_super_admin),
    service: SiteContentService = Depends(get_site_content_service),
) -> SiteContentListResponse:
    """
    List all site content pages.

    Returns all configured site content for the dashboard.
    Super-admin only.
    """
    try:
        contents = await service.list_all()

        return SiteContentListResponse(
            items=[
                SiteContentResponse(
                    id=c["id"],
                    page_id=c["page_id"],
                    content=c["content"],
                    updated_at=c["updated_at"],
                )
                for c in contents
            ]
        )

    except Exception as e:
        logger.error(f"Error listing site content: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to list site content")


@router.get("/{page_id}", response_model=SiteContentResponse)
async def get_site_content(
    page_id: str = Path(..., description="Page identifier"),
    user: Dict[str, Any] = Depends(require_super_admin),
    service: SiteContentService = Depends(get_site_content_service),
) -> SiteContentResponse:
    """
    Get site content for a specific page.

    Super-admin only.
    """
    try:
        content = await service.get_by_page_id(page_id)

        return SiteContentResponse(
            id=content["id"],
            page_id=content["page_id"],
            content=content["content"],
            updated_at=content["updated_at"],
        )

    except EntityNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Site content for page '{page_id}' not found"
        )
    except Exception as e:
        logger.error(f"Error getting site content: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to get site content")


# ============================================================================
# Type-Safe Convenience Endpoints
# ============================================================================


@router.put("/home/testimonials", response_model=SiteContentResponse)
async def update_testimonials(
    request: TestimonialsUpdateRequest,
    user: Dict[str, Any] = Depends(require_super_admin),
    service: SiteContentService = Depends(get_site_content_service),
) -> SiteContentResponse:
    """
    Update home page testimonials.

    Super-admin only.
    """
    testimonials_data = [t.model_dump() for t in request.testimonials]

    content = await service.merge_content(
        page_id="home",
        key="testimonials",
        value=testimonials_data,
        updated_by=UUID(user["id"]),
    )

    return SiteContentResponse(
        id=content["id"],
        page_id=content["page_id"],
        content=content["content"],
        updated_at=content["updated_at"],
    )


@router.put("/home/features", response_model=SiteContentResponse)
async def update_features(
    request: FeaturesUpdateRequest,
    user: Dict[str, Any] = Depends(require_super_admin),
    service: SiteContentService = Depends(get_site_content_service),
) -> SiteContentResponse:
    """
    Update home page feature blocks.

    Super-admin only.
    """
    features_data = [f.model_dump() for f in request.features]

    content = await service.merge_content(
        page_id="home",
        key="features",
        value=features_data,
        updated_by=UUID(user["id"]),
    )

    return SiteContentResponse(
        id=content["id"],
        page_id=content["page_id"],
        content=content["content"],
        updated_at=content["updated_at"],
    )


@router.put("/terms", response_model=SiteContentResponse)
async def update_terms(
    request: TermsPrivacyUpdateRequest,
    user: Dict[str, Any] = Depends(require_super_admin),
    service: SiteContentService = Depends(get_site_content_service),
) -> SiteContentResponse:
    """
    Update terms of service content.

    Super-admin only.
    """
    content_data = {
        "content": request.content,
        "last_updated": request.last_updated or datetime.now(UTC).strftime("%B %d, %Y"),
    }

    content = await service.update_or_create(
        page_id="terms",
        content_data=content_data,
        updated_by=UUID(user["id"]),
    )

    return SiteContentResponse(
        id=content["id"],
        page_id=content["page_id"],
        content=content["content"],
        updated_at=content["updated_at"],
    )


@router.put("/privacy", response_model=SiteContentResponse)
async def update_privacy(
    request: TermsPrivacyUpdateRequest,
    user: Dict[str, Any] = Depends(require_super_admin),
    service: SiteContentService = Depends(get_site_content_service),
) -> SiteContentResponse:
    """
    Update privacy policy content.

    Super-admin only.
    """
    content_data = {
        "content": request.content,
        "last_updated": request.last_updated or datetime.now(UTC).strftime("%B %d, %Y"),
    }

    content = await service.update_or_create(
        page_id="privacy",
        content_data=content_data,
        updated_by=UUID(user["id"]),
    )

    return SiteContentResponse(
        id=content["id"],
        page_id=content["page_id"],
        content=content["content"],
        updated_at=content["updated_at"],
    )


@router.put("/contact", response_model=SiteContentResponse)
async def update_contact_info(
    request: ContactInfoUpdateRequest,
    user: Dict[str, Any] = Depends(require_super_admin),
    service: SiteContentService = Depends(get_site_content_service),
) -> SiteContentResponse:
    """
    Update contact information.

    Super-admin only.
    """
    content_data = {
        "email": request.email,
        "phone": request.phone,
        "address": request.address,
    }

    content = await service.update_or_create(
        page_id="contact",
        content_data=content_data,
        updated_by=UUID(user["id"]),
    )

    return SiteContentResponse(
        id=content["id"],
        page_id=content["page_id"],
        content=content["content"],
        updated_at=content["updated_at"],
    )


@router.put("/about/story", response_model=SiteContentResponse)
async def update_about_story(
    request: AboutStoryUpdateRequest,
    user: Dict[str, Any] = Depends(require_super_admin),
    service: SiteContentService = Depends(get_site_content_service),
) -> SiteContentResponse:
    """
    Update about page story content.

    Super-admin only.
    """
    # Merge all about fields into the page content
    about_data = {"story": request.story}
    if request.title is not None:
        about_data["title"] = request.title
    if request.subtitle is not None:
        about_data["subtitle"] = request.subtitle

    content = None
    for key, value in about_data.items():
        content = await service.merge_content(
            page_id="about",
            key=key,
            value=value,
            updated_by=UUID(user["id"]),
        )

    if content is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update about story content"
        )

    return SiteContentResponse(
        id=content["id"],
        page_id=content["page_id"],
        content=content["content"],
        updated_at=content["updated_at"],
    )


@router.put("/settings/page-visibility", response_model=SiteContentResponse)
async def update_page_visibility(
    request: PageVisibilityUpdateRequest,
    user: Dict[str, Any] = Depends(require_super_admin),
    service: SiteContentService = Depends(get_site_content_service),
) -> SiteContentResponse:
    """
    Update page visibility settings.

    Controls which public pages are enabled/disabled.
    Disabled pages will return 404.

    Super-admin only.
    """
    content_data = {
        "about": request.about,
        "compliance": request.compliance,
        "contact": request.contact,
        "docs": request.docs,
        "pricing": request.pricing,
        "privacy": request.privacy,
        "support": request.support,
        "terms": request.terms,
    }

    content = await service.merge_content(
        page_id="settings",
        key="page_visibility",
        value=content_data,
        updated_by=UUID(user["id"]),
    )

    return SiteContentResponse(
        id=content["id"],
        page_id=content["page_id"],
        content=content["content"],
        updated_at=content["updated_at"],
    )


@router.put("/settings/disclosures", response_model=SiteContentResponse)
async def update_disclosures(
    request: DisclosuresUpdateRequest,
    user: Dict[str, Any] = Depends(require_super_admin),
    service: SiteContentService = Depends(get_site_content_service),
) -> SiteContentResponse:
    """
    Update compliance disclosure blocks.

    These are togglable, editable compliance texts (e.g., Twilio SMS consent)
    displayed on the public /compliance page.

    Super-admin only.
    """
    content_data = [d.model_dump() for d in request.disclosures]

    content = await service.merge_content(
        page_id="settings",
        key="disclosures",
        value=content_data,
        updated_by=UUID(user["id"]),
    )

    return SiteContentResponse(
        id=content["id"],
        page_id=content["page_id"],
        content=content["content"],
        updated_at=content["updated_at"],
    )


@router.put("/settings/compliance", response_model=SiteContentResponse)
async def update_compliance_settings(
    request: ComplianceSettingsUpdateRequest,
    user: Dict[str, Any] = Depends(require_super_admin),
    service: SiteContentService = Depends(get_site_content_service),
) -> SiteContentResponse:
    """
    Update ROSCA/compliance settings.

    Controls subscription disclosure text for ROSCA compliance.
    These settings affect how subscription terms are displayed to users
    at registration and checkout.

    Super-admin only.
    """
    content_data = {
        "rosca_enabled": request.rosca_enabled,
        "trial_disclosure": request.trial_disclosure,
        "recurring_disclosure": request.recurring_disclosure,
        "one_time_disclosure": request.one_time_disclosure,
        "cancellation_instructions": request.cancellation_instructions,
        "consent_checkbox_text": request.consent_checkbox_text,
        "registration_disclosure": request.registration_disclosure,
    }

    content = await service.merge_content(
        page_id="settings",
        key="compliance",
        value=content_data,
        updated_by=UUID(user["id"]),
    )

    return SiteContentResponse(
        id=content["id"],
        page_id=content["page_id"],
        content=content["content"],
        updated_at=content["updated_at"],
    )


@router.put("/home/hero", response_model=SiteContentResponse)
async def update_hero(
    request: HeroUpdateRequest,
    user: Dict[str, Any] = Depends(require_super_admin),
    service: SiteContentService = Depends(get_site_content_service),
) -> SiteContentResponse:
    """
    Update home page hero section configuration.

    Super-admin only.
    """
    hero_data = {
        "visible": request.visible,
        "headline": request.headline,
        "subtext": request.subtext,
        "cta_text": request.cta_text,
        "cta_link": request.cta_link,
    }

    content = await service.merge_content(
        page_id="home",
        key="hero",
        value=hero_data,
        updated_by=UUID(user["id"]),
    )

    return SiteContentResponse(
        id=content["id"],
        page_id=content["page_id"],
        content=content["content"],
        updated_at=content["updated_at"],
    )


@router.put("/settings/registration", response_model=SiteContentResponse)
async def update_registration_settings(
    request: RegistrationSettingsUpdateRequest,
    user: Dict[str, Any] = Depends(require_super_admin),
    service: SiteContentService = Depends(get_site_content_service),
) -> SiteContentResponse:
    """
    Update registration settings.

    Controls whether new user registration is allowed.
    Both the public read endpoint (GET /api/v1/public/registration-settings)
    and this write endpoint operate on the same DB row:
    SiteContentModel page_id="settings", key path content.site_settings.allow_registration

    Super-admin only.
    """
    content_data = {
        "allow_registration": request.allow_registration,
    }

    content = await service.merge_content(
        page_id="settings",
        key="site_settings",
        value=content_data,
        updated_by=UUID(user["id"]),
    )

    return SiteContentResponse(
        id=content["id"],
        page_id=content["page_id"],
        content=content["content"],
        updated_at=content["updated_at"],
    )


# ============================================================================
# Generic Fallback Endpoint (must be AFTER typed endpoints to avoid shadowing)
# ============================================================================


@router.put("/{page_id}", response_model=SiteContentResponse)
async def update_site_content(
    request: SiteContentUpdateRequest,
    page_id: str = Path(..., description="Page identifier"),
    user: Dict[str, Any] = Depends(require_super_admin),
    service: SiteContentService = Depends(get_site_content_service),
) -> SiteContentResponse:
    """
    Update or create site content for a page.

    This is a generic fallback endpoint that accepts any content structure.
    For type-safe updates, use the specific endpoints above.

    Super-admin only.
    """
    try:
        content = await service.update_or_create(
            page_id=page_id,
            content_data=request.content,
            updated_by=UUID(user["id"]),
        )

        return SiteContentResponse(
            id=content["id"],
            page_id=content["page_id"],
            content=content["content"],
            updated_at=content["updated_at"],
        )

    except Exception as e:
        logger.error(f"Error updating site content: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update site content")
