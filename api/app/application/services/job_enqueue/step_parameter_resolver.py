# api/app/application/services/job_enqueue/step_parameter_resolver.py

"""Resolve a step's job.parameters for a step that parks instead of enqueueing."""

import logging
from typing import Any, Dict

from app.application.services.job_enqueue.input_mapping_service import (
    apply_input_mappings,
    get_input_mappings,
)
from app.application.services.job_enqueue.iteration_service import (
    convert_star_to_zero,
)
from app.application.services.job_enqueue.variable_resolver import VariableResolver
from app.application.services.mapping_resolver import UnresolvedMappingError
from app.domain.workflow.workflow_navigator import WorkflowNavigator
from app.infrastructure.security.step_secrets import (
    step_secret_paths,
    without_secret_values,
)

logger = logging.getLogger(__name__)


def resolve_step_job_parameters(
    workflow_snapshot: Dict[str, Any],
    step_id: str,
    instance_parameters: Dict[str, Any],
    previous_step_results: Dict[str, Any],
) -> Dict[str, Any]:
    """The step's job.parameters after {{ }} resolution and input mappings, scoped to its dependency closure, without secret values."""
    steps = workflow_snapshot.get("steps") or {}
    closure = WorkflowNavigator.get_dependency_closure(steps, step_id)
    scoped = {k: v for k, v in previous_step_results.items() if k in closure}
    step_config = convert_star_to_zero(steps.get(step_id) or {})
    resolved = VariableResolver().resolve_variables_in_config(
        step_config, scoped, instance_parameters
    )
    input_mappings = get_input_mappings(step_config)
    if input_mappings:
        try:
            resolved = apply_input_mappings(
                resolved, input_mappings, scoped, instance_parameters
            )
        except UnresolvedMappingError:
            logger.warning(
                f"Step {step_id}: an input mapping produced no value; "
                f"keeping the {{ }}-resolved parameters"
            )
    return without_secret_values(
        dict((resolved.get("job") or {}).get("parameters") or {}),
        step_secret_paths(step_config),
    )
