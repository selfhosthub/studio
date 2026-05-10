# api/app/application/services/result_processing/output_extractor.py

"""Extracts named outputs from job results using JSONPath expressions.

Example:
    Step config outputs: {"project_id": {"path": "project"}, "status_url": {"path": "status_url"}}
    Job result: {"project": "abc123", "status_url": "https://..."}
    Extracted outputs: {"project_id": "abc123", "status_url": "https://..."}
"""

import json
import logging
from typing import Any, Dict, Optional

import jsonpath_ng

from app.domain.instance_step.step_execution import StepExecution
from app.domain.provider.repository import ProviderServiceRepository

logger = logging.getLogger(__name__)


class OutputExtractor:
    """Extracts named outputs from job results using JSONPath.

    Supports both step-level output configuration and service-level defaults.
    """

    async def extract_outputs(
        self,
        job: StepExecution,
        step_config: Dict[str, Any],
        provider_service_repo: Optional[ProviderServiceRepository] = None,
    ) -> Dict[str, Any]:
        """Extract named outputs from the job result using step output configuration.

        Falls back to service-level outputs from the database when step outputs
        are not configured.
        """
        if not job.result:
            logger.warning(f"Step {job.step_key}: No job.result to extract from")
            return {}

        # Log what we received
        logger.debug(
            f"OutputExtractor ENTRY step={job.step_key}: "
            f"step_config_keys={list(step_config.keys()) if isinstance(step_config, dict) else type(step_config)}, "
            f"has_outputs={'outputs' in step_config if isinstance(step_config, dict) else 'N/A'}, "
            f"outputs_raw_type={type(step_config.get('outputs')).__name__ if isinstance(step_config, dict) else 'N/A'}"
        )

        # First try step-level outputs config
        outputs_config = step_config.get("outputs") or {}

        # Fall back to service-level outputs if step doesn't define them
        if not outputs_config and provider_service_repo:
            outputs_config = await self._get_service_outputs(
                step_config, provider_service_repo, job.step_key
            )

        logger.debug(
            f"OutputExtractor step {job.step_key}: "
            f"result_keys={list(job.result.keys()) if isinstance(job.result, dict) else type(job.result)}, "
            f"outputs_config={list(outputs_config.keys()) if isinstance(outputs_config, dict) else outputs_config}"
        )

        if not outputs_config:
            # No output mapping configured - use raw result as extracted_outputs
            # Copy to avoid shared reference between job.result and extracted_outputs
            job.extracted_outputs = (
                dict(job.result) if isinstance(job.result, dict) else job.result
            )
            return job.extracted_outputs

        extracted = self._extract_with_jsonpath(job, outputs_config)
        job.extracted_outputs = extracted

        if extracted:
            logger.debug(f"Extracted {len(extracted)} outputs from step {job.step_key}")

        return extracted

    async def _get_service_outputs(
        self,
        step_config: Dict[str, Any],
        provider_service_repo: ProviderServiceRepository,
        step_id: str,
    ) -> Dict[str, Any]:
        """Return output configuration from service-level metadata, or empty dict."""
        service_id = step_config.get("service_id") or step_config.get("job", {}).get(
            "service_id"
        )
        if not service_id:
            return {}

        service = await provider_service_repo.get_by_service_id(
            service_id, skip=0, limit=1
        )
        if service and service.client_metadata:
            outputs_config = service.client_metadata.get("outputs", {})
            if outputs_config:
                logger.debug(
                    f"Using service-level outputs for {step_id}: "
                    f"{list(outputs_config.keys())}"
                )
                return outputs_config

        return {}

    def extract_from_data(
        self,
        data: Dict[str, Any],
        outputs_config: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Extract named outputs from an arbitrary data dict using the outputs config.

        Used to filter aggregated iteration results down to only declared outputs.
        Unlike the async extract path, this operates on a plain dict rather than
        a job execution object.
        """
        if not outputs_config or not data:
            return data

        extracted: Dict[str, Any] = {}
        for output_name, output_config in outputs_config.items():
            if not isinstance(output_config, dict):
                continue
            path = output_config.get("path")
            if not path:
                continue
            try:
                expr = jsonpath_ng.parse(path)
                matches = expr.find(data)
                if matches:
                    values = [m.value for m in matches]
                    extracted[output_name] = values[0] if len(values) == 1 else values
            except Exception as e:
                logger.error(
                    f"Failed to extract aggregated output '{output_name}': {e}"
                )
        return extracted

    def _extract_with_jsonpath(
        self,
        job: StepExecution,
        outputs_config: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Extract outputs using JSONPath expressions."""
        extracted: Dict[str, Any] = {}

        for output_name, output_config in outputs_config.items():
            if not isinstance(output_config, dict):
                continue

            path = output_config.get("path")
            if not path:
                logger.warning(f"Output '{output_name}' missing 'path' configuration")
                continue

            try:
                # Parse and evaluate JSONPath expression
                expr = jsonpath_ng.parse(path)
                matches = expr.find(job.result)

                if matches:
                    # Extract all matches - single value if one, array if multiple
                    values = [m.value for m in matches]
                    extracted_value = values[0] if len(values) == 1 else values
                    extracted[output_name] = extracted_value

                    # Log what was extracted (truncate if large)
                    if isinstance(extracted_value, list):
                        logger.debug(
                            f"Extracted '{output_name}' from path '{path}': "
                            f"array of {len(extracted_value)} items"
                        )
                    else:
                        value_preview = str(extracted_value)[:100]
                        logger.debug(
                            f"Extracted '{output_name}' from path '{path}': {value_preview}"
                        )
                else:
                    logger.debug(
                        f"No direct match for '{output_name}' at '{path}', "
                        f"trying JSON string navigation..."
                    )
                    # Try navigating through JSON strings (e.g., OpenAI json_object mode
                    # returns content as a JSON string, not a parsed object)
                    value = self._extract_through_json_string(job.result, path)
                    if value is not None:
                        extracted[output_name] = value
                        logger.debug(
                            f"Extracted '{output_name}' from path '{path}' "
                            f"(via JSON string parse): {str(value)[:100]}"
                        )
                    else:
                        result_keys = (
                            list(job.result.keys())
                            if isinstance(job.result, dict)
                            else type(job.result).__name__
                        )
                        logger.warning(
                            f"Step '{job.step_key}': output '{output_name}' "
                            f"not found at path '{path}' "
                            f"(result top-level: {result_keys})"
                        )

            except Exception as e:
                logger.error(
                    f"Failed to extract output '{output_name}': {e}", exc_info=True
                )

        return extracted

    def _extract_through_json_string(
        self,
        data: Any,
        path: str,
    ) -> Any:
        """Extract a value when an intermediate path element is a JSON string.

        When APIs return embedded JSON strings rather than parsed objects, standard
        JSONPath cannot navigate into them. This method tries progressively shorter
        prefix paths, parses any string value it finds as JSON, then evaluates the
        remaining suffix path against the parsed object.
        """
        parts = path.split(".")
        logger.debug(
            f"_extract_through_json_string: path='{path}', "
            f"parts={parts}, num_splits={len(parts)}"
        )

        for i in range(len(parts) - 1, 0, -1):
            parent_path = ".".join(parts[:i])
            child_path = ".".join(parts[i:])

            try:
                logger.debug(
                    f"  Trying split i={i}: parent='{parent_path}', child='{child_path}'"
                )
                parent_expr = jsonpath_ng.parse(parent_path)
                parent_matches = parent_expr.find(data)

                if not parent_matches:
                    logger.debug(f"  No matches for parent path '{parent_path}'")
                    continue

                parent_value = parent_matches[0].value
                logger.debug(
                    f"  Parent match type={type(parent_value).__name__}, "
                    f"is_str={isinstance(parent_value, str)}, "
                    f"preview={str(parent_value)[:120]}"
                )

                if not isinstance(parent_value, str):
                    continue

                try:
                    parsed = json.loads(parent_value)
                    logger.debug(
                        f"  JSON parsed OK, type={type(parsed).__name__}, "
                        f"keys={list(parsed.keys()) if isinstance(parsed, dict) else 'N/A'}"
                    )
                except (json.JSONDecodeError, ValueError) as je:
                    logger.debug(f"  JSON parse failed: {je}")
                    continue

                child_expr = jsonpath_ng.parse(child_path)
                child_matches = child_expr.find(parsed)

                if child_matches:
                    values = [m.value for m in child_matches]
                    result = values[0] if len(values) == 1 else values
                    logger.debug(
                        f"  SUCCESS: child path '{child_path}' matched, "
                        f"type={type(result).__name__}, preview={str(result)[:120]}"
                    )
                    return result
                else:
                    logger.debug(
                        f"  Child path '{child_path}' found no matches in parsed JSON"
                    )
            except Exception as e:
                logger.error(
                    f"  Exception during JSON string extraction: "
                    f"{type(e).__name__}: {e}",
                    exc_info=True,
                )
                continue

        logger.debug(
            f"_extract_through_json_string: no extraction succeeded for path '{path}'"
        )
        return None
