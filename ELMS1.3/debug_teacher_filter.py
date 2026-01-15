from app import create_app, db
from app.models import User, Group, Direction, TeacherSubject, DirectionCurriculum

app = create_app()
with app.app_context():
    teacher = User.query.filter(User.full_name.ilike("%Dilshod%")).first()
    if not teacher:
        print("Teacher not found")
        exit()
    
    print(f"Teacher: {teacher.full_name}")
    ts_list = TeacherSubject.query.filter_by(teacher_id=teacher.id).all()
    print(f"Total assignments: {len(ts_list)}\n")
    
    filtered_count = 0
    for ts in ts_list:
        g = Group.query.get(ts.group_id)
        if not g or not g.direction_id:
            continue
        
        student_count = g.get_students_count()
        current_sem = g.direction.semester if g.direction else 1
        
        curr_item = DirectionCurriculum.query.filter_by(
            direction_id=g.direction_id,
            subject_id=ts.subject_id,
            semester=current_sem
        ).first()
        
        passes_filter = student_count > 0 and curr_item is not None
        if passes_filter:
            filtered_count += 1
        
        print(f"Subject: {ts.subject.name}")
        print(f"  Group: {g.name}, Students: {student_count}")
        print(f"  Group semester: {current_sem}")
        print(f"  Curriculum item exists for semester {current_sem}: {curr_item is not None}")
        print(f"  PASSES FILTER: {passes_filter}\n")
    
    print(f"Summary: {filtered_count}/{len(ts_list)} assignments pass the filter")
