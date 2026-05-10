# api/app/domain/common/converters.py

"""Convert dictionaries to domain value objects."""

from enum import Enum
from typing import Any, Dict, List, Type

from app.domain.common.value_objects import (
    JobConfig,
    ResourceRequirements,
    StepConfig,
    StepReference,
)


def dict_to_resource_requirements(data: Dict[str, Any]) -> ResourceRequirements:
    return ResourceRequirements(
        cpu_cores=data.get("cpu_cores"),
        memory_gb=data.get("memory_gb"),
        gpu_count=data.get("gpu_count"),
        gpu_type=data.get("gpu_type"),
        disk_gb=data.get("disk_gb"),
        **{
            k: v
            for k, v in data.items()
            if k not in ["cpu_cores", "memory_gb", "gpu_count", "gpu_type", "disk_gb"]
        },
    )


def dict_to_job_config(data: Dict[str, Any]) -> JobConfig:
    import uuid

    provider_id = data.get("provider_id")
    if provider_id and isinstance(provider_id, str):
        provider_id = uuid.UUID(provider_id)

    credential_id = data.get("credential_id")
    if credential_id and isinstance(credential_id, str):
        credential_id = uuid.UUID(credential_id)

    resource_requirements = None
    if "resource_requirements" in data:
        if isinstance(data["resource_requirements"], dict):
            resource_requirements = dict_to_resource_requirements(
                data["resource_requirements"]
            )
        else:
            resource_requirements = data["resource_requirements"]

    return JobConfig(
        provider_id=provider_id,
        credential_id=credential_id,
        service_id=data.get("service_id"),
        service_type=data.get("service_type"),
        capability_type=data.get("capability_type"),
        command=data.get("command"),
        parameters=data.get("parameters", {}),
        resource_requirements=resource_requirements,
        timeout_seconds=data.get("timeout_seconds"),
        retry_count=data.get("retry_count"),
        retry_delay_seconds=data.get("retry_delay_seconds"),
        environment_variables=data.get("environment_variables"),
        secrets=data.get("secrets"),
        input_mapping=data.get("input_mapping"),
        output_mapping=data.get("output_mapping"),
    )


def dict_to_step_config(data: Dict[str, Any]) -> StepConfig:
    """Convert dictionary to StepConfig. step_type is deprecated; defaults to TASK."""
    from app.domain.common.value_objects import StepType

    step_type = data.get("step_type", "TASK")
    if isinstance(step_type, str):
        try:
            step_type = StepType(step_type.lower())
        except ValueError:
            step_type = StepType.TASK

    job = None
    if "job" in data:
        if isinstance(data["job"], dict):
            job = dict_to_job_config(data["job"])
        else:
            job = data["job"]

    return StepConfig(
        name=data.get("name", ""),
        description=data.get("description"),
        step_type=step_type,
        job=job,
        depends_on=data.get("depends_on", []),
        timeout_seconds=data.get("timeout_seconds"),
        retry_count=data.get("retry_count", 0),
        retry_delay_seconds=data.get("retry_delay_seconds", 60),
        is_required=data.get("is_required", True),
        on_failure=data.get("on_failure", "fail_workflow"),
        condition=data.get("condition"),
        client_metadata=data.get("client_metadata", {}),
    )


def dict_to_step_reference(data: Dict[str, Any]) -> StepReference:
    import uuid

    step_id = data.get("step_id")

    if isinstance(step_id, str):
        try:
            step_id = uuid.UUID(step_id)
        except ValueError:
            step_id = uuid.uuid4()
    elif not isinstance(step_id, uuid.UUID):
        step_id = uuid.uuid4()

    assert isinstance(step_id, uuid.UUID)

    return StepReference(
        step_id=step_id,
        step_name=data.get("step_name"),
        version=data.get("version"),
    )


def validate_and_convert_enum(
    value: str,
    enum_class: Type[Enum],
    field_name: str,
) -> Any:
    try:
        return enum_class(value)
    except ValueError:
        valid_values = [member.value for member in enum_class]
        raise ValueError(
            f"Invalid {field_name}: '{value}'. "
            f"Must be one of: {', '.join(map(str, valid_values))}"
        )


def dict_list_to_resource_requirements(
    data_list: List[Dict[str, Any]],
) -> List[ResourceRequirements]:
    return [dict_to_resource_requirements(data) for data in data_list]


def dict_to_step_configs(data: Dict[str, Dict[str, Any]]) -> Dict[str, StepConfig]:
    result: Dict[str, StepConfig] = {}
    for step_id, step_data in data.items():
        result[step_id] = dict_to_step_config(step_data)
    return result


def dict_list_to_job_configs(data_list: List[Dict[str, Any]]) -> List[JobConfig]:
    results: List[JobConfig] = []
    for data in data_list:
        results.append(dict_to_job_config(data))
    return results


def dict_list_to_step_references(
    data_list: List[Dict[str, Any]],
) -> List[StepReference]:
    results: List[StepReference] = []
    for data in data_list:
        results.append(dict_to_step_reference(data))
    return results
