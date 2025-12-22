#!/usr/bin/env python3
"""
User jadvalida email maydonini nullable qilish
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
    print("Email maydonini nullable qilish...")
    
    # Avval email maydoni nullable ekanligini tekshirish
    cursor.execute("PRAGMA table_info(user)")
    columns = cursor.fetchall()
    email_col = [c for c in columns if c[1] == 'email']
    
    if email_col and email_col[0][3] == 0:  # NOT NULL
        print("Email maydoni NOT NULL. Yangilash kerak...")
        # SQLite'da ALTER TABLE ... ALTER COLUMN qo'llab-quvvatlanmaydi
        # Shuning uchun yangi jadval yaratamiz
        cursor.execute("""
            CREATE TABLE user_new (
                id INTEGER PRIMARY KEY,
                email VARCHAR(120),
                login VARCHAR(50) UNIQUE,
                password_hash VARCHAR(256) NOT NULL,
                full_name VARCHAR(100) NOT NULL,
                role VARCHAR(20) NOT NULL DEFAULT 'student',
                is_active BOOLEAN DEFAULT 1,
                created_at DATETIME,
                last_login DATETIME,
                phone VARCHAR(20),
                student_id VARCHAR(20) UNIQUE,
                group_id INTEGER,
                enrollment_year INTEGER,
                semester INTEGER DEFAULT 1,
                passport_number VARCHAR(20),
                pinfl VARCHAR(14),
                birth_date DATE,
                specialty VARCHAR(200),
                specialty_code VARCHAR(50),
                education_type VARCHAR(50),
                department VARCHAR(100),
                position VARCHAR(50),
                faculty_id INTEGER,
                description TEXT,
                FOREIGN KEY (group_id) REFERENCES group(id),
                FOREIGN KEY (faculty_id) REFERENCES faculty(id)
            )
        """)
        
        # Ma'lumotlarni ko'chirish
        cursor.execute("""
            INSERT INTO user_new 
            SELECT * FROM user
        """)
        
        # Eski jadvalni o'chirish
        cursor.execute("DROP TABLE user")
        
        # Yangi jadvalni qayta nomlash
        cursor.execute("ALTER TABLE user_new RENAME TO user")
        
        # Indexlarni qayta yaratish
        cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_user_email ON user(email)")
        cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_user_login ON user(login)")
        cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_user_student_id ON user(student_id)")
        
        conn.commit()
        print("✅ Email maydoni muvaffaqiyatli nullable qilindi!")
    else:
        print("✅ Email maydoni allaqachon nullable.")
    
    conn.close()
    print("Migration yakunlandi.")
    
except Exception as e:
    print(f"❌ Xatolik: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

