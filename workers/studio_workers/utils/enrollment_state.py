# workers/studio_workers/utils/enrollment_state.py

"""Workspace files for the registration handshake: bootstrap token, saved credential, pending request."""

import json
import os
from pathlib import Path
from typing import Dict, Optional

BOOTSTRAP_FILE = ".worker-bootstrap"
STATE_DIR = ".studio-worker"


def _read_text(path: Path) -> Optional[str]:
    """Return the stripped file contents, or None when missing, unreadable or empty."""
    try:
        return path.read_text(encoding="utf-8").strip() or None
    except (OSError, UnicodeDecodeError):
        return None


def _write_private(path: Path, content: str) -> None:
    """Write content atomically with mode 0600 inside a 0700 directory."""
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    tmp = path.with_name(f"{path.name}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(content)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def _remove(path: Path) -> None:
    """Delete a file, ignoring a missing one."""
    path.unlink(missing_ok=True)


def _state_file(root: str, worker_type: str, suffix: str) -> Path:
    """Path of a worker type's state file."""
    return Path(root) / STATE_DIR / f"{worker_type}.{suffix}"


def read_bootstrap_token(root: str) -> Optional[str]:
    """The API's current bootstrap token, or None."""
    return _read_text(Path(root) / BOOTSTRAP_FILE)


def load_credential(root: str, worker_type: str) -> Optional[str]:
    """The saved enrollment credential, or None."""
    return _read_text(_state_file(root, worker_type, "credential"))


def save_credential(root: str, worker_type: str, credential: str) -> None:
    """Save the enrollment credential."""
    _write_private(_state_file(root, worker_type, "credential"), credential)


def clear_credential(root: str, worker_type: str) -> None:
    """Delete the saved enrollment credential."""
    _remove(_state_file(root, worker_type, "credential"))


def load_request(root: str, worker_type: str) -> Optional[Dict[str, str]]:
    """The pending enrollment request (request_id, poll_token), or None."""
    text = _read_text(_state_file(root, worker_type, "request"))
    if text is None:
        return None
    try:
        data = json.loads(text)
    except ValueError:
        return None
    if not isinstance(data, dict) or not data.get("request_id") or not data.get("poll_token"):
        return None
    return {"request_id": str(data["request_id"]), "poll_token": str(data["poll_token"])}


def save_request(root: str, worker_type: str, request_id: str, poll_token: str) -> None:
    """Save the pending enrollment request."""
    content = json.dumps({"request_id": request_id, "poll_token": poll_token})
    _write_private(_state_file(root, worker_type, "request"), content)


def clear_request(root: str, worker_type: str) -> None:
    """Delete the pending enrollment request."""
    _remove(_state_file(root, worker_type, "request"))
