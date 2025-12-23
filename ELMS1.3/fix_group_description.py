import sqlite3
import os

db_path = os.path.join('ELMS1.3', 'instance', 'eduspace.db')
if not os.path.exists(db_path):
    db_path = os.path.join('ELMS1.3', 'eduspace.db')

if not os.path.exists(db_path):
    print("Database topilmadi")
    exit(1)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

try:
    cursor.execute('PRAGMA table_info("group")')
    cols = [c[1] for c in cursor.fetchall()]
    print('Columns:', cols)
    
    if 'description' not in cols:
        cursor.execute('ALTER TABLE "group" ADD COLUMN description TEXT')
        conn.commit()
        print('✅ description maydoni qo\'shildi')
    else:
        print('ℹ️ description allaqachon mavjud')
except Exception as e:
    print(f'Xatolik: {e}')
finally:
    conn.close()

