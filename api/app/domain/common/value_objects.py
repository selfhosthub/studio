# api/app/domain/common/value_objects.py

"""Common value objects shared across domains."""

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, NewType, Optional, Union

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.config.settings import settings
from app.domain.common.exceptions import ValidationError
from app.domain.instance_step.models import StepExecutionStatus

UserId = NewType("UserId", uuid.UUID)


class Role(str, Enum):
    USER = "user"
    ADMIN = "admin"
    SUPER_ADMIN = "super_admin"


class OrganizationStatus(str, Enum):
    """Organization access state.

    - pending_approval: build-only; capped at 1 user, 0 executions, 50MB.
    - active: full access per plan/default limits.
    - suspended: read-only (billing, policy violations).
    """

    PENDING_APPROVAL = "pending_approval"
    ACTIVE = "active"
    SUSPENDED = "suspended"


class ActivationMethod(str, Enum):
    MANUAL = "manual"
    SUBSCRIPTION = "subscription"
    AUTO = "auto"


class Email(BaseModel):
    email: EmailStr

    model_config = ConfigDict(frozen=True)


class ResourceSpecification(BaseModel):
    """Compute, memory, and storage requirements for a resource."""

    cpu: Optional[str] = None
    memory: Optional[str] = None
    gpu: Optional[str] = None
    storage: Optional[str] = None
    network: Optional[str] = None
    timeout_seconds: Optional[int] = None
    max_retry_count: Optional[int] = settings.DEFAULT_MAX_RETRIES
    custom: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(frozen=True)

    @field_validator("timeout_seconds")
    @classmethod
    def timeout_must_be_positive(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and v <= 0:
            raise ValidationError(
                message="timeout_seconds must be positive",
                code="INVALID_TIMEOUT",
            )
        return v

    @field_validator("max_retry_count")
    @classmethod
    def retry_count_must_be_non_negative(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and v < 0:
            raise ValidationError(
                message="max_retry_count must be non-negative",
                code="INVALID_RETRY_COUNT",
            )
        return v


class Money(BaseModel):
    amount: float
    currency: str = "USD"

    model_config = ConfigDict(frozen=True)

    def __add__(self, other: "Money") -> "Money":
        if self.currency != other.currency:
            raise ValidationError(
                message=f"Cannot add money with different currencies: {self.currency} and {other.currency}",
                code="CURRENCY_MISMATCH",
            )
        return Money(amount=self.amount + other.amount, currency=self.currency)

    def __sub__(self, other: "Money") -> "Money":
        if self.currency != other.currency:
            raise ValidationError(
                message=f"Cannot subtract money with different currencies: {self.currency} and {other.currency}",
                code="CURRENCY_MISMATCH",
            )
        return Money(amount=self.amount - other.amount, currency=self.currency)

    def __mul__(self, multiplier: float) -> "Money":
        return Money(amount=self.amount * multiplier, currency=self.currency)


class DateRange(BaseModel):
    start_date: datetime
    end_date: Optional[datetime] = None

    model_config = ConfigDict(frozen=True)

    @field_validator("end_date")
    @classmethod
    def end_date_after_start_date(
        cls, v: Optional[datetime], info: Any
    ) -> Optional[datetime]:
        if v is not None and "start_date" in info.data and v < info.data["start_date"]:
            raise ValidationError(
                message="end_date must be after start_date",
                code="INVALID_DATE_RANGE",
            )
        return v

    def contains(self, date: datetime) -> bool:
        if date < self.start_date:
            return False
        if self.end_date is not None and date > self.end_date:
            return False
        return True

    def overlaps(self, other: "DateRange") -> bool:
        if other.end_date is not None and other.end_date < self.start_date:
            return False
        if self.end_date is not None and other.start_date > self.end_date:
            return False
        return True


class PromptSource(str, Enum):
    CUSTOM = "custom"
    SUPER_ADMIN = "super_admin"
    MARKETPLACE = "marketplace"
    UNINSTALLED = "uninstalled"


class PromptScope(str, Enum):
    PERSONAL = "personal"
    ORGANIZATION = "organization"


class PromptPublishStatus(str, Enum):
    PENDING = "pending"
    REJECTED = "rejected"


class StepType(str, Enum):
    """Deprecated. Orchestration is driven by orchestrator_hints in the service JSON definition.

    Kept only for parsing existing workflows; new code should always use TASK.
    """

    TASK = "task"
    APPROVAL = "approval"
    DECISION = "decision"
    NOTIFICATION = "notification"
    WEBHOOK = "webhook"
    API_CALL = "api_call"
    SCRIPT = "script"
    CONTAINER = "container"
    FUNCTION = "function"
    CONDITION = "condition"
    TRIGGER = "trigger"


class StepFailureAction(str, Enum):
    FAIL_WORKFLOW = "fail_workflow"
    CONTINUE = "continue"
    RETRY = "retry"


class StepTriggerType(str, Enum):
    AUTO = "auto"
    MANUAL = "manual"


class ResourceRequirements(BaseModel):
    cpu_cores: Optional[float] = None
    memory_gb: Optional[float] = None
    gpu_count: Optional[int] = None
    gpu_type: Optional[str] = None
    disk_gb: Optional[int] = None

    model_config = ConfigDict(extra="allow")


class JobConfig(BaseModel):
    """Configuration for a job execution within a step."""

    # provider_id accepts UUID or slug string. Slugs are stored when a marketplace workflow
    # is installed before its providers are registered; resolved to UUIDs at execution.
    provider_id: Optional[Union[uuid.UUID, str]] = None
    credential_id: Optional[uuid.UUID] = None
    credential_provider_id: Optional[Union[uuid.UUID, str]] = None
    auth_config: Optional[Dict[str, Any]] = None
    service_id: Optional[str] = None

    service_type: Optional[str] = None
    capability_type: Optional[str] = None

    # Legacy format
    provider_type: Optional[str] = None
    command: Optional[str] = None

    parameters: Dict[str, Any] = Field(default_factory=dict)
    resource_requirements: Optional[ResourceRequirements] = None
    timeout_seconds: Optional[int] = None
    retry_count: Optional[int] = settings.STEP_DEFAULT_RETRY_COUNT
    retry_delay_seconds: Optional[int] = settings.DEFAULT_RETRY_DELAY_SECONDS

    environment_variables: Optional[Dict[str, str]] = None
    secrets: Optional[List[str]] = None

    input_mapping: Optional[Dict[str, str]] = None
    output_mapping: Optional[Dict[str, str]] = None

    provider_version: Optional[str] = None
    service_version: Optional[str] = None

    model_config = ConfigDict(extra="allow")

    @field_validator("credential_id", mode="before")
    @classmethod
    def _empty_str_to_none(cls, v: Any) -> Any:
        # Empty string would otherwise raise during UUID parse.
        if v == "":
            return None
        return v

    @field_validator("provider_id", "credential_provider_id", mode="before")
    @classmethod
    def _coerce_provider_ref(cls, v: Any) -> Any:
        """Accept UUID, slug string, or None. Non-UUID strings are kept as slugs for later resolution at execution."""
        if v == "" or v is None:
            return None
        if isinstance(v, uuid.UUID):
            return v
        if isinstance(v, str):
            try:
                return uuid.UUID(v)
            except ValueError:
                return v
        return v  # pragma: no cover

    def is_legacy_format(self) -> bool:
        return bool(self.command) and not self.service_id and not self.service_type

    def is_generic_format(self) -> bool:
        return (
            bool(self.service_type or self.capability_type)
            and not self.service_id
            and not self.provider_id
        )

    def is_workflow_format(self) -> bool:
        return bool(self.provider_id or self.service_id)


class InputMapping(BaseModel):
    """How a step parameter gets its value: static, mapped from a prior step, or runtime form input.

    For 'form' mappings, field config is derived from the service's parameter schema
    (label from title, type from JSON schema type, options from enum).
    """

    mapping_type: str = "static"  # "static" | "mapped" | "form"
    static_value: Optional[Any] = None
    step_id: Optional[str] = None
    output_field: Optional[str] = None

    # Path expression for nested access within the output field:
    #   ".url"     - property (iterates if source is array and target expects single)
    #   "[0].url"  - first item's property (no iteration)
    #   "[-1].url" - last item's property (no iteration)
    #   "[*].url"  - pluck all values into array (no iteration)
    #   "[*]"      - transform each element via element_mapping (no iteration)
    path: Optional[str] = None

    # Used when path is "[*]" to reshape each object in the source array.
    # Example: {"image_url": ".url", "height": ".height", "duration": "value:5"}
    element_mapping: Optional[Dict[str, str]] = None

    model_config = ConfigDict(extra="allow")

    def is_mapped(self) -> bool:
        return self.mapping_type == "mapped" and self.step_id is not None

    def is_iterating(self) -> bool:
        """True only when a schema path (e.g. .url) is applied over an array source. Explicit index or pluck shapes do not iterate."""
        if not self.is_mapped() or not self.path:
            return False
        if self.path.startswith("["):
            return False
        return True

    def is_array_transform(self) -> bool:
        """True for path "[*]" with element_mapping: reshape each element without iteration."""
        return self.path == "[*]" and self.element_mapping is not None

    def is_form(self) -> bool:
        return self.mapping_type == "form"


class IterationConfig(BaseModel):
    """Run a step once per element of an array source.

    sequential: one at a time, allows accumulators carrying state between iterations.
    parallel: all at once, faster, no inter-iteration dependencies.
    """

    enabled: bool = False
    source_step_id: Optional[str] = None
    source_output_field: Optional[str] = None
    target_parameter: Optional[str] = None
    execution_mode: str = "sequential"
    estimated_count: Optional[int] = None
    # [{field_name, expression}] - values carried across sequential iterations.
    accumulators: Optional[List[Dict[str, str]]] = None

    model_config = ConfigDict(extra="allow")


class StepConfig(BaseModel):
    """Configuration for a workflow step. step_type is deprecated; orchestration uses orchestrator_hints in the service definition."""

    name: str
    description: Optional[str] = None
    step_type: Optional[StepType] = StepType.TASK
    job: Optional[JobConfig] = None
    depends_on: List[str] = Field(default_factory=list)
    timeout_seconds: Optional[int] = None
    retry_count: int = 0
    retry_delay_seconds: int = 60
    is_required: bool = True
    on_failure: str = "fail_workflow"
    condition: Optional[str] = None
    trigger_type: StepTriggerType = StepTriggerType.AUTO

    # {field_name: {path, type, description}}
    outputs: Optional[Dict[str, Dict[str, Any]]] = None

    # Computed at save time, validated at runtime.
    iteration_config: Optional[IterationConfig] = None

    # Visual editor: position {x, y}, color, shape, width, height, hidden, etc.
    ui_config: Optional[Dict[str, Any]] = None

    # Maps parameter names to their data sources (form fields, prior outputs, etc.).
    input_mappings: Optional[Dict[str, Any]] = None

    client_metadata: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="allow")


class StepReference(BaseModel):
    step_id: uuid.UUID
    step_name: Optional[str] = None
    version: Optional[int] = None

    model_config = ConfigDict(frozen=True)


class ExecutionContext(BaseModel):
    user_id: Optional[uuid.UUID] = None
    organization_id: uuid.UUID
    workflow_id: Optional[uuid.UUID] = None
    instance_id: Optional[uuid.UUID] = None
    correlation_id: Optional[str] = None
    client_metadata: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(frozen=True)


class ExecutionResult(BaseModel):
    status: StepExecutionStatus
    output_data: Dict[str, Any] = Field(default_factory=dict)
    error_message: Optional[str] = None
    error_details: Optional[Dict[str, Any]] = None
    duration_seconds: Optional[float] = None
    client_metadata: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(frozen=True)
