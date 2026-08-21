# workers/studio_workers/utils/startup_checks.py

"""Startup requirement checks declared per worker type."""

import importlib.util
import os
import tempfile
from typing import Dict, List

from studio_workers.worker_types import WORKER_TYPES


class StartupCheckError(RuntimeError):
    """Raised when a worker's declared startup requirements are not met."""


def run_startup_checks(worker_type: str, setting_values: Dict[str, str]) -> List[str]:
    """Return one failure message per unmet requirement declared by the worker type.

    A type outside the registry declares nothing and has nothing to check.
    """
    config = WORKER_TYPES.get(worker_type)
    requirements = config.startup_requirements if config else {}
    failures: List[str] = []

    for module_name in requirements.get("required_modules", []):
        if importlib.util.find_spec(module_name) is None:
            failures.append(f"required module '{module_name}' is not installed")

    by_setting = requirements.get("required_modules_by_setting", {})
    for setting_name, module_by_value in by_setting.items():
        value = setting_values.get(setting_name)
        module_name = module_by_value.get(value)
        if module_name is None:
            failures.append(
                f"SHS_{setting_name}={value!r} names no known option "
                f"(expected one of {sorted(module_by_value)})"
            )
        elif importlib.util.find_spec(module_name) is None:
            failures.append(
                f"SHS_{setting_name}={value!r} needs module '{module_name}', which is not installed"
            )

    for env_name in requirements.get("writable_path_envs", []):
        path = os.environ.get(env_name)
        if path:
            failures.extend(_writable_failures(env_name, path))

    return failures


def _writable_failures(env_name: str, path: str) -> List[str]:
    """Return a failure message when path cannot be created and written."""
    try:
        os.makedirs(path, exist_ok=True)
        with tempfile.TemporaryFile(dir=path):
            pass
    except OSError as exc:
        return [f"{env_name}={path} is not writable: {exc.strerror or exc}"]
    return []
