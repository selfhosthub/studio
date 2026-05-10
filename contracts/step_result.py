# contracts/step_result.py

"""Step Result Contract: minimal worker → API payload shape."""

from typing import Any, Dict, Optional

from pydantic import BaseModel


class StepResultContract(BaseModel):
    """
    Minimal payload workers POST to /api/v1/internal/step-results.

    Workers send only what they know. Context (instance_id, step_id, input_data)
    is resolved server-side from the JWT worker_id → active job lookup.

    Rules:
    - result is always a dict, never None over the wire (default: {})
    - iteration fields are worker-side only (extracted from job payload before the call)
    """

    status: str  # PROCESSING, COMPLETED, FAILED, WAITING_FOR_WEBHOOK, WAITING_FOR_APPROVAL
    result: Dict[str, Any] = {}
    error: Optional[str] = None
