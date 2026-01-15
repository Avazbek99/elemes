"""
Script to clean up ALL subject assignments
"""
from app import create_app, db
from app.models import TeacherSubject

app = create_app()

with app.app_context():
    print("Deleting all subject assignments...")
    
    # Count before deletion
    count = TeacherSubject.query.count()
    print(f"Total assignments to delete: {count}")
    
    # Delete all
    TeacherSubject.query.delete()
    db.session.commit()
    
    print(f"✅ Successfully deleted {count} subject assignments")
    print("All teacher-subject assignments have been removed.")
