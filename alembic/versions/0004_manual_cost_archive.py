"""add manual cost archive flags

Revision ID: 0004_manual_cost_archive
Revises: 0003_sync_runs_and_auto_values
Create Date: 2026-02-28 00:30:00
"""

from alembic import op
import sqlalchemy as sa

revision = '0004_manual_cost_archive'
down_revision = '0003_sync_runs_and_auto_values'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('manual_costs', sa.Column('is_archived', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('manual_costs', sa.Column('archived_at', sa.DateTime(), nullable=True))
    op.execute("UPDATE manual_costs SET is_archived = 0 WHERE is_archived IS NULL")


def downgrade() -> None:
    op.drop_column('manual_costs', 'archived_at')
    op.drop_column('manual_costs', 'is_archived')
