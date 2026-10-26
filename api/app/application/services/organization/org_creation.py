# api/app/application/services/organization/org_creation.py

"""Create an organization with a generated slug, regenerating the suffix on collision."""

from typing import List, Optional, Tuple

from app.domain.common.events import DomainEvent
from app.domain.common.exceptions import DuplicateEntityError
from app.domain.organization import slug as org_slug
from app.domain.organization.models import Organization
from app.domain.organization.repository import OrganizationRepository

SLUG_ATTEMPTS = 5


async def create_organization_with_generated_slug(
    repository: OrganizationRepository,
    name: str,
    description: Optional[str] = None,
) -> Tuple[Organization, List[DomainEvent]]:
    """Persist a new organization and return it with its pending events; 409-class error when no slug is free."""
    for _ in range(SLUG_ATTEMPTS):
        organization = Organization.create(
            name=name,
            slug=org_slug.generate_org_slug(name),
            description=description,
        )
        events = organization.clear_events()
        try:
            return await repository.create(organization), events
        except DuplicateEntityError:
            continue
    raise DuplicateEntityError(
        "Could not generate a unique slug for this organization. Try again.",
        "DUPLICATE_ORGANIZATION_SLUG",
    )
