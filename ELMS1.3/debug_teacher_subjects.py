from app import create_app, db
from app.models import User, TeacherSubject, Group, Direction

app = create_app()
with app.app_context():
    teachers = User.query.filter(User.full_name.ilike("%Dilshod%")).all() + \
               User.query.filter(User.full_name.ilike("%Aziz%")).all()
    for teacher in teachers:
        print(f"\nTeacher: {teacher.full_name} (ID: {teacher.id})")
        ts_entries = TeacherSubject.query.filter_by(teacher_id=teacher.id).all()
        for ts in ts_entries:
            group = Group.query.get(ts.group_id)
            if not group:
                print(f"  Assignment with missing group ID: {ts.group_id}")
                continue
            
            direction = Direction.query.get(group.direction_id) if group.direction_id else None
            student_count = group.get_students_count()
            current_semester = direction.semester if direction else "N/A"
            
            print(f"  Subject: {ts.subject.name}")
            print(f"    Group: {group.name} (ID: {group.id})")
            print(f"    Students: {student_count}")
            print(f"    Group Course Year: {group.course_year}")
            print(f"    Direction Semester: {current_semester}")
            
            # Check what our filter does
            is_active = student_count > 0
            has_curriculum = False
            if direction and ts.subject_id:
                from app.models import DirectionCurriculum
                curr = DirectionCurriculum.query.filter_by(
                    direction_id=direction.id,
                    subject_id=ts.subject_id,
                    semester=current_semester
                ).first()
                has_curriculum = curr is not None
            
            print(f"    Filter Result -> Students > 0: {is_active}, Has Curriculum for Semester {current_semester}: {has_curriculum}")
