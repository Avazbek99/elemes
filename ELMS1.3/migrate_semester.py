"""
Migration script: Semester ustunini qo'shish va barcha mavjud talabalarga semester=1 ni belgilash
"""
import sqlite3
import os
import sys

print("Migration script ishga tushmoqda...")

# Config'dan database URI ni olish (Flask app yaratmasdan)
sys.path.insert(0, os.path.dirname(__file__))
try:
    from config import Config
    print("Config import qilindi.")
except Exception as e:
    print(f"Config import xatosi: {e}")
    sys.exit(1)

config = Config()
db_uri = config.SQLALCHEMY_DATABASE_URI
print(f"Database URI: {db_uri}")

# sqlite:///eduspace.db formatidan fayl yo'lini ajratish
if db_uri.startswith('sqlite:///'):
    db_filename = db_uri.replace('sqlite:///', '')
    print(f"Database fayl nomi: {db_filename}")
    
    # Turli joylarni tekshirish
    script_dir = os.path.dirname(os.path.abspath(__file__))
    current_dir = os.getcwd()
    possible_paths = [
        os.path.join(script_dir, 'instance', db_filename),  # ELMS1.3/instance/eduspace.db
        os.path.join(script_dir, db_filename),  # ELMS1.3/eduspace.db
        os.path.join(current_dir, 'ELMS1.3', 'instance', db_filename),  # D:\Ish\Platforma\ELMS1.3\ELMS1.3\instance\eduspace.db
        os.path.join(current_dir, db_filename),  # current_dir/eduspace.db
        r'D:\Ish\Platforma\ELMS1.3\ELMS1.3\instance\eduspace.db',  # To'g'ridan-to'g'ri ma'lum yo'l
    ]
    
    print("Quyidagi yo'llarni tekshiryapman:")
    for path in possible_paths:
        exists = os.path.exists(path)
        print(f"  - {path} {'[TOPILDI]' if exists else '[TOPILMADI]'}")
    
    db_path = None
    for path in possible_paths:
        if os.path.exists(path):
            db_path = path
            break
    
    if not db_path:
        print(f"\nXatolik: Database fayl topilmadi!")
        sys.exit(1)

print(f"\nDatabase fayl topildi: {db_path}")

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
    
    # Barcha talabalarga semester=1 ni belgilash (agar semester None yoki 0 bo'lsa)
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
    sys.exit(1)
finally:
    conn.close()

