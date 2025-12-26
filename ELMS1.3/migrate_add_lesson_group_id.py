"""Migration: Add group_id column to Lesson table"""
import sqlite3
import os

def migrate():
    db_path = 'instance/eduspace.db'
    if not os.path.exists(db_path):
        print(f"Database file not found: {db_path}")
        return
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if column already exists
        cursor.execute("PRAGMA table_info(lesson)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'group_id' not in columns:
            cursor.execute("ALTER TABLE lesson ADD COLUMN group_id INTEGER")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_lesson_group_id ON lesson(group_id)")
            conn.commit()
            print("Successfully added group_id column to lesson table")
        else:
            print("group_id column already exists")
        
        conn.close()
    except Exception as e:
        print(f"Error during migration: {str(e)}")

if __name__ == '__main__':
    migrate()
