# api/app/application/services/result_processing/step_result_enrichment.py

"""Single source of truth for the enriched step-result payload.

A worker publishes only the *thin* terminal report (``status`` / ``result`` /
``error`` / ``job_id``). The API resolves the routing fields the result
processor needs (``instance_id``, ``step_id``, ``input_data``, and any
iteration metadata) from the job record. Both the live ``/step-results``
endpoint and the dead-letter replay MUST build the payload identically - if
they diverge, a result delivered after a connectivity outage (replayed from
disk) is dropped with "missing step_id" while the same result delivered live
succeeds (Bug #2 - the dead-letter routing-loss bug).

This helper takes the resolved job and the thin fields and returns the exact
payload shape the result processor consumes. Callers own job resolution
(by ``job_id``) and the broker-state transition; this is the pure projection.
"""

from datetime import UTC, datetime
from typing import Any, Dict, Optional

# Iteration metadata keys copied through verbatim when present on the job's
# input_data. Top-level on the payload per Contract 1 / invariant I-11.
_ITERATION_KEYS = ("iteration_index", "iteration_count", "iteration_group_id")


def build_step_result_payload(
    job: Any,
    *,
    status: str,
    result: Optional[Dict[str, Any]],
    error: Optional[str],
    webhook_pending: bool = False,
) -> Dict[str, Any]:
    """Build the result-processing payload from a resolved queued job.

    ``job`` must expose ``instance_id`` (uuid or None) and ``input_data``
    (dict or None) - the ``QueuedJob`` domain shape. ``status`` / ``result`` /
    ``error`` / ``webhook_pending`` are the worker's thin terminal report.
    """
    instance_id = str(job.instance_id) if job.instance_id else None
    input_data = job.input_data or {}
    step_id = input_data.get("step_id", "")

    payload: Dict[str, Any] = {
        "instance_id": instance_id,
        "step_id": step_id,
        "status": status,
        "result": result,
        "error": error,
        "input_data": input_data,
        "request_body": None,
        "webhook_pending": webhook_pending,
        "published_at": datetime.now(UTC).isoformat(),
    }

    for key in _ITERATION_KEYS:
        if key in input_data:
            payload[key] = input_data[key]

    return payload


__all__ = ["build_step_result_payload"]
