# api/app/application/services/workflow_slug_resolution.py

"""Slug resolution for workflow steps authored against the catalog.

Catalog workflows reference providers and prompts by slug (shs/openai,
promptSlug); stored steps reference them by UUID. The marketplace install path
and the file-import path both run their steps through here.
"""

from typing import Any, Dict, List, Tuple, TypeGuard

PROVIDER_FIELDS = ("provider_id", "credential_provider_id")
ROUTING_FIELDS = ("service_type", "provider_id", "service_id")


def is_slug(value: Any) -> TypeGuard[str]:
    """True for a namespaced slug (shs/openai), false for a UUID or empty."""
    return isinstance(value, str) and "/" in value


def collect_slugs(steps: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    """Provider slugs and prompt slugs referenced by steps, de-duplicated."""
    provider_slugs: List[str] = []
    prompt_slugs: List[str] = []
    for step_data in steps.values():
        if not isinstance(step_data, dict):
            continue
        job = step_data.get("job")
        job = job if isinstance(job, dict) else {}
        for field in PROVIDER_FIELDS:
            for value in (step_data.get(field), job.get(field)):
                if is_slug(value) and value not in provider_slugs:
                    provider_slugs.append(value)
        input_mappings = step_data.get("input_mappings")
        if not isinstance(input_mappings, dict):
            continue
        for mapping in input_mappings.values():
            if not isinstance(mapping, dict):
                continue
            slug = mapping.get("promptSlug")
            if isinstance(slug, str) and slug and slug not in prompt_slugs:
                prompt_slugs.append(slug)
    return provider_slugs, prompt_slugs


def resolve_step_slugs(
    steps: Dict[str, Any],
    provider_slug_to_uuid: Dict[str, str],
    prompt_slug_to_uuid: Dict[str, str],
) -> Tuple[Dict[str, Any], List[str]]:
    """Rewrite slugs to UUIDs and lift routing fields from job to step level.

    Returns the rewritten steps and a warning per slug with no installed match.
    """
    resolved: Dict[str, Any] = {}
    warnings: List[str] = []
    for step_id, step_data in steps.items():
        # Malformed steps pass through; each caller decides whether to reject.
        if not isinstance(step_data, dict):
            resolved[step_id] = step_data
            continue
        step_data = dict(step_data)

        targets: List[Dict[str, Any]] = [step_data]
        if isinstance(step_data.get("job"), dict):
            step_data["job"] = dict(step_data["job"])
            targets.append(step_data["job"])

        for target in targets:
            for field in PROVIDER_FIELDS:
                slug = target.get(field)
                if not is_slug(slug):
                    continue
                if slug in provider_slug_to_uuid:
                    target[field] = provider_slug_to_uuid[slug]
                else:
                    warnings.append(
                        f"Step '{step_id}': Provider {slug} is not installed"
                    )

        job = step_data.get("job")
        if isinstance(job, dict):
            for field in ROUTING_FIELDS:
                if field in job and field not in step_data:
                    step_data[field] = job.pop(field)

        input_mappings = step_data.get("input_mappings")
        if isinstance(input_mappings, dict):
            mappings = {
                key: dict(mapping) if isinstance(mapping, dict) else mapping
                for key, mapping in input_mappings.items()
            }
            step_data["input_mappings"] = mappings
            for mapping in mappings.values():
                if not isinstance(mapping, dict):
                    continue
                slug = mapping.get("promptSlug")
                if not slug:
                    continue
                if slug in prompt_slug_to_uuid:
                    mapping["promptId"] = prompt_slug_to_uuid[slug]
                    del mapping["promptSlug"]
                else:
                    warnings.append(
                        f"Step '{step_id}': AI prompt {slug} is not installed"
                    )

        resolved[step_id] = step_data
    return resolved, warnings
