"""Migration: Add author_role column to Announcement table"""
import sqlite3
import os

def migrate():
    # Database path
    db_path = 'instance/eduspace.db'
    
    if not os.path.exists(db_path):
        print(f"Database file not found: {db_path}")
        return
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if column already exists
        cursor.execute("PRAGMA table_info(announcement)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'author_role' not in columns:
            cursor.execute("ALTER TABLE announcement ADD COLUMN author_role VARCHAR(50)")
            conn.commit()
            print("Successfully added author_role column to announcement table")
        else:
            print("author_role column already exists")
        
        conn.close()
    except Exception as e:
        print(f"Error during migration: {str(e)}")

if __name__ == '__main__':
    migrate()
