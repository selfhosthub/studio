# api/app/infrastructure/persistence/rls_posture.py

"""Per-transaction RLS posture: session GUCs re-asserted at every transaction begin.

set_config(..., is_local=true) dies at the first commit, and repositories
commit internally - so a one-shot set at session acquisition silently loses
the posture mid-request. Attaching the posture to the session and replaying
it from an after_begin event keeps the GUCs true for every transaction the
session opens, without ever leaking them past the transaction (is_local).
"""

from typing import Dict

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

_POSTURE_KEY = "rls_posture"

_SET_CONFIG = text("SELECT set_config(:name, :value, true)")


def _reassert_posture(session: Session, transaction, connection) -> None:
    """after_begin listener: replay the session's posture GUCs transaction-locally."""
    posture = session.info.get(_POSTURE_KEY)
    if not posture:
        return
    for name, value in posture.items():
        connection.execute(_SET_CONFIG, {"name": name, "value": value})


async def _attach(session: AsyncSession, posture: Dict[str, str]) -> None:
    sync_session = session.sync_session
    sync_session.info[_POSTURE_KEY] = posture
    if not event.contains(sync_session, "after_begin", _reassert_posture):
        event.listen(sync_session, "after_begin", _reassert_posture)
    # A transaction may already be open (e.g. the auth lookup on the shared
    # request session) - after_begin has already fired for it, so assert the
    # posture into the current transaction explicitly.
    for name, value in posture.items():
        await session.execute(_SET_CONFIG, {"name": name, "value": value})


async def set_org_posture(
    session: AsyncSession, org_id: str, *, is_super_admin: bool = False
) -> None:
    """Attach org-scoped posture; re-asserted on every transaction until the session ends."""
    posture: Dict[str, str] = {"app.current_org_id": str(org_id)}
    if is_super_admin:
        posture["app.is_super_admin"] = "true"
    await _attach(session, posture)


async def set_service_posture(session: AsyncSession) -> None:
    """Attach trusted-service posture (matches the RLS service_bypass policies)."""
    await _attach(session, {"app.is_service_account": "true"})


async def set_user_claim_posture(session: AsyncSession, user_id: str) -> None:
    """Attach the QUARANTINED auth-lookup claim (app.current_user_id).

    Set from the unverified JWT sub so the auth SELECT can pass the
    SELECT-only users_self_lookup policy. It must never be trusted anywhere
    else; org/service posture is derived from the verified row afterwards
    and replaces this posture entirely.
    """
    await _attach(session, {"app.current_user_id": str(user_id)})


def prime_service_posture(session: AsyncSession) -> None:
    """Attach service posture WITHOUT asserting into an open transaction.

    Sync variant for factory wrappers priming fresh sessions - no
    transaction exists yet, so the after_begin listener alone covers every
    transaction the session will open. Not for sessions already mid-transaction
    (use set_service_posture there).
    """
    sync_session = session.sync_session
    sync_session.info[_POSTURE_KEY] = {"app.is_service_account": "true"}
    if not event.contains(sync_session, "after_begin", _reassert_posture):
        event.listen(sync_session, "after_begin", _reassert_posture)


def clear_posture(session: AsyncSession) -> None:
    """Detach the posture; open-transaction GUCs die with the transaction (is_local)."""
    sync_session = session.sync_session
    sync_session.info.pop(_POSTURE_KEY, None)
    if event.contains(sync_session, "after_begin", _reassert_posture):
        event.remove(sync_session, "after_begin", _reassert_posture)
