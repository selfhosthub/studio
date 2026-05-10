# api/app/infrastructure/scheduling/periodic_scheduler.py

"""In-process periodic task scheduler - fixed intervals, in-memory only, no cron or pause/resume."""

import asyncio
import logging
from dataclasses import dataclass
from typing import Awaitable, Callable, List, Optional

logger = logging.getLogger(__name__)


Callback = Callable[[], Awaitable[None]]


@dataclass
class ScheduledTask:
    name: str
    interval_seconds: float
    callback: Callback
    # Delay before the first run - lets startup finish before the first cycle fires.
    initial_delay_seconds: float = 0.0


class PeriodicScheduler:
    """Runs registered tasks on fixed intervals. Each task gets its own asyncio.Task.

    Exceptions are logged and swallowed so one bad cycle doesn't kill the loop.
    """

    def __init__(self) -> None:
        self._tasks: List[ScheduledTask] = []
        self._running: List[asyncio.Task[None]] = []
        self._started = False

    def register(self, task: ScheduledTask) -> None:
        """Register a task. Must be called before start()."""
        if self._started:
            raise RuntimeError("Cannot register tasks after scheduler has started")
        self._tasks.append(task)

    async def start(self) -> None:
        """Start all registered tasks. Idempotent - safe to call once."""
        if self._started:
            return
        self._started = True
        for task in self._tasks:
            async_task = asyncio.create_task(
                self._run_task(task), name=f"scheduled:{task.name}"
            )
            self._running.append(async_task)
        logger.info(
            f"PeriodicScheduler started {len(self._running)} task(s): "
            f"{[t.name for t in self._tasks]}"
        )

    async def stop(self) -> None:
        """Cancel all running tasks and wait for them to exit cleanly."""
        if not self._started:
            return
        for async_task in self._running:
            if not async_task.done():
                async_task.cancel()
        # Wait for cancellation to settle; swallow CancelledError
        for async_task in self._running:
            try:
                await async_task
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.warning(f"Scheduled task exited with error during shutdown: {e}")
        self._running.clear()
        self._started = False
        logger.info("PeriodicScheduler stopped")

    async def _run_task(self, task: ScheduledTask) -> None:
        """Inner loop for one scheduled task."""
        if task.initial_delay_seconds > 0:
            try:
                await asyncio.sleep(task.initial_delay_seconds)
            except asyncio.CancelledError:
                return
        while True:
            try:
                await asyncio.sleep(task.interval_seconds)
            except asyncio.CancelledError:
                return
            try:
                await task.callback()
            except asyncio.CancelledError:
                return
            except Exception as e:
                # Never break the loop on callback errors - next tick gets
                # another chance. Log with task name so operators can grep.
                logger.error(
                    f"Scheduled task '{task.name}' failed: {e}",
                    exc_info=True,
                )


__all__ = ["PeriodicScheduler", "ScheduledTask", "Callback"]


_scheduler_singleton: Optional[PeriodicScheduler] = None


def get_scheduler() -> PeriodicScheduler:
    """Get (or lazily create) the process-wide scheduler singleton."""
    global _scheduler_singleton
    if _scheduler_singleton is None:
        _scheduler_singleton = PeriodicScheduler()
    return _scheduler_singleton


async def reset_scheduler_for_tests() -> None:
    """Stop and clear the singleton. Tests only."""
    global _scheduler_singleton
    if _scheduler_singleton is not None:
        await _scheduler_singleton.stop()
        _scheduler_singleton = None
