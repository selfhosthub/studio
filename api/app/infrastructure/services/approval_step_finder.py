# api/app/infrastructure/services/approval_step_finder.py

"""Identifies approval steps in a workflow by checking service configurations."""

import logging
from typing import Dict, List, Optional

from app.domain.instance.models import Instance
from app.infrastructure.repositories.provider_repository import (
    SQLAlchemyProviderServiceRepository,
)

logger = logging.getLogger(__name__)


class ApprovalStepFinder:
    """Finds the first approval step among ready workflow steps via orchestrator_hints."""

    async def find_approval_step(
        self,
        instance: Instance,
        ready_steps: List[str],
        provider_service_repo: SQLAlchemyProviderServiceRepository,
    ) -> Optional[str]:
        logger.debug(f"find_approval_step: ready_steps={ready_steps}")

        if not instance.workflow_snapshot:
            logger.debug("find_approval_step: no workflow_snapshot")
            return None

        steps = instance.workflow_snapshot.get("steps", {})

        for step_id in ready_steps:
            if await self._is_approval_step(step_id, steps, provider_service_repo):
                return step_id

        logger.debug("find_approval_step: no approval step found")
        return None

    async def _is_approval_step(
        self,
        step_id: str,
        steps: Dict,
        provider_service_repo: SQLAlchemyProviderServiceRepository,
    ) -> bool:
        """Check if a single step is an approval step."""
        step_config = steps.get(step_id)
        if not step_config or not isinstance(step_config, dict):
            logger.debug(f"find_approval_step: step {step_id} has no config")
            return False

        service_id = self._get_service_id(step_config)
        logger.debug(f"find_approval_step: step {step_id} has service_id={service_id}")

        if service_id:
            if await self._check_service_hints(
                step_id, service_id, provider_service_repo
            ):
                return True

        # Also check step_type - some workflows set this without a service_id.
        step_type = step_config.get("step_type", "")
        if step_type and step_type.lower() == "approval":
            logger.info(
                f"find_approval_step: found approval step {step_id} via step_type"
            )
            return True

        return False

    def _get_service_id(self, step_config: Dict) -> str:
        """Extract service_id from step config (step level or job level)."""
        service_id = step_config.get("service_id", "")
        if not service_id:
            job = step_config.get("job")
            if job and isinstance(job, dict):
                service_id = job.get("service_id", "")
        return service_id

    async def _check_service_hints(
        self,
        step_id: str,
        service_id: str,
        provider_service_repo: SQLAlchemyProviderServiceRepository,
    ) -> bool:
        """Check if service requires human approval via orchestrator_hints."""
        service = await provider_service_repo.get_by_service_id(
            service_id, skip=0, limit=1
        )
        logger.debug(
            f"find_approval_step: service lookup for {service_id} returned {service is not None}"
        )

        if service:
            client_metadata = service.client_metadata or {}
            orchestrator_hints = client_metadata.get("orchestrator_hints", {})
            logger.debug(f"find_approval_step: client_metadata={client_metadata}")
            logger.debug(f"find_approval_step: orchestrator_hints={orchestrator_hints}")

            if (
                orchestrator_hints
                and orchestrator_hints.get("wait_for") == "human_action"
            ):
                logger.info(f"find_approval_step: found approval step {step_id}")
                return True
        else:
            # Fallback: check known approval service IDs if database lookup fails
            if service_id == "core.approval":
                logger.warning(
                    f"find_approval_step: service {service_id} not found in DB, "
                    "but detected via known service_id fallback"
                )
                return True

        return False
