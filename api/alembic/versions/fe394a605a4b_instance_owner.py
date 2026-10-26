# api/alembic/versions/fe394a605a4b_instance_owner.py

"""instance owner

Revision ID: fe394a605a4b
Revises: 362c5faa2e93
Create Date: 2026-10-08 10:40:41.548759

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fe394a605a4b'
down_revision: Union[str, Sequence[str], None] = '362c5faa2e93'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('instances', sa.Column('user_id', sa.UUID(), nullable=True))
    op.create_index(op.f('ix_instances_user_id'), 'instances', ['user_id'], unique=False)
    # Triggered runs (schedule, webhook, api, event) belong to the workflow owner; other runs stay null.
    op.execute(
        """
        UPDATE instances AS i
        SET user_id = w.created_by
        FROM workflows AS w
        WHERE i.workflow_id = w.id
          AND i.user_id IS NULL
          AND i.client_metadata->>'source' IN ('schedule', 'webhook', 'api', 'event')
          AND EXISTS (SELECT 1 FROM users AS u WHERE u.id = w.created_by)
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    raise NotImplementedError('Downgrades are not supported. Redeploy the previous major image.')
