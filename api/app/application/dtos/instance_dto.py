# api/app/application/dtos/instance_dto.py

"""
Data transfer objects for workflow instance operations.
"""

import uuid
from datetime import datetime
from typing import Any, ClassVar, Dict, List, Optional, Set

from pydantic import BaseModel, Field

from app.domain.instance.iteration_execution import (
    IterationExecution,
    IterationExecutionStatus,
)
from app.domain.instance.models import Instance
from app.domain.instance_step.models import StepExecutionStatus
from app.domain.instance_step.step_execution import StepExecution
from app.infrastructure.security.redaction import redact_sensitive_data

# NOTE: `derive_instance_step_status_dict` and `order_steps_topologically` are
# imported inside `InstanceResponse.from_domain` to avoid a circular import.
# `app/application/services/__init__.py` imports `instance_service`, which
# imports this DTO module - pulling the helpers in at module load time would
# bounce through that cycle. Function-local imports keep the cycle broken.


class InstanceBase(BaseModel):
    """Base DTO for workflow instance data."""

    workflow_id: uuid.UUID
    input_data: Optional[Dict[str, Any]] = None
    client_metadata: Optional[Dict[str, Any]] = None


class InstanceCreate(InstanceBase):
    """DTO for creating a new workflow instance."""

    user_id: Optional[uuid.UUID] = None
    created_by: uuid.UUID


class InstanceUpdate(BaseModel):
    """DTO for updating a workflow instance."""

    client_metadata: Optional[Dict[str, Any]] = None
    output_data: Optional[Dict[str, Any]] = None
    updated_by: uuid.UUID


class InstanceResponse(BaseModel):
    """DTO for workflow instance response data."""

    id: uuid.UUID
    workflow_id: uuid.UUID
    organization_id: uuid.UUID
    user_id: Optional[uuid.UUID] = None
    name: str
    workflow_name: str
    status: str
    version: int
    input_data: Dict[str, Any]
    output_data: Dict[str, Any]
    client_metadata: Dict[str, Any]
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    current_step_ids: List[str]
    step_status: Dict[str, str]
    workflow_snapshot: Optional[Dict[str, Any]] = None
    # Error fields for failed instances
    error_message: Optional[str] = None
    failed_step_ids: List[str] = []
    error_data: Optional[Dict[str, Any]] = None
    # Step executions (populated separately via service)
    steps: Optional[List["StepExecutionResponse"]] = None

    @classmethod
    def from_domain(cls, instance: Instance) -> "InstanceResponse":
        """Create a response DTO from a domain `Instance` entity, generating a display name from workflow name and version."""
        # Get workflow_name from transient field (populated by repository JOIN)
        workflow_name = instance.workflow_name or "Unknown Workflow"

        # Generate display name: "{workflow_name} - Run #{version}"
        instance_name = f"{workflow_name} - Run #{instance.version}"

        # Extract error_message from error_data if available
        error_message = None
        if instance.error_data:
            error_message = instance.error_data.get("error")

        # Local import: avoids circular dependency.
        from app.application.services.instance.status_derivation import (
            derive_instance_step_status_dict,
        )
        from app.application.services.instance.step_ordering import (
            order_steps_topologically,
        )

        step_status = derive_instance_step_status_dict(instance)

        # Populate steps in topological order when workflow_snapshot is present.
        steps: Optional[List[StepExecutionResponse]] = None
        if instance.workflow_snapshot and instance.step_entities:
            ordered_ids = order_steps_topologically(instance.workflow_snapshot)
            snapshot_steps = (instance.workflow_snapshot or {}).get("steps") or {}
            built: List[StepExecutionResponse] = []
            for step_id in ordered_ids:
                step_entity = instance.step_entities.get(step_id)
                if step_entity is None:
                    continue
                built.append(
                    StepExecutionResponse.from_domain(
                        step_entity,
                        workflow_step_config=snapshot_steps.get(step_id),
                    )
                )
            steps = built

        return cls(
            id=instance.id,
            workflow_id=instance.workflow_id,
            organization_id=instance.organization_id,
            user_id=instance.user_id,
            name=instance_name,
            workflow_name=workflow_name,
            status=instance.status,
            version=instance.version,
            input_data=instance.input_data,
            output_data=instance.output_data,
            client_metadata=instance.client_metadata,
            created_at=instance.created_at,
            updated_at=instance.updated_at,
            started_at=instance.started_at,
            completed_at=instance.completed_at,
            current_step_ids=instance.current_step_ids,
            step_status=step_status,
            workflow_snapshot=instance.workflow_snapshot,
            error_message=error_message,
            failed_step_ids=instance.failed_step_ids,
            error_data=instance.error_data,
            steps=steps,
        )


class PaginatedInstanceResponse(BaseModel):
    """Paginated response for instance listings."""

    items: List[InstanceResponse]
    total: int
    skip: int
    limit: int


class StepExecutionBase(BaseModel):
    """Base DTO for step execution data."""

    instance_id: uuid.UUID
    step_key: str
    execution_data: Optional[Dict[str, Any]] = None


class StepExecutionCreate(StepExecutionBase):
    """DTO for creating a new step execution."""

    created_by: uuid.UUID


class StepExecutionUpdate(BaseModel):
    """DTO for updating a step execution."""

    status: str
    result: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    updated_by: uuid.UUID


class IterationExecutionResponse(BaseModel):
    """DTO for a single iteration row under a fan-out step execution."""

    id: uuid.UUID
    step_execution_id: uuid.UUID
    iteration_index: int
    iteration_group_id: Optional[uuid.UUID] = None
    status: IterationExecutionStatus
    parameters: Dict[str, Any] = Field(default_factory=dict)
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @classmethod
    def from_domain(cls, iteration: IterationExecution) -> "IterationExecutionResponse":
        return cls(
            id=iteration.id,
            step_execution_id=iteration.step_id,
            iteration_index=iteration.iteration_index,
            iteration_group_id=iteration.iteration_group_id,
            status=iteration.status,
            parameters=iteration.parameters,
            result=iteration.result,
            error=iteration.error,
            started_at=iteration.started_at,
            completed_at=iteration.completed_at,
            created_at=iteration.created_at,
            updated_at=iteration.updated_at,
        )


class StepExecutionResponse(BaseModel):
    """Unified DTO for a step execution, combining lifecycle, display, and worker-attempt fields with a child iterations collection."""

    # Identity
    id: uuid.UUID
    instance_id: uuid.UUID
    step_id: str  # workflow-definition step key (e.g. "generate_images")
    step_name: str = ""

    # Lifecycle status
    status: StepExecutionStatus
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    # Output / error
    output_data: Dict[str, Any] = Field(default_factory=dict)
    error_message: Optional[str] = None

    # Worker-attempt fields
    result: Optional[Dict[str, Any]] = None
    retry_count: int = 0
    execution_data: Dict[str, Any] = Field(default_factory=dict)
    input_data: Dict[str, Any] = Field(default_factory=dict)
    request_body: Optional[Dict[str, Any]] = None
    iteration_requests: Optional[List[Dict[str, Any]]] = None

    # Computed display fields
    status_display: str = ""
    can_retry: bool = False
    can_rerun: bool = False
    can_approve: bool = False
    can_trigger: bool = False
    is_terminal: bool = False

    # Step-config fields sourced from workflow_snapshot.steps[step_id] when
    # workflow_step_config is passed to from_domain; otherwise defaults.
    name: str = ""
    depends_on: List[str] = Field(default_factory=list)
    service_id: Optional[str] = None
    provider_id: Optional[str] = None
    service_type: Optional[str] = None
    trigger_type: Optional[str] = None
    execution_mode: Optional[str] = None
    parameters: Dict[str, Any] = Field(default_factory=dict)
    # input_mappings values are sometimes mapping-config dicts
    # (e.g. {"formField": "subject", "mappingType": "form"}), not flat
    # strings - Dict[str, Any] matches runtime reality.
    input_mappings: Dict[str, Any] = Field(default_factory=dict)

    iterations: List[IterationExecutionResponse] = Field(default_factory=list)

    # Timestamps
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    # Human-readable display names for statuses (not serialized)
    STATUS_DISPLAY: ClassVar[Dict[StepExecutionStatus, str]] = {
        StepExecutionStatus.PENDING: "Pending",
        StepExecutionStatus.QUEUED: "Queued",
        StepExecutionStatus.RUNNING: "Running",
        StepExecutionStatus.COMPLETED: "Completed",
        StepExecutionStatus.FAILED: "Failed",
        StepExecutionStatus.SKIPPED: "Skipped",
        StepExecutionStatus.STOPPED: "Stopped",
        StepExecutionStatus.WAITING_APPROVAL: "Waiting for Approval",
        StepExecutionStatus.WAITING_FOR_MANUAL_TRIGGER: "Waiting for Trigger",
        StepExecutionStatus.CANCELLED: "Cancelled",
        StepExecutionStatus.TIMEOUT: "Timed Out",
        StepExecutionStatus.BLOCKED: "Blocked",
        # PAUSED intentionally absent - display label ships with the pause feature.
    }

    # Terminal statuses where no further transitions expected (not serialized)
    TERMINAL_STATUSES: ClassVar[Set[StepExecutionStatus]] = {
        StepExecutionStatus.COMPLETED,
        StepExecutionStatus.FAILED,
        StepExecutionStatus.SKIPPED,
        StepExecutionStatus.CANCELLED,
        StepExecutionStatus.TIMEOUT,
    }

    @classmethod
    def from_domain(
        cls,
        step: StepExecution,
        workflow_step_config: Optional[Dict[str, Any]] = None,
    ) -> "StepExecutionResponse":
        """Create a response DTO from a `StepExecution` domain entity.

        Computes display fields and, when `workflow_step_config` is provided,
        populates step-config fields (name, depends_on, service_id, etc.) from it.
        """
        status = step.status
        config = workflow_step_config or {}
        job_config = (config.get("job") or {}) if isinstance(config, dict) else {}

        step_job_params = (
            (job_config.get("parameters") or {}) if isinstance(job_config, dict) else {}
        )
        step_params_override = config.get("parameters") or {}
        merged_parameters: Dict[str, Any] = {}
        if isinstance(step_job_params, dict):
            merged_parameters.update(step_job_params)
        if isinstance(step_params_override, dict):
            merged_parameters.update(step_params_override)

        name_value = (
            config.get("name")
            or (
                job_config.get("display_name") if isinstance(job_config, dict) else None
            )
            or step.step_key
        )

        redacted_iteration_requests = None
        if step.iteration_requests:
            redacted_iteration_requests = [
                redact_sensitive_data(req, include_pii=False) or {}
                for req in step.iteration_requests
            ]

        return cls(
            id=step.id,
            instance_id=step.instance_id,
            step_id=step.step_key,
            step_name=step.step_name,
            status=status,
            started_at=step.started_at,
            completed_at=step.completed_at,
            output_data=step.output_data,
            error_message=step.error_message,
            # Worker-attempt fields
            # Use get_outputs() to prefer extracted_outputs over raw result.
            result=step.get_outputs(),
            retry_count=step.retry_count,
            execution_data=step.execution_data,
            input_data=(
                redact_sensitive_data(step.input_data, include_pii=False) or {}
            ),
            request_body=redact_sensitive_data(step.request_body, include_pii=False),
            iteration_requests=redacted_iteration_requests,
            # Computed display fields
            status_display=cls.STATUS_DISPLAY.get(
                status, status.value.replace("_", " ").title()
            ),
            can_retry=status == StepExecutionStatus.FAILED,
            can_rerun=status == StepExecutionStatus.COMPLETED,
            can_approve=status == StepExecutionStatus.WAITING_APPROVAL,
            can_trigger=status == StepExecutionStatus.WAITING_FOR_MANUAL_TRIGGER,
            is_terminal=status in cls.TERMINAL_STATUSES,
            name=str(name_value),
            depends_on=list(config.get("depends_on") or []),
            service_id=(
                job_config.get("service_id") if isinstance(job_config, dict) else None
            ),
            provider_id=(
                job_config.get("provider_id") if isinstance(job_config, dict) else None
            ),
            service_type=(
                config.get("service_type")
                or (
                    job_config.get("service_type")
                    if isinstance(job_config, dict)
                    else None
                )
            ),
            trigger_type=config.get("trigger_type"),
            execution_mode=config.get("execution_mode"),
            parameters=merged_parameters,
            input_mappings=(
                config.get("input_mappings") or {} if isinstance(config, dict) else {}
            ),
            iterations=[
                IterationExecutionResponse.from_domain(it) for it in step.iterations
            ],
            created_at=step.created_at,
            updated_at=step.updated_at,
        )
