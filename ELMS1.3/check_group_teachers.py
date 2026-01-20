from app import create_app, db
from app.models import Group, TeacherSubject, Subject

app = create_app()
with app.app_context():
    group_name = "MT 25-03 uz" # Case sensitive check in code, let's try ilike
    group = Group.query.filter(Group.name.ilike(group_name)).first()
    
    if not group:
        print(f"Group '{group_name}' not found.")
        # Try finding all groups to see names
        print("Available groups:")
        for g in Group.query.all():
            print(f"  {g.id}: {g.name}")
    else:
        print(f"Group found: {group.id}: {group.name}")
        assignments = TeacherSubject.query.filter_by(group_id=group.id).all()
        print(f"Assignments for group {group.name} (ID: {group.id}):")
        if not assignments:
            print("  No assignments found.")
        for a in assignments:
            subject = Subject.query.get(a.subject_id)
            print(f"  ID: {a.id}, Subject: {subject.name if subject else 'N/A'}, Type: {a.lesson_type}, Teacher ID: {a.teacher_id}")
