# api/app/infrastructure/repositories/org_file_repository.py

"""SQLAlchemy implementation of OrgFileRepository."""

import uuid
from typing import List, Optional, Tuple

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.org_file.models import (
    OrgFile,
    ResourceSource,
    ResourceStatus,
)
from app.domain.org_file.repository import OrgFileRepository
from app.infrastructure.persistence.models import (
    OrgFileModel,
    StepExecutionModel,
)


class SQLAlchemyOrgFileRepository(OrgFileRepository):
    """SQLAlchemy implementation of job output resource repository."""

    def __init__(self, session: AsyncSession):
        self.session = session

    def _to_domain(self, model: OrgFileModel) -> OrgFile:
        return OrgFile(
            id=model.id,
            job_execution_id=model.job_execution_id,
            instance_id=model.instance_id,
            instance_step_id=model.instance_step_id,
            organization_id=model.organization_id,
            file_extension=model.file_extension,
            file_size=model.file_size,
            mime_type=model.mime_type,
            checksum=model.checksum,
            virtual_path=model.virtual_path,
            display_name=model.display_name,
            source=model.source,
            provider_id=model.provider_id,
            provider_resource_id=model.provider_resource_id,
            provider_url=model.provider_url,
            download_timestamp=model.download_timestamp,
            status=model.status,
            metadata=model.resource_metadata,
            has_thumbnail=model.has_thumbnail,
            display_order=model.display_order,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    def _to_model(self, entity: OrgFile) -> OrgFileModel:
        return OrgFileModel(
            id=entity.id,
            job_execution_id=entity.job_execution_id,
            instance_id=entity.instance_id,
            instance_step_id=entity.instance_step_id,
            organization_id=entity.organization_id,
            file_extension=entity.file_extension,
            file_size=entity.file_size,
            mime_type=entity.mime_type,
            checksum=entity.checksum,
            virtual_path=entity.virtual_path,
            display_name=entity.display_name,
            source=entity.source,
            provider_id=entity.provider_id,
            provider_resource_id=entity.provider_resource_id,
            provider_url=entity.provider_url,
            download_timestamp=entity.download_timestamp,
            status=entity.status,
            resource_metadata=entity.metadata,
            has_thumbnail=entity.has_thumbnail,
            display_order=entity.display_order,
        )

    async def create(self, resource: OrgFile) -> OrgFile:
        model = self._to_model(resource)
        self.session.add(model)
        await self.session.flush()
        await self.session.refresh(model)
        await self.session.commit()
        return self._to_domain(model)

    async def get_by_id(self, resource_id: uuid.UUID) -> Optional[OrgFile]:
        stmt = select(OrgFileModel).where(
            OrgFileModel.id == resource_id
        )
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model else None

    async def list_by_job(self, job_execution_id: uuid.UUID) -> List[OrgFile]:
        # job_execution_id is the step execution row ID - lookup is effectively
        # identity, but also picks up user uploads linked by instance_step_id.
        job_stmt = select(StepExecutionModel.id).where(
            StepExecutionModel.id == job_execution_id
        )
        job_result = await self.session.execute(job_stmt)
        instance_step_id = job_result.scalar_one_or_none()

        # Build query: match by job_execution_id OR by instance_step_id (if job has one)
        if instance_step_id:
            stmt = (
                select(OrgFileModel)
                .where(
                    or_(
                        OrgFileModel.job_execution_id == job_execution_id,
                        OrgFileModel.instance_step_id == instance_step_id,
                    )
                )
                .where(OrgFileModel.status != ResourceStatus.DELETED)
                .order_by(
                    OrgFileModel.display_order.asc(),
                    OrgFileModel.created_at.asc(),
                )
            )
        else:
            # Fallback: only match by job_execution_id
            stmt = (
                select(OrgFileModel)
                .where(OrgFileModel.job_execution_id == job_execution_id)
                .where(OrgFileModel.status != ResourceStatus.DELETED)
                .order_by(
                    OrgFileModel.display_order.asc(),
                    OrgFileModel.created_at.asc(),
                )
            )

        result = await self.session.execute(stmt)
        models = result.scalars().all()
        return [self._to_domain(model) for model in models]

    async def list_by_instance(
        self,
        instance_id: uuid.UUID,
        status: Optional[ResourceStatus] = None,
        source: Optional[ResourceSource] = None,
    ) -> List[OrgFile]:
        stmt = (
            select(OrgFileModel)
            .where(OrgFileModel.instance_id == instance_id)
            .where(OrgFileModel.status != ResourceStatus.DELETED)
        )

        if status:
            stmt = stmt.where(OrgFileModel.status == status)

        if source:
            stmt = stmt.where(OrgFileModel.source == source)

        stmt = stmt.order_by(OrgFileModel.created_at.asc())

        result = await self.session.execute(stmt)
        models = result.scalars().all()
        return [self._to_domain(model) for model in models]

    async def list_by_organization(
        self,
        organization_id: uuid.UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> List[OrgFile]:
        stmt = (
            select(OrgFileModel)
            .where(OrgFileModel.organization_id == organization_id)
            .where(OrgFileModel.status != ResourceStatus.DELETED)
            .order_by(OrgFileModel.created_at.desc())
            .offset(skip)
            .limit(limit)
        )

        result = await self.session.execute(stmt)
        models = result.scalars().all()
        return [self._to_domain(model) for model in models]

    async def update(self, resource: OrgFile) -> OrgFile:
        stmt = select(OrgFileModel).where(
            OrgFileModel.id == resource.id
        )
        result = await self.session.execute(stmt)
        model = result.scalar_one()

        # Update fields
        model.status = resource.status
        model.resource_metadata = resource.metadata
        model.has_thumbnail = resource.has_thumbnail
        model.checksum = resource.checksum

        await self.session.flush()
        await self.session.refresh(model)
        await self.session.commit()
        return self._to_domain(model)

    async def delete(self, resource_id: uuid.UUID) -> None:
        stmt = select(OrgFileModel).where(
            OrgFileModel.id == resource_id
        )
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()

        if model:
            await self.session.delete(model)
            await self.session.flush()
            await self.session.commit()

    async def list_by_instance_step(
        self,
        instance_step_id: uuid.UUID,
    ) -> List[OrgFile]:
        stmt = (
            select(OrgFileModel)
            .where(OrgFileModel.instance_step_id == instance_step_id)
            .where(OrgFileModel.status != ResourceStatus.DELETED)
            .order_by(OrgFileModel.created_at.desc())
        )
        result = await self.session.execute(stmt)
        models = result.scalars().all()
        return [self._to_domain(model) for model in models]

    async def batch_update_order(
        self,
        order_updates: List[Tuple[uuid.UUID, int]],
    ) -> List[OrgFile]:
        for resource_id, new_order in order_updates:
            stmt = (
                update(OrgFileModel)
                .where(OrgFileModel.id == resource_id)
                .values(display_order=new_order)
            )
            await self.session.execute(stmt)

        await self.session.commit()

        # Fetch and return updated resources in order
        resource_ids = [rid for rid, _ in order_updates]
        stmt = (
            select(OrgFileModel)
            .where(OrgFileModel.id.in_(resource_ids))
            .order_by(OrgFileModel.display_order.asc())
        )
        result = await self.session.execute(stmt)
        return [self._to_domain(model) for model in result.scalars().all()]
