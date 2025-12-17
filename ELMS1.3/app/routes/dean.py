from flask import Blueprint, render_template, request, redirect, url_for, flash, Response
from flask_login import login_required, current_user
from app.models import User, Faculty, Group, Subject, TeacherSubject, Schedule, Announcement, Direction
from app import db
from functools import wraps
from sqlalchemy import func
from datetime import datetime
import calendar

bp = Blueprint('dean', __name__, url_prefix='/dean')

def dean_required(f):
    """Faqat dekan uchun"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'dean':
            flash("Sizda bu sahifaga kirish huquqi yo'q", 'error')
            return redirect(url_for('main.dashboard'))
        return f(*args, **kwargs)
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
            'total_subjects': faculty.subjects.count(),
            'total_students': User.query.join(Group).filter(Group.faculty_id == faculty.id).count(),
            'total_teachers': TeacherSubject.query.join(Subject).filter(Subject.faculty_id == faculty.id).distinct(TeacherSubject.teacher_id).count(),
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
        subjects = faculty.subjects.order_by(Subject.code).all()
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
    
    # GET parametrlar orqali kelgan default yo'nalish
    default_direction_id = request.args.get('direction_id', type=int)
    
    directions = Direction.query.filter_by(faculty_id=faculty.id).order_by(Direction.name).all()
    
    if request.method == 'POST':
        name = request.form.get('name').upper()
        direction_id = request.form.get('direction_id', type=int)
        
        if Group.query.filter_by(name=name, faculty_id=faculty.id).first():
            flash("Bu guruh nomi allaqachon mavjud", 'error')
            return render_template('dean/create_group.html', faculty=faculty, directions=directions, default_direction_id=direction_id)
        
        group = Group(
            name=name,
            faculty_id=faculty.id,
            course_year=request.form.get('course_year', 1, type=int),
            education_type=request.form.get('education_type', 'kunduzgi'),
            direction_id=direction_id if direction_id else None
        )
        db.session.add(group)
        db.session.commit()
        
        flash("Guruh muvaffaqiyatli yaratildi", 'success')
        # Agar yo'nalish bo'lsa, yo'nalish detail sahifasiga qaytish
        if direction_id:
            return redirect(url_for('dean.direction_detail', id=direction_id))
        return redirect(url_for('dean.groups'))
    
    return render_template('dean/create_group.html', faculty=faculty, directions=directions, default_direction_id=default_direction_id)


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
    
    if request.method == 'POST':
        group.name = request.form.get('name').upper()
        group.course_year = request.form.get('course_year', 1, type=int)
        group.education_type = request.form.get('education_type')
        
        db.session.commit()
        flash("Guruh yangilandi", 'success')
        return redirect(url_for('dean.groups'))
    
    return render_template('dean/edit_group.html', group=group, faculty=faculty)


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


# ==================== O'QITUVCHI-FAN BIRIKTIRISH ====================
@bp.route('/assignments')
@login_required
@dean_required
def teacher_assignments():
    faculty = Faculty.query.get(current_user.faculty_id)
    if not faculty:
        flash("Sizga fakultet biriktirilmagan", 'error')
        return redirect(url_for('main.dashboard'))
    
    # Fakultetdagi fanlar uchun biriktirmalar
    assignments = TeacherSubject.query.join(Subject).filter(
        Subject.faculty_id == faculty.id
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
    
    subjects = faculty.subjects.order_by(Subject.code).all()
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
    faculty = Faculty.query.get(current_user.faculty_id)
    if not faculty:
        flash("Sizga fakultet biriktirilmagan", 'error')
        return redirect(url_for('main.dashboard'))
    
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '')
    group_id = request.args.get('group', type=int)
    
    # Fakultet guruhlari
    faculty_group_ids = [g.id for g in faculty.groups.all()]
    
    query = User.query.filter(
        User.role == 'student',
        User.group_id.in_(faculty_group_ids)
    )
    
    if search:
        query = query.filter(
            (User.full_name.ilike(f'%{search}%')) |
            (User.email.ilike(f'%{search}%')) |
            (User.student_id.ilike(f'%{search}%'))
        )
    
    if group_id:
        query = query.filter(User.group_id == group_id)
    
    students = query.order_by(User.full_name).paginate(page=page, per_page=20)
    groups = faculty.groups.order_by(Group.name).all()
    
    return render_template('dean/students.html', 
                         faculty=faculty, 
                         students=students, 
                         groups=groups,
                         current_group=group_id,
                         search=search)


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


@bp.route('/students/create', methods=['GET', 'POST'])
@login_required
@dean_required
def create_student():
    """Dekan uchun talaba yaratish"""
    faculty = Faculty.query.get(current_user.faculty_id)
    if not faculty:
        flash("Sizga fakultet biriktirilmagan", 'error')
        return redirect(url_for('main.dashboard'))
    
    # Faqat o'z fakultetidagi guruhlar
    groups = faculty.groups.order_by(Group.name).all()
    
    if request.method == 'POST':
        email = request.form.get('email')
        full_name = request.form.get('full_name')
        password = request.form.get('password')
        student_id = request.form.get('student_id')
        group_id = request.form.get('group_id', type=int)
        enrollment_year = request.form.get('enrollment_year', type=int)
        phone = request.form.get('phone')
        
        # Email tekshiruvi
        if User.query.filter_by(email=email).first():
            flash("Bu email allaqachon mavjud", 'error')
            return render_template('dean/create_student.html', faculty=faculty, groups=groups)
        
        # Talaba ID tekshiruvi
        if student_id and User.query.filter_by(student_id=student_id).first():
            flash("Bu talaba ID allaqachon mavjud", 'error')
            return render_template('dean/create_student.html', faculty=faculty, groups=groups)
        
        # Guruh tekshiruvi - faqat o'z fakultetidagi guruhlarga
        if group_id:
            group = Group.query.get(group_id)
            if not group or group.faculty_id != faculty.id:
                flash("Noto'g'ri guruh tanlandi", 'error')
                return render_template('dean/create_student.html', faculty=faculty, groups=groups)
        
        user = User(
            email=email,
            full_name=full_name,
            role='student',
            student_id=student_id,
            group_id=group_id,
            enrollment_year=enrollment_year,
            phone=phone
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        
        flash(f"Talaba {user.full_name} muvaffaqiyatli yaratildi", 'success')
        return redirect(url_for('dean.students'))
    
    return render_template('dean/create_student.html', faculty=faculty, groups=groups)


# ==================== O'QITUVCHILAR ====================
@bp.route('/teachers')
@login_required
@dean_required
def teachers():
    faculty = Faculty.query.get(current_user.faculty_id)
    if not faculty:
        flash("Sizga fakultet biriktirilmagan", 'error')
        return redirect(url_for('main.dashboard'))
    
    # Fakultetda dars beradigan o'qituvchilar
    teacher_ids = db.session.query(TeacherSubject.teacher_id).join(Subject).filter(
        Subject.faculty_id == faculty.id
    ).distinct().all()
    teacher_ids = [t[0] for t in teacher_ids]
    
    teachers = User.query.filter(User.id.in_(teacher_ids)).order_by(User.full_name).all()
    
    # Har bir o'qituvchining fanlari
    teacher_subjects = {}
    for teacher in teachers:
        subjects = TeacherSubject.query.filter_by(teacher_id=teacher.id).join(Subject).filter(
            Subject.faculty_id == faculty.id
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
    faculty = Faculty.query.get(current_user.faculty_id)
    if not faculty:
        flash("Sizga fakultet biriktirilmagan", 'error')
        return redirect(url_for('main.dashboard'))
    
    directions_list = Direction.query.filter_by(faculty_id=faculty.id).order_by(Direction.name).all()
    # Faqat biriktirilmagan guruhlar (yo'nalishlarga qo'shish uchun)
    unassigned_groups = Group.query.filter_by(faculty_id=faculty.id, direction_id=None).order_by(Group.name).all()
    
    # Har bir yo'nalish uchun biriktirilgan guruhlar
    direction_groups = {}
    for direction in directions_list:
        direction_groups[direction.id] = Group.query.filter_by(direction_id=direction.id).all()
    
    return render_template('dean/directions.html',
                         faculty=faculty,
                         directions=directions_list,
                         unassigned_groups=unassigned_groups,
                         direction_groups=direction_groups)


@bp.route('/directions/create', methods=['POST'])
@login_required
@dean_required
def create_direction():
    faculty = Faculty.query.get(current_user.faculty_id)
    if not faculty:
        flash("Sizga fakultet biriktirilmagan", 'error')
        return redirect(url_for('main.dashboard'))
    
    name = request.form.get('name')
    code = request.form.get('code')
    description = request.form.get('description', '')
    
    if not name or not code:
        flash("Yo'nalish nomi va kodi to'ldirilishi shart", 'error')
        return redirect(url_for('dean.directions'))
    
    # Kod takrorlanmasligini tekshirish
    existing = Direction.query.filter_by(faculty_id=faculty.id, code=code).first()
    if existing:
        flash("Bu kod allaqachon mavjud", 'error')
        return redirect(url_for('dean.directions'))
    
    direction = Direction(
        name=name,
        code=code,
        description=description,
        faculty_id=faculty.id
    )
    db.session.add(direction)
    db.session.commit()
    
    flash("Yo'nalish muvaffaqiyatli yaratildi", 'success')
    return redirect(url_for('dean.directions'))


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
        code = request.form.get('code')
        description = request.form.get('description', '')
        
        if not name or not code:
            flash("Yo'nalish nomi va kodi to'ldirilishi shart", 'error')
            return render_template('dean/edit_direction.html', direction=direction)
        
        # Kod takrorlanmasligini tekshirish (o'z kodini hisobga olmasdan)
        existing = Direction.query.filter(
            Direction.faculty_id == current_user.faculty_id,
            Direction.code == code,
            Direction.id != id
        ).first()
        if existing:
            flash("Bu kod allaqachon mavjud", 'error')
            return render_template('dean/edit_direction.html', direction=direction)
        
        direction.name = name
        direction.code = code
        direction.description = description
        
        db.session.commit()
        
        flash("Yo'nalish yangilandi", 'success')
        return redirect(url_for('dean.directions'))
    
    return render_template('dean/edit_direction.html', direction=direction)


@bp.route('/directions/<int:id>/delete', methods=['POST'])
@login_required
@dean_required
def delete_direction(id):
    direction = Direction.query.get_or_404(id)
    
    # Fakultet tekshiruvi
    if direction.faculty_id != current_user.faculty_id:
        flash("Sizda bu amal uchun ruxsat yo'q", 'error')
        return redirect(url_for('dean.directions'))
    
    # Biriktirilgan guruhlardan yo'nalishni olib tashlash
    Group.query.filter_by(direction_id=direction.id).update({'direction_id': None})
    
    db.session.delete(direction)
    db.session.commit()
    
    flash("Yo'nalish o'chirildi", 'success')
    return redirect(url_for('dean.directions'))


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
    subjects = faculty.subjects.order_by(Subject.code).all()
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
    subjects = faculty.subjects.order_by(Subject.code).all()
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
        'total_subjects': faculty.subjects.count(),
        'total_students': User.query.filter(
            User.role == 'student',
            User.group_id.in_(faculty_group_ids)
        ).count(),
        'total_teachers': db.session.query(TeacherSubject.teacher_id).join(Subject).filter(
            Subject.faculty_id == faculty.id
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


# ==================== EXCEL EXPORT ====================
@bp.route('/export/students')
@login_required
@dean_required
def export_students():
    """Talabalar ro'yxatini Excel formatida yuklab olish"""
    try:
        from app.utils.excel_export import create_students_excel
    except ImportError:
        flash("Excel export funksiyasi ishlamayapti. Iltimos, 'pip install openpyxl' buyrug'ini bajaring.", 'error')
        return redirect(url_for('dean.students'))
    
    faculty = Faculty.query.get(current_user.faculty_id) if current_user.faculty_id else None
    
    if not faculty:
        flash("Fakultet topilmadi", 'error')
        return redirect(url_for('dean.index'))
    
    group_id = request.args.get('group_id', type=int)
    
    if group_id:
        group = Group.query.filter_by(id=group_id, faculty_id=faculty.id).first_or_404()
        students = User.query.filter_by(role='student', group_id=group_id).order_by(User.full_name).all()
        excel_file = create_students_excel(students, f"{faculty.name} - {group.name}")
        filename = f"talabalar_{group.name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    else:
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

