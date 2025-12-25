from flask import Blueprint, render_template, request, redirect, url_for, flash, Response, send_file, session
from flask_login import login_required, current_user
from app.models import User, Faculty, Group, Subject, TeacherSubject, Schedule, Announcement, Direction, StudentPayment, DirectionCurriculum
from app import db
from functools import wraps
from sqlalchemy import func
from datetime import datetime
import calendar
from werkzeug.security import generate_password_hash

bp = Blueprint('dean', __name__, url_prefix='/dean')

def dean_required(f):
    """Faqat dekan uchun (joriy tanlangan rol yoki asosiy rol)"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash("Sizda bu sahifaga kirish huquqi yo'q", 'error')
            return redirect(url_for('main.dashboard'))
        
        # Session'dan joriy rol ni olish
        current_role = session.get('current_role', current_user.role)
        
        # Foydalanuvchida dekan roli borligini tekshirish
        if current_role == 'dean' and 'dean' in current_user.get_roles():
            return f(*args, **kwargs)
        elif current_user.has_role('dean'):
            # Agar joriy rol dekan emas, lekin foydalanuvchida dekan roli bor bo'lsa, ruxsat berish
            return f(*args, **kwargs)
        else:
            flash("Sizda bu sahifaga kirish huquqi yo'q", 'error')
            return redirect(url_for('main.dashboard'))
    return decorated_function


# ==================== ASOSIY SAHIFA ====================
@bp.route('/')
@login_required
@dean_required
def index():
    # Dekanning fakulteti
    faculty = Faculty.query.get(current_user.faculty_id) if current_user.faculty_id else None
    
    stats = {}
    if faculty:
        stats = {
            'total_groups': faculty.groups.count(),
            'total_subjects': Subject.query.count(),
            'total_students': User.query.join(Group).filter(Group.faculty_id == faculty.id).count(),
            'total_teachers': TeacherSubject.query.distinct(TeacherSubject.teacher_id).count(),
        }
        # Yo'nalishlar ro'yxati
        directions = Direction.query.filter_by(faculty_id=faculty.id).order_by(Direction.name).all()
        # Har bir yo'nalish uchun guruhlar soni
        direction_stats = {}
        for direction in directions:
            direction_stats[direction.id] = {
                'groups_count': Group.query.filter_by(direction_id=direction.id).count(),
                'groups': Group.query.filter_by(direction_id=direction.id).order_by(Group.name).all()
            }
        subjects = Subject.query.order_by(Subject.name).all()
    else:
        directions = []
        direction_stats = {}
        subjects = []
    
    return render_template('dean/index.html', faculty=faculty, stats=stats, directions=directions, direction_stats=direction_stats, subjects=subjects)




# ==================== GURUHLAR ====================
@bp.route('/groups')
@login_required
@dean_required
def groups():
    faculty = Faculty.query.get(current_user.faculty_id)
    if not faculty:
        flash("Sizga fakultet biriktirilmagan", 'error')
        return redirect(url_for('main.dashboard'))
    
    groups = faculty.groups.order_by(Group.course_year, Group.name).all()
    return render_template('dean/groups.html', faculty=faculty, groups=groups)


@bp.route('/groups/create', methods=['GET', 'POST'])
@login_required
@dean_required
def create_group():
    faculty = Faculty.query.get(current_user.faculty_id)
    if not faculty:
        flash("Sizga fakultet biriktirilmagan", 'error')
        return redirect(url_for('main.dashboard'))
    
    # Fakultetdagi barcha kurslarni olish
    courses = db.session.query(Direction.course_year).filter_by(faculty_id=faculty.id).distinct().order_by(Direction.course_year).all()
    courses = [c[0] for c in courses]
    
    # Barcha yo'nalishlarni ma'lumotlar bazasi sifatida yuborish (JavaScript uchun)
    all_directions = Direction.query.filter_by(faculty_id=faculty.id).order_by(Direction.course_year, Direction.semester, Direction.name).all()
    
    if request.method == 'POST':
        name = request.form.get('name')
        direction_id = request.form.get('direction_id', type=int)
        
        # Validatsiya
        if not name:
            flash("Guruh nomi majburiy", 'error')
            return render_template('dean/create_group.html', faculty=faculty, courses=courses, all_directions=all_directions)
        
        if not direction_id:
            flash("Yo'nalish tanlash majburiy", 'error')
            return render_template('dean/create_group.html', faculty=faculty, courses=courses, all_directions=all_directions)
        
        # Yo'nalish tekshiruvi - faqat shu fakultetga tegishli bo'lishi kerak
        direction = Direction.query.get(direction_id)
        if not direction or direction.faculty_id != faculty.id:
            flash("Noto'g'ri yo'nalish tanlandi", 'error')
            return render_template('dean/create_group.html', faculty=faculty, courses=courses, all_directions=all_directions)
        
        # Bir yo'nalishda bir xil guruh nomi bo'lishi mumkin emas
        if Group.query.filter_by(name=name.upper(), direction_id=direction_id).first():
            flash("Bu yo'nalishda bunday nomli guruh allaqachon mavjud", 'error')
            return render_template('dean/create_group.html', faculty=faculty, courses=courses, all_directions=all_directions)
        
        # Kurs, semestr va ta'lim shaklini yo'nalishdan olish
        description = request.form.get('description', '').strip()
        course_year = request.form.get('course_year', type=int) or direction.course_year
        semester = request.form.get('semester', type=int) or direction.semester
        education_type = request.form.get('education_type') or direction.education_type
        
        group = Group(
            name=name.upper(),
            faculty_id=faculty.id,
            course_year=course_year,
            education_type=education_type,  # Yo'nalishdan olinadi
            direction_id=direction_id,
            description=description if description else None
        )
        db.session.add(group)
        db.session.commit()
        
        flash("Guruh muvaffaqiyatli yaratildi", 'success')
        return redirect(url_for('dean.courses'))
    
    return render_template('dean/create_group.html', faculty=faculty, courses=courses, all_directions=all_directions)


@bp.route('/groups/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@dean_required
def edit_group(id):
    group = Group.query.get_or_404(id)
    faculty = Faculty.query.get(current_user.faculty_id)
    
    # Faqat o'z fakultetidagi guruhlarni tahrirlashi mumkin
    if group.faculty_id != current_user.faculty_id:
        flash("Sizda bu guruhni tahrirlash huquqi yo'q", 'error')
        return redirect(url_for('dean.groups'))
    
    # Faqat shu fakultetdagi yo'nalishlar
    directions = Direction.query.filter_by(faculty_id=faculty.id).order_by(Direction.course_year, Direction.semester, Direction.name).all()
    
    if request.method == 'POST':
        # Guruh nomi, kurs, semestr, ta'lim shakli, yo'nalish va tavsifni o'zgartirish mumkin
        new_name = request.form.get('name').upper()
        course_year = request.form.get('course_year', type=int)
        semester = request.form.get('semester', type=int)
        education_type = request.form.get('education_type')
        direction_id = request.form.get('direction_id', type=int)
        description = request.form.get('description', '').strip()
        
        # Validatsiya
        if not course_year or not semester or not education_type or not direction_id:
            flash("Barcha maydonlar to'ldirilishi kerak", 'error')
            return redirect(url_for('dean.edit_group', id=group.id))
        
        # Yo'nalish tekshiruvi
        direction = Direction.query.get(direction_id)
        if not direction or direction.faculty_id != group.faculty_id:
            flash("Noto'g'ri yo'nalish tanlandi", 'error')
            return redirect(url_for('dean.edit_group', id=group.id))
        
        # Bir yo'nalishda bir xil guruh nomi bo'lishi mumkin emas
        # Agar nom yoki yo'nalish o'zgarganda tekshirish kerak
        if (new_name != group.name or direction_id != group.direction_id):
            existing_group = Group.query.filter_by(name=new_name, direction_id=direction_id).first()
            if existing_group and existing_group.id != group.id:
                flash("Bu yo'nalishda bunday nomli guruh allaqachon mavjud", 'error')
                return redirect(url_for('dean.edit_group', id=group.id))
        
        group.name = new_name
        old_direction_id = group.direction_id
        group.direction_id = direction_id
        group.course_year = course_year
        group.education_type = education_type
        group.description = description if description else None
        
        db.session.commit()
        flash("Guruh yangilandi", 'success')
        # Yo'nalishga qaytish (yangi yoki eski yo'nalishga)
        return redirect(url_for('dean.direction_detail', id=direction_id))
    
    # GET request - ma'lumotlarni tayyorlash
    # Fakultetdagi barcha kurslarni olish
    courses = db.session.query(Direction.course_year).filter_by(faculty_id=faculty.id).distinct().order_by(Direction.course_year).all()
    courses = [c[0] for c in courses]
    
    # Barcha yo'nalishlarni ma'lumotlar bazasi sifatida yuborish (JavaScript uchun)
    all_directions = Direction.query.filter_by(faculty_id=faculty.id).order_by(Direction.course_year, Direction.semester, Direction.name).all()
    
    return render_template('dean/edit_group.html', 
                         group=group,
                         faculty=faculty,
                         courses=courses,
                         all_directions=all_directions)


@bp.route('/groups/<int:id>/delete', methods=['POST'])
@login_required
@dean_required
def delete_group(id):
    group = Group.query.get_or_404(id)
    
    if group.faculty_id != current_user.faculty_id:
        flash("Sizda bu guruhni o'chirish huquqi yo'q", 'error')
        return redirect(url_for('dean.groups'))
    
    if group.students.count() > 0:
        flash("Guruhda talabalar mavjud. Avval talabalarni boshqa guruhga o'tkazing", 'error')
    else:
        db.session.delete(group)
        db.session.commit()
        flash("Guruh o'chirildi", 'success')
    
    return redirect(url_for('dean.groups'))


@bp.route('/groups/<int:id>/students')
@login_required
@dean_required
def group_students(id):
    group = Group.query.get_or_404(id)
    
    if group.faculty_id != current_user.faculty_id:
        flash("Sizda bu guruhni ko'rish huquqi yo'q", 'error')
        return redirect(url_for('dean.groups'))
    
    students = group.students.order_by(User.full_name).all()
    # Guruhga qo'shish uchun bo'sh talabalar
    available_students = User.query.filter(
        User.role == 'student',
        User.group_id == None
    ).order_by(User.full_name).all()
    
    return render_template('dean/group_students.html', group=group, students=students, available_students=available_students)


@bp.route('/groups/<int:id>/add-student', methods=['POST'])
@login_required
@dean_required
def add_student_to_group(id):
    group = Group.query.get_or_404(id)
    
    if group.faculty_id != current_user.faculty_id:
        flash("Sizda bu guruhga talaba qo'shish huquqi yo'q", 'error')
        return redirect(url_for('dean.groups'))
    
    # Bir nechta talabani qo'shish
    student_ids = request.form.getlist('student_ids')
    student_ids = [int(sid) for sid in student_ids if sid]
    
    if not student_ids:
        flash("Hech qanday talaba tanlanmagan", 'error')
        return redirect(url_for('dean.group_students', id=id))
    
    added_count = 0
    for student_id in student_ids:
        student = User.query.get(student_id)
        if student and student.role == 'student' and student.group_id is None:
            student.group_id = group.id
            added_count += 1
    
    db.session.commit()
    
    if added_count > 0:
        flash(f"{added_count} ta talaba guruhga qo'shildi", 'success')
    else:
        flash("Hech qanday talaba qo'shilmadi. Tanlangan talabalar allaqachon boshqa guruhga biriktirilgan bo'lishi mumkin", 'warning')
    
    return redirect(url_for('dean.group_students', id=id))


@bp.route('/groups/<int:id>/remove-student/<int:student_id>', methods=['POST'])
@login_required
@dean_required
def remove_student_from_group(id, student_id):
    group = Group.query.get_or_404(id)
    
    if group.faculty_id != current_user.faculty_id:
        flash("Sizda bu amaliyot uchun huquq yo'q", 'error')
        return redirect(url_for('dean.groups'))
    
    student = User.query.get_or_404(student_id)
    student.group_id = None
    db.session.commit()
    flash(f"{student.full_name} guruhdan chiqarildi", 'success')
    
    return redirect(url_for('dean.group_students', id=id))


@bp.route('/groups/<int:id>/remove-students', methods=['POST'])
@login_required
@dean_required
def remove_students_from_group(id):
    """Bir nechta talabani bir vaqtning o'zida guruhdan chiqarish"""
    group = Group.query.get_or_404(id)
    
    if group.faculty_id != current_user.faculty_id:
        flash("Sizda bu amaliyot uchun huquq yo'q", 'error')
        return redirect(url_for('dean.groups'))
    
    ids = request.form.getlist('remove_student_ids')
    student_ids = [int(sid) for sid in ids if sid]
    
    if not student_ids:
        flash("Hech qanday talaba tanlanmagan", 'error')
        return redirect(url_for('dean.group_students', id=id))
    
    students = User.query.filter(
        User.id.in_(student_ids),
        User.group_id == group.id,
        User.role == 'student'
    ).all()
    
    count = 0
    for student in students:
        student.group_id = None
        count += 1
    
    db.session.commit()
    
    if count:
        flash(f"{count} ta talaba guruhdan chiqarildi", 'success')
    else:
        flash("Hech qanday talaba guruhdan chiqarilmadi", 'warning')
    
    return redirect(url_for('dean.group_students', id=id))


# ==================== KURSLAR ====================
@bp.route('/courses')
@login_required
@dean_required
def courses():
    """Dekan uchun kurslar bo'limi - kurs>yo'nalish>guruh struktura"""
    faculty = Faculty.query.get(current_user.faculty_id)
    if not faculty:
        flash("Sizga fakultet biriktirilmagan", 'error')
        return redirect(url_for('main.dashboard'))
    
    # Fakultetdagi barcha yo'nalishlarni olish va kurs va semestr bo'yicha tartiblash
    all_directions = Direction.query.filter_by(faculty_id=faculty.id).order_by(
        Direction.course_year, 
        Direction.semester, 
        Direction.name
    ).all()
    
    # Fakultetdagi barcha guruhlarni olish
    all_groups = faculty.groups.order_by(Group.course_year, Group.name).all()
    
    # Kurslar bo'yicha guruhlash (yo'nalishlarning course_year bo'yicha)
    courses_dict = {}
    
    # Avval barcha kurslarni yaratish (1-4 kurslar)
    # Fakultetdagi barcha kurslarni topish (guruhlar yoki yo'nalishlar orqali)
    all_course_years = set()
    for group in all_groups:
        all_course_years.add(group.course_year)
    for direction in all_directions:
        all_course_years.add(direction.course_year)
    
    # Har doim 1-5 kurslarni yaratish (guruhlar yoki yo'nalishlar bo'lmasa ham)
    all_course_years.update({1, 2, 3, 4, 5})
    
    # Barcha kurslarni yaratish
    for course_year in all_course_years:
        if course_year not in courses_dict:
            courses_dict[course_year] = {}
    
    # Barcha yo'nalishlarni kurs va semestr bo'yicha guruhlash
    for direction in all_directions:
        course_year = direction.course_year
        semester = direction.semester
        
        # Semestr bo'yicha guruhlash (1-semestr, 2-semestr, ...)
        if semester not in courses_dict[course_year]:
            courses_dict[course_year][semester] = {}
        
        # Bu yo'nalishga tegishli guruhlarni topish
        direction_groups = [g for g in all_groups if g.direction_id == direction.id]
        
        # Faqat guruhlari bo'lgan yo'nalishlarni ko'rsatish
        if not direction_groups:
            continue
        
        # Yo'nalishni semestr ichiga qo'shish
        direction_id = direction.id
        if direction_id not in courses_dict[course_year][semester]:
            courses_dict[course_year][semester][direction_id] = {
                'direction': direction,
                'direction_name': direction.name,
                'groups': direction_groups
            }
    
    # Biriktirilmagan guruhlarni qo'shish
    for group in all_groups:
        if not group.direction_id:
            course_year = group.course_year
            if course_year not in courses_dict:
                courses_dict[course_year] = {}
            
            # Biriktirilmagan guruhlar uchun 1-semestr bo'limiga qo'shish
            if 1 not in courses_dict[course_year]:
                courses_dict[course_year][1] = {}
            
            direction_id = None
            if direction_id not in courses_dict[course_year][1]:
                courses_dict[course_year][1][direction_id] = {
                    'direction': None,
                    'direction_name': "Biriktirilmagan",
                    'groups': []
                }
            
            courses_dict[course_year][1][direction_id]['groups'].append(group)
    
    # Har bir kurs uchun statistika hisoblash
    for course_year, course_data in courses_dict.items():
        # course_data endi semestrlar bo'yicha guruhlangan {1: {direction_id: {...}}, 2: {...}}
        total_directions = 0
        total_groups = 0
        total_students = 0
        
        # Har bir semestr uchun statistika
        for semester, semester_data in course_data.items():
            # Har bir yo'nalish uchun statistika
            for direction_id, direction_data in semester_data.items():
                direction_data['students_count'] = User.query.filter(
                    User.group_id.in_([g.id for g in direction_data['groups']]),
                    User.role == 'student'
                ).count() if direction_data['groups'] else 0
                
                if direction_data['direction']:
                    # Yo'nalishdagi fanlar sonini o'quv rejasi orqali hisoblash (unique subject_id lar soni)
                    direction_data['subjects_count'] = db.session.query(
                        func.count(func.distinct(DirectionCurriculum.subject_id))
                    ).filter_by(direction_id=direction_data['direction'].id).scalar() or 0
                else:
                    direction_data['subjects_count'] = 0
                
                total_directions += 1
                total_groups += len(direction_data['groups'])
                total_students += direction_data['students_count']
        
        course_data['total_directions'] = total_directions
        course_data['total_groups'] = total_groups
        course_data['total_students'] = total_students
    
    # Kurslarni tartiblash
    sorted_courses = sorted(courses_dict.items())
    
    # Template uchun courses_dict'ni to'g'rilash
    # courses_dict strukturasini template'ga moslashtirish
    # course_data endi {semester: {direction_id: {...}}} formatida
    # Template uchun {semester: {direction_id: {...}}} formatini {direction_id: {...}} formatiga o'zgartirish
    formatted_courses_dict = {}
    for course_year, course_data in dict(sorted_courses).items():
        # Semestrlar bo'yicha guruhlangan yo'nalishlarni birlashtirish
        # Avval 1-semestr, keyin 2-semestr va hokazo
        all_directions = {}
        
        # Semestrlar ro'yxatini tartiblash (faqat int bo'lganlar)
        semesters_list = sorted([s for s in course_data.keys() if isinstance(s, int)])
        
        # Semestrlar bo'yicha yo'nalishlarni birlashtirish (faqat guruhlari bo'lganlar)
        for semester in semesters_list:
            for direction_id, direction_data in course_data[semester].items():
                # Faqat guruhlari bo'lgan yo'nalishlarni qo'shish
                if direction_data.get('groups'):
                    all_directions[direction_id] = direction_data
        
        # Semestrlar bo'yicha ajratilgan struktura (template uchun)
        # Faqat yo'nalishlari bo'lgan semestrlarni qo'shish
        semesters_dict = {}
        for semester in semesters_list:
            # Faqat guruhlari bo'lgan yo'nalishlar bo'lishi kerak
            filtered_directions = {
                direction_id: direction_data 
                for direction_id, direction_data in course_data[semester].items()
                if direction_data.get('groups')  # Guruhlari bo'lgan yo'nalishlar
            }
            if filtered_directions:  # Faqat bo'sh bo'lmagan semestrlarni qo'shish
                semesters_dict[semester] = filtered_directions
        
        # semesters_list ni faqat semesters_dict da mavjud bo'lgan semestrlar bilan yangilash
        filtered_semesters_list = sorted([s for s in semesters_list if s in semesters_dict])
        
        formatted_courses_dict[course_year] = {
            'directions': all_directions,  # Barcha semestrlar birlashtirilgan
            'semesters': semesters_dict,  # Semestrlar bo'yicha ajratilgan (template uchun)
            'semesters_list': filtered_semesters_list,  # Faqat guruhlari bo'lgan semestrlar ro'yxati
            'total_directions': course_data.get('total_directions', len(all_directions)),
            'total_groups': course_data.get('total_groups', 0),
            'total_students': course_data.get('total_students', 0)
        }
    
    # Fakultetdagi barcha yo'nalishlarni popup uchun olish
    all_faculty_directions = Direction.query.filter_by(faculty_id=faculty.id).order_by(
        Direction.course_year, 
        Direction.semester, 
        Direction.name
    ).all()
    
    return render_template('dean/courses.html', 
                         faculty=faculty,
                         courses_dict=formatted_courses_dict,
                         all_directions=all_faculty_directions)


# ==================== O'QITUVCHI-FAN BIRIKTIRISH ====================
@bp.route('/assignments')
@login_required
@dean_required
def teacher_assignments():
    faculty = Faculty.query.get(current_user.faculty_id)
    if not faculty:
        flash("Sizga fakultet biriktirilmagan", 'error')
        return redirect(url_for('main.dashboard'))
    
    # Fakultetdagi fanlar uchun biriktirmalar (guruhlar orqali)
    assignments = TeacherSubject.query.join(Group).join(Subject).filter(
        Group.faculty_id == faculty.id
    ).order_by(Subject.code).all()
    
    return render_template('dean/teacher_assignments.html', faculty=faculty, assignments=assignments)


@bp.route('/assignments/create', methods=['GET', 'POST'])
@login_required
@dean_required
def create_assignment():
    faculty = Faculty.query.get(current_user.faculty_id)
    if not faculty:
        flash("Sizga fakultet biriktirilmagan", 'error')
        return redirect(url_for('main.dashboard'))
    
    # Fanlarni guruhlar orqali olish
    subjects = Subject.query.join(TeacherSubject).join(Group).filter(
        Group.faculty_id == faculty.id
    ).distinct().order_by(Subject.code).all()
    groups = faculty.groups.order_by(Group.name).all()
    teachers = User.query.filter_by(role='teacher').order_by(User.full_name).all()
    
    if request.method == 'POST':
        teacher_id = request.form.get('teacher_id', type=int)
        subject_id = request.form.get('subject_id', type=int)
        group_id = request.form.get('group_id', type=int)
        academic_year = request.form.get('academic_year')
        semester = request.form.get('semester', 1, type=int)
        
        lesson_type = request.form.get('lesson_type', 'maruza')
        
        # Mavjudligini tekshirish (xuddi shu tur uchun)
        existing = TeacherSubject.query.filter_by(
            subject_id=subject_id,
            group_id=group_id,
            lesson_type=lesson_type,
            academic_year=academic_year,
            semester=semester
        ).first()
        
        if existing:
            lesson_type_display = "Maruza" if lesson_type == 'maruza' else "Amaliyot"
            flash(f"Bu fan uchun bu guruhga {lesson_type_display} bo'limi uchun allaqachon o'qituvchi biriktirilgan", 'error')
            return render_template('dean/create_assignment.html', 
                                 faculty=faculty, subjects=subjects, groups=groups, teachers=teachers)
        
        assignment = TeacherSubject(
            teacher_id=teacher_id,
            subject_id=subject_id,
            group_id=group_id,
            lesson_type=lesson_type,
            academic_year=academic_year,
            semester=semester,
            assigned_by=current_user.id
        )
        db.session.add(assignment)
        db.session.commit()
        
        teacher = User.query.get(teacher_id)
        subject = Subject.query.get(subject_id)
        group = Group.query.get(group_id)
        flash(f"{teacher.full_name} {subject.name} faniga {group.name} guruhi uchun biriktirildi", 'success')
        return redirect(url_for('dean.teacher_assignments'))
    
    return render_template('dean/create_assignment.html', 
                         faculty=faculty, subjects=subjects, groups=groups, teachers=teachers)


@bp.route('/assignments/<int:id>/delete', methods=['POST'])
@login_required
@dean_required
def delete_assignment(id):
    assignment = TeacherSubject.query.get_or_404(id)
    
    # Faqat o'z fakultetidagi biriktirmalarni o'chirishi mumkin
    if assignment.subject.faculty_id != current_user.faculty_id:
        flash("Sizda bu biriktirmani o'chirish huquqi yo'q", 'error')
        return redirect(url_for('dean.teacher_assignments'))
    
    db.session.delete(assignment)
    db.session.commit()
    flash("Biriktirma o'chirildi", 'success')
    
    return redirect(url_for('dean.teacher_assignments'))


# ==================== TALABALAR ====================
@bp.route('/students')
@login_required
@dean_required
def students():
    """Dekan uchun talabalar (faqat o'z fakulteti doirasida)"""
    from app.models import Direction
    from datetime import datetime
    
    faculty = Faculty.query.get(current_user.faculty_id)
    if not faculty:
        flash("Sizga fakultet biriktirilmagan", 'error')
        return redirect(url_for('main.dashboard'))
    
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '')
    course_year = request.args.get('course', type=int)
    semester = request.args.get('semester', type=int)
    education_type = request.args.get('education_type', '')
    direction_id = request.args.get('direction', type=int)
    group_id = request.args.get('group', type=int)
    
    # Dekan uchun faqat o'z fakultetidagi guruhlar
    faculty_group_ids = [g.id for g in faculty.groups.all()]
    
    query = User.query.filter(
        User.role == 'student',
        User.group_id.in_(faculty_group_ids)
    )
    
    # Qidiruv - kengaytirilgan
    if search:
        query = query.filter(
            (User.full_name.ilike(f'%{search}%')) |
            (User.login.ilike(f'%{search}%')) |
            (User.passport_number.ilike(f'%{search}%')) |
            (User.pinfl.ilike(f'%{search}%')) |
            (User.phone.ilike(f'%{search}%')) |
            (User.email.ilike(f'%{search}%')) |
            (User.student_id.ilike(f'%{search}%'))
        )
    
    # Filtrlash (faqat o'z fakulteti doirasida)
    if group_id:
        # Guruh tanlangan bo'lsa, faqat shu guruhni tekshirish
        if group_id in faculty_group_ids:
            query = query.filter(User.group_id == group_id)
        else:
            query = query.filter(User.id == -1)  # Hech narsa topilmaydi
    elif direction_id:
        # Yo'nalish bo'yicha filtrlash (faqat o'z fakultetidagi yo'nalishlar)
        direction = Direction.query.get(direction_id)
        if direction and direction.faculty_id == faculty.id:
            group_ids = [g.id for g in Group.query.filter_by(direction_id=direction_id).all() if g.id in faculty_group_ids]
            if group_ids:
                query = query.filter(User.group_id.in_(group_ids))
            else:
                query = query.filter(User.id == -1)
        else:
            query = query.filter(User.id == -1)
    elif education_type:
        # Ta'lim shakli bo'yicha filtrlash (faqat o'z fakulteti doirasida)
        group_ids = [g.id for g in Group.query.filter_by(education_type=education_type).all() if g.id in faculty_group_ids]
        if group_ids:
            query = query.filter(User.group_id.in_(group_ids))
        else:
            query = query.filter(User.id == -1)
    elif semester:
        # Semestr bo'yicha filtrlash (faqat o'z fakulteti doirasida)
        direction_ids = [d.id for d in Direction.query.filter_by(faculty_id=faculty.id, semester=semester).all()]
        if direction_ids:
            group_ids = [g.id for g in Group.query.filter(Group.direction_id.in_(direction_ids)).all() if g.id in faculty_group_ids]
            if group_ids:
                query = query.filter(User.group_id.in_(group_ids))
            else:
                query = query.filter(User.id == -1)
        else:
            query = query.filter(User.id == -1)
    elif course_year:
        # Kurs bo'yicha filtrlash (faqat o'z fakulteti doirasida)
        group_ids = [g.id for g in Group.query.filter_by(faculty_id=faculty.id, course_year=course_year).all()]
        if group_ids:
            query = query.filter(User.group_id.in_(group_ids))
        else:
            query = query.filter(User.id == -1)
    
    students = query.order_by(User.full_name).paginate(page=page, per_page=20)
    
    # Filtrlar uchun ma'lumotlar (faqat o'z fakulteti doirasida)
    groups = Group.query.filter_by(faculty_id=faculty.id).order_by(Group.name).all()
    directions = Direction.query.filter_by(faculty_id=faculty.id).order_by(Direction.code, Direction.name).all()
    
    # JavaScript uchun guruhlar ma'lumotlari (JSON formatida)
    groups_json = [{
        'id': g.id,
        'name': g.name,
        'faculty_id': g.faculty_id,
        'course_year': g.course_year,
        'direction_id': g.direction_id,
        'education_type': g.education_type
    } for g in groups]
    
    # JavaScript uchun ma'lumotlar (JSON formatida) - faqat o'z fakulteti uchun
    # Fakultet -> Kurslar
    faculty_courses = {}
    courses_set = set()
    for group in groups:
        if group.course_year:
            courses_set.add(group.course_year)
    faculty_courses[faculty.id] = sorted(list(courses_set))
    
    # Fakultet + Kurs -> Semestrlar
    faculty_course_semesters = {}
    faculty_course_semesters[faculty.id] = {}
    for course in range(1, 5):
        semesters_set = set()
        for direction in Direction.query.filter_by(faculty_id=faculty.id, course_year=course).all():
            semesters_set.add(direction.semester)
        if semesters_set:
            faculty_course_semesters[faculty.id][course] = sorted(list(semesters_set))
    
    # Fakultet + Kurs + Semestr -> Ta'lim shakllari
    faculty_course_semester_education_types = {}
    faculty_course_semester_education_types[faculty.id] = {}
    for course in range(1, 5):
        faculty_course_semester_education_types[faculty.id][course] = {}
        for direction in Direction.query.filter_by(faculty_id=faculty.id, course_year=course).all():
            semester = direction.semester
            if semester not in faculty_course_semester_education_types[faculty.id][course]:
                faculty_course_semester_education_types[faculty.id][course][semester] = set()
            faculty_course_semester_education_types[faculty.id][course][semester].add(direction.education_type)
        # Set'larni list'ga o'tkazish
        for semester in faculty_course_semester_education_types[faculty.id][course]:
            faculty_course_semester_education_types[faculty.id][course][semester] = sorted(list(faculty_course_semester_education_types[faculty.id][course][semester]))
    
    # Fakultet + Kurs + Semestr + Ta'lim shakli -> Yo'nalishlar
    faculty_course_semester_education_directions = {}
    faculty_course_semester_education_directions[faculty.id] = {}
    for course in range(1, 5):
        faculty_course_semester_education_directions[faculty.id][course] = {}
        for direction in Direction.query.filter_by(faculty_id=faculty.id, course_year=course).all():
            semester = direction.semester
            education_type = direction.education_type
            if semester not in faculty_course_semester_education_directions[faculty.id][course]:
                faculty_course_semester_education_directions[faculty.id][course][semester] = {}
            if education_type not in faculty_course_semester_education_directions[faculty.id][course][semester]:
                faculty_course_semester_education_directions[faculty.id][course][semester][education_type] = []
            faculty_course_semester_education_directions[faculty.id][course][semester][education_type].append({
                'id': direction.id,
                'code': direction.code,
                'name': direction.name
            })
        # Yo'nalishlarni tartiblash
        for semester in faculty_course_semester_education_directions[faculty.id][course]:
            for education_type in faculty_course_semester_education_directions[faculty.id][course][semester]:
                faculty_course_semester_education_directions[faculty.id][course][semester][education_type].sort(key=lambda x: (x['code'], x['name']))
    
    # Yo'nalish -> Guruhlar
    direction_groups = {}
    for direction in directions:
        direction_groups[direction.id] = []
        for group in Group.query.filter_by(direction_id=direction.id).all():
            if group.id in faculty_group_ids:
                direction_groups[direction.id].append({
                    'id': group.id,
                    'name': group.name
                })
        direction_groups[direction.id].sort(key=lambda x: x['name'])
    
    # Teskari filtrlash uchun qo'shimcha ma'lumotlar (faqat o'z fakulteti uchun)
    # Kurs -> Fakultetlar (biz uchun faqat bitta fakultet)
    course_faculties = {}
    for course in range(1, 5):
        if course in courses_set:
            course_faculties[course] = [faculty.id]
    
    # Semestr -> Kurslar
    semester_courses = {}
    for direction in directions:
        semester = direction.semester
        course = direction.course_year
        if semester not in semester_courses:
            semester_courses[semester] = set()
        semester_courses[semester].add(course)
    for semester in semester_courses:
        semester_courses[semester] = sorted(list(semester_courses[semester]))
    
    # Fakultet + Semestr -> Kurslar
    faculty_semester_courses = {}
    faculty_semester_courses[faculty.id] = {}
    for direction in directions:
        semester = direction.semester
        course = direction.course_year
        if semester not in faculty_semester_courses[faculty.id]:
            faculty_semester_courses[faculty.id][semester] = set()
        faculty_semester_courses[faculty.id][semester].add(course)
    for semester in faculty_semester_courses[faculty.id]:
        faculty_semester_courses[faculty.id][semester] = sorted(list(faculty_semester_courses[faculty.id][semester]))
    
    # Ta'lim shakli -> Semestrlar
    education_type_semesters = {}
    for direction in directions:
        education_type = direction.education_type
        semester = direction.semester
        if education_type not in education_type_semesters:
            education_type_semesters[education_type] = set()
        education_type_semesters[education_type].add(semester)
    for et in education_type_semesters:
        education_type_semesters[et] = sorted(list(education_type_semesters[et]))
    
    # Fakultet + Kurs + Ta'lim shakli -> Semestrlar
    faculty_course_education_semesters = {}
    faculty_course_education_semesters[faculty.id] = {}
    for course in range(1, 5):
        faculty_course_education_semesters[faculty.id][course] = {}
        for direction in Direction.query.filter_by(faculty_id=faculty.id, course_year=course).all():
            education_type = direction.education_type
            semester = direction.semester
            if education_type not in faculty_course_education_semesters[faculty.id][course]:
                faculty_course_education_semesters[faculty.id][course][education_type] = set()
            faculty_course_education_semesters[faculty.id][course][education_type].add(semester)
        for et in faculty_course_education_semesters[faculty.id][course]:
            faculty_course_education_semesters[faculty.id][course][et] = sorted(list(faculty_course_education_semesters[faculty.id][course][et]))
    
    # Yo'nalish -> Ta'lim shakllari
    direction_education_types = {}
    for direction in directions:
        direction_education_types[direction.id] = direction.education_type
    
    # Fakultet + Kurs -> Guruhlar
    faculty_course_groups = {}
    faculty_course_groups[faculty.id] = {}
    for course in range(1, 5):
        faculty_course_groups[faculty.id][course] = []
        for group in Group.query.filter_by(faculty_id=faculty.id, course_year=course).all():
            faculty_course_groups[faculty.id][course].append({
                'id': group.id,
                'name': group.name
            })
        faculty_course_groups[faculty.id][course].sort(key=lambda x: x['name'])
    
    # Fakultet + Kurs + Semestr -> Guruhlar
    faculty_course_semester_groups = {}
    faculty_course_semester_groups[faculty.id] = {}
    for course in range(1, 5):
        faculty_course_semester_groups[faculty.id][course] = {}
        for direction in Direction.query.filter_by(faculty_id=faculty.id, course_year=course).all():
            semester = direction.semester
            if semester not in faculty_course_semester_groups[faculty.id][course]:
                faculty_course_semester_groups[faculty.id][course][semester] = []
            for group in Group.query.filter_by(direction_id=direction.id).all():
                if group.id in faculty_group_ids:
                    faculty_course_semester_groups[faculty.id][course][semester].append({
                        'id': group.id,
                        'name': group.name
                    })
        for semester in faculty_course_semester_groups[faculty.id][course]:
            faculty_course_semester_groups[faculty.id][course][semester].sort(key=lambda x: x['name'])
    
    # Fakultet + Kurs + Semestr + Ta'lim shakli -> Guruhlar
    faculty_course_semester_education_groups = {}
    faculty_course_semester_education_groups[faculty.id] = {}
    for course in range(1, 5):
        faculty_course_semester_education_groups[faculty.id][course] = {}
        for direction in Direction.query.filter_by(faculty_id=faculty.id, course_year=course).all():
            semester = direction.semester
            education_type = direction.education_type
            if semester not in faculty_course_semester_education_groups[faculty.id][course]:
                faculty_course_semester_education_groups[faculty.id][course][semester] = {}
            if education_type not in faculty_course_semester_education_groups[faculty.id][course][semester]:
                faculty_course_semester_education_groups[faculty.id][course][semester][education_type] = []
            for group in Group.query.filter_by(direction_id=direction.id).all():
                if group.id in faculty_group_ids:
                    faculty_course_semester_education_groups[faculty.id][course][semester][education_type].append({
                        'id': group.id,
                        'name': group.name
                    })
        for semester in faculty_course_semester_education_groups[faculty.id][course]:
            for et in faculty_course_semester_education_groups[faculty.id][course][semester]:
                faculty_course_semester_education_groups[faculty.id][course][semester][et].sort(key=lambda x: x['name'])
    
    # Guruh -> Yo'nalish, Ta'lim shakli, Semestr, Kurs, Fakultet
    group_info = {}
    for group in groups:
        group_info[group.id] = {
            'faculty_id': group.faculty_id,
            'course_year': group.course_year,
            'education_type': group.education_type,
            'direction_id': group.direction_id
        }
    
    # Yo'nalish ma'lumotlari
    direction_info = {}
    for direction in directions:
        direction_info[direction.id] = {
            'faculty_id': direction.faculty_id,
            'course_year': direction.course_year,
            'semester': direction.semester,
            'education_type': direction.education_type
        }
    
    # Kurslar ro'yxati
    courses = sorted(list(courses_set)) if courses_set else []
    
    # Semestrlarni olish
    semesters = sorted(set([d.semester for d in directions]))
    
    # Ta'lim shakllari
    education_types = sorted(set([g.education_type for g in groups if g.education_type]))
    
    return render_template('dean/students.html', 
                         faculty=faculty, 
                         students=students, 
                         groups=groups,
                         directions=directions,
                         courses=courses,
                         semesters=semesters,
                         education_types=education_types,
                         current_group=group_id,
                         current_course=course_year,
                         current_semester=semester,
                         current_education_type=education_type,
                         current_direction=direction_id,
                         search=search,
                         faculty_courses=faculty_courses,
                         faculty_course_semesters=faculty_course_semesters,
                         faculty_course_semester_education_types=faculty_course_semester_education_types,
                         faculty_course_semester_education_directions=faculty_course_semester_education_directions,
                         direction_groups=direction_groups,
                         course_faculties=course_faculties,
                         semester_courses=semester_courses,
                         faculty_semester_courses=faculty_semester_courses,
                         education_type_semesters=education_type_semesters,
                         faculty_course_education_semesters=faculty_course_education_semesters,
                         direction_education_types=direction_education_types,
                         faculty_course_groups=faculty_course_groups,
                         faculty_course_semester_groups=faculty_course_semester_groups,
                         faculty_course_semester_education_groups=faculty_course_semester_education_groups,
                         group_info=group_info,
                         direction_info=direction_info,
                         groups_json=groups_json)


@bp.route('/students/import', methods=['GET', 'POST'])
@login_required
@dean_required
def import_students():
    """Excel fayldan talabalar import qilish"""
    faculty = Faculty.query.get(current_user.faculty_id)
    if not faculty:
        flash("Sizga fakultet biriktirilmagan", 'error')
        return redirect(url_for('main.dashboard'))
    
    if request.method == 'POST':
        if 'excel_file' not in request.files:
            flash("Fayl tanlanmagan", 'error')
            return redirect(url_for('dean.students'))
        
        file = request.files['excel_file']
        if file.filename == '':
            flash("Fayl tanlanmagan", 'error')
            return redirect(url_for('dean.students'))
        
        if not file.filename.endswith(('.xlsx', '.xls')):
            flash("Faqat Excel fayllar (.xlsx, .xls) qo'llab-quvvatlanadi", 'error')
            return redirect(url_for('dean.students'))
        
        try:
            from app.utils.excel_import import import_students_from_excel
            
            result = import_students_from_excel(file, faculty_id=faculty.id)
            
            if result['success']:
                if result['imported'] > 0:
                    flash(f"{result['imported']} ta talaba muvaffaqiyatli import qilindi", 'success')
                else:
                    flash("Hech qanday talaba import qilinmadi", 'warning')
                
                if result['errors']:
                    error_msg = f"Xatolar ({len(result['errors'])}): " + "; ".join(result['errors'][:5])
                    if len(result['errors']) > 5:
                        error_msg += f" va yana {len(result['errors']) - 5} ta xato"
                    flash(error_msg, 'warning')
            else:
                flash(f"Import xatosi: {result['errors'][0] if result['errors'] else 'Noma`lum xatolik'}", 'error')
                
        except ImportError as e:
            flash(f"Excel import funksiyasi ishlamayapti: {str(e)}", 'error')
        except Exception as e:
            flash(f"Import xatosi: {str(e)}", 'error')
        
        return redirect(url_for('dean.students'))
    
    return render_template('dean/import_students.html', faculty=faculty)


@bp.route('/students/import/sample')
@login_required
@dean_required
def download_sample_import():
    """Talabalar import qilish uchun namuna Excel faylni yuklab berish (dekan)"""
    try:
        from app.utils.excel_import import generate_sample_file
        file_stream = generate_sample_file()
        return send_file(
            file_stream,
            as_attachment=True,
            download_name='talabalar_import_namuna.xlsx',
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
    except Exception as e:
        flash(f"Namuna fayl yaratishda xatolik: {str(e)}", 'error')
        return redirect(url_for('dean.import_students'))


@bp.route('/students/export')
@login_required
@dean_required
def export_students():
    """Dekan uchun talabalar ro'yxatini Excel formatida yuklab olish (faqat o'z fakulteti)"""
    faculty = Faculty.query.get(current_user.faculty_id)
    if not faculty:
        flash("Sizga fakultet biriktirilmagan", 'error')
        return redirect(url_for('main.dashboard'))
    
    try:
        from app.utils.excel_export import create_students_excel
    except ImportError:
        flash("Excel export funksiyasi ishlamayapti. Iltimos, 'pip install openpyxl' buyrug'ini bajaring.", 'error')
        return redirect(url_for('dean.students'))
    
    # Faqat o'z fakultetidagi talabalar
    group_ids = [g.id for g in faculty.groups.all()]
    students = User.query.filter(
        User.role == 'student',
        User.group_id.in_(group_ids)
    ).order_by(User.full_name).all()
    
    excel_file = create_students_excel(students, faculty.name)
    
    filename = f"talabalar_{faculty.name.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    
    return Response(
        excel_file,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )


@bp.route('/students/create', methods=['GET', 'POST'])
@login_required
@dean_required
def create_student():
    """Dekan uchun yangi talaba yaratish (admin versiyasiga o'xshash)"""
    from datetime import datetime
    
    faculty = Faculty.query.get(current_user.faculty_id)
    if not faculty:
        flash("Sizga fakultet biriktirilmagan", 'error')
        return redirect(url_for('main.dashboard'))
    
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        full_name = request.form.get('full_name', '').strip()
        passport_number = request.form.get('passport_number', '').strip()
        phone = request.form.get('phone', '').strip()
        student_id = request.form.get('student_id', '').strip()
        pinfl = request.form.get('pinfl', '').strip()
        birth_date = request.form.get('birth_date', '').strip()
        description = request.form.get('description', '').strip()
        
        # Talaba ID majburiy
        if not student_id:
            flash("Talaba ID majburiy maydon", 'error')
            return render_template('dean/create_student.html', faculty=faculty)
        
        if User.query.filter_by(student_id=student_id).first():
            flash("Bu talaba ID allaqachon mavjud", 'error')
            return render_template('dean/create_student.html', faculty=faculty)
        
        # Pasport seriyasi va raqami majburiy
        if not passport_number:
            flash("Pasport seriyasi va raqami majburiy", 'error')
            return render_template('dean/create_student.html', faculty=faculty)
        
        # Email ixtiyoriy, lekin agar kiritilgan bo'lsa, unikallikni tekshirish
        if email:
            if User.query.filter_by(email=email).first():
                flash("Bu email allaqachon mavjud", 'error')
                return render_template('dean/create_student.html', faculty=faculty)
        
        # Pasport raqamini katta harfga o'zgartirish
        passport_number = passport_number.upper()
        
        # Tug'ilgan sanani parse qilish (yyyy-mm-dd)
        parsed_birth_date = None
        if birth_date:
            try:
                parsed_birth_date = datetime.strptime(birth_date, '%Y-%m-%d').date()
            except ValueError:
                flash("Tug'ilgan sana noto'g'ri formatda (yyyy-mm-dd)", 'error')
                return render_template('dean/create_student.html', faculty=faculty)
        
        # Email maydonini tozalash
        email_value = email.strip() if email and email.strip() else None
        
        student = User(
            full_name=full_name,
            role='student',
            student_id=student_id,
            passport_number=passport_number,
            phone=phone.strip() if phone and phone.strip() else None,
            pinfl=pinfl.strip() if pinfl and pinfl.strip() else None,
            birth_date=parsed_birth_date,
            description=description.strip() if description and description.strip() else None
        )
        
        # Email maydonini alohida o'rnatish (agar bo'sh bo'lsa, o'rnatmaymiz)
        if email_value:
            student.email = email_value
        
        # Parolni pasport raqamiga o'rnatish
        student.set_password(passport_number)
        
        db.session.add(student)
        
        # Commit qilish va agar email NOT NULL xatolik bo'lsa, email maydonini bo'sh qatorga o'zgartirish
        try:
            db.session.commit()
        except Exception as e:
            error_str = str(e).lower()
            if 'email' in error_str and ('not null' in error_str or 'constraint' in error_str):
                # Database'da email NOT NULL bo'lsa, bo'sh qator qo'yamiz
                db.session.rollback()
                student.email = ''  # Bo'sh qator (database NOT NULL constraint uchun)
                db.session.add(student)
                db.session.commit()
            else:
                raise
        
        flash(f"{student.full_name} muvaffaqiyatli yaratildi", 'success')
        return redirect(url_for('dean.students'))
    
    return render_template('dean/create_student.html', faculty=faculty)


@bp.route('/students/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@dean_required
def edit_student(id):
    """Dekan uchun talabani tahrirlash (faqat o'z fakulteti doirasida)"""
    from datetime import datetime
    
    faculty = Faculty.query.get(current_user.faculty_id)
    if not faculty:
        flash("Sizga fakultet biriktirilmagan", 'error')
        return redirect(url_for('main.dashboard'))
    
    student = User.query.get_or_404(id)
    
    # Faqat talaba va shu fakultetga tegishli guruhda bo'lishi kerak (agar guruh bo'lsa)
    if student.role != 'student':
        flash("Bu foydalanuvchi talaba emas", 'error')
        return redirect(url_for('dean.students'))
    
    # Agar talabaning guruh bo'lsa, fakultetni tekshirish
    if student.group and student.group.faculty_id != faculty.id:
        flash("Sizda bu talabani tahrirlash huquqi yo'q", 'error')
        return redirect(url_for('dean.students'))
    
    if request.method == 'POST':
        student_id = request.form.get('student_id', '').strip()
        full_name = request.form.get('full_name', '').strip()
        passport_number = request.form.get('passport_number', '').strip()
        phone = request.form.get('phone', '').strip()
        email = request.form.get('email', '').strip()
        pinfl = request.form.get('pinfl', '').strip()
        birth_date_str = request.form.get('birth_date', '').strip()
        description = request.form.get('description', '').strip()
        
        # Talaba ID majburiy
        if not student_id:
            flash("Talaba ID majburiy maydon", 'error')
            return render_template('dean/edit_student.html', faculty=faculty, student=student)
        
        # Talaba ID unikalligi (boshqa talabada bo'lmasligi kerak)
        existing_student = User.query.filter_by(student_id=student_id).first()
        if existing_student and existing_student.id != student.id:
            flash("Bu talaba ID allaqachon boshqa talabada mavjud", 'error')
            return render_template('dean/edit_student.html', faculty=faculty, student=student)
        
        # Pasport seriyasi va raqami majburiy
        if not passport_number:
            flash("Pasport seriyasi va raqami majburiy", 'error')
            return render_template('dean/edit_student.html', faculty=faculty, student=student)
        
        # Email ixtiyoriy, lekin agar kiritilgan bo'lsa, unikallikni tekshirish
        if email:
            existing_student_with_email = User.query.filter_by(email=email).first()
            if existing_student_with_email and existing_student_with_email.id != student.id:
                flash("Bu email allaqachon boshqa talabada mavjud", 'error')
                return render_template('dean/edit_student.html', faculty=faculty, student=student)
        
        # Pasport raqamini katta harfga o'zgartirish
        passport_number = passport_number.upper()
        
        # Tug'ilgan sanani parse qilish (yyyy-mm-dd)
        if birth_date_str:
            try:
                student.birth_date = datetime.strptime(birth_date_str, '%Y-%m-%d').date()
            except ValueError:
                flash("Tug'ilgan sana noto'g'ri formatda (yyyy-mm-dd)", 'error')
                return render_template('dean/edit_student.html', faculty=faculty, student=student)
        else:
            student.birth_date = None
        
        student.email = email if email else None
        student.full_name = full_name
        student.phone = phone if phone else None
        student.student_id = student_id
        student.passport_number = passport_number
        student.pinfl = pinfl if pinfl else None
        student.description = description if description else None
        
        db.session.commit()
        flash(f"{student.full_name} ma'lumotlari yangilandi", 'success')
        return redirect(url_for('dean.students'))
    
    return render_template('dean/edit_student.html', faculty=faculty, student=student)


@bp.route('/students/<int:id>/toggle', methods=['POST'])
@login_required
@dean_required
def toggle_student_status(id):
    """Talabani bloklash / blokdan chiqarish (dekan faqat o'z fakulteti bo'yicha)"""
    faculty = Faculty.query.get(current_user.faculty_id)
    if not faculty:
        flash("Sizga fakultet biriktirilmagan", 'error')
        return redirect(url_for('main.dashboard'))
    
    student = User.query.get_or_404(id)
    if student.role != 'student' or not student.group or student.group.faculty_id != faculty.id:
        flash("Sizda bu amal uchun huquq yo'q", 'error')
        return redirect(url_for('dean.students'))
    
    student.is_active = not student.is_active
    db.session.commit()
    
    status = "faollashtirildi" if student.is_active else "bloklandi"
    flash(f"Talaba {student.full_name} {status}", 'success')
    return redirect(url_for('dean.students'))


@bp.route('/students/<int:id>/reset-password', methods=['POST'])
@login_required
@dean_required
def reset_student_password(id):
    """Talaba parolini boshlang'ich holatga qaytarish (student123)"""
    faculty = Faculty.query.get(current_user.faculty_id)
    if not faculty:
        flash("Sizga fakultet biriktirilmagan", 'error')
        return redirect(url_for('main.dashboard'))
    
    student = User.query.get_or_404(id)
    if student.role != 'student' or not student.group or student.group.faculty_id != faculty.id:
        flash("Sizda bu amal uchun huquq yo'q", 'error')
        return redirect(url_for('dean.students'))
    
    new_password = 'student123'
    student.set_password(new_password)
    db.session.commit()
    flash(f"{student.full_name} paroli boshlang'ich holatga qaytarildi. Yangi parol: {new_password}", 'success')
    return redirect(url_for('dean.students'))


@bp.route('/students/<int:id>/delete', methods=['POST'])
@login_required
@dean_required
def delete_student(id):
    """Talabani o'chirish"""
    faculty = Faculty.query.get(current_user.faculty_id)
    if not faculty:
        flash("Sizga fakultet biriktirilmagan", 'error')
        return redirect(url_for('main.dashboard'))
    
    student = User.query.get_or_404(id)
    if student.role != 'student':
        flash("Bu foydalanuvchi talaba emas", 'error')
        return redirect(url_for('dean.students'))
    
    # Fakultet tekshiruvi (agar guruh bo'lsa)
    if student.group and student.group.faculty_id != faculty.id:
        flash("Sizda bu amal uchun huquq yo'q", 'error')
        return redirect(url_for('dean.students'))
    
    student_name = student.full_name
    
    # Talabaning to'lovlarini o'chirish
    StudentPayment.query.filter_by(student_id=student.id).delete()
    
    # Talabani o'chirish
    db.session.delete(student)
    db.session.commit()
    flash(f"{student_name} o'chirildi", 'success')
    return redirect(url_for('dean.students'))


# ==================== O'QITUVCHILAR ====================
@bp.route('/teachers')
@login_required
@dean_required
def teachers():
    faculty = Faculty.query.get(current_user.faculty_id)
    if not faculty:
        flash("Sizga fakultet biriktirilmagan", 'error')
        return redirect(url_for('main.dashboard'))
    
    # Fakultetda dars beradigan o'qituvchilar (guruhlar orqali)
    teacher_ids = db.session.query(TeacherSubject.teacher_id).join(Group).filter(
        Group.faculty_id == faculty.id
    ).distinct().all()
    teacher_ids = [t[0] for t in teacher_ids]
    
    # UserRole orqali o'qituvchi roliga ega bo'lgan foydalanuvchilarni ham qo'shish
    from app.models import UserRole
    teacher_role_ids = db.session.query(UserRole.user_id).filter_by(role='teacher').distinct().all()
    teacher_role_ids = [uid[0] for uid in teacher_role_ids]
    
    # Agar UserRole orqali topilmasa, eski usul bilan qidirish
    if not teacher_role_ids:
        teachers_by_role = User.query.filter_by(role='teacher').all()
        teacher_role_ids = [t.id for t in teachers_by_role]
    
    # Agar hali ham topilmasa, get_roles() orqali qidirish
    if not teacher_role_ids:
        all_users = User.query.all()
        teacher_role_ids = [u.id for u in all_users if 'teacher' in u.get_roles()]
    
    # Ikkala ro'yxatni birlashtirish
    all_teacher_ids = list(set(teacher_ids + teacher_role_ids))
    
    teachers = User.query.filter(User.id.in_(all_teacher_ids)).order_by(User.full_name).all() if all_teacher_ids else []
    
    # Har bir o'qituvchining fanlari (guruhlar orqali)
    teacher_subjects = {}
    for teacher in teachers:
        subjects = TeacherSubject.query.filter_by(teacher_id=teacher.id).join(Group).filter(
            Group.faculty_id == faculty.id
        ).all()
        teacher_subjects[teacher.id] = subjects
    
    return render_template('dean/teachers.html', 
                         faculty=faculty, 
                         teachers=teachers,
                         teacher_subjects=teacher_subjects)


# ==================== YO'NALISHLAR ====================
@bp.route('/directions')
@login_required
@dean_required
def directions():
    """Yo'nalishlar sahifasi - courses sahifasiga yo'naltiradi"""
    return redirect(url_for('dean.courses'))


@bp.route('/directions/import', methods=['GET', 'POST'])
@login_required
@dean_required
def import_directions():
    """Excel fayldan yo'nalish va guruhlarni import qilish"""
    faculty = Faculty.query.get(current_user.faculty_id)
    if not faculty:
        flash("Sizga fakultet biriktirilmagan", 'error')
        return redirect(url_for('main.dashboard'))
    
    if request.method == 'POST':
        if 'excel_file' not in request.files:
            flash("Fayl tanlanmagan", 'error')
            return redirect(url_for('dean.import_directions'))
        
        file = request.files['excel_file']
        if file.filename == '':
            flash("Fayl tanlanmagan", 'error')
            return redirect(url_for('dean.import_directions'))
        
        if not file.filename.endswith(('.xlsx', '.xls')):
            flash("Faqat Excel fayllar (.xlsx, .xls) qo'llab-quvvatlanadi", 'error')
            return redirect(url_for('dean.import_directions'))
        
        try:
            from app.utils.excel_import import import_directions_from_excel
            result = import_directions_from_excel(file, faculty_id=faculty.id)
            
            if result['success']:
                d_count = result.get('imported_directions', 0)
                g_count = result.get('imported_groups', 0)
                if d_count or g_count:
                    flash(f"{d_count} ta yo'nalish va {g_count} ta guruh import qilindi", 'success')
                else:
                    flash("Hech qanday yo'nalish yoki guruh import qilinmadi", 'warning')
                
                errors = result.get('errors', [])
                if errors:
                    msg = f"Xatolar ({len(errors)}): " + "; ".join(errors[:5])
                    if len(errors) > 5:
                        msg += f" va yana {len(errors) - 5} ta xato"
                    flash(msg, 'warning')
            else:
                errors = result.get('errors', [])
                flash(errors[0] if errors else "Import xatosi", 'error')
        
        except ImportError as e:
            flash(f"Excel import funksiyasi ishlamayapti: {str(e)}", 'error')
        except Exception as e:
            flash(f"Import xatosi: {str(e)}", 'error')
        
        return redirect(url_for('dean.directions'))
    
    return render_template('dean/import_directions.html', faculty=faculty)


@bp.route('/directions/create', methods=['GET', 'POST'])
@login_required
@dean_required
def create_direction():
    faculty = Faculty.query.get(current_user.faculty_id)
    if not faculty:
        flash("Sizga fakultet biriktirilmagan", 'error')
        return redirect(url_for('main.dashboard'))
    
    if request.method == 'POST':
        name = request.form.get('name')
        code = request.form.get('code', '').upper()
        description = request.form.get('description', '')
        course_year = request.form.get('course_year', type=int)
        semester = request.form.get('semester', type=int)
        education_type = request.form.get('education_type', 'kunduzgi')
        enrollment_year = request.form.get('enrollment_year', type=int)
        
        # Validatsiya
        if not name or not code:
            flash("Yo'nalish nomi va kodi majburiy", 'error')
            return render_template('dean/create_direction.html', faculty=faculty)
        
        if not course_year or course_year < 1 or course_year > 5:
            flash("Kurs 1-5 oralig'ida bo'lishi kerak", 'error')
            return render_template('dean/create_direction.html', faculty=faculty)
        
        if not semester or semester < 1 or semester > 10:
            flash("Semestr 1-10 oralig'ida bo'lishi kerak", 'error')
            return render_template('dean/create_direction.html', faculty=faculty)
        
        if not enrollment_year or enrollment_year < 2000 or enrollment_year > 2100:
            flash("Qabul yili to'g'ri kiriting (2000-2100)", 'error')
            return render_template('dean/create_direction.html', faculty=faculty)
        
        # Ta'lim shakli validatsiyasi
        valid_education_types = ['kunduzgi', 'sirtqi', 'masofaviy', 'kechki']
        if education_type not in valid_education_types:
            flash("Noto'g'ri ta'lim shakli tanlandi", 'error')
            return render_template('dean/create_direction.html', faculty=faculty)
        
        # Kod takrorlanmasligini tekshirish (fakultet, kurs, semestr va ta'lim shakli bo'yicha)
        existing = Direction.query.filter_by(
            code=code,
            faculty_id=faculty.id,
            course_year=course_year,
            semester=semester,
            education_type=education_type
        ).first()
        
        if existing:
            flash("Bu kod, kurs, semestr va ta'lim shakli bilan yo'nalish allaqachon mavjud", 'error')
            return render_template('dean/create_direction.html', faculty=faculty)
        
        direction = Direction(
            name=name,
            code=code,
            description=description,
            faculty_id=faculty.id,
            course_year=course_year,
            semester=semester,
            education_type=education_type,
            enrollment_year=enrollment_year
        )
        db.session.add(direction)
        db.session.commit()
        
        flash("Yo'nalish muvaffaqiyatli yaratildi", 'success')
        return redirect(url_for('dean.courses'))
    
    from datetime import datetime as dt
    return render_template('dean/create_direction.html', faculty=faculty, datetime=dt)


@bp.route('/directions/<int:id>')
@login_required
@dean_required
def direction_detail(id):
    """Yo'nalish detail sahifasi - ichidagi guruhlar"""
    direction = Direction.query.get_or_404(id)
    
    # Fakultet tekshiruvi
    if direction.faculty_id != current_user.faculty_id:
        flash("Sizda bu sahifaga kirish huquqi yo'q", 'error')
        return redirect(url_for('dean.index'))
    
    # Bu yo'nalishga biriktirilgan guruhlar
    groups = Group.query.filter_by(direction_id=direction.id).order_by(Group.course_year, Group.name).all()
    
    # Har bir guruh uchun talabalar soni
    group_stats = {}
    for group in groups:
        group_stats[group.id] = group.students.count()
    
    # Biriktirilmagan guruhlar (yo'nalishga qo'shish uchun)
    faculty = Faculty.query.get(current_user.faculty_id)
    unassigned_groups = Group.query.filter_by(faculty_id=faculty.id, direction_id=None).order_by(Group.name).all()
    
    return render_template('dean/direction_detail.html',
                         direction=direction,
                         groups=groups,
                         group_stats=group_stats,
                         unassigned_groups=unassigned_groups)


@bp.route('/directions/<int:id>/assign-groups', methods=['POST'])
@login_required
@dean_required
def assign_groups_to_direction(id):
    direction = Direction.query.get_or_404(id)
    
    # Fakultet tekshiruvi
    if direction.faculty_id != current_user.faculty_id:
        flash("Sizda bu amal uchun ruxsat yo'q", 'error')
        return redirect(url_for('dean.directions'))
    
    # Tanlangan guruhlar
    selected_group_ids = request.form.getlist('group_ids')
    selected_group_ids = [int(gid) for gid in selected_group_ids if gid]
    
    # Faqat biriktirilmagan guruhlar (direction_id == None)
    faculty = Faculty.query.get(current_user.faculty_id)
    unassigned_groups = Group.query.filter_by(faculty_id=faculty.id, direction_id=None).all()
    unassigned_group_ids = [g.id for g in unassigned_groups]
    
    # Tanlangan guruhlarni yo'nalishga biriktirish
    for group_id in unassigned_group_ids:
        if group_id in selected_group_ids:
            group = Group.query.get(group_id)
            group.direction_id = direction.id
    
    db.session.commit()
    flash("Guruhlar yo'nalishga biriktirildi", 'success')
    return redirect(url_for('dean.direction_detail', id=id))


@bp.route('/directions/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@dean_required
def edit_direction(id):
    direction = Direction.query.get_or_404(id)
    
    # Fakultet tekshiruvi
    if direction.faculty_id != current_user.faculty_id:
        flash("Sizda bu amal uchun ruxsat yo'q", 'error')
        return redirect(url_for('dean.directions'))
    
    if request.method == 'POST':
        name = request.form.get('name')
        code = request.form.get('code', '').upper()
        description = request.form.get('description', '')
        course_year = request.form.get('course_year', type=int)
        semester = request.form.get('semester', type=int)
        education_type = request.form.get('education_type', 'kunduzgi')
        enrollment_year = request.form.get('enrollment_year', type=int)
        
        if not name or not code:
            flash("Yo'nalish nomi va kodi to'ldirilishi shart", 'error')
            return render_template('dean/edit_direction.html', direction=direction)
        
        if not course_year or course_year < 1 or course_year > 5:
            flash("Kurs 1-5 oralig'ida bo'lishi kerak", 'error')
            return render_template('dean/edit_direction.html', direction=direction)
        
        if not semester or semester < 1 or semester > 10:
            flash("Semestr 1-10 oralig'ida bo'lishi kerak", 'error')
            return render_template('dean/edit_direction.html', direction=direction)
        
        if not enrollment_year or enrollment_year < 2000 or enrollment_year > 2100:
            flash("Qabul yili to'g'ri kiriting (2000-2100)", 'error')
            return render_template('dean/edit_direction.html', direction=direction)
        
        # Ta'lim shakli validatsiyasi
        valid_education_types = ['kunduzgi', 'sirtqi', 'masofaviy', 'kechki']
        if education_type not in valid_education_types:
            flash("Noto'g'ri ta'lim shakli tanlandi", 'error')
            return render_template('dean/edit_direction.html', direction=direction)
        
        # Kod takrorlanmasligini tekshirish (o'z kodini, kurs, semestr va ta'lim shaklini hisobga olmasdan)
        existing = Direction.query.filter(
            Direction.faculty_id == current_user.faculty_id,
            Direction.code == code,
            Direction.course_year == course_year,
            Direction.semester == semester,
            Direction.education_type == education_type,
            Direction.id != id
        ).first()
        if existing:
            flash("Bu kod, kurs, semestr va ta'lim shakli bilan yo'nalish allaqachon mavjud", 'error')
            return render_template('dean/edit_direction.html', direction=direction)
        
        direction.name = name
        direction.code = code
        direction.description = description
        direction.course_year = course_year
        direction.semester = semester
        direction.education_type = education_type
        direction.enrollment_year = enrollment_year
        
        db.session.commit()
        
        flash("Yo'nalish yangilandi", 'success')
        return redirect(url_for('dean.courses'))
    
    from datetime import datetime as dt
    return render_template('dean/edit_direction.html', direction=direction, datetime=dt)


@bp.route('/directions/<int:id>/delete', methods=['POST'])
@login_required
@dean_required
def delete_direction(id):
    direction = Direction.query.get_or_404(id)
    
    # Fakultet tekshiruvi
    if direction.faculty_id != current_user.faculty_id:
        flash("Sizda bu amal uchun ruxsat yo'q", 'error')
        return redirect(url_for('dean.courses'))
    
    # Guruhlar borligini tekshirish
    groups = direction.groups.all()
    if groups:
        # Har bir guruhda talabalar borligini tekshirish
        total_students = 0
        for group in groups:
            total_students += group.students.count()
        
        if total_students > 0:
            flash(f"Yo'nalishda {len(groups)} ta guruh va {total_students} ta talaba mavjud. O'chirish mumkin emas", 'error')
        else:
            flash(f"Yo'nalishda {len(groups)} ta guruh mavjud. Avval guruhlarni o'chiring yoki boshqa yo'nalishga o'tkazing", 'error')
    else:
        db.session.delete(direction)
        db.session.commit()
        flash("Yo'nalish o'chirildi", 'success')
    
    return redirect(url_for('dean.courses'))


# ==================== O'QUV REJA ====================
@bp.route('/directions/<int:id>/curriculum')
@login_required
@dean_required
def direction_curriculum(id):
    """Yo'nalish o'quv rejasi"""
    direction = Direction.query.get_or_404(id)
    
    # Fakultet tekshiruvi
    if direction.faculty_id != current_user.faculty_id:
        flash("Sizda bu sahifaga kirish huquqi yo'q", 'error')
        return redirect(url_for('dean.courses'))
    
    # Barcha fanlar
    all_subjects = Subject.query.order_by(Subject.name).all()
    
    # O'quv rejadagi fanlar (semestr bo'yicha guruhlangan)
    curriculum_by_semester = {}
    semester_totals = {}  # Har bir semestr uchun jami soat va kredit
    semester_auditoriya = {}  # Har bir semestr uchun auditoriya soatlari
    semester_mustaqil = {}  # Har bir semestr uchun mustaqil ta'lim soatlari
    total_hours = 0
    total_credits = 0
    
    for item in direction.curriculum_items.join(Subject).order_by(
        DirectionCurriculum.semester,
        Subject.name
    ).all():
        semester = item.semester
        if semester not in curriculum_by_semester:
            curriculum_by_semester[semester] = []
            semester_totals[semester] = {'hours': 0, 'credits': 0}
            semester_auditoriya[semester] = {'m': 0, 'a': 0, 'l': 0, 's': 0, 'k': 0}
            semester_mustaqil[semester] = 0
        curriculum_by_semester[semester].append(item)
        
        # Auditoriya soatlari
        semester_auditoriya[semester]['m'] += (item.hours_maruza or 0)
        semester_auditoriya[semester]['a'] += (item.hours_amaliyot or 0)
        semester_auditoriya[semester]['l'] += (item.hours_laboratoriya or 0)
        semester_auditoriya[semester]['s'] += (item.hours_seminar or 0)
        semester_auditoriya[semester]['k'] += (item.hours_kurs_ishi or 0)
        
        # Mustaqil ta'lim
        semester_mustaqil[semester] += (item.hours_mustaqil or 0)
        
        # Semestr jami soat va kreditni hisoblash (K qo'shilmaydi)
        item_hours = (item.hours_maruza or 0) + (item.hours_amaliyot or 0) + \
                    (item.hours_laboratoriya or 0) + (item.hours_seminar or 0) + \
                    (item.hours_mustaqil or 0)
        item_credits = item_hours / 30
        
        semester_totals[semester]['hours'] += item_hours
        semester_totals[semester]['credits'] += item_credits
        
        # Umumiy yuklamani hisoblash
        total_hours += item_hours
        total_credits += item_credits
    
    return render_template('dean/direction_curriculum.html',
                         direction=direction,
                         all_subjects=all_subjects,
                         curriculum_by_semester=curriculum_by_semester,
                         semester_totals=semester_totals,
                         semester_auditoriya=semester_auditoriya,
                         semester_mustaqil=semester_mustaqil,
                         total_hours=total_hours,
                         total_credits=total_credits)


@bp.route('/directions/<int:id>/curriculum/export')
@login_required
@dean_required
def export_curriculum(id):
    """O'quv rejani Excel formatida export qilish"""
    from app.utils.excel_export import create_curriculum_excel
    
    direction = Direction.query.get_or_404(id)
    
    # Fakultet tekshiruvi
    if direction.faculty_id != current_user.faculty_id:
        flash("Sizda bu sahifaga kirish huquqi yo'q", 'error')
        return redirect(url_for('dean.courses'))
    
    # O'quv rejadagi barcha elementlar
    curriculum_items = direction.curriculum_items.join(Subject).order_by(
        DirectionCurriculum.semester,
        Subject.name
    ).all()
    
    excel_file = create_curriculum_excel(direction, curriculum_items)
    
    filename = f"oquv_reja_{direction.code}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return send_file(
        excel_file,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=filename
    )


@bp.route('/directions/<int:id>/curriculum/import', methods=['GET', 'POST'])
@login_required
@dean_required
def import_curriculum(id):
    """O'quv rejani Excel fayldan import qilish"""
    from app.utils.excel_import import import_curriculum_from_excel
    
    direction = Direction.query.get_or_404(id)
    
    # Fakultet tekshiruvi
    if direction.faculty_id != current_user.faculty_id:
        flash("Sizda bu sahifaga kirish huquqi yo'q", 'error')
        return redirect(url_for('dean.courses'))
    
    if request.method == 'POST':
        if 'file' not in request.files:
            flash("Fayl tanlanmagan", 'error')
            return redirect(url_for('dean.direction_curriculum', id=id))
        
        file = request.files['file']
        if file.filename == '':
            flash("Fayl tanlanmagan", 'error')
            return redirect(url_for('dean.direction_curriculum', id=id))
        
        if not file.filename.endswith(('.xlsx', '.xls')):
            flash("Faqat .xlsx yoki .xls formatidagi fayllar qabul qilinadi", 'error')
            return redirect(url_for('dean.direction_curriculum', id=id))
        
        result = import_curriculum_from_excel(file, direction.id)
        
        if result['success']:
            if result['imported'] > 0 or result['updated'] > 0:
                message = f"Muvaffaqiyatli! {result['imported']} ta yangi qo'shildi, {result['updated']} ta yangilandi."
                if result['errors']:
                    message += f" {len(result['errors'])} ta xatolik yuz berdi."
                flash(message, 'success' if not result['errors'] else 'warning')
            else:
                flash("Hech qanday o'zgarish kiritilmadi", 'info')
            
            if result['errors']:
                for error in result['errors'][:10]:  # Faqat birinchi 10 ta xatolikni ko'rsatish
                    flash(error, 'error')
        else:
            flash(f"Import qilishda xatolik: {', '.join(result['errors'])}", 'error')
        
        return redirect(url_for('dean.direction_curriculum', id=id))
    
    return render_template('dean/import_curriculum.html', direction=direction)


@bp.route('/directions/<int:id>/subjects', methods=['GET', 'POST'])
@login_required
@dean_required
def direction_subjects(id):
    """Yo'nalish fanlari sahifasi - jadval ko'rinishida"""
    direction = Direction.query.get_or_404(id)
    
    # Fakultet tekshiruvi
    if direction.faculty_id != current_user.faculty_id:
        flash("Sizda bu sahifaga kirish huquqi yo'q", 'error')
        return redirect(url_for('dean.courses'))
    
    # POST so'rov - o'qituvchilarni saqlash
    if request.method == 'POST':
        semester = request.form.get('semester', type=int)
        if not semester:
            flash("Semestr tanlanmagan", 'error')
            return redirect(url_for('dean.direction_subjects', id=id))
        
        # Yo'nalishga biriktirilgan guruhlar
        groups = Group.query.filter_by(direction_id=direction.id).all()
        if not groups:
            flash("Yo'nalishda guruhlar mavjud emas", 'error')
            return redirect(url_for('dean.direction_subjects', id=id))
        
        # Semestrdagi barcha fanlar uchun o'qituvchilarni yangilash
        for item in direction.curriculum_items.filter_by(semester=semester).all():
            # Maruza o'qituvchisi
            maruza_teacher_id = request.form.get(f'teacher_maruza_{item.id}', type=int)
            teacher_subject = TeacherSubject.query.filter_by(
                subject_id=item.subject_id,
                group_id=groups[0].id,
                lesson_type='maruza'
            ).first()
            
            if maruza_teacher_id:
                # Mavjud biriktirishni topish yoki yangi yaratish
                if teacher_subject:
                    teacher_subject.teacher_id = maruza_teacher_id
                else:
                    teacher_subject = TeacherSubject(
                        teacher_id=maruza_teacher_id,
                        subject_id=item.subject_id,
                        group_id=groups[0].id,
                        lesson_type='maruza'
                    )
                    db.session.add(teacher_subject)
            else:
                # Agar o'qituvchi tanlanmagan bo'lsa, mavjud biriktirishni o'chirish
                if teacher_subject:
                    db.session.delete(teacher_subject)
            
            # Amaliyot o'qituvchisi (faqat amaliyot soatlari bo'lsa)
            if (item.hours_amaliyot or 0) > 0 or (item.hours_laboratoriya or 0) > 0:
                amaliyot_teacher_id = request.form.get(f'teacher_amaliyot_{item.id}', type=int)
                teacher_subject = TeacherSubject.query.filter_by(
                    subject_id=item.subject_id,
                    group_id=groups[0].id,
                    lesson_type='amaliyot'
                ).first()
                
                if amaliyot_teacher_id:
                    if teacher_subject:
                        teacher_subject.teacher_id = amaliyot_teacher_id
                    else:
                        teacher_subject = TeacherSubject(
                            teacher_id=amaliyot_teacher_id,
                            subject_id=item.subject_id,
                            group_id=groups[0].id,
                            lesson_type='amaliyot'
                        )
                        db.session.add(teacher_subject)
                else:
                    # Agar o'qituvchi tanlanmagan bo'lsa, mavjud biriktirishni o'chirish
                    if teacher_subject:
                        db.session.delete(teacher_subject)
            
            # Seminar o'qituvchisi (faqat seminar soatlari bo'lsa)
            if (item.hours_seminar or 0) > 0:
                seminar_teacher_id = request.form.get(f'teacher_seminar_{item.id}', type=int)
                # Seminar uchun alohida TeacherSubject yaratish yoki topish
                # Seminar uchun 'seminar' lesson_type ishlatamiz yoki alohida identifikator
                teacher_subject = TeacherSubject.query.filter_by(
                    subject_id=item.subject_id,
                    group_id=groups[0].id,
                    lesson_type='seminar'
                ).first()
                
                # Agar 'seminar' lesson_type topilmasa, amaliyot turidagi va seminar soatlari bo'lganini qidirish
                if not teacher_subject and (item.hours_seminar or 0) > 0:
                    # Seminar uchun alohida yozuv yaratish
                    pass
                
                if seminar_teacher_id:
                    if teacher_subject:
                        teacher_subject.teacher_id = seminar_teacher_id
                    else:
                        # Seminar uchun 'seminar' lesson_type bilan yaratish
                        teacher_subject = TeacherSubject(
                            teacher_id=seminar_teacher_id,
                            subject_id=item.subject_id,
                            group_id=groups[0].id,
                            lesson_type='seminar'
                        )
                        db.session.add(teacher_subject)
                else:
                    # Agar o'qituvchi tanlanmagan bo'lsa, mavjud biriktirishni o'chirish
                    if teacher_subject:
                        db.session.delete(teacher_subject)
        
        db.session.commit()
        flash(f"{semester}-semestr o'qituvchilari muvaffaqiyatli saqlandi", 'success')
        return redirect(url_for('dean.direction_subjects', id=id))
    
    # Yo'nalishga biriktirilgan guruhlar
    groups = Group.query.filter_by(direction_id=direction.id).all()
    
    # O'quv rejadagi fanlar (semestr bo'yicha guruhlangan)
    subjects_by_semester = {}
    
    for item in direction.curriculum_items.join(Subject).order_by(DirectionCurriculum.semester, Subject.name).all():
        semester = item.semester
        if semester not in subjects_by_semester:
            subjects_by_semester[semester] = []
        
        # Har bir fan uchun dars turlarini va o'qituvchilarni olish
        subject_data = {
            'subject': item.subject,
            'curriculum_item': item,  # Curriculum item ID uchun
            'lessons': []
        }
        
        # Maruza
        if item.hours_maruza and item.hours_maruza > 0:
            # O'qituvchini topish (birinchi guruhdan)
            teacher = None
            if groups:
                teacher_subject = TeacherSubject.query.filter_by(
                    subject_id=item.subject_id,
                    group_id=groups[0].id,
                    lesson_type='maruza'
                ).first()
                if teacher_subject:
                    teacher = teacher_subject.teacher
            
            subject_data['lessons'].append({
                'type': 'Maruza',
                'hours': item.hours_maruza,
                'teacher': teacher
            })
        
        # Amaliyot (amaliyot + lobaratoriya, kurs ishi qo'shilmaydi)
        amaliyot_hours = (item.hours_amaliyot or 0) + (item.hours_laboratoriya or 0)
        if amaliyot_hours > 0:
            # O'qituvchini topish
            teacher = None
            if groups:
                teacher_subject = TeacherSubject.query.filter_by(
                    subject_id=item.subject_id,
                    group_id=groups[0].id,
                    lesson_type='amaliyot'
                ).first()
                if teacher_subject:
                    teacher = teacher_subject.teacher
            
            subject_data['lessons'].append({
                'type': 'Amaliyot',
                'hours': amaliyot_hours,
                'teacher': teacher
            })
        # Agar amaliyot yo'q bo'lsa, faqat lobaratoriya bo'lsa
        elif (item.hours_laboratoriya or 0) > 0:
            teacher = None
            if groups:
                teacher_subject = TeacherSubject.query.filter_by(
                    subject_id=item.subject_id,
                    group_id=groups[0].id,
                    lesson_type='amaliyot'
                ).first()
                if teacher_subject:
                    teacher = teacher_subject.teacher
            
            subject_data['lessons'].append({
                'type': 'Amaliyot',
                'hours': item.hours_laboratoriya,
                'teacher': teacher
            })
        
        # Seminar
        if item.hours_seminar and item.hours_seminar > 0:
            teacher = None
            if groups:
                # Seminar uchun alohida qidirish
                teacher_subject = TeacherSubject.query.filter_by(
                    subject_id=item.subject_id,
                    group_id=groups[0].id,
                    lesson_type='seminar'
                ).first()
                # Agar topilmasa, amaliyot turidagini qidirish (eski ma'lumotlar uchun)
                if not teacher_subject:
                    teacher_subject = TeacherSubject.query.filter_by(
                        subject_id=item.subject_id,
                        group_id=groups[0].id,
                        lesson_type='amaliyot'
                    ).first()
                    # Agar amaliyot topilsa va fanda faqat seminar bo'lsa, uni seminar deb hisoblash
                    if teacher_subject and (item.hours_amaliyot or 0) == 0 and (item.hours_laboratoriya or 0) == 0:
                        pass  # Bu seminar o'qituvchisi
                    elif teacher_subject:
                        teacher_subject = None  # Bu amaliyot o'qituvchisi, seminar emas
                if teacher_subject:
                    teacher = teacher_subject.teacher
            
            subject_data['lessons'].append({
                'type': 'Seminar',
                'hours': item.hours_seminar,
                'teacher': teacher
            })
        
        subjects_by_semester[semester].append(subject_data)
    
    # Tizimdagi barcha o'qituvchilar
    # UserRole orqali o'qituvchi roliga ega bo'lgan foydalanuvchilarni topish
    from app.models import UserRole
    teacher_user_ids = db.session.query(UserRole.user_id).filter_by(role='teacher').distinct().all()
    teacher_user_ids = [uid[0] for uid in teacher_user_ids]
    
    # Agar UserRole orqali topilmasa, eski usul bilan qidirish
    if not teacher_user_ids:
        teachers_by_role = User.query.filter_by(role='teacher').all()
        teacher_user_ids = [t.id for t in teachers_by_role]
    
    # Agar hali ham topilmasa, get_roles() orqali qidirish
    if not teacher_user_ids:
        all_users = User.query.all()
        teacher_user_ids = [u.id for u in all_users if 'teacher' in u.get_roles()]
    
    # Barcha o'qituvchilar (fakultet cheklovi yo'q)
    if teacher_user_ids:
        teachers = User.query.filter(
            User.id.in_(teacher_user_ids)
        ).order_by(User.full_name).all()
    else:
        teachers = []
    
    return render_template('dean/direction_subjects.html',
                         direction=direction,
                         subjects_by_semester=subjects_by_semester,
                         groups=groups,
                         teachers=teachers)


@bp.route('/directions/<int:id>/curriculum/add', methods=['POST'])
@login_required
@dean_required
def add_subject_to_curriculum(id):
    """O'quv rejaga fan qo'shish"""
    direction = Direction.query.get_or_404(id)
    
    # Fakultet tekshiruvi
    if direction.faculty_id != current_user.faculty_id:
        flash("Sizda bu amal uchun ruxsat yo'q", 'error')
        return redirect(url_for('dean.courses'))
    
    subject_ids = request.form.getlist('subject_ids')
    semester = request.form.get('semester', type=int)
    
    if not subject_ids or not semester:
        flash("Fan va semestr tanlash majburiy", 'error')
        return redirect(url_for('dean.direction_curriculum', id=id))
    
    added = 0
    for subject_id in subject_ids:
        subject_id = int(subject_id)
        subject = Subject.query.get(subject_id)
        if not subject:
            continue
        
        # Takrorlanmasligini tekshirish
        existing = DirectionCurriculum.query.filter_by(
            direction_id=direction.id,
            subject_id=subject_id,
            semester=semester
        ).first()
        
        if not existing:
            curriculum_item = DirectionCurriculum(
                direction_id=direction.id,
                subject_id=subject_id,
                semester=semester
            )
            db.session.add(curriculum_item)
            added += 1
    
    db.session.commit()
    flash(f"{added} ta fan o'quv rejaga qo'shildi", 'success')
    return redirect(url_for('dean.direction_curriculum', id=id))


@bp.route('/directions/<int:id>/curriculum/<int:item_id>/update', methods=['POST'])
@login_required
@dean_required
def update_curriculum_item(id, item_id):
    """O'quv reja elementini yangilash (soatlar) - eski versiya, saqlab qolindi"""
    direction = Direction.query.get_or_404(id)
    item = DirectionCurriculum.query.get_or_404(item_id)
    
    # Fakultet tekshiruvi
    if direction.faculty_id != current_user.faculty_id or item.direction_id != direction.id:
        flash("Sizda bu amal uchun ruxsat yo'q", 'error')
        return redirect(url_for('dean.courses'))
    
    item.hours_maruza = request.form.get('hours_maruza', type=int) or 0
    item.hours_amaliyot = request.form.get('hours_amaliyot', type=int) or 0
    item.hours_laboratoriya = request.form.get('hours_laboratoriya', type=int) or 0
    item.hours_seminar = request.form.get('hours_seminar', type=int) or 0
    item.hours_kurs_ishi = request.form.get('hours_kurs_ishi', type=int) or 0
    item.hours_mustaqil = request.form.get('hours_mustaqil', type=int) or 0
    
    db.session.commit()
    flash("O'quv reja yangilandi", 'success')
    return redirect(url_for('dean.direction_curriculum', id=id))


@bp.route('/directions/<int:id>/curriculum/semester/<int:semester>/update', methods=['POST'])
@login_required
@dean_required
def update_semester_curriculum(id, semester):
    """Semestr bo'yicha barcha fanlarni yangilash"""
    direction = Direction.query.get_or_404(id)
    
    # Fakultet tekshiruvi
    if direction.faculty_id != current_user.faculty_id:
        flash("Sizda bu amal uchun ruxsat yo'q", 'error')
        return redirect(url_for('dean.courses'))
    
    # Bu semestr uchun barcha fanlarni olish
    items = DirectionCurriculum.query.filter_by(
        direction_id=direction.id,
        semester=semester
    ).all()
    
    updated = 0
    for item in items:
        item_id = str(item.id)
        
        # Soatlarni yangilash
        item.hours_maruza = request.form.get(f'hours_maruza[{item_id}]', type=int) or 0
        item.hours_amaliyot = request.form.get(f'hours_amaliyot[{item_id}]', type=int) or 0
        item.hours_laboratoriya = request.form.get(f'hours_laboratoriya[{item_id}]', type=int) or 0
        item.hours_seminar = request.form.get(f'hours_seminar[{item_id}]', type=int) or 0
        item.hours_mustaqil = request.form.get(f'hours_mustaqil[{item_id}]', type=int) or 0
        
        # Kurs ishi checkbox - agar belgilangan bo'lsa 1, aks holda 0
        kurs_ishi_values = request.form.getlist('hours_kurs_ishi')
        item.hours_kurs_ishi = 1 if item_id in kurs_ishi_values else 0
        
        updated += 1
    
    db.session.commit()
    flash(f"{updated} ta fan yangilandi", 'success')
    return redirect(url_for('dean.direction_curriculum', id=id))


@bp.route('/directions/<int:id>/curriculum/<int:item_id>/replace', methods=['POST'])
@login_required
@dean_required
def replace_curriculum_subject(id, item_id):
    """O'quv rejadagi fanni boshqa fan bilan almashtirish"""
    direction = Direction.query.get_or_404(id)
    item = DirectionCurriculum.query.get_or_404(item_id)
    
    # Fakultet tekshiruvi
    if direction.faculty_id != current_user.faculty_id or item.direction_id != direction.id:
        flash("Sizda bu amal uchun ruxsat yo'q", 'error')
        return redirect(url_for('dean.courses'))
    
    new_subject_id = request.form.get('subject_id', type=int)
    if not new_subject_id:
        flash("Fan tanlash majburiy", 'error')
        return redirect(url_for('dean.direction_curriculum', id=id))
    
    # Takrorlanmasligini tekshirish
    existing = DirectionCurriculum.query.filter_by(
        direction_id=direction.id,
        subject_id=new_subject_id,
        semester=item.semester
    ).filter(DirectionCurriculum.id != item_id).first()
    
    if existing:
        flash("Bu semestrda bu fan allaqachon mavjud", 'error')
        return redirect(url_for('dean.direction_curriculum', id=id))
    
    item.subject_id = new_subject_id
    db.session.commit()
    flash("Fan almashtirildi", 'success')
    return redirect(url_for('dean.direction_curriculum', id=id))


@bp.route('/directions/<int:id>/curriculum/<int:item_id>/delete', methods=['POST'])
@login_required
@dean_required
def delete_curriculum_item(id, item_id):
    """O'quv rejadan fanni o'chirish"""
    direction = Direction.query.get_or_404(id)
    item = DirectionCurriculum.query.get_or_404(item_id)
    
    # Fakultet tekshiruvi
    if direction.faculty_id != current_user.faculty_id or item.direction_id != direction.id:
        flash("Sizda bu amal uchun ruxsat yo'q", 'error')
        return redirect(url_for('dean.courses'))
    
    db.session.delete(item)
    db.session.commit()
    flash("Fan o'quv rejadan o'chirildi", 'success')
    return redirect(url_for('dean.direction_curriculum', id=id))


# ==================== DARS JADVALI ====================
@bp.route('/schedule')
@login_required
@dean_required
def schedule():
    faculty = Faculty.query.get(current_user.faculty_id)
    if not faculty:
        flash("Sizga fakultet biriktirilmagan", 'error')
        return redirect(url_for('main.dashboard'))
    
    today = datetime.now()
    year = request.args.get('year', type=int) or today.year
    month = request.args.get('month', type=int) or today.month
    if month < 1:
        month = 12
        year -= 1
    elif month > 12:
        month = 1
        year += 1
    days_in_month = calendar.monthrange(year, month)[1]
    start_weekday = calendar.monthrange(year, month)[0]  # 0=Monday
    # Oldingi va keyingi oylar
    if month == 1:
        prev_month, prev_year = 12, year - 1
    else:
        prev_month, prev_year = month - 1, year
    if month == 12:
        next_month, next_year = 1, year + 1
    else:
        next_month, next_year = month + 1, year
    
    current_date = datetime(year, month, 1)
    today_year = today.year
    today_month = today.month
    today_day = today.day
    
    # Joriy oy uchun sanalar diapazoni (YYYYMMDD ko'rinishida)
    start_code = int(f"{year}{month:02d}01")
    end_code = int(f"{year}{month:02d}{days_in_month:02d}")
    
    group_id = request.args.get('group', type=int)
    
    groups = faculty.groups.order_by(Group.name).all()
    
    if group_id:
        schedules = Schedule.query.filter(
            Schedule.group_id == group_id,
            Schedule.day_of_week.between(start_code, end_code)
        ).order_by(Schedule.day_of_week, Schedule.start_time).all()
    else:
        group_ids = [g.id for g in groups]
        schedules = Schedule.query.filter(
            Schedule.group_id.in_(group_ids),
            Schedule.day_of_week.between(start_code, end_code)
        ).order_by(Schedule.day_of_week, Schedule.start_time).all()
    
    # Oy kunlari bo'yicha guruhlash (har bir dars aniq sana bo'yicha)
    schedule_by_day = {i: [] for i in range(1, days_in_month + 1)}
    for s in schedules:
        try:
            code_str = str(s.day_of_week)
            day = int(code_str[-2:])
        except (TypeError, ValueError):
            continue
        if 1 <= day <= days_in_month:
            schedule_by_day[day].append(s)
    
    for day in schedule_by_day:
        schedule_by_day[day].sort(key=lambda x: x.start_time or '')
    
    return render_template('dean/schedule.html', 
                         faculty=faculty,
                         groups=groups,
                         current_group=group_id,
                         schedule_by_day=schedule_by_day,
                         days_in_month=days_in_month,
                         start_weekday=start_weekday,
                         current_date=current_date,
                         year=year,
                         month=month,
                         today_year=today_year,
                         today_month=today_month,
                         today_day=today_day,
                         prev_year=prev_year,
                         prev_month=prev_month,
                         next_year=next_year,
                         next_month=next_month)


@bp.route('/schedule/create', methods=['GET', 'POST'])
@login_required
@dean_required
def create_schedule():
    faculty = Faculty.query.get(current_user.faculty_id)
    if not faculty:
        flash("Sizga fakultet biriktirilmagan", 'error')
        return redirect(url_for('main.dashboard'))
    
    groups = faculty.groups.order_by(Group.name).all()
    # Fanlarni guruhlar orqali olish
    subjects = Subject.query.join(TeacherSubject).join(Group).filter(
        Group.faculty_id == faculty.id
    ).distinct().order_by(Subject.code).all()
    teachers = User.query.filter_by(role='teacher').order_by(User.full_name).all()
    
    # GET parametrlar orqali kelgan default sana va guruh
    default_date = request.args.get('date')
    default_group_id = request.args.get('group', type=int)
    
    if request.method == 'POST':
        # Sana (kalendardan) -> YYYYMMDD formatida int
        date_str = request.form.get('schedule_date')
        date_code = None
        if date_str:
            try:
                parsed_date = datetime.strptime(date_str, "%Y-%m-%d")
                date_code = int(parsed_date.strftime("%Y%m%d"))
            except ValueError:
                flash("Sana noto'g'ri formatda. Iltimos, kalendardan tanlang.", 'error')
                return redirect(url_for('dean.create_schedule'))
        
        if not date_code:
            flash("Sana tanlanishi shart.", 'error')
            return redirect(url_for('dean.create_schedule'))
        
        schedule = Schedule(
            subject_id=request.form.get('subject_id', type=int),
            group_id=request.form.get('group_id', type=int),
            teacher_id=request.form.get('teacher_id', type=int),
            day_of_week=date_code,
            start_time=request.form.get('start_time'),
            end_time=request.form.get('end_time') or None,
            link=request.form.get('link'),
            lesson_type=request.form.get('lesson_type')
        )
        db.session.add(schedule)
        db.session.commit()
        
        flash("Dars jadvalga qo'shildi", 'success')
        # Sana bo'yicha qayta ochish (shu oy/yil)
        return redirect(url_for(
            'dean.schedule',
            year=parsed_date.year,
            month=parsed_date.month,
            group=schedule.group_id
        ))
    
    return render_template('dean/create_schedule.html',
                         faculty=faculty,
                         groups=groups,
                         subjects=subjects,
                         teachers=teachers,
                         default_date=default_date,
                         default_group_id=default_group_id)


@bp.route('/schedule/<int:id>/delete', methods=['POST'])
@login_required
@dean_required
def delete_schedule(id):
    schedule = Schedule.query.get_or_404(id)
    
    # Faqat o'z fakultetidagi jadvallarni o'chirishi mumkin
    if schedule.subject.faculty_id != current_user.faculty_id:
        flash("Sizda bu amaliyot uchun huquq yo'q", 'error')
        return redirect(url_for('dean.schedule'))
    
    db.session.delete(schedule)
    db.session.commit()
    flash("Jadval o'chirildi", 'success')
    
    return redirect(url_for('dean.schedule'))


@bp.route('/schedule/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@dean_required
def edit_schedule(id):
    schedule = Schedule.query.get_or_404(id)
    
    # Faqat o'z fakultetidagi jadvallarni tahrirlashi mumkin
    if schedule.subject.faculty_id != current_user.faculty_id:
        flash("Sizda bu amaliyot uchun huquq yo'q", 'error')
        return redirect(url_for('dean.schedule'))
    
    faculty = Faculty.query.get(current_user.faculty_id)
    groups = faculty.groups.order_by(Group.name).all()
    # Fanlarni guruhlar orqali olish
    subjects = Subject.query.join(TeacherSubject).join(Group).filter(
        Group.faculty_id == faculty.id
    ).distinct().order_by(Subject.code).all()
    teachers = User.query.filter_by(role='teacher').order_by(User.full_name).all()
    
    # Eski sana
    try:
        code_str = str(schedule.day_of_week)
        existing_date = datetime.strptime(code_str, "%Y%m%d")
    except (ValueError, TypeError):
        existing_date = datetime.now()
    
    if request.method == 'POST':
        date_str = request.form.get('schedule_date')
        date_code = None
        if date_str:
            try:
                parsed_date = datetime.strptime(date_str, "%Y-%m-%d")
                date_code = int(parsed_date.strftime("%Y%m%d"))
            except ValueError:
                flash("Sana noto'g'ri formatda. Iltimos, kalendardan tanlang.", 'error')
                return redirect(url_for('dean.edit_schedule', id=id))
        
        if not date_code:
            flash("Sana tanlanishi shart.", 'error')
            return redirect(url_for('dean.edit_schedule', id=id))
        
        schedule.subject_id = request.form.get('subject_id', type=int)
        schedule.group_id = request.form.get('group_id', type=int)
        schedule.teacher_id = request.form.get('teacher_id', type=int)
        schedule.day_of_week = date_code
        schedule.start_time = request.form.get('start_time')
        schedule.end_time = request.form.get('end_time') or None
        schedule.link = request.form.get('link')
        schedule.lesson_type = request.form.get('lesson_type')
        
        db.session.commit()
        
        flash("Dars jadvali yangilandi", 'success')
        return redirect(url_for(
            'dean.schedule',
            year=parsed_date.year,
            month=parsed_date.month,
            group=schedule.group_id
        ))
    
    schedule_date = existing_date.strftime("%Y-%m-%d")
    year = existing_date.year
    month = existing_date.month
    
    return render_template(
        'dean/edit_schedule.html',
        faculty=faculty,
        groups=groups,
        subjects=subjects,
        teachers=teachers,
        schedule=schedule,
        schedule_date=schedule_date,
        year=year,
        month=month
    )


# ==================== HISOBOTLAR ====================
@bp.route('/reports')
@login_required
@dean_required
def reports():
    faculty = Faculty.query.get(current_user.faculty_id)
    if not faculty:
        flash("Sizga fakultet biriktirilmagan", 'error')
        return redirect(url_for('main.dashboard'))
    
    # Fakultet statistikasi
    faculty_group_ids = [g.id for g in faculty.groups.all()]
    
    stats = {
        'total_groups': faculty.groups.count(),
        'total_subjects': Subject.query.join(TeacherSubject).join(Group).filter(
            Group.faculty_id == faculty.id
        ).distinct().count(),
        'total_students': User.query.filter(
            User.role == 'student',
            User.group_id.in_(faculty_group_ids)
        ).count(),
        'total_teachers': db.session.query(TeacherSubject.teacher_id).join(Group).filter(
            Group.faculty_id == faculty.id
        ).distinct().count(),
    }
    
    # Guruhlar bo'yicha talabalar
    group_stats = []
    for group in faculty.groups.all():
        group_stats.append({
            'group': group,
            'students': group.students.count(),
            'subjects': TeacherSubject.query.filter_by(group_id=group.id).count()
        })
    
    return render_template('dean/reports.html', faculty=faculty, stats=stats, group_stats=group_stats)


@bp.route('/export/schedule')
@login_required
@dean_required
def export_schedule():
    """Dars jadvalini Excel formatida yuklab olish"""
    try:
        from app.utils.excel_export import create_schedule_excel
    except ImportError:
        flash("Excel export funksiyasi ishlamayapti. Iltimos, 'pip install openpyxl' buyrug'ini bajaring.", 'error')
        return redirect(url_for('dean.schedule'))
    
    faculty = Faculty.query.get(current_user.faculty_id) if current_user.faculty_id else None
    
    if not faculty:
        flash("Fakultet topilmadi", 'error')
        return redirect(url_for('dean.index'))
    
    # Oy/yil parametrlari (jadval sahifasidagi kabi)
    today = datetime.now()
    year = request.args.get('year', type=int) or today.year
    month = request.args.get('month', type=int) or today.month
    if month < 1:
        month = 12
        year -= 1
    elif month > 12:
        month = 1
        year += 1
    
    days_in_month = calendar.monthrange(year, month)[1]
    start_code = int(f"{year}{month:02d}01")
    end_code = int(f"{year}{month:02d}{days_in_month:02d}")
    
    group_id = request.args.get('group', type=int)
    
    if group_id:
        group = Group.query.filter_by(id=group_id, faculty_id=faculty.id).first_or_404()
        schedules = Schedule.query.filter(
            Schedule.group_id == group_id,
            Schedule.day_of_week.between(start_code, end_code)
        ).order_by(Schedule.day_of_week, Schedule.start_time).all()
        excel_file = create_schedule_excel(schedules, group.name, None)
        filename = f"dars_jadvali_{group.name}_{year}_{month:02d}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    else:
        group_ids = [g.id for g in faculty.groups.all()]
        schedules = Schedule.query.filter(
            Schedule.group_id.in_(group_ids),
            Schedule.day_of_week.between(start_code, end_code)
        ).order_by(Schedule.day_of_week, Schedule.start_time).all()
        excel_file = create_schedule_excel(schedules, None, faculty.name)
        filename = f"dars_jadvali_{faculty.name.replace(' ', '_')}_{year}_{month:02d}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    
    return Response(
        excel_file,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )

