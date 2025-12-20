import sqlite3
import os
import sys

script_dir = os.path.dirname(os.path.abspath(__file__))
possible_paths = [
    os.path.join(script_dir, 'instance', 'eduspace.db'),
    os.path.join(script_dir, 'eduspace.db'),
    os.path.join(script_dir, 'instance', 'database.db'),
]

db_path = None
for path in possible_paths:
    if os.path.exists(path):
        db_path = path
        break

if not db_path:
    print(f"Database fayl topilmadi. Quyidagi joylarni tekshirdim:")
    for path in possible_paths:
        print(f"  - {path}")
    print(f"\nHozirgi papka: {script_dir}")
    sys.exit(1)

print(f"Database fayl topildi: {db_path}")

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

try:
    cursor.execute("PRAGMA table_info(direction)")
    columns = [col[1] for col in cursor.fetchall()]

    if 'education_type' not in columns:
        print("education_type ustuni mavjud emas. Qo'shilmoqda...")
        cursor.execute("ALTER TABLE direction ADD COLUMN education_type VARCHAR(20) DEFAULT 'kunduzgi' NOT NULL")
        print("education_type ustuni qo'shildi.")
    else:
        print("education_type ustuni allaqachon mavjud.")

    # Barcha yo'nalishlarga default qiymatni belgilash
    cursor.execute("""
        UPDATE direction
        SET education_type = 'kunduzgi'
        WHERE education_type IS NULL OR education_type = ''
    """)

    conn.commit()

    print(f"Muvaffaqiyatli! Barcha yo'nalishlarga education_type='kunduzgi' belgilandi.")

except Exception as e:
    conn.rollback()
    print(f"Xatolik: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
finally:
    conn.close()

