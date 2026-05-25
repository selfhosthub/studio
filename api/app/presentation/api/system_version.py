# api/app/presentation/api/system_version.py

"""
Version-disclosure endpoint for studio-console restore preflight.

Exposes the running Studio's installed alembic revisions so the console can
compare against a backup's recorded revision and pick the right confirmation
tier (older-known: soft warn; unknown-future: hard block).

Super-admin only - the endpoint reveals software-version info that helps an
attacker map running code to known CVEs.
"""

import os
from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text

from app import __version__
from app.infrastructure.persistence.database import db
from app.presentation.api.dependencies import require_super_admin

router = APIRouter(prefix="/system", tags=["System"])


class SystemVersionResponse(BaseModel):
    api_version: str
    git_sha: Optional[str]
    alembic_head: Optional[str]
    alembic_heads: List[str]
    alembic_current: Optional[str]
    alembic_known_revisions: List[str]


def _alembic_script_dir():
    """ScriptDirectory for the running app's alembic.ini.

    Lazy import keeps alembic out of cold-import paths for every other route.
    """
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    api_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    cfg = Config(os.path.join(api_dir, "alembic.ini"))
    return ScriptDirectory.from_config(cfg)


async def _read_alembic_current() -> Optional[str]:
    """Current head stamped in alembic_version, or None if the table is absent
    (brownfield pre-bootstrap, or test schema with create_all-only setup)."""
    if db.engine is None:
        return None
    async with db.engine.begin() as conn:
        exists = (
            await conn.execute(text("SELECT to_regclass('alembic_version')"))
        ).scalar()
        if exists is None:
            return None
        row = (
            await conn.execute(text("SELECT version_num FROM alembic_version LIMIT 1"))
        ).first()
        return row[0] if row is not None else None


@router.get(
    "/version",
    response_model=SystemVersionResponse,
    summary="Get installed version + alembic revision history",
    description=(
        "Returns the running Studio's API version, git SHA, and alembic "
        "revision history. Used by studio-console restore preflight to "
        "compare a backup's revision against revisions this code knows "
        "about. Super-admin only."
    ),
)
async def get_system_version(
    _: None = Depends(require_super_admin),
) -> SystemVersionResponse:
    script_dir = _alembic_script_dir()
    heads = list(script_dir.get_heads())
    head = heads[0] if len(heads) == 1 else None
    known = [s.revision for s in script_dir.walk_revisions()]
    current = await _read_alembic_current()

    return SystemVersionResponse(
        api_version=__version__,
        git_sha=os.getenv("SHS_GIT_SHA") or None,
        alembic_head=head,
        alembic_heads=heads,
        alembic_current=current,
        alembic_known_revisions=known,
    )
