# contracts/schema_projection.py

"""
Schema-based projection for request and result payloads.

The provider service definition (parameter_schema, result_schema) is the contract
for what a step accepts as input and produces as output. These projections enforce
that contract at component boundaries:

- Input projection (orchestrator): strip keys not declared in parameter_schema before
  the job is enqueued. Prevents other steps' form values from leaking into a step's
  request_body.

- Output projection (worker): strip keys not declared in result_schema from the raw
  provider response before post-processing. Prevents bulky/undeclared fields (e.g.,
  a provider echoing back the full render spec) from bloating output_data.

Rules:
- If the schema has no "properties" (i.e., the service doesn't declare a shape),
  the payload passes through unchanged. This preserves backward compatibility for
  services that haven't been schema'd yet.
- Projection is deep for object-typed properties: nested objects are projected
  recursively using their own "properties". This lets a service declare
  {"movie": {"type": "object", "properties": {"url": ...}}} and strip undeclared
  sibling keys like "movie.json".
- Arrays and non-object types pass through unchanged - their internal shape is
  considered opaque for projection purposes.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


def project_by_schema(data: Any, schema: Dict[str, Any] | None) -> Any:
    """Project ``data`` to only the keys declared in ``schema.properties``.

    Recurses into nested objects when a child schema declares ``type: object``
    with its own ``properties``. Arrays and scalars pass through unchanged.

    When ``schema`` is falsy or has no ``properties``, ``data`` is returned
    as-is (no contract to enforce).

    When projection drops top-level data keys that the schema didn't declare,
    a single WARN is emitted naming the dropped keys and the declared keys.
    Diagnostic only - behavior is unchanged. This makes schema/impl drift
    audible at first execution instead of surfacing as a missing-path error
    several steps downstream (Bug 3, 2026-04-26).
    """
    if not isinstance(schema, dict):
        return data
    properties = schema.get("properties")
    if not isinstance(properties, dict) or not properties:
        return data
    if not isinstance(data, dict):
        return data

    dropped = set(data.keys()) - set(properties.keys())
    if dropped:
        logger.warning(
            "schema_projection dropped undeclared top-level keys: %s "
            "(declared: %s) - if these were real outputs, the service's "
            "result_schema is out of sync with the worker's emitted shape",
            sorted(dropped),
            sorted(properties.keys()),
        )

    projected: Dict[str, Any] = {}
    for key, child_schema in properties.items():
        if key not in data:
            continue
        value = data[key]
        if (
            isinstance(child_schema, dict)
            and child_schema.get("type") == "object"
            and isinstance(child_schema.get("properties"), dict)
        ):
            projected[key] = project_by_schema(value, child_schema)
        else:
            projected[key] = value
    return projected
