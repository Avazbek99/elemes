#!/usr/bin/env python3
"""
Subject jadvalida faculty_id maydonini nullable qilish
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
    
    # SQLite'da ALTER TABLE bilan NOT NULL constraint'ni o'chirib bo'lmaydi
    # Shuning uchun yangi jadval yaratib, ma'lumotlarni ko'chirish kerak
    print("Subject jadvalida faculty_id maydonini nullable qilish...")
    
    # Avval faculty_id maydoni nullable ekanligini tekshirish
    cursor.execute("PRAGMA table_info(subject)")
    columns = cursor.fetchall()
    faculty_id_col = [c for c in columns if c[1] == 'faculty_id']
    
    if faculty_id_col and faculty_id_col[0][3] == 1:  # NOT NULL
        print("faculty_id maydoni NOT NULL. Yangilash kerak...")
        
        # Foreign key constraint'larni o'chirish
        cursor.execute("PRAGMA foreign_keys=OFF")
        
        # Yangi jadval yaratish (faculty_id nullable)
        cursor.execute("""
            CREATE TABLE subject_new (
                id INTEGER PRIMARY KEY,
                name VARCHAR(200) NOT NULL,
                code VARCHAR(20) NOT NULL,
                description TEXT,
                credits INTEGER DEFAULT 3,
                faculty_id INTEGER,
                semester INTEGER DEFAULT 1,
                created_at DATETIME,
                FOREIGN KEY (faculty_id) REFERENCES faculty(id)
            )
        """)
        
        # Ma'lumotlarni ko'chirish
        cursor.execute("""
            INSERT INTO subject_new (id, name, code, description, credits, faculty_id, semester, created_at)
            SELECT id, name, code, description, credits, faculty_id, semester, created_at
            FROM subject
        """)
        
        # Eski jadvalni o'chirish
        cursor.execute("DROP TABLE subject")
        
        # Yangi jadvalni qayta nomlash
        cursor.execute("ALTER TABLE subject_new RENAME TO subject")
        
        # Foreign key constraint'larni qayta yoqish
        cursor.execute("PRAGMA foreign_keys=ON")
        
        conn.commit()
        print("faculty_id maydoni muvaffaqiyatli nullable qilindi!")
    else:
        print("faculty_id maydoni allaqachon nullable!")
    
    conn.close()
    
except Exception as e:
    print(f"Xatolik: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
