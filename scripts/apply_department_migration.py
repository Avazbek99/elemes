"""Department migratsiyasini qo'lda qo'llash (flask yuklanmasdan)"""
import sqlite3
import os

# instance/eduspace.db
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE, 'instance', 'eduspace.db')

def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    try:
        # department jadvali bormi?
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='department'")
        if cur.fetchone():
            print("department jadvali allaqachon mavjud.")
        else:
            cur.execute("""
                CREATE TABLE department (
                    id INTEGER NOT NULL PRIMARY KEY,
                    name VARCHAR(200) NOT NULL,
                    description TEXT,
                    created_at DATETIME
                )
            """)
            print("department jadvali yaratildi.")

        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='teacher_department'")
        if cur.fetchone():
            print("teacher_department jadvali allaqachon mavjud.")
        else:
            cur.execute("""
                CREATE TABLE teacher_department (
                    id INTEGER NOT NULL PRIMARY KEY,
                    teacher_id INTEGER NOT NULL REFERENCES user(id),
                    department_id INTEGER NOT NULL REFERENCES department(id),
                    created_at DATETIME
                )
            """)
            print("teacher_department jadvali yaratildi.")

        # subject jadvalida department_id ustuni
        cur.execute("PRAGMA table_info(subject)")
        cols = [r[1] for r in cur.fetchall()]
        if 'department_id' not in cols:
            cur.execute("ALTER TABLE subject ADD COLUMN department_id INTEGER REFERENCES department(id)")
            print("subject.department_id qo'shildi.")
        else:
            print("subject.department_id allaqachon mavjud.")

        # user jadvalida managed_department_id ustuni
        cur.execute("PRAGMA table_info(user)")
        cols = [r[1] for r in cur.fetchall()]
        if 'managed_department_id' not in cols:
            cur.execute("ALTER TABLE user ADD COLUMN managed_department_id INTEGER REFERENCES department(id)")
            print("user.managed_department_id qo'shildi.")
        else:
            print("user.managed_department_id allaqachon mavjud.")

        # alembic_version ga g6h7i8j9k0 qo'shish (b5c831920202 dan keyin)
        cur.execute("SELECT version_num FROM alembic_version")
        ver = cur.fetchone()
        if ver and ver[0] == 'b5c831920202':
            cur.execute("UPDATE alembic_version SET version_num='g6h7i8j9k0'")
            print("alembic_version yangilandi.")
        elif ver and ver[0] != 'g6h7i8j9k0':
            print(f"alembic_version: {ver[0]} (g6h7i8j9k0 qo'llanmagan bo'lishi mumkin)")

        conn.commit()
        print("Migratsiya muvaffaqiyatli qo'llandi.")
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

if __name__ == '__main__':
    main()
