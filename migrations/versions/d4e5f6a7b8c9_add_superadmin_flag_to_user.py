"""Add superadmin_flag to user

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-02-09

"""
from alembic import op
import sqlalchemy as sa


revision = 'd4e5f6a7b8c9'
down_revision = 'c3d4e5f6a7b8'
branch_labels = None
depends_on = None


def upgrade():
    from sqlalchemy.engine.reflection import Inspector
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    table_names = inspector.get_table_names()
    if 'user' not in table_names:
        return
    cols = [c['name'] for c in inspector.get_columns('user')]
    if 'superadmin_flag' not in cols:
        op.add_column('user', sa.Column('superadmin_flag', sa.Boolean(), nullable=True))


def downgrade():
    op.drop_column('user', 'superadmin_flag')
