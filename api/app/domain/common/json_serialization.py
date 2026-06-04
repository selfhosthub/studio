# api/app/domain/common/json_serialization.py

"""JSON serialization helpers for domain objects."""

import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional, TypeVar

from pydantic import ValidationError

logger = logging.getLogger(__name__)

T = TypeVar("T")
DictT = TypeVar("DictT", bound=Dict[str, Any])

from app.domain.common.value_objects import StepConfig, StepTriggerType, StepType

if TYPE_CHECKING:
    pass


def serialize_step_config(step_config: StepConfig) -> Dict[str, Any]:
    """Convert StepConfig to a JSON-serializable dict. step_type is deprecated; new code emits TASK."""
    job_dict = None
    if step_config.job:
        if hasattr(step_config.job, "model_dump"):
            job_dict = step_config.job.model_dump(mode="json")

    result = {
        "name": step_config.name,
        "description": step_config.description,
        "step_type": (
            step_config.step_type.name.upper() if step_config.step_type else "TASK"
        ),
        "job": job_dict,
        "depends_on": step_config.depends_on,
        "timeout_seconds": step_config.timeout_seconds,
        "retry_count": step_config.retry_count,
        "retry_delay_seconds": step_config.retry_delay_seconds,
        "is_required": step_config.is_required,
        "on_failure": step_config.on_failure,
        "condition": step_config.condition,
        "trigger_type": (
            step_config.trigger_type.value if step_config.trigger_type else "auto"
        ),
        "outputs": step_config.outputs,
        "ui_config": step_config.ui_config,
        "client_metadata": step_config.client_metadata,
    }

    # StepConfig sets extra="allow"; pass through any unmodelled fields (provider_id, etc.).
    step_dict = step_config.model_dump(mode="json")
    for key, value in step_dict.items():
        if key not in result:
            result[key] = value

    return result


def serialize_steps(steps: Dict[str, StepConfig]) -> Dict[str, Dict[str, Any]]:
    return {
        step_id: serialize_step_config(step_config)
        for step_id, step_config in steps.items()
    }


def deserialize_step_config(step_data: Dict[str, Any]) -> StepConfig:
    """Build StepConfig from serialized form. step_type is deprecated; unknown values default to TASK."""
    from app.domain.common.value_objects import JobConfig

    if not isinstance(step_data, dict):
        return StepConfig(step_type=StepType.TASK, name="unknown")

    step_type_str = step_data.get("step_type")
    step_type = StepType.TASK

    if step_type_str:
        try:
            step_type = StepType(step_type_str.lower())
        except ValueError:
            step_type = StepType.TASK

    job_data = step_data.get("job")
    job: Optional[JobConfig] = None
    if isinstance(job_data, dict):
        try:
            job = JobConfig.model_validate(job_data)
        except ValidationError as e:
            logger.warning("Failed to parse JobConfig from step data: %s", e)
    elif isinstance(job_data, JobConfig):
        job = job_data

    step_data_dict: Dict[str, Any] = step_data

    trigger_type_str = step_data_dict.get("trigger_type")
    trigger_type = StepTriggerType.AUTO
    if trigger_type_str:
        try:
            trigger_type = StepTriggerType(trigger_type_str.lower())
        except ValueError:
            trigger_type = StepTriggerType.AUTO

    name: str = str(step_data_dict.get("name", ""))
    description: Optional[str] = step_data_dict.get("description")
    depends_on_raw = step_data_dict.get("depends_on", [])
    depends_on: List[str] = (
        list(depends_on_raw) if isinstance(depends_on_raw, list) else []
    )
    timeout_seconds_step: Optional[int] = step_data_dict.get("timeout_seconds")
    retry_count_step_raw = step_data_dict.get("retry_count", 0)
    retry_count_step: int = (
        int(retry_count_step_raw) if retry_count_step_raw is not None else 0
    )
    retry_delay_step_raw = step_data_dict.get("retry_delay_seconds", 60)
    retry_delay_step: int = (
        int(retry_delay_step_raw) if retry_delay_step_raw is not None else 60
    )
    is_required_raw = step_data_dict.get("is_required", True)
    is_required: bool = bool(is_required_raw) if is_required_raw is not None else True
    on_failure_raw = step_data_dict.get("on_failure", "fail_workflow")
    on_failure: str = (
        str(on_failure_raw) if on_failure_raw is not None else "fail_workflow"
    )
    condition: Optional[str] = step_data_dict.get("condition")
    outputs: Optional[Dict[str, Dict[str, Any]]] = step_data_dict.get("outputs")
    ui_config: Optional[Dict[str, Any]] = step_data_dict.get("ui_config")
    client_metadata_raw = step_data_dict.get("client_metadata", {})
    client_metadata: Dict[str, Any] = (
        dict(client_metadata_raw) if isinstance(client_metadata_raw, dict) else {}
    )

    standard_field_names = {
        "name",
        "description",
        "step_type",
        "job",
        "depends_on",
        "timeout_seconds",
        "retry_count",
        "retry_delay_seconds",
        "is_required",
        "on_failure",
        "condition",
        "trigger_type",
        "outputs",
        "ui_config",
        "client_metadata",
    }

    # StepConfig has extra="allow" - pass through unmodelled keys (provider_id, service_id, etc.).
    extra_fields: Dict[str, Any] = {}
    for key, value in step_data_dict.items():
        if key not in standard_field_names:
            extra_fields[key] = value

    return StepConfig(
        name=name,
        description=description,
        step_type=step_type or StepType.TASK,
        job=job,
        depends_on=depends_on,
        timeout_seconds=timeout_seconds_step,
        retry_count=retry_count_step,
        retry_delay_seconds=retry_delay_step,
        is_required=is_required,
        on_failure=on_failure,
        condition=condition,
        trigger_type=trigger_type,
        outputs=outputs,
        ui_config=ui_config,
        client_metadata=client_metadata,
        **extra_fields,
    )


def deserialize_steps(step_data: Dict[str, Dict[str, Any]]) -> Dict[str, StepConfig]:
    return {
        step_id: deserialize_step_config(step_config)
        for step_id, step_config in step_data.items()
    }
