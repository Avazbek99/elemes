"""add department name_uz, name_ru, name_en

Revision ID: h7i8j9k0l1
Revises: g6h7i8j9k0
Create Date: 2026-02-18

"""
from alembic import op
import sqlalchemy as sa


revision = 'h7i8j9k0l1'
down_revision = 'g6h7i8j9k0'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('department', schema=None) as batch_op:
        batch_op.add_column(sa.Column('name_uz', sa.String(length=200), nullable=True))
        batch_op.add_column(sa.Column('name_ru', sa.String(length=200), nullable=True))
        batch_op.add_column(sa.Column('name_en', sa.String(length=200), nullable=True))


def downgrade():
    with op.batch_alter_table('department', schema=None) as batch_op:
        batch_op.drop_column('name_en')
        batch_op.drop_column('name_ru')
        batch_op.drop_column('name_uz')
