"""Drop unique constraint from direction_contract_amount to allow multiple per year

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-02-05

"""
from alembic import op


revision = 'b2c3d4e5f6a7'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('direction_contract_amount', schema=None) as batch_op:
        batch_op.drop_constraint('uq_direction_contract_year_type', type_='unique')


def downgrade():
    with op.batch_alter_table('direction_contract_amount', schema=None) as batch_op:
        batch_op.create_unique_constraint(
            'uq_direction_contract_year_type',
            ['direction_id', 'enrollment_year', 'education_type']
        )
