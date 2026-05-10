# api/app/domain/organization_secret/__init__.py

"""Organization Secret domain module."""

from app.domain.organization_secret.models import OrganizationSecret
from app.domain.organization_secret.repository import OrganizationSecretRepository

__all__ = ["OrganizationSecret", "OrganizationSecretRepository"]
