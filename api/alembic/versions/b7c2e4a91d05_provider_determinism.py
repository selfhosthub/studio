# api/alembic/versions/b7c2e4a91d05_provider_determinism.py

"""provider_determinism

Revision ID: b7c2e4a91d05
Revises: a3d1f0c7e9b2
Create Date: 2026-08-16 00:00:00.000000

"""
import logging
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b7c2e4a91d05'
down_revision: Union[str, Sequence[str], None] = 'a3d1f0c7e9b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

logger = logging.getLogger("alembic.runtime.migration")


def _semver_key(version: str) -> tuple[int, int, int, str]:
    """Sort key for a version string; unparseable parts sort lowest."""
    parts = (version or "").split(".")
    nums = []
    for part in parts[:3]:
        digits = ""
        for ch in part:
            if not ch.isdigit():
                break
            digits += ch
        nums.append(int(digits) if digits else 0)
    while len(nums) < 3:
        nums.append(0)
    return (nums[0], nums[1], nums[2], version or "")


def _retire_duplicate_active_providers(bind) -> None:
    """Leave one ACTIVE row per slug, keeping the highest version."""
    rows = bind.execute(
        sa.text(
            "SELECT id, slug, version FROM providers "
            "WHERE operational_status = 'ACTIVE' ORDER BY slug"
        )
    ).fetchall()

    by_slug: dict[str, list] = {}
    for row in rows:
        by_slug.setdefault(row.slug, []).append(row)

    for slug, group in by_slug.items():
        if len(group) < 2:
            continue
        group.sort(key=lambda r: _semver_key(r.version), reverse=True)
        keep, retire = group[0], group[1:]
        for row in retire:
            logger.warning(
                "provider_determinism: retiring duplicate ACTIVE row %s@%s "
                "(keeping %s)",
                slug,
                row.version,
                keep.version,
            )
            bind.execute(
                sa.text(
                    "UPDATE providers SET operational_status = 'INACTIVE' "
                    "WHERE id = :id"
                ),
                {"id": row.id},
            )


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()

    _retire_duplicate_active_providers(bind)

    op.create_index(
        "uix_providers_one_active_per_slug",
        "providers",
        ["slug"],
        unique=True,
        postgresql_where=sa.text("operational_status = 'ACTIVE'"),
    )

    op.add_column(
        "provider_credentials",
        sa.Column("provider_slug", sa.String(length=255), nullable=True),
    )
    op.execute(
        "UPDATE provider_credentials AS c "
        "SET provider_slug = p.slug FROM providers AS p WHERE p.id = c.provider_id"
    )
    orphans = bind.execute(
        sa.text(
            "SELECT count(*) FROM provider_credentials WHERE provider_slug IS NULL"
        )
    ).scalar()
    if orphans:
        raise RuntimeError(
            f"{orphans} provider_credentials rows have no matching provider; "
            "cannot backfill provider_slug"
        )
    op.alter_column("provider_credentials", "provider_slug", nullable=False)

    op.drop_index(
        "ix_provider_credentials_provider_org", table_name="provider_credentials"
    )
    op.drop_constraint(
        "provider_credentials_provider_id_fkey",
        "provider_credentials",
        type_="foreignkey",
    )
    op.drop_column("provider_credentials", "provider_id")
    op.create_index(
        "ix_provider_credentials_provider_org",
        "provider_credentials",
        ["provider_slug", "organization_id"],
    )


def downgrade() -> None:
    raise NotImplementedError('Downgrades are not supported. Redeploy the previous major image.')
