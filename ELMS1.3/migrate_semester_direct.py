"""
Migration script: Semester ustunini qo'shish va barcha mavjud talabalarga semester=1 ni belgilash
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
    # Avval semester ustunini tekshirish
    cursor.execute("PRAGMA table_info(user)")
    columns = [col[1] for col in cursor.fetchall()]
    
    if 'semester' not in columns:
        print("Semester ustuni mavjud emas. Qo'shilmoqda...")
        # SQLite'da ALTER TABLE bilan yangi ustun qo'shish
        cursor.execute("ALTER TABLE user ADD COLUMN semester INTEGER DEFAULT 1")
        conn.commit()
        print("Semester ustuni qo'shildi.")
    else:
        print("Semester ustuni allaqachon mavjud.")
    
    # Barcha talabalarga semester=1 ni belgilash
    cursor.execute("""
        UPDATE user 
        SET semester = 1 
        WHERE role = 'student' AND (semester IS NULL OR semester = 0)
    """)
    
    updated_count = cursor.rowcount
    
    # Barcha talabalarga semester=1 ni belgilash (agar semester None bo'lsa)
    cursor.execute("""
        UPDATE user 
        SET semester = 1 
        WHERE role = 'student' AND semester IS NULL
    """)
    
    updated_count += cursor.rowcount
    conn.commit()
    
    print(f"Muvaffaqiyatli! {updated_count} ta talabaga semester=1 belgilandi.")
    
except Exception as e:
    conn.rollback()
    print(f"Xatolik: {e}")
    import traceback
    traceback.print_exc()
    exit(1)
finally:
    conn.close()

