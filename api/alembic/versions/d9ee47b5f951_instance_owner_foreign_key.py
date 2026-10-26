# api/alembic/versions/d9ee47b5f951_instance_owner_foreign_key.py

"""instance owner foreign key

Revision ID: d9ee47b5f951
Revises: fe394a605a4b
Create Date: 2026-10-08 11:28:36.474626

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'd9ee47b5f951'
down_revision: Union[str, Sequence[str], None] = 'fe394a605a4b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Runs whose owner no longer exists lose the owner before the constraint lands.
    op.execute(
        """
        UPDATE instances AS i
        SET user_id = NULL
        WHERE i.user_id IS NOT NULL
          AND NOT EXISTS (SELECT 1 FROM users AS u WHERE u.id = i.user_id)
        """
    )
    op.create_foreign_key(
        'instances_user_id_fkey', 'instances', 'users', ['user_id'], ['id'], ondelete='SET NULL'
    )


def downgrade() -> None:
    """Downgrade schema."""
    raise NotImplementedError('Downgrades are not supported. Redeploy the previous major image.')
