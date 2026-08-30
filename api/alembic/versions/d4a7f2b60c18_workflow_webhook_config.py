# api/alembic/versions/d4a7f2b60c18_workflow_webhook_config.py

"""workflow_webhook_config

Revision ID: d4a7f2b60c18
Revises: c9e3b58f1a44
Create Date: 2026-08-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'd4a7f2b60c18'
down_revision: Union[str, Sequence[str], None] = 'c9e3b58f1a44'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add the nullable webhook_config blob to workflows."""
    op.add_column(
        "workflows",
        sa.Column("webhook_config", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    raise NotImplementedError('Downgrades are not supported. Redeploy the previous major image.')
