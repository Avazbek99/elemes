from app import create_app, db
from app.models import User
from sqlalchemy import text

import os

# Skip demo data creation to avoid DB errors during migration
os.environ['FLASK_SKIP_DEMO_DATA'] = '1'

app = create_app()

def migrate_user_table():
    with app.app_context():
        # SQLite da 'ALTER TABLE' cheklangan, shuning uchun har bir ustunni alohida qo'shamiz
        columns = [
            ("passport_number", "VARCHAR(20)"),
            ("pinfl", "VARCHAR(14)"),
            ("birth_date", "DATE"),
            ("specialty", "VARCHAR(200)"),
            ("specialty_code", "VARCHAR(50)"),
            ("education_type", "VARCHAR(50)")
        ]
        
        with db.engine.connect() as conn:
            for col_name, col_type in columns:
                try:
                    # Ustun bor-yo'qligini tekshirish (o'ta primitiv usul, lekin ishlaydi)
                    # Yoki shunchaki qo'shishga urinib ko'ramiz, xato bersa demak bor
                    conn.execute(text(f"ALTER TABLE user ADD COLUMN {col_name} {col_type}"))
                    print(f"Added column {col_name}")
                except Exception as e:
                    print(f"Column {col_name} might already exist or error: {e}")
            
            conn.commit()
            print("Migration completed successfully.")

if __name__ == "__main__":
    migrate_user_table()
