"""
Ma'lumotlar bazasiga group jadvaliga description maydonini qo'shish uchun migration script
"""
import sqlite3
import os

# Ma'lumotlar bazasi fayl yo'li
db_path = os.path.join(os.path.dirname(__file__), 'instance', 'eduspace.db')
if not os.path.exists(db_path):
    db_path = os.path.join(os.path.dirname(__file__), 'eduspace.db')

if not os.path.exists(db_path):
    print("❌ Database fayli topilmadi!")
    exit(1)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

try:
    # Avval jadval nomlarini olish
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='group'")
    table_exists = cursor.fetchone()
    
    if not table_exists:
        print("❌ group jadvali topilmadi!")
        exit(1)
    
    # group jadvalida description maydoni bor-yo'qligini tekshirish
    # SQLite'da group kalit so'z bo'lgani uchun, uni qo'shtirnoq ichiga olish kerak
    cursor.execute('PRAGMA table_info("group")')
    columns = [column[1] for column in cursor.fetchall()]
    
    print(f"Jadval ustunlari: {columns}")
    
    if 'description' not in columns:
        # description maydonini qo'shish
        cursor.execute('ALTER TABLE "group" ADD COLUMN description TEXT')
        conn.commit()
        print("✅ description maydoni muvaffaqiyatli qo'shildi!")
        print("   group jadvaliga description maydoni qo'shildi.")
    else:
        print("ℹ️  description maydoni allaqachon mavjud.")
        
except sqlite3.Error as e:
    print(f"❌ Xatolik: {e}")
    import traceback
    traceback.print_exc()
finally:
    conn.close()

