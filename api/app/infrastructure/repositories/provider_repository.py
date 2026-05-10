# api/app/infrastructure/repositories/provider_repository.py

"""SQLAlchemy repository implementations for provider domain entities."""
import logging
import uuid
from datetime import UTC, datetime
from typing import List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.common.exceptions import EntityNotFoundError
from app.domain.provider.models import (
    CredentialType,
    Provider,
    ProviderCredential,
    ProviderService,
    ProviderStatus,
    ProviderType,
    ServiceType,
)
from app.domain.provider.repository import (
    ProviderCredentialRepository,
    ProviderRepository,
    ProviderServiceRepository,
)
from app.infrastructure.persistence.models import (
    ProviderCredentialModel,
    ProviderModel,
    ProviderServiceModel,
)
from app.infrastructure.security.credential_encryption import get_credential_encryption

logger = logging.getLogger(__name__)


class SQLAlchemyProviderRepository(ProviderRepository):
    """SQLAlchemy implementation of provider repository."""

    def __init__(self, session: AsyncSession):
        self.session = session

    def _to_domain(self, model: ProviderModel) -> Provider:
        return Provider(
            id=model.id,
            name=model.name,
            slug=model.slug,
            description=model.description,
            provider_type=model.provider_type,
            endpoint_url=model.endpoint_url,
            status=model.status,
            config=model.config,
            capabilities=model.capabilities,
            client_metadata=model.client_metadata,
            version=model.version,
            source_hash=model.source_hash,
            created_by=model.created_by,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    async def create(self, provider: Provider) -> Provider:
        provider_model = ProviderModel(
            id=provider.id,
            name=provider.name,
            slug=provider.slug,
            description=provider.description,
            provider_type=provider.provider_type,
            endpoint_url=provider.endpoint_url,
            status=provider.status,
            config=provider.config,
            capabilities=provider.capabilities,
            client_metadata=provider.client_metadata,
            version=provider.version,
            source_hash=provider.source_hash,
            created_by=provider.created_by,
        )
        self.session.add(provider_model)
        await self.session.commit()
        await self.session.refresh(provider_model)

        return self._to_domain(provider_model)

    async def update(self, provider: Provider) -> Provider:
        stmt = select(ProviderModel).where(ProviderModel.id == provider.id)
        result = await self.session.execute(stmt)
        provider_model = result.scalars().first()

        if not provider_model:
            raise EntityNotFoundError(
                entity_type="Provider",
                entity_id=provider.id,
                code=f"Provider with ID {provider.id} not found",
            )

        provider_model.name = provider.name
        provider_model.slug = provider.slug
        provider_model.description = provider.description
        provider_model.provider_type = provider.provider_type
        provider_model.endpoint_url = provider.endpoint_url
        provider_model.status = provider.status
        provider_model.config = provider.config
        provider_model.capabilities = provider.capabilities
        provider_model.client_metadata = provider.client_metadata
        provider_model.version = provider.version
        provider_model.source_hash = provider.source_hash
        provider_model.updated_at = datetime.now(UTC)

        await self.session.commit()
        await self.session.refresh(provider_model)

        return self._to_domain(provider_model)

    async def get_by_id(self, provider_id: uuid.UUID) -> Optional[Provider]:
        stmt = select(ProviderModel).where(ProviderModel.id == provider_id)
        result = await self.session.execute(stmt)
        provider_model = result.scalars().first()

        return self._to_domain(provider_model) if provider_model else None

    async def get_by_name(self, name: str) -> Optional[Provider]:
        stmt = select(ProviderModel).where(ProviderModel.name == name)
        result = await self.session.execute(stmt)
        provider_model = result.scalars().first()

        return self._to_domain(provider_model) if provider_model else None

    async def get_by_slug(self, slug: str) -> Optional[Provider]:
        """Return the highest semver row for a slug; non-conforming versions sort below all valid ones."""
        from app.infrastructure.utils.semver import parse_semver

        stmt = select(ProviderModel).where(ProviderModel.slug == slug)
        result = await self.session.execute(stmt)
        candidates = list(result.scalars().all())
        if not candidates:
            return None

        latest = max(candidates, key=lambda p: parse_semver(p.version))
        return self._to_domain(latest)

    async def find_active_providers(self, skip: int, limit: int) -> List[Provider]:
        stmt = select(ProviderModel).where(
            ProviderModel.status == ProviderStatus.ACTIVE
        )

        stmt = stmt.offset(skip).limit(limit)

        result = await self.session.execute(stmt)
        models = result.scalars().all()

        return [self._to_domain(model) for model in models]

    async def find_providers_by_type(
        self,
        provider_type: ProviderType,
        skip: int,
        limit: int,
    ) -> List[Provider]:
        stmt = select(ProviderModel).where(
            ProviderModel.provider_type == provider_type,
            ProviderModel.status == ProviderStatus.ACTIVE,
        )

        stmt = stmt.offset(skip).limit(limit)

        result = await self.session.execute(stmt)
        models = result.scalars().all()

        return [self._to_domain(model) for model in models]

    async def find_global_providers(self, skip: int, limit: int) -> List[Provider]:
        stmt = select(ProviderModel).where(
            ProviderModel.status == ProviderStatus.ACTIVE
        ).order_by(ProviderModel.name)

        stmt = stmt.offset(skip).limit(limit)

        result = await self.session.execute(stmt)
        models = result.scalars().all()

        return [self._to_domain(model) for model in models]

    async def list_all(
        self,
        skip: int,
        limit: int,
        status: Optional[ProviderStatus] = None,
        provider_type: Optional[ProviderType] = None,
    ) -> List[Provider]:
        stmt = select(ProviderModel)

        if status is not None:
            stmt = stmt.where(ProviderModel.status == status)
        if provider_type is not None:
            stmt = stmt.where(ProviderModel.provider_type == provider_type)

        stmt = stmt.order_by(ProviderModel.name)

        stmt = stmt.offset(skip).limit(limit)

        result = await self.session.execute(stmt)
        models = result.scalars().all()

        return [self._to_domain(model) for model in models]

    async def count(
        self,
        status: Optional[ProviderStatus] = None,
    ) -> int:
        stmt = select(func.count()).select_from(ProviderModel)

        if status is not None:
            stmt = stmt.where(ProviderModel.status == status)

        result = await self.session.execute(stmt)
        count = result.scalar()

        return count or 0

    async def delete(self, provider_id: uuid.UUID) -> bool:
        stmt = select(ProviderModel).where(ProviderModel.id == provider_id)
        result = await self.session.execute(stmt)
        provider_model = result.scalars().first()

        if not provider_model:
            return False

        await self.session.delete(provider_model)
        await self.session.commit()

        return True

    async def exists(self, provider_id: uuid.UUID) -> bool:
        stmt = (
            select(func.count())
            .select_from(ProviderModel)
            .where(ProviderModel.id == provider_id)
        )
        result = await self.session.execute(stmt)
        count = result.scalar()

        return bool(count and count > 0)


class SQLAlchemyProviderServiceRepository(ProviderServiceRepository):
    """SQLAlchemy implementation of provider service repository."""

    def __init__(self, session: AsyncSession):
        self.session = session

    def _to_domain(self, model: ProviderServiceModel) -> ProviderService:
        return ProviderService(
            id=model.id,
            provider_id=model.provider_id,
            service_id=model.service_id,
            display_name=model.display_name,
            service_type=model.service_type,
            categories=model.categories or [],
            description=model.description,
            endpoint=model.endpoint,
            parameter_schema=model.parameter_schema,
            result_schema=model.result_schema,
            example_parameters=model.example_parameters,
            is_active=model.is_active,
            client_metadata=model.client_metadata,
            created_by=model.created_by,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    async def create(self, service: ProviderService) -> ProviderService:
        """Denormalizes provider version onto the service row at insert time."""
        provider_version = await self.session.scalar(
            select(ProviderModel.version).where(ProviderModel.id == service.provider_id)
        )
        if provider_version is None:
            raise EntityNotFoundError(
                entity_type="Provider",
                entity_id=service.provider_id,
                code=f"Provider with ID {service.provider_id} not found",
            )

        service_model = ProviderServiceModel(
            id=service.id,
            provider_id=service.provider_id,
            service_id=service.service_id,
            display_name=service.display_name,
            service_type=service.service_type,
            categories=service.categories or [],
            description=service.description,
            endpoint=service.endpoint,
            parameter_schema=service.parameter_schema,
            result_schema=service.result_schema,
            example_parameters=service.example_parameters,
            is_active=service.is_active,
            client_metadata=service.client_metadata,
            version=provider_version,
            created_by=service.created_by,
        )
        self.session.add(service_model)
        await self.session.commit()
        await self.session.refresh(service_model)

        return self._to_domain(service_model)

    async def update(self, service: ProviderService) -> ProviderService:
        stmt = select(ProviderServiceModel).where(ProviderServiceModel.id == service.id)
        result = await self.session.execute(stmt)
        service_model = result.scalars().first()

        if not service_model:
            raise EntityNotFoundError(
                entity_type="ProviderService",
                entity_id=service.id,
                code=f"Provider service with ID {service.id} not found",
            )

        service_model.service_id = service.service_id
        service_model.display_name = service.display_name
        service_model.service_type = service.service_type
        service_model.categories = service.categories or []
        service_model.description = service.description
        service_model.endpoint = service.endpoint
        service_model.parameter_schema = service.parameter_schema
        service_model.result_schema = service.result_schema
        service_model.example_parameters = service.example_parameters
        service_model.is_active = service.is_active
        service_model.client_metadata = service.client_metadata
        service_model.updated_at = datetime.now(UTC)

        await self.session.commit()
        await self.session.refresh(service_model)

        return self._to_domain(service_model)

    async def get_by_id(self, service_id: uuid.UUID) -> Optional[ProviderService]:
        stmt = select(ProviderServiceModel).where(ProviderServiceModel.id == service_id)
        result = await self.session.execute(stmt)
        service_model = result.scalars().first()

        return self._to_domain(service_model) if service_model else None

    async def get_by_service_id(
        self, service_id: str, skip: int, limit: int
    ) -> Optional[ProviderService]:
        stmt = select(ProviderServiceModel).where(
            ProviderServiceModel.service_id == service_id
        )

        stmt = stmt.offset(skip).limit(limit)

        result = await self.session.execute(stmt)
        service_model = result.scalars().first()

        return self._to_domain(service_model) if service_model else None

    async def list_by_provider(
        self,
        provider_id: uuid.UUID,
        skip: int,
        limit: int,
        service_type: Optional[ServiceType] = None,
        is_active: Optional[bool] = None,
        supports_gpu: Optional[bool] = None,
    ) -> List[ProviderService]:
        stmt = select(ProviderServiceModel).where(
            ProviderServiceModel.provider_id == provider_id
        )

        if service_type is not None:
            stmt = stmt.where(ProviderServiceModel.service_type == service_type)
        if is_active is not None:
            stmt = stmt.where(ProviderServiceModel.is_active == is_active)

        stmt = stmt.offset(skip).limit(limit)

        result = await self.session.execute(stmt)
        models = result.scalars().all()

        return [self._to_domain(model) for model in models]

    async def list_by_type(
        self,
        service_type: ServiceType,
        skip: int,
        limit: int,
        is_active: Optional[bool] = None,
    ) -> List[ProviderService]:
        stmt = select(ProviderServiceModel).where(
            ProviderServiceModel.service_type == service_type
        )

        if is_active is not None:
            stmt = stmt.where(ProviderServiceModel.is_active == is_active)

        stmt = stmt.offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        models = result.scalars().all()

        return [self._to_domain(model) for model in models]

    async def search(
        self,
        query: str,
        skip: int,
        limit: int,
    ) -> List[ProviderService]:
        query_lower = f"%{query.lower()}%"
        stmt = select(ProviderServiceModel).where(
            (ProviderServiceModel.service_id.ilike(query_lower))
            | (ProviderServiceModel.description.ilike(query_lower))
        )

        stmt = stmt.offset(skip).limit(limit)

        result = await self.session.execute(stmt)
        models = result.scalars().all()

        return [self._to_domain(model) for model in models]

    async def delete(self, service_id: uuid.UUID) -> bool:
        stmt = select(ProviderServiceModel).where(ProviderServiceModel.id == service_id)
        result = await self.session.execute(stmt)
        service_model = result.scalars().first()

        if not service_model:
            return False

        await self.session.delete(service_model)
        await self.session.commit()

        return True

    async def exists(self, service_id: uuid.UUID) -> bool:
        stmt = (
            select(func.count())
            .select_from(ProviderServiceModel)
            .where(ProviderServiceModel.id == service_id)
        )
        result = await self.session.execute(stmt)
        count = result.scalar()

        return bool(count and count > 0)


class SQLAlchemyProviderCredentialRepository(ProviderCredentialRepository):
    """SQLAlchemy implementation of provider credential repository."""

    def __init__(self, session: AsyncSession):
        self.session = session
        try:
            self._encryption = get_credential_encryption()
            self.encryption_available = True
        except ValueError:
            self._encryption = None
            self.encryption_available = False
            # Suppressed: logger.warning about encryption not configured
            # Uncomment for production deployments:
            # logger.warning(
            #     "Credential encryption not configured. Credentials will be stored unencrypted. "
            #     "Set CREDENTIAL_ENCRYPTION_KEY environment variable for production."
            # )

    def _to_domain(self, model: ProviderCredentialModel) -> ProviderCredential:
        credentials = model.secret_data
        if self.encryption_available and self._encryption:
            credentials = self._encryption.decrypt_credential_dict(model.secret_data)

        return ProviderCredential(
            id=model.id,
            provider_id=model.provider_id,
            organization_id=model.organization_id,
            credential_type=CredentialType(model.credential_type),
            name=model.name,
            description=model.description,
            credentials=credentials or {},
            is_active=model.is_active,
            is_token_type=getattr(model, "is_token_type", False),
            expires_at=model.expires_at,
            created_by=model.created_by,
            client_metadata={},
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    async def create(self, credential: ProviderCredential) -> ProviderCredential:
        credentials_to_store = credential.credentials
        if self.encryption_available and self._encryption:
            credentials_to_store = self._encryption.encrypt_credential_dict(
                credential.credentials
            )

        credential_model = ProviderCredentialModel(
            id=credential.id,
            provider_id=credential.provider_id,
            organization_id=credential.organization_id,
            name=credential.name,
            description=credential.description,
            credential_type=credential.credential_type.value,
            secret_data=credentials_to_store or {},
            is_active=credential.is_active,
            is_token_type=getattr(credential, "is_token_type", False),
            expires_at=credential.expires_at,
            created_by=credential.created_by,
        )
        self.session.add(credential_model)
        await self.session.commit()
        await self.session.refresh(credential_model)

        return self._to_domain(credential_model)

    async def update(self, credential: ProviderCredential) -> ProviderCredential:
        stmt = select(ProviderCredentialModel).where(
            ProviderCredentialModel.id == credential.id
        )
        result = await self.session.execute(stmt)
        credential_model = result.scalars().first()

        if not credential_model:
            raise EntityNotFoundError(
                entity_type="ProviderCredential",
                entity_id=credential.id,
                code=f"Provider credential with ID {credential.id} not found",
            )

        credentials_to_store = credential.credentials
        if self.encryption_available and self._encryption:
            credentials_to_store = self._encryption.encrypt_credential_dict(
                credential.credentials
            )

        credential_model.name = credential.name
        credential_model.description = credential.description
        credential_model.credential_type = credential.credential_type.value
        credential_model.secret_data = credentials_to_store or {}
        credential_model.is_active = credential.is_active
        credential_model.expires_at = credential.expires_at
        credential_model.updated_at = datetime.now(UTC)

        await self.session.commit()
        await self.session.refresh(credential_model)

        return self._to_domain(credential_model)

    async def get_by_id(self, credential_id: uuid.UUID) -> Optional[ProviderCredential]:
        stmt = select(ProviderCredentialModel).where(
            ProviderCredentialModel.id == credential_id
        )
        result = await self.session.execute(stmt)
        credential_model = result.scalars().first()

        return self._to_domain(credential_model) if credential_model else None

    async def get_default_credential(
        self,
        provider_id: uuid.UUID,
        organization_id: uuid.UUID,
    ) -> Optional[ProviderCredential]:
        stmt = (
            select(ProviderCredentialModel)
            .where(
                ProviderCredentialModel.provider_id == provider_id,
                ProviderCredentialModel.organization_id == organization_id,
                ProviderCredentialModel.is_active == True,
            )
            .order_by(ProviderCredentialModel.created_at.desc())
        )
        result = await self.session.execute(stmt)
        credential_model = result.scalars().first()

        return self._to_domain(credential_model) if credential_model else None

    async def list_by_provider(
        self,
        provider_id: uuid.UUID,
        skip: int,
        limit: int,
        credential_type: Optional[CredentialType] = None,
        is_active: Optional[bool] = None,
    ) -> List[ProviderCredential]:
        stmt = select(ProviderCredentialModel).where(
            ProviderCredentialModel.provider_id == provider_id
        )

        if credential_type is not None:
            stmt = stmt.where(
                ProviderCredentialModel.credential_type == credential_type.value
            )
        if is_active is not None:
            stmt = stmt.where(ProviderCredentialModel.is_active == is_active)

        stmt = stmt.offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        models = result.scalars().all()

        return [self._to_domain(model) for model in models]

    async def list_by_organization(
        self,
        organization_id: uuid.UUID,
        skip: int,
        limit: int,
        provider_id: Optional[uuid.UUID] = None,
        credential_type: Optional[CredentialType] = None,
        is_active: Optional[bool] = None,
        search: Optional[str] = None,
    ) -> List[ProviderCredential]:
        stmt = select(ProviderCredentialModel).where(
            ProviderCredentialModel.organization_id == organization_id
        )

        if provider_id is not None:
            stmt = stmt.where(ProviderCredentialModel.provider_id == provider_id)

        if credential_type is not None:
            stmt = stmt.where(
                ProviderCredentialModel.credential_type == credential_type.value
            )

        if is_active is not None:
            stmt = stmt.where(ProviderCredentialModel.is_active == is_active)

        if search is not None:
            stmt = stmt.where(ProviderCredentialModel.name.ilike(f"%{search}%"))

        stmt = stmt.order_by(ProviderCredentialModel.created_at.desc())
        stmt = stmt.offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        models = result.scalars().all()

        return [self._to_domain(model) for model in models]

    async def delete(self, credential_id: uuid.UUID) -> bool:
        stmt = select(ProviderCredentialModel).where(
            ProviderCredentialModel.id == credential_id
        )
        result = await self.session.execute(stmt)
        credential_model = result.scalars().first()

        if not credential_model:
            return False

        await self.session.delete(credential_model)
        await self.session.commit()

        return True

    async def exists(self, credential_id: uuid.UUID) -> bool:
        stmt = (
            select(func.count())
            .select_from(ProviderCredentialModel)
            .where(ProviderCredentialModel.id == credential_id)
        )
        result = await self.session.execute(stmt)
        count = result.scalar()

        return bool(count and count > 0)
