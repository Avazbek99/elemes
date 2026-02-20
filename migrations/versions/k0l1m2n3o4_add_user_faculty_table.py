"""add user_faculty table (one user can be linked to multiple faculties)

Revision ID: k0l1m2n3o4
Revises: j9k0l1m2n3
Create Date: 2026-02-18

"""
from alembic import op
import sqlalchemy as sa


revision = 'k0l1m2n3o4'
down_revision = 'j9k0l1m2n3'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    # Idempotent: skip if table already exists (e.g. created manually or previous partial run)
    if conn.dialect.name == 'sqlite':
        r = conn.execute(sa.text("SELECT 1 FROM sqlite_master WHERE type='table' AND name='user_faculty'"))
        if r.fetchone():
            # Table exists; only run data migration if needed
            try:
                r2 = conn.execute(sa.text("SELECT id, faculty_id FROM user WHERE faculty_id IS NOT NULL"))
                for row in r2:
                    uid, fid = row[0], row[1]
                    conn.execute(sa.text("INSERT OR IGNORE INTO user_faculty (user_id, faculty_id, created_at) VALUES (:u, :f, datetime('now'))"), {"u": uid, "f": fid})
            except Exception:
                pass
            return
    else:
        from sqlalchemy import inspect
        insp = inspect(conn)
        if 'user_faculty' in insp.get_table_names():
            return

    op.create_table(
        'user_faculty',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('faculty_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ),
        sa.ForeignKeyConstraint(['faculty_id'], ['faculty.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'faculty_id', name='uq_user_faculty_user_faculty')
    )
    op.create_index(op.f('ix_user_faculty_user_id'), 'user_faculty', ['user_id'], unique=False)
    op.create_index(op.f('ix_user_faculty_faculty_id'), 'user_faculty', ['faculty_id'], unique=False)

    # Migrate existing user.faculty_id -> user_faculty row
    try:
        r = conn.execute(sa.text("SELECT id, faculty_id FROM user WHERE faculty_id IS NOT NULL"))
        for row in r:
            uid, fid = row[0], row[1]
            conn.execute(sa.text("INSERT OR IGNORE INTO user_faculty (user_id, faculty_id, created_at) VALUES (:u, :f, datetime('now'))"), {"u": uid, "f": fid})
    except Exception:
        pass


def downgrade():
    op.drop_index(op.f('ix_user_faculty_faculty_id'), table_name='user_faculty')
    op.drop_index(op.f('ix_user_faculty_user_id'), table_name='user_faculty')
    op.drop_table('user_faculty')
