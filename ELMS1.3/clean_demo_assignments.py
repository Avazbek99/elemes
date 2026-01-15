"""
Script to clean up demo/test subject assignments
"""
from app import create_app, db
from app.models import TeacherSubject, User, Subject, Group

app = create_app()

def clean_demo_assignments():
    with app.app_context():
        print("Cleaning demo subject assignments...")
        
        # Get all teacher subject assignments
        all_assignments = TeacherSubject.query.all()
        print(f"\nTotal assignments before cleanup: {len(all_assignments)}")
        
        # Show breakdown by teacher
        teachers = {}
        for ta in all_assignments:
            teacher = User.query.get(ta.teacher_id)
            if teacher:
                if teacher.full_name not in teachers:
                    teachers[teacher.full_name] = 0
                teachers[teacher.full_name] += 1
        
        print("\nAssignments by teacher:")
        for name, count in sorted(teachers.items()):
            print(f"  {name}: {count} assignments")
        
        # Ask for confirmation
        print("\n" + "="*60)
        response = input("\nDo you want to DELETE ALL subject assignments? (yes/no): ")
        
        if response.lower() == 'yes':
            # Delete all assignments
            deleted = TeacherSubject.query.delete()
            db.session.commit()
            print(f"\n✅ Deleted {deleted} subject assignments")
            print("All teachers' subject assignments have been removed.")
        else:
            print("\n❌ Cleanup cancelled. No changes made.")

if __name__ == '__main__':
    clean_demo_assignments()
