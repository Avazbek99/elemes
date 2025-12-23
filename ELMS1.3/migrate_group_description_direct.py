"""
Migration script: group jadvaliga description ustunini qo'shish
To'g'ridan-to'g'ri database fayliga ulanadi
"""
import sqlite3
import os

# Ma'lum database yo'li
db_path = r'D:\Ish\Platforma\ELMS1.3\ELMS1.3\instance\eduspace.db'

print(f"Database fayl: {db_path}")

if not os.path.exists(db_path):
    print(f"Xatolik: Database fayl topilmadi: {db_path}")
    exit(1)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

try:
    # Avval description ustunini tekshirish
    cursor.execute('PRAGMA table_info("group")')
    columns = [col[1] for col in cursor.fetchall()]
    
    print(f"Jadval ustunlari: {columns}")
    
    if 'description' not in columns:
        print("description ustuni mavjud emas. Qo'shilmoqda...")
        # SQLite'da ALTER TABLE bilan yangi ustun qo'shish
        cursor.execute('ALTER TABLE "group" ADD COLUMN description TEXT')
        conn.commit()
        print("✅ description ustuni qo'shildi.")
    else:
        print("ℹ️  description ustuni allaqachon mavjud.")
    
except Exception as e:
    conn.rollback()
    print(f"Xatolik: {e}")
    import traceback
    traceback.print_exc()
    exit(1)
finally:
    conn.close()

