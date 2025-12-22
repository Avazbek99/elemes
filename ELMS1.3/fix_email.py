import sqlite3
import os

db_path = 'ELMS1.3/instance/eduspace.db' if os.path.exists('ELMS1.3/instance/eduspace.db') else 'instance/eduspace.db'

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Get table definition
cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='user'")
result = cursor.fetchone()
if result:
    print("Current table definition contains NOT NULL for email:", "NOT NULL" in result[0] and "email" in result[0])

# Check column info
cursor.execute("PRAGMA table_info(user)")
cols = cursor.fetchall()
for col in cols:
    if col[1] == 'email':
        print(f"Email column: name={col[1]}, type={col[2]}, notnull={col[3]}, default={col[4]}")

# If email is NOT NULL, recreate table
email_col = [c for c in cols if c[1] == 'email'][0]
if email_col[3] == 0:  # NOT NULL
    print("Recreating table with nullable email...")
    
    # Get all columns
    cursor.execute("PRAGMA table_info(user)")
    all_cols = cursor.fetchall()
    
    # Create new table
    cursor.execute("""
        CREATE TABLE user_temp (
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
    cursor.execute("INSERT INTO user_temp SELECT * FROM user")
    
    # Drop old
    cursor.execute("DROP TABLE user")
    
    # Rename
    cursor.execute("ALTER TABLE user_temp RENAME TO user")
    
    conn.commit()
    print("✅ Table recreated with nullable email")
else:
    print("✅ Email is already nullable")

conn.close()

