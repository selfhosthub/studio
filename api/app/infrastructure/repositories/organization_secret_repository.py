# api/app/infrastructure/repositories/organization_secret_repository.py

"""SQLAlchemy implementation of OrganizationSecret repository.

SECURITY: secret_data is encrypted at rest; names are immutable; never log decrypted values.
"""

import logging
import uuid
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.common.exceptions import EntityNotFoundError
from app.domain.organization_secret import OrganizationSecret, OrganizationSecretRepository
from app.infrastructure.persistence.models import OrganizationSecretModel
from app.infrastructure.security.credential_encryption import get_credential_encryption

logger = logging.getLogger(__name__)


class SQLAlchemyOrganizationSecretRepository(OrganizationSecretRepository):
    """SQLAlchemy implementation of organization secret repository."""

    def __init__(self, session: AsyncSession):
        self.session = session
        try:
            self._encryption = get_credential_encryption()
            self.encryption_available = True
        except ValueError:
            self._encryption = None
            self.encryption_available = False

    def _to_domain(self, model: OrganizationSecretModel) -> OrganizationSecret:
        """Convert database model to domain entity.

        SECURITY: Decrypts secret_data. Never log the result.
        """
        secret_data = model.secret_data
        if self.encryption_available and self._encryption:
            secret_data = self._encryption.decrypt_credential_dict(model.secret_data)

        return OrganizationSecret(
            id=model.id,
            organization_id=model.organization_id,
            name=model.name,
            secret_type=model.secret_type,
            secret_data=secret_data or {},
            description=model.description,
            is_active=model.is_active,
            is_protected=model.is_protected,
            expires_at=model.expires_at,
            created_by=model.created_by,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    async def create(self, secret: OrganizationSecret) -> OrganizationSecret:
        """Create a new organization secret.

        SECURITY: Encrypts secret_data before storage.
        """
        secret_data_to_store = secret.secret_data
        if self.encryption_available and self._encryption:
            secret_data_to_store = self._encryption.encrypt_credential_dict(
                secret.secret_data
            )

        secret_model = OrganizationSecretModel(
            id=secret.id,
            organization_id=secret.organization_id,
            name=secret.name,  # Immutable - cannot be changed after this
            secret_type=secret.secret_type,
            secret_data=secret_data_to_store or {},
            description=secret.description,
            is_active=secret.is_active,
            is_protected=secret.is_protected,
            expires_at=secret.expires_at,
            created_by=secret.created_by,
        )
        self.session.add(secret_model)
        await self.session.commit()
        await self.session.refresh(secret_model)

        return self._to_domain(secret_model)

    async def update(self, secret: OrganizationSecret) -> OrganizationSecret:
        """Update an existing organization secret.

        SECURITY:
        - Name cannot be changed (immutable)
        - Encrypts new secret_data before storage
        """
        stmt = select(OrganizationSecretModel).where(
            OrganizationSecretModel.id == secret.id
        )
        result = await self.session.execute(stmt)
        secret_model = result.scalars().first()

        if not secret_model:
            raise EntityNotFoundError(
                entity_type="OrganizationSecret",
                entity_id=secret.id,
                code=f"Organization secret with ID {secret.id} not found",
            )

        secret_data_to_store = secret.secret_data
        if self.encryption_available and self._encryption:
            secret_data_to_store = self._encryption.encrypt_credential_dict(
                secret.secret_data
            )

        # SECURITY: Name is immutable - do not update it
        secret_model.secret_type = secret.secret_type
        secret_model.secret_data = secret_data_to_store or {}
        secret_model.is_active = secret.is_active
        secret_model.expires_at = secret.expires_at
        secret_model.updated_at = datetime.now(UTC)

        await self.session.commit()
        await self.session.refresh(secret_model)

        return self._to_domain(secret_model)

    async def get_by_id(
        self, secret_id: uuid.UUID, organization_id: uuid.UUID
    ) -> Optional[OrganizationSecret]:
        """Retrieve an organization secret by its ID.

        SECURITY: Returns decrypted secret_data. Use carefully.
        """
        stmt = select(OrganizationSecretModel).where(
            OrganizationSecretModel.id == secret_id,
            OrganizationSecretModel.organization_id == organization_id,
        )
        result = await self.session.execute(stmt)
        secret_model = result.scalars().first()

        return self._to_domain(secret_model) if secret_model else None

    async def get_by_name(
        self, organization_id: uuid.UUID, name: str
    ) -> Optional[OrganizationSecret]:
        """Retrieve an organization secret by its name.

        SECURITY: Returns decrypted secret_data. Use carefully.
        """
        stmt = select(OrganizationSecretModel).where(
            OrganizationSecretModel.name == name,
            OrganizationSecretModel.organization_id == organization_id,
        )
        result = await self.session.execute(stmt)
        secret_model = result.scalars().first()

        return self._to_domain(secret_model) if secret_model else None

    async def list_by_organization(
        self,
        organization_id: uuid.UUID,
        include_inactive: bool = False,
    ) -> List[OrganizationSecret]:
        """List all secrets for an organization.

        SECURITY: Returns decrypted secret_data.
        Consider using list_metadata_only() for safer listings.
        """
        stmt = select(OrganizationSecretModel).where(
            OrganizationSecretModel.organization_id == organization_id
        )

        if not include_inactive:
            stmt = stmt.where(OrganizationSecretModel.is_active == True)

        stmt = stmt.order_by(OrganizationSecretModel.name)

        result = await self.session.execute(stmt)
        models = result.scalars().all()

        return [self._to_domain(model) for model in models]

    async def list_metadata_only(
        self,
        organization_id: uuid.UUID,
        active_only: bool = True,
    ) -> List[Dict[str, Any]]:
        """List secret metadata WITHOUT decrypted values.

        SECURITY: Safe for API list endpoints. Returns names/metadata only.
        """
        stmt = select(OrganizationSecretModel).where(
            OrganizationSecretModel.organization_id == organization_id
        )

        if active_only:
            stmt = stmt.where(OrganizationSecretModel.is_active == True)

        stmt = stmt.order_by(OrganizationSecretModel.name)

        result = await self.session.execute(stmt)
        models = result.scalars().all()

        # Return metadata only - NO secret_data
        return [
            {
                "id": str(model.id),
                "name": model.name,
                "secret_type": model.secret_type,
                "description": model.description,
                "is_active": model.is_active,
                "is_protected": model.is_protected,
                "expires_at": (
                    model.expires_at.isoformat() if model.expires_at else None
                ),
                "created_at": model.created_at.isoformat(),
                "updated_at": model.updated_at.isoformat(),
            }
            for model in models
        ]

    async def delete(self, secret_id: uuid.UUID, organization_id: uuid.UUID) -> bool:
        """Delete an organization secret by its ID.

        SECURITY: Protected secrets cannot be deleted.
        """
        stmt = select(OrganizationSecretModel).where(
            OrganizationSecretModel.id == secret_id,
            OrganizationSecretModel.organization_id == organization_id,
        )
        result = await self.session.execute(stmt)
        secret_model = result.scalars().first()

        if not secret_model:
            return False

        # Protected secrets cannot be deleted
        if secret_model.is_protected:
            raise ValueError(
                f"Secret '{secret_model.name}' is protected and cannot be deleted"
            )

        await self.session.delete(secret_model)
        await self.session.commit()

        return True
