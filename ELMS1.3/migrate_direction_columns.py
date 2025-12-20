import sqlite3
import os
import sys

# Database faylini topish
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
    # direction jadvalining ustunlarini tekshirish
    cursor.execute("PRAGMA table_info(direction)")
    columns = [col[1] for col in cursor.fetchall()]
    
    # course_year ustunini qo'shish
    if 'course_year' not in columns:
        print("course_year ustuni mavjud emas. Qo'shilmoqda...")
        cursor.execute("ALTER TABLE direction ADD COLUMN course_year INTEGER DEFAULT 1")
        print("course_year ustuni qo'shildi.")
    else:
        print("course_year ustuni allaqachon mavjud.")
    
    # semester ustunini qo'shish
    if 'semester' not in columns:
        print("semester ustuni mavjud emas. Qo'shilmoqda...")
        cursor.execute("ALTER TABLE direction ADD COLUMN semester INTEGER DEFAULT 1")
        print("semester ustuni qo'shildi.")
    else:
        print("semester ustuni allaqachon mavjud.")
    
    # Mavjud yo'nalishlarga default qiymatlar berish
    cursor.execute("""
        UPDATE direction
        SET course_year = 1
        WHERE course_year IS NULL
    """)
    
    cursor.execute("""
        UPDATE direction
        SET semester = 1
        WHERE semester IS NULL
    """)
    
    conn.commit()
    
    print(f"Muvaffaqiyatli! Barcha yo'nalishlarga course_year=1 va semester=1 belgilandi.")

except Exception as e:
    conn.rollback()
    print(f"Xatolik: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
finally:
    conn.close()

