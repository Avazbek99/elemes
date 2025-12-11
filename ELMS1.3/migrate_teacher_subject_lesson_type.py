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
    # lesson_type maydonini qo'shish
    cursor.execute("ALTER TABLE teacher_subject ADD COLUMN lesson_type VARCHAR(20) DEFAULT 'maruza'")
    cursor.execute("UPDATE teacher_subject SET lesson_type = 'maruza' WHERE lesson_type IS NULL")
    conn.commit()
    print("✅ lesson_type maydoni muvaffaqiyatli qo'shildi!")
    print("   Mavjud barcha o'qituvchi biriktirishlar 'maruza' sifatida belgilandi.")
except sqlite3.OperationalError as e:
    if "duplicate column name: lesson_type" in str(e):
        print("ℹ️ lesson_type maydoni allaqachon mavjud. O'tkazib yuborildi.")
    else:
        print(f"❌ Xatolik yuz berdi: {e}")
finally:
    conn.close()

