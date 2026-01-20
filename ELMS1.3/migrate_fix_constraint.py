import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instance', 'eduspace.db')

def migrate():
    print(f"Connecting to database at {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # 1. Rename existing table
        print("Renaming existing table...")
        cursor.execute("ALTER TABLE direction_curriculum RENAME TO direction_curriculum_old")
        
        # 2. Create new table with updated constraints
        print("Creating new table...")
        cursor.execute("""
            CREATE TABLE direction_curriculum (
                id INTEGER NOT NULL, 
                direction_id INTEGER NOT NULL, 
                subject_id INTEGER NOT NULL, 
                semester INTEGER NOT NULL, 
                enrollment_year INTEGER, 
                education_type VARCHAR(20), 
                hours_maruza INTEGER DEFAULT 0, 
                hours_amaliyot INTEGER DEFAULT 0, 
                hours_laboratoriya INTEGER DEFAULT 0, 
                hours_seminar INTEGER DEFAULT 0, 
                hours_kurs_ishi INTEGER DEFAULT 0, 
                hours_mustaqil INTEGER DEFAULT 0, 
                created_at DATETIME, 
                PRIMARY KEY (id), 
                CONSTRAINT uq_direction_subject_semester_year_type UNIQUE (direction_id, subject_id, semester, enrollment_year, education_type), 
                FOREIGN KEY(direction_id) REFERENCES direction (id), 
                FOREIGN KEY(subject_id) REFERENCES subject (id)
            )
        """)
        
        # 3. Copy data from old table to new table
        print("Copying data...")
        cursor.execute("""
            INSERT INTO direction_curriculum (
                id, direction_id, subject_id, semester, 
                enrollment_year, education_type, 
                hours_maruza, hours_amaliyot, hours_laboratoriya, 
                hours_seminar, hours_kurs_ishi, hours_mustaqil, 
                created_at
            )
            SELECT 
                id, direction_id, subject_id, semester, 
                enrollment_year, education_type, 
                hours_maruza, hours_amaliyot, hours_laboratoriya, 
                hours_seminar, hours_kurs_ishi, hours_mustaqil, 
                created_at
            FROM direction_curriculum_old
        """)
        
        # 4. Drop old table
        print("Dropping old table...")
        cursor.execute("DROP TABLE direction_curriculum_old")
        
        conn.commit()
        print("Migration completed successfully")
        
    except Exception as e:
        print(f"Migration failed: {e}")
        conn.rollback()
        # Restore if something went wrong during creation/copy but AFTER rename
        # This part is tricky in a script, simplistic rollback might not be enough if table was renamed but not recreated.
        # But SQLite transaction should handle DDL statements too.
    finally:
        conn.close()

if __name__ == '__main__':
    migrate()
