"""
Migration: Assignment va Submission jadvallariga yangi maydonlar qo'shish
"""
import sqlite3
import os

def migrate():
    db_path = os.path.join(os.path.dirname(__file__), 'instance', 'eduspace.db')
    
    if not os.path.exists(db_path):
        print(f"Database fayl topilmadi: {db_path}")
        return
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Assignment jadvaliga yangi maydonlar qo'shish
        print("Assignment jadvaliga maydonlar qo'shilmoqda...")
        
        # direction_id tekshirish va qo'shish
        cursor.execute("PRAGMA table_info(assignment)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'direction_id' not in columns:
            cursor.execute("ALTER TABLE assignment ADD COLUMN direction_id INTEGER")
            print("  - direction_id qo'shildi")
        
        if 'lesson_type' not in columns:
            cursor.execute("ALTER TABLE assignment ADD COLUMN lesson_type VARCHAR(20)")
            print("  - lesson_type qo'shildi")
        
        if 'lesson_ids' not in columns:
            cursor.execute("ALTER TABLE assignment ADD COLUMN lesson_ids TEXT")
            print("  - lesson_ids qo'shildi")
        
        # Submission jadvaliga yangi maydonlar qo'shish
        print("Submission jadvaliga maydonlar qo'shilmoqda...")
        
        cursor.execute("PRAGMA table_info(submission)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'resubmission_count' not in columns:
            cursor.execute("ALTER TABLE submission ADD COLUMN resubmission_count INTEGER DEFAULT 0")
            print("  - resubmission_count qo'shildi")
        
        if 'allow_resubmission' not in columns:
            cursor.execute("ALTER TABLE submission ADD COLUMN allow_resubmission BOOLEAN DEFAULT 0")
            print("  - allow_resubmission qo'shildi")
        
        if 'is_active' not in columns:
            cursor.execute("ALTER TABLE submission ADD COLUMN is_active BOOLEAN DEFAULT 1")
            print("  - is_active qo'shildi")
            
            # Barcha mavjud submission'larni faol qilish
            cursor.execute("UPDATE submission SET is_active = 1 WHERE is_active IS NULL")
            print("  - Mavjud submission'lar faol qilindi")
        
        conn.commit()
        print("\nMigration muvaffaqiyatli yakunlandi!")
        
    except Exception as e:
        conn.rollback()
        print(f"Xatolik: {e}")
        raise
    finally:
        conn.close()

if __name__ == '__main__':
    migrate()
