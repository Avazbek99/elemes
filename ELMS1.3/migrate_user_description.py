#!/usr/bin/env python3
"""
User jadvaliga description maydonini qo'shish
"""
import sqlite3
import os
import sys

# Database fayl yo'li
# Bir nechta mumkin bo'lgan yo'llarni tekshirish
possible_paths = [
    os.path.join(os.path.dirname(__file__), 'instance', 'eduspace.db'),
    os.path.join(os.path.dirname(__file__), 'ELMS1.3', 'instance', 'eduspace.db'),
    'instance/eduspace.db',
    'ELMS1.3/instance/eduspace.db'
]

db_path = None
for path in possible_paths:
    if os.path.exists(path):
        db_path = path
        break

if not db_path:
    # Hali ham topilmasa, joriy papkada qidirish
    current_dir = os.getcwd()
    test_path = os.path.join(current_dir, 'instance', 'eduspace.db')
    if os.path.exists(test_path):
        db_path = test_path

if not os.path.exists(db_path):
    print(f"Database fayl topilmadi: {db_path}")
    sys.exit(1)

try:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Avval ustun mavjudligini tekshirish
    cursor.execute("PRAGMA table_info(user)")
    columns = [column[1] for column in cursor.fetchall()]
    
    if 'description' not in columns:
        print("User jadvaliga description maydonini qo'shish...")
        cursor.execute("ALTER TABLE user ADD COLUMN description TEXT")
        conn.commit()
        print("✅ Description maydoni muvaffaqiyatli qo'shildi!")
    else:
        print("✅ Description maydoni allaqachon mavjud.")
    
    conn.close()
    print("Migration yakunlandi.")
    
except Exception as e:
    print(f"❌ Xatolik: {e}")
    sys.exit(1)

