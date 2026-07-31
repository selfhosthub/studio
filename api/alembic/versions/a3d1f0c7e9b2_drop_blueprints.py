# api/alembic/versions/a3d1f0c7e9b2_drop_blueprints.py

"""drop_blueprints

Revision ID: a3d1f0c7e9b2
Revises: 8f45c14bd638
Create Date: 2026-07-29 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a3d1f0c7e9b2'
down_revision: Union[str, Sequence[str], None] = '8f45c14bd638'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("DELETE FROM marketplace_catalogs WHERE catalog_type = 'BLUEPRINTS'")
    op.execute("DELETE FROM package_versions WHERE package_type = 'BLUEPRINT'")
    op.drop_index('ix_workflows_blueprint', table_name='workflows')
    op.drop_constraint('workflows_blueprint_id_fkey', 'workflows', type_='foreignkey')
    op.drop_column('workflows', 'blueprint_id')
    op.drop_index('ix_blueprints_organization_status', table_name='blueprints')
    op.drop_table('blueprints')
    sa.Enum(name='blueprintstatus').drop(op.get_bind(), checkfirst=False)
    sa.Enum(name='blueprintcategory').drop(op.get_bind(), checkfirst=False)


def downgrade() -> None:
    raise NotImplementedError('Downgrades are not supported. Redeploy the previous major image.')
