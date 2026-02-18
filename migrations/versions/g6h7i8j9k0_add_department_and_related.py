"""add department and related

Revision ID: g6h7i8j9k0
Revises: b5c831920202
Create Date: 2026-02-11

"""
from alembic import op
import sqlalchemy as sa


revision = 'g6h7i8j9k0'
down_revision = 'b5c831920202'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('department',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_table('teacher_department',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('teacher_id', sa.Integer(), nullable=False),
        sa.Column('department_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['department_id'], ['department.id'], ),
        sa.ForeignKeyConstraint(['teacher_id'], ['user.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('subject', schema=None) as batch_op:
        batch_op.add_column(sa.Column('department_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_subject_department', 'department', ['department_id'], ['id'])
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.add_column(sa.Column('managed_department_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_user_managed_department', 'department', ['managed_department_id'], ['id'])


def downgrade():
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.drop_constraint('fk_user_managed_department', type_='foreignkey')
        batch_op.drop_column('managed_department_id')
    with op.batch_alter_table('subject', schema=None) as batch_op:
        batch_op.drop_constraint('fk_subject_department', type_='foreignkey')
        batch_op.drop_column('department_id')
    op.drop_table('teacher_department')
    op.drop_table('department')
