# api/app/infrastructure/persistence/rls_boot_check.py

"""Boot-time check: can the runtime DB role be subject to RLS at all?

Superusers and BYPASSRLS roles skip row security entirely (even with
FORCE), so every RLS policy is inert under them. Single-URL deployments
(runtime role = postgres) get a loud warning; once the operator opts into
the restricted role (DATABASE_APP_URL set), an RLS-inert runtime role is
a misconfiguration and the API refuses to boot.
"""

import logging
from typing import Optional, Tuple

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger(__name__)


class RlsInertError(RuntimeError):
    """The runtime DB role bypasses RLS while a restricted role was configured."""


async def check_runtime_rls_posture(
    engine: AsyncEngine,
    *,
    fail_closed: bool = False,
) -> Optional[Tuple[bool, bool]]:
    """Return (rolsuper, rolbypassrls) for the runtime role; None if unreadable.

    fail_closed=False: best-effort, never raises (single-URL deployments).
    fail_closed=True: raises RlsInertError when the role bypasses RLS or the
    flags cannot be read (DATABASE_APP_URL deployments - misconfiguration).
    """
    try:
        async with engine.connect() as conn:
            row = (
                await conn.execute(
                    text(
                        "SELECT rolsuper, rolbypassrls FROM pg_roles "
                        "WHERE rolname = current_user"
                    )
                )
            ).first()
    except Exception as e:
        if fail_closed:
            raise RlsInertError(
                f"RLS boot check could not read pg_roles: {e}"
            ) from e
        logger.warning(f"RLS boot check could not read pg_roles: {e}")
        return None

    if row is None:
        if fail_closed:
            raise RlsInertError(
                "RLS boot check: current_user not found in pg_roles"
            )
        logger.warning("RLS boot check: current_user not found in pg_roles")
        return None

    rolsuper, rolbypassrls = bool(row[0]), bool(row[1])
    if rolsuper or rolbypassrls:
        message = (
            "RLS IS INERT for the runtime DB role "
            f"(rolsuper={rolsuper}, rolbypassrls={rolbypassrls}): row-level "
            "security policies are NOT enforced on any query this API runs. "
            "Tenant isolation relies on app-layer checks alone."
        )
        if fail_closed:
            raise RlsInertError(
                message + " DATABASE_APP_URL is set, so this is a "
                "misconfiguration - point it at the restricted shs_app role."
            )
        logger.warning(
            message + " This becomes a boot failure once DATABASE_APP_URL "
            "points the API at the restricted shs_app role."
        )
    else:
        logger.info(
            "RLS boot check: runtime DB role is subject to row-level security "
            f"(rolsuper={rolsuper}, rolbypassrls={rolbypassrls})"
        )
    return (rolsuper, rolbypassrls)
