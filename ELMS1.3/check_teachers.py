from app import create_app, db
from app.models import TeacherSubject, Subject, Group

app = create_app()
with app.app_context():
    print("TeacherSubject lesson_type distribution:")
    types = db.session.query(TeacherSubject.lesson_type, db.func.count(TeacherSubject.id)).group_by(TeacherSubject.lesson_type).all()
    for t_type, count in types:
        print(f"  {t_type}: {count}")
    
    print("\nSample assignments for 'ma'ruza' or 'Maruza' if any:")
    samples = TeacherSubject.query.filter(TeacherSubject.lesson_type.ilike("%maru%")).limit(5).all()
    for s in samples:
        subject = Subject.query.get(s.subject_id)
        group = Group.query.get(s.group_id)
        print(f"  ID: {s.id}, Type: {s.lesson_type}, Subject: {subject.name if subject else 'N/A'}, Group: {group.name if group else 'N/A'}")
