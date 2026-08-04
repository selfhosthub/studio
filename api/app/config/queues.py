# api/app/config/queues.py

"""The queue allowlist: compiled defaults union the operator's widening.

Queues stay a pre-registered allowlist (ruling 2026-07-29): manifests and
packages name queues, never create or widen the set; only the operator
extends it (SHS_ALLOWED_QUEUES). Ruling 2026-08-03.
"""

from studio_workers.contracts.queues import REGISTERED_QUEUES

from app.config.settings import settings


def allowed_queues() -> frozenset[str]:
    """Compiled defaults union SHS_ALLOWED_QUEUES (comma-separated)."""
    operator = {
        q.strip() for q in settings.ALLOWED_QUEUES.split(",") if q.strip()
    }
    return frozenset(REGISTERED_QUEUES) | operator
