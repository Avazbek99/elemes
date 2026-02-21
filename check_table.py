import sqlite3

conn = sqlite3.connect('instance/elms.db')
cur = conn.cursor()

# subject_department jadvalini tekshirish
cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='subject_department'")
result = cur.fetchall()
if result:
    print("subject_department jadvali MAVJUD")
else:
    print("subject_department jadvali MAVJUD EMAS")

# Barcha jadvallarni ko'rish
cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
tables = cur.fetchall()
print("\nBarcha jadvallar:")
for t in tables:
    print(f"  - {t[0]}")

conn.close()
