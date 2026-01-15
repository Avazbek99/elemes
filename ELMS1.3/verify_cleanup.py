"""
Verify cleanup - check if assignments were deleted
"""
from app import create_app, db
from app.models import TeacherSubject

app = create_app()

with app.app_context():
    count = TeacherSubject.query.count()
    print(f"Remaining subject assignments: {count}")
    
    if count == 0:
        print("SUCCESS: All subject assignments have been deleted!")
    else:
        print(f"WARNING: {count} assignments still remain")
