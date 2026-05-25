# api/app/presentation/api/public.py

"""Public (unauthenticated) endpoints: branding, team, site content, contact info."""

import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.application.services.public_content_service import PublicContentService
from app.infrastructure.maintenance import state as maintenance_state
from app.presentation.api.dependencies import get_public_content_service

logger = logging.getLogger(__name__)

router = APIRouter()


class MaintenanceStatusResponse(BaseModel):
    maintenance_mode: bool  # site is down
    warning_mode: bool = False  # countdown warning active
    warning_until: Optional[str] = None  # ISO timestamp when maintenance starts
    reason: Optional[str] = None


@router.get("/maintenance", response_model=MaintenanceStatusResponse)
async def get_maintenance_status() -> MaintenanceStatusResponse:
    """Public - frontend polls on page load to show maintenance UI."""
    result = await maintenance_state.get_maintenance_status()
    return MaintenanceStatusResponse(
        maintenance_mode=result.maintenance_mode,
        warning_mode=result.warning_mode,
        warning_until=result.warning_until,
        reason=result.reason,
    )


class BrandingResponse(BaseModel):
    company_name: str
    short_name: str
    logo_url: Optional[str] = None
    primary_color: str
    secondary_color: str
    accent_color: str
    tagline: Optional[str] = None

    hero_gradient_start: Optional[str] = None
    hero_gradient_end: Optional[str] = None
    header_background: Optional[str] = None
    header_text: Optional[str] = None
    section_background: Optional[str] = None

    organization_id: UUID
    organization_slug: str


@router.get("/branding", response_model=BrandingResponse)
async def get_public_branding(
    service: PublicContentService = Depends(get_public_content_service),
) -> BrandingResponse:
    """System-org branding for all public pages."""
    try:
        data = await service.get_branding()
        if not data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="System organization not configured",
            )
        return BrandingResponse(**data)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching public branding: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch branding configuration",
        )


class PublicTeamMemberResponse(BaseModel):
    """A public team member."""

    id: UUID
    first_name: str
    last_name: str
    role: str
    bio: Optional[str] = None
    avatar_url: Optional[str] = None


@router.get("/team", response_model=List[PublicTeamMemberResponse])
async def get_public_team(
    service: PublicContentService = Depends(get_public_content_service),
) -> List[PublicTeamMemberResponse]:
    """Active users with is_public=True. Drives About page team section."""
    try:
        members = await service.get_public_team()
        return [PublicTeamMemberResponse(**m) for m in members]

    except Exception as e:
        logger.error(f"Error fetching public team: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch team members",
        )


class ContactInfoResponse(BaseModel):
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None


@router.get("/contact", response_model=ContactInfoResponse)
async def get_public_contact(
    service: PublicContentService = Depends(get_public_content_service),
) -> ContactInfoResponse:
    """Contact details from the 'contact' page content."""
    try:
        data = await service.get_contact_info()
        return ContactInfoResponse(**data)

    except Exception as e:
        logger.error(f"Error fetching contact info: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch contact information",
        )


class ContactFormRequest(BaseModel):
    name: str
    email: str
    company: Optional[str] = None
    subject: str
    message: str


class ContactFormResponse(BaseModel):
    success: bool
    message: str


@router.post("/contact", response_model=ContactFormResponse)
async def submit_contact_form(
    form: ContactFormRequest,
) -> ContactFormResponse:
    """Currently log-only; future: email notification or ticket creation."""
    try:
        logger.info(
            f"Contact form submission: name={form.name}, email={form.email}, "
            f"subject={form.subject}, company={form.company}"
        )
        return ContactFormResponse(
            success=True,
            message="Thank you for your message. We'll get back to you soon.",
        )

    except Exception as e:
        logger.error(f"Error processing contact form: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to submit contact form",
        )


class SiteContentResponse(BaseModel):
    page_id: str
    content: Dict[str, Any]


@router.get("/site-content/{page_id}", response_model=SiteContentResponse)
async def get_site_content(
    page_id: str,
    service: PublicContentService = Depends(get_public_content_service),
) -> SiteContentResponse:
    """page_id ∈ home, about, terms, privacy, contact."""
    try:
        data = await service.get_site_content(page_id)
        return SiteContentResponse(**data)

    except Exception as e:
        logger.error(f"Error fetching site content for {page_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch site content",
        )


class PageVisibilityResponse(BaseModel):
    """Which public pages are enabled."""

    about: bool = True
    blueprints: bool = False
    compliance: bool = True
    contact: bool = True
    docs: bool = True
    privacy: bool = True
    support: bool = True
    terms: bool = True


@router.get("/page-visibility", response_model=PageVisibilityResponse)
async def get_page_visibility(
    service: PublicContentService = Depends(get_public_content_service),
) -> PageVisibilityResponse:
    """Frontend uses this to 404 disabled pages."""
    try:
        data = await service.get_page_visibility()
        return PageVisibilityResponse(**data)

    except Exception as e:
        logger.error(f"Error fetching page visibility: {e}")
        return PageVisibilityResponse()


class ComplianceSettingsResponse(BaseModel):
    """ROSCA/compliance settings."""

    rosca_enabled: bool = False
    trial_disclosure: str = (
        "After your {trial_days}-day free trial ends on {trial_end_date}, "
        "you will be automatically charged {price} every {interval} until you cancel."
    )
    recurring_disclosure: str = (
        "You will be charged {price} today and automatically every {interval} until you cancel."
    )
    one_time_disclosure: str = (
        "This is a one-time payment of {price}. No recurring charges."
    )
    cancellation_instructions: str = (
        "You can cancel anytime from your account Settings → Billing page. "
        "Your access continues until the end of your billing period."
    )
    consent_checkbox_text: str = (
        "I understand this is a recurring subscription and I will be charged "
        "{price} every {interval} until I cancel."
    )
    registration_disclosure: str = (
        "By creating an account with the {plan_name} plan, you agree to be charged "
        "{price}/{interval} after any applicable trial period. "
        "You can cancel anytime from your account settings."
    )


@router.get("/compliance-settings", response_model=ComplianceSettingsResponse)
async def get_compliance_settings(
    service: PublicContentService = Depends(get_public_content_service),
) -> ComplianceSettingsResponse:
    """Subscription disclosure text templates for registration/checkout."""
    try:
        compliance = await service.get_compliance_settings()
        if not compliance:
            return ComplianceSettingsResponse()

        return ComplianceSettingsResponse(
            rosca_enabled=compliance.get("rosca_enabled", False),
            trial_disclosure=compliance.get(
                "trial_disclosure",
                ComplianceSettingsResponse.model_fields["trial_disclosure"].default,
            ),
            recurring_disclosure=compliance.get(
                "recurring_disclosure",
                ComplianceSettingsResponse.model_fields["recurring_disclosure"].default,
            ),
            one_time_disclosure=compliance.get(
                "one_time_disclosure",
                ComplianceSettingsResponse.model_fields["one_time_disclosure"].default,
            ),
            cancellation_instructions=compliance.get(
                "cancellation_instructions",
                ComplianceSettingsResponse.model_fields[
                    "cancellation_instructions"
                ].default,
            ),
            consent_checkbox_text=compliance.get(
                "consent_checkbox_text",
                ComplianceSettingsResponse.model_fields[
                    "consent_checkbox_text"
                ].default,
            ),
            registration_disclosure=compliance.get(
                "registration_disclosure",
                ComplianceSettingsResponse.model_fields[
                    "registration_disclosure"
                ].default,
            ),
        )

    except Exception as e:
        logger.error(f"Error fetching compliance settings: {e}")
        return ComplianceSettingsResponse()


class DisclosureItemResponse(BaseModel):
    """A single public compliance disclosure block."""

    key: str
    title: str
    content: str


class DisclosuresResponse(BaseModel):
    disclosures: List[DisclosureItemResponse]


@router.get("/disclosures", response_model=DisclosuresResponse)
async def get_disclosures(
    service: PublicContentService = Depends(get_public_content_service),
) -> DisclosuresResponse:
    """Admin-toggled disclosures for the public /compliance page."""
    try:
        disclosures = await service.get_disclosures()
        return DisclosuresResponse(
            disclosures=[DisclosureItemResponse(**d) for d in disclosures]
        )

    except Exception as e:
        logger.error(f"Error fetching disclosures: {e}")
        return DisclosuresResponse(disclosures=[])


async def get_allow_registration(service: PublicContentService) -> bool:
    """Reads site settings. Defaults False; super-admin must enable."""
    return await service.get_allow_registration()


class RegistrationSettingsResponse(BaseModel):
    allow_registration: bool = False


@router.get("/registration-settings", response_model=RegistrationSettingsResponse)
async def get_registration_settings(
    service: PublicContentService = Depends(get_public_content_service),
) -> RegistrationSettingsResponse:
    """Reads same DB row admin writes via PUT /site-content/settings/registration."""
    allow = await get_allow_registration(service)
    return RegistrationSettingsResponse(allow_registration=allow)
