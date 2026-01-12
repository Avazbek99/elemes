#!/usr/bin/env python3
"""
Migration script: Demo topshiriqlarni o'chirish
"""

import sqlite3
import sys
import os
from datetime import datetime

# Database fayl yo'li
script_dir = os.path.dirname(os.path.abspath(__file__))
possible_paths = [
    os.path.join(script_dir, 'instance', 'eduspace.db'),
    os.path.join(script_dir, 'instance', 'database.db'),
    os.path.join(script_dir, 'eduspace.db'),
]

db_path = None
for path in possible_paths:
    if os.path.exists(path):
        db_path = path
        break

if not db_path:
    print(f"Xatolik: Database fayl topilmadi!")
    print("Quyidagi joylarni tekshirdim:")
    for path in possible_paths:
        print(f"  - {path}")
    sys.exit(1)

print(f"Database fayl topildi: {db_path}")

try:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print("Demo topshiriqlarni o'chirish...")
    
    # Demo topshiriqlarni aniqlash: "Amaliy topshiriq #" bilan boshlanadigan topshiriqlar
    cursor.execute("""
        SELECT id, title FROM assignment 
        WHERE title LIKE 'Amaliy topshiriq #%'
    """)
    demo_assignments = cursor.fetchall()
    
    if not demo_assignments:
        print("Demo topshiriqlar topilmadi.")
        conn.close()
        sys.exit(0)
    
    print(f"Topilgan demo topshiriqlar: {len(demo_assignments)}")
    for assignment_id, title in demo_assignments[:5]:  # Faqat birinchi 5 tasini ko'rsatish
        print(f"  - {title} (ID: {assignment_id})")
    if len(demo_assignments) > 5:
        print(f"  ... va yana {len(demo_assignments) - 5} ta")
    
    # Demo topshiriqlarga tegishli submissions'larni o'chirish
    assignment_ids = [a[0] for a in demo_assignments]
    if assignment_ids:
        placeholders = ','.join('?' * len(assignment_ids))
        cursor.execute(f"DELETE FROM submission WHERE assignment_id IN ({placeholders})", assignment_ids)
        deleted_submissions = cursor.rowcount
        print(f"O'chirilgan submissions: {deleted_submissions}")
    
    # Demo topshiriqlarni o'chirish
    if assignment_ids:
        placeholders = ','.join('?' * len(assignment_ids))
        cursor.execute(f"DELETE FROM assignment WHERE id IN ({placeholders})", assignment_ids)
        deleted_assignments = cursor.rowcount
        print(f"O'chirilgan topshiriqlar: {deleted_assignments}")
    
    conn.commit()
    print("Migration muvaffaqiyatli yakunlandi!")
    print(f"  - {deleted_assignments} ta demo topshiriq o'chirildi")
    print(f"  - {deleted_submissions} ta submission o'chirildi")
    
    conn.close()
    
except sqlite3.Error as e:
    print(f"SQLite xatolik: {e}")
    if conn:
        conn.rollback()
        conn.close()
    sys.exit(1)
except Exception as e:
    print(f"Xatolik: {e}")
    import traceback
    traceback.print_exc()
    if conn:
        conn.rollback()
        conn.close()
    sys.exit(1)
