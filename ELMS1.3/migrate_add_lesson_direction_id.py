"""
Migration script: Lesson jadvaliga direction_id qo'shish
"""
import sqlite3
import os

# Database fayl yo'li
db_path = os.path.join(os.path.dirname(__file__), 'instance', 'eduspace.db')

if not os.path.exists(db_path):
    print(f"Database fayl topilmadi: {db_path}")
    exit(1)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

try:
    # direction_id ustunini qo'shish
    cursor.execute("""
        ALTER TABLE lesson 
        ADD COLUMN direction_id INTEGER REFERENCES direction(id)
    """)
    
    conn.commit()
    print("direction_id ustuni muvaffaqiyatli qo'shildi!")
    
    # Mavjud darslar uchun direction_id ni guruh orqali to'ldirish
    cursor.execute("""
        UPDATE lesson 
        SET direction_id = (
            SELECT group.direction_id 
            FROM "group" 
            WHERE "group".id = lesson.group_id
        )
        WHERE group_id IS NOT NULL
    """)
    
    conn.commit()
    print("Mavjud darslar uchun direction_id to'ldirildi!")
    
except sqlite3.OperationalError as e:
    if "duplicate column name" in str(e).lower():
        print("direction_id ustuni allaqachon mavjud")
    else:
        print(f"Xatolik: {e}")
        conn.rollback()
finally:
    conn.close()
    print("Migration yakunlandi!")
