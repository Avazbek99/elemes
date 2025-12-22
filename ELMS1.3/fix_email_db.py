import sqlite3
import os

db_path = 'ELMS1.3/instance/eduspace.db' if os.path.exists('ELMS1.3/instance/eduspace.db') else 'instance/eduspace.db'

print(f"Database path: {db_path}")

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Check current state
cursor.execute("PRAGMA table_info(user)")
cols = cursor.fetchall()
email_col = [c for c in cols if c[1] == 'email'][0]
print(f"Email column NOT NULL: {email_col[3] == 0}")

# Get table SQL
cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='user'")
result = cursor.fetchone()
if result:
    sql = result[0]
    print(f"Email in SQL has NOT NULL: {'email' in sql.lower() and 'not null' in sql.lower() and sql.lower().index('email') < sql.lower().index('not null', sql.lower().index('email') + 10)}")

# If email is NOT NULL in SQL definition, recreate table
if email_col[3] == 0 or (result and 'email' in result[0].lower() and 'not null' in result[0].lower()):
    print("Recreating table with nullable email...")
    
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

