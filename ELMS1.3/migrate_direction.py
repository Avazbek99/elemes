"""
Migration: Direction modeli va Group.direction_id maydoni qo'shish
"""
import sqlite3
import os

# Ma'lumotlar bazasi yo'li
db_path = os.path.join(os.path.dirname(__file__), 'instance', 'eduspace.db')

if not os.path.exists(db_path):
    print(f"❌ Ma'lumotlar bazasi topilmadi: {db_path}")
    exit(1)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

try:
    print("🔄 Migration boshlandi...")
    
    # 1. Direction jadvalini yaratish
    print("   📋 Direction jadvalini yaratish...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS direction (
            id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
            name VARCHAR(200) NOT NULL,
            code VARCHAR(20) NOT NULL,
            description TEXT,
            faculty_id INTEGER NOT NULL,
            created_at DATETIME,
            FOREIGN KEY(faculty_id) REFERENCES faculty (id)
        )
    """)
    print("   ✅ Direction jadvali yaratildi")
    
    # 2. Group jadvaliga direction_id maydonini qo'shish
    print("   📋 Group jadvaliga direction_id maydonini qo'shish...")
    
    # SQLite'da ALTER TABLE ADD COLUMN qo'llab-quvvatlanadi
    try:
        cursor.execute("ALTER TABLE \"group\" ADD COLUMN direction_id INTEGER")
        print("   ✅ direction_id maydoni qo'shildi")
        # SQLite'da ALTER TABLE bilan FOREIGN KEY constraint qo'shib bo'lmaydi
        # Lekin bu maydon ishlaydi, faqat referential integrity check qilmaydi
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e).lower() or "already exists" in str(e).lower() or "duplicate" in str(e).lower():
            print("   ⚠️  direction_id maydoni allaqachon mavjud")
        else:
            raise
    
    conn.commit()
    print("✅ Migration muvaffaqiyatli yakunlandi!")
    
except Exception as e:
    conn.rollback()
    print(f"❌ Xato: {e}")
    raise
finally:
    conn.close()

