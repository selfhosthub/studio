# contracts/job_claim.py

"""
Job Claim Contract: API → Worker payload shape.

This is the canonical definition of the job dict workers receive
when claiming a job from the API via GET /api/v1/internal/jobs/claim.

Python 3.11 compatible.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class JobClaimContract(BaseModel):
    """
    Canonical job claim payload shape.

    API builds this in the claim endpoint response.
    Workers parse it in worker_base.py to dispatch to handlers.

    Iteration fields are top-level when present.
    """

    job_id: str
    instance_id: str
    step_id: str
    service_type: str
    service_id: str
    config: Dict[str, Any] = {}
    input_mappings: Dict[str, Any] = {}
    credentials: Dict[str, Any] = {}
    workspace_path: Optional[str] = None

    # Request tracing - propagated from API correlation_id
    correlation_id: Optional[str] = None

    # Iteration metadata - top-level when present
    iteration_index: Optional[int] = None
    iteration_count: Optional[int] = None
    iteration_group_id: Optional[str] = None
    iteration_requests: Optional[List[Dict[str, Any]]] = None
