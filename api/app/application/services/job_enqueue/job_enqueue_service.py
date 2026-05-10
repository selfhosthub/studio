# api/app/application/services/job_enqueue/job_enqueue_service.py

"""Orchestrator for enqueueing workflow steps.

Resolution pipeline order is load-bearing:
1. Resolve {{ }} expressions (skips [*] placeholders)
2. Expand [*] into array items (must run after step 1 to know source array length)
"""

import logging
import uuid
from datetime import datetime, UTC
from typing import Any, Dict, Optional

from app.config.settings import settings
from app.application.services.image_presets import apply_image_presets
from app.application.services.job_enqueue.variable_resolver import VariableResolver
from app.infrastructure.errors import safe_error_message
from app.application.services.job_enqueue.input_mapping_service import (
    get_input_mappings,
    apply_input_mappings,
    pre_resolve_prompts,
)
from app.application.services.job_enqueue.iteration_service import (
    convert_star_to_zero,
    expand_array_parameter,
    supports_image_presets,
    IterationJobEnqueuer,
)
from app.application.services.job_enqueue.step_endpoint_resolver import (
    EmptyIterationSourceError,
    StepEndpointResolver,
)
from app.application.services.job_enqueue.http_request_builder import (
    try_build_http_request,
)
from app.application.services.job_enqueue.parameter_resolution import (
    resolve_step_parameters,
)
from app.application.services.job_enqueue.step_readiness import (
    find_entry_step,
    get_ready_steps,
)
from app.application.services.job_enqueue.inline_service_executor import (
    InlineServiceExecutor,
)
from app.domain.instance_step.models import StepExecutionStatus
from app.domain.instance.iteration_execution_repository import (
    IterationExecutionRepository,
)
from app.domain.instance_step.step_execution_repository import StepExecutionRepository
from app.domain.organization.repository import OrganizationRepository
from app.domain.provider.repository import (
    ProviderCredentialRepository,
    ProviderRepository,
    ProviderServiceRepository,
)
from app.domain.queue.models import QueuedJob
from app.domain.queue.repository import QueuedJobRepository, WorkerRepository
from app.domain.workflow.repository import WorkflowRepository
from app.domain.common.interfaces import JobStatusPublisher
from app.domain.queue.interfaces import QueueRoutingContext
from app.infrastructure.messaging.queue_router import (
    QueueRouter,
    QueueRoutingError,
)
from app.infrastructure.logging.request_context import get_request_context

logger = logging.getLogger(__name__)

# Enable worker availability warnings (set to False in tests)
WARN_NO_WORKERS = settings.WARN_NO_WORKERS


class JobEnqueueService:

    def __init__(
        self,
        workflow_repository: WorkflowRepository,
        credential_repository: ProviderCredentialRepository,
        provider_repository: ProviderRepository,
        provider_service_repository: ProviderServiceRepository,
        status_publisher: JobStatusPublisher,
        organization_repository: Optional[OrganizationRepository] = None,
        queued_job_repository: Optional[QueuedJobRepository] = None,
        worker_repository: Optional[WorkerRepository] = None,
        prompt_service: Optional[Any] = None,
        iteration_execution_repository: Optional[IterationExecutionRepository] = None,
        step_execution_repository: Optional[StepExecutionRepository] = None,
    ):
        self.workflow_repository = workflow_repository
        self.credential_repository = credential_repository
        self.provider_repository = provider_repository
        self.provider_service_repository = provider_service_repository
        self.organization_repository = organization_repository
        self.queued_job_repository = queued_job_repository
        self.worker_repository = worker_repository
        self.prompt_service = prompt_service
        self.iteration_execution_repository = iteration_execution_repository
        self.step_execution_repository = step_execution_repository

        self.queue_router = QueueRouter()
        self.status_publisher = status_publisher
        self._variable_resolver = VariableResolver()
        self._endpoint_resolver = StepEndpointResolver(
            credential_repository=credential_repository,
            provider_repository=provider_repository,
            provider_service_repository=provider_service_repository,
            organization_repository=organization_repository,
        )
        self._inline_executor = InlineServiceExecutor(
            credential_repository=credential_repository,
            status_publisher=self.status_publisher,
        )
        self._iteration_enqueuer = IterationJobEnqueuer(
            variable_resolver=self._variable_resolver,
            endpoint_resolver=self._endpoint_resolver,
            queued_job_repository=queued_job_repository,
            worker_repository=worker_repository,
            status_publisher=self.status_publisher,
            queue_router=self.queue_router,
            iteration_execution_repository=iteration_execution_repository,
            step_execution_repository=step_execution_repository,
            warn_no_workers=WARN_NO_WORKERS,
        )

    async def enqueue_step(
        self,
        instance_id: uuid.UUID,
        step_id: str,
        organization_id: uuid.UUID,
        workflow_snapshot: Dict[str, Any],
        instance_parameters: Optional[Dict[str, Any]] = None,
        previous_step_results: Optional[Dict[str, Any]] = None,
        iteration_metadata: Optional[Dict[str, Any]] = None,
        pre_resolved_parameters: Optional[Dict[str, Any]] = None,
        parameter_overrides: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """Enqueue a single step. pre_resolved_parameters bypasses the resolution pipeline."""
        import copy

        steps = workflow_snapshot.get("steps", {})
        original_step_config = steps.get(step_id)

        if not original_step_config:
            raise ValueError(f"Step {step_id} not found in workflow snapshot")

        # Deep copy to avoid mutating the shared snapshot.
        step_config = copy.deepcopy(original_step_config)

        # Extract early for routing decisions.
        _job = step_config.get("job") or {}
        service_id = step_config.get("service_id") or _job.get("service_id") or ""

        if pre_resolved_parameters is not None:
            resolved_step_config = step_config
            if "job" not in resolved_step_config:
                resolved_step_config["job"] = {}
            resolved_step_config["job"]["parameters"] = pre_resolved_parameters
            _prompt_variables: Dict[str, str] = {}
            logger.debug(
                f"Step {step_id}: passthrough mode - using pre-resolved parameters, "
                f"skipping resolution pipeline"
            )
        else:
            iteration_config = step_config.get("iteration_config") or {}

            logger.debug(
                f"Step {step_id} iteration_config: enabled={iteration_config.get('enabled')}, "
                f"target={iteration_config.get('target_parameter')}, "
                f"source={iteration_config.get('source_step_id')}.{iteration_config.get('source_output_field')}"
            )

            # If iteration is not enabled, convert [*] to [0].
            if not iteration_config.get("enabled"):
                step_config = convert_star_to_zero(step_config)

            resolved_step_config = self._variable_resolver.resolve_variables_in_config(
                step_config,
                previous_step_results or {},
                instance_parameters or {},
            )

            input_mappings = get_input_mappings(step_config)

            # Pre-resolve prompt mappings before input_mappings application.
            _prompt_variables = {}
            if input_mappings and self.prompt_service:
                input_mappings, _prompt_variables = await pre_resolve_prompts(
                    input_mappings,
                    organization_id,
                    self.prompt_service,
                    previous_step_results=previous_step_results,
                    instance_parameters=instance_parameters,
                )

            logger.debug(f"Step {step_id} input_mappings: {input_mappings}")
            logger.debug(
                f"Step {step_id} previous_step_results keys: {list((previous_step_results or {}).keys())}"
            )
            if input_mappings:
                # When iteration is enabled, exclude the target parameter from resolution
                iteration_target = (
                    iteration_config.get("target_parameter")
                    if iteration_config.get("enabled")
                    else None
                )
                if iteration_target and iteration_target in input_mappings:
                    input_mappings_for_resolution = {
                        k: v for k, v in input_mappings.items() if k != iteration_target
                    }
                    logger.debug(
                        f"Step {step_id} excluding iteration target '{iteration_target}' from input_mappings resolution"
                    )

                    # Synthesize the [*] expression in job.parameters
                    source_step_id = iteration_config.get("source_step_id")
                    source_field = iteration_config.get("source_output_field")
                    if source_step_id and source_field:
                        step_job = step_config.get("job") or {}
                        step_params = step_job.get("parameters") or {}
                        current_value = step_params.get(iteration_target)

                        if (
                            not isinstance(current_value, str)
                            or "[*]" not in current_value
                        ):
                            expression = (
                                "{{ " + f"{source_step_id}.{source_field}[*]" + " }}"
                            )

                            if "job" not in step_config:
                                step_config["job"] = {}
                            if "parameters" not in step_config["job"]:
                                step_config["job"]["parameters"] = {}
                            step_config["job"]["parameters"][
                                iteration_target
                            ] = expression

                            if "job" not in resolved_step_config:
                                resolved_step_config["job"] = {}
                            if "parameters" not in resolved_step_config["job"]:
                                resolved_step_config["job"]["parameters"] = {}
                            resolved_step_config["job"]["parameters"][
                                iteration_target
                            ] = expression

                            logger.debug(
                                f"Step {step_id} synthesized iteration expression for '{iteration_target}': {expression}"
                            )
                else:
                    input_mappings_for_resolution = input_mappings

                resolved_step_config = apply_input_mappings(
                    resolved_step_config,
                    input_mappings_for_resolution,
                    previous_step_results or {},
                    instance_parameters or {},
                )
                job_params = resolved_step_config.get("job", {}).get("parameters", {})
                logger.debug(f"Step {step_id} resolved job.parameters: {job_params}")

            # Check for multi-job iteration (scalar target parameter)
            if iteration_config.get("enabled"):
                target_param = iteration_config.get("target_parameter")
                if target_param:
                    job_params = resolved_step_config.get("job", {}).get(
                        "parameters", {}
                    )
                    target_value = job_params.get(target_param)

                    if not isinstance(target_value, list):
                        source_step = iteration_config.get("source_step_id")
                        source_field = iteration_config.get("source_output_field")
                        if source_step and source_field:
                            source_array = (
                                (previous_step_results or {})
                                .get(source_step, {})
                                .get(source_field, [])
                            )
                            if isinstance(source_array, list) and len(source_array) > 0:
                                logger.debug(
                                    f"Multi-job iteration: {len(source_array)} jobs for scalar param '{target_param}'"
                                )
                                return await self._iteration_enqueuer.enqueue_iteration_jobs(
                                    instance_id=instance_id,
                                    step_id=step_id,
                                    organization_id=organization_id,
                                    workflow_snapshot=workflow_snapshot,
                                    step_config=step_config,
                                    resolved_step_config=resolved_step_config,
                                    iteration_config=iteration_config,
                                    source_array=source_array,
                                    instance_parameters=instance_parameters,
                                    previous_step_results=previous_step_results,
                                )
                            elif (
                                isinstance(source_array, list)
                                and len(source_array) == 0
                            ):
                                # Empty iteration source - raise so the action
                                # executor can fail the step + instance with
                                # the descriptive message. Returning None
                                # silently would leave the step PENDING until
                                # the 15-min stale-step sweep - see I-13.
                                logger.warning(
                                    f"Step {step_id}: source array "
                                    f"'{source_step}.{source_field}' is empty."
                                )
                                raise EmptyIterationSourceError(
                                    step_id=step_id,
                                    source_step=source_step,
                                    source_field=source_field,
                                )

            # Array expansion: single-call model
            if iteration_config.get("enabled"):
                target_param = iteration_config.get("target_parameter")
                if target_param:
                    step_input_mappings = get_input_mappings(step_config)
                    resolved_step_config = expand_array_parameter(
                        resolved_step_config,
                        target_param,
                        iteration_config,
                        previous_step_results or {},
                        step_input_mappings,
                    )

            # Apply image style presets for ComfyUI services
            job_config_for_styles = resolved_step_config.get("job") or {}
            service_id = (
                job_config_for_styles.get("service_id")
                or resolved_step_config.get("service_id")
                or ""
            )
            if supports_image_presets(service_id):
                job_params = job_config_for_styles.get("parameters") or {}
                if job_params.get("styles"):
                    styled_params = apply_image_presets(job_params)
                    resolved_step_config["job"]["parameters"] = styled_params

        # Resolve credential and endpoint
        credential_id = await self._endpoint_resolver.resolve_step_credential(
            resolved_step_config, organization_id
        )
        endpoint = await self._endpoint_resolver.resolve_step_endpoint(
            resolved_step_config
        )
        org_settings = await self._endpoint_resolver.get_org_settings(organization_id)

        # Execute inline if service declares orchestrator_hints.inline: true
        hints = (endpoint.service_metadata or {}).get("orchestrator_hints") or {}
        if hints.get("inline") and self._inline_executor.can_handle(service_id):
            return await self._inline_executor.execute(
                instance_id=instance_id,
                step_id=step_id,
                organization_id=organization_id,
                service_id=service_id,
                resolved_step_config=resolved_step_config,
            )

        # Merge schema defaults for missing parameters (safety net for old/programmatic workflows)
        if endpoint.parameter_schema:
            schema_props = endpoint.parameter_schema.get("properties", {})
            job_params = resolved_step_config.get("job", {}).get("parameters", {})
            defaults_applied = []
            for key, prop_schema in schema_props.items():
                if key not in job_params and "default" in prop_schema:
                    if "job" not in resolved_step_config:
                        resolved_step_config["job"] = {}
                    if "parameters" not in resolved_step_config["job"]:
                        resolved_step_config["job"]["parameters"] = {}
                    resolved_step_config["job"]["parameters"][key] = prop_schema[
                        "default"
                    ]
                    defaults_applied.append(key)
            if defaults_applied:
                logger.debug(
                    f"Step {step_id}: applied schema defaults for: {defaults_applied}"
                )

            # Project resolved parameters to the declared schema shape. This strips
            # cross-step form values (keyed as {step_id}.{field}) and anything else
            # the service doesn't declare, so the worker's request body and the UI's
            # Request Data panel both reflect the true contract.
            from contracts.schema_projection import project_by_schema

            job_params = resolved_step_config.get("job", {}).get("parameters")
            if isinstance(job_params, dict):
                projected = project_by_schema(job_params, endpoint.parameter_schema)
                dropped = [k for k in job_params if k not in projected]
                if dropped:
                    logger.debug(
                        f"Step {step_id}: dropped {len(dropped)} undeclared params: {dropped}"
                    )
                resolved_step_config["job"]["parameters"] = projected

        # Extract provider_id and service_id for worker routing
        job_config = resolved_step_config.get("job") or {}
        provider_id_for_worker = resolved_step_config.get(
            "provider_id"
        ) or job_config.get("provider_id")
        service_id_for_worker = resolved_step_config.get(
            "service_id"
        ) or job_config.get("service_id")

        # input_data = outputs from depends_on steps
        depends_on = step_config.get("depends_on") or []
        input_data = {
            dep_step_id: (previous_step_results or {}).get(dep_step_id, {})
            for dep_step_id in depends_on
            if dep_step_id in (previous_step_results or {})
        }

        # Build single-step job payload
        job_payload = {
            "job_id": str(uuid.uuid4()),
            "step_id": step_id,  # stored for API-side result routing only
            "step_config": resolved_step_config,
            "input_data": input_data,
            "credential_id": credential_id,
            "provider_id": provider_id_for_worker,
            "service_id": service_id_for_worker,
            "request_url": endpoint.url,
            "http_method": endpoint.http_method,
            "post_processing": endpoint.post_processing,
            "polling": endpoint.polling,
            "auth_config": endpoint.auth_config,
            "default_headers": endpoint.default_headers,
            "local_worker": endpoint.local_worker,
            "parameter_mapping": endpoint.parameter_mapping,
            "result_schema": endpoint.result_schema,
            "dispatch": endpoint.dispatch,
            "org_settings": org_settings,
            "instance_parameters": instance_parameters or {},
            "previous_step_results": previous_step_results or {},
            "workflow_name": workflow_snapshot.get("name", ""),
            "created_at": datetime.now(UTC).isoformat(),
        }

        # Apply scene expansion + file URL resolution so the http_request
        # body is byte-equivalent to what the worker would otherwise
        # compute.
        job_cfg = resolved_step_config.get("job") or {}
        job_params = job_cfg.get("parameters")
        if isinstance(job_params, dict):
            resolved_step_config.setdefault("job", {})["parameters"] = (
                resolve_step_parameters(
                    job_params,
                    org_id=str(organization_id),
                    instance_id=str(instance_id),
                )
            )

        # Attach the wire envelope.
        http_request = try_build_http_request(
            endpoint=endpoint,
            resolved_step_config=resolved_step_config,
            organization_id=organization_id,
            step_id=step_id,
        )
        if http_request is not None:
            job_payload["http_request"] = http_request

        # Propagate correlation_id for end-to-end request tracing
        ctx = get_request_context()
        if ctx and ctx.correlation_id:
            job_payload["correlation_id"] = ctx.correlation_id

        # Store prompt variables for API reference
        if _prompt_variables:
            job_payload["_prompt_variables"] = _prompt_variables

        # Add iteration metadata for regeneration
        if iteration_metadata:
            if "iteration_index" in iteration_metadata:
                job_payload["iteration_index"] = iteration_metadata["iteration_index"]
                job_payload["input_data"]["iteration_index"] = iteration_metadata[
                    "iteration_index"
                ]
            if "iteration_count" in iteration_metadata:
                job_payload["iteration_count"] = iteration_metadata["iteration_count"]
                job_payload["input_data"]["iteration_count"] = iteration_metadata[
                    "iteration_count"
                ]
            if "iteration_group_id" in iteration_metadata:
                job_payload["iteration_group_id"] = iteration_metadata[
                    "iteration_group_id"
                ]
                job_payload["input_data"]["iteration_group_id"] = iteration_metadata[
                    "iteration_group_id"
                ]

        # Add parameter_overrides to job payload (for worker merge, tree editor)
        if parameter_overrides:
            job_payload["parameter_overrides"] = parameter_overrides

        # Build request_body for debugging visibility (resolved parameters = actual API request)
        job_config = resolved_step_config.get("job") or {}
        request_body = job_config.get("parameters") or {}

        # Build input_data for debugging visibility (pre-resolution data = what went INTO building the request)
        # - parameters: original step params with {{ }} expressions before resolution
        # - prompt_variables: values that filled in the prompts
        # - depends_on: outputs from upstream dependency steps
        original_job = (original_step_config or {}).get("job") or {}
        original_params = original_job.get("parameters", {})
        step_input_data: Dict[str, Any] = {}
        if original_params:
            step_input_data["parameters"] = original_params
        if _prompt_variables:
            step_input_data["prompt_variables"] = _prompt_variables
        if input_data:
            step_input_data["depends_on"] = input_data

        # Determine queue name - no silent fallback, every service must have an explicit route
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
            # Publish FAILED status so the step shows a clear error in the UI
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

        # Publish QUEUED status
        # input_data = pre-resolution parameters (expressions, variables, depends_on outputs)
        # request_body = resolved parameters (actual API request body)
        queued_result: Dict[str, Any] = {
            "instance_id": str(instance_id),
            "step_id": step_id,
            "status": "QUEUED",
            "result": {},
            "error": None,
            "input_data": step_input_data,
            "request_body": request_body,
            "published_at": datetime.now(UTC).isoformat(),
        }

        if _prompt_variables:
            queued_result["_prompt_variables"] = _prompt_variables

        if iteration_metadata:
            if "iteration_index" in iteration_metadata:
                queued_result["iteration_index"] = iteration_metadata["iteration_index"]
            if "iteration_count" in iteration_metadata:
                queued_result["iteration_count"] = iteration_metadata["iteration_count"]
            if "iteration_group_id" in iteration_metadata:
                queued_result["iteration_group_id"] = iteration_metadata[
                    "iteration_group_id"
                ]

        await self.status_publisher.publish_status(queued_result)
        logger.debug(
            f"Published QUEUED status for step {step_id}: instance={instance_id}"
        )

        # Enqueue job to PostgreSQL
        job_id_str = str(job_payload["job_id"])
        await self._enqueue_to_postgres(
            job_id=uuid.UUID(job_id_str),
            instance_id=instance_id,
            organization_id=organization_id,
            step_id=step_id,
            queue_name=queue_name,
            payload=job_payload,
        )
        logger.debug(
            f"Enqueued step {step_id} to queue '{queue_name}': instance={instance_id}"
        )

        # Check worker availability (non-blocking warning)
        if WARN_NO_WORKERS and self.worker_repository:
            await self._check_worker_availability(queue_name)

        return job_payload["job_id"]

    async def enqueue_first_step(
        self,
        instance_id: uuid.UUID,
        organization_id: uuid.UUID,
        workflow_snapshot: Dict[str, Any],
        instance_parameters: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """Locate and enqueue the workflow entry point.

        Returns the job ID, None if no entry step found,
        "SKIP" if the step was skipped, or "STOP" if the workflow should complete.
        """
        first_step_id = find_entry_step(workflow_snapshot)

        if not first_step_id:
            logger.warning(f"No entry step found for instance {instance_id}")
            return None

        # Check execution_mode of the first step
        steps = workflow_snapshot.get("steps", {})
        first_step_config = steps.get(first_step_id, {})
        if isinstance(first_step_config, dict):
            exec_mode = first_step_config.get("execution_mode")
            if exec_mode == "stop":
                logger.info(
                    f"First step {first_step_id} has stop mode - workflow should complete immediately"
                )
                return "STOP"
            if exec_mode == "skip":
                logger.debug(f"First step {first_step_id} has skip mode - skipping")
                return "SKIP"

        logger.info(f"Step enqueued: step={first_step_id}")
        return await self.enqueue_step(
            instance_id=instance_id,
            step_id=first_step_id,
            organization_id=organization_id,
            workflow_snapshot=workflow_snapshot,
            instance_parameters=instance_parameters,
            previous_step_results={},
        )

    def find_entry_step(self, workflow_snapshot: Dict[str, Any]) -> Optional[str]:
        """Return the ID of the entry step, or None if none exists."""
        return find_entry_step(workflow_snapshot)

    def _get_ready_steps(
        self,
        workflow_snapshot: Dict[str, Any],
        completed_step_ids: set[str],
        running_step_ids: set[str],
    ) -> list[str]:
        """Return steps whose dependencies are all satisfied."""
        return get_ready_steps(workflow_snapshot, completed_step_ids, running_step_ids)

    async def enqueue_ready_steps_after_skip(
        self,
        instance_id: uuid.UUID,
        organization_id: uuid.UUID,
        workflow_snapshot: Dict[str, Any],
        skipped_step_ids: set[str],
        instance_parameters: Optional[Dict[str, Any]] = None,
    ) -> list[str]:
        """Find and enqueue all ready steps after one or more steps were skipped.

        Returns a list of job IDs, or ["STOP"] if a stop step was found.
        """
        steps = workflow_snapshot.get("steps", {})

        # Build completed set (skipped steps count as completed)
        completed_step_ids = set(skipped_step_ids)

        # Also treat all 'skip' mode steps as completed
        for step_id_key, step_config in steps.items():
            if isinstance(step_config, dict):
                exec_mode = step_config.get("execution_mode")
                if exec_mode == "skip":
                    completed_step_ids.add(step_id_key)

        # Find ready steps
        ready_steps = get_ready_steps(
            workflow_snapshot=workflow_snapshot,
            completed_step_ids=completed_step_ids,
            running_step_ids=set(),
        )

        if not ready_steps:
            logger.debug(f"No ready steps found after skipping {skipped_step_ids}")
            return []

        # Enqueue all ready steps
        enqueued_job_ids = []
        for ready_step_id in ready_steps:
            try:
                job_id = await self.enqueue_step(
                    instance_id=instance_id,
                    step_id=ready_step_id,
                    organization_id=organization_id,
                    workflow_snapshot=workflow_snapshot,
                    instance_parameters=instance_parameters,
                    previous_step_results={},
                )
                enqueued_job_ids.append(job_id)
                logger.debug(f"Enqueued step {ready_step_id} after skip")
            except Exception as e:
                logger.error(f"Failed to enqueue step {ready_step_id} after skip: {e}")
                raise

        return enqueued_job_ids

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
