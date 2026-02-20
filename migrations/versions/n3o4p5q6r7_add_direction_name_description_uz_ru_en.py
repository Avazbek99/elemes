"""add direction name_uz/ru/en, description_uz/ru/en

Revision ID: n3o4p5q6r7
Revises: m2n3o4p5q6
Create Date: 2026-02-18

"""
from alembic import op
import sqlalchemy as sa


revision = 'n3o4p5q6r7'
down_revision = 'm2n3o4p5q6'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('direction', schema=None) as batch_op:
        batch_op.add_column(sa.Column('name_uz', sa.String(200), nullable=True))
        batch_op.add_column(sa.Column('name_ru', sa.String(200), nullable=True))
        batch_op.add_column(sa.Column('name_en', sa.String(200), nullable=True))
        batch_op.add_column(sa.Column('description_uz', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('description_ru', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('description_en', sa.Text(), nullable=True))
    op.execute(sa.text("UPDATE direction SET name_uz = name WHERE name IS NOT NULL AND name != ''"))
    op.execute(sa.text("UPDATE direction SET description_uz = description WHERE description IS NOT NULL AND description != ''"))


def downgrade():
    with op.batch_alter_table('direction', schema=None) as batch_op:
        batch_op.drop_column('description_en')
        batch_op.drop_column('description_ru')
        batch_op.drop_column('description_uz')
        batch_op.drop_column('name_en')
        batch_op.drop_column('name_ru')
        batch_op.drop_column('name_uz')
