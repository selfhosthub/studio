# api/app/application/services/instance/deletion_service.py

"""Full instance deletion: files first, then FK-safe DB row order, then workspace dir.

Order: resource files → resources → queued_jobs → job_executions → steps →
instance → workspace dir."""

import logging
import shutil
import uuid
from dataclasses import dataclass

from app.domain.instance.repository import InstanceRepository
from app.domain.instance_step.step_execution_repository import StepExecutionRepository
from app.domain.org_file.repository import OrgFileRepository
from app.domain.queue.repository import QueuedJobRepository
from app.infrastructure.storage.workspace import (
    cleanup_resource_files,
    get_workspace_path,
)

logger = logging.getLogger(__name__)


@dataclass
class DeletionResult:
    instance_id: uuid.UUID
    files_deleted: int
    resources_deleted: int
    jobs_deleted: int
    steps_deleted: int
    queued_jobs_deleted: int
    directory_removed: bool


class DeletionService:
    def __init__(
        self,
        instance_repository: InstanceRepository,
        step_execution_repository: StepExecutionRepository,
        resource_repository: OrgFileRepository,
        queued_job_repository: QueuedJobRepository,
    ):
        self.instance_repository = instance_repository
        self.step_execution_repository = step_execution_repository
        self.resource_repository = resource_repository
        self.queued_job_repository = queued_job_repository

    async def delete_instance(
        self,
        instance_id: uuid.UUID,
        organization_id: uuid.UUID,
    ) -> DeletionResult:
        """Permanently delete an instance and all associated data.

        Caller must verify existence, authorization, and terminal status."""
        workspace_path = get_workspace_path()
        files_deleted = 0

        resources = await self.resource_repository.list_by_instance(instance_id)
        for resource in resources:
            virtual_path = resource.virtual_path
            thumbnail_path = (
                resource.metadata.get("thumbnail_path") if resource.metadata else None
            )
            try:
                cleanup_resource_files(
                    virtual_path=virtual_path,
                    thumbnail_path=thumbnail_path,
                    workspace_path=workspace_path,
                )
                files_deleted += 1
                if thumbnail_path:
                    files_deleted += 1
            except Exception as e:
                logger.warning(f"Failed to delete file for resource {resource.id}: {e}")

        for resource in resources:
            await self.resource_repository.delete(resource.id)

        queued_jobs_deleted = await self.queued_job_repository.delete_by_instance(
            instance_id
        )

        jobs_deleted = await self.step_execution_repository.delete_by_instance(instance_id)

        steps_deleted = await self.step_execution_repository.delete_by_instance(
            instance_id
        )

        await self.instance_repository.delete(instance_id)

        directory_removed = False
        instance_dir = (
            workspace_path
            / "orgs"
            / str(organization_id)
            / "instances"
            / str(instance_id)
        )
        if instance_dir.exists():
            try:
                shutil.rmtree(instance_dir)
                directory_removed = True
                logger.info(f"Removed instance directory: {instance_dir}")
            except Exception as e:
                logger.warning(
                    f"Failed to remove instance directory {instance_dir}: {e}"
                )

        logger.info(
            f"Deleted instance {instance_id}: "
            f"{files_deleted} files, {len(resources)} resources, "
            f"{jobs_deleted} jobs, {steps_deleted} steps, "
            f"{queued_jobs_deleted} queued jobs"
        )

        return DeletionResult(
            instance_id=instance_id,
            files_deleted=files_deleted,
            resources_deleted=len(resources),
            jobs_deleted=jobs_deleted,
            steps_deleted=steps_deleted,
            queued_jobs_deleted=queued_jobs_deleted,
            directory_removed=directory_removed,
        )
