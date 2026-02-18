"""add period_start and period_end to direction_contract_amount

Revision ID: a1b2c3d4e5f6
Revises: 1416fea68992
Create Date: 2026-02-05

"""
from alembic import op
import sqlalchemy as sa


revision = 'a1b2c3d4e5f6'
down_revision = '1416fea68992'
branch_labels = None
depends_on = None


def upgrade():
    from sqlalchemy.engine.reflection import Inspector
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    if 'direction_contract_amount' not in inspector.get_table_names():
        return
    cols = [c['name'] for c in inspector.get_columns('direction_contract_amount')]
    if 'period_start' not in cols:
        op.add_column('direction_contract_amount', sa.Column('period_start', sa.Date(), nullable=True))
    if 'period_end' not in cols:
        op.add_column('direction_contract_amount', sa.Column('period_end', sa.Date(), nullable=True))


def downgrade():
    op.drop_column('direction_contract_amount', 'period_end')
    op.drop_column('direction_contract_amount', 'period_start')
