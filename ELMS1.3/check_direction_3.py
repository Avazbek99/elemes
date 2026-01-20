from app import create_app, db
from app.models import Direction, DirectionCurriculum, TeacherSubject, Group, Subject

app = create_app()
with app.app_context():
    direction_id = 3
    direction = Direction.query.get(direction_id)
    if not direction:
        print(f"Direction {direction_id} not found.")
    else:
        print(f"Direction {direction_id}: {direction.name}")
        
        print("\nCurriculum Items:")
        items = DirectionCurriculum.query.filter_by(direction_id=direction_id).all()
        for item in items:
            subject = Subject.query.get(item.subject_id)
            print(f"  ID: {item.id}, Subject: {subject.name if subject else 'N/A'}, Semester: {item.semester}, Year: {item.enrollment_year}, Type: {item.education_type}")
            
        print("\nGroups in this direction:")
        groups = Group.query.filter_by(direction_id=direction_id).all()
        for g in groups:
            print(f"  ID: {g.id}, Name: {g.name}, Year: {g.enrollment_year}, Type: {g.education_type}")
            
        print("\nTeacher Assignments for this direction's subjects:")
        subject_ids = [item.subject_id for item in items]
        group_ids = [g.id for g in groups]
        assignments = TeacherSubject.query.filter(TeacherSubject.subject_id.in_(subject_ids), TeacherSubject.group_id.in_(group_ids)).all()
        for a in assignments:
            s = Subject.query.get(a.subject_id)
            g = Group.query.get(a.group_id)
            print(f"  ID: {a.id}, Subject: {s.name if s else 'N/A'}, Group: {g.name if g else 'N/A'}, Type: {a.lesson_type}, Teacher: {a.teacher.full_name if a.teacher else 'N/A'}")
