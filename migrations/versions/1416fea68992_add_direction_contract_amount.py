"""add_direction_contract_amount

Revision ID: 1416fea68992
Revises: 7e821dc4bbf5
Create Date: 2026-02-04 17:56:48.773254

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '1416fea68992'
down_revision = '7e821dc4bbf5'
branch_labels = None
depends_on = None


def upgrade():
    from sqlalchemy.engine.reflection import Inspector
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    if 'direction_contract_amount' in inspector.get_table_names():
        return
    op.create_table('direction_contract_amount',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('direction_id', sa.Integer(), nullable=False),
        sa.Column('enrollment_year', sa.Integer(), nullable=False),
        sa.Column('education_type', sa.String(20), nullable=True),
        sa.Column('contract_amount', sa.Numeric(15, 2), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['direction_id'], ['direction.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('direction_id', 'enrollment_year', 'education_type', name='uq_direction_contract_year_type')
    )


def downgrade():
    op.drop_table('direction_contract_amount')
