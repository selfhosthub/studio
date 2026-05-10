# api/app/application/services/dead_letter_replay_service.py

"""Dead-letter replay.

Workers write undeliverable terminal step results to
`{WORKSPACE_ROOT}/dead-letters/` when publish fails after all retries
(transient 5xx, restart, network blip). Each cleanup tick this service
replays them through the normal result-processing path - already idempotent
via terminal-state and iteration-index dedup, so safe to retry.

Both successful and failed replays delete the file: leaving failures would
replay the same error forever, and unbounded growth is worse than a logged
loss. The stale-step sweep still catches orphans, so this is a recovery
accelerator, not a load-bearing safety net.

If WORKSPACE_ROOT is unset the replay is a no-op."""

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, Optional

from app.config.settings import settings

logger = logging.getLogger(__name__)


DEAD_LETTER_SUBDIR = "dead-letters"


@dataclass
class DeadLetterReplayResult:
    files_found: int
    files_replayed: int
    files_failed: int
    timestamp: str


class DeadLetterReplayService:
    def __init__(
        self,
        process_result_fn: Callable[[Dict[str, Any]], Awaitable[None]],
        workspace_root: Optional[str] = None,
    ):
        self.process_result_fn = process_result_fn
        self._workspace_root_override = workspace_root

    @property
    def dead_letter_dir(self) -> Optional[Path]:
        root = self._workspace_root_override or settings.WORKSPACE_ROOT
        if not root:
            return None
        return Path(root) / DEAD_LETTER_SUBDIR

    async def replay(self) -> DeadLetterReplayResult:
        # Filename order is approximately chronological ({epoch_ms}__{uuid}.json),
        # which matters for iteration jobs whose aggregation depends on arrival.
        timestamp = datetime.now(UTC).isoformat()
        dir_path = self.dead_letter_dir

        if dir_path is None:
            logger.debug("Dead-letter replay skipped: WORKSPACE_ROOT not configured")
            return DeadLetterReplayResult(0, 0, 0, timestamp)

        if not dir_path.exists():
            return DeadLetterReplayResult(0, 0, 0, timestamp)

        # Workers write .json.tmp then atomic-rename to .json - skip in-flight files.
        files = sorted(p for p in dir_path.iterdir() if p.suffix == ".json")
        if not files:
            return DeadLetterReplayResult(0, 0, 0, timestamp)

        logger.info(f"Dead-letter replay: {len(files)} undelivered result(s) found")

        replayed = 0
        failed = 0
        for path in files:
            try:
                payload = self._load_payload(path)
            except Exception as e:
                logger.error(
                    f"Dead-letter file unreadable, dropping: {path.name} ({e})"
                )
                self._delete_quiet(path)
                failed += 1
                continue

            try:
                await self.process_result_fn(payload)
                replayed += 1
                logger.info(
                    f"Replayed dead-letter {path.name} "
                    f"(instance={payload.get('instance_id')}, "
                    f"step={payload.get('step_id')}, "
                    f"status={payload.get('status')})"
                )
            except Exception as e:
                # Escaped the processor's own handler. Still delete the file -
                # leaving it would replay the same failure forever.
                logger.error(
                    f"Dead-letter replay raised for {path.name}: {e}",
                    exc_info=True,
                )
                failed += 1

            self._delete_quiet(path)

        return DeadLetterReplayResult(
            files_found=len(files),
            files_replayed=replayed,
            files_failed=failed,
            timestamp=timestamp,
        )

    @staticmethod
    def _load_payload(path: Path) -> Dict[str, Any]:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def _delete_quiet(path: Path) -> None:
        try:
            path.unlink(missing_ok=True)
        except OSError as e:
            logger.warning(f"Failed to delete dead-letter {path.name}: {e}")


__all__ = ["DeadLetterReplayService", "DeadLetterReplayResult"]
