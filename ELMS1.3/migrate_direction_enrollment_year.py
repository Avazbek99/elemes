#!/usr/bin/env python3
"""
Direction jadvaliga enrollment_year maydonini qo'shish va DirectionCurriculum jadvalini yaratish
"""
import sqlite3
import os
import sys

# Database fayl yo'li
script_dir = os.path.dirname(os.path.abspath(__file__))
possible_paths = [
    os.path.join(script_dir, 'instance', 'eduspace.db'),
    os.path.join(script_dir, 'ELMS1.3', 'instance', 'eduspace.db'),
    os.path.join(os.path.dirname(script_dir), 'instance', 'eduspace.db'),
    os.path.join(os.path.dirname(script_dir), 'ELMS1.3', 'instance', 'eduspace.db'),
    'instance/eduspace.db',
    'ELMS1.3/instance/eduspace.db'
]

db_path = None
for path in possible_paths:
    abs_path = os.path.abspath(path)
    if os.path.exists(abs_path):
        db_path = abs_path
        print(f"Database topildi: {db_path}")
        break

if not db_path:
    print(f"Database fayl topilmadi. Qidirilgan yo'llar:")
    for path in possible_paths:
        print(f"  - {os.path.abspath(path)}")
    sys.exit(1)

try:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print("Migration boshlandi...")
    
    # 1. Direction jadvaliga enrollment_year maydonini qo'shish
    print("\n1. Direction jadvaliga enrollment_year maydonini qo'shish...")
    cursor.execute("PRAGMA table_info(direction)")
    columns = cursor.fetchall()
    column_names = [col[1] for col in columns]
    
    if 'enrollment_year' not in column_names:
        print("  enrollment_year maydoni yo'q. Qo'shilyapti...")
        cursor.execute("ALTER TABLE direction ADD COLUMN enrollment_year INTEGER")
        print("  enrollment_year maydoni qo'shildi!")
    else:
        print("  enrollment_year maydoni allaqachon mavjud!")
    
    # 2. DirectionCurriculum jadvalini yaratish
    print("\n2. DirectionCurriculum jadvalini yaratish...")
    cursor.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name='direction_curriculum'
    """)
    table_exists = cursor.fetchone()
    
    if not table_exists:
        print("  DirectionCurriculum jadvali yo'q. Yaratilmoqda...")
        cursor.execute("""
            CREATE TABLE direction_curriculum (
                id INTEGER PRIMARY KEY,
                direction_id INTEGER NOT NULL,
                subject_id INTEGER NOT NULL,
                semester INTEGER NOT NULL,
                hours_maruza INTEGER DEFAULT 0,
                hours_amaliyot INTEGER DEFAULT 0,
                hours_laboratoriya INTEGER DEFAULT 0,
                hours_seminar INTEGER DEFAULT 0,
                hours_kurs_ishi INTEGER DEFAULT 0,
                hours_mustaqil INTEGER DEFAULT 0,
                created_at DATETIME,
                FOREIGN KEY (direction_id) REFERENCES direction(id),
                FOREIGN KEY (subject_id) REFERENCES subject(id),
                UNIQUE(direction_id, subject_id, semester)
            )
        """)
        print("  DirectionCurriculum jadvali yaratildi!")
    else:
        print("  DirectionCurriculum jadvali allaqachon mavjud!")
    
    conn.commit()
    print("\nMigration muvaffaqiyatli yakunlandi!")
    
    conn.close()
    
except Exception as e:
    print(f"\nXatolik: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
