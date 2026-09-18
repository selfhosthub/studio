# workers/studio_workers/utils/internal_auth.py

"""Process-wide worker JWT and current job id for internal API downloads."""

import logging
from typing import Callable, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

_token_getter: Optional[Callable[[], Optional[str]]] = None
_job_id_getter: Optional[Callable[[], Optional[str]]] = None


def set_auth_context(
    token_getter: Optional[Callable[[], Optional[str]]],
    job_id_getter: Optional[Callable[[], Optional[str]]],
) -> None:
    """Register the getters this process uses to authenticate internal calls."""
    global _token_getter, _job_id_getter
    _token_getter = token_getter
    _job_id_getter = job_id_getter


def internal_request_auth() -> Tuple[Dict[str, str], Dict[str, str]]:
    """Return (headers, params) carrying the Bearer JWT and job_id when known."""
    headers: Dict[str, str] = {}
    params: Dict[str, str] = {}
    token = _token_getter() if _token_getter else None
    if token:
        headers["Authorization"] = f"Bearer {token}"
    else:
        logger.warning("No worker JWT available - internal request may fail")
    job_id = _job_id_getter() if _job_id_getter else None
    if job_id:
        params["job_id"] = job_id
    return headers, params
