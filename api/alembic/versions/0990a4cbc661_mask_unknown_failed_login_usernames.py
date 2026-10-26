# api/alembic/versions/0990a4cbc661_mask_unknown_failed_login_usernames.py

"""mask unknown failed login usernames

Revision ID: 0990a4cbc661
Revises: 9d5da241674b
Create Date: 2026-10-21 04:51:01.007470

"""
import json
import logging
from typing import Any, Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0990a4cbc661'
down_revision: Union[str, Sequence[str], None] = '9d5da241674b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

logger = logging.getLogger("alembic.runtime.migration")

UNKNOWN_LOGIN_USERNAME = "[unknown user]"

UNKNOWN_ROWS = sa.text(
    "SELECT a.id, a.event_metadata, a.resource_name FROM audit_events a "
    "WHERE a.action = 'LOGIN_FAILED' "
    "AND CAST(a.event_metadata AS JSONB) ->> 'attempted_username' IS NOT NULL "
    "AND CAST(a.event_metadata AS JSONB) ->> 'attempted_username' <> :marker "
    "AND NOT EXISTS (SELECT 1 FROM users u WHERE "
    "lower(u.username) = lower(trim(CAST(a.event_metadata AS JSONB) ->> 'attempted_username')) "
    "OR u.email = CAST(a.event_metadata AS JSONB) ->> 'attempted_username')"
)


def mask_rows(bind: Any) -> int:
    """Replace each failed sign-in's typed name that matches no user with the marker; returns rows updated."""
    rows = bind.execute(UNKNOWN_ROWS, {"marker": UNKNOWN_LOGIN_USERNAME}).fetchall()
    for row_id, metadata, resource_name in rows:
        attempted = metadata["attempted_username"]
        bind.execute(
            sa.text(
                "UPDATE audit_events SET event_metadata = CAST(:meta AS JSON), resource_name = :name WHERE id = :id"
            ),
            {
                "meta": json.dumps({**metadata, "attempted_username": UNKNOWN_LOGIN_USERNAME}),
                "name": UNKNOWN_LOGIN_USERNAME if resource_name == attempted[:255] else resource_name,
                "id": row_id,
            },
        )
    return len(rows)


def upgrade() -> None:
    """Mask failed sign-in usernames that name no existing user."""
    updated = mask_rows(op.get_bind())
    if updated:
        logger.info(f"audit_events.event_metadata.attempted_username: masked {updated} rows")


def downgrade() -> None:
    raise NotImplementedError('Downgrades are not supported. Redeploy the previous major image.')
