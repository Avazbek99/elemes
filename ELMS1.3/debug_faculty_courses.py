from app import create_app, db
from app.models import Faculty, Group

app = create_app()
with app.app_context():
    # Find IT faculty
    it_faculty = Faculty.query.filter(Faculty.name.ilike("%texnolog%")).first()
    if not it_faculty:
        print("IT Faculty not found")
        exit()
    
    print(f"Faculty: {it_faculty.name} (ID: {it_faculty.id})")
    print("\nAll groups in this faculty:")
    
    all_groups = Group.query.filter_by(faculty_id=it_faculty.id).all()
    course_student_count = {}
    
    for g in all_groups:
        student_count = g.get_students_count()
        course = g.course_year
        
        if course not in course_student_count:
            course_student_count[course] = 0
        course_student_count[course] += student_count
        
        print(f"  {g.name}: Course {course}, Students: {student_count}")
    
    print("\n\nCourse Summary:")
    for course, count in sorted(course_student_count.items()):
        print(f"  {course}-kurs: {count} students total")
    
    print("\n\nActive courses (with students):")
    active_courses = set()
    for g in all_groups:
        if g.get_students_count() == 0:
            continue
        if g.course_year:
            active_courses.add(g.course_year)
    
    print(f"  {sorted(list(active_courses))}")
