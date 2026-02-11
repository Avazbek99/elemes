"""Bazaga superadmin_flag ustunini qo'shish (migratsiya ilovani yuklamasdan).
Ishlatish: python add_superadmin_flag_column.py
Bundan keyin run.py yoki flask db upgrade ishlashi kerak.
"""
import os
import sqlite3

INSTANCE_PATH = os.path.join(os.path.dirname(__file__), 'instance')
DB_PATH = os.path.join(INSTANCE_PATH, 'eduspace.db')
REVISION = 'd4e5f6a7b8c9'

def main():
    if not os.path.isfile(DB_PATH):
        print(f'Baza topilmadi: {DB_PATH}')
        return
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(user)")
    columns = [row[1] for row in cur.fetchall()]
    if 'superadmin_flag' in columns:
        print("superadmin_flag ustuni allaqachon mavjud.")
        conn.close()
        return
    cur.execute("ALTER TABLE user ADD COLUMN superadmin_flag INTEGER")
    conn.commit()
    cur.execute("SELECT version_num FROM alembic_version")
    row = cur.fetchone()
    if row:
        cur.execute("UPDATE alembic_version SET version_num = ?", (REVISION,))
    else:
        cur.execute("INSERT INTO alembic_version (version_num) VALUES (?)", (REVISION,))
    conn.commit()
    conn.close()
    print("superadmin_flag ustuni qo'shildi va migratsiya versiyasi yangilandi.")

if __name__ == '__main__':
    main()
