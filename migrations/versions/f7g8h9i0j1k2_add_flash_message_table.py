"""Add flash_message table

Revision ID: f7g8h9i0j1k2
Revises: e5f6a7b8c9d0
Create Date: 2026-02-11

"""
from alembic import op
import sqlalchemy as sa


revision = 'f7g8h9i0j1k2'
down_revision = 'e5f6a7b8c9d0'
branch_labels = None
depends_on = None


def upgrade():
    from sqlalchemy.engine.reflection import Inspector
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    if 'flash_message' in inspector.get_table_names():
        return
    op.create_table(
        'flash_message',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('text_uz', sa.Text(), nullable=True),
        sa.Column('text_ru', sa.Text(), nullable=True),
        sa.Column('text_en', sa.Text(), nullable=True),
        sa.Column('url', sa.String(500), nullable=True),
        sa.Column('text_color', sa.String(20), nullable=True),
        sa.Column('enabled', sa.Boolean(), nullable=True),
        sa.Column('date_from', sa.Date(), nullable=True),
        sa.Column('date_to', sa.Date(), nullable=True),
        sa.Column('sort_order', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade():
    op.drop_table('flash_message')
