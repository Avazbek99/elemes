from flask import Blueprint, render_template, request, redirect, url_for, flash, Response, send_file, session, jsonify
from flask_login import login_required, current_user
from app.models import User, Faculty, Group, Subject, TeacherSubject, Schedule, Announcement, Direction, StudentPayment, DirectionCurriculum, Message, Submission, LessonView, PasswordResetToken
from app import db
from functools import wraps
from sqlalchemy import func, asc, desc
from datetime import datetime
import calendar
from werkzeug.security import generate_password_hash
from app.utils.excel_export import create_schedule_excel
from app.utils.excel_import import generate_schedule_sample_file, import_schedule_from_excel
from app.utils.translations import t

bp = Blueprint('dean', __name__, url_prefix='/dean')

def dean_required(f):
    """Faqat dekan uchun (joriy tanlangan rol yoki asosiy rol)"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash(t('no_access_permission'), 'error')
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
            flash(t('no_access_permission'), 'error')
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
            'total_subjects': Subject.query.join(DirectionCurriculum).join(Direction).filter(Direction.faculty_id == faculty.id).distinct().count(),
            'total_students': User.query.join(Group).filter(Group.faculty_id == faculty.id).count(),
            'total_teachers': User.query.filter_by(role='teacher').count(), # Tizimdagi barcha o'qituvchilar yoki fakultetdagi? (TeacherSubject join kerak)
            'total_directions': Direction.query.filter_by(faculty_id=faculty.id).count()
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
    
    from app.utils.date_utils import get_tashkent_time
    now_dt = get_tashkent_time()
    
    return render_template('dean/index.html', faculty=faculty, stats=stats, directions=directions, direction_stats=direction_stats, subjects=subjects, now_dt=now_dt)




# ==================== GURUHLAR ====================
@bp.route('/groups')
@login_required
@dean_required
def groups():
    faculty = Faculty.query.get(current_user.faculty_id)
    if not faculty:
        flash(t('faculty_not_assigned'), 'error')
        return redirect(url_for('main.dashboard'))
    
    course_year = request.args.get('course_year', type=int)
    semester = request.args.get('semester', type=int)
    direction_id = request.args.get('direction_id', type=int)
    search = request.args.get('search', '')
    
    from sqlalchemy import exists
    has_student = exists().where(User.group_id == Group.id, User.role == 'student')
    
    query = faculty.groups.filter(has_student)
    if course_year:
        query = query.filter_by(course_year=course_year)
    if semester:
        query = query.filter_by(semester=semester)
    if direction_id:
        query = query.filter_by(direction_id=direction_id)
    if search:
        query = query.filter(Group.name.ilike(f'%{search}%'))
    
    groups = query.order_by(Group.course_year, Group.semester, Group.name).all()
    
    # Filtrlar uchun ma'lumotlar (faqat talabasi bor guruhlar)
    active = faculty.groups.filter(has_student).all()
    all_courses = sorted(set([g.course_year for g in active if g.course_year]))
    all_semesters = sorted(set([g.semester for g in active if g.semester]))
    direction_ids = [g.direction_id for g in active if g.direction_id]
    all_directions = []
    if direction_ids:
        all_directions = Direction.query.filter(Direction.id.in_(set(direction_ids))).all()
        all_directions = sorted(all_directions, key=lambda d: ((d.code or '').lower(), (d.name or '').lower()))
    
    return render_template('dean/groups.html', 
                         faculty=faculty, 
                         groups=groups,
                         all_courses=all_courses,
                         all_semesters=all_semesters,
                         all_directions=all_directions,
                         current_course_year=course_year,
                         current_semester=semester,
                         current_direction_id=direction_id,
                         search=search)


@bp.route('/groups/create', methods=['GET', 'POST'])
@login_required
@dean_required
def create_group():
    faculty = Faculty.query.get(current_user.faculty_id)
    if not faculty:
        flash(t('faculty_not_assigned'), 'error')
        return redirect(url_for('main.dashboard'))
    
    # Fakultetdagi barcha yo'nalishlarni olish
    all_directions = Direction.query.filter_by(faculty_id=faculty.id).order_by(Direction.name).all()
    
    if request.method == 'POST':
        name = request.form.get('name')
        direction_id = request.form.get('direction_id', type=int)
        
        from app.utils.date_utils import get_tashkent_time
        _now_dt = get_tashkent_time()
        _courses = [1, 2, 3, 4, 5, 6, 7]
        _from_d = request.args.get('from_directions') or request.form.get('from_directions')
        _ctx = lambda: {'faculty': faculty, 'courses': _courses, 'all_directions': all_directions, 'now_dt': _now_dt, 'from_directions': _from_d}

        # Validatsiya
        if not name:
            flash(t('group_name_required'), 'error')
            return render_template('dean/create_group.html', **_ctx())
        
        if not direction_id:
            flash(t('direction_required'), 'error')
            return render_template('dean/create_group.html', **_ctx())
        
        direction = Direction.query.get(direction_id)
        if not direction or direction.faculty_id != faculty.id:
            flash(t('direction_incorrect_selection'), 'error')
            return render_template('dean/create_group.html', **_ctx())
        
        course_year = request.form.get('course_year', type=int)
        semester = request.form.get('semester', type=int)
        education_type = request.form.get('education_type')
        if Group.query.filter_by(name=name.upper(), direction_id=direction_id, course_year=course_year, semester=semester).first():
            flash(t('group_already_exists'), 'error')
            return render_template('dean/create_group.html', **_ctx())
        
        description = request.form.get('description', '').strip()
        enrollment_year = request.form.get('enrollment_year', type=int)
        
        if not course_year or not semester or not education_type:
            flash(t('group_all_fields_required'), 'error')
            return render_template('dean/create_group.html', **_ctx())
        
        group = Group(
            name=name.upper(),
            faculty_id=faculty.id,
            course_year=course_year,
            semester=semester,
            education_type=education_type,
            enrollment_year=enrollment_year,
            direction_id=direction_id,
            description=description if description else None
        )
        db.session.add(group)
        db.session.commit()
        
        flash(t('group_created'), 'success')
        if request.args.get('from_directions') or request.form.get('from_directions'):
            return redirect(url_for('dean.directions'))
        return redirect(url_for('dean.groups'))
    
    from app.utils.date_utils import get_tashkent_time
    now_dt = get_tashkent_time()
    courses = [1, 2, 3, 4, 5, 6, 7]
    from_directions = request.args.get('from_directions')
    
    return render_template('dean/create_group.html', faculty=faculty, courses=courses, all_directions=all_directions, now_dt=now_dt, from_directions=from_directions)


@bp.route('/groups/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@dean_required
def edit_group(id):
    group = Group.query.get_or_404(id)
    faculty = Faculty.query.get(current_user.faculty_id)
    
    # Faqat o'z fakultetidagi guruhlarni tahrirlashi mumkin
    if group.faculty_id != current_user.faculty_id:
        flash(t('no_permission_to_edit_group'), 'error')
        return redirect(url_for('dean.groups'))
    
    # Faqat shu fakultetdagi yo'nalishlar
    directions = Direction.query.filter_by(faculty_id=faculty.id).order_by(Direction.name).all()
    
    if request.method == 'POST':
        # Guruh nomi, kurs, semestr, ta'lim shakli, yo'nalish va tavsifni o'zgartirish mumkin
        new_name = request.form.get('name').upper()
        course_year = request.form.get('course_year', type=int)
        semester = request.form.get('semester', type=int)
        education_type = request.form.get('education_type')
        direction_id = request.form.get('direction_id', type=int)
        enrollment_year = request.form.get('enrollment_year', type=int)
        description = request.form.get('description', '').strip()
        
        _edit_redirect = lambda: redirect(url_for('dean.edit_group', id=group.id, **({'from_directions': 1} if (request.args.get('from_directions') or request.form.get('from_directions')) else {})))
        
        if not course_year or not semester or not education_type or not direction_id or not enrollment_year:
            flash(t('all_fields_required'), 'error')
            return _edit_redirect()
        
        direction = Direction.query.get(direction_id)
        if not direction or direction.faculty_id != group.faculty_id:
            flash(t('direction_incorrect_selection'), 'error')
            return _edit_redirect()
        
        if (new_name != group.name or direction_id != group.direction_id or course_year != group.course_year or semester != group.semester):
            existing_group = Group.query.filter_by(name=new_name, direction_id=direction_id, course_year=course_year, semester=semester).first()
            if existing_group and existing_group.id != group.id:
                flash(t('group_already_exists'), 'error')
                return _edit_redirect()
        
        group.name = new_name
        old_direction_id = group.direction_id
        group.direction_id = direction_id
        group.course_year = course_year
        group.semester = semester
        group.education_type = education_type
        group.enrollment_year = enrollment_year
        group.description = description if description else None
        
        db.session.commit()
        flash(t('group_updated'), 'success')
        
        # Redireksiya
        if request.args.get('from_directions') or request.form.get('from_directions'):
            return redirect(url_for('dean.directions'))
        if request.args.get('from_courses') or request.form.get('from_courses'):
            return redirect(url_for('dean.groups'))
        return redirect(url_for('dean.direction_detail', id=direction_id))
    
    all_directions = Direction.query.filter_by(faculty_id=faculty.id).order_by(Direction.name).all()
    from app.utils.date_utils import get_tashkent_time
    now_dt = get_tashkent_time()
    courses = [1, 2, 3, 4, 5, 6, 7]
    from_directions = request.args.get('from_directions')
    
    return render_template('dean/edit_group.html', 
                         group=group,
                         faculty=faculty,
                         all_directions=all_directions,
                         now_dt=now_dt,
                         courses=courses,
                         from_directions=from_directions)


@bp.route('/groups/<int:id>/delete', methods=['POST'])
@login_required
@dean_required
def delete_group(id):
    group = Group.query.get_or_404(id)
    
    if group.faculty_id != current_user.faculty_id:
        flash(t('no_permission_to_delete_group'), 'error')
        return redirect(url_for('dean.groups'))
    
    if group.students.count() > 0:
        flash(t('group_has_students_transfer_first'), 'error')
    else:
        db.session.delete(group)
        db.session.commit()
        flash(t('group_deleted'), 'success')
    
    if request.args.get('from_directions'):
        return redirect(url_for('dean.directions'))
    if request.args.get('from_courses'):
        return redirect(url_for('dean.groups'))
    return redirect(url_for('dean.groups'))


@bp.route('/groups/<int:id>/students')
@login_required
@dean_required
def group_students(id):
    group = Group.query.get_or_404(id)
    
    if group.faculty_id != current_user.faculty_id:
        flash(t('no_permission_to_view_group'), 'error')
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
        flash(t('no_permission_to_add_students_to_group'), 'error')
        return redirect(url_for('dean.groups'))
    
    # Bir nechta talabani qo'shish
    student_ids = request.form.getlist('student_ids')
    student_ids = [int(sid) for sid in student_ids if sid]
    
    if not student_ids:
        flash(t('no_students_selected'), 'error')
        return redirect(url_for('dean.group_students', id=id))
    
    added_count = 0
    for student_id in student_ids:
        student = User.query.get(student_id)
        if student and student.role == 'student' and student.group_id is None:
            student.group_id = group.id
            added_count += 1
    
    db.session.commit()
    
    if added_count > 0:
        flash(t('students_added_to_group', added_count=added_count), 'success')
    else:
        flash(t('no_students_added'), 'warning')
    
    return redirect(url_for('dean.group_students', id=id))


@bp.route('/groups/<int:id>/remove-student/<int:student_id>', methods=['POST'])
@login_required
@dean_required
def remove_student_from_group(id, student_id):
    group = Group.query.get_or_404(id)
    
    if group.faculty_id != current_user.faculty_id:
        flash(t('no_permission_for_operation'), 'error')
        return redirect(url_for('dean.groups'))
    
    student = User.query.get_or_404(student_id)
    student.group_id = None
    db.session.commit()
    flash(t('student_removed_from_group', full_name=student.full_name), 'success')
    
    return redirect(url_for('dean.group_students', id=id))


@bp.route('/groups/<int:id>/remove-students', methods=['POST'])
@login_required
@dean_required
def remove_students_from_group(id):
    """Bir nechta talabani bir vaqtning o'zida guruhdan chiqarish"""
    group = Group.query.get_or_404(id)
    
    if group.faculty_id != current_user.faculty_id:
        flash(t('no_permission_for_operation'), 'error')
        return redirect(url_for('dean.groups'))
    
    ids = request.form.getlist('remove_student_ids')
    student_ids = [int(sid) for sid in ids if sid]
    
    if not student_ids:
        flash(t('no_students_selected'), 'error')
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
        flash(t('students_removed_from_group', count=count), 'success')
    else:
        flash(t('no_students_removed'), 'warning')
    
    return redirect(url_for('dean.group_students', id=id))


# ==================== API ENDPOINTS ====================

@bp.route('/api/groups')
@login_required
@dean_required
def api_groups():
    """Get groups for current dean's faculty with optional filters"""
    query = Group.query.filter_by(faculty_id=current_user.faculty_id)
    
    # Apply filters
    direction_id = request.args.get('direction_id')
    course_year = request.args.get('course_year')
    semester = request.args.get('semester')
    education_type = request.args.get('education_type')
    enrollment_year = request.args.get('enrollment_year')
    
    if direction_id:
        query = query.filter(Group.direction_id == int(direction_id))
    if course_year:
        query = query.filter(Group.course_year == int(course_year))
    if semester:
        query = query.filter(Group.semester == int(semester))
    if education_type:
        query = query.filter(Group.education_type == education_type)
    if enrollment_year:
        query = query.filter(Group.enrollment_year == int(enrollment_year))
    
    groups = query.order_by(Group.name).all()
    
    return jsonify([{
        'id': g.id,
        'name': g.name,
        'faculty_id': g.faculty_id,
        'direction_id': g.direction_id,
        'course_year': g.course_year,
        'semester': g.semester,
        'education_type': g.education_type,
        'enrollment_year': g.enrollment_year
    } for g in groups])


@bp.route('/api/groups/<int:group_id>')
@login_required
@dean_required
def api_group_detail(group_id):
    """Get detailed information about a specific group"""
    group = Group.query.get_or_404(group_id)
    
    # Security check: ensure group belongs to dean's faculty
    if group.faculty_id != current_user.faculty_id:
        return jsonify({'error': 'Unauthorized'}), 403
        
    return jsonify({
        'id': group.id,
        'name': group.name,
        'faculty_id': group.faculty_id,
        'direction_id': group.direction_id,
        'course_year': group.course_year,
        'semester': group.semester,
        'education_type': group.education_type,
        'enrollment_year': group.enrollment_year
    })


@bp.route('/api/directions')
@login_required
@dean_required
def api_directions():
    """Get directions for current dean's faculty"""
    directions = Direction.query.filter_by(faculty_id=current_user.faculty_id).order_by(Direction.code).all()
    
    return jsonify([{
        'id': d.id,
        'code': d.code,
        'name': d.name,
        'formatted_direction': d.formatted_direction,
        'faculty_id': d.faculty_id
    } for d in directions])


# ==================== KURSLAR ====================
@bp.route('/courses')
@login_required
@dean_required
def courses():
    """Dekan uchun kurslar bo'limi (Yo'nalishlar)"""
    faculty = Faculty.query.get(current_user.faculty_id)
    if not faculty:
        flash(t('faculty_not_assigned'), 'error')
        return redirect(url_for('main.dashboard'))
    
    # Filtrlarni olish
    course_filter = request.args.get('course', type=int)
    direction_filter = request.args.get('direction', type=int)
    group_filter = request.args.get('group', type=int)

    # Fakultetdagi barcha guruhlarni olish
    query = faculty.groups
    all_groups = query.all()
    
    # Qabul yili va ta'lim shakli bo'yicha guruhlash
    courses_dict = {}
    
    # Barcha guruhlarni ko'rib chiqish
    for group in all_groups:
        if not group.semester:
            continue
            
        semester = group.semester
        course_year = group.course_year or ((semester + 1) // 2)
        enrollment_year = group.enrollment_year if group.enrollment_year else "Noma'lum"
        edu_type = group.education_type if group.education_type else "Noma'lum"
        
        # Filtrelar
        if course_filter and course_year != course_filter:
            continue
        if group_filter and group.id != group_filter:
            continue
        if direction_filter and group.direction_id != direction_filter:
            continue
            
        # Guruhga tegishli talabalar sonini hisoblash
        students_count = User.query.filter(User.group_id == group.id, User.role == 'student').count()
        
        # Talabasi yo'q guruhlarni ko'rsatish yoki ko'rsatmaslik? 
        # Admin loģikasida 0 talabali guruhlar ham ko'rinishi kerak (agar students_count > 0 check bo'lmasa)
        # Lekin admin.py kodida 'if students_count == 0: continue' bor edi, keyin olib tashlangan bo'lishi mumkin.
        # Admin kodida: 'if students_count == 0: continue' bor edi. Keling shuni saqlaymiz.
        if students_count == 0:
           continue

        # 1-daraja: Qabul yili + Ta'lim shakli
        # Kalit: (2025, 'masofaviy')
        main_key = (enrollment_year, edu_type)
        
        if main_key not in courses_dict:
            courses_dict[main_key] = {
                'directions': {},
                'total_groups': 0,
                'total_students': 0
            }
            
        # 2-daraja: Yo'nalish
        direction_key = (group.direction_id, group.education_type)
        
        if direction_key not in courses_dict[main_key]['directions']:
            # Sarlavha shakllantirish (ta'lim shakli tanlangan tilda)
            if group.direction:
                code = group.direction.code
                name = group.direction.name
                et = (group.education_type or "").strip().lower()
                edu_type_str = t('education_type_' + et) if et in ('kunduzgi', 'sirtqi', 'kechki', 'masofaviy') else t('education_type_not_set')
                enrollment_year_str = str(group.enrollment_year) if group.enrollment_year else "____"
                heading = f"{enrollment_year_str} - {code} - {name} ({edu_type_str})"
            else:
                heading = "____ - Biriktirilmagan"
            
            courses_dict[main_key]['directions'][direction_key] = {
                'heading': heading,
                'subtitle_parts': set(), 
                'subtitle': "",
                'direction': group.direction,
                'courses': {}, # 3-daraja: Kurs
                'total_students': 0,
                'total_groups': 0
            }
            
        # 3-daraja: Kurs
        if course_year not in courses_dict[main_key]['directions'][direction_key]['courses']:
             courses_dict[main_key]['directions'][direction_key]['courses'][course_year] = {
                'semesters': {},
                'total_students': 0,
                'total_groups': 0
             }

        # 4-daraja: Semestr
        course_ptr = courses_dict[main_key]['directions'][direction_key]['courses'][course_year]
        if semester not in course_ptr['semesters']:
            course_ptr['semesters'][semester] = {
                'groups': [],
                'students_count': 0
            }
            
        # 5-daraja: Guruhni qo'shish
        semester_pointer = course_ptr['semesters'][semester]
        
        semester_pointer['groups'].append({
            'group': group,
            'students_count': students_count
        })
        semester_pointer['students_count'] += students_count
        
        # Statistikalarni yangilash
        course_ptr['total_students'] += students_count
        course_ptr['total_groups'] += 1
        
        dict_pointer = courses_dict[main_key]['directions'][direction_key]
        dict_pointer['total_students'] += students_count
        dict_pointer['total_groups'] += 1
        dict_pointer['subtitle_parts'].add(f"{course_year}-kurs, {semester}-semestr")
        
        courses_dict[main_key]['total_students'] += students_count
        courses_dict[main_key]['total_groups'] += 1

    # Formatlash va saralash (Listga o'tkazish)
    courses_list = []
    
    # Kalitlarni saralash: Yil (ASC) -> Ta'lim shakli (ASC)
    sorted_keys = sorted(courses_dict.keys(), key=lambda k: (str(k[0]), str(k[1])))
    
    for key in sorted_keys:
        year, edu_type = key
        year_data = courses_dict[key]
        formatted_directions = []
        
        # Yo'nalishlarni saralash
        sorted_dir_keys = sorted(year_data['directions'].keys(), 
                               key=lambda k: year_data['directions'][k]['heading'])
                               
        for d_key in sorted_dir_keys:
            d_data = year_data['directions'][d_key]
            
            # Subtitle
            # sorted_subs = sorted(list(d_data['subtitle_parts']), key=lambda x: x) 
            # d_data['subtitle'] = ", ".join(sorted_subs) 
            # Subtitle endi guruh va talaba soni
            d_data['subtitle'] = f"{d_data['total_groups']} guruh • {d_data['total_students']} talaba"
            
            # Kurslarni saralash
            formatted_courses = {}
            for c_year in sorted(d_data['courses'].keys()):
                c_data = d_data['courses'][c_year]
                
                # Semestrlarni saralash
                sorted_semesters = {}
                for sem in sorted(c_data['semesters'].keys()):
                    sorted_semesters[sem] = c_data['semesters'][sem]
                    # Guruhlar
                    sorted_semesters[sem]['groups'].sort(key=lambda x: x['group'].name)
                
                c_data['semesters'] = sorted_semesters
                formatted_courses[c_year] = c_data
            
            d_data['courses'] = formatted_courses
            formatted_directions.append(d_data)
        
        # Safe ID key generation for frontend
        safe_key = f"{year}-{edu_type}".replace(" ", "_").lower()
        
        courses_list.append({
            'year': year,
            'edu_type': edu_type,
            'key': safe_key,
            'directions': formatted_directions,
            'total_directions': len(formatted_directions),
            'total_students': year_data['total_students'],
            'total_groups': year_data['total_groups']
        })
    
    # Fakultetdagi barcha yo'nalishlarni popup uchun olish
    all_faculty_directions = Direction.query.filter_by(faculty_id=faculty.id).order_by(Direction.name).all()
    
    # Modal uchun yo'nalishlar ma'lumotlari
    directions_list_data = []
    used_formatted_directions = set()  # Dublikatlarni oldini olish uchun
    
    for direction in all_faculty_directions:
        first_group = direction.groups.first()
        if not first_group or not first_group.enrollment_year or not first_group.education_type:
            formatted_val = f"____ - {direction.code} - {direction.name}"
        else:
            et = first_group.education_type.strip().lower()
            edu_label = t('education_type_' + et) if et in ('kunduzgi', 'sirtqi', 'kechki', 'masofaviy') else t('education_type_not_set')
            formatted_val = f"{first_group.enrollment_year} - {direction.code} - {direction.name} ({edu_label})"
        if formatted_val not in used_formatted_directions:
            enrollment_year = str(first_group.enrollment_year) if first_group and first_group.enrollment_year else ''
            education_type = first_group.education_type.lower() if first_group and first_group.education_type else ''
            directions_list_data.append({
                'id': direction.id,
                'name': direction.name,
                'code': direction.code,
                'formatted_direction': formatted_val,
                'enrollment_year': enrollment_year,
                'education_type': education_type
            })
            used_formatted_directions.add(formatted_val)
    
    # Saralash
    directions_list_data.sort(key=lambda x: (x['code'] or '', x['name'] or ''))

    return render_template('dean/courses.html', 
                         faculty=faculty,
                         courses_list=courses_list,
                         all_directions=all_faculty_directions,
                         directions_list=directions_list_data,
                         groups_list=faculty.groups.order_by(Group.name).all())


# ==================== O'QITUVCHI-FAN BIRIKTIRISH ====================
# Assignments sahifasi o'chirildi - o'qituvchi biriktirish endi yo'nalish-semestr fanlaridan amalga oshiriladi
# @bp.route('/assignments')
# @login_required
# @dean_required
# def teacher_assignments():
#     ...

# @bp.route('/assignments/create', methods=['GET', 'POST'])
# @login_required
# @dean_required
# def create_assignment():
#     ...

# @bp.route('/assignments/<int:id>/delete', methods=['POST'])
# @login_required
# @dean_required
# def delete_assignment(id):
#     ...



# ==================== GURUHLAR ====================



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
        flash(t('faculty_not_assigned'), 'error')
        return redirect(url_for('main.dashboard'))
    
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '')
    course_year = request.args.get('course', type=int)
    semester = request.args.get('semester', type=int)
    education_type = request.args.get('education_type', '') or None
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
    
    # Filtrlash (faqat o'z fakulteti doirasida) - barcha tanlangan filtrlar birga qo'llaniladi (AND)
    if group_id and group_id in faculty_group_ids:
        query = query.filter(User.group_id == group_id)
    else:
        # Guruh bo'yicha filtrlash (direction, course, education_type - faculty_id har doim faculty)
        group_filters = {'faculty_id': faculty.id}
        if direction_id:
            direction = Direction.query.get(direction_id)
            if direction and direction.faculty_id == faculty.id:
                group_filters['direction_id'] = direction_id
            else:
                query = query.filter(User.id == -1)  # Noto'g'ri yo'nalish - hech narsa
                group_filters = None
        if course_year and group_filters is not None:
            group_filters['course_year'] = course_year
        if education_type and group_filters is not None:
            group_filters['education_type'] = education_type

        if group_filters is not None:
            groups_list = Group.query.filter_by(**group_filters).all()
            group_ids = [g.id for g in groups_list if g.id in faculty_group_ids]
            if group_ids:
                query = query.filter(User.group_id.in_(group_ids))
            else:
                query = query.filter(User.id == -1)

    # Semestr filtri - talabaning guruhidagi semestr bo'yicha (daraxtdagi 3-semestr bilan mos)
    if semester:
        query = query.join(Group, User.group_id == Group.id).filter(Group.semester == semester)
    
    # Ustun bo'yicha tartiblash
    sort = request.args.get('sort', 'name')
    order = request.args.get('order', 'asc') or 'asc'
    if sort == 'group':
        if not semester:
            query = query.outerjoin(Group, User.group_id == Group.id)
        order_col = Group.name
    else:
        order_col = {'name': User.full_name, 'passport': User.passport_number, 'phone': User.phone}.get(sort, User.full_name)
    direction = asc if order == 'asc' else desc
    query = query.order_by(direction(order_col))
    
    students = query.paginate(page=page, per_page=50, error_out=False)
    
    # Filtrlar uchun ma'lumotlar (faqat o'z fakulteti doirasida)
    from sqlalchemy import exists
    has_student = exists().where(User.group_id == Group.id, User.role == 'student')
    
    # Faqat ichida talaba bor bo'lgan guruhlar
    all_groups = Group.query.filter_by(faculty_id=faculty.id).order_by(Group.name).all()
    groups_with_students = Group.query.filter(
        Group.faculty_id == faculty.id,
        has_student
    ).order_by(Group.name).all()
    
    # Bir xil nomli guruhlarni umumlashtirish (faqat filtr uchun), A–Z tartibida
    unique_group_names = {}
    for g in groups_with_students:
        if g.name not in unique_group_names:
            unique_group_names[g.name] = g
    groups = sorted(unique_group_names.values(), key=lambda g: (g.name or '').lower())
    
    # Faqat ichida talaba bor bo'lgan yo'nalishlar (filtrda ko'rsatish uchun, A–Z)
    direction_ids_with_students = set(g.direction_id for g in groups_with_students if g.direction_id)
    directions = Direction.query.filter(Direction.faculty_id == faculty.id, Direction.id.in_(direction_ids_with_students)).all() if direction_ids_with_students else []
    directions = sorted(directions, key=lambda d: ((d.code or '').lower(), (d.name or '').lower()))
    
    # JavaScript uchun guruhlar ma'lumotlari (JSON formatida)
    groups_json = [{
        'id': g.id,
        'name': g.name,
        'faculty_id': g.faculty_id,
        'course_year': g.course_year,
        'semester': g.semester if g.semester else 1,
        'direction_id': g.direction_id,
        'education_type': g.education_type,
        'enrollment_year': g.enrollment_year
    } for g in groups]
    
    # JavaScript uchun ma'lumotlar (JSON formatida) - faqat o'z fakulteti uchun
    # Fakultet -> Kurslar
    faculty_courses = {}
    courses_set = set()
    for group in groups:
        if group.course_year:
            courses_set.add(group.course_year)
    faculty_courses[faculty.id] = sorted(list(courses_set))
    
    # Fakultet + Kurs -> Semestrlar (guruhlardan)
    faculty_course_semesters = {}
    faculty_course_semesters[faculty.id] = {}
    for course in range(1, 8):
        semesters_set = set()
        for group in Group.query.filter_by(faculty_id=faculty.id, course_year=course).all():
            if group.semester:
                semesters_set.add(group.semester)
        if semesters_set:
            faculty_course_semesters[faculty.id][course] = sorted(list(semesters_set))
    
    # Fakultet + Kurs + Semestr -> Ta'lim shakllari (guruhlardan)
    faculty_course_semester_education_types = {}
    faculty_course_semester_education_types[faculty.id] = {}
    for course in range(1, 8):
        faculty_course_semester_education_types[faculty.id][course] = {}
        for group in Group.query.filter_by(faculty_id=faculty.id, course_year=course).all():
            semester = group.semester if group.semester else 1
            if semester not in faculty_course_semester_education_types[faculty.id][course]:
                faculty_course_semester_education_types[faculty.id][course][semester] = set()
            if group.education_type:
                faculty_course_semester_education_types[faculty.id][course][semester].add(group.education_type)
        # Set'larni list'ga o'tkazish
        for semester in faculty_course_semester_education_types[faculty.id][course]:
            faculty_course_semester_education_types[faculty.id][course][semester] = sorted(list(faculty_course_semester_education_types[faculty.id][course][semester]), key=lambda x: (x or '').lower())
    
    # Fakultet + Kurs + Semestr + Ta'lim shakli -> Yo'nalishlar (guruhlardan, faqat ichida talaba bor bo'lgan yo'nalishlar)
    faculty_course_semester_education_directions = {}
    faculty_course_semester_education_directions[faculty.id] = {}
    for course in range(1, 8):
        faculty_course_semester_education_directions[faculty.id][course] = {}
        # Faqat ichida talaba bor bo'lgan guruhlar
        for group in Group.query.filter(
            Group.faculty_id == faculty.id,
            Group.course_year == course,
            has_student
        ).all():
            if not group.direction_id:
                continue
            semester = group.semester if group.semester else 1
            education_type = group.education_type if group.education_type else 'kunduzgi'
            if semester not in faculty_course_semester_education_directions[faculty.id][course]:
                faculty_course_semester_education_directions[faculty.id][course][semester] = {}
            if education_type not in faculty_course_semester_education_directions[faculty.id][course][semester]:
                faculty_course_semester_education_directions[faculty.id][course][semester][education_type] = []
            # Yo'nalishni qo'shish (takrorlanmaslik uchun tekshirish)
            direction = group.direction
            if direction and not any(d['id'] == direction.id for d in faculty_course_semester_education_directions[faculty.id][course][semester][education_type]):
                faculty_course_semester_education_directions[faculty.id][course][semester][education_type].append({
                    'id': direction.id,
                    'code': direction.code,
                    'name': direction.name,
                    'enrollment_year': group.enrollment_year,
                    'education_type': group.education_type
                })
        # Yo'nalishlarni tartiblash
        for semester in faculty_course_semester_education_directions[faculty.id][course]:
            for education_type in faculty_course_semester_education_directions[faculty.id][course][semester]:
                faculty_course_semester_education_directions[faculty.id][course][semester][education_type].sort(key=lambda x: ((x.get('code') or '').lower(), (x.get('name') or '').lower()))
    
    # Yo'nalish -> Guruhlar (faqat ichida talaba bor bo'lgan guruhlar, bir xil nomli guruhlarni umumlashtirish)
    direction_groups = {}
    for direction in directions:
        direction_groups[direction.id] = []
        # Faqat ichida talaba bor bo'lgan guruhlar
        groups_with_students = Group.query.filter(
            Group.direction_id == direction.id,
            Group.faculty_id == faculty.id,
            has_student
        ).all()
        
        # Bir xil nomli guruhlarni umumlashtirish
        unique_group_names = {}
        for group in groups_with_students:
            if group.name not in unique_group_names:
                unique_group_names[group.name] = group.id
        
        # Faqat unique nomli guruhlarni qo'shish
        for group_name, group_id in unique_group_names.items():
            direction_groups[direction.id].append({
                'id': group_id,
                'name': group_name
            })
        direction_groups[direction.id].sort(key=lambda x: (x['name'] or '').lower())
    
    # Teskari filtrlash uchun qo'shimcha ma'lumotlar (faqat o'z fakulteti uchun)
    # Kurs -> Fakultetlar (biz uchun faqat bitta fakultet)
    course_faculties = {}
    for course in range(1, 8):
        if course in courses_set:
            course_faculties[course] = [faculty.id]
    
    # Semestr -> Kurslar (guruhlardan)
    semester_courses = {}
    for group in groups:
        semester = group.semester if group.semester else 1
        course = group.course_year
        if semester not in semester_courses:
            semester_courses[semester] = set()
        semester_courses[semester].add(course)
    for semester in semester_courses:
        semester_courses[semester] = sorted(list(semester_courses[semester]))
    
    # Fakultet + Semestr -> Kurslar (guruhlardan)
    faculty_semester_courses = {}
    faculty_semester_courses[faculty.id] = {}
    for group in groups:
        semester = group.semester if group.semester else 1
        course = group.course_year
        if semester not in faculty_semester_courses[faculty.id]:
            faculty_semester_courses[faculty.id][semester] = set()
        faculty_semester_courses[faculty.id][semester].add(course)
    for semester in faculty_semester_courses[faculty.id]:
        faculty_semester_courses[faculty.id][semester] = sorted(list(faculty_semester_courses[faculty.id][semester]))
    
    # Ta'lim shakli -> Semestrlar (guruhlardan)
    education_type_semesters = {}
    for group in groups:
        education_type = group.education_type if group.education_type else 'kunduzgi'
        semester = group.semester if group.semester else 1
        if education_type not in education_type_semesters:
            education_type_semesters[education_type] = set()
        education_type_semesters[education_type].add(semester)
    for et in education_type_semesters:
        education_type_semesters[et] = sorted(list(education_type_semesters[et]))
    
    # Fakultet + Kurs + Ta'lim shakli -> Semestrlar (guruhlardan)
    faculty_course_education_semesters = {}
    faculty_course_education_semesters[faculty.id] = {}
    for course in range(1, 8):
        faculty_course_education_semesters[faculty.id][course] = {}
        for group in Group.query.filter_by(faculty_id=faculty.id, course_year=course).all():
            education_type = group.education_type if group.education_type else 'kunduzgi'
            semester = group.semester if group.semester else 1
            if education_type not in faculty_course_education_semesters[faculty.id][course]:
                faculty_course_education_semesters[faculty.id][course][education_type] = set()
            faculty_course_education_semesters[faculty.id][course][education_type].add(semester)
        for et in faculty_course_education_semesters[faculty.id][course]:
            faculty_course_education_semesters[faculty.id][course][et] = sorted(list(faculty_course_education_semesters[faculty.id][course][et]))
    
    # Yo'nalish -> Ta'lim shakllari (Guruhlardan olinadi)
    direction_education_types = {}
    for group in groups:
        if group.direction_id:
            direction_education_types[group.direction_id] = group.education_type
    
    # Semestrlarni guruhlardan olish
    semesters = sorted(list(set([g.semester for g in groups if g.semester])))
    
    # Fakultet + Kurs -> Guruhlar
    faculty_course_groups = {}
    faculty_course_groups[faculty.id] = {}
    for course in range(1, 8):
        faculty_course_groups[faculty.id][course] = []
        # Faqat ichida talaba bor bo'lgan guruhlar
        groups_with_students = Group.query.filter(
            Group.faculty_id == faculty.id,
            Group.course_year == course,
            has_student
        ).all()
        
        # Bir xil nomli guruhlarni umumlashtirish
        unique_group_names = {}
        for group in groups_with_students:
            if group.name not in unique_group_names:
                unique_group_names[group.name] = group.id
        
        # Faqat unique nomli guruhlarni qo'shish
        for group_name, group_id in unique_group_names.items():
            faculty_course_groups[faculty.id][course].append({
                'id': group_id,
                'name': group_name
            })
        faculty_course_groups[faculty.id][course].sort(key=lambda x: (x['name'] or '').lower())
    
    # Fakultet + Kurs + Semestr -> Guruhlar (guruhlardan, bir xil nomli guruhlarni umumlashtirish)
    faculty_course_semester_groups = {}
    faculty_course_semester_groups[faculty.id] = {}
    for course in range(1, 8):
        faculty_course_semester_groups[faculty.id][course] = {}
        # Faqat ichida talaba bor bo'lgan guruhlar
        groups_with_students = Group.query.filter(
            Group.faculty_id == faculty.id,
            Group.course_year == course,
            has_student
        ).all()
        
        for group in groups_with_students:
            semester_val = group.semester if group.semester else 1
            if semester_val not in faculty_course_semester_groups[faculty.id][course]:
                faculty_course_semester_groups[faculty.id][course][semester_val] = {}
            
            # Bir xil nomli guruhlarni umumlashtirish
            if group.name not in faculty_course_semester_groups[faculty.id][course][semester_val]:
                faculty_course_semester_groups[faculty.id][course][semester_val][group.name] = group.id
        
        # Dictionary'ni list'ga o'tkazish
        for s_val in faculty_course_semester_groups[faculty.id][course]:
            faculty_course_semester_groups[faculty.id][course][s_val] = [
                {'id': group_id, 'name': group_name}
                for group_name, group_id in faculty_course_semester_groups[faculty.id][course][s_val].items()
            ]
            faculty_course_semester_groups[faculty.id][course][s_val].sort(key=lambda x: (x['name'] or '').lower())
    
    # Fakultet + Kurs + Semestr + Ta'lim shakli -> Guruhlar (guruhlardan, bir xil nomli guruhlarni umumlashtirish)
    faculty_course_semester_education_groups = {}
    faculty_course_semester_education_groups[faculty.id] = {}
    for course in range(1, 8):
        faculty_course_semester_education_groups[faculty.id][course] = {}
        # Faqat ichida talaba bor bo'lgan guruhlar
        groups_with_students = Group.query.filter(
            Group.faculty_id == faculty.id,
            Group.course_year == course,
            has_student
        ).all()
        
        for group in groups_with_students:
            semester_val = group.semester if group.semester else 1
            education_type_val = group.education_type if group.education_type else 'kunduzgi'
            if semester_val not in faculty_course_semester_education_groups[faculty.id][course]:
                faculty_course_semester_education_groups[faculty.id][course][semester_val] = {}
            if education_type_val not in faculty_course_semester_education_groups[faculty.id][course][semester_val]:
                faculty_course_semester_education_groups[faculty.id][course][semester_val][education_type_val] = {}
            
            # Bir xil nomli guruhlarni umumlashtirish
            if group.name not in faculty_course_semester_education_groups[faculty.id][course][semester_val][education_type_val]:
                faculty_course_semester_education_groups[faculty.id][course][semester_val][education_type_val][group.name] = group.id
        
        # Dictionary'ni list'ga o'tkazish
        for s_val in faculty_course_semester_education_groups[faculty.id][course]:
            for et_val in faculty_course_semester_education_groups[faculty.id][course][s_val]:
                faculty_course_semester_education_groups[faculty.id][course][s_val][et_val] = [
                    {'id': group_id, 'name': group_name}
                    for group_name, group_id in faculty_course_semester_education_groups[faculty.id][course][s_val][et_val].items()
                ]
                faculty_course_semester_education_groups[faculty.id][course][s_val][et_val].sort(key=lambda x: (x['name'] or '').lower())
    
    # Guruh -> Yo'nalish, Ta'lim shakli, Semestr, Kurs, Fakultet
    group_info = {}
    for group in groups:
        group_info[group.id] = {
            'faculty_id': group.faculty_id,
            'course_year': group.course_year,
            'semester': group.semester if group.semester else 1,
            'education_type': group.education_type,
            'direction_id': group.direction_id
        }
    
    # Yo'nalish ma'lumotlari (JavaScript uchun)
    direction_info = {}
    for direction in directions:
        direction_info[direction.id] = {
            'id': direction.id,
            'code': direction.code,
            'name': direction.name
        }
    
    # Ta'lim shakllari (A–Z)
    education_types = sorted(set([g.education_type for g in groups if g.education_type]), key=lambda x: (x or '').lower())
    
    # Kurslar ro'yxati
    courses = sorted(list(courses_set)) if courses_set else []
    
    if request.args.get('partial'):
        return render_template('dean/students_partial.html',
                             students=students,
                             search=search,
                             current_course=course_year,
                             current_semester=semester,
                             current_education_type=education_type,
                             current_direction=direction_id,
                             current_group=group_id,
                             sort_by=sort,
                             sort_order=order)
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
                         groups_json=groups_json,
                         sort_by=sort,
                         sort_order=order)


@bp.route('/students/import', methods=['GET', 'POST'])
@login_required
@dean_required
def import_students():
    """Excel fayldan talabalar import qilish"""
    faculty = Faculty.query.get(current_user.faculty_id)
    if not faculty:
        flash(t('faculty_not_assigned'), 'error')
        return redirect(url_for('main.dashboard'))
    
    if request.method == 'POST':
        if 'excel_file' not in request.files:
            flash(t('file_not_selected'), 'error')
            return redirect(url_for('dean.students'))
        
        file = request.files['excel_file']
        if file.filename == '':
            flash(t('file_not_selected'), 'error')
            return redirect(url_for('dean.students'))
        
        if not file.filename.endswith(('.xlsx', '.xls')):
            flash(t('only_excel_files_allowed'), 'error')
            return redirect(url_for('dean.students'))
        
        try:
            from app.utils.excel_import import import_students_from_excel
            
            result = import_students_from_excel(file, faculty_id=faculty.id)
            
            if result['success']:
                if result['imported'] > 0:
                    flash(t('students_imported', imported_count=result['imported']), 'success')
                else:
                    flash(t('no_students_imported'), 'warning')
                
                if result['errors']:
                    errors_list = "; ".join(result['errors'][:5])
                    if len(result['errors']) > 5:
                        errors_list += f" va yana {len(result['errors']) - 5} ta xato"
                    flash(t('import_error_with_details', errors=errors_list), 'warning')
            else:
                flash(t('import_error', error=result['errors'][0] if result['errors'] else 'Noma`lum xatolik'), 'error')
                
        except ImportError as e:
            flash(t('excel_import_not_working', error=str(e)), 'error')
        except Exception as e:
            flash(t('import_error', error=str(e)), 'error')
        
        return redirect(url_for('dean.students'))
    
    return render_template('dean/import_students.html', faculty=faculty)


@bp.route('/students/import/sample')
@login_required
@dean_required
def download_sample_import():
    """Talabalar import qilish uchun namuna Excel faylni yuklab berish (tanlangan til bo'yicha)"""
    try:
        from app.utils.excel_import import generate_sample_file
        lang = session.get('language', 'uz')
        file_stream = generate_sample_file(lang=lang)
        download_name = t('sample_filename_students') + '.xlsx'
        return send_file(
            file_stream,
            as_attachment=True,
            download_name=download_name,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
    except Exception as e:
        flash(t('template_file_creation_error', error=str(e)), 'error')
        return redirect(url_for('dean.import_students'))


@bp.route('/students/export')
@login_required
@dean_required
def export_students():
    """Dekan uchun talabalar ro'yxatini Excel formatida yuklab olish (faqat o'z fakulteti)"""
    faculty = Faculty.query.get(current_user.faculty_id)
    if not faculty:
        flash(t('faculty_not_assigned'), 'error')
        return redirect(url_for('main.dashboard'))
    
    try:
        from app.utils.excel_export import create_students_excel
    except ImportError:
        flash(t('openpyxl_not_installed'), 'error')
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
        flash(t('faculty_not_assigned'), 'error')
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
        enrollment_year = request.form.get('enrollment_year', type=int)
        
        # Talaba ID majburiy
        if not student_id:
            flash(t('student_id_required'), 'error')
            return render_template('dean/create_student.html', faculty=faculty)
        
        if User.query.filter_by(student_id=student_id).first():
            flash(t('student_id_already_exists'), 'error')
            return render_template('dean/create_student.html', faculty=faculty)
        
        # Pasport seriyasi va raqami majburiy
        if not passport_number:
            flash(t('passport_required'), 'error')
            return render_template('dean/create_student.html', faculty=faculty)
        
        # Email ixtiyoriy, lekin agar kiritilgan bo'lsa, unikallikni tekshirish
        if email:
            if User.query.filter_by(email=email).first():
                flash(t('email_already_exists'), 'error')
                return render_template('dean/create_student.html', faculty=faculty)
        
        # Pasport raqamini katta harfga o'zgartirish
        passport_number = passport_number.upper()
        
        # Tug'ilgan sanani parse qilish (yyyy-mm-dd)
        parsed_birth_date = None
        if birth_date:
            try:
                parsed_birth_date = datetime.strptime(birth_date, '%Y-%m-%d').date()
            except ValueError:
                flash(t('birthdate_invalid_format'), 'error')
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
            description=description.strip() if description and description.strip() else None,
            enrollment_year=enrollment_year
        )
        
        # Email maydonini alohida o'rnatish (agar bo'sh bo'lsa, o'rnatmaymiz)
        if email_value:
            student.email = email_value
        
        # Parolni pasport raqamiga o'rnatish
        student.set_password(passport_number)
        
        # Guruh biriktirish
        group_id = request.form.get('group_id')
        manual_group_name = request.form.get('manual_group_name', '').strip()
        
        if manual_group_name:
            # Yangi guruh yaratish uchun kerakli ma'lumotlar
            # Dekan uchun faculty_id doimiy
            direction_id = request.form.get('direction_id')
            course_year = request.form.get('course_year')
            semester = request.form.get('semester')
            education_type = request.form.get('education_type')
            # Use same enrollment year for group if provided, or student's enrollment year
            group_enrollment_year = enrollment_year
            
            if direction_id and course_year and semester and education_type:
                # Guruh mavjudligini tekshirish
                existing_group = Group.query.filter_by(
                    name=manual_group_name,
                    faculty_id=faculty.id,
                    direction_id=int(direction_id),
                    course_year=int(course_year),
                    semester=int(semester),
                    education_type=education_type,
                    enrollment_year=group_enrollment_year
                ).first()
                
                if existing_group:
                    student.group_id = existing_group.id
                else:
                    new_group = Group(
                        name=manual_group_name,
                        faculty_id=faculty.id,
                        direction_id=int(direction_id),
                        course_year=int(course_year),
                        semester=int(semester),
                        education_type=education_type,
                        enrollment_year=group_enrollment_year
                    )
                    db.session.add(new_group)
                    db.session.flush() # ID olish uchun
                    student.group_id = new_group.id
        elif group_id:
            student.group_id = int(group_id)
            
        db.session.add(student)
        
        try:
            db.session.commit()
        except Exception as e:
            error_str = str(e).lower()
            if 'email' in error_str and ('not null' in error_str or 'constraint' in error_str):
                db.session.rollback()
                student.email = ''
                db.session.add(student)
                db.session.commit()
            else:
                raise
        
        flash(t('student_created', full_name=student.full_name), 'success')
        return redirect(url_for('dean.students'))
    
    # Fakultetdagi barcha yo'nalishlar
    all_directions = Direction.query.filter_by(faculty_id=faculty.id).order_by(Direction.name).all()
    return render_template('dean/create_student.html', faculty=faculty, all_directions=all_directions)


@bp.route('/students/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@dean_required
def edit_student(id):
    """Dekan uchun talabani tahrirlash (faqat o'z fakulteti doirasida)"""
    from datetime import datetime
    
    faculty = Faculty.query.get(current_user.faculty_id)
    if not faculty:
        flash(t('faculty_not_assigned'), 'error')
        return redirect(url_for('main.dashboard'))
    
    student = User.query.get_or_404(id)
    
    # Faqat talaba va shu fakultetga tegishli guruhda bo'lishi kerak (agar guruh bo'lsa)
    if student.role != 'student':
        flash(t('user_not_student'), 'error')
        return redirect(url_for('dean.students'))
    
    # Agar talabaning guruh bo'lsa, fakultetni tekshirish
    if student.group and student.group.faculty_id != faculty.id:
        flash(t('no_permission_to_edit_student'), 'error')
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
        enrollment_year = request.form.get('enrollment_year', type=int)
        
        # Talaba ID majburiy
        if not student_id:
            flash(t('student_id_required'), 'error')
            return render_template('dean/edit_student.html', faculty=faculty, student=student)
        
        # Talaba ID unikalligi (boshqa talabada bo'lmasligi kerak)
        existing_student = User.query.filter_by(student_id=student_id).first()
        if existing_student and existing_student.id != student.id:
            flash(t('student_id_already_exists_other_student'), 'error')
            return render_template('dean/edit_student.html', faculty=faculty, student=student)
        
        # Pasport seriyasi va raqami majburiy
        if not passport_number:
            flash(t('passport_required'), 'error')
            return render_template('dean/edit_student.html', faculty=faculty, student=student)
        
        # Email ixtiyoriy, lekin agar kiritilgan bo'lsa, unikallikni tekshirish
        if email:
            existing_student_with_email = User.query.filter_by(email=email).first()
            if existing_student_with_email and existing_student_with_email.id != student.id:
                flash(t('email_already_exists_other_student'), 'error')
                return render_template('dean/edit_student.html', faculty=faculty, student=student)
        
        # Pasport raqamini katta harfga o'zgartirish
        passport_number = passport_number.upper()
        
        # Tug'ilgan sanani parse qilish (yyyy-mm-dd)
        if birth_date_str:
            try:
                student.birth_date = datetime.strptime(birth_date_str, '%Y-%m-%d').date()
            except ValueError:
                flash(t('birthdate_invalid_format'), 'error')
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
        student.enrollment_year = enrollment_year
        
        # Guruh biriktirish: agar mavjud guruh tanlangan (group_id) bo'lsa uni ishlatamiz; manual_group_name faqat yangi guruh rejimida
        group_id = request.form.get('group_id')
        manual_group_name = request.form.get('manual_group_name', '').strip()
        
        if group_id:
            student.group_id = int(group_id)
        elif manual_group_name:
            # Yangi guruh yaratish uchun kerakli ma'lumotlar
            direction_id = request.form.get('direction_id')
            course_year = request.form.get('course_year')
            semester = request.form.get('semester')
            education_type = request.form.get('education_type')
            group_enrollment_year = enrollment_year
            education_type = request.form.get('education_type')
            
            if direction_id and course_year and semester and education_type:
                # Guruh mavjudligini tekshirish
                existing_group = Group.query.filter_by(
                    name=manual_group_name,
                    faculty_id=faculty.id,
                    direction_id=int(direction_id),
                    course_year=int(course_year),
                    semester=int(semester),
                    education_type=education_type,
                    enrollment_year=group_enrollment_year
                ).first()
                
                if existing_group:
                    student.group_id = existing_group.id
                else:
                    new_group = Group(
                        name=manual_group_name,
                        faculty_id=faculty.id,
                        direction_id=int(direction_id),
                        course_year=int(course_year),
                        semester=int(semester),
                        education_type=education_type,
                        enrollment_year=group_enrollment_year
                    )
                    db.session.add(new_group)
                    db.session.flush() # ID olish uchun
                    student.group_id = new_group.id
        else:
            student.group_id = None
            
        db.session.commit()
        flash(t('student_updated', full_name=student.full_name), 'success')
        return redirect(url_for('dean.students'))
    
    # Fakultetdagi barcha yo'nalishlar
    all_directions = Direction.query.filter_by(faculty_id=faculty.id).order_by(Direction.name).all()
    return render_template('dean/edit_student.html', faculty=faculty, student=student, all_directions=all_directions)


@bp.route('/students/<int:id>/toggle', methods=['POST'])
@login_required
@dean_required
def toggle_student_status(id):
    """Talabani bloklash / blokdan chiqarish (dekan faqat o'z fakulteti bo'yicha)"""
    faculty = Faculty.query.get(current_user.faculty_id)
    if not faculty:
        flash(t('faculty_not_assigned'), 'error')
        return redirect(url_for('main.dashboard'))
    
    student = User.query.get_or_404(id)
    if student.role != 'student' or not student.group or student.group.faculty_id != faculty.id:
        flash(t('no_permission_for_operation'), 'error')
        return redirect(url_for('dean.students'))
    
    student.is_active = not student.is_active
    db.session.commit()
    
    status = "faollashtirildi" if student.is_active else "bloklandi"
    flash(t('student_status_changed', full_name=student.full_name, status=status), 'success')
    return redirect(url_for('dean.students'))


@bp.route('/students/<int:id>/reset-password', methods=['POST'])
@login_required
@dean_required
def reset_student_password(id):
    """Talaba parolini boshlang'ich holatga qaytarish (student123)"""
    faculty = Faculty.query.get(current_user.faculty_id)
    if not faculty:
        flash(t('faculty_not_assigned'), 'error')
        return redirect(url_for('main.dashboard'))
    
    student = User.query.get_or_404(id)
    if student.role != 'student' or not student.group or student.group.faculty_id != faculty.id:
        flash(t('no_permission_for_operation'), 'error')
        return redirect(url_for('dean.students'))
    
    new_password = 'student123'
    student.set_password(new_password)
    db.session.commit()
    flash(t('student_password_reset', full_name=student.full_name, new_password=new_password), 'success')
    return redirect(url_for('dean.students'))


@bp.route('/students/<int:id>/delete', methods=['POST'])
@login_required
@dean_required
def delete_student(id):
    """Talabani o'chirish"""
    faculty = Faculty.query.get(current_user.faculty_id)
    if not faculty:
        flash(t('faculty_not_assigned'), 'error')
        return redirect(url_for('main.dashboard'))
    
    student = User.query.get_or_404(id)
    if getattr(student, 'is_superadmin', False):
        flash(t('cannot_delete_superadmin'), 'error')
        return redirect(url_for('dean.students'))
    if student.role != 'student':
        flash(t('user_not_student'), 'error')
        return redirect(url_for('dean.students'))
    
    # Fakultet tekshiruvi (agar guruh bo'lsa)
    if student.group and student.group.faculty_id != faculty.id:
        flash(t('no_permission_for_operation'), 'error')
        return redirect(url_for('dean.students'))
    
    student_name = student.full_name
    
    # Talabaning xabarlarini o'chirish (sender yoki receiver bo'lgan)
    Message.query.filter(
        (Message.sender_id == student.id) | (Message.receiver_id == student.id)
    ).delete(synchronize_session=False)
    
    # Talabaning topshiriq yuborishlarini o'chirish
    Submission.query.filter_by(student_id=student.id).delete(synchronize_session=False)
    
    # Talabaning dars ko'rish yozuvlarini o'chirish (lesson_view.student_id NOT NULL)
    LessonView.query.filter_by(student_id=student.id).delete(synchronize_session=False)
    
    # Talabaning parol tiklash tokenlarini o'chirish (password_reset_token.user_id NOT NULL)
    PasswordResetToken.query.filter_by(user_id=student.id).delete(synchronize_session=False)
    
    # Talabaning to'lovlarini o'chirish
    StudentPayment.query.filter_by(student_id=student.id).delete()
    
    # Talabani o'chirish
    db.session.delete(student)
    db.session.commit()
    flash(t('student_deleted', student_name=student_name), 'success')
    return redirect(url_for('dean.students'))


# ==================== O'QITUVCHILAR ====================
@bp.route('/teachers')
@login_required
@dean_required
def teachers():
    faculty = Faculty.query.get(current_user.faculty_id)
    if not faculty:
        flash(t('faculty_not_assigned'), 'error')
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
    """Yo'nalishlar sahifasi – admin faculty_detail ga mos (Yil+Ta'lim shakli → Yo'nalish → Kurs → Semestr → Guruhlar)"""
    faculty = Faculty.query.get(current_user.faculty_id)
    if not faculty:
        flash(t('faculty_not_assigned'), 'error')
        return redirect(url_for('main.dashboard'))

    course_filter = request.args.get('course', type=int)
    direction_filter = request.args.get('direction', type=int)
    search = request.args.get('search', '')

    all_directions = Direction.query.filter_by(faculty_id=faculty.id).order_by(Direction.name).all()
    all_groups = list(faculty.groups.order_by(Group.course_year, Group.name).all())

    if course_filter:
        all_groups = [g for g in all_groups if g.course_year == course_filter]
    if direction_filter:
        all_groups = [g for g in all_groups if g.direction_id == direction_filter]

    # Qidiruv: qabul yili, kod, nom, ta'lim shakli bo'yicha
    if search:
        search_lower = search.lower().strip()
        filtered_groups = []
        for group in all_groups:
            # Qabul yili bo'yicha
            if group.enrollment_year and search_lower in str(group.enrollment_year).lower():
                filtered_groups.append(group)
                continue
            # Ta'lim shakli bo'yicha
            if group.education_type and search_lower in group.education_type.lower():
                filtered_groups.append(group)
                continue
            # Yo'nalish kodi va nomi bo'yicha
            if group.direction:
                if (group.direction.code and search_lower in group.direction.code.lower()) or \
                   (group.direction.name and search_lower in group.direction.name.lower()):
                    filtered_groups.append(group)
                    continue
        all_groups = filtered_groups

    courses_dict = {}
    for group in all_groups:
        if not group.semester:
            continue
        semester = group.semester
        course_year = group.course_year or ((semester + 1) // 2)
        enrollment_year = group.enrollment_year if group.enrollment_year else "Noma'lum"
        edu_type = group.education_type if group.education_type else "Noma'lum"

        if course_filter and course_year != course_filter:
            continue
        if direction_filter and group.direction_id != direction_filter:
            continue

        students_count = User.query.filter(User.group_id == group.id, User.role == 'student').count()
        if students_count == 0:
            continue

        main_key = (enrollment_year, edu_type)
        if main_key not in courses_dict:
            courses_dict[main_key] = {'directions': {}, 'total_groups': 0, 'total_students': 0}

        direction_key = (group.direction_id, group.education_type)
        if direction_key not in courses_dict[main_key]['directions']:
            if group.direction:
                code = group.direction.code
                name = group.direction.name
                et = (group.education_type or "").strip().lower()
                if et in ('kunduzgi', 'sirtqi', 'kechki', 'masofaviy'):
                    edu_type_str = t('education_type_' + et)
                else:
                    edu_type_str = t('education_type_not_set')
                enrollment_year_str = str(group.enrollment_year) if group.enrollment_year else "____"
                heading = f"{enrollment_year_str} - {code} - {name} ({edu_type_str})"
            else:
                heading = "____ - Biriktirilmagan"

            courses_dict[main_key]['directions'][direction_key] = {
                'heading': heading,
                'subtitle_parts': set(),
                'subtitle': "",
                'direction': group.direction,
                'enrollment_year': enrollment_year,
                'education_type': edu_type,
                'courses': {},
                'total_students': 0,
                'total_groups': 0,
            }

        if course_year not in courses_dict[main_key]['directions'][direction_key]['courses']:
            courses_dict[main_key]['directions'][direction_key]['courses'][course_year] = {
                'semesters': {}, 'total_students': 0, 'total_groups': 0,
            }

        course_ptr = courses_dict[main_key]['directions'][direction_key]['courses'][course_year]
        if semester not in course_ptr['semesters']:
            course_ptr['semesters'][semester] = {'groups': [], 'students_count': 0}

        semester_pointer = course_ptr['semesters'][semester]
        semester_pointer['groups'].append({'group': group, 'students_count': students_count})
        semester_pointer['students_count'] += students_count

        course_ptr['total_students'] += students_count
        course_ptr['total_groups'] += 1
        dict_pointer = courses_dict[main_key]['directions'][direction_key]
        dict_pointer['total_students'] += students_count
        dict_pointer['total_groups'] += 1
        dict_pointer['subtitle_parts'].add(f"{course_year}-kurs, {semester}-semestr")
        courses_dict[main_key]['total_students'] += students_count
        courses_dict[main_key]['total_groups'] += 1

    sorted_keys = sorted(courses_dict.keys(), key=lambda k: ((k[0] if k[0] is not None else 9999), str(k[1])))
    courses_list = []
    for key in sorted_keys:
        year, edu_type = key
        year_data = courses_dict[key]
        formatted_directions = []
        sorted_dir_keys = sorted(year_data['directions'].keys(), key=lambda k: year_data['directions'][k]['heading'])
        for d_key in sorted_dir_keys:
            d_data = year_data['directions'][d_key]
            sorted_subs = sorted(list(d_data['subtitle_parts']), key=lambda x: x)
            d_data['subtitle'] = ", ".join(sorted_subs)
            formatted_courses = {}
            for c_year in sorted(d_data['courses'].keys()):
                c_data = d_data['courses'][c_year]
                sorted_semesters = {}
                for sem in sorted(c_data['semesters'].keys()):
                    sorted_semesters[sem] = c_data['semesters'][sem]
                    sorted_semesters[sem]['groups'].sort(key=lambda x: x['group'].name)
                c_data['semesters'] = sorted_semesters
                formatted_courses[c_year] = c_data
            d_data['courses'] = formatted_courses
            formatted_directions.append(d_data)

        safe_key = f"{year}-{edu_type}".replace(" ", "_").lower()
        courses_list.append({
            'year': year,
            'edu_type': edu_type,
            'key': safe_key,
            'directions': formatted_directions,
            'total_directions': len(formatted_directions),
            'total_students': year_data['total_students'],
            'total_groups': year_data['total_groups'],
        })

    used_combinations = set()
    directions_list_data = []
    groups_with_directions = db.session.query(
        Group.direction_id, Group.enrollment_year, Group.education_type
    ).filter(
        Group.faculty_id == faculty.id,
        Group.direction_id.isnot(None),
    ).distinct().all()

    for d_id, yr, e_type in groups_with_directions:
        direction = Direction.query.get(d_id)
        if not direction:
            continue
        combination_key = f"{d_id}_{yr}_{e_type}"
        if combination_key in used_combinations:
            continue
        year_str = str(yr) if yr else "____"
        et = (e_type or "").strip().lower()
        edu_type_str = t('education_type_' + et) if et in ('kunduzgi', 'sirtqi', 'kechki', 'masofaviy') else (t('education_type_not_set') if e_type else "")
        formatted = f"{year_str} - {direction.code} - {direction.name}"
        if edu_type_str:
            formatted += f" ({edu_type_str})"
        directions_list_data.append({
            'id': direction.id,
            'name': direction.name,
            'code': direction.code,
            'enrollment_year': yr,
            'education_type': e_type,
            'description': direction.description,
            'formatted_direction': formatted,
        })
        used_combinations.add(combination_key)

    for direction in Direction.query.filter_by(faculty_id=faculty.id).all():
        has_groups = db.session.query(Group).filter(
            Group.direction_id == direction.id,
            Group.faculty_id == faculty.id,
        ).first() is not None
        if has_groups:
            continue
        directions_list_data.append({
            'id': direction.id,
            'name': direction.name,
            'code': direction.code,
            'enrollment_year': None,
            'education_type': None,
            'description': direction.description,
            'formatted_direction': f"____ - {direction.code} - {direction.name}",
        })

    directions_list_data.sort(key=lambda x: ((x['enrollment_year'] or 9999), x['code'] or '', x['name'] or ''))
    groups_list = list(faculty.groups.order_by(Group.name).all())
    all_courses = sorted(set(g.course_year for g in groups_list if g.course_year))

    return render_template(
        'dean/faculty_directions.html',
        faculty=faculty,
        courses_list=courses_list,
        all_directions=all_directions,
        directions_list=directions_list_data,
        groups_list=groups_list,
        all_courses=all_courses,
        course_filter=course_filter,
        direction_filter=direction_filter,
        search=search,
    )


@bp.route('/directions/import', methods=['GET', 'POST'])
@login_required
@dean_required
def import_directions():
    """Excel fayldan yo'nalish va guruhlarni import qilish"""
    faculty = Faculty.query.get(current_user.faculty_id)
    if not faculty:
        flash(t('faculty_not_assigned'), 'error')
        return redirect(url_for('main.dashboard'))
    
    if request.method == 'POST':
        if 'excel_file' not in request.files:
            flash(t('file_not_selected'), 'error')
            return redirect(url_for('dean.import_directions'))
        
        file = request.files['excel_file']
        if file.filename == '':
            flash(t('file_not_selected'), 'error')
            return redirect(url_for('dean.import_directions'))
        
        if not file.filename.endswith(('.xlsx', '.xls')):
            flash(t('only_excel_files_allowed'), 'error')
            return redirect(url_for('dean.import_directions'))
        
        try:
            from app.utils.excel_import import import_directions_from_excel
            result = import_directions_from_excel(file, faculty_id=faculty.id)
            
            if result['success']:
                d_count = result.get('imported_directions', 0)
                g_count = result.get('imported_groups', 0)
                if d_count or g_count:
                    flash(t('directions_and_groups_imported', d_count=d_count, g_count=g_count), 'success')
                else:
                    flash(t('no_records_imported'), 'warning')
                
                errors = result.get('errors', [])
                if errors:
                    errors_list = "; ".join(errors[:5])
                    if len(errors) > 5:
                        errors_list += f" va yana {len(errors) - 5} ta xato"
                    flash(t('import_error_with_details', errors=errors_list), 'warning')
            else:
                errors = result.get('errors', [])
                flash(t('import_error', error=errors[0] if errors else 'Import xatosi'), 'error')
        
        except ImportError as e:
            flash(t('excel_import_not_working', error=str(e)), 'error')
        except Exception as e:
            flash(t('import_error', error=str(e)), 'error')
        
        return redirect(url_for('dean.directions'))
    
    return render_template('dean/import_directions.html', faculty=faculty)


@bp.route('/directions/create', methods=['GET', 'POST'])
@login_required
@dean_required
def create_direction():
    faculty = Faculty.query.get(current_user.faculty_id)
    if not faculty:
        flash(t('faculty_not_assigned'), 'error')
        return redirect(url_for('main.dashboard'))
    
    if request.method == 'POST':
        name = request.form.get('name')
        code = request.form.get('code', '').strip()
        description = request.form.get('description', '')
        
        # Validatsiya
        if not name or not code:
            flash(t('direction_name_and_code_required'), 'error')
            return render_template('dean/create_direction.html', faculty=faculty)
        if not code.isdigit():
            flash(t('direction_code_digits_only'), 'error')
            return render_template('dean/create_direction.html', faculty=faculty)
        
        # Kod takrorlanmasligini tekshirish (faqat fakultet va kod bo'yicha)
        existing = Direction.query.filter_by(
            code=code,
            faculty_id=faculty.id
        ).first()
        
        if existing:
            flash(t('direction_code_already_exists'), 'error')
            return render_template('dean/create_direction.html', faculty=faculty)
        
        direction = Direction(
            name=name,
            code=code,
            description=description,
            faculty_id=faculty.id
        )
        db.session.add(direction)
        db.session.commit()
        
        flash(t('direction_created'), 'success')
        return redirect(url_for('dean.directions'))
    
    return render_template('dean/create_direction.html', faculty=faculty)





@bp.route('/directions/<int:id>/assign-groups', methods=['POST'])
@login_required
@dean_required
def assign_groups_to_direction(id):
    direction = Direction.query.get_or_404(id)
    
    # Fakultet tekshiruvi
    if direction.faculty_id != current_user.faculty_id:
        flash(t('no_permission_for_operation'), 'error')
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
    flash(t('groups_assigned_to_direction'), 'success')
    return redirect(url_for('dean.direction_detail', id=id))


@bp.route('/directions/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@dean_required
def edit_direction(id):
    direction = Direction.query.get_or_404(id)
    
    # Fakultet tekshiruvi
    if direction.faculty_id != current_user.faculty_id:
        flash(t('no_permission_for_operation'), 'error')
        return redirect(url_for('dean.directions'))
    
    if request.method == 'POST':
        name = request.form.get('name')
        code = request.form.get('code', '').upper()
        description = request.form.get('description', '')
        
        if not name or not code:
            flash(t('direction_name_and_code_required_fill'), 'error')
            return render_template('dean/edit_direction.html', direction=direction)
        
        # Kod takrorlanmasligini tekshirish (o'z kodini hisobga olmasdan)
        existing = Direction.query.filter(
            Direction.faculty_id == current_user.faculty_id,
            Direction.code == code,
            Direction.id != id
        ).first()
        if existing:
            flash(t('direction_code_already_exists'), 'error')
            return render_template('dean/edit_direction.html', direction=direction)
        
        direction.name = name
        direction.code = code
        direction.description = description
        
        db.session.commit()
        
        flash(t('direction_updated'), 'success')
        return redirect(url_for('dean.directions'))
    
    return render_template('dean/edit_direction.html', direction=direction)


@bp.route('/directions/<int:id>/delete', methods=['POST'])
@login_required
@dean_required
def delete_direction(id):
    direction = Direction.query.get_or_404(id)
    
    # Fakultet tekshiruvi
    if direction.faculty_id != current_user.faculty_id:
        flash(t('no_permission_for_operation'), 'error')
        return redirect(url_for('dean.directions'))
    
    # Guruhlar borligini tekshirish
    groups = direction.groups.all()
    if groups:
        total_students = sum(g.students.count() for g in groups)
        if total_students > 0:
            flash(t('direction_has_groups_and_students', groups_count=len(groups), total_students=total_students), 'error')
        else:
            flash(t('direction_has_groups', groups_count=len(groups)), 'error')
    else:
        db.session.delete(direction)
        db.session.commit()
        flash(t('direction_deleted'), 'success')
    
    return redirect(url_for('dean.directions'))


@bp.route('/directions/<int:id>')
@login_required
@dean_required
def direction_detail(id):
    direction = Direction.query.get_or_404(id)
    if direction.faculty_id != current_user.faculty_id:
        return redirect(url_for('dean.directions'))
    
    first_group = Group.query.filter_by(direction_id=id).order_by(Group.enrollment_year.desc()).first()
    if first_group and first_group.enrollment_year and first_group.education_type:
        return redirect(url_for('dean.direction_groups_with_params', id=id, year=first_group.enrollment_year, education_type=first_group.education_type))
    
    return redirect(url_for('dean.directions'))


@bp.route('/directions/<int:id>/<int:year>/<string:education_type>/groups')
@login_required
@dean_required
def direction_groups_with_params(id, year, education_type):
    """Yo'nalish guruhlari sahifasi - qabul yili va ta'lim shakli bilan"""
    direction = Direction.query.get_or_404(id)
    
    # Fakultet tekshiruvi
    if direction.faculty_id != current_user.faculty_id:
        flash(t('no_access_permission'), 'error')
        return redirect(url_for('dean.directions'))
    
    # Berilgan qabul yili va ta'lim shakli bo'yicha guruhlar
    groups = Group.query.filter_by(
        direction_id=direction.id,
        enrollment_year=year,
        education_type=education_type
    ).order_by(Group.course_year, Group.name).all()
    
    if not groups:
        flash(t('no_groups_for_year_education_type', year=year, education_type=education_type), 'error')
        return redirect(url_for('dean.directions'))
    
    # Har bir guruh uchun talabalar soni
    group_stats = {}
    for group in groups:
        group_stats[group.id] = group.students.count()
    
    return render_template('dean/direction_detail.html',
                         direction=direction,
                         groups=groups,
                         group_stats=group_stats,
                         enrollment_year=year,
                         education_type=education_type)


# ==================== O'QUV REJA ====================
@bp.route('/directions/<int:id>/curriculum')
@bp.route('/directions/<int:id>/<int:year>/<string:education_type>/curriculum')
@login_required
@dean_required
def direction_curriculum(id, year=None, education_type=None):
    """Yo'nalish o'quv rejasi sahifasi (Context aware)"""
    direction = Direction.query.get_or_404(id)
    
    # Agar yil yoki ta'lim shakli berilmagan bo'lsa, redirect qilamiz
    if not year or not education_type:
        first_group = Group.query.filter_by(direction_id=id).order_by(Group.enrollment_year.desc()).first()
        if first_group and first_group.enrollment_year and first_group.education_type:
            return redirect(url_for('dean.direction_curriculum', id=id, year=first_group.enrollment_year, education_type=first_group.education_type))
            
    # Fakultet tekshiruvi
    if direction.faculty_id != current_user.faculty_id:
        flash(t('no_access_permission'), 'error')
        return redirect(url_for('dean.courses'))
    
    # Contextni aniqlash (yil va ta'lim shakli bo'yicha)
    enrollment_year = year
    education_type = education_type

    # Barcha fanlar
    all_subjects = Subject.query.order_by(Subject.name).all()
    
    # O'quv rejadagi fanlar (semestr bo'yicha guruhlangan)
    curriculum_by_semester = {}
    semester_totals = {}  # Har bir semestr uchun jami soat va kredit
    semester_auditoriya = {}  # Har bir semestr uchun auditoriya soatlari
    semester_mustaqil = {}  # Har bir semestr uchun mustaqil ta'lim soatlari
    total_hours = 0
    total_credits = 0
    
    # Independent Curriculum filtrlash
    items_query = direction.curriculum_items.join(Subject)
    if enrollment_year and education_type:
        items_query = items_query.filter(
            DirectionCurriculum.enrollment_year == enrollment_year,
            DirectionCurriculum.education_type == education_type
        )
    
    for item in items_query.order_by(
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
                         enrollment_year=enrollment_year,
                         education_type=education_type,
                         all_subjects=all_subjects,
                         curriculum_by_semester=curriculum_by_semester,
                         semester_totals=semester_totals,
                         semester_auditoriya=semester_auditoriya,
                         semester_mustaqil=semester_mustaqil,
                         total_hours=total_hours,
                         total_credits=total_credits)


@bp.route('/directions/<int:id>/curriculum/export')
@bp.route('/directions/<int:id>/<int:year>/<string:education_type>/curriculum/export')
@login_required
@dean_required
def export_curriculum(id, year=None, education_type=None):
    """O'quv rejani Excel formatida export qilish"""
    from app.utils.excel_export import create_curriculum_excel
    
    direction = Direction.query.get_or_404(id)
    
    # Fakultet tekshiruvi
    if direction.faculty_id != current_user.faculty_id:
        flash(t('no_access_permission'), 'error')
        return redirect(url_for('dean.courses'))
    
    # O'quv rejadagi barcha elementlar (independent curriculum support)
    items_query = direction.curriculum_items.join(Subject)
    if year and education_type:
        items_query = items_query.filter(
            DirectionCurriculum.enrollment_year == year,
            DirectionCurriculum.education_type == education_type
        )
        
    curriculum_items = items_query.order_by(
        DirectionCurriculum.semester,
        Subject.name
    ).all()
    
    excel_file = create_curriculum_excel(direction, curriculum_items)
    
    filename = f"oquv_reja_{direction.code}"
    if year and education_type:
        filename += f"_{year}_{education_type}"
    filename += f"_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    
    return send_file(
        excel_file,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=filename
    )


@bp.route('/directions/<int:id>/curriculum/import', methods=['GET', 'POST'])
@bp.route('/directions/<int:id>/<int:year>/<string:education_type>/curriculum/import', methods=['GET', 'POST'])
@login_required
@dean_required
def import_curriculum(id, year=None, education_type=None):
    """O'quv rejani Excel fayldan import qilish"""
    from app.utils.excel_import import import_curriculum_from_excel
    
    direction = Direction.query.get_or_404(id)
    
    # Fakultet tekshiruvi
    if direction.faculty_id != current_user.faculty_id:
        flash(t('no_access_permission'), 'error')
        return redirect(url_for('dean.courses'))
    
    if request.method == 'POST':
        if 'file' not in request.files:
            flash(t('file_not_selected'), 'error')
            if year and education_type:
                return redirect(url_for('dean.direction_curriculum', id=id, year=year, education_type=education_type))
            return redirect(url_for('dean.direction_curriculum', id=id))
        
        file = request.files['file']
        if file.filename == '':
            flash(t('file_not_selected'), 'error')
            if year and education_type:
                return redirect(url_for('dean.direction_curriculum', id=id, year=year, education_type=education_type))
            return redirect(url_for('dean.direction_curriculum', id=id))
        
        if not file.filename.endswith(('.xlsx', '.xls')):
            flash(t('only_xlsx_or_xls_allowed'), 'error')
            if year and education_type:
                return redirect(url_for('dean.direction_curriculum', id=id, year=year, education_type=education_type))
            return redirect(url_for('dean.direction_curriculum', id=id))
        
        # Import funksiyasiga yil va ta'lim shaklini ham uzatish
        result = import_curriculum_from_excel(file, direction.id, enrollment_year=year, education_type=education_type)
        
        if result['success']:
            if result['imported'] > 0 or result['updated'] > 0:
                message = t('curriculum_import_success', imported=result['imported'], updated=result['updated'])
                if result.get('subjects_created', 0) > 0:
                    message += " " + t('curriculum_import_subjects_created', subjects_created=result['subjects_created'])
                if result['errors']:
                    message += " " + t('curriculum_import_errors', errors_count=len(result['errors']))
                flash(message, 'success' if not result['errors'] else 'warning')
            else:
                flash(t('no_changes_made'), 'info')
            
            if result['errors']:
                for error in result['errors'][:10]:  # Faqat birinchi 10 ta xatolikni ko'rsatish
                    flash(t('import_error', error=error), 'error')
        else:
            flash(t('import_error_joined', errors=', '.join(result['errors'])), 'error')
        
        if year and education_type:
            return redirect(url_for('dean.direction_curriculum', id=id, year=year, education_type=education_type))
        return redirect(url_for('dean.direction_curriculum', id=id))
    
    return render_template('dean/import_curriculum.html', 
                         direction=direction,
                         enrollment_year=year,
                         education_type=education_type)


@bp.route('/directions/<int:id>/curriculum/import/sample')
@login_required
@dean_required
def download_curriculum_sample(id):
    """O'quv reja import uchun namuna fayl yuklab olish (tanlangan til bo'yicha)"""
    from app.utils.excel_import import generate_curriculum_sample_file
    direction = Direction.query.get_or_404(id)
    if direction.faculty_id != current_user.faculty_id:
        flash(t('no_access_permission'), 'error')
        return redirect(url_for('dean.courses'))
    lang = session.get('language', 'uz')
    excel_file = generate_curriculum_sample_file(lang=lang)
    filename = t('sample_filename_curriculum') + f"_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return send_file(
        excel_file,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=filename
    )
@bp.route('/directions/<int:id>/subjects', methods=['GET', 'POST'])
@bp.route('/directions/<int:id>/<int:year>/<string:education_type>/subjects', methods=['GET', 'POST'])
@login_required
@dean_required
def direction_subjects(id, year=None, education_type=None):
    """Yo'nalish fanlari sahifasi - jadval ko'rinishida"""
    direction = Direction.query.get_or_404(id)

    # Agar yil yoki ta'lim shakli berilmagan bo'lsa, birinchi guruhdan yoki oxirgisidan context olishga harakat qilamiz
    if not year or not education_type:
        first_group = Group.query.filter_by(direction_id=id).order_by(Group.enrollment_year.desc()).first()
        if first_group and first_group.enrollment_year and first_group.education_type:
            return redirect(url_for('dean.direction_subjects', id=id, year=first_group.enrollment_year, education_type=first_group.education_type))
    
    # Fakultet tekshiruvi
    if direction.faculty_id != current_user.faculty_id:
        flash(t('no_access_permission'), 'error')
        return redirect(url_for('dean.courses'))
    
    # Berilgan qabul yili va ta'lim shakli bo'yicha guruhlar (optional context support)
    group_query = Group.query.filter_by(direction_id=direction.id)
    if year:
        group_query = group_query.filter_by(enrollment_year=year)
    if education_type:
        group_query = group_query.filter_by(education_type=education_type)
        
    all_groups = group_query.all()
    
    # Talabasi bor yoki o'qituvchi biriktirilgan guruhlarni olamiz
    groups = []
    for g in all_groups:
        has_students = g.students.count() > 0
        has_teachers = TeacherSubject.query.filter_by(group_id=g.id).first() is not None
        if has_students or has_teachers:
            groups.append(g)
    
    # Agar talabasi bor/biriktirilgan guruhlar bo'lmasa, lekin guruhlar mavjud bo'lsa, hammasini korsatamiz
    if not groups and all_groups:
        groups = all_groups

    # Guruhlarni semestrlar bo'yicha guruhlash
    groups_by_semester = {}
    for g in groups:
        if g.semester not in groups_by_semester:
            groups_by_semester[g.semester] = []
        groups_by_semester[g.semester].append(g)

    # POST so'rov - o'qituvchilarni saqlash
    if request.method == 'POST':
        semester = request.form.get('semester', type=int)
        if not semester:
            flash(t('semester_not_selected'), 'error')
            if year and education_type:
                return redirect(url_for('dean.direction_subjects', id=id, year=year, education_type=education_type))
            return redirect(url_for('dean.direction_subjects', id=id))
        
        # Bu semestr uchun faol guruhlar
        active_semester_groups = groups_by_semester.get(semester, [])
        if not active_semester_groups:
            flash(t('no_active_groups_for_semester', semester=semester), 'error')
            if year and education_type:
                return redirect(url_for('dean.direction_subjects', id=id, year=year, education_type=education_type))
            return redirect(url_for('dean.direction_subjects', id=id))
        
        # Semestrdagi barcha fanlar uchun o'qituvchilarni yangilash (context aware)
        curriculum_query = direction.curriculum_items.filter_by(semester=semester)
        if year:
            curriculum_query = curriculum_query.filter_by(enrollment_year=year)
        if education_type:
            curriculum_query = curriculum_query.filter_by(education_type=education_type)
            
        for item in curriculum_query.all():
            # Har bir guruh uchun alohida saqlash
            for group in active_semester_groups:
                # Maruza o'qituvchisi
                maruza_teacher_id = request.form.get(f'teacher_maruza_{item.id}_{group.id}', type=int)
                
                teacher_subject = TeacherSubject.query.filter_by(
                    subject_id=item.subject_id,
                    group_id=group.id,
                    lesson_type='maruza'
                ).first()
                
                if maruza_teacher_id:
                    if teacher_subject:
                        teacher_subject.teacher_id = maruza_teacher_id
                    else:
                        teacher_subject = TeacherSubject(
                            teacher_id=maruza_teacher_id,
                            subject_id=item.subject_id,
                            group_id=group.id,
                            lesson_type='maruza'
                        )
                        db.session.add(teacher_subject)
                else:
                    if teacher_subject:
                        db.session.delete(teacher_subject)
                
                # Practical teachers
                if (item.hours_amaliyot or 0) > 0 or (item.hours_laboratoriya or 0) > 0 or (item.hours_kurs_ishi or 0) > 0:
                    practical_teacher_id = request.form.get(f'teacher_practical_{item.id}_{group.id}', type=int)
                    teacher_subject = TeacherSubject.query.filter_by(
                        subject_id=item.subject_id,
                        group_id=group.id,
                        lesson_type='amaliyot'
                    ).first()
                    
                    if practical_teacher_id:
                        if teacher_subject:
                            teacher_subject.teacher_id = practical_teacher_id
                        else:
                            teacher_subject = TeacherSubject(
                                teacher_id=practical_teacher_id,
                                subject_id=item.subject_id,
                                group_id=group.id,
                                lesson_type='amaliyot'
                            )
                            db.session.add(teacher_subject)
                    else:
                        if teacher_subject:
                            db.session.delete(teacher_subject)
                
                # Seminar teachers
                if (item.hours_seminar or 0) > 0:
                    seminar_teacher_id = request.form.get(f'teacher_seminar_{item.id}_{group.id}', type=int)
                    teacher_subject = TeacherSubject.query.filter_by(
                        subject_id=item.subject_id,
                        group_id=group.id,
                        lesson_type='seminar'
                    ).first()
                    
                    if seminar_teacher_id:
                        if teacher_subject:
                            teacher_subject.teacher_id = seminar_teacher_id
                        else:
                            teacher_subject = TeacherSubject(
                                teacher_id=seminar_teacher_id,
                                subject_id=item.subject_id,
                                group_id=group.id,
                                lesson_type='seminar'
                            )
                            db.session.add(teacher_subject)
                    else:
                        if teacher_subject:
                            db.session.delete(teacher_subject)
        
        db.session.commit()
        flash(t('semester_teachers_saved', semester=semester), 'success')
        if year and education_type:
            return redirect(url_for('dean.direction_subjects', id=id, year=year, education_type=education_type))
        return redirect(url_for('dean.direction_subjects', id=id))
    
    # O'quv rejadagi fanlar (semestr bo'yicha guruhlangan)
    subjects_by_semester = {}
    
    # Curriculum items with context filtering
    curriculum_query = direction.curriculum_items.join(Subject)
    if year:
        curriculum_query = curriculum_query.filter(DirectionCurriculum.enrollment_year == year)
    if education_type:
        curriculum_query = curriculum_query.filter(DirectionCurriculum.education_type == education_type)
        
    for item in curriculum_query.order_by(DirectionCurriculum.semester, Subject.name).all():
        semester = item.semester
        if semester not in subjects_by_semester:
            subjects_by_semester[semester] = []
        
        # Lessons restructuring - now we don't need teacher info here since template uses get_teacher_for_type
        lessons = []
        if (item.hours_maruza or 0) > 0:
            lessons.append({'type': 'Maruza', 'hours': item.hours_maruza})
            
        practical_types = []
        practical_hours = 0
        if (item.hours_amaliyot or 0) > 0:
            practical_types.append('Amaliyot')
            practical_hours += item.hours_amaliyot
        if (item.hours_laboratoriya or 0) > 0:
            practical_types.append('Laboratoriya')
            practical_hours += item.hours_laboratoriya
        if (item.hours_kurs_ishi or 0) > 0:
            practical_types.append('Kurs ishi')
            
        if practical_types:
            lessons.append({'type': ', '.join(practical_types), 'hours': practical_hours})
            
        if (item.hours_seminar or 0) > 0:
            lessons.append({'type': 'Seminar', 'hours': item.hours_seminar})
            
        subjects_by_semester[semester].append({
            'subject': item.subject,
            'curriculum_item': item,
            'lessons': lessons
        })
    
    # O'qituvchilar ro'yxati (faqat o'qituvchi roliga ega bo'lganlar)
    from app.models import UserRole
    from sqlalchemy import or_
    teacher_user_ids = [uid[0] for uid in db.session.query(UserRole.user_id).filter_by(role='teacher').distinct().all()]
    
    teachers = User.query.filter(
        or_(
            User.role == 'teacher',
            User.id.in_(teacher_user_ids) if teacher_user_ids else False
        )
    ).order_by(User.full_name).all()
    
    return render_template('dean/direction_subjects.html',
                         direction=direction,
                         subjects_by_semester=subjects_by_semester,
                         groups_by_semester=groups_by_semester,
                         teachers=teachers,
                         enrollment_year=year,
                         education_type=education_type)





@bp.route('/directions/<int:id>/curriculum/add', methods=['POST'])
@bp.route('/directions/<int:id>/<int:year>/<string:education_type>/curriculum/add', methods=['POST'])
@login_required
@dean_required
def add_subject_to_curriculum(id, year=None, education_type=None):
    """O'quv rejaga fan qo'shish (Context aware)"""
    direction = Direction.query.get_or_404(id)
    
    # Fakultet tekshiruvi
    if direction.faculty_id != current_user.faculty_id:
        flash(t('no_permission_for_operation'), 'error')
        return redirect(url_for('dean.courses'))
    
    subject_ids = request.form.getlist('subject_ids')
    semester = request.form.get('semester', type=int)
    
    if not subject_ids or not semester:
        flash(t('subject_and_semester_required'), 'error')
        if year and education_type:
            return redirect(url_for('dean.direction_curriculum', id=id, year=year, education_type=education_type))
        return redirect(url_for('dean.direction_curriculum', id=id))
    
    added = 0
    for subject_id in subject_ids:
        subject_id = int(subject_id)
        subject = Subject.query.get(subject_id)
        if not subject:
            continue
        
        # Takrorlanmasligini tekshirish (independent curriculum support)
        existing = DirectionCurriculum.query.filter_by(
            direction_id=direction.id,
            subject_id=subject_id,
            semester=semester,
            enrollment_year=year,
            education_type=education_type
        ).first()
        
        if not existing:
            curriculum_item = DirectionCurriculum(
                direction_id=direction.id,
                subject_id=subject_id,
                semester=semester,
                enrollment_year=year,
                education_type=education_type
            )
            db.session.add(curriculum_item)
            added += 1
    
    db.session.commit()
    flash(t('subjects_added_to_curriculum', added=added), 'success')
    if year and education_type:
        return redirect(url_for('dean.direction_curriculum', id=id, year=year, education_type=education_type))
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
        flash(t('no_permission_for_operation'), 'error')
        return redirect(url_for('dean.courses'))
    
    item.hours_maruza = request.form.get('hours_maruza', type=int) or 0
    item.hours_amaliyot = request.form.get('hours_amaliyot', type=int) or 0
    item.hours_laboratoriya = request.form.get('hours_laboratoriya', type=int) or 0
    item.hours_seminar = request.form.get('hours_seminar', type=int) or 0
    item.hours_kurs_ishi = request.form.get('hours_kurs_ishi', type=int) or 0
    item.hours_mustaqil = request.form.get('hours_mustaqil', type=int) or 0
    
    DirectionCurriculum.remove_teacher_assignments_for_zeroed_hours(item)
    db.session.commit()
    flash(t('curriculum_updated', semester=1), 'success')  # Note: semester not available, using default
    return redirect(url_for('dean.direction_curriculum', id=id))


@bp.route('/directions/<int:id>/curriculum/semester/<int:semester>/update', methods=['POST'])
@bp.route('/directions/<int:id>/<int:year>/<string:education_type>/curriculum/semester/<int:semester>/update', methods=['POST'])
@login_required
@dean_required
def update_semester_curriculum(id, semester, year=None, education_type=None):
    """Semestr bo'yicha barcha fanlarni yangilash"""
    direction = Direction.query.get_or_404(id)
    
    # Fakultet tekshiruvi
    if direction.faculty_id != current_user.faculty_id:
        flash(t('no_permission_for_operation'), 'error')
        return redirect(url_for('dean.courses'))
    
    # Bu semestr uchun barcha fanlarni olish (context-aware)
    items = DirectionCurriculum.query.filter_by(
        direction_id=direction.id,
        semester=semester,
        enrollment_year=year,
        education_type=education_type
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
        
        # Soatlari 0 qilingan dars turlariga biriktirilgan o'qituvchilarni bekor qilish
        DirectionCurriculum.remove_teacher_assignments_for_zeroed_hours(item)
        
        updated += 1
    
    db.session.commit()
    flash(t('curriculum_updated', semester=semester), 'success')
    if year and education_type:
        return redirect(url_for('dean.direction_curriculum', id=id, year=year, education_type=education_type))
    return redirect(url_for('dean.direction_curriculum', id=id))


@bp.route('/directions/<int:id>/curriculum/<int:item_id>/replace', methods=['POST'])
@bp.route('/directions/<int:id>/<int:year>/<string:education_type>/curriculum/<int:item_id>/replace', methods=['POST'])
@login_required
@dean_required
def replace_curriculum_subject(id, item_id, year=None, education_type=None):
    """O'quv rejadagi fanni boshqa fan bilan almashtirish"""
    direction = Direction.query.get_or_404(id)
    item = DirectionCurriculum.query.get_or_404(item_id)
    
    # Fakultet tekshiruvi
    if direction.faculty_id != current_user.faculty_id or item.direction_id != direction.id:
        flash(t('no_permission_for_operation'), 'error')
        return redirect(url_for('dean.courses'))
    
    new_subject_id = request.form.get('subject_id', type=int)
    if not new_subject_id:
        flash(t('subject_and_semester_required'), 'error')
        return _redirect_curriculum(id, year, education_type, item)
    
    new_subject = Subject.query.get(new_subject_id)
    if not new_subject:
        flash(t('subject_not_found'), 'error')
        return _redirect_curriculum(id, year, education_type, item)
    
    # Takrorlanmasligini tekshirish (context-aware: URL yoki item bo‘yicha)
    ctx_year = year if (year is not None) else item.enrollment_year
    ctx_edu = education_type if (education_type is not None) else item.education_type
    existing = DirectionCurriculum.query.filter(
        DirectionCurriculum.direction_id == direction.id,
        DirectionCurriculum.subject_id == new_subject_id,
        DirectionCurriculum.semester == item.semester,
        DirectionCurriculum.id != item_id
    )
    if ctx_year is not None:
        existing = existing.filter(DirectionCurriculum.enrollment_year == ctx_year)
    else:
        existing = existing.filter(DirectionCurriculum.enrollment_year.is_(None))
    if ctx_edu is not None:
        existing = existing.filter(DirectionCurriculum.education_type == ctx_edu)
    else:
        existing = existing.filter(DirectionCurriculum.education_type.is_(None))
    existing = existing.first()
    
    if existing:
        flash(t('subject_already_in_semester', subject_name=new_subject.name), 'error')
        return _redirect_curriculum(id, year, education_type, item)
    
    item.subject_id = new_subject_id
    db.session.commit()
    flash(t('subject_replaced', new_subject_name=new_subject.name), 'success')
    return _redirect_curriculum(id, year, education_type, item)


def _redirect_curriculum(id, year, education_type, item):
    if year is not None and education_type is not None:
        return redirect(url_for('dean.direction_curriculum', id=id, year=year, education_type=education_type))
    if item.enrollment_year is not None and item.education_type is not None:
        return redirect(url_for('dean.direction_curriculum', id=id, year=item.enrollment_year, education_type=item.education_type))
    return redirect(url_for('dean.direction_curriculum', id=id))


@bp.route('/directions/<int:id>/curriculum/<int:item_id>/delete', methods=['POST'])
@bp.route('/directions/<int:id>/<int:year>/<string:education_type>/curriculum/<int:item_id>/delete', methods=['POST'])
@login_required
@dean_required
def delete_curriculum_item(id, item_id, year=None, education_type=None):
    """O'quv rejadan fanni o'chirish"""
    direction = Direction.query.get_or_404(id)
    item = DirectionCurriculum.query.get_or_404(item_id)
    
    # Fakultet tekshiruvi
    if direction.faculty_id != current_user.faculty_id or item.direction_id != direction.id:
        flash(t('no_permission_for_operation'), 'error')
        return redirect(url_for('dean.courses'))
    
    db.session.delete(item)
    db.session.commit()
    flash(t('subject_removed_from_curriculum'), 'success')
    if year and education_type:
        return redirect(url_for('dean.direction_curriculum', id=id, year=year, education_type=education_type))
    return redirect(url_for('dean.direction_curriculum', id=id))



# ==================== DARS JADVALI ====================
@bp.route('/schedule')
@login_required
@dean_required
def schedule():
    faculty = Faculty.query.get(current_user.faculty_id)
    if not faculty:
        flash(t('faculty_not_assigned'), 'error')
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
    # Hafta Dushanbadan boshlanadi – calendar.Calendar orqali to'g'ri joylashtirish
    cal = calendar.Calendar(firstweekday=0)
    calendar_weeks = cal.monthdatescalendar(year, month)

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
    
    # Kalendarda ko'rinadigan barcha kunlarni qamrab olish (oldingi va keyingi oy kunlari ham)
    first_calendar_date = calendar_weeks[0][0]
    last_calendar_date = calendar_weeks[-1][-1]
    start_code = int(first_calendar_date.strftime("%Y%m%d"))
    end_code = int(last_calendar_date.strftime("%Y%m%d"))
    
    # Filter parametrlari
    course_year = request.args.get('course_year', type=int)
    semester = request.args.get('semester', type=int)
    direction_id = request.args.get('direction_id', type=int)
    group_id = request.args.get('group_id', type=int)
    teacher_id = request.args.get('teacher_id', type=int)
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    # Sana diapazoni bo'yicha filter (Admin kabi logic)
    if start_date or end_date:
        try:
            if start_date and end_date:
                start_dt = datetime.strptime(start_date, "%Y-%m-%d")
                end_dt = datetime.strptime(end_date, "%Y-%m-%d")
                start_code = int(start_dt.strftime("%Y%m%d"))
                end_code = int(end_dt.strftime("%Y%m%d"))
            elif start_date:
                start_dt = datetime.strptime(start_date, "%Y-%m-%d")
                start_code = int(start_dt.strftime("%Y%m%d"))
                end_code = 99991231
            elif end_date:
                end_dt = datetime.strptime(end_date, "%Y-%m-%d")
                start_code = 19000101
                end_code = int(end_dt.strftime("%Y%m%d"))
        except ValueError:
            pass # Standard oy filteriga qaytish

    # Query qurish
    query = Schedule.query.join(Group).filter(
        Group.faculty_id == faculty.id,
        Schedule.day_of_week.between(start_code, end_code)
    )
    
    if course_year:
        query = query.filter(Group.course_year == course_year)
    if direction_id:
        query = query.filter(Group.direction_id == direction_id)
    if group_id:
        query = query.filter(Schedule.group_id == group_id)
    if teacher_id:
        query = query.filter(Schedule.teacher_id == teacher_id)
    if semester:
        query = query.filter(Group.semester == semester)
        
    schedules = query.order_by(Schedule.day_of_week, Schedule.start_time).all()
    
    # Sana bo'yicha guruhlash (YYYY-MM-DD formatida)
    schedule_by_date = {}
    for s in schedules:
        try:
            code_str = str(s.day_of_week)
            date_key = f"{code_str[:4]}-{code_str[4:6]}-{code_str[6:8]}"
            if date_key not in schedule_by_date:
                schedule_by_date[date_key] = []
            schedule_by_date[date_key].append(s)
        except (TypeError, ValueError, IndexError):
            continue
    
    for date_key in schedule_by_date:
        schedule_by_date[date_key].sort(key=lambda x: x.start_time or '')
    
    # Eski format uchun moslik (faqat joriy oy kunlari)
    schedule_by_day = {i: [] for i in range(1, days_in_month + 1)}
    for i in range(1, days_in_month + 1):
        date_key = f"{year}-{month:02d}-{i:02d}"
        schedule_by_day[i] = schedule_by_date.get(date_key, [])
        
    # Filter groups that have students
    active_groups = [g for g in Group.query.filter_by(faculty_id=faculty.id).all() if g.get_students_count() > 0]
    all_courses = sorted(list(set(g.course_year for g in active_groups if g.course_year)))
    all_semesters = sorted(list(set(g.semester for g in active_groups if g.semester)))
    all_directions = sorted(list(set(g.direction for g in active_groups if g.direction)), key=lambda x: x.name)
    all_groups = sorted(active_groups, key=lambda x: x.name)
    
    # O'qituvchilar (shu fakultetga dars beradigan)
    # Oddiylashtirish uchun barcha o'qituvchilarni olib kelamiz yoki fakultetga bog'langanlarini
    all_teachers = User.query.filter_by(role='teacher').order_by(User.full_name).all()

    return render_template('dean/schedule.html', 
                         faculty=faculty,
                         schedule_by_day=schedule_by_day,
                         schedule_by_date=schedule_by_date,
                         days_in_month=days_in_month,
                         calendar_weeks=calendar_weeks,
                         current_date=current_date,
                         year=year,
                         month=month,
                         today_year=today_year,
                         today_month=today_month,
                         today_day=today_day,
                         prev_year=prev_year,
                         prev_month=prev_month,
                         next_year=next_year,
                         next_month=next_month,
                         # Filters context
                         all_courses=all_courses,
                         all_semesters=all_semesters,
                         all_directions=all_directions,
                         all_groups=all_groups,
                         all_teachers=all_teachers,
                         current_course_year=course_year,
                         current_semester=semester,
                         current_direction_id=direction_id,
                         current_group_id=group_id,
                         current_teacher_id=teacher_id
                         )

@bp.route('/schedule/import', methods=['GET', 'POST'])
@login_required
@dean_required
def import_schedule():
    """Dars jadvalini Excel fayldan import qilish"""
    if request.method == 'POST':
        if 'file' not in request.files:
            flash(t('file_not_selected'), 'error')
            return redirect(url_for('dean.schedule'))
        
        file = request.files['file']
        if file.filename == '':
            flash(t('file_not_selected'), 'error')
            return redirect(url_for('dean.schedule'))
        
        if not file.filename.endswith(('.xlsx', '.xls')):
            flash(t('only_xlsx_or_xls_allowed'), 'error')
            return redirect(url_for('dean.schedule'))
            
        try:
            # Import logic
            result = import_schedule_from_excel(file)
            
            if result['success']:
                msg = t('schedules_imported', count=result['imported'])
                if result['errors']:
                    msg += " " + t('curriculum_import_errors', errors_count=len(result['errors']))
                flash(msg, 'success' if not result['errors'] else 'warning')
                
                for err in result['errors'][:5]:
                    flash(t('import_error', error=err), 'error')
            else:
                flash(t('import_error_with_details', errors='; '.join(result['errors'])), 'error')
                
        except Exception as e:
            flash(t('error_occurred', error=str(e)), 'error')
            
        return redirect(url_for('dean.schedule'))
        
    return render_template('dean/import_schedule.html')

@bp.route('/schedule/sample')
@login_required
@dean_required
def schedule_sample():
    """Dars jadvali importi uchun namuna yuklab olish (tanlangan til bo'yicha)"""
    try:
        lang = session.get('language', 'uz')
        excel_file = generate_schedule_sample_file(lang=lang)
        filename = t('sample_filename_schedule') + ".xlsx"
        return send_file(
            excel_file,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        flash(t('template_file_creation_error', error=str(e)), 'error')
        return redirect(url_for('dean.schedule'))

@bp.route('/schedule/export')
@login_required
@dean_required
def export_schedule():
    """Dars jadvalini Excelga eksport qilish"""
    faculty = Faculty.query.get(current_user.faculty_id)
    if not faculty:
        flash(t('faculty_not_found'), 'error')
        return redirect(url_for('dean.schedule'))

    # Parametrlarni olish
    course_year = request.args.get('course_year', type=int)
    semester = request.args.get('semester', type=int)
    direction_id = request.args.get('direction_id', type=int)
    group_id = request.args.get('group_id', type=int)
    teacher_id = request.args.get('teacher_id', type=int)
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    # Sana filteri (Admin kabi logic)
    if start_date or end_date:
        try:
            if start_date and end_date:
                start_dt = datetime.strptime(start_date, "%Y-%m-%d")
                end_dt = datetime.strptime(end_date, "%Y-%m-%d")
                start_code = int(start_dt.strftime("%Y%m%d"))
                end_code = int(end_dt.strftime("%Y%m%d"))
            elif start_date:
                start_dt = datetime.strptime(start_date, "%Y-%m-%d")
                start_code = int(start_dt.strftime("%Y%m%d"))
                end_code = 99991231
            elif end_date:
                end_dt = datetime.strptime(end_date, "%Y-%m-%d")
                start_code = 19000101
                end_code = int(end_dt.strftime("%Y%m%d"))
        except ValueError:
            flash(t('date_invalid_format'), 'error')
            return redirect(url_for('dean.schedule'))
    else:
        # Standart holatda barcha
        start_code = 19000101
        end_code = 99991231

    query = Schedule.query.join(Group).filter(
        Group.faculty_id == faculty.id,
        Schedule.day_of_week.between(start_code, end_code)
    )

    if course_year:
        query = query.filter(Group.course_year == course_year)
    if direction_id:
        query = query.filter(Group.direction_id == direction_id)
    if group_id:
        query = query.filter(Schedule.group_id == group_id)
    if teacher_id:
        query = query.filter(Schedule.teacher_id == teacher_id)
    if semester:
        query = query.filter(Group.semester == semester)

    schedules = query.order_by(Schedule.day_of_week, Schedule.start_time).all()

    # Generate descriptive filename
    filename_parts = ["dars_jadvali"]
    if group_id and schedules:
        filename_parts.append(schedules[0].group.name if schedules[0].group else "")
    else:
        filename_parts.append(faculty.name.replace(' ', '_'))
    
    if teacher_id:
        teacher = User.query.get(teacher_id)
        if teacher:
            filename_parts.append(teacher.full_name.replace(' ', '_'))

    if start_date and end_date:
        filename_parts.append(f"{start_date}_{end_date}")
    
    filename = "_".join(filter(None, filename_parts)) + ".xlsx"

    # Create Excel file
    group_name = schedules[0].group.name if schedules and schedules[0].group else None
    
    excel_file = create_schedule_excel(schedules, group_name, faculty.name)
    
    return Response(
        excel_file,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )


@bp.route('/api/schedule/filters')
@login_required
@dean_required
def api_schedule_filters():
    """Dekan uchun dars jadvali filtrlarini dinamik qaytarish (faqat o'z fakulteti)"""
    from app.models import Direction, Subject, TeacherSubject
    
    group_id = request.args.get('group_id', type=int)
    subject_id = request.args.get('subject_id', type=int)
    teacher_id = request.args.get('teacher_id', type=int)
    
    if group_id and not subject_id:
        from app.models import Group, DirectionCurriculum, TeacherSubject
        group = Group.query.get(group_id)
        if not group:
            return jsonify([])
            
        current_semester = group.semester if group.semester else 1
        
        # Guruhga biriktirilgan fanlar, lekin faqat joriy semestrdagilar
        assignments = TeacherSubject.query.filter_by(group_id=group_id).all()
        subjects_data = {}
        for a in assignments:
            # Tekshirish: bu fan bu guruhda shu semestrda bormi?
            curr_item = DirectionCurriculum.query.filter_by(
                direction_id=group.direction_id,
                subject_id=a.subject_id,
                semester=current_semester
            ).first()
            
            if curr_item and a.subject_id not in subjects_data:
                subjects_data[a.subject_id] = {
                    'id': a.subject.id,
                    'name': a.subject.name,
                    'code': a.subject.code
                }
        return jsonify(sorted(list(subjects_data.values()), key=lambda x: x['name']))
    
    if group_id and subject_id and not teacher_id:
        # Guruh va fan uchun biriktirilgan o'qituvchilar
        assignments = TeacherSubject.query.filter_by(group_id=group_id, subject_id=subject_id).all()
        teachers_data = {}
        for a in assignments:
            if a.teacher_id not in teachers_data:
                teachers_data[a.teacher_id] = {
                    'id': a.teacher.id,
                    'full_name': a.teacher.full_name
                }
        return jsonify(sorted(list(teachers_data.values()), key=lambda x: x['full_name']))
        
    return jsonify([])

@bp.route('/schedule/create', methods=['GET', 'POST'])
@login_required
@dean_required
def create_schedule():
    faculty = Faculty.query.get(current_user.faculty_id)
    if not faculty:
        flash(t('faculty_not_assigned'), 'error')
        return redirect(url_for('main.dashboard'))
    
    faculty_id = faculty.id
    
    # Robust mapping logic (Group-driven)
    faculty_course_semesters = {}
    faculty_course_semester_education_directions = {}
    direction_groups = {}
    active_courses = set()
    
    all_groups = Group.query.filter_by(faculty_id=faculty_id).all()
    for g in all_groups:
        if g.get_students_count() == 0: continue # Skip empty groups
        
        c = g.course_year
        if not c: continue
        active_courses.add(c)
        
        if g.direction:
            d = g.direction
            s = g.semester
            
            if c not in faculty_course_semesters:
                faculty_course_semesters[c] = set()
            faculty_course_semesters[c].add(s)
            
            if s not in faculty_course_semester_education_directions:
                faculty_course_semester_education_directions[s] = {}
            if c not in faculty_course_semester_education_directions[s]:
                faculty_course_semester_education_directions[s][c] = {}
            
            etype = g.education_type or 'kunduzgi'
            if etype not in faculty_course_semester_education_directions[s][c]:
                faculty_course_semester_education_directions[s][c][etype] = []
            
            if not any(item['id'] == d.id for item in faculty_course_semester_education_directions[s][c][etype]):
                faculty_course_semester_education_directions[s][c][etype].append({
                    'id': d.id,
                    'name': d.name,
                    'code': d.code,
                    'enrollment_year': g.enrollment_year,
                    'education_type': etype
                })
            
            if d.id not in direction_groups:
                direction_groups[d.id] = []
            if not any(item['id'] == g.id for item in direction_groups[d.id]):
                direction_groups[d.id].append({
                    'id': g.id,
                    'name': g.name
                })

    # Convert sets to sorted lists
    faculty_courses = sorted(list(active_courses))
    for c in faculty_course_semesters:
        faculty_course_semesters[c] = sorted(list(faculty_course_semesters[c]))

    teachers = User.query.filter_by(role='teacher').order_by(User.full_name).all()
    
    # GET parametrlar orqali kelgan default sana va guruh
    default_date = request.args.get('date')
    default_group_id = request.args.get('group', type=int)
    
    if request.method == 'POST':
        # Sana (kalendardan) -> YYYYMMDD formatida int
        faculty = current_user.managed_faculty
        date_str = request.form.get('schedule_date')
        date_code = None
        parsed_date = None
        if date_str:
            try:
                parsed_date = datetime.strptime(date_str, "%Y-%m-%d")
                date_code = int(parsed_date.strftime("%Y%m%d"))
            except ValueError:
                flash(t('date_invalid_format'), 'error')
                return redirect(url_for('dean.create_schedule'))
        
        if not date_code:
            flash(t('date_required_select'), 'error')
            return redirect(url_for('dean.create_schedule'))
        
        # Takrorlanishni tekshirish
        start_time = request.form.get('start_time')
        group_id = request.form.get('group_id', type=int)
        
        existing = Schedule.query.filter_by(
            group_id=group_id,
            day_of_week=date_code,
            start_time=start_time
        ).first()
        
        from app.models import TeacherSubject
        subject_id = request.form.get('subject_id', type=int)
        teacher_id = request.form.get('teacher_id', type=int)
        
        # O'qituvchiga biriktirilgan barcha dars turlarini topish
        assignments = TeacherSubject.query.filter_by(
            group_id=group_id,
            subject_id=subject_id,
            teacher_id=teacher_id
        ).all()
        
        # Dars turlarini yig'ish
        types_map = {
            'maruza': 'Ma\'ruza',
            'ma\'ruza': 'Ma\'ruza',
            'lecture': 'Ma\'ruza',
            'amaliyot': 'Amaliyot',
            'practice': 'Amaliyot',
            'laboratoriya': 'Laboratoriya',
            'lab': 'Laboratoriya',
            'seminar': 'Seminar',
            'kurs ishi': 'Kurs ishi',
            'kurs_ishi': 'Kurs ishi',
            'mustaqil ta\'lim': 'Mustaqil ta\'lim',
            'mustaqil talim': 'Mustaqil ta\'lim',
        }
        found_types = sorted(list(set([types_map.get(a.lesson_type.lower() if a.lesson_type else '', a.lesson_type.capitalize() if a.lesson_type else '') for a in assignments if a.lesson_type])))
        lesson_type_display = "/".join(found_types) if found_types else 'Ma\'ruza'

        link = request.form.get('link') or ''
        # Zoom meeting avtomatik yaratish (link bo'sh bo'lsa va Zoom sozlangan bo'lsa)
        if not link.strip():
            try:
                from flask import current_app
                from app.services.zoom_service import create_schedule_meeting
                subject = Subject.query.get(subject_id)
                group = Group.query.get(group_id)
                zoom_config = {
                    'ZOOM_ACCOUNT_ID': current_app.config.get('ZOOM_ACCOUNT_ID'),
                    'ZOOM_CLIENT_ID': current_app.config.get('ZOOM_CLIENT_ID'),
                    'ZOOM_CLIENT_SECRET': current_app.config.get('ZOOM_CLIENT_SECRET'),
                    'ZOOM_DURATION_MINUTES': current_app.config.get('ZOOM_DURATION_MINUTES'),
                    'ZOOM_TIMEZONE': current_app.config.get('ZOOM_TIMEZONE'),
                }
                zoom_link = create_schedule_meeting(
                    subject_name=subject.name if subject else '',
                    group_name=group.name if group else '',
                    lesson_type=lesson_type_display,
                    date_code=date_code,
                    start_time=start_time or '09:00',
                    config=zoom_config,
                )
                if zoom_link:
                    link = zoom_link
            except Exception:
                pass

        schedule = Schedule(
            subject_id=subject_id,
            group_id=group_id,
            teacher_id=teacher_id,
            day_of_week=date_code,
            start_time=start_time,
            end_time=request.form.get('end_time') or None,
            link=link or None,
            lesson_type=lesson_type_display[:20]
        )
        db.session.add(schedule)
        db.session.commit()
        
        flash(t('schedule_added'), 'success')
        return redirect(url_for(
            'dean.schedule',
            year=parsed_date.year,
            month=parsed_date.month,
            group=group_id
        ))
    
    return render_template('dean/create_schedule.html',
                         faculty=faculty,
                         faculty_courses=faculty_courses,
                         faculty_course_semesters=faculty_course_semesters,
                         faculty_course_semester_education_directions=faculty_course_semester_education_directions,
                         direction_groups=direction_groups,
                         teachers=teachers,
                         default_date=default_date,
                         default_group_id=default_group_id)


@bp.route('/schedule/<int:id>/delete', methods=['POST'])
@login_required
@dean_required
def delete_schedule(id):
    schedule = Schedule.query.get_or_404(id)
    
    # Faqat o'z fakultetidagi jadvallarni o'chirishi mumkin
    if schedule.group.faculty_id != current_user.faculty_id:
        flash(t('no_permission_for_operation'), 'error')
        return redirect(url_for('dean.schedule'))
    
    # O'chirishdan oldin yil va oyni saqlab qo'yamiz
    # day_of_week maydonida sana YYYYMMDD formatida saqlanadi
    if schedule.day_of_week and schedule.day_of_week > 7:
        date_str = str(schedule.day_of_week)
        schedule_year = int(date_str[:4])
        schedule_month = int(date_str[4:6])
    else:
        from datetime import datetime
        schedule_year = datetime.now().year
        schedule_month = datetime.now().month
    
    db.session.delete(schedule)
    db.session.commit()
    flash(t('schedule_deleted'), 'success')
    
    return redirect(url_for('dean.schedule', year=schedule_year, month=schedule_month))


@bp.route('/schedule/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@dean_required
def edit_schedule(id):
    schedule = Schedule.query.get_or_404(id)
    
    # Faqat o'z fakultetidagi jadvallarni tahrirlashi mumkin
    if schedule.group.faculty_id != current_user.faculty_id:
        flash(t('no_permission_for_operation'), 'error')
        return redirect(url_for('dean.schedule'))
    
    faculty = current_user.managed_faculty
    faculty_id = faculty.id
    
    # Robust mapping logic (Group-driven)
    faculty_course_semesters = {}
    faculty_course_semester_education_directions = {}
    direction_groups = {}
    active_courses = set()
    
    all_groups = Group.query.filter_by(faculty_id=faculty_id).all()
    for g in all_groups:
        if g.get_students_count() == 0: continue # Skip empty groups
        
        c = g.course_year
        if not c: continue
        active_courses.add(c)
        
        if g.direction:
            d = g.direction
            s = g.semester
            
            if c not in faculty_course_semesters:
                faculty_course_semesters[c] = set()
            faculty_course_semesters[c].add(s)
            
            if s not in faculty_course_semester_education_directions:
                faculty_course_semester_education_directions[s] = {}
            if c not in faculty_course_semester_education_directions[s]:
                faculty_course_semester_education_directions[s][c] = {}
            
            etype = g.education_type or 'kunduzgi'
            if etype not in faculty_course_semester_education_directions[s][c]:
                faculty_course_semester_education_directions[s][c][etype] = []
            
            if not any(item['id'] == d.id for item in faculty_course_semester_education_directions[s][c][etype]):
                faculty_course_semester_education_directions[s][c][etype].append({
                    'id': d.id,
                    'name': d.name,
                    'code': d.code,
                    'enrollment_year': g.enrollment_year,
                    'education_type': etype
                })
            
            if d.id not in direction_groups:
                direction_groups[d.id] = []
            if not any(item['id'] == g.id for item in direction_groups[d.id]):
                direction_groups[d.id].append({
                    'id': g.id,
                    'name': g.name
                })

    # Convert sets to sorted lists
    faculty_courses = sorted(list(active_courses))
    for c in faculty_course_semesters:
        faculty_course_semesters[c] = sorted(list(faculty_course_semesters[c]))

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
                flash(t('date_invalid_format'), 'error')
                return redirect(url_for('dean.edit_schedule', id=id))
        
        if not date_code:
            flash(t('date_required_select'), 'error')
            return redirect(url_for('dean.edit_schedule', id=id))
        
        schedule.subject_id = request.form.get('subject_id', type=int)
        schedule.group_id = request.form.get('group_id', type=int)
        schedule.teacher_id = request.form.get('teacher_id', type=int)
        schedule.day_of_week = date_code
        schedule.start_time = request.form.get('start_time')
        schedule.end_time = request.form.get('end_time') or None
        schedule.link = request.form.get('link')
        
        # O'qituvchiga biriktirilgan barcha dars turlarini topish
        assignments = TeacherSubject.query.filter_by(
            group_id=schedule.group_id,
            subject_id=schedule.subject_id,
            teacher_id=schedule.teacher_id
        ).all()
        
        # Dars turlarini yig'ish
        types_map = {
            'maruza': 'Ma\'ruza',
            'ma\'ruza': 'Ma\'ruza',
            'lecture': 'Ma\'ruza',
            'amaliyot': 'Amaliyot',
            'practice': 'Amaliyot',
            'laboratoriya': 'Laboratoriya',
            'lab': 'Laboratoriya',
            'seminar': 'Seminar',
            'kurs ishi': 'Kurs ishi',
            'kurs_ishi': 'Kurs ishi',
            'mustaqil ta\'lim': 'Mustaqil ta\'lim',
            'mustaqil talim': 'Mustaqil ta\'lim',
        }
        found_types = sorted(list(set([types_map.get(a.lesson_type.lower() if a.lesson_type else '', a.lesson_type.capitalize() if a.lesson_type else '') for a in assignments if a.lesson_type])))
        schedule.lesson_type = "/".join(found_types) if found_types else 'Ma\'ruza'
        
        db.session.commit()
        
        flash(t('schedule_updated'), 'success')
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
        faculty_courses=faculty_courses,
        faculty_course_semesters=faculty_course_semesters,
        faculty_course_semester_education_directions=faculty_course_semester_education_directions,
        direction_groups=direction_groups,
        teachers=teachers,
        schedule=schedule,
        schedule_date=schedule_date,
        year=year,
        month=month,
        current_faculty_id=faculty_id,
        current_course_year=schedule.group.course_year,
        current_semester=schedule.group.semester if schedule.group else None,
        current_direction_id=schedule.group.direction_id
    )


# ==================== HISOBOTLAR ====================
@bp.route('/reports')
@login_required
@dean_required
def reports():
    faculty = Faculty.query.get(current_user.faculty_id)
    if not faculty:
        flash(t('faculty_not_assigned'), 'error')
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


# ==================== FANLAR BAZASI ====================
@bp.route('/curriculum-subjects')
@login_required
@dean_required
def curriculum_subjects():
    """Legacy route: Fanlar bazasini yagona /subjects/ sahifasiga yo'naltirish."""
    params = request.args.to_dict(flat=True)
    if 'direction_id' in params and 'direction' not in params:
        params['direction'] = params.pop('direction_id')
    return redirect(url_for('courses.index', **params))



