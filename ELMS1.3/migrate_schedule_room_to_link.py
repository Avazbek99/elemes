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
    # link maydonini qo'shish
    cursor.execute("ALTER TABLE schedule ADD COLUMN link VARCHAR(500)")
    
    # room maydonidagi ma'lumotlarni link ga ko'chirish (agar room bo'lsa)
    cursor.execute("UPDATE schedule SET link = room WHERE room IS NOT NULL AND room != ''")
    
    # room maydonini o'chirish (SQLite'da ALTER TABLE DROP COLUMN qo'llab-quvvatlanmaydi, shuning uchun yangi jadval yaratamiz)
    # Lekin bu murakkab, shuning uchun faqat link qo'shamiz va room ni ishlatmaymiz
    conn.commit()
    print("✅ link maydoni muvaffaqiyatli qo'shildi!")
    print("   Mavjud room ma'lumotlari link ga ko'chirildi.")
    print("   ⚠️  Eslatma: room maydoni hali ham jadvalda qoladi, lekin ishlatilmaydi.")
except sqlite3.OperationalError as e:
    if "duplicate column name: link" in str(e):
        print("ℹ️ link maydoni allaqachon mavjud. O'tkazib yuborildi.")
    else:
        print(f"❌ Xatolik yuz berdi: {e}")
finally:
    conn.close()

