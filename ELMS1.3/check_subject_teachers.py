from app import create_app, db
from app.models import Subject, TeacherSubject, Group, Direction

app = create_app()
with app.app_context():
    # Find the subject in the image (likely Amaliy matematika)
    subject_name = "Amaliy matematika"
    subject = Subject.query.filter(Subject.name.ilike(subject_name)).first()
    
    if not subject:
        print(f"Subject '{subject_name}' not found.")
        # Try generic search
        print("Searching for similar subjects:")
        for s in Subject.query.filter(Subject.name.ilike("%matem%")).all():
            print(f"  {s.id}: {s.name}")
    else:
        print(f"Subject found: {subject.id}: {subject.name}")
        assignments = TeacherSubject.query.filter_by(subject_id=subject.id).all()
        print(f"All assignments for subject {subject.name}:")
        if not assignments:
            print("  No assignments found.")
        for a in assignments:
            group = Group.query.get(a.group_id)
            print(f"  ID: {a.id}, Group: {group.name if group else 'N/A'} (ID: {a.group_id}), Type: {a.lesson_type}, Teacher ID: {a.teacher_id}")
