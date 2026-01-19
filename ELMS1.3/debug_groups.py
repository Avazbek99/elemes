from app import create_app, db
from app.models import Group, TeacherSubject, DirectionCurriculum, Subject, Direction, Lesson, Assignment

app = create_app()
with app.app_context():
    # Looking for 'Dasturlash asoslari'
    subject = Subject.query.filter(Subject.name.like('%Dasturlash asoslari%')).first()
    if not subject:
        print("Subject not found")
        exit()
    
    print(f"Subject: {subject.name} (ID: {subject.id})")
    
    # Looking for direction
    direction = Direction.query.filter(Direction.name.like('%Kunduzgi%')).first()
    if direction:
        print(f"Direction: {direction.name} (ID: {direction.id})")
        
        groups = Group.query.filter_by(direction_id=direction.id).all()
        print(f"Groups in direction: {[(g.id, g.name, g.get_students_count()) for g in groups]}")
        
        curriculum = DirectionCurriculum.query.filter_by(direction_id=direction.id, subject_id=subject.id).all()
        print(f"Curriculum semesters: {[c.semester for c in curriculum]}")
        
        lessons_count = Lesson.query.filter_by(subject_id=subject.id, direction_id=direction.id).count()
        assignments_count = Assignment.query.filter_by(subject_id=subject.id, direction_id=direction.id).count()
        print(f"Counts: {lessons_count} lessons, {assignments_count} assignments")
        
        ts = TeacherSubject.query.filter_by(subject_id=subject.id).all()
        print(f"Teacher assignments:")
        for t in ts:
            g_name = t.group.name if t.group else "Global"
            t_name = t.teacher.full_name if t.teacher else "Unknown"
            print(f"  - {t_name} | Group: {g_name} | Type: {t.lesson_type} | Semester: {t.semester}")
