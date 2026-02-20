"""add faculty description_uz, description_ru, description_en

Revision ID: l1m2n3o4p5
Revises: k0l1m2n3o4
Create Date: 2026-02-18

"""
from alembic import op
import sqlalchemy as sa


revision = 'l1m2n3o4p5'
down_revision = 'k0l1m2n3o4'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('faculty', schema=None) as batch_op:
        batch_op.add_column(sa.Column('description_uz', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('description_ru', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('description_en', sa.Text(), nullable=True))
    op.execute(sa.text("UPDATE faculty SET description_uz = description WHERE description IS NOT NULL AND (description_uz IS NULL OR description_uz = '')"))


def downgrade():
    with op.batch_alter_table('faculty', schema=None) as batch_op:
        batch_op.drop_column('description_en')
        batch_op.drop_column('description_ru')
        batch_op.drop_column('description_uz')
