"""
Ma'lumotlar bazasiga lesson_type maydonini qo'shish uchun migration script
"""
import sqlite3
import os

# Ma'lumotlar bazasi fayl yo'li
db_path = 'instance/eduspace.db'

if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # lesson jadvalida lesson_type maydoni bor-yo'qligini tekshirish
        cursor.execute("PRAGMA table_info(lesson)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'lesson_type' not in columns:
            # lesson_type maydonini qo'shish
            cursor.execute("ALTER TABLE lesson ADD COLUMN lesson_type VARCHAR(20) DEFAULT 'maruza'")
            conn.commit()
            print("✅ lesson_type maydoni muvaffaqiyatli qo'shildi!")
            print("   Mavjud barcha darslar 'maruza' sifatida belgilandi.")
        else:
            print("ℹ️  lesson_type maydoni allaqachon mavjud.")
            
    except sqlite3.Error as e:
        print(f"❌ Xatolik: {e}")
    finally:
        conn.close()
else:
    print(f"ℹ️  Ma'lumotlar bazasi fayli ({db_path}) topilmadi.")
    print("   Ilovani birinchi marta ishga tushirganda avtomatik yaratiladi.")

