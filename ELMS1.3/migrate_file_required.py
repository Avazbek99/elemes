import sqlite3
import os

# Database faylini topish
db_path = os.path.join(os.path.dirname(__file__), 'instance', 'eduspace.db')
if not os.path.exists(db_path):
    db_path = os.path.join(os.path.dirname(__file__), 'eduspace.db')

if not os.path.exists(db_path):
    print("❌ Database fayli topilmadi!")
    exit(1)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

try:
    # file_required maydonini qo'shish
    cursor.execute("ALTER TABLE assignment ADD COLUMN file_required BOOLEAN DEFAULT 0")
    cursor.execute("UPDATE assignment SET file_required = 0 WHERE file_required IS NULL")
    conn.commit()
    print("✅ file_required maydoni muvaffaqiyatli qo'shildi!")
    print("   Mavjud barcha topshiriqlar uchun fayl yuklash ixtiyoriy bo'lib belgilandi.")
except sqlite3.OperationalError as e:
    if "duplicate column name: file_required" in str(e):
        print("ℹ️ file_required maydoni allaqachon mavjud. O'tkazib yuborildi.")
    else:
        print(f"❌ Xatolik yuz berdi: {e}")
finally:
    conn.close()

