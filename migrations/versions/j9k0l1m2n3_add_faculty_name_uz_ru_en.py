"""add faculty name_uz, name_ru, name_en

Revision ID: j9k0l1m2n3
Revises: i8j9k0l1m2
Create Date: 2026-02-18

"""
from alembic import op
import sqlalchemy as sa


revision = 'j9k0l1m2n3'
down_revision = 'i8j9k0l1m2'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('faculty', schema=None) as batch_op:
        batch_op.add_column(sa.Column('name_uz', sa.String(length=200), nullable=True))
        batch_op.add_column(sa.Column('name_ru', sa.String(length=200), nullable=True))
        batch_op.add_column(sa.Column('name_en', sa.String(length=200), nullable=True))
    # Mavjud name ni name_uz ga nusxalash
    op.execute(sa.text("UPDATE faculty SET name_uz = name WHERE name_uz IS NULL OR name_uz = ''"))


def downgrade():
    with op.batch_alter_table('faculty', schema=None) as batch_op:
        batch_op.drop_column('name_en')
        batch_op.drop_column('name_ru')
        batch_op.drop_column('name_uz')
