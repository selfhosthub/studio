# api/app/application/services/file_usage.py

"""Runs and steps that hold a set of organization files."""

from dataclasses import dataclass
from typing import List, Optional, Sequence
from uuid import UUID

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

_RUNS_HOLDING_FILES = text(
    """
    SELECT f.instance_id,
           w.name,
           i.version,
           NULLIF(COALESCE(NULLIF(s.step_name, ''), s.step_key), ''),
           count(*)
    FROM org_files f
    JOIN instances i ON i.id = f.instance_id
    JOIN workflows w ON w.id = i.workflow_id
    LEFT JOIN step_executions s ON s.id = COALESCE(f.job_execution_id, f.instance_step_id)
    WHERE f.organization_id = :organization_id AND f.id IN :file_ids
    GROUP BY 1, 2, 3, 4
    ORDER BY 2, 3, 4
    """
).bindparams(bindparam("file_ids", expanding=True))


@dataclass(frozen=True)
class FileRunUsage:
    """Files of one run step among the asked files."""

    instance_id: UUID
    instance_name: str
    step_name: Optional[str]
    file_count: int


async def runs_holding_files(
    session: AsyncSession, organization_id: UUID, file_ids: Sequence[UUID]
) -> List[FileRunUsage]:
    """Each run step holding any of the organization's files in file_ids, with how many it holds."""
    result = await session.execute(
        _RUNS_HOLDING_FILES,
        {"organization_id": organization_id, "file_ids": list(file_ids)},
    )
    return [
        FileRunUsage(
            instance_id=instance_id,
            instance_name=f"{workflow_name} - Run #{version}",
            step_name=step_name,
            file_count=int(file_count),
        )
        for instance_id, workflow_name, version, step_name, file_count in result.all()
    ]
