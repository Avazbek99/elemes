import sqlite3
import os

db_path = 'ELMS1.3/instance/eduspace.db'
if not os.path.exists(db_path):
    db_path = 'instance/eduspace.db'

print(f"Fixing email column in {db_path}")

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Check current state
cursor.execute("PRAGMA table_info(user)")
cols = cursor.fetchall()
email_col = [c for c in cols if c[1] == 'email'][0]
print(f"Email column NOT NULL: {email_col[3] == 0}")

if email_col[3] == 0:  # NOT NULL
    print("Recreating table...")
    
    # Create temp table with nullable email
    cursor.execute("""
        CREATE TABLE user_new (
            id INTEGER PRIMARY KEY,
            email VARCHAR(120),
            login VARCHAR(50) UNIQUE,
            password_hash VARCHAR(256) NOT NULL,
            full_name VARCHAR(100) NOT NULL,
            role VARCHAR(20) NOT NULL DEFAULT 'student',
            is_active BOOLEAN DEFAULT 1,
            created_at DATETIME,
            last_login DATETIME,
            phone VARCHAR(20),
            student_id VARCHAR(20) UNIQUE,
            group_id INTEGER,
            enrollment_year INTEGER,
            semester INTEGER DEFAULT 1,
            passport_number VARCHAR(20),
            pinfl VARCHAR(14),
            birth_date DATE,
            specialty VARCHAR(200),
            specialty_code VARCHAR(50),
            education_type VARCHAR(50),
            department VARCHAR(100),
            position VARCHAR(50),
            faculty_id INTEGER,
            description TEXT
        )
    """)
    
    # Copy data
    cursor.execute("INSERT INTO user_new SELECT * FROM user")
    
    # Drop old
    cursor.execute("DROP TABLE user")
    
    # Rename
    cursor.execute("ALTER TABLE user_new RENAME TO user")
    
    conn.commit()
    print("✅ Fixed!")
else:
    print("✅ Already nullable")

conn.close()

