# api/app/domain/organization_secret/models.py

"""Organization Secret domain models. Names are immutable; never log secret_data."""

import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import Field

from app.domain.common.base_entity import AggregateRoot


class OrganizationSecret(AggregateRoot):
    """API keys/credentials/tokens for an organization. secret_data is encrypted at rest in infrastructure. is_protected blocks deletion."""

    organization_id: uuid.UUID
    name: str  # Immutable after creation
    secret_type: str
    secret_data: Dict[str, Any] = Field(default_factory=dict)
    description: Optional[str] = None
    is_active: bool = True
    is_protected: bool = False
    expires_at: Optional[datetime] = None
    created_by: Optional[uuid.UUID] = None

    @classmethod
    def create(
        cls,
        organization_id: uuid.UUID,
        name: str,
        secret_type: str,
        secret_data: Dict[str, Any],
        description: Optional[str] = None,
        is_protected: bool = False,
        expires_at: Optional[datetime] = None,
        created_by: Optional[uuid.UUID] = None,
    ) -> "OrganizationSecret":
        return cls(
            organization_id=organization_id,
            name=name,
            secret_type=secret_type,
            secret_data=secret_data,
            description=description,
            is_protected=is_protected,
            expires_at=expires_at,
            created_by=created_by,
        )

    def update(
        self,
        secret_type: Optional[str] = None,
        secret_data: Optional[Dict[str, Any]] = None,
        description: Optional[str] = None,
        is_active: Optional[bool] = None,
        expires_at: Optional[datetime] = None,
    ) -> None:
        """Update mutable fields. Name is immutable and cannot be changed."""
        if secret_type is not None:
            self.secret_type = secret_type
        if secret_data is not None:
            self.secret_data = secret_data
        if description is not None:
            self.description = description
        if is_active is not None:
            self.is_active = is_active
        if expires_at is not None:
            self.expires_at = expires_at

    def deactivate(self) -> None:
        self.is_active = False

    def activate(self) -> None:
        self.is_active = True

    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        from datetime import UTC

        return datetime.now(UTC) > self.expires_at

    def can_delete(self) -> bool:
        return not self.is_protected
