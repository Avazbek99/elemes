"""Add period_start and period_end to student_payment for maxsus kontrakt

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-02-05

"""
from alembic import op
import sqlalchemy as sa


revision = 'c3d4e5f6a7b8'
down_revision = 'b2c3d4e5f6a7'
branch_labels = None
depends_on = None


def upgrade():
    from sqlalchemy.engine.reflection import Inspector
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    if 'student_payment' not in [t for t in inspector.get_table_names()]:
        return
    cols = [c['name'] for c in inspector.get_columns('student_payment')]
    if 'period_start' not in cols:
        op.add_column('student_payment', sa.Column('period_start', sa.Date(), nullable=True))
    if 'period_end' not in cols:
        op.add_column('student_payment', sa.Column('period_end', sa.Date(), nullable=True))


def downgrade():
    op.drop_column('student_payment', 'period_end')
    op.drop_column('student_payment', 'period_start')
