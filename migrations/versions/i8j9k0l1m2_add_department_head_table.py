"""add department_head table (many-to-many: one user can head multiple departments)

Revision ID: i8j9k0l1m2
Revises: h7i8j9k0l1
Create Date: 2026-02-18

"""
from alembic import op
import sqlalchemy as sa


revision = 'i8j9k0l1m2'
down_revision = 'h7i8j9k0l1'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    # SQLite: jadval mavjud bo‘lsa yaratmaslik (idempotent)
    if conn.dialect.name == 'sqlite':
        r = conn.execute(sa.text("SELECT name FROM sqlite_master WHERE type='table' AND name='department_head'"))
        if r.scalar():
            # Jadval mavjud, migratsiya qatorini bitta qo‘shish
            try:
                r2 = conn.execute(sa.text("SELECT id, managed_department_id FROM user WHERE managed_department_id IS NOT NULL"))
                for row in r2:
                    uid, dept_id = row[0], row[1]
                    conn.execute(sa.text("INSERT OR IGNORE INTO department_head (department_id, user_id, created_at) VALUES (:d, :u, datetime('now'))"), {"d": dept_id, "u": uid})
            except Exception:
                pass
            return
    else:
        # PostgreSQL va boshqalar: mavjudligini tekshirish
        from sqlalchemy import inspect
        if inspect(conn).has_table('department_head'):
            return
    op.create_table(
        'department_head',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('department_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['department_id'], ['department.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('department_id', 'user_id', name='uq_department_head_dept_user')
    )
    op.create_index(op.f('ix_department_head_department_id'), 'department_head', ['department_id'], unique=False)
    op.create_index(op.f('ix_department_head_user_id'), 'department_head', ['user_id'], unique=False)

    # Migrate existing: user.managed_department_id -> department_head row
    try:
        r = conn.execute(sa.text("SELECT id, managed_department_id FROM user WHERE managed_department_id IS NOT NULL"))
        for row in r:
            uid, dept_id = row[0], row[1]
            conn.execute(sa.text("INSERT INTO department_head (department_id, user_id, created_at) VALUES (:d, :u, datetime('now'))"), {"d": dept_id, "u": uid})
    except Exception:
        pass


def downgrade():
    op.drop_index(op.f('ix_department_head_user_id'), table_name='department_head')
    op.drop_index(op.f('ix_department_head_department_id'), table_name='department_head')
    op.drop_table('department_head')
