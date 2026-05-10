# api/app/application/services/job_enqueue/iteration_service.py

"""
Iteration handling for workflow step execution.

Handles array expansion (single-call model) and multi-job iteration
(scalar target parameter model) for iterated workflow steps.
"""

import copy
import logging
import uuid
from datetime import datetime, UTC
from typing import Any, Dict, List, Optional

from app.config.settings import settings
from app.application.services.image_presets import apply_image_presets
from app.application.services.mapping_resolver import MappingResolver
from app.infrastructure.errors import safe_error_message
from app.application.services.job_enqueue.step_endpoint_resolver import (
    StepEndpointResolver,
)
from app.application.services.job_enqueue.http_request_builder import (
    build_adapter_for_endpoint,
    try_build_http_request,
)
from app.application.services.job_enqueue.parameter_resolution import (
    resolve_step_parameters,
)
from app.application.services.job_enqueue.variable_resolver import VariableResolver
from app.domain.instance_step.models import StepExecutionStatus
from app.domain.instance.iteration_execution import IterationExecution
from app.domain.instance.iteration_execution_repository import (
    IterationExecutionRepository,
)
from app.domain.instance_step.step_execution_repository import StepExecutionRepository
from app.domain.queue.models import QueuedJob
from app.domain.queue.repository import QueuedJobRepository, WorkerRepository
from app.domain.common.interfaces import JobStatusPublisher
from app.domain.queue.interfaces import QueueRouter, QueueRoutingContext
from app.infrastructure.messaging.queue_router import QueueRoutingError

logger = logging.getLogger(__name__)

# Service ID prefixes that support image style presets
IMAGE_PRESET_SERVICE_PREFIXES = ("shs-comfyui.",)


def supports_image_presets(service_id: Optional[str]) -> bool:
    """True if the service is known to accept image style preset parameters."""
    if not service_id:
        return False
    return service_id.startswith(IMAGE_PRESET_SERVICE_PREFIXES)


def convert_star_to_zero(step_config: Dict[str, Any]) -> Dict[str, Any]:
    """Convert [*] to [0] in all string values within step config.

    When a user maps an iterable array field but doesn't enable iteration,
    default to the first element [0] instead of the [*] wildcard.
    """

    def convert_value(value: object) -> object:
        if isinstance(value, str):
            return value.replace("[*]", "[0]")
        elif isinstance(value, dict):
            return {k: convert_value(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [convert_value(item) for item in value]
        else:
            return value

    result = convert_value(copy.deepcopy(step_config))
    return result if isinstance(result, dict) else step_config


def expand_array_parameter(
    step_config: Dict[str, Any],
    target_parameter: str,
    iteration_config: Dict[str, Any],
    previous_step_results: Dict[str, Any],
    input_mappings: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Expand an array parameter based on iteration configuration.

    Single-call model: copies the prototype N times (one per source element),
    substituting array values into mapped fields.
    """
    config = copy.deepcopy(step_config)

    job = config.get("job", {})
    parameters = job.get("parameters", {})

    # Get the prototype array (what user configured, e.g., 1 scene with mappings)
    prototype_array = parameters.get(target_parameter, [])

    if not isinstance(prototype_array, list):
        logger.debug(
            f"Target parameter '{target_parameter}' is not an array "
            f"(expected for multi-job iteration steps)"
        )
        return step_config

    # Build execution context for the MappingResolver
    execution_context = {
        "steps": previous_step_results,
        "trigger": {},
    }

    # Log source data for iteration
    source_step = iteration_config.get("source_step_id")
    source_field = iteration_config.get("source_output_field")
    if source_step and source_field:
        source_data = previous_step_results.get(source_step, {}).get(source_field, [])
        source_count = len(source_data) if isinstance(source_data, list) else "N/A"
        logger.debug(
            f"Iteration source: {source_step}.{source_field} has {source_count} items"
        )

    # Use MappingResolver to expand the array
    resolver = MappingResolver()
    expanded_array = resolver.expand_array_parameter(
        prototype_array=prototype_array,
        iteration_config=iteration_config,
        execution_context=execution_context,
        input_mappings=input_mappings,
    )

    # Update the parameters with the expanded array
    parameters[target_parameter] = expanded_array
    job["parameters"] = parameters
    config["job"] = job

    logger.info(
        f"Expanded '{target_parameter}' from {len(prototype_array)} prototype(s) "
        f"to {len(expanded_array)} items"
    )

    return config


class IterationJobEnqueuer:
    """Creates multiple jobs for multi-job iteration (scalar target parameter)."""

    def __init__(
        self,
        variable_resolver: VariableResolver,
        endpoint_resolver: StepEndpointResolver,
        queued_job_repository: Optional[QueuedJobRepository],
        worker_repository: Optional[WorkerRepository],
        status_publisher: JobStatusPublisher,
        queue_router: QueueRouter,
        iteration_execution_repository: Optional[IterationExecutionRepository] = None,
        step_execution_repository: Optional[StepExecutionRepository] = None,
        warn_no_workers: bool = True,
    ):
        self.variable_resolver = variable_resolver
        self.endpoint_resolver = endpoint_resolver
        self.queued_job_repository = queued_job_repository
        self.worker_repository = worker_repository
        self.status_publisher = status_publisher
        self.queue_router = queue_router
        self.iteration_execution_repository = iteration_execution_repository
        self.step_execution_repository = step_execution_repository
        self.warn_no_workers = warn_no_workers

    async def enqueue_iteration_jobs(
        self,
        instance_id: uuid.UUID,
        step_id: str,
        organization_id: uuid.UUID,
        workflow_snapshot: Dict[str, Any],
        step_config: Dict[str, Any],
        resolved_step_config: Dict[str, Any],
        iteration_config: Dict[str, Any],
        source_array: List[Any],
        instance_parameters: Optional[Dict[str, Any]] = None,
        previous_step_results: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Create N separate jobs for multi-job iteration (scalar target parameter).

        When iteration is enabled on a step with a scalar target parameter (e.g., prompt),
        N jobs are created - one per source element - instead of expanding arrays in-place.
        Each job gets one source element with [*] substituted to [i], respects batch_size,
        and carries iteration metadata (index, count, group_id).

        Returns the iteration group ID.
        """
        iteration_count = len(source_array)
        iteration_group_id = str(uuid.uuid4())
        job_ids: List[str] = []

        # Resolve common data once (credential, endpoint, etc.)
        credential_id = await self.endpoint_resolver.resolve_step_credential(
            resolved_step_config, organization_id
        )
        endpoint = await self.endpoint_resolver.resolve_step_endpoint(
            resolved_step_config
        )
        org_settings = await self.endpoint_resolver.get_org_settings(organization_id)

        # Extract provider_id and service_id
        job_config_base = resolved_step_config.get("job") or {}
        provider_id_for_worker = resolved_step_config.get(
            "provider_id"
        ) or job_config_base.get("provider_id")
        service_id_for_worker = resolved_step_config.get(
            "service_id"
        ) or job_config_base.get("service_id")

        # Build input_data (outputs from depends_on steps)
        depends_on = step_config.get("depends_on") or []
        input_data = {
            dep_step_id: (previous_step_results or {}).get(dep_step_id, {})
            for dep_step_id in depends_on
            if dep_step_id in (previous_step_results or {})
        }

        # Determine queue name via centralized router - no silent fallback
        try:
            queue_name = self.queue_router.get_queue_name(
                QueueRoutingContext(
                    service_id=service_id_for_worker or "",
                    local_worker=endpoint.local_worker,
                    service_metadata=endpoint.service_metadata,
                    provider_default_queue=endpoint.provider_default_queue,
                )
            )
        except QueueRoutingError as e:
            logger.exception(f"Step {step_id}: queue routing error")
            safe_msg = safe_error_message(e)
            await self.status_publisher.publish_status(
                {
                    "instance_id": str(instance_id),
                    "step_id": step_id,
                    "status": "FAILED",
                    "result": {},
                    "error": safe_msg,
                    "published_at": datetime.now(UTC).isoformat(),
                }
            )
            raise ValueError(safe_msg)

        # Build ALL iteration request params upfront for immediate UI visibility
        iteration_requests = []
        for i in range(iteration_count):
            iter_step_config = copy.deepcopy(resolved_step_config)

            def replace_star(value: object, index: int) -> object:
                if isinstance(value, str):
                    return value.replace("[*]", f"[{index}]")
                elif isinstance(value, dict):
                    return {k: replace_star(v, index) for k, v in value.items()}
                elif isinstance(value, list):
                    return [replace_star(item, index) for item in value]
                return value

            iter_step_config = replace_star(iter_step_config, i)
            iter_step_config_dict: Dict[str, Any] = iter_step_config  # type: ignore[assignment]  - dataclass treated as dict; runtime conversion valid but pyright flags type mismatch
            resolved_iter_config = self.variable_resolver.resolve_variables_in_config(
                iter_step_config_dict,
                previous_step_results or {},
                instance_parameters or {},
            )

            iter_job_config = resolved_iter_config.get("job") or {}
            iter_params = iter_job_config.get("parameters") or {}

            if supports_image_presets(service_id_for_worker):
                if iter_params.get("styles"):
                    iter_params = apply_image_presets(iter_params)

            iteration_requests.append(
                {
                    "iteration_index": i,
                    "params": iter_params,
                }
            )

        logger.debug(
            f"Built {len(iteration_requests)} iteration requests for step {step_id}"
        )

        # Create IterationExecution rows at enqueue time so per-iteration
        # state is persisted in its own table rather than in
        # Instance.output_data["iteration_tracking"]. Rows start in PENDING
        # with parameters populated (middle layer of the three-layer
        # parameter model). Use commit=False so row creation is inside the
        # same transaction as the queued_jobs writes.
        await self._create_iteration_execution_rows(
            instance_id=instance_id,
            step_key=step_id,
            iteration_group_id=iteration_group_id,
            iteration_requests=iteration_requests,
        )

        # Build the adapter once; reuse across all iterations. Constructing
        # GenericHTTPAdapter is dominated by httpx.AsyncClient setup
        # (~3ms), which would otherwise multiply by iteration_count.
        iteration_adapter = build_adapter_for_endpoint(endpoint)

        # Create N jobs, one per source array element
        for i in range(iteration_count):
            iteration_step_config = copy.deepcopy(step_config)

            def replace_star_with_index(value: object, index: int) -> object:
                if isinstance(value, str):
                    return value.replace("[*]", f"[{index}]")
                elif isinstance(value, dict):
                    return {
                        k: replace_star_with_index(v, index) for k, v in value.items()
                    }
                elif isinstance(value, list):
                    return [replace_star_with_index(item, index) for item in value]
                return value

            iteration_step_config = replace_star_with_index(iteration_step_config, i)

            iteration_step_config_dict: Dict[str, Any] = iteration_step_config  # type: ignore[assignment]  - dataclass treated as dict; runtime conversion valid but pyright flags type mismatch
            resolved_iteration_config = (
                self.variable_resolver.resolve_variables_in_config(
                    iteration_step_config_dict,
                    previous_step_results or {},
                    instance_parameters or {},
                )
            )

            # Apply image style presets if applicable
            job_config = resolved_iteration_config.get("job") or {}
            params = job_config.get("parameters") or {}
            if supports_image_presets(service_id_for_worker):
                if params.get("styles"):
                    styled_params = apply_image_presets(params)
                    resolved_iteration_config["job"]["parameters"] = styled_params

            # Build job payload with iteration metadata
            job_id = str(uuid.uuid4())
            job_payload = {
                "job_id": job_id,
                "step_id": step_id,  # stored for API-side result routing only
                "step_config": resolved_iteration_config,
                "input_data": input_data,
                "credential_id": credential_id,
                "provider_id": provider_id_for_worker,
                "service_id": service_id_for_worker,
                "request_url": endpoint.url,
                "http_method": endpoint.http_method,
                "post_processing": endpoint.post_processing,
                "polling": endpoint.polling,
                "auth_config": endpoint.auth_config,
                "local_worker": endpoint.local_worker,
                "parameter_mapping": endpoint.parameter_mapping,
                "default_headers": endpoint.default_headers,
                "dispatch": endpoint.dispatch,
                "org_settings": org_settings,
                "instance_parameters": instance_parameters or {},
                "previous_step_results": previous_step_results or {},
                "workflow_name": workflow_snapshot.get("name", ""),
                "created_at": datetime.now(UTC).isoformat(),
                # Iteration metadata
                "iteration_index": i,
                "iteration_count": iteration_count,
                "iteration_group_id": iteration_group_id,
            }

            # Apply scene expansion + file URL resolution so the
            # per-iteration http_request body is byte-equivalent to what
            # the worker would compute.
            iter_job_cfg = resolved_iteration_config.get("job") or {}
            iter_params = iter_job_cfg.get("parameters")
            if isinstance(iter_params, dict):
                resolved_iteration_config.setdefault("job", {})["parameters"] = (
                    resolve_step_parameters(
                        iter_params,
                        org_id=str(organization_id),
                        instance_id=str(instance_id),
                    )
                )

            # Per-iteration wire envelope.
            iter_http_request = try_build_http_request(
                endpoint=endpoint,
                resolved_step_config=resolved_iteration_config,
                organization_id=organization_id,
                step_id=step_id,
                adapter=iteration_adapter,
            )
            if iter_http_request is not None:
                job_payload["http_request"] = iter_http_request

            job_ids.append(job_id)

            # Build request_body for debugging
            request_body = job_config.get("parameters") or {}

            # Publish QUEUED status for this iteration job
            # input_data = resolved parameters (Contract 3 compliant)
            queued_result = {
                "instance_id": str(instance_id),
                "step_id": step_id,
                "status": "QUEUED",
                "result": {},
                "error": None,
                "input_data": request_body,
                "request_body": request_body,
                "published_at": datetime.now(UTC).isoformat(),
                "iteration_index": i,
                "iteration_count": iteration_count,
                "iteration_group_id": iteration_group_id,
            }

            # Only publish QUEUED once (for first job) to avoid UI spam
            if i == 0:
                queued_result["iteration_requests"] = iteration_requests
                await self.status_publisher.publish_status(queued_result)
                logger.debug(
                    f"Published QUEUED status for iteration group {iteration_group_id} "
                    f"with {len(iteration_requests)} iteration requests"
                )

            # Enqueue job to PostgreSQL
            await self._enqueue_to_postgres(
                job_id=uuid.UUID(job_id),
                instance_id=instance_id,
                organization_id=organization_id,
                step_id=step_id,
                queue_name=queue_name,
                payload=job_payload,
            )

        logger.debug(
            f"Created {iteration_count} iteration jobs for step {step_id}: "
            f"group_id={iteration_group_id}, job_ids={job_ids}"
        )

        # Check worker availability once
        if self.warn_no_workers and self.worker_repository:
            await self._check_worker_availability(queue_name)

        return iteration_group_id

    async def _enqueue_to_postgres(
        self,
        job_id: uuid.UUID,
        instance_id: uuid.UUID,
        organization_id: uuid.UUID,
        step_id: str,
        queue_name: str,
        payload: Dict[str, Any],
    ) -> None:
        """Enqueue a job to PostgreSQL queued_jobs table."""
        if not self.queued_job_repository:
            logger.error(
                "queued_job_repository not available - job will not be enqueued"
            )
            return

        queued_job = QueuedJob(
            id=job_id,
            organization_id=organization_id,
            enqueued_by=organization_id,
            queue_name=queue_name,
            instance_id=instance_id,
            priority=0,
            status=StepExecutionStatus.PENDING,
            input_data=payload,
            enqueued_at=datetime.now(UTC),
        )

        await self.queued_job_repository.create(queued_job)

    async def _create_iteration_execution_rows(
        self,
        instance_id: uuid.UUID,
        step_key: str,
        iteration_group_id: str,
        iteration_requests: List[Dict[str, Any]],
    ) -> None:
        """Create per-iteration execution rows at enqueue time.

        Eager creation is required for the three-layer parameter model and
        for edit-params semantics (parameters must be mutable before worker claim).
        """
        if (
            self.iteration_execution_repository is None
            or self.step_execution_repository is None
        ):
            # Repos not wired - skip. Covered by the DI default paths
            # (standalone workers, some test setups). Production DI wiring
            # always provides both.
            logger.debug(
                "IterationExecutionRepository not wired; skipping row creation"
            )
            return

        step = await self.step_execution_repository.get_by_instance_and_key(
            instance_id=instance_id,
            step_key=step_key,
        )
        if step is None:
            logger.warning(
                f"InstanceStep not found for (instance={instance_id}, "
                f"step_key={step_key}); skipping iteration row creation"
            )
            return

        try:
            group_uuid = uuid.UUID(iteration_group_id)
        except (ValueError, AttributeError):
            group_uuid = None

        iterations = [
            IterationExecution.create(
                instance_id=instance_id,
                step_id=step.id,
                iteration_index=req["iteration_index"],
                iteration_group_id=group_uuid,
                parameters=req.get("params") or {},
            )
            for req in iteration_requests
        ]
        await self.iteration_execution_repository.create_many(iterations, commit=False)
        logger.debug(
            f"Created {len(iterations)} IterationExecution rows for "
            f"step={step_key} group={iteration_group_id}"
        )

    async def _check_worker_availability(self, queue_name: str) -> None:
        """Warn if no active workers are registered for the queue."""
        try:
            if not self.worker_repository:
                return
            active_workers = await self.worker_repository.list_active_workers(
                skip=0, limit=settings.DEFAULT_FETCH_LIMIT
            )
            count = len(active_workers)
            if count == 0:
                logger.warning(
                    f"No active workers for queue '{queue_name}'! "
                    f"Jobs will wait until a worker registers."
                )
        except Exception as e:
            logger.warning(f"Could not check worker availability: {e}")
