import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instance', 'eduspace.db')

def migrate():
    print(f"Connecting to database at {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # Add enrollment_year column
        try:
            print("Adding enrollment_year column...")
            cursor.execute("ALTER TABLE direction_curriculum ADD COLUMN enrollment_year INTEGER")
            print("Success")
        except sqlite3.OperationalError as e:
            if "duplicate column" in str(e):
                print("Column enrollment_year already exists")
            else:
                print(f"Error adding enrollment_year: {e}")

        # Add education_type column
        try:
            print("Adding education_type column...")
            cursor.execute("ALTER TABLE direction_curriculum ADD COLUMN education_type VARCHAR(20)")
            print("Success")
        except sqlite3.OperationalError as e:
            if "duplicate column" in str(e):
                print("Column education_type already exists")
            else:
                print(f"Error adding education_type: {e}")

        conn.commit()
        print("Migration completed successfully")
        
    except Exception as e:
        print(f"Migration failed: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == '__main__':
    migrate()
