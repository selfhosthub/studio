# workers/shared/utils/dead_letter.py

"""
Dead-letter writer for step results that couldn't be delivered to the API.

When result publishing exhausts its retry budget for a terminal status
(COMPLETED/FAILED), the result is written to a JSON file in
{WORKSPACE_ROOT}/dead-letters/. The API picks these up on its next cleanup
tick and replays them via the normal result processor.

Constraints:
- Workspace must be readable by the API process (shared mount in dev; required in prod).
- Only terminal results are dead-lettered; PROCESSING/QUEUED are informational and losable.
- The result processor is idempotent for terminal results, so duplicate delivery is safe.
"""

import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from shared.settings import settings

logger = logging.getLogger(__name__)


DEAD_LETTER_SUBDIR = "dead-letters"


def _dead_letter_dir() -> Path:
    """Resolve the dead-letter directory (lazily - workspace may not exist yet)."""
    return Path(settings.WORKSPACE_ROOT) / DEAD_LETTER_SUBDIR


def write_dead_letter(payload: Dict[str, Any]) -> Optional[Path]:
    """Persist a result payload that couldn't be delivered to the API.

    Returns the file path on success, None if writing itself failed (in which
    case the result is genuinely lost - log and continue, the worker can't do
    more about it).

    Filename format: `{epoch_ms}__{uuid}.json`. The timestamp prefix gives
    natural ordering for the API's pickup loop without parsing the JSON.
    """
    if not settings.DEAD_LETTER_ENABLED:
        return None

    try:
        dir_path = _dead_letter_dir()
        dir_path.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        logger.error(
            f"Dead-letter dir is unwritable; result will be lost. dir={_dead_letter_dir()} err={e}"
        )
        return None

    timestamp_ms = int(time.time() * 1000)
    file_id = uuid.uuid4().hex
    filename = f"{timestamp_ms}__{file_id}.json"
    file_path = dir_path / filename

    # Write atomically: write to .tmp, then rename. Prevents the API from
    # picking up a half-written file mid-flight.
    tmp_path = file_path.with_suffix(".json.tmp")
    try:
        with tmp_path.open("w", encoding="utf-8") as f:
            json.dump(payload, f)
        tmp_path.replace(file_path)
    except (OSError, TypeError, ValueError) as e:
        logger.error(
            f"Failed to write dead-letter for instance="
            f"{payload.get('instance_id')} step={payload.get('step_id')}: {e}"
        )
        # Best-effort cleanup of the partial file
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        return None

    logger.warning(
        f"Wrote dead-letter for undeliverable result: {file_path.name} "
        f"(instance={payload.get('instance_id')}, step={payload.get('step_id')}, "
        f"status={payload.get('status')}). API will replay on next cleanup tick."
    )
    return file_path


__all__ = ["write_dead_letter", "DEAD_LETTER_SUBDIR"]
