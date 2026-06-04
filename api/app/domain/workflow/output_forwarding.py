# api/app/domain/workflow/output_forwarding.py

"""Output forwarding: when a step has output_forwarding.enabled=True, predecessor outputs are merged into its own outputs so downstream steps can reference them through the forwarding step."""

import logging
from typing import Any, Dict, Set

logger = logging.getLogger(__name__)


def apply_output_forwarding(
    results: Dict[str, Any],
    steps_config: Dict[str, Any],
) -> Dict[str, Any]:
    """Merge predecessor outputs into each forwarding step. Modifies results in place; native outputs take precedence over forwarded ones. Handles forwarding chains recursively."""
    logger.debug(
        f"[OUTPUT_FORWARDING] Starting with results keys={list(results.keys())}, "
        f"steps_config keys={list(steps_config.keys())}"
    )
    # Track processed steps to handle forwarding chains correctly
    processed: Set[str] = set()

    def process_step(step_id: str) -> Dict[str, Any]:
        """Process a step and return its effective outputs (including forwarded)."""
        if step_id in processed:
            logger.debug(f"[OUTPUT_FORWARDING] Step '{step_id}' already processed")
            return results.get(step_id, {})

        step_config = steps_config.get(step_id, {})
        if not isinstance(step_config, dict):
            logger.debug(
                f"[OUTPUT_FORWARDING] Step '{step_id}' has no config or not a dict"
            )
            processed.add(step_id)
            return results.get(step_id, {})

        # Check if output_forwarding is enabled
        forwarding_config = step_config.get("output_forwarding", {})
        if not forwarding_config.get("enabled"):
            logger.debug(
                f"[OUTPUT_FORWARDING] Step '{step_id}' has forwarding disabled or missing. "
                f"Config: {forwarding_config}"
            )
            processed.add(step_id)
            return results.get(step_id, {})

        # Get immediate predecessor (first dependency)
        depends_on = step_config.get("depends_on", []) or []
        if not depends_on:
            logger.debug(
                f"[OUTPUT_FORWARDING] Step '{step_id}' has forwarding enabled but no depends_on. "
                f"Returning native results: {list(results.get(step_id, {}).keys())}"
            )
            processed.add(step_id)
            return results.get(step_id, {})

        # Process predecessor first (handles forwarding chains)
        predecessor_id = depends_on[0]
        logger.debug(
            f"[OUTPUT_FORWARDING] Step '{step_id}' has forwarding enabled. "
            f"Predecessor: '{predecessor_id}'"
        )
        predecessor_outputs = process_step(predecessor_id)
        logger.debug(
            f"[OUTPUT_FORWARDING] Predecessor '{predecessor_id}' outputs: "
            f"{list(predecessor_outputs.keys())}"
        )

        # Get this step's native outputs
        native_outputs = results.get(step_id, {})
        logger.debug(
            f"[OUTPUT_FORWARDING] Step '{step_id}' native outputs: "
            f"{list(native_outputs.keys())}"
        )

        # Determine which fields to forward
        forwarding_mode = forwarding_config.get("mode", "all")
        selected_fields = forwarding_config.get("selected_fields", [])

        forwarded: Dict[str, Any] = {}
        for field_name, field_value in predecessor_outputs.items():
            if forwarding_mode == "selected":
                if field_name not in selected_fields:
                    continue
            forwarded[field_name] = field_value

        # Merge: native outputs take precedence over forwarded
        merged = {**forwarded, **native_outputs}
        results[step_id] = merged

        processed.add(step_id)
        logger.debug(
            f"[OUTPUT_FORWARDING] Applied for step '{step_id}': "
            f"forwarded {list(forwarded.keys())} from '{predecessor_id}', "
            f"merged keys: {list(merged.keys())}"
        )
        return merged

    # Process all steps
    for step_id in steps_config.keys():
        process_step(step_id)

    return results
