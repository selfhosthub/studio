# workers/studio_workers/env_files.py

"""Helper for resolving env files for worker settings classes.

Honors SHS_DISABLE_ENV_FILES for test isolation. Intentionally side-effect-free
so engine settings modules can import it without pulling in shared settings.
"""

import os
from pathlib import Path


def resolve_env_files(envs_dir: Path) -> tuple[str, ...] | None:
    """Return the env file tuple for settings, or None when SHS_DISABLE_ENV_FILES is set.

    .env.local loads only with SHS_ALLOW_ENV_LOCAL=1 (explicit opt-in, same
    gate as the API); it silently overrode real config when picked up implicitly.
    """
    if os.getenv("SHS_DISABLE_ENV_FILES", "").lower() in ("1", "true", "yes"):
        return None
    files = [str(envs_dir / ".env.dev")]
    if os.getenv("SHS_ALLOW_ENV_LOCAL") == "1":
        files.append(str(envs_dir / ".env.local"))
    return tuple(files)
