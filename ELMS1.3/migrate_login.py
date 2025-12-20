"""
Migration: User jadvaliga login ustunini qo'shish
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
    
    # Login ustunini tekshirish
    print("   📋 Login ustunini tekshirish...")
    cursor.execute("PRAGMA table_info(user)")
    columns = [column[1] for column in cursor.fetchall()]
    
    if 'login' not in columns:
        print("   📋 Login ustunini qo'shish...")
        # SQLite'da ALTER TABLE bilan yangi ustun qo'shish
        try:
            cursor.execute("ALTER TABLE user ADD COLUMN login VARCHAR(50)")
            conn.commit()
            print("   ✅ Login ustuni qo'shildi")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower() or "already exists" in str(e).lower() or "duplicate" in str(e).lower():
                print("   ⚠️  Login ustuni allaqachon mavjud")
            else:
                raise
    else:
        print("   ⚠️  Login ustuni allaqachon mavjud")
    
    print("✅ Migration muvaffaqiyatli yakunlandi!")
    
except Exception as e:
    conn.rollback()
    print(f"❌ Xato: {e}")
    raise
finally:
    conn.close()
