# api/alembic/versions/062dc0040854_worker_enrollment.py

"""worker_enrollment

Revision ID: 062dc0040854
Revises: d4a7f2b60c18
Create Date: 2026-08-28 13:36:21.486236

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '062dc0040854'
down_revision: Union[str, Sequence[str], None] = 'd4a7f2b60c18'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add the join-token and per-worker enrollment tables."""
    op.create_table(
        "worker_join_tokens",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("queues", postgresql.ARRAY(sa.String()), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("used_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_worker_join_tokens_expires", "worker_join_tokens", ["expires_at"], unique=False
    )
    op.create_index(
        op.f("ix_worker_join_tokens_token_hash"),
        "worker_join_tokens",
        ["token_hash"],
        unique=True,
    )
    op.create_table(
        "worker_enrollments",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("credential_hash", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("queues", postgresql.ARRAY(sa.String()), nullable=False),
        sa.Column("join_token_id", sa.UUID(), nullable=True),
        sa.Column("revoked_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["join_token_id"], ["worker_join_tokens.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_worker_enrollments_credential_hash"),
        "worker_enrollments",
        ["credential_hash"],
        unique=True,
    )
    op.create_index(
        "ix_worker_enrollments_revoked", "worker_enrollments", ["revoked_at"], unique=False
    )


def downgrade() -> None:
    raise NotImplementedError('Downgrades are not supported. Redeploy the previous major image.')
