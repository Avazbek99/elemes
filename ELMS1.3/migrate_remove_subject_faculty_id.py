#!/usr/bin/env python3
"""
Migration script: Subject jadvalidan faculty_id ustunini olib tashlash
"""

import sqlite3
import sys
import os

# Database fayl yo'li
db_path = os.path.join(os.path.dirname(__file__), 'instance', 'database.db')

if not os.path.exists(db_path):
    print(f"Xatolik: Database fayl topilmadi: {db_path}")
    print("Iltimos, avval Flask ilovasini ishga tushiring va database yarating.")
    sys.exit(1)

try:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print("Subject jadvalidan faculty_id ustunini olib tashlash...")
    
    # Avval faculty_id ustuni mavjudligini tekshirish
    cursor.execute("PRAGMA table_info(subject)")
    columns = cursor.fetchall()
    faculty_id_exists = any(c[1] == 'faculty_id' for c in columns)
    
    if not faculty_id_exists:
        print("faculty_id ustuni mavjud emas. Migration kerak emas.")
        conn.close()
        sys.exit(0)
    
    # Foreign key constraint'larni o'chirish
    cursor.execute("PRAGMA foreign_keys=OFF")
    
    # Yangi jadval yaratish (faculty_id ustunisiz)
    cursor.execute("""
        CREATE TABLE subject_new (
            id INTEGER PRIMARY KEY,
            name VARCHAR(200) NOT NULL,
            code VARCHAR(20) NOT NULL,
            description TEXT,
            credits INTEGER DEFAULT 3,
            semester INTEGER DEFAULT 1,
            created_at DATETIME
        )
    """)
    
    # Ma'lumotlarni ko'chirish (faculty_id ni o'tkazib yuborish)
    cursor.execute("""
        INSERT INTO subject_new (id, name, code, description, credits, semester, created_at)
        SELECT id, name, code, description, credits, semester, created_at
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
    print("  - faculty_id ustuni olib tashlandi")
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
    if conn:
        conn.rollback()
        conn.close()
    sys.exit(1)
