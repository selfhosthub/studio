# api/app/infrastructure/security/worker_bootstrap.py

"""The workspace bootstrap token: a worker that can read it is inside the deployment."""

import hmac
import logging
import os
import secrets
from pathlib import Path
from typing import Optional

from app.infrastructure.storage.workspace import get_workspace_path

logger = logging.getLogger(__name__)

BOOTSTRAP_FILE = ".worker-bootstrap"


def bootstrap_path() -> Path:
    """Where the token lives: the root of the shared workspace."""
    return get_workspace_path() / BOOTSTRAP_FILE


def write_bootstrap_token() -> None:
    """Replace the token with a fresh one, readable only by the deployment's user."""
    path = bootstrap_path()
    tmp = path.with_name(f"{BOOTSTRAP_FILE}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as fh:
        fh.write(secrets.token_urlsafe(32))
    os.replace(tmp, path)


def bootstrap_token_matches(presented: Optional[str]) -> bool:
    """Compare against the file as it is now; False when either side is missing."""
    if not presented:
        return False
    try:
        current = bootstrap_path().read_text().strip()
    except (OSError, RuntimeError) as exc:
        logger.warning(f"Worker bootstrap token unreadable: {exc}")
        return False
    return bool(current) and hmac.compare_digest(current, presented)
