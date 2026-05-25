# api/app/infrastructure/scheduling/__init__.py

"""
In-process periodic task scheduler.

Runs registered async callbacks on fixed intervals inside the API process.
Purpose-built for cleanup chores (stale workers, stale steps) that must
happen on every deploy without operator intervention - zero-config, runs
wherever the API runs.

Not a workflow scheduler. Workflow scheduling (cron expressions, per-workflow
schedules, catch-up semantics, timezone handling) will be a separate feature
that *consumes* this primitive; see `docs/plans/workflow-scheduler.md` when
that work starts.
"""

from app.infrastructure.scheduling.periodic_scheduler import (
    PeriodicScheduler,
    ScheduledTask,
)

__all__ = ["PeriodicScheduler", "ScheduledTask"]
