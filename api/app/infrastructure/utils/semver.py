# api/app/infrastructure/utils/semver.py

"""Minimal semver parsing for catalog versioning."""

from __future__ import annotations

import re
from typing import Tuple

# Catalog schemas enforce `^\d+\.\d+\.\d+$`; non-matching input returns the sentinel rather than raising.
_SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


def parse_semver(version: str) -> Tuple[int, int, int]:
    """Parse a MAJOR.MINOR.PATCH version string into a comparable tuple; returns `(-1, -1, -1)` for non-conforming input."""
    if not isinstance(version, str):
        return (-1, -1, -1)
    m = _SEMVER_RE.match(version)
    if not m:
        return (-1, -1, -1)
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)))
