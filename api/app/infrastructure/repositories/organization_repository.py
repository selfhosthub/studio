# api/app/infrastructure/repositories/organization_repository.py

"""SQLAlchemy repository implementation for organization domain entities."""
import uuid
from datetime import UTC, datetime
from typing import Any, List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import attributes

from app.domain.common.exceptions import EntityNotFoundError
from app.domain.common.value_objects import (
    ActivationMethod,
    Email,
    OrganizationStatus,
    Role,
)
from app.domain.organization.models import Organization, User
from app.domain.organization.repository import (
    OrganizationRepository,
    UserRepository,
)
from app.infrastructure.persistence.models import (
    OrganizationModel,
    BlueprintModel,
    UserModel,
    InstanceModel,
    WorkflowModel,
)


class SQLAlchemyOrganizationRepository(OrganizationRepository):
    """SQLAlchemy implementation of organization repository."""

    def __init__(self, session: AsyncSession):
        self.session = session

    def _to_domain(self, model: OrganizationModel) -> Organization:
        settings: dict[str, Any] = model.settings or {}

        status = model.status if model.status else OrganizationStatus.ACTIVE

        activation_method = None
        if model.activation_method:
            try:
                activation_method = ActivationMethod(model.activation_method)
            except ValueError:
                activation_method = None

        return Organization(
            id=model.id,
            name=model.name,
            slug=model.slug,
            description=model.description,
            is_active=model.is_active,
            status=status,
            settings=settings,
            max_users=None,
            max_workflows=None,
            activated_at=model.activated_at,
            activated_by=model.activated_by,
            activation_method=activation_method,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    async def create(self, organization: Organization) -> Organization:
        org_model = OrganizationModel(
            id=organization.id,
            name=organization.name,
            slug=organization.slug,
            description=organization.description,
            is_active=organization.is_active,
            status=organization.status,
            settings=organization.settings,
            activated_at=organization.activated_at,
            activated_by=organization.activated_by,
            activation_method=(
                organization.activation_method.value
                if organization.activation_method
                else None
            ),
            created_at=organization.created_at,
            updated_at=organization.updated_at,
        )

        self.session.add(org_model)
        await self.session.commit()
        await self.session.refresh(org_model)

        return self._to_domain(org_model)

    async def update(self, organization: Organization) -> Organization:
        stmt = select(OrganizationModel).where(OrganizationModel.id == organization.id)
        result = await self.session.execute(stmt)
        org_model = result.scalars().first()

        if not org_model:
            raise EntityNotFoundError(
                entity_type="Organization",
                entity_id=organization.id,
            )

        org_model.name = organization.name
        org_model.slug = organization.slug
        org_model.description = organization.description
        org_model.is_active = organization.is_active
        org_model.status = organization.status
        org_model.settings = organization.settings
        # Explicitly mark settings as modified for SQLAlchemy JSON column mutation detection
        attributes.flag_modified(org_model, "settings")

        org_model.activated_at = organization.activated_at
        org_model.activated_by = organization.activated_by
        org_model.activation_method = organization.activation_method  # type: ignore[assignment]  - domain enum assigned to SA column; SA type stubs expect Column type

        org_model.updated_at = organization.updated_at or datetime.now(UTC)  # type: ignore[assignment]  - domain datetime assigned to SA column; SA type stubs expect Column type

        await self.session.commit()
        await self.session.refresh(org_model)

        return self._to_domain(org_model)

    async def get_by_id(self, organization_id: uuid.UUID) -> Optional[Organization]:
        stmt = select(OrganizationModel).where(OrganizationModel.id == organization_id)
        result = await self.session.execute(stmt)
        org_model = result.scalars().first()

        if not org_model:
            return None

        return self._to_domain(org_model)

    async def get_by_slug(self, slug: str) -> Optional[Organization]:
        stmt = select(OrganizationModel).where(OrganizationModel.slug == slug)
        result = await self.session.execute(stmt)
        org_model = result.scalars().first()

        if not org_model:
            return None

        return self._to_domain(org_model)

    async def find_active_organizations(
        self,
        skip: int,
        limit: int,
    ) -> List[Organization]:
        stmt = select(OrganizationModel).where(OrganizationModel.is_active == True)

        stmt = stmt.offset(skip).limit(limit)

        result = await self.session.execute(stmt)
        org_models = result.scalars().all()

        return [self._to_domain(org_model) for org_model in org_models]

    async def search(
        self,
        query: str,
        skip: int,
        limit: int,
    ) -> List[Organization]:
        search_pattern = f"%{query}%"
        stmt = select(OrganizationModel).where(
            (OrganizationModel.name.ilike(search_pattern))
            | (OrganizationModel.slug.ilike(search_pattern))
        )

        stmt = stmt.offset(skip).limit(limit)

        result = await self.session.execute(stmt)
        org_models = result.scalars().all()

        return [self._to_domain(org_model) for org_model in org_models]

    async def list_all(self) -> List[Organization]:
        stmt = select(OrganizationModel).order_by(OrganizationModel.name)
        result = await self.session.execute(stmt)
        org_models = result.scalars().all()

        return [self._to_domain(org_model) for org_model in org_models]

    async def count_workflows(self, organization_id: uuid.UUID) -> int:
        stmt = (
            select(func.count())
            .select_from(WorkflowModel)
            .where(WorkflowModel.organization_id == organization_id)
        )
        result = await self.session.execute(stmt)
        count = result.scalar()

        return int(count) if count else 0

    async def count_active_users(self, organization_id: uuid.UUID) -> int:
        stmt = (
            select(func.count())
            .select_from(UserModel)
            .where(
                (UserModel.organization_id == organization_id)
                & (UserModel.is_active == True)
            )
        )
        result = await self.session.execute(stmt)
        count = result.scalar()

        return int(count) if count else 0

    async def count_blueprints(self, organization_id: uuid.UUID) -> int:
        stmt = (
            select(func.count())
            .select_from(BlueprintModel)
            .where(BlueprintModel.organization_id == organization_id)
        )
        result = await self.session.execute(stmt)
        count = result.scalar()

        return int(count) if count else 0

    async def count_instances(self, organization_id: uuid.UUID) -> int:
        stmt = (
            select(func.count())
            .select_from(InstanceModel)
            .where(InstanceModel.organization_id == organization_id)
        )
        result = await self.session.execute(stmt)
        count = result.scalar()

        return int(count) if count else 0

    async def delete(self, organization_id: uuid.UUID) -> bool:
        stmt = select(OrganizationModel).where(OrganizationModel.id == organization_id)
        result = await self.session.execute(stmt)
        org_model = result.scalars().first()

        if not org_model:
            return False

        await self.session.delete(org_model)
        await self.session.commit()

        return True

    async def exists(self, organization_id: uuid.UUID) -> bool:
        stmt = (
            select(func.count())
            .select_from(OrganizationModel)
            .where(OrganizationModel.id == organization_id)
        )
        result = await self.session.execute(stmt)
        count = result.scalar()

        return bool(count and count > 0)

    async def find_by_status(
        self,
        status: OrganizationStatus,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Organization]:
        stmt = (
            select(OrganizationModel)
            .where(OrganizationModel.status == status)
            .order_by(OrganizationModel.created_at.desc())
            .offset(skip)
            .limit(limit)
        )

        result = await self.session.execute(stmt)
        org_models = result.scalars().all()

        return [self._to_domain(org_model) for org_model in org_models]

    async def count_by_status(self, status: OrganizationStatus) -> int:
        stmt = (
            select(func.count())
            .select_from(OrganizationModel)
            .where(OrganizationModel.status == status)
        )
        result = await self.session.execute(stmt)
        count = result.scalar()

        return int(count) if count else 0


class SQLAlchemyUserRepository(UserRepository):
    """SQLAlchemy implementation of user repository."""

    def __init__(self, session: AsyncSession):
        self.session = session

    def _to_domain(self, model: UserModel) -> User:
        role = Role(model.role)
        email = Email(email=model.email)

        return User(
            id=model.id,
            organization_id=model.organization_id,
            username=model.username,
            email=email,
            hashed_password=model.hashed_password,
            role=role,
            is_active=model.is_active,
            first_name=model.first_name,
            last_name=model.last_name,
            avatar_url=model.avatar_url,
            bio=model.bio,
            is_public=model.is_public or False,
            created_at=model.created_at,
            updated_at=model.updated_at,
            last_login=model.last_login,
            password_changed_at=model.password_changed_at,
            role_changed_at=model.role_changed_at,
            logged_out_at=model.logged_out_at,
        )

    async def create(self, user: User) -> User:
        user_model = UserModel(
            id=user.id,
            username=user.username,
            email=user.email.email,
            hashed_password=user.hashed_password,
            role=user.role.value,
            is_active=user.is_active,
            first_name=user.first_name,
            last_name=user.last_name,
            avatar_url=user.avatar_url,
            bio=user.bio,
            is_public=user.is_public,
            organization_id=user.organization_id,
            created_at=user.created_at,
            updated_at=user.updated_at,
        )

        self.session.add(user_model)
        await self.session.commit()
        await self.session.refresh(user_model)

        return self._to_domain(user_model)

    async def update(self, user: User) -> User:
        stmt = select(UserModel).where(UserModel.id == user.id)
        result = await self.session.execute(stmt)
        user_model = result.scalars().first()

        if not user_model:
            raise EntityNotFoundError(
                entity_id=user.id,
                entity_type="User",
            )

        user_model.username = user.username
        user_model.email = user.email.email
        user_model.hashed_password = user.hashed_password
        user_model.role = user.role.value
        user_model.is_active = user.is_active
        user_model.first_name = user.first_name
        user_model.last_name = user.last_name
        user_model.avatar_url = user.avatar_url
        user_model.bio = user.bio
        user_model.is_public = user.is_public
        user_model.last_login = user.last_login
        user_model.password_changed_at = user.password_changed_at
        user_model.role_changed_at = user.role_changed_at
        user_model.logged_out_at = user.logged_out_at

        user_model.updated_at = user.updated_at or datetime.now(UTC)  # type: ignore[assignment]  - domain datetime assigned to SA column; SA type stubs expect Column type

        await self.session.commit()
        await self.session.refresh(user_model)

        return self._to_domain(user_model)

    async def get_by_id(self, user_id: uuid.UUID) -> Optional[User]:
        stmt = select(UserModel).where(UserModel.id == user_id)
        result = await self.session.execute(stmt)
        user_model = result.scalars().first()

        if not user_model:
            return None

        return self._to_domain(user_model)

    async def get_by_email(self, email: str) -> Optional[User]:
        stmt = select(UserModel).where(UserModel.email == email)
        result = await self.session.execute(stmt)
        user_model = result.scalars().first()

        if not user_model:
            return None

        return self._to_domain(user_model)

    async def get_by_username(self, username: str) -> Optional[User]:
        stmt = select(UserModel).where(func.lower(UserModel.username) == username.strip().lower())
        result = await self.session.execute(stmt)
        user_model = result.scalars().first()

        if not user_model:
            return None

        return self._to_domain(user_model)

    async def find_by_email(self, email: str) -> Optional[User]:
        return await self.get_by_email(email)

    async def find_active_users_in_organization(
        self,
        organization_id: uuid.UUID,
        skip: int,
        limit: int,
    ) -> List[User]:
        stmt = select(UserModel).where(
            (UserModel.organization_id == organization_id)
            & (UserModel.is_active == True)
        )

        stmt = stmt.offset(skip).limit(limit)

        result = await self.session.execute(stmt)
        user_models = result.scalars().all()

        return [self._to_domain(user_model) for user_model in user_models]

    async def list(
        self,
        skip: int,
        limit: int,
        organization_id: Optional[uuid.UUID] = None,
        only_active: bool = False,
    ) -> List[User]:
        stmt = select(UserModel)

        if organization_id:
            stmt = stmt.where(UserModel.organization_id == organization_id)

        if only_active:
            stmt = stmt.where(UserModel.is_active == True)

        stmt = stmt.offset(skip).limit(limit)

        result = await self.session.execute(stmt)
        user_models = result.scalars().all()

        return [self._to_domain(user_model) for user_model in user_models]

    async def search(
        self,
        query: str,
        skip: int,
        limit: int,
        organization_id: Optional[uuid.UUID] = None,
    ) -> List[User]:
        search_pattern = f"%{query}%"

        stmt = select(UserModel).where(
            (UserModel.username.ilike(search_pattern))
            | (UserModel.email.ilike(search_pattern))
            | (UserModel.first_name.ilike(search_pattern))
            | (UserModel.last_name.ilike(search_pattern))
        )

        if organization_id:
            stmt = stmt.where(UserModel.organization_id == organization_id)

        stmt = stmt.offset(skip).limit(limit)

        result = await self.session.execute(stmt)
        user_models = result.scalars().all()

        return [self._to_domain(user_model) for user_model in user_models]

    async def delete(self, user_id: uuid.UUID) -> bool:
        stmt = select(UserModel).where(UserModel.id == user_id)
        result = await self.session.execute(stmt)
        user_model = result.scalars().first()

        if not user_model:
            return False

        await self.session.delete(user_model)
        await self.session.commit()

        return True

    async def count_by_organization_and_role(
        self, organization_id: uuid.UUID, role: Role, only_active: bool = True
    ) -> int:
        stmt = (
            select(func.count())
            .select_from(UserModel)
            .where(
                (UserModel.organization_id == organization_id)
                & (UserModel.role == role)
            )
        )

        if only_active:
            stmt = stmt.where(UserModel.is_active == True)

        result = await self.session.execute(stmt)
        count = result.scalar()

        return int(count) if count else 0

    async def exists(self, user_id: uuid.UUID) -> bool:
        stmt = (
            select(func.count()).select_from(UserModel).where(UserModel.id == user_id)
        )
        result = await self.session.execute(stmt)
        count = result.scalar()

        return bool(count and count > 0)

    async def list_public_team(self) -> List[User]:
        """List active users with is_public=True, ordered by creation date."""
        stmt = (
            select(UserModel)
            .where(UserModel.is_public == True, UserModel.is_active == True)
            .order_by(UserModel.created_at)
        )
        result = await self.session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]
