"""add sync runs and auto fallback values

Revision ID: 0003_sync_runs_and_auto_values
Revises: 0002_invoice_field_sources
Create Date: 2026-02-28 00:00:00
"""

from alembic import op
import sqlalchemy as sa

revision = '0003_sync_runs_and_auto_values'
down_revision = '0002_invoice_field_sources'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('invoices', sa.Column('vendor_auto', sa.String(length=255), nullable=True))
    op.add_column('invoices', sa.Column('amount_auto', sa.Numeric(precision=12, scale=2), nullable=True))
    op.execute("UPDATE invoices SET vendor_auto = vendor WHERE vendor_source = 'auto' AND vendor_auto IS NULL")
    op.execute("UPDATE invoices SET amount_auto = amount WHERE amount_source = 'auto' AND amount_auto IS NULL")

    op.create_table(
        'sync_runs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('started_at', sa.DateTime(), nullable=False),
        sa.Column('finished_at', sa.DateTime(), nullable=False),
        sa.Column('duration_ms', sa.Integer(), nullable=False),
        sa.Column('checked_docs', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('new_invoices', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('updated_invoices', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('skipped_invoices', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('error_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_error_text', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_sync_runs_started_at', 'sync_runs', ['started_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_sync_runs_started_at', table_name='sync_runs')
    op.drop_table('sync_runs')
    op.drop_column('invoices', 'amount_auto')
    op.drop_column('invoices', 'vendor_auto')
