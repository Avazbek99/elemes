#!/usr/bin/env python3
"""
Migration script: Subject jadvalidan code ustunini olib tashlash
"""

import sqlite3
import sys
import os

# Database fayl yo'li
script_dir = os.path.dirname(os.path.abspath(__file__))
possible_paths = [
    os.path.join(script_dir, 'instance', 'eduspace.db'),
    os.path.join(script_dir, 'instance', 'database.db'),
    os.path.join(script_dir, 'eduspace.db'),
]

db_path = None
for path in possible_paths:
    if os.path.exists(path):
        db_path = path
        break

if not db_path:
    print(f"Xatolik: Database fayl topilmadi!")
    print("Quyidagi joylarni tekshirdim:")
    for path in possible_paths:
        print(f"  - {path}")
    sys.exit(1)

print(f"Database fayl topildi: {db_path}")

try:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print("Subject jadvalidan code ustunini olib tashlash...")
    
    # Avval code ustuni mavjudligini tekshirish
    cursor.execute("PRAGMA table_info(subject)")
    columns = cursor.fetchall()
    code_exists = any(c[1] == 'code' for c in columns)
    
    if not code_exists:
        print("code ustuni mavjud emas. Migration kerak emas.")
        conn.close()
        sys.exit(0)
    
    # Foreign key constraint'larni o'chirish
    cursor.execute("PRAGMA foreign_keys=OFF")
    
    # Yangi jadval yaratish (code ustunisiz)
    cursor.execute("""
        CREATE TABLE subject_new (
            id INTEGER PRIMARY KEY,
            name VARCHAR(200) NOT NULL,
            description TEXT,
            credits INTEGER DEFAULT 3,
            semester INTEGER DEFAULT 1,
            created_at DATETIME
        )
    """)
    
    # Ma'lumotlarni ko'chirish (code ni o'tkazib yuborish)
    cursor.execute("""
        INSERT INTO subject_new (id, name, description, credits, semester, created_at)
        SELECT id, name, description, credits, semester, created_at
        FROM subject
    """)
    
    # Eski jadvalni o'chirish
    cursor.execute("DROP TABLE subject")
    
    # Yangi jadvalni qayta nomlash
    cursor.execute("ALTER TABLE subject_new RENAME TO subject")
    
    # Foreign key constraint'larni qayta yoqish
    cursor.execute("PRAGMA foreign_keys=ON")
    
    conn.commit()
    print("✓ Migration muvaffaqiyatli yakunlandi!")
    print("  - code ustuni olib tashlandi")
    print("  - Barcha ma'lumotlar saqlandi")
    
    conn.close()
    
except sqlite3.Error as e:
    print(f"SQLite xatolik: {e}")
    if conn:
        conn.rollback()
        conn.close()
    sys.exit(1)
except Exception as e:
    print(f"Xatolik: {e}")
    import traceback
    traceback.print_exc()
    if conn:
        conn.rollback()
        conn.close()
    sys.exit(1)
