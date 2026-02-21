from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app, jsonify
from flask_login import login_required, current_user
from app.models import User, Subject, Assignment, Announcement, Schedule, Submission, Message, Group, Faculty, TeacherSubject, StudentPayment, UserRole
from app import db
from datetime import datetime, timedelta, date

def get_tashkent_time():
    """Toshkent vaqtini qaytaradi (UTC+5)"""
    return datetime.utcnow() + timedelta(hours=5)
from sqlalchemy import func, or_, and_
from app.utils.translations import get_translation, get_current_language, t
import calendar

bp = Blueprint('main', __name__)


def _build_edu_dept_teachers_list():
    """O'quv bo'limi uchun o'qituvchi–fan–guruh ro'yxati (dashboard va fan_resurslari uchun).
    DirectionCurriculum asosida har bir dars turi alohida qatorda."""
    from app.models import DirectionCurriculum, Lesson, TeacherDepartment, Department, Direction
    from flask import session as flask_session
    from sqlalchemy import func
    _lang = flask_session.get('language', 'uz')
    teacher_dept_cache = {}
    dept_cache = {}
    result = []
    seen_combinations = set()
    
    # Faol guruhlar (talabalari bor)
    active_groups = Group.query.filter(Group.students.any()).all()
    
    for group in active_groups:
        if not group.direction_id:
            continue
        direction = Direction.query.get(group.direction_id)
        if not direction:
            continue
        
        # Shu guruhga mos curriculum yozuvlarini olish
        curr_query = DirectionCurriculum.query.filter(
            DirectionCurriculum.direction_id == group.direction_id,
            DirectionCurriculum.semester == (group.semester or 1)
        )
        curr_items = DirectionCurriculum.filter_by_group_context(curr_query, group).all()
        
        for item in curr_items:
            subject = item.subject
            if not subject:
                continue
            
            for lesson_type, hours_field in [('maruza', 'hours_maruza'), ('amaliyot', 'hours_amaliyot'), ('laboratoriya', 'hours_laboratoriya'), ('seminar', 'hours_seminar')]:
                hours = getattr(item, hours_field, 0) or 0
                if hours <= 0:
                    continue
                
                # Takrorlanishni oldini olish
                combo_key = (subject.id, group.id, lesson_type)
                if combo_key in seen_combinations:
                    continue
                seen_combinations.add(combo_key)
                
                # O'qituvchini topish - lesson_type variantlari
                lesson_type_map = {
                    'maruza': ['maruza', 'ma\'ruza', 'lecture'],
                    'amaliyot': ['amaliyot', 'laboratoriya', 'kurs_ishi', 'lab', 'practice'],
                    'laboratoriya': ['laboratoriya', 'lab', 'amaliyot'],
                    'seminar': ['seminar'],
                }
                lesson_type_variants = lesson_type_map.get(lesson_type, [lesson_type])
                existing_ts = TeacherSubject.query.filter(
                    TeacherSubject.subject_id == subject.id,
                    TeacherSubject.group_id == group.id,
                    func.lower(TeacherSubject.lesson_type).in_([lt.lower() for lt in lesson_type_variants])
                ).first()
                
                if not existing_ts:
                    continue  # Fan resurslarida faqat o'qituvchi biriktirilganlarni ko'rsatish
                
                teacher = User.query.get(existing_ts.teacher_id)
                if not teacher:
                    continue
                
                # Darslar sonini hisoblash
                search_lesson_types = [lesson_type]
                if lesson_type == 'amaliyot':
                    search_lesson_types = ['amaliyot', 'laboratoriya', 'kurs_ishi']
                created_count = Lesson.query.filter(
                    Lesson.subject_id == subject.id,
                    Lesson.created_by == teacher.id,
                    Lesson.lesson_type.in_(search_lesson_types),
                    ((Lesson.group_id == group.id) | (Lesson.group_id.is_(None) & (Lesson.direction_id == group.direction_id)))
                ).count()
                loaded_hours = created_count * 2
                remaining_hours = max(0, hours - loaded_hours)
                progress_pct = min(100, int((loaded_hours / hours) * 100)) if hours else 0
                
                # Kafedra nomlari
                if teacher.id not in teacher_dept_cache:
                    teacher_depts = Department.query.join(TeacherDepartment, Department.id == TeacherDepartment.department_id).filter(
                        TeacherDepartment.teacher_id == teacher.id
                    ).all()
                    teacher_dept_cache[teacher.id] = teacher_depts
                teacher_depts = teacher_dept_cache[teacher.id]
                teacher_dept_ids = {d.id for d in teacher_depts}
                subject_dept_id = subject.department_id
                if subject_dept_id and subject_dept_id not in dept_cache:
                    dept_cache[subject_dept_id] = Department.query.get(subject_dept_id)
                subject_dept = dept_cache.get(subject_dept_id) if subject_dept_id else None
                matched_depts = []
                if teacher_depts:
                    if subject_dept and subject_dept_id in teacher_dept_ids:
                        matched_depts = [subject_dept]
                    elif subject_dept:
                        intersection = [d for d in teacher_depts if d.id == subject_dept_id]
                        matched_depts = intersection if intersection else teacher_depts
                    else:
                        matched_depts = teacher_depts
                elif subject_dept:
                    matched_depts = [subject_dept]
                dept_names = '<br>'.join(d.get_display_name(_lang) or d.name for d in matched_depts) if matched_depts else ''
                
                result.append({
                    'teacher_id': teacher.id,
                    'teacher_name': teacher.full_name or teacher.login or '',
                    'department_names': dept_names,
                    'subject_id': subject.id,
                    'subject_name': subject.get_display_name(_lang) or subject.name,
                    'group_name': group.name,
                    'direction_name': (direction.get_display_name(_lang) or direction.name) if direction else '',
                    'lesson_type': lesson_type,
                    'total_hours': hours,
                    'loaded_hours': loaded_hours,
                    'remaining_hours': remaining_hours,
                    'progress_percent': progress_pct,
                    'semester': item.semester,
                })
    return result


@bp.route('/ping')
@login_required
def ping():
    """Session'ni yangilash uchun ping endpoint"""
    from flask import jsonify
    # Session'ni yangilash
    session.permanent = True
    return jsonify({'status': 'ok'})

@bp.route('/set-language/<lang>')
def set_language(lang):
    """Tilni o'zgartirish"""
    if lang in ['uz', 'ru', 'en']:
        session['language'] = lang
    return redirect(request.referrer or url_for('main.dashboard'))

@bp.route('/switch-role/<role>')
@login_required
def switch_role(role):
    """Rolni o'zgartirish"""
    # Foydalanuvchining mavjud rollarini tekshirish
    user_roles = current_user.get_roles()
    
    if role in user_roles:
        session['current_role'] = role
        role_name = t(role)  # Tanlangan til bo'yicha rol nomi
        flash(t('profile_role_changed', role_name=role_name), 'success')
        return redirect(url_for('main.dashboard'))
    else:
        flash(t('no_permission_for_role'), 'error')
        return redirect(url_for('main.dashboard'))

@bp.route('/')
def index():
    """Asosiy sahifa"""
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    return redirect(url_for('auth.login'))

@bp.route('/dashboard')
@login_required
def dashboard():
    """Dashboard sahifasi"""
    try:
        return _dashboard_inner()
    except Exception as e:
        import traceback
        err_msg = traceback.format_exc()
        current_app.logger.exception("Dashboard error")
        from flask import Response
        return Response('<pre style="white-space:pre-wrap;font-size:12px;padding:20px;">' + err_msg.replace('<', '&lt;') + '</pre>', status=500, mimetype='text/html')

def _dashboard_inner():
    """Dashboard sahifasi - ichki funksiya"""
    user = current_user
    # Foydalanuvchining faol (tanlangan) roli:
    # Agar bir nechta rol bo'lsa, session['current_role'] orqali tanlanadi,
    # aks holda user.role ishlatiladi.
    from flask import session as flask_session
    active_role = flask_session.get('current_role') or user.role
    # Agar session'dagi rol foydalanuvchida mavjud bo'lmasa, asosiy rolga qaytamiz
    if hasattr(user, "has_role") and active_role and not user.has_role(active_role):
        active_role = user.role
    
    # Foydalanuvchi rollariga qarab turli ma'lumotlar
    stats = {}
    edu_dept_sort_by = 'teacher'
    edu_dept_sort_order = 'asc'

    # Xodimlar sonini hisoblash (Talaba bo'lmagan barcha foydalanuvchilar)
    total_staff = User.query.filter(User.role != 'student').count()

    announcements = []
    recent_assignments = []
    upcoming_schedules = []
    
    # my_subjects o'zgaruvchisini barcha rollar uchun yaratish
    my_subjects = []
    semester_progress = 0
    semester_grade = None
    payment_info = None
    direction_id = None
    
    # Salomlashuv va bugungi sana (tanlangan til bo'yicha)
    now = get_tashkent_time()
    today = now.strftime('%d.%m.%Y')
    lang = session.get('language', 'uz')
    hour = now.hour
    if 5 <= hour < 10:
        greeting = get_translation('good_morning', lang)
    elif 10 <= hour < 18:
        greeting = get_translation('good_afternoon', lang)
    elif 18 <= hour < 22:
        greeting = get_translation('good_evening', lang)
    else:
        greeting = get_translation('good_night', lang)
    
    if active_role == 'student':
        from app.models import DirectionCurriculum, Direction
        current_semester = user.semester
        my_subjects_info = {}
        current_semester_subjects_count = 0
        total_semester_credits = 0.0
        direction_id = None
        
        if user.group_id:
            group = Group.query.get(user.group_id)
            curriculum_list = []  # Har doim o'rnatish – group None bo'lsa ham NameError bo'lmasligi uchun
            if group:
                direction_id = group.direction_id
                if group.direction:
                    current_semester = group.semester
            
            # Fetch curriculum items for all subjects in the current semester (o'z yo'nalishi, yili, ta'lim shakli)
            if direction_id and group:
                curr_q = DirectionCurriculum.query.filter(
                    DirectionCurriculum.direction_id == direction_id,
                    DirectionCurriculum.semester == current_semester
                ).join(Subject).order_by(Subject.name)
                curriculum_list = DirectionCurriculum.filter_by_group_context(curr_q, group).all()
            
            # Populate basic info and collect subject IDs
            subject_ids = []
            total_semester_credits = 0.0
            for item in curriculum_list:
                subject_ids.append(item.subject_id)
                course_year = ((item.semester - 1) // 2) + 1
                
                # Formula: (maruza + amaliyot + laboratoriya + seminar + mustaqil) / 30
                total_hours = (item.hours_maruza or 0) + (item.hours_amaliyot or 0) + \
                             (item.hours_laboratoriya or 0) + (item.hours_seminar or 0) + \
                             (item.hours_mustaqil or 0)
                
                subject = Subject.query.get(item.subject_id)
                if total_hours > 0:
                    credits = total_hours / 30.0
                else:
                    credits = float(subject.credits) if subject and subject.credits else 0.0
                
                total_semester_credits += credits
                direction_obj = Direction.query.get(group.direction_id) if group and group.direction_id else None
                my_subjects_info[item.subject_id] = {
                    'semester': item.semester,
                    'course_year': course_year,
                    'credits': credits,
                    'progress': 0,
                    'graded_count': 0,
                    'total_assignments': 0,
                    'progress_score': 0,
                    'progress_max': 100,
                    'direction': direction_obj,
                    'group_id': user.group_id
                }

            # If my_subjects is still empty, try to populate from curriculum
            if not my_subjects and subject_ids:
                my_subjects = Subject.query.filter(Subject.id.in_(subject_ids)).order_by(Subject.name).all()
            
            # Now calculate scores for ALL subjects we found
            all_subj_ids = list(set(subject_ids + [s.id for s in my_subjects]))
            
            if all_subj_ids:
                # Fetch assignments
                assignment_query = Assignment.query.filter(Assignment.subject_id.in_(all_subj_ids))
                if direction_id:
                    assignment_query = assignment_query.filter(
                        (Assignment.direction_id == direction_id) | (Assignment.direction_id.is_(None)),
                        (Assignment.group_id == user.group_id) | (Assignment.group_id.is_(None))
                    )
                else:
                    assignment_query = assignment_query.filter(
                        (Assignment.group_id == user.group_id) | (Assignment.group_id.is_(None))
                    )
                all_assignments_list = assignment_query.all()
                
                # Fetch submissions
                assign_ids = [a.id for a in all_assignments_list]
                user_submissions = Submission.query.filter(
                    Submission.student_id == user.id,
                    Submission.assignment_id.in_(assign_ids)
                ).all() if assign_ids else []
                
                # Highest score map
                submissions_map = {}
                for s in user_submissions:
                    if s.assignment_id not in submissions_map:
                        submissions_map[s.assignment_id] = s
                    elif s.score is not None:
                        current = submissions_map[s.assignment_id]
                        if current.score is None or s.score > current.score:
                            submissions_map[s.assignment_id] = s

                total_semester_score = 0.0
                total_semester_max_score = 0.0
                
                # Group assignments by subject for efficient lookup
                assignments_by_subject = {}
                for a in all_assignments_list:
                    if a.subject_id not in assignments_by_subject:
                        assignments_by_subject[a.subject_id] = []
                    assignments_by_subject[a.subject_id].append(a)

                for sid in all_subj_ids:
                    s_assignments = assignments_by_subject.get(sid, [])
                    sub_score = 0.0
                    sub_max = 0.0
                    sub_graded = 0
                    
                    for a in s_assignments:
                        sub_max += (a.max_score or 0)
                        subm = submissions_map.get(a.id)
                        if subm and subm.score is not None:
                            sub_score += subm.score
                            sub_graded += 1
                    
                    prog = (sub_score / sub_max) * 100 if sub_max > 0 else 0.0
                    
                    if sid not in my_subjects_info:
                        # Ensure we have info for subjects that were found via get_subjects but not curriculum
                        subject = Subject.query.get(sid)
                        c_semester = current_semester or 1
                        my_subjects_info[sid] = {
                            'semester': current_semester,
                            'course_year': ((c_semester - 1) // 2) + 1,
                            'credits': float(subject.credits) if subject and subject.credits else 0.0,
                            'progress': 0,
                            'graded_count': 0,
                            'total_assignments': 0,
                            'progress_score': 0,
                            'progress_max': 100
                        }
                    
                    my_subjects_info[sid].update({
                        'progress': prog,
                        'graded_count': sub_graded,
                        'total_assignments': len(s_assignments),
                        'progress_score': sub_score,
                        'progress_max': sub_max if sub_max > 0 else 100
                    })
                    
                    # Only add to semester totals if the subject is in the current semester curriculum
                    if sid in subject_ids:
                        total_semester_score += sub_score
                        total_semester_max_score += sub_max

                current_semester_subjects_count = len(subject_ids)
                if total_semester_max_score > 0:
                    semester_progress = (total_semester_score / total_semester_max_score) * 100
                    from app.models import GradeScale
                    semester_grade = GradeScale.get_grade(semester_progress)
                else:
                    semester_progress = 0
                    semester_grade = None
        
        # Barcha topshiriqlar (talabaning guruhiga tegishli va joriy semestrdagi fanlar uchun)
        all_assignments = []
        if user.group_id:
            group = Group.query.get(user.group_id)
            if group and group.direction_id:
                # Joriy semestrdagi fanlar (yo'nalish, yil, ta'lim shakli bo'yicha)
                curr_q = DirectionCurriculum.query.filter_by(
                    direction_id=group.direction_id,
                    semester=current_semester
                )
                curriculum_items = DirectionCurriculum.filter_by_group_context(curr_q, group).all()
                current_semester_subject_ids = [item.subject_id for item in curriculum_items]
                
                if current_semester_subject_ids:
                    # Faqat joriy semestrdagi fanlarga tegishli topshiriqlar
                    # Filterlash mantiqi courses.grades dagi kabi bo'lishi kerak
                    all_assignments = Assignment.query.filter(
                        Assignment.subject_id.in_(current_semester_subject_ids),
                        (Assignment.group_id == user.group_id) | (Assignment.group_id.is_(None)),
                        (Assignment.direction_id == group.direction_id) | (Assignment.direction_id.is_(None))
                    ).order_by(Assignment.due_date.desc()).all()
                else:
                    all_assignments = []
        
        # Topshirilgan topshiriqlar (baholangan) - faqat joriy semestrdagi topshiriqlar uchun
        graded_submissions = []
        graded_assignment_ids = []
        if all_assignments:
            assignment_ids = [a.id for a in all_assignments]
            graded_submissions = Submission.query.join(Assignment).filter(
                Submission.student_id == user.id,
                Submission.is_active == True,
                Submission.score != None,
                Assignment.id.in_(assignment_ids)
            ).all()
            graded_assignment_ids = [s.assignment_id for s in graded_submissions]
        
        # Topshirilgan lekin baholanmagan - faqat joriy semestrdagi topshiriqlar uchun
        submitted_ungraded = []
        submitted_ungraded_ids = []
        if all_assignments:
            assignment_ids = [a.id for a in all_assignments]
            submitted_ungraded = Submission.query.join(Assignment).filter(
                Submission.student_id == user.id,
                Submission.is_active == True,
                Submission.score == None,
                Assignment.id.in_(assignment_ids)
            ).all()
            submitted_ungraded_ids = [s.assignment_id for s in submitted_ungraded]
        
        # Topshirilmagan topshiriqlar
        all_assignment_ids = [a.id for a in all_assignments]
        submitted_ids = graded_assignment_ids + submitted_ungraded_ids
        not_submitted_ids = [aid for aid in all_assignment_ids if aid not in submitted_ids]
        
        graded_count = len(graded_assignment_ids)
        submitted_count = len(submitted_ungraded_ids)
        submitted_total_count = graded_count + submitted_count  # Barcha topshirilgan topshiriqlar (baholangan + yuborilgan)
        not_submitted_count = len(not_submitted_ids)
        
        stats = {
            'subjects': my_subjects,
            'assignments': len(all_assignments),
            'submissions': Submission.query.filter_by(student_id=user.id).count(),
            'completed_assignments': graded_count,
            'current_semester_subjects': current_semester_subjects_count,
            'total_semester_credits': total_semester_credits,
            'graded_assignments': graded_count,
            'submitted_assignments': submitted_total_count,  # Barcha topshirilgan (baholangan + yuborilgan)
            'not_submitted_assignments': not_submitted_count,
            'overdue_assignments': 0  # Keyinroq yangilanadi
        }
        
        # E'lonlar
        announcements = Announcement.query.filter(
            (Announcement.target_roles.contains('student')) |
            (Announcement.target_roles == None)
        ).order_by(Announcement.created_at.desc()).limit(5).all()
        
        # Barcha topshiriqlar (template'ga uzatish uchun)
        recent_assignments = all_assignments
        
        # Joriy vaqt (Toshkent vaqti)
        now_dt = get_tashkent_time()
        
        # Muddati yaqinlashgan topshiriqlar (faqat 36 soatdan kam qolganlar)
        upcoming_due_assignments = []
        if all_assignments and 'not_submitted_ids' in locals():
            # Faqat topshirilmagan topshiriqlar ro'yxatidan olish
            upcoming_assignments_temp = []
            for assignment in all_assignments:
                if assignment.id in not_submitted_ids and assignment.due_date:
                    # assignment.due_date datetime bo'lishi kerak, lekin xavfsizlik uchun tekshiramiz
                    assignment_due = assignment.due_date
                    if assignment_due:
                        # Timezone'ni olib tashlash
                        if hasattr(assignment_due, 'tzinfo') and assignment_due.tzinfo:
                            assignment_due = assignment_due.replace(tzinfo=None)
                        
                        now_clean = now_dt.replace(tzinfo=None) if now_dt.tzinfo else now_dt
                        
                        # Deadline kun oxirigacha (23:59:59) hisoblanadi
                        if hasattr(assignment_due, 'replace') and hasattr(assignment_due, 'hour'):
                            # Bu datetime
                            deadline_end = assignment_due.replace(hour=23, minute=59, second=59)
                        else:
                            # Bu date, datetime ga o'tkazamiz
                            from datetime import time as dt_time
                            deadline_end = datetime.combine(assignment_due, dt_time(23, 59, 59))
                        
                        # Qolgan vaqtni hisoblash
                        time_left = deadline_end - now_clean
                        hours_left = time_left.total_seconds() / 3600
                        
                        # Agar manfiy bo'lsa, 0 qilib qo'yish
                        if hours_left < 0:
                            hours_left = 0
                        
                        # Faqat 36 soatdan kam qolgan topshiriqlar (0 soatni ham kiritmaymiz)
                        if 0 < hours_left <= 36:
                            assignment_date = deadline_end.date()
                            now_date = now_clean.date()
                            days_left = (assignment_date - now_date).days
                            if days_left < 0:
                                days_left = 0
                            
                            # Progress percent hisoblash (36 soat = 100%, 0 soat = 0%)
                            progress_percent = (hours_left / 36) * 100
                            
                            upcoming_assignments_temp.append({
                                'assignment': assignment,
                                'status': 'upcoming',
                                'submission': None,
                                'days_left': days_left,
                                'hours_left': hours_left,
                                'progress_percent': progress_percent
                            })
            
            # Topshiriqlarni muddati bo'yicha tartiblash (eng yaqin muddat birinchi)
            upcoming_due_assignments = sorted(upcoming_assignments_temp, key=lambda x: x['hours_left'])
        
        
        # Dars jadvali
        if user.group_id:
            # Only show subjects from the current semester's curriculum
            subject_ids = [item.subject_id for item in curriculum_list]
            upcoming_schedules = Schedule.query.filter(
                Schedule.group_id == user.group_id,
                Schedule.subject_id.in_(subject_ids)
            ).all()
            
            # Bugungi dars jadvali (Toshkent vaqti bo'yicha)
            today_date = get_tashkent_time().date()
            date_code = int(today_date.strftime("%Y%m%d"))
            today_schedule = Schedule.query.filter(
                Schedule.group_id == user.group_id,
                Schedule.subject_id.in_(subject_ids),
                Schedule.day_of_week == date_code
            ).order_by(Schedule.start_time).all()
        else:
            today_schedule = []
        
        # Topshiriqlar ma'lumotlari (har bir topshiriq uchun holat)
        assignments_with_status = []
        now_dt_check = get_tashkent_time()
        for assignment in all_assignments:
            submission = Submission.query.filter_by(
                student_id=user.id,
                assignment_id=assignment.id,
                is_active=True
            ).first()

            status = 'not_submitted'
            if submission:
                if submission.score is not None:
                    status = 'graded'
                else:
                    status = 'submitted'

            # Qolgan vaqtni hisoblash (muddati yaqinlashgan topshiriqlar uchun)
            days_left = None
            hours_left = None
            is_urgent = False
            is_overdue = False
            if assignment.due_date and status != 'graded':
                assignment_due = assignment.due_date.replace(tzinfo=None) if assignment.due_date.tzinfo else assignment.due_date
                now_clean = now_dt_check.replace(tzinfo=None) if now_dt_check.tzinfo else now_dt_check
                # Deadline kun oxirigacha (23:59:59) hisoblanadi
                if isinstance(assignment_due, datetime):
                    deadline_end = assignment_due.replace(hour=23, minute=59, second=59)
                else:
                    from datetime import time as dt_time
                    deadline_end = datetime.combine(assignment_due, dt_time(23, 59, 59))
                # Qolgan vaqtni hisoblash
                time_left = deadline_end - now_clean
                hours_left = time_left.total_seconds() / 3600
                deadline_date = deadline_end.date()
                now_date = now_clean.date()
                days_left = (deadline_date - now_date).days
                
                # Muddat o'tganligini tekshirish
                if hours_left < 0:
                    is_overdue = True
                    hours_left = 0
                    days_left = 0
                else:
                    is_overdue = False
                
                # 36 soat ichida va hali topshirilmagan bo'lsa - urgent
                if 0 <= hours_left <= 36:
                    is_urgent = True
                
                # Progress percent hisoblash (faqat 36 soatdan kam qolganlar uchun)
                # 36 soat = 100%, 0 soat = 0%
                progress_percent = None
                if hours_left >= 0 and hours_left <= 36:
                    # Faqat 36 soat ichida: progress = qancha vaqt qolgani (foizda)
                    progress_percent = (hours_left / 36) * 100
                # 36 soatdan ko'p qolgan yoki muddat o'tgan: progress_percent None qoladi (ko'rsatilmaydi)
            else:
                progress_percent = None

            assignments_with_status.append({
                'assignment': assignment,
                'status': status,
                'submission': submission,
                'days_left': days_left,
                'hours_left': hours_left,
                'is_urgent': is_urgent,
                'is_overdue': is_overdue,
                'progress_percent': progress_percent
            })

        # Topshiriqlarni muddati bo'yicha tartiblash (eng yaqin muddat birinchi)
        # hours_left bo'yicha tartiblaymiz (None bo'lsa, juda katta qiymat - oxiriga qo'yamiz)
        def sort_key(item):
            if item['hours_left'] is not None:
                return item['hours_left']
            # hours_left None bo'lsa (masalan, graded topshiriqlar yoki due_date yo'q topshiriqlar)
            # ularni oxiriga qo'yamiz
            return float('inf')
        
        pending_assignments = sorted(assignments_with_status, key=sort_key)
        
        # Muddati o'tgan topshiriqlar sonini stats'ga qo'shish va not_submitted_count'dan chiqarish
        overdue_count = sum(1 for item in assignments_with_status if item.get('is_overdue', False) and item.get('status') == 'not_submitted')
        stats['overdue_assignments'] = overdue_count
        # Muddati o'tgan topshiriqlarni "Topshirilmagan" sonidan chiqarish
        stats['not_submitted_assignments'] = stats['not_submitted_assignments'] - overdue_count
        
        # semester_progress, total_semester_score, total_semester_max_score already calculated above for students
        pass
        
        # To'lov ma'lumotlari: joriy o'quv yili uchun (maxsus kontrakt, ortiqcha to'lov bilan)
        payment_info = None
        from app.utils.payment_utils import get_current_year_payment_info
        pi = get_current_year_payment_info(user)
        if pi:
            payment_info = {
                'contract': pi['contract'],
                'paid': pi['paid_display'],  # Kontrakt miqdorigacha ko'rsatiladi
                'remaining': pi['remaining'],
                'percentage': pi['percentage'],
                'overpayment': pi.get('overpayment', 0)
            }
    
    elif active_role == 'teacher':
        # O'qituvchi uchun
        from app.models import DirectionCurriculum, Direction, Lesson
        teacher_subjects = TeacherSubject.query.filter_by(teacher_id=user.id).all()
        subject_ids = [ts.subject_id for ts in teacher_subjects]
        
        # Fanlarni semester va kurs ma'lumotlari bilan yig'ish (har bir guruh uchun alohida)
        my_subjects_list = []
        my_subjects_info = {}
        seen_subject_group = set()
        
        for ts in teacher_subjects:
            group = Group.query.get(ts.group_id)
            if group and group.direction_id:
                # Check if group has students
                if group.get_students_count() == 0:
                    continue
                
                # Deduplication check
                sg_key = (ts.subject_id, ts.group_id)
                if sg_key in seen_subject_group:
                    continue
                seen_subject_group.add(sg_key)
                # Only show subjects that belong to the group's current semester (yil, ta'lim shakli)
                current_semester = group.semester if group.semester else 1
                curr_q = DirectionCurriculum.query.filter_by(
                    direction_id=group.direction_id,
                    subject_id=ts.subject_id,
                    semester=current_semester
                )
                curriculum_item = DirectionCurriculum.filter_by_group_context(curr_q, group).first()
                if curriculum_item:
                    subject = Subject.query.get(ts.subject_id)
                    if subject:
                        course_year = ((curriculum_item.semester - 1) // 2) + 1
                        
                        # Kreditlarni hisoblash
                        total_hours = (curriculum_item.hours_maruza or 0) + (curriculum_item.hours_amaliyot or 0) + \
                                     (curriculum_item.hours_laboratoriya or 0) + (curriculum_item.hours_seminar or 0) + \
                                     (curriculum_item.hours_mustaqil or 0)
                        
                        if total_hours > 0:
                            credits = total_hours / 30.0
                        else:
                            credits = float(subject.credits) if subject and subject.credits else 0.0
                            
                        # Progress hisoblash
                        # 1. Biriktirilgan dars turlarini aniqlash
                        assigned_types = []
                        search_lesson_types = []
                        assigned_total_hours = 0
                        
                        # Ushbu guruh va fan bo'yicha o'qituvchining barcha biriktiruvlarini olish
                        # Chunki ts faqat bittasini ko'rsatishi mumkin, bizga hammasi kerak
                        group_assignments = TeacherSubject.query.filter_by(
                            teacher_id=user.id,
                            group_id=group.id,
                            subject_id=subject.id
                        ).all()
                        
                        for ga in group_assignments:
                            if ga.lesson_type:
                                assigned_types.append(ga.lesson_type)
                                
                                # Soatni qo'shish va qidiriladigan dars turlarini kengaytirish
                                if ga.lesson_type == 'maruza':
                                    assigned_total_hours += (curriculum_item.hours_maruza or 0)
                                    search_lesson_types.append('maruza')
                                    
                                elif ga.lesson_type == 'amaliyot':
                                    # Dean.py da amaliyot o'qituvchisi laboratoriya va kurs ishiga ham mas'ul ekanligi ko'rinmoqda
                                    assigned_total_hours += (curriculum_item.hours_amaliyot or 0) + \
                                                          (curriculum_item.hours_laboratoriya or 0) + \
                                                          (curriculum_item.hours_kurs_ishi or 0)
                                    search_lesson_types.extend(['amaliyot', 'laboratoriya', 'kurs_ishi'])
                                    
                                elif ga.lesson_type == 'laboratoriya':
                                    assigned_total_hours += (curriculum_item.hours_laboratoriya or 0)
                                    search_lesson_types.append('laboratoriya')
                                    
                                elif ga.lesson_type == 'seminar':
                                    assigned_total_hours += (curriculum_item.hours_seminar or 0)
                                    search_lesson_types.append('seminar')
                                    
                                elif ga.lesson_type == 'kurs_ishi':
                                    assigned_total_hours += (curriculum_item.hours_kurs_ishi or 0)
                                    search_lesson_types.append('kurs_ishi')
                        
                        # Unikal qilish
                        search_lesson_types = list(set(search_lesson_types))
                        
                        # 2. Yaratilgan mavzularni sanash:
                        # - guruhga biriktirilgan (group_id == group.id) yoki
                        # - yo'nalish darajasidagi umumiy darslar (group_id=None, direction_id == group.direction_id)
                        created_lessons_count = 0
                        if search_lesson_types:
                            created_lessons_count = Lesson.query.filter(
                                Lesson.subject_id == subject.id,
                                Lesson.created_by == user.id,
                                Lesson.lesson_type.in_(search_lesson_types),
                                (
                                    (Lesson.group_id == group.id) |
                                    (
                                        Lesson.group_id.is_(None) &
                                        (Lesson.direction_id == group.direction_id)
                                    )
                                )
                            ).count()
                        
                        # Foiz hisoblash (1 mavzu = 2 soat deb faraz qilinadi)
                        progress_percent = 0
                        if assigned_total_hours > 0:
                            progress_percent = min(100, int((created_lessons_count * 2 / assigned_total_hours) * 100))

                        item = {
                            'id': subject.id,
                            'name': subject.name,
                            'display_name': f"{subject.name} ({group.name})",
                            'semester': curriculum_item.semester,
                            'course_year': course_year,
                            'direction': Direction.query.get(group.direction_id),
                            'credits': credits,
                            'group_id': group.id,
                            'group_name': group.name,
                            'total_hours': assigned_total_hours,
                            'created_count': created_lessons_count,
                            'progress': progress_percent
                        }
                        my_subjects_list.append(item)
                        # Fallback info key
                        my_subjects_info[f"{subject.id}_{group.id}"] = item
        
        # Tartiblash: Kurs -> Semester -> Fan nomi -> Guruh nomi
        my_subjects_list.sort(key=lambda x: (x['course_year'], x['semester'], x['name'], x['display_name']))
        
        my_subjects = my_subjects_list
        
        # Stats
        stats = {
            'total_subjects': len(set(item['id'] for item in my_subjects)),
            'total_groups': len(set(ts.group_id for ts in teacher_subjects)),
            'assignments': Assignment.query.filter(
                Assignment.subject_id.in_(subject_ids),
                Assignment.created_by == user.id
            ).count() if subject_ids else 0,
            'pending_submissions': Submission.query.join(Assignment).filter(
                Assignment.subject_id.in_(subject_ids),
                Assignment.created_by == user.id,
                Submission.score == None
            ).count() if subject_ids else 0
        }
        
        # E'lonlar
        announcements = Announcement.query.filter(
            (Announcement.target_roles.contains('teacher')) |
            (Announcement.target_roles == None)
        ).order_by(Announcement.created_at.desc()).limit(5).all()
        
        # Yaqin topshiriqlar
        recent_assignments = Assignment.query.filter(
            Assignment.subject_id.in_(subject_ids)
        ).order_by(Assignment.due_date.desc()).limit(5).all() if subject_ids else []
        
        # Topshiriqlar ro'yxati (Assignments) — faqat o'qituvchiga biriktirilgan guruhlar bo'yicha
        teacher_assignments_list = []
        if subject_ids:
            # O'qituvchiga biriktirilgan (subject_id, group_id) juftliklari — faqat faol guruhlar
            teacher_subject_group = set()
            teacher_direction_groups = {}
            for ts in TeacherSubject.query.filter_by(teacher_id=user.id).all():
                if not ts.group_id:
                    continue
                gr = Group.query.get(ts.group_id)
                if not gr or gr.get_students_count() == 0:
                    continue
                teacher_subject_group.add((ts.subject_id, ts.group_id))
                if gr.direction_id:
                    if gr.direction_id not in teacher_direction_groups:
                        teacher_direction_groups[gr.direction_id] = {}
                    teacher_direction_groups[gr.direction_id][ts.subject_id] = teacher_direction_groups[gr.direction_id].get(ts.subject_id, [])
                    if gr.name and gr.name not in teacher_direction_groups[gr.direction_id][ts.subject_id]:
                        teacher_direction_groups[gr.direction_id][ts.subject_id].append(gr.name)
            for k in teacher_direction_groups:
                for s in teacher_direction_groups[k]:
                    teacher_direction_groups[k][s].sort(key=lambda x: (x or '').upper())

            assignments_query = Assignment.query.filter(
                Assignment.subject_id.in_(subject_ids),
                Assignment.created_by == user.id
            ).order_by(Assignment.due_date.desc()).all()

            for asm in assignments_query:
                group_name = None
                if asm.group_id:
                    # Guruh darajasidagi topshiriq — faqat o'qituvchi shu fan uchun shu guruhga biriktirilgan bo'lsa
                    if (asm.subject_id, asm.group_id) not in teacher_subject_group:
                        continue
                    gr = Group.query.get(asm.group_id)
                    if not gr or gr.get_students_count() == 0:
                        continue
                    group_name = gr.name
                else:
                    # Yo'nalish darajasidagi topshiriq — o'qituvchi shu fan uchun shu yo'nalishdagi guruhga biriktirilgan bo'lsa
                    if not asm.direction_id or asm.direction_id not in teacher_direction_groups:
                        continue
                    subj_groups = teacher_direction_groups[asm.direction_id].get(asm.subject_id)
                    if not subj_groups:
                        continue
                    group_name = ', '.join(subj_groups)

                pending_query = asm.submissions.filter(Submission.score == None)
                pending_count = pending_query.count()
                resubmitted_count = pending_query.filter(Submission.resubmission_count > 0).count()

                item = {
                    'id': asm.id,
                    'title': asm.title,
                    'subject_name': asm.subject.name,
                    'group_name': group_name,
                    'due_date': asm.due_date,
                    'lesson_type': asm.lesson_type,
                    'pending_count': pending_count,
                    'resubmitted_count': resubmitted_count
                }
                teacher_assignments_list.append(item)
            
            # Pending topshiriqlar ro'yxati (Tekshirilmagan)
            teacher_pending_assignments_list = [a for a in teacher_assignments_list if a['pending_count'] > 0]
            # Stats ni filtrlangan topshiriqlarga moslashtirish
            stats['assignments'] = len(teacher_assignments_list)
            stats['pending_submissions'] = sum(a['pending_count'] for a in teacher_assignments_list)


    elif active_role == 'dean':
        # Dekan uchun
        faculty = Faculty.query.get(user.faculty_id) if user.faculty_id else None
        
        if faculty:
            stats = {
                'total_students': User.query.join(Group).filter(Group.faculty_id == faculty.id, User.role == 'student').count(),
                'total_teachers': User.query.filter_by(role='teacher').count(),
                'total_subjects': Subject.query.count(),  # Subject modelida faculty_id maydoni yo'q
                'total_groups': Group.query.filter_by(faculty_id=faculty.id).count()
            }
            
            # E'lonlar
            announcements = Announcement.query.filter(
                ((Announcement.target_roles.contains('dean')) | (Announcement.target_roles == None)),
                (Announcement.faculty_id == faculty.id) | (Announcement.faculty_id == None)
            ).order_by(Announcement.created_at.desc()).limit(5).all()

    elif active_role == 'admin':
        # Admin uchun
        stats = {
            'total_users': User.query.count(),
            'total_students': User.query.filter_by(role='student').count(),
            'total_teachers': User.query.filter_by(role='teacher').count(),
            'total_faculties': Faculty.query.count(),
            'total_subjects': Subject.query.count(),
            'total_staff': total_staff
        }
        
        # E'lonlar
        announcements = Announcement.query.order_by(Announcement.created_at.desc()).limit(5).all()

    elif active_role == 'department_head':
        # Kafedra mudiri uchun - o'z kafedrasiga oid statistika
        from app.models import DepartmentHead, TeacherDepartment, Department, DirectionCurriculum, Direction
        my_dept_ids = [link.department_id for link in DepartmentHead.query.filter_by(user_id=current_user.id).all()]
        my_departments = Department.query.filter(Department.id.in_(my_dept_ids)).all() if my_dept_ids else []
        
        # O'z kafedrasidagi o'qituvchilar
        teachers_in_dept = User.query.join(TeacherDepartment, User.id == TeacherDepartment.teacher_id).filter(
            TeacherDepartment.department_id.in_(my_dept_ids)
        ).distinct().all() if my_dept_ids else []
        
        # O'z kafedrasidagi fanlar
        subjects_in_dept = Subject.query.filter(Subject.department_id.in_(my_dept_ids)).all() if my_dept_ids else []
        subject_ids_in_dept = [s.id for s in subjects_in_dept]
        
        # Faol guruhlar soni (kafedra fanlari o'qitiladigan)
        active_groups = Group.query.filter(Group.students.any()).all()
        groups_with_dept_subjects = set()
        if subject_ids_in_dept:
            for group in active_groups:
                if group.direction_id:
                    curr_count = DirectionCurriculum.query.filter(
                        DirectionCurriculum.direction_id == group.direction_id,
                        DirectionCurriculum.semester == (group.semester or 1),
                        DirectionCurriculum.subject_id.in_(subject_ids_in_dept)
                    ).count()
                    if curr_count > 0:
                        groups_with_dept_subjects.add(group.id)
        
        stats = {
            'total_departments': len(my_departments),
            'total_teachers': len(teachers_in_dept),
            'total_subjects': len(subjects_in_dept),
            'total_groups': len(groups_with_dept_subjects),
        }
        
        # 0% ro'yxati - o'z kafedrasidagi fanlar uchun
        dept_head_teachers = []
        try:
            all_rows = _build_edu_dept_teachers_list()
            dept_head_teachers = [r for r in all_rows if r.get('subject_id') in subject_ids_in_dept]
        except Exception as e:
            current_app.logger.warning("department_head dashboard: %s", e)
        
        announcements = Announcement.query.order_by(Announcement.created_at.desc()).limit(5).all()

    elif active_role == 'edu_dept':
        # O'quv bo'limi uchun: fanlar, resurslar, o'qituvchilar, guruhlar
        try:
            from app.models import DirectionCurriculum, Department, Direction
            groups_with_students = Group.query.filter(Group.students.any()).all()
            teacher_ids_with_assignments = db.session.query(TeacherSubject.teacher_id).distinct().join(
                Group, TeacherSubject.group_id == Group.id
            ).filter(Group.students.any()).all()
            teacher_ids_with_assignments = [r[0] for r in teacher_ids_with_assignments if r[0]]
            stats = {
                'total_directions': Direction.query.count(),
                'total_departments': Department.query.count(),
                'total_teachers': len(set(teacher_ids_with_assignments)),
                'total_subjects': Subject.query.count(),
                'total_groups': len(groups_with_students),
            }
            edu_dept_teachers = _build_edu_dept_teachers_list()
            announcements = Announcement.query.filter(
                (Announcement.target_roles.contains('edu_dept')) | (Announcement.target_roles == None)
            ).order_by(Announcement.created_at.desc()).limit(5).all()
        except Exception as e:
            current_app.logger.warning("edu_dept dashboard: %s", e)
            try:
                from app.models import Department, Direction
                stats = {
                    'total_directions': Direction.query.count(),
                    'total_departments': Department.query.count(),
                    'total_teachers': 0,
                    'total_subjects': Subject.query.count(),
                    'total_groups': Group.query.count(),
                }
            except Exception:
                stats = {'total_directions': 0, 'total_departments': 0, 'total_teachers': 0, 'total_subjects': 0, 'total_groups': 0}
            edu_dept_teachers = []
            announcements = []

        # O'quv bo'limi jadvali: ustun bo'yicha tartiblash (yo'nalishlar bo'limi uslubida)
        edu_dept_sort_by = request.args.get('sort', 'teacher', type=str)
        edu_dept_sort_order = request.args.get('order', 'asc', type=str)
        if edu_dept_sort_order not in ('asc', 'desc'):
            edu_dept_sort_order = 'asc'
        sort_key_map = {
            'teacher': 'teacher_name',
            'department': 'department_names',
            'subject': 'subject_name',
            'direction': 'direction_name',
            'group': 'group_name',
            'lesson_type': 'lesson_type',
            'total_hours': 'total_hours',
            'loaded_hours': 'loaded_hours',
            'remaining_hours': 'remaining_hours',
            'progress': 'progress_percent',
        }
        sort_key = sort_key_map.get(edu_dept_sort_by, 'teacher_name')
        if sort_key in ('total_hours', 'loaded_hours', 'remaining_hours', 'progress_percent'):
            edu_dept_teachers.sort(key=lambda r: (r.get(sort_key) is None, r.get(sort_key) if isinstance(r.get(sort_key), (int, float)) else 0), reverse=(edu_dept_sort_order == 'desc'))
        else:
            edu_dept_teachers.sort(key=lambda r: (r.get(sort_key) or '').lower(), reverse=(edu_dept_sort_order == 'desc'))

        # Dashboardda asosan 0% li qatorlarni ko'rsatish; to'liq ro'yxat Fan resurslari bo'limida
        edu_dept_teachers = [r for r in edu_dept_teachers if r.get('progress_percent') == 0]

    # To'lov statistikasi: admin, accounting, dean uchun dashboardda
    payment_total_contract = 0
    payment_total_paid = 0
    payment_stats_by_course = {}
    if active_role in ('admin', 'accounting', 'dean'):
        from app.models import DirectionContractAmount
        from collections import defaultdict
        faculty_restrict = user.faculty_id if active_role == 'dean' and user.faculty_id else None
        students_q = User.query.filter(User.role == 'student')
        if faculty_restrict:
            faculty_group_ids = [g.id for g in Group.query.filter_by(faculty_id=faculty_restrict).all()]
            students_q = students_q.filter(User.group_id.in_(faculty_group_ids))
        _students_list = students_q.all()
        payment_total_contract = sum(DirectionContractAmount.get_contract_for_student(s) for s in _students_list)
        _student_ids = [s.id for s in _students_list]
        payment_total_paid = db.session.query(func.sum(StudentPayment.paid_amount)).filter(
            StudentPayment.student_id.in_(_student_ids) if _student_ids else StudentPayment.student_id == -1
        ).scalar() or 0
        all_payments_for_stats = StudentPayment.query.all()
        _stats = defaultdict(lambda: {'0%': 0, '25%': 0, '50%': 0, '75%': 0, '100%': 0, 'total': 0})
        for s in _students_list:
            if not s.group or (faculty_restrict and s.group.faculty_id != faculty_restrict):
                continue
            cy = s.group.course_year
            contract = DirectionContractAmount.get_contract_for_student(s)
            if contract == 0:
                contract = sum(float(x.contract_amount or 0) for x in all_payments_for_stats if x.student_id == s.id)
            paid = sum(float(x.paid_amount or 0) for x in all_payments_for_stats if x.student_id == s.id)
            pc = (paid / contract * 100) if contract > 0 else 0
            if pc == 0 or pc <= 25:
                _stats[cy]['0%'] += 1
            elif pc <= 50:
                _stats[cy]['25%'] += 1
            elif pc <= 75:
                _stats[cy]['50%'] += 1
            elif pc < 100:
                _stats[cy]['75%'] += 1
            else:
                _stats[cy]['100%'] += 1
            _stats[cy]['total'] += 1
        payment_stats_by_course = dict(sorted(_stats.items()))
    else:
        payment_total_contract = 0
        payment_total_paid = 0
        payment_stats_by_course = {}

    # today_schedule o'zgaruvchisini barcha rollar uchun yaratish (agar yaratilmagan bo'lsa)
    if 'today_schedule' not in locals():
        today_schedule = []

    # O'qituvchi uchun fanlar ma'lumotlari
    if 'my_subjects_info' not in locals():
        my_subjects_info = {}

    if user.role == 'teacher' or user.has_role('teacher'):
        from app.models import DirectionCurriculum, Direction
        teacher_subjects = TeacherSubject.query.filter_by(teacher_id=user.id).all()
        for ts in teacher_subjects:
            group = Group.query.get(ts.group_id)
            if group and group.direction_id:
                curr_q = DirectionCurriculum.query.filter_by(
                    direction_id=group.direction_id,
                    subject_id=ts.subject_id
                )
                curriculum_item = DirectionCurriculum.filter_by_group_context(curr_q, group).first()
                if curriculum_item and ts.subject_id not in my_subjects_info:
                    course_year = ((curriculum_item.semester - 1) // 2) + 1
                    subject = Subject.query.get(ts.subject_id)
                    
                    # Teacher subjects credits
                    total_hours = (curriculum_item.hours_maruza or 0) + (curriculum_item.hours_amaliyot or 0) + \
                                 (curriculum_item.hours_laboratoriya or 0) + (curriculum_item.hours_seminar or 0) + \
                                 (curriculum_item.hours_mustaqil or 0)
                    
                    if total_hours > 0:
                        credits = total_hours / 30.0
                    else:
                        credits = float(subject.credits) if subject and subject.credits else 0.0
                        
                    info_key = f"{ts.subject_id}_{ts.group_id}"
                    if info_key not in my_subjects_info:
                        my_subjects_info[info_key] = {
                            'semester': curriculum_item.semester,
                            'course_year': course_year,
                            'credits': credits,
                            'direction': Direction.query.get(group.direction_id)
                        }

    # Admin uchun barcha topshiriqlar ro'yxati
    if active_role == 'admin':
        # Barcha topshiriqlarni olish (o'qituvchilar yaratgan)
        all_admin_assignments = Assignment.query.order_by(Assignment.created_at.desc()).all()
        
        # Topshiriqlar ro'yxatini yaratish
        teacher_assignments_list = []
        for assignment in all_admin_assignments:
            # Yangi javoblarni sanash (Submission.score == None)
            pending_query = assignment.submissions.filter(Submission.score == None)
            pending_count = pending_query.count()
            resubmitted_count = pending_query.filter(Submission.resubmission_count > 0).count()
            
            # Yaratuvchi o'qituvchini olish
            creator = User.query.get(assignment.created_by) if assignment.created_by else None
            
            item = {
                'id': assignment.id,
                'title': assignment.title,
                'subject_name': assignment.subject.name if assignment.subject else 'Noma\'lum',
                'group_name': assignment.group.name if assignment.group else None,
                'due_date': assignment.due_date,
                'lesson_type': assignment.lesson_type,
                'pending_count': pending_count,
                'resubmitted_count': resubmitted_count,
                'creator_name': creator.full_name if creator else 'Noma\'lum',
                'created_at': assignment.created_at
            }
            teacher_assignments_list.append(item)
        
        # Pending topshiriqlar ro'yxati (Tekshirilmagan)
        teacher_pending_assignments_list = [a for a in teacher_assignments_list if a['pending_count'] > 0]
        
        # recent_assignments ni admin uchun ham to'ldirish
        if 'recent_assignments' not in locals():
            recent_assignments = all_admin_assignments
    
    # pending_assignments ni boshqa rollar uchun ham yaratish (agar mavjud bo'lmasa)
    if active_role != 'student':
        if 'pending_assignments' not in locals():
            pending_assignments = []
            if 'recent_assignments' in locals() and recent_assignments:
                for assignment in recent_assignments[:5]:
                    pending_assignments.append({
                        'assignment': assignment,
                        'status': 'not_submitted',
                        'submission': None
                    })

    # now o'zgaruvchisini barcha rollar uchun aniqlash (Toshkent vaqti)
    if 'now_dt' not in locals():
        now_dt = get_tashkent_time()

    # To'lov statistikasi (admin, accounting, dean uchun dashboardda) - fakultetlar bo'yicha, har birida kurslar
    payment_total_contract = 0
    payment_total_paid = 0
    payment_stats_by_faculty = []
    if active_role in ('admin', 'accounting', 'dean'):
        from collections import defaultdict
        from app.models import DirectionContractAmount
        faculty_restrict = user.faculty_id if active_role == 'dean' and user.faculty_id else None
        _faculties = Faculty.query.order_by(Faculty.name).all()
        if faculty_restrict:
            _faculties = [f for f in _faculties if f.id == faculty_restrict]
        faculty_group_ids = [g.id for g in Group.query.filter_by(faculty_id=faculty_restrict).all()] if faculty_restrict else None
        _base_q = User.query.filter(User.role == 'student')
        if faculty_restrict and faculty_group_ids:
            _base_q = _base_q.filter(User.group_id.in_(faculty_group_ids))
        _students = _base_q.all()
        payment_total_contract = float(sum(DirectionContractAmount.get_contract_for_student(s) for s in _students))
        _sid_list = [s.id for s in _students]
        payment_total_paid = float(db.session.query(func.sum(StudentPayment.paid_amount)).filter(
            StudentPayment.student_id.in_(_sid_list) if _sid_list else StudentPayment.student_id == -1
        ).scalar() or 0)
        _all_p = StudentPayment.query.all()
        _paid_by_student = defaultdict(float)
        for x in _all_p:
            _paid_by_student[x.student_id] += float(x.paid_amount or 0)
        # faculty_id -> course_year -> stats (barcha talabalar, faqat to'lov yozuvi borlar emas)
        _by_faculty = defaultdict(lambda: defaultdict(lambda: {'0%': 0, '25%': 0, '50%': 0, '75%': 0, '100%': 0, 'total': 0}))
        for s in _students:
            if not s.group or (faculty_restrict and s.group.faculty_id != faculty_restrict):
                continue
            g = s.group
            fid, cy = g.faculty_id, g.course_year
            contract = DirectionContractAmount.get_contract_for_student(s)
            if contract == 0:
                contract = sum(float(x.contract_amount or 0) for x in _all_p if x.student_id == s.id)
            paid = _paid_by_student[s.id]
            pc = (paid / contract * 100) if contract > 0 else 0
            st = _by_faculty[fid][cy]
            if pc == 0 or pc <= 25:
                st['0%'] += 1
            elif pc <= 50:
                st['25%'] += 1
            elif pc <= 75:
                st['50%'] += 1
            elif pc < 100:
                st['75%'] += 1
            else:
                st['100%'] += 1
            st['total'] += 1
        for f in _faculties:
            courses = _by_faculty.get(f.id, {})
            if courses:
                courses_sorted = dict(sorted(courses.items()))
                payment_stats_by_faculty.append({'faculty': f, 'courses': courses_sorted})

    # Admin / Kafedra mudiri dashboardida "Yangi a'zolar" uchun
    if 'recent_users' not in locals():
        recent_users = []
    if active_role in ('admin', 'department_head'):
        all_recent = User.query.order_by(User.created_at.desc()).limit(15).all()
        recent_users = [u for u in all_recent if not getattr(u, 'is_superadmin', False)][:10]

    # Dashboard bloki (admin/edu_dept/department_head) uchun stats bo'sh bo'lmasin
    if active_role in ('admin', 'edu_dept', 'department_head') and not stats:
        stats = {'total_users': 0, 'total_students': 0, 'total_teachers': 0, 'total_staff': 0, 'total_faculties': 0, 'total_subjects': 0, 'total_groups': 0, 'total_departments': 0, 'total_directions': 0}

    try:
        return render_template('dashboard.html', stats=stats, **stats, announcements=announcements,
                             recent_users=recent_users if 'recent_users' in locals() else [],
                             recent_assignments=recent_assignments, upcoming_schedules=upcoming_schedules,
                             my_subjects=my_subjects, today_schedule=today_schedule, my_subjects_info=my_subjects_info,
                             pending_assignments=pending_assignments if 'pending_assignments' in locals() else [],
                             semester_progress=semester_progress if 'semester_progress' in locals() else 0,
                             total_semester_score=total_semester_score if 'total_semester_score' in locals() else 0,
                             total_semester_max_score=total_semester_max_score if 'total_semester_max_score' in locals() else 0,
                             semester_grade=semester_grade if 'semester_grade' in locals() else None,
                             payment_info=payment_info if 'payment_info' in locals() else None,
                             payment_total_contract=payment_total_contract if 'payment_total_contract' in locals() else 0,
                             payment_total_paid=float(payment_total_paid) if 'payment_total_paid' in locals() else 0,
                             payment_stats_by_faculty=payment_stats_by_faculty if 'payment_stats_by_faculty' in locals() else [],
                             upcoming_due_assignments=upcoming_due_assignments if 'upcoming_due_assignments' in locals() else [],
                             greeting=greeting, today=today, role=active_role, direction_id=direction_id,
                             teacher_assignments_list=teacher_assignments_list if 'teacher_assignments_list' in locals() else [],
                             teacher_pending_assignments_list=teacher_pending_assignments_list if 'teacher_pending_assignments_list' in locals() else [],
                             edu_dept_teachers=edu_dept_teachers if 'edu_dept_teachers' in locals() else [],
                             dept_head_teachers=dept_head_teachers if 'dept_head_teachers' in locals() else [],
                             edu_dept_sort_by=edu_dept_sort_by, edu_dept_sort_order=edu_dept_sort_order)
    except Exception as e:
        import traceback
        err_msg = traceback.format_exc()
        current_app.logger.exception("Dashboard render error")
        from flask import Response
        return Response('<pre style="white-space:pre-wrap;font-size:12px;">' + err_msg.replace('<', '&lt;') + '</pre>', status=500, mimetype='text/html')


@bp.route('/fan-resurslari')
@login_required
def fan_resurslari():
    """O'quv bo'limi: to'liq ro'yxat va filtrlar (fan resurslari bo'limi)."""
    from flask import session as flask_session
    active_role = flask_session.get('current_role') or current_user.role
    if active_role not in ('edu_dept', 'admin', 'dean', 'department_head') and not current_user.is_superadmin:
        flash(t('no_permission_for_action'), 'error')
        return redirect(url_for('main.dashboard'))
    try:
        rows = _build_edu_dept_teachers_list()
    except Exception as e:
        current_app.logger.warning("fan_resurslari: %s", e)
        rows = []
    # Kafedralar ro'yxati (filtr uchun)
    from app.models import Department, TeacherDepartment, DepartmentHead
    # Kafedra mudiri uchun faqat o'z kafedrasi
    if active_role == 'department_head' and not current_user.is_superadmin:
        my_dept_ids = [link.department_id for link in DepartmentHead.query.filter_by(user_id=current_user.id).all()]
        if my_dept_ids:
            subject_ids_in_dept = {s.id for s in Subject.query.filter(Subject.department_id.in_(my_dept_ids)).all()}
            rows = [r for r in rows if r.get('subject_id') in subject_ids_in_dept]
        else:
            rows = []
        departments = Department.query.filter(Department.id.in_(my_dept_ids)).order_by(Department.name).all()
    else:
        departments = Department.query.order_by(Department.name).all()
    department_id = request.args.get('department_id', type=int)
    if department_id:
        teacher_ids_in_dept = {td.teacher_id for td in TeacherDepartment.query.filter_by(department_id=department_id).all()}
        rows = [r for r in rows if r.get('teacher_id') in teacher_ids_in_dept]
    # Filtrlar
    progress_filter = request.args.get('progress', '', type=str)  # '', '0', '100', 'not100'
    q = (request.args.get('q', '') or '').strip().lower()  # umumiy qidiruv (o'qituvchi, fan, guruh)
    lesson_type_q = (request.args.get('lesson_type', '') or '').strip().lower()
    if progress_filter == '0':
        rows = [r for r in rows if r.get('progress_percent') == 0]
    elif progress_filter == '100':
        rows = [r for r in rows if r.get('progress_percent') == 100]
    elif progress_filter == 'not100':
        rows = [r for r in rows if r.get('progress_percent', 0) < 100]
    if q:
        rows = [r for r in rows if (
            q in (r.get('teacher_name') or '').lower()
            or q in (r.get('subject_name') or '').lower()
            or q in (r.get('group_name') or '').lower()
            or q in (r.get('direction_name') or '').lower()
        )]
    if lesson_type_q:
        rows = [r for r in rows if (r.get('lesson_type') or '').lower() == lesson_type_q]
    # Tartiblash
    sort_by = request.args.get('sort', 'teacher', type=str)
    sort_order = request.args.get('order', 'asc', type=str)
    if sort_order not in ('asc', 'desc'):
        sort_order = 'asc'
    sort_key_map = {
        'teacher': 'teacher_name', 'department': 'department_names', 'subject': 'subject_name',
        'direction': 'direction_name', 'group': 'group_name',
        'lesson_type': 'lesson_type', 'total_hours': 'total_hours', 'loaded_hours': 'loaded_hours',
        'remaining_hours': 'remaining_hours', 'progress': 'progress_percent',
    }
    sort_key = sort_key_map.get(sort_by, 'teacher_name')
    if sort_key in ('total_hours', 'loaded_hours', 'remaining_hours', 'progress_percent'):
        rows.sort(key=lambda r: (r.get(sort_key) is None, r.get(sort_key) if isinstance(r.get(sort_key), (int, float)) else 0), reverse=(sort_order == 'desc'))
    else:
        rows.sort(key=lambda r: (r.get(sort_key) or '').lower(), reverse=(sort_order == 'desc'))
    # Filter options for dropdowns (unique values from full list)
    try:
        all_rows = _build_edu_dept_teachers_list()
        lesson_types_choices = sorted(set((r.get('lesson_type') or '') for r in all_rows if r.get('lesson_type')))
    except Exception:
        lesson_types_choices = []
    return render_template('fan_resurslari.html',
        rows=rows,
        sort_by=sort_by,
        sort_order=sort_order,
        departments=departments,
        department_id=department_id,
        progress_filter=progress_filter,
        search_q=q,
        lesson_type_q=lesson_type_q,
        lesson_types_choices=lesson_types_choices,
    )


@bp.route('/department-head/my-department')
@login_required
def department_head_my_department():
    """Kafedra mudiri: O'z kafedrasi - fanlar va o'qituvchilar."""
    from flask import session as flask_session
    from app.models import Department, TeacherDepartment, DepartmentHead
    
    active_role = flask_session.get('current_role') or current_user.role
    if active_role != 'department_head' and not current_user.is_superadmin:
        flash(t('no_permission_for_action'), 'error')
        return redirect(url_for('main.dashboard'))
    
    # Foydalanuvchiga biriktirilgan kafedralar
    my_dept_links = DepartmentHead.query.filter_by(user_id=current_user.id).all()
    my_dept_ids = [link.department_id for link in my_dept_links]
    
    if not my_dept_ids:
        flash(t('no_department_assigned'), 'warning')
        return redirect(url_for('main.dashboard'))
    
    # Barcha kafedralar (filtr uchun)
    all_my_departments = Department.query.filter(Department.id.in_(my_dept_ids)).order_by(Department.name).all()
    
    # Tanlangan kafedra (filtr)
    selected_dept_id = request.args.get('department_id', type=int)
    if selected_dept_id and selected_dept_id in my_dept_ids:
        filter_dept_ids = [selected_dept_id]
        selected_department = Department.query.get(selected_dept_id)
    else:
        filter_dept_ids = my_dept_ids
        selected_department = None
    
    _lang = flask_session.get('language', 'uz')
    
    # Fanlar
    subjects_in_dept = Subject.query.filter(Subject.department_id.in_(filter_dept_ids)).order_by(Subject.name).all()
    
    # O'qituvchilar
    teachers_in_dept = User.query.join(TeacherDepartment, User.id == TeacherDepartment.teacher_id).filter(
        TeacherDepartment.department_id.in_(filter_dept_ids)
    ).distinct().order_by(User.full_name).all()
    
    # Qidiruv
    search_q = request.args.get('q', '').strip().lower()
    if search_q:
        subjects_in_dept = [s for s in subjects_in_dept if search_q in (s.get_display_name(_lang) or s.name or '').lower()]
        teachers_in_dept = [t for t in teachers_in_dept if search_q in (t.full_name or t.login or '').lower()]
    
    return render_template('department_head/my_department.html',
        all_departments=all_my_departments,
        selected_department=selected_department,
        selected_dept_id=selected_dept_id,
        subjects=subjects_in_dept,
        teachers=teachers_in_dept,
        search_q=search_q,
        current_lang=_lang,
        show_department_filter=len(all_my_departments) > 1
    )


@bp.route('/department-head/assign')
@login_required
def department_head_assign():
    """Kafedra mudiri: O'qituvchi biriktirish (DirectionCurriculum asosida)."""
    from flask import session as flask_session
    from app.models import Department, TeacherDepartment, DepartmentHead, DirectionCurriculum, Direction
    try:
        active_role = flask_session.get('current_role') or current_user.role
        if active_role != 'department_head' and not current_user.is_superadmin:
            flash(t('no_permission_for_action'), 'error')
            return redirect(url_for('main.dashboard'))
        my_dept_ids = [link.department_id for link in DepartmentHead.query.filter_by(user_id=current_user.id).all()]
        if not my_dept_ids:
            flash(t('no_department_assigned'), 'warning')
            return redirect(url_for('main.dashboard'))
        _lang = flask_session.get('language', 'uz')
        
        # Filter parametrlari
        filter_semester = request.args.get('semester', '', type=str)
        filter_direction = request.args.get('direction_id', '', type=str)
        filter_group = request.args.get('group_id', '', type=str)
        filter_subject = request.args.get('subject_id', '', type=str)
        filter_lesson_type = request.args.get('lesson_type', '', type=str)
        filter_status = request.args.get('status', '', type=str)
        search_q = request.args.get('q', '', type=str).strip()
        
        subject_ids_in_dept = [s.id for s in Subject.query.filter(Subject.department_id.in_(my_dept_ids)).all()]
        teachers_in_dept = User.query.join(TeacherDepartment, User.id == TeacherDepartment.teacher_id).filter(
            TeacherDepartment.department_id.in_(my_dept_ids)
        ).distinct().order_by(User.full_name).all()
        active_groups = Group.query.filter(Group.students.any()).all()
        
        # Filtr uchun tanlovlar
        semesters_set = set()
        directions_dict = {}
        groups_dict = {}
        subjects_dict = {}
        
        rows = []
        if not subject_ids_in_dept:
            return render_template('department_head/assign.html',
                rows=rows,
                teachers=teachers_in_dept,
                current_lang=_lang,
                sort_by='semester',
                sort_order='asc',
                semesters=[],
                directions=[],
                groups=[],
                subjects=[],
                lesson_types_choices=['maruza', 'amaliyot', 'laboratoriya', 'seminar'],
                filter_semester=filter_semester,
                filter_direction=filter_direction,
                filter_group=filter_group,
                filter_subject=filter_subject,
                filter_lesson_type=filter_lesson_type,
                filter_status=filter_status,
                search_q=search_q
            )
        
        seen_combinations = set()
        for group in active_groups:
            if not group.direction_id:
                continue
            curr_query = DirectionCurriculum.query.filter(
                DirectionCurriculum.direction_id == group.direction_id,
                DirectionCurriculum.semester == (group.semester or 1),
                DirectionCurriculum.subject_id.in_(subject_ids_in_dept)
            )
            curr_items = DirectionCurriculum.filter_by_group_context(curr_query, group).all()
            direction = Direction.query.get(group.direction_id)
            if not direction:
                continue
            
            # Filterlar uchun tanlovlarni to'plash
            if group.semester:
                semesters_set.add(group.semester)
            if direction.id not in directions_dict:
                directions_dict[direction.id] = direction.get_display_name(_lang) or direction.name
            if group.id not in groups_dict:
                groups_dict[group.id] = group.name
            
            for item in curr_items:
                if item.subject_id not in subjects_dict and item.subject:
                    subjects_dict[item.subject_id] = item.subject.get_display_name(_lang) or item.subject.name
                
                for lesson_type, hours_field in [('maruza', 'hours_maruza'), ('amaliyot', 'hours_amaliyot'), ('laboratoriya', 'hours_laboratoriya'), ('seminar', 'hours_seminar')]:
                    hours = getattr(item, hours_field, 0) or 0
                    if hours <= 0:
                        continue
                    combo_key = (item.subject_id, group.id, lesson_type)
                    if combo_key in seen_combinations:
                        continue
                    seen_combinations.add(combo_key)
                    
                    lesson_type_map = {
                        'maruza': ['maruza', 'ma\'ruza', 'lecture'],
                        'amaliyot': ['amaliyot', 'laboratoriya', 'kurs_ishi', 'lab', 'practice'],
                        'laboratoriya': ['laboratoriya', 'lab', 'amaliyot'],
                        'seminar': ['seminar'],
                    }
                    lesson_type_variants = lesson_type_map.get(lesson_type, [lesson_type])
                    existing_ts = TeacherSubject.query.filter(
                        TeacherSubject.subject_id == item.subject_id,
                        TeacherSubject.group_id == group.id,
                        func.lower(TeacherSubject.lesson_type).in_([lt.lower() for lt in lesson_type_variants])
                    ).first()
                    
                    teacher_id = existing_ts.teacher_id if existing_ts else None
                    teacher_name = (User.query.get(existing_ts.teacher_id).full_name if existing_ts and existing_ts.teacher_id else '')
                    direction_name = direction.get_display_name(_lang) or direction.name
                    subject_name = item.subject.get_display_name(_lang) or item.subject.name
                    
                    # Filtrlash
                    if filter_semester and str(item.semester) != filter_semester:
                        continue
                    if filter_direction and str(direction.id) != filter_direction:
                        continue
                    if filter_group and str(group.id) != filter_group:
                        continue
                    if filter_subject and str(item.subject_id) != filter_subject:
                        continue
                    if filter_lesson_type and lesson_type.lower() != filter_lesson_type.lower():
                        continue
                    if filter_status == 'assigned' and not teacher_id:
                        continue
                    if filter_status == 'not_assigned' and teacher_id:
                        continue
                    if search_q:
                        search_lower = search_q.lower()
                        if not (search_lower in direction_name.lower() or 
                                search_lower in group.name.lower() or 
                                search_lower in subject_name.lower() or 
                                search_lower in teacher_name.lower()):
                            continue
                    
                    rows.append({
                        'curriculum_id': item.id,
                        'semester': item.semester,
                        'direction_id': direction.id,
                        'direction_name': direction_name,
                        'group_id': group.id,
                        'group_name': group.name,
                        'subject_id': item.subject_id,
                        'subject_name': subject_name,
                        'lesson_type': lesson_type,
                        'hours': hours,
                        'teacher_id': teacher_id,
                        'teacher_name': teacher_name,
                        'teacher_subject_id': existing_ts.id if existing_ts else None,
                    })
        
        # Sorting
        sort_by = request.args.get('sort', 'semester', type=str)
        sort_order = request.args.get('order', 'asc', type=str)
        sort_keys = {
            'semester': lambda r: r.get('semester', 0),
            'direction': lambda r: (r.get('direction_name') or '').lower(),
            'group': lambda r: (r.get('group_name') or '').lower(),
            'subject': lambda r: (r.get('subject_name') or '').lower(),
            'lesson_type': lambda r: (r.get('lesson_type') or '').lower(),
            'hours': lambda r: r.get('hours', 0),
            'teacher': lambda r: (r.get('teacher_name') or '').lower(),
        }
        key_fn = sort_keys.get(sort_by, sort_keys['semester'])
        rows = sorted(rows, key=key_fn, reverse=(sort_order == 'desc'))
        
        # Tanlovlar ro'yxatini tayyorlash
        semesters_list = sorted(list(semesters_set))
        directions_list = sorted(directions_dict.items(), key=lambda x: x[1].lower())
        groups_list = sorted(groups_dict.items(), key=lambda x: x[1].lower())
        subjects_list = sorted(subjects_dict.items(), key=lambda x: x[1].lower())
        
        return render_template('department_head/assign.html',
            rows=rows,
            teachers=teachers_in_dept,
            current_lang=_lang,
            sort_by=sort_by,
            sort_order=sort_order,
            semesters=semesters_list,
            directions=directions_list,
            groups=groups_list,
            subjects=subjects_list,
            lesson_types_choices=['maruza', 'amaliyot', 'laboratoriya', 'seminar'],
            filter_semester=filter_semester,
            filter_direction=filter_direction,
            filter_group=filter_group,
            filter_subject=filter_subject,
            filter_lesson_type=filter_lesson_type,
            filter_status=filter_status,
            search_q=search_q
        )
    except Exception as e:
        current_app.logger.error("department_head_assign error: %s", str(e))
        import traceback
        current_app.logger.error(traceback.format_exc())
        flash(f"Xatolik: {str(e)}", 'error')
        return redirect(url_for('main.dashboard'))


@bp.route('/department-head/assign/save', methods=['POST'])
@login_required
def department_head_assign_save():
    """Kafedra mudiri: O'qituvchi saqlash."""
    from flask import session as flask_session
    from app.models import DepartmentHead, TeacherDepartment
    active_role = flask_session.get('current_role') or current_user.role
    if active_role != 'department_head' and not current_user.is_superadmin:
        flash(t('no_permission_for_action'), 'error')
        return redirect(url_for('main.dashboard'))
    my_dept_ids = [link.department_id for link in DepartmentHead.query.filter_by(user_id=current_user.id).all()]
    if not my_dept_ids:
        flash(t('no_department_assigned'), 'warning')
        return redirect(url_for('main.dashboard'))
    subject_id = request.form.get('subject_id', type=int)
    group_id = request.form.get('group_id', type=int)
    lesson_type = request.form.get('lesson_type', '').strip()
    teacher_id = request.form.get('teacher_id', type=int)
    if not all([subject_id, group_id, lesson_type]):
        flash(t('fill_all_fields'), 'error')
        return redirect(url_for('main.department_head_assign'))
    subject = Subject.query.get(subject_id)
    if not subject or subject.department_id not in my_dept_ids:
        flash(t('no_permission_for_action'), 'error')
        return redirect(url_for('main.department_head_assign'))
    existing_ts = TeacherSubject.query.filter_by(
        subject_id=subject_id, group_id=group_id, lesson_type=lesson_type
    ).first()
    if teacher_id:
        if existing_ts:
            existing_ts.teacher_id = teacher_id
        else:
            ts = TeacherSubject(subject_id=subject_id, group_id=group_id, lesson_type=lesson_type, teacher_id=teacher_id)
            db.session.add(ts)
    else:
        if existing_ts:
            db.session.delete(existing_ts)
    db.session.commit()
    flash(t('teacher_assigned_successfully'), 'success')
    return redirect(url_for('main.department_head_assign'))


@bp.route('/department-head/subjects')
@login_required
def department_head_subjects():
    """Kafedra mudiri: Fanlar bazasi (o'z kafedrasi uchun)."""
    from flask import session as flask_session
    from app.models import Department, TeacherDepartment, DepartmentHead, TeacherSubject
    active_role = flask_session.get('current_role') or current_user.role
    if active_role != 'department_head' and not current_user.is_superadmin:
        flash(t('no_permission_for_action'), 'error')
        return redirect(url_for('main.dashboard'))
    my_dept_ids = [link.department_id for link in DepartmentHead.query.filter_by(user_id=current_user.id).all()]
    if not my_dept_ids:
        flash(t('no_department_assigned'), 'warning')
        return redirect(url_for('main.dashboard'))
    departments = Department.query.filter(Department.id.in_(my_dept_ids)).order_by(Department.name).all()
    _lang = flask_session.get('language', 'uz')
    subjects_in_dept = Subject.query.filter(Subject.department_id.in_(my_dept_ids)).order_by(Subject.name).all()
    teachers_in_dept = User.query.join(TeacherDepartment, User.id == TeacherDepartment.teacher_id).filter(
        TeacherDepartment.department_id.in_(my_dept_ids)
    ).distinct().order_by(User.full_name).all()
    groups_list = Group.query.join(TeacherSubject, Group.id == TeacherSubject.group_id).filter(
        TeacherSubject.subject_id.in_([s.id for s in subjects_in_dept])
    ).distinct().order_by(Group.name).all()
    return render_template('department_head/subjects.html',
        departments=departments,
        subjects=subjects_in_dept,
        teachers=teachers_in_dept,
        groups=groups_list,
        current_lang=_lang
    )


def _build_department_head_resources_list(dept_ids):
    """Kafedra mudiri uchun fan resurslari ro'yxati."""
    from app.models import DirectionCurriculum, Lesson, TeacherDepartment, Department, Direction
    from flask import session as flask_session
    _lang = flask_session.get('language', 'uz')
    lesson_type_to_hours = {
        'maruza': lambda c: (c.hours_maruza or 0),
        'amaliyot': lambda c: (c.hours_amaliyot or 0) + (c.hours_laboratoriya or 0) + (c.hours_kurs_ishi or 0),
        'laboratoriya': lambda c: (c.hours_laboratoriya or 0),
        'seminar': lambda c: (c.hours_seminar or 0),
        'kurs_ishi': lambda c: (c.hours_kurs_ishi or 0),
    }
    result = []
    teacher_ids_in_dept = {td.teacher_id for td in TeacherDepartment.query.filter(TeacherDepartment.department_id.in_(dept_ids)).all()}
    subject_ids_in_dept = {s.id for s in Subject.query.filter(Subject.department_id.in_(dept_ids)).all()}
    for ts in TeacherSubject.query.join(Group, TeacherSubject.group_id == Group.id).filter(Group.students.any()).order_by(TeacherSubject.teacher_id, TeacherSubject.subject_id).all():
        if ts.teacher_id not in teacher_ids_in_dept and ts.subject_id not in subject_ids_in_dept:
            continue
        group = Group.query.get(ts.group_id)
        if not group or not group.direction_id:
            continue
        teacher = User.query.get(ts.teacher_id)
        subject = Subject.query.get(ts.subject_id)
        if not teacher or not subject:
            continue
        curr_q = DirectionCurriculum.query.filter_by(
            direction_id=group.direction_id,
            subject_id=ts.subject_id,
            semester=group.semester or 1
        )
        curriculum_item = DirectionCurriculum.filter_by_group_context(curr_q, group).first()
        if not curriculum_item:
            continue
        get_hours = lesson_type_to_hours.get((ts.lesson_type or '').lower()) or (lambda c: 0)
        total_hours = get_hours(curriculum_item)
        if total_hours <= 0:
            continue
        search_lesson_types = [ts.lesson_type] if ts.lesson_type else []
        if (ts.lesson_type or '').lower() == 'amaliyot':
            search_lesson_types = ['amaliyot', 'laboratoriya', 'kurs_ishi']
        created_count = Lesson.query.filter(
            Lesson.subject_id == subject.id,
            Lesson.created_by == teacher.id,
            Lesson.lesson_type.in_(search_lesson_types),
            ((Lesson.group_id == group.id) | (Lesson.group_id.is_(None) & (Lesson.direction_id == group.direction_id)))
        ).count()
        loaded_hours = created_count * 2
        remaining_hours = max(0, total_hours - loaded_hours)
        progress_pct = min(100, int((loaded_hours / total_hours) * 100)) if total_hours else 0
        direction = group.direction if hasattr(group, 'direction') and group.direction else None
        dept = Department.query.get(subject.department_id) if subject.department_id else None
        result.append({
            'teacher_subject_id': ts.id,
            'teacher_id': teacher.id,
            'teacher_name': teacher.full_name or teacher.login or '',
            'department_name': (dept.get_display_name(_lang) or dept.name) if dept else '',
            'direction_name': (direction.get_display_name(_lang) or direction.name) if direction else '',
            'group_name': group.name,
            'subject_name': subject.get_display_name(_lang) or subject.name,
            'lesson_type': ts.lesson_type or '-',
            'total_hours': total_hours,
            'loaded_hours': loaded_hours,
            'remaining_hours': remaining_hours,
            'progress_percent': progress_pct,
        })
    return result


@bp.route('/department-head/resources')
@login_required
def department_head_resources():
    """Kafedra mudiri: Fan resurslari (o'z kafedrasi uchun)."""
    from flask import session as flask_session
    from app.models import Department, DepartmentHead
    active_role = flask_session.get('current_role') or current_user.role
    if active_role != 'department_head' and not current_user.is_superadmin:
        flash(t('no_permission_for_action'), 'error')
        return redirect(url_for('main.dashboard'))
    my_dept_ids = [link.department_id for link in DepartmentHead.query.filter_by(user_id=current_user.id).all()]
    if not my_dept_ids:
        flash(t('no_department_assigned'), 'warning')
        return redirect(url_for('main.dashboard'))
    departments = Department.query.filter(Department.id.in_(my_dept_ids)).order_by(Department.name).all()
    _lang = flask_session.get('language', 'uz')
    try:
        rows = _build_department_head_resources_list(my_dept_ids)
    except Exception as e:
        current_app.logger.warning("department_head_resources: %s", e)
        rows = []
    q = (request.args.get('q', '') or '').strip().lower()
    lesson_type_q = (request.args.get('lesson_type', '') or '').strip().lower()
    progress_filter = request.args.get('progress', '', type=str)
    if q:
        rows = [r for r in rows if (
            q in (r.get('teacher_name') or '').lower()
            or q in (r.get('subject_name') or '').lower()
            or q in (r.get('group_name') or '').lower()
            or q in (r.get('direction_name') or '').lower()
        )]
    if lesson_type_q:
        rows = [r for r in rows if (r.get('lesson_type') or '').lower() == lesson_type_q]
    if progress_filter == '0':
        rows = [r for r in rows if r.get('progress_percent') == 0]
    elif progress_filter == '100':
        rows = [r for r in rows if r.get('progress_percent') == 100]
    elif progress_filter == 'not100':
        rows = [r for r in rows if r.get('progress_percent', 0) < 100]
    sort_by = request.args.get('sort', 'teacher', type=str)
    sort_order = request.args.get('order', 'asc', type=str)
    sort_key_map = {
        'department': 'department_name', 'direction': 'direction_name', 'group': 'group_name',
        'subject': 'subject_name', 'lesson_type': 'lesson_type', 'total_hours': 'total_hours',
        'teacher': 'teacher_name', 'progress': 'progress_percent',
    }
    sort_key = sort_key_map.get(sort_by, 'teacher_name')
    if sort_key in ('total_hours', 'progress_percent'):
        rows.sort(key=lambda r: (r.get(sort_key) is None, r.get(sort_key) if isinstance(r.get(sort_key), (int, float)) else 0), reverse=(sort_order == 'desc'))
    else:
        rows.sort(key=lambda r: (r.get(sort_key) or '').lower(), reverse=(sort_order == 'desc'))
    lesson_types_choices = sorted(set((r.get('lesson_type') or '') for r in rows if r.get('lesson_type')))
    return render_template('department_head/resources.html',
        rows=rows,
        departments=departments,
        sort_by=sort_by,
        sort_order=sort_order,
        search_q=q,
        lesson_type_q=lesson_type_q,
        progress_filter=progress_filter,
        lesson_types_choices=lesson_types_choices,
        current_lang=_lang
    )


@bp.route('/department-head/assign-teacher', methods=['POST'])
@login_required
def department_head_assign_teacher():
    """Kafedra mudiri: O'qituvchi biriktirish."""
    from flask import session as flask_session
    from app.models import DepartmentHead, TeacherDepartment
    active_role = flask_session.get('current_role') or current_user.role
    if active_role != 'department_head' and not current_user.is_superadmin:
        flash(t('no_permission_for_action'), 'error')
        return redirect(url_for('main.dashboard'))
    my_dept_ids = [link.department_id for link in DepartmentHead.query.filter_by(user_id=current_user.id).all()]
    if not my_dept_ids:
        flash(t('no_department_assigned'), 'warning')
        return redirect(url_for('main.dashboard'))
    subject_id = request.form.get('subject_id', type=int)
    teacher_id = request.form.get('teacher_id', type=int)
    group_id = request.form.get('group_id', type=int)
    lesson_type = request.form.get('lesson_type', '').strip()
    if not all([subject_id, teacher_id, group_id, lesson_type]):
        flash(t('fill_all_fields'), 'error')
        return redirect(url_for('main.department_head_subjects'))
    subject = Subject.query.get(subject_id)
    if not subject or subject.department_id not in my_dept_ids:
        flash(t('no_permission_for_action'), 'error')
        return redirect(url_for('main.department_head_subjects'))
    existing = TeacherSubject.query.filter_by(
        subject_id=subject_id, teacher_id=teacher_id, group_id=group_id, lesson_type=lesson_type
    ).first()
    if existing:
        flash(t('assignment_already_exists'), 'warning')
        return redirect(url_for('main.department_head_subjects'))
    ts = TeacherSubject(
        subject_id=subject_id,
        teacher_id=teacher_id,
        group_id=group_id,
        lesson_type=lesson_type
    )
    db.session.add(ts)
    db.session.commit()
    flash(t('teacher_assigned_successfully'), 'success')
    return redirect(url_for('main.department_head_subjects'))


@bp.route('/department-head/change-teacher', methods=['POST'])
@login_required
def department_head_change_teacher():
    """Kafedra mudiri: O'qituvchi almashtirish."""
    from flask import session as flask_session
    from app.models import DepartmentHead, TeacherDepartment
    active_role = flask_session.get('current_role') or current_user.role
    if active_role != 'department_head' and not current_user.is_superadmin:
        flash(t('no_permission_for_action'), 'error')
        return redirect(url_for('main.dashboard'))
    my_dept_ids = [link.department_id for link in DepartmentHead.query.filter_by(user_id=current_user.id).all()]
    if not my_dept_ids:
        flash(t('no_department_assigned'), 'warning')
        return redirect(url_for('main.dashboard'))
    ts_id = request.form.get('teacher_subject_id', type=int)
    new_teacher_id = request.form.get('new_teacher_id', type=int)
    if not ts_id or not new_teacher_id:
        flash(t('fill_all_fields'), 'error')
        return redirect(url_for('main.department_head_resources'))
    ts = TeacherSubject.query.get(ts_id)
    if not ts:
        flash(t('assignment_not_found'), 'error')
        return redirect(url_for('main.department_head_resources'))
    subject = Subject.query.get(ts.subject_id)
    teacher_in_dept = TeacherDepartment.query.filter(
        TeacherDepartment.teacher_id == ts.teacher_id,
        TeacherDepartment.department_id.in_(my_dept_ids)
    ).first()
    subject_in_dept = subject and subject.department_id in my_dept_ids
    if not teacher_in_dept and not subject_in_dept:
        flash(t('no_permission_for_action'), 'error')
        return redirect(url_for('main.department_head_resources'))
    ts.teacher_id = new_teacher_id
    db.session.commit()
    flash(t('teacher_changed_successfully'), 'success')
    return redirect(url_for('main.department_head_resources'))


def _get_fan_resurslari_filtered_rows():
    """Fan resurslari sahifasidagi kabi filtrlangan va tartiblangan qatorlarni qaytaradi (export uchun)."""
    try:
        rows = _build_edu_dept_teachers_list()
    except Exception as e:
        current_app.logger.warning("fan_resurslari_export: %s", e)
        return []
    from app.models import Department, TeacherDepartment
    department_id = request.args.get('department_id', type=int)
    if department_id:
        teacher_ids_in_dept = {td.teacher_id for td in TeacherDepartment.query.filter_by(department_id=department_id).all()}
        rows = [r for r in rows if r.get('teacher_id') in teacher_ids_in_dept]
    progress_filter = request.args.get('progress', '', type=str)
    q = (request.args.get('q', '') or '').strip().lower()
    lesson_type_q = (request.args.get('lesson_type', '') or '').strip().lower()
    if progress_filter == '0':
        rows = [r for r in rows if r.get('progress_percent') == 0]
    elif progress_filter == '100':
        rows = [r for r in rows if r.get('progress_percent') == 100]
    elif progress_filter == 'not100':
        rows = [r for r in rows if r.get('progress_percent', 0) < 100]
    if q:
        rows = [r for r in rows if (
            q in (r.get('teacher_name') or '').lower()
            or q in (r.get('subject_name') or '').lower()
            or q in (r.get('group_name') or '').lower()
            or q in (r.get('direction_name') or '').lower()
        )]
    if lesson_type_q:
        rows = [r for r in rows if (r.get('lesson_type') or '').lower() == lesson_type_q]
    sort_by = request.args.get('sort', 'teacher', type=str)
    sort_order = request.args.get('order', 'asc', type=str)
    if sort_order not in ('asc', 'desc'):
        sort_order = 'asc'
    sort_key_map = {
        'teacher': 'teacher_name', 'department': 'department_names', 'subject': 'subject_name',
        'direction': 'direction_name', 'group': 'group_name',
        'lesson_type': 'lesson_type', 'total_hours': 'total_hours', 'loaded_hours': 'loaded_hours',
        'remaining_hours': 'remaining_hours', 'progress': 'progress_percent',
    }
    sort_key = sort_key_map.get(sort_by, 'teacher_name')
    if sort_key in ('total_hours', 'loaded_hours', 'remaining_hours', 'progress_percent'):
        rows.sort(key=lambda r: (r.get(sort_key) is None, r.get(sort_key) if isinstance(r.get(sort_key), (int, float)) else 0), reverse=(sort_order == 'desc'))
    else:
        rows.sort(key=lambda r: (r.get(sort_key) or '').lower(), reverse=(sort_order == 'desc'))
    return rows


@bp.route('/fan-resurslari/export')
@login_required
def fan_resurslari_export():
    """Fan resurslari ro'yxatini Excel formatida eksport qilish (joriy filtrlarga muvofiq)."""
    from flask import session as flask_session
    from flask import Response
    from app.utils.excel_export import create_fan_resurslari_excel
    active_role = flask_session.get('current_role') or current_user.role
    if active_role not in ('edu_dept', 'admin', 'dean', 'department_head') and not current_user.is_superadmin:
        flash(t('no_permission_for_action'), 'error')
        return redirect(url_for('main.dashboard'))
    try:
        rows = _get_fan_resurslari_filtered_rows()
        output = create_fan_resurslari_excel(rows, t)
        filename = 'fan_resurslari_{}.xlsx'.format(datetime.now().strftime('%Y-%m-%d_%H-%M'))
        return Response(
            output.getvalue(),
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            headers={'Content-Disposition': 'attachment; filename="%s"' % filename},
        )
    except ImportError as e:
        flash(t('openpyxl_not_installed'), 'error')
        return redirect(url_for('main.fan_resurslari'))


@bp.route('/library')
@login_required
def library():
    """Elektron kutubxona — unilibrary.uz tizim ichida"""
    return render_template('library.html')

@bp.route('/announcements')
@login_required
def announcements():
    """E'lonlar sahifasi"""
    user = current_user
    page = request.args.get('page', 1, type=int)
    
    # Foydalanuvchi roliga qarab e'lonlarni filtrlash
    query = Announcement.query
    
    # Admin barcha e'lonlarni ko'radi
    if user.has_role('admin'):
        # Admin uchun filtrlash yo'q, barcha e'lonlar
        pass
    elif user.role == 'student':
        query = query.filter(
            (Announcement.target_roles.contains('student')) |
            (Announcement.target_roles == None)
        )
    elif user.role == 'teacher':
        query = query.filter(
            (Announcement.target_roles.contains('teacher')) |
            (Announcement.target_roles == None)
        )
    elif user.role == 'dean':
        if user.faculty_id:
            query = query.filter(
                ((Announcement.target_roles.contains('dean')) | (Announcement.target_roles == None)),
                (Announcement.faculty_id == user.faculty_id) | (Announcement.faculty_id == None)
            )
    
    announcements = query.order_by(Announcement.created_at.desc()).paginate(
        page=page,
        per_page=50,
        error_out=False
    )
    
    return render_template('announcements.html', announcements=announcements)

@bp.route('/announcements/create', methods=['GET', 'POST'])
@login_required
def create_announcement():
    """Yangi e'lon yaratish"""
    if not current_user.has_permission('create_announcement'):
        flash(t('no_permission_to_create_announcement'), 'error')
        return redirect(url_for('main.announcements'))
    
    if request.method == 'POST':
        title = request.form.get('title')
        content = request.form.get('content')
        target_roles = request.form.getlist('target_roles')
        is_important = request.form.get('is_important') == 'on'
        
        if not title or not content:
            flash(t('title_and_text_required'), 'error')
            return render_template('create_announcement.html')
        
        # Target roles ni string sifatida saqlash
        target_roles_str = ','.join(target_roles) if target_roles else None
        
        # Joriy rolni olish (session'dan yoki asosiy roldan)
        current_role = session.get('current_role', current_user.role)
        
        announcement = Announcement(
            title=title,
            content=content,
            target_roles=target_roles_str,
            is_important=is_important,
            author_id=current_user.id,
            author_role=current_role,  # E'lon yaratilganda tanlangan rol
            faculty_id=current_user.faculty_id if current_role == 'dean' else None
        )
        
        db.session.add(announcement)
        db.session.commit()
        
        flash(t('announcement_created'), 'success')
        return redirect(url_for('main.announcements'))
    
    return render_template('create_announcement.html')

@bp.route('/announcements/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit_announcement(id):
    """E'lonni tahrirlash"""
    announcement = Announcement.query.get_or_404(id)
    
    # Joriy rolni olish (session'dan yoki asosiy roldan)
    current_role = session.get('current_role', current_user.role)
    
    # Ruxsat: admin roli tanlangan bo'lsa barcha e'lonlarni; aks holda faqat shu rolda o'zi yaratganini
    is_admin_with_admin_role = current_user.has_role('admin') and current_role == 'admin'
    is_own_created_in_current_role = (announcement.author_id == current_user.id and
                                      (announcement.author_role == current_role or announcement.author_role is None))
    if not is_admin_with_admin_role and not is_own_created_in_current_role:
        flash(t('no_permission_to_edit_announcement'), 'error')
        return redirect(url_for('main.announcements'))
    
    if request.method == 'POST':
        title = request.form.get('title')
        content = request.form.get('content')
        target_roles = request.form.getlist('target_roles')
        is_important = request.form.get('is_important') == 'on'
        
        if not title or not content:
            flash(t('title_and_text_required'), 'error')
            return render_template('edit_announcement.html', announcement=announcement)
        
        # Target roles ni string sifatida saqlash
        target_roles_str = ','.join(target_roles) if target_roles else None
        
        announcement.title = title
        announcement.content = content
        announcement.target_roles = target_roles_str
        announcement.is_important = is_important
        
        db.session.commit()
        
        flash(t('announcement_updated'), 'success')
        return redirect(url_for('main.announcements'))
    
    return render_template('edit_announcement.html', announcement=announcement)

@bp.route('/announcements/<int:id>/delete', methods=['POST'])
@login_required
def delete_announcement(id):
    """E'lonni o'chirish"""
    announcement = Announcement.query.get_or_404(id)
    
    # Joriy rolni olish (session'dan yoki asosiy roldan)
    current_role = session.get('current_role', current_user.role)
    
    # Ruxsat: admin roli tanlangan bo'lsa barcha e'lonlarni; aks holda faqat shu rolda o'zi yaratganini
    is_admin_with_admin_role = current_user.has_role('admin') and current_role == 'admin'
    is_own_created_in_current_role = (announcement.author_id == current_user.id and
                                      (announcement.author_role == current_role or announcement.author_role is None))
    if not is_admin_with_admin_role and not is_own_created_in_current_role:
        flash(t('no_permission_to_delete_announcement'), 'error')
        return redirect(url_for('main.announcements'))
    
    try:
        db.session.delete(announcement)
        db.session.commit()
        flash(t('announcement_deleted'), 'success')
    except Exception as e:
        db.session.rollback()
        flash(t('announcement_delete_error', error=str(e)), 'error')
    
    return redirect(url_for('main.announcements'))

@bp.route('/announcements/delete-all', methods=['POST'])
@login_required
def delete_all_announcements():
    """Barcha e'lonlarni o'chirish (faqat admin roli tanlangan bo'lsa)"""
    # Joriy rolni olish (session'dan yoki asosiy roldan)
    current_role = session.get('current_role', current_user.role)
    
    # Admin faqat admin roli tanlangan bo'lsa barcha e'lonlarni o'chira oladi
    is_admin_with_admin_role = current_user.has_role('admin') and current_role == 'admin'
    
    if not is_admin_with_admin_role:
        flash(t('no_permission_to_delete_all_announcements'), 'error')
        return redirect(url_for('main.announcements'))
    
    try:
        # Barcha e'lonlarni olish va o'chirish
        all_announcements = Announcement.query.all()
        count = len(all_announcements)
        
        for announcement in all_announcements:
            db.session.delete(announcement)
        
        db.session.commit()
        flash(t('all_announcements_deleted', count=count), 'success')
    except Exception as e:
        db.session.rollback()
        flash(t('announcements_delete_error', error=str(e)), 'error')
    
    return redirect(url_for('main.announcements'))

@bp.route('/messages')
@login_required
def messages():
    """Xabarlar sahifasi"""
    user = current_user
    
    # Barcha xabarlarni olish (yuborilgan va qabul qilingan)
    all_messages = Message.query.filter(
        (Message.sender_id == user.id) | (Message.receiver_id == user.id)
    ).order_by(Message.created_at.desc()).all()
    
    # Suhbatlar ro'yxatini yaratish (har bir foydalanuvchi bilan alohida suhbat)
    chats_dict = {}
    for msg in all_messages:
        # Qaysi foydalanuvchi bilan suhbat
        other_user_id = msg.receiver_id if msg.sender_id == user.id else msg.sender_id
        other_user = User.query.get(other_user_id)
        
        if other_user and other_user_id not in chats_dict:
            chats_dict[other_user_id] = {
                'user': other_user,
                'last_message': msg,
                'unread_count': 0
            }
        elif other_user and other_user_id in chats_dict:
            # Agar bu xabar keyinroq bo'lsa, last_message ni yangilash
            if msg.created_at > chats_dict[other_user_id]['last_message'].created_at:
                chats_dict[other_user_id]['last_message'] = msg
        
        # O'qilmagan xabarlarni hisoblash
        if msg.receiver_id == user.id and not msg.is_read:
            chats_dict[other_user_id]['unread_count'] += 1
    
    # Chats ro'yxatini yaratish
    chats = list(chats_dict.values())
    chats.sort(key=lambda x: x['last_message'].created_at, reverse=True)
    
    # Mavjud foydalanuvchilar (suhbat boshlash uchun)
    if user.role == 'student':
        if not user.group_id:
            # Guruhsiz talaba faqat admin va accounting bilan suhbat boshlashi mumkin
            admin_accounting_ids = [r.user_id for r in UserRole.query.filter(UserRole.role.in_(['admin', 'accounting'])).all()]
            filters = [User.role.in_(['admin', 'accounting'])]
            if admin_accounting_ids:
                filters.append(User.id.in_(admin_accounting_ids))
            all_users = User.query.filter(
                User.id != user.id,
                User.is_active == True,
                or_(*filters)
            ).distinct().all()
        else:
            # Talaba uchun: o'z guruhi, dars beradigan o'qituvchilari va O'Z dekani + admin/accounting
            faculty_id = user.group.faculty_id if user.group else None
            teacher_ids = [ts.teacher_id for ts in TeacherSubject.query.filter_by(group_id=user.group_id).all()]
            
            filters = [
                User.group_id == user.group_id, # O'z guruhi
                User.id.in_(teacher_ids),       # O'z o'qituvchilari
                User.role.in_(['admin', 'accounting']) # Ma'muriyat
            ]
            if faculty_id:
                filters.append((User.role == 'dean') & (User.faculty_id == faculty_id))
            
            all_users = User.query.filter(
                User.id != user.id,
                User.is_active == True,
                or_(*filters)
            ).all()
    elif user.role == 'teacher':
        # O'qituvchi uchun: dars beradigan guruhlari va hamkasblari/ma'muriyat
        group_ids = [ts.group_id for ts in TeacherSubject.query.filter_by(teacher_id=user.id).all()]
        
        all_users = User.query.filter(
            User.id != user.id,
            User.is_active == True,
            or_(
                User.group_id.in_(group_ids),
                User.role.in_(['teacher', 'dean', 'admin', 'accounting'])
            )
        ).all()
    else:
        # Admin va dekan hammani ko'ra oladi
        all_users = User.query.filter(User.id != user.id, User.is_active == True).all()
        
    # Barcha foydalanuvchilar (suhbat qilinganlar ham qidiruvda chiqishi kerak) — superadmin ko'rsatilmasin
    available_users = [u for u in all_users if not getattr(u, 'is_superadmin', False)]
    
    return render_template('messages.html', chats=chats, available_users=available_users)

@bp.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    """Profil sozlamalari"""
    if request.method == 'POST':
        user = current_user

        # Superadmin o'z profilida barcha ma'lumotlarni tahrirlashi mumkin
        if getattr(user, 'is_superadmin', False):
            full_name = (request.form.get('full_name') or '').strip().upper()
            if full_name:
                user.full_name = full_name
            new_login = request.form.get('login', '').strip()
            if new_login and new_login != (user.login or ''):
                existing = User.query.filter_by(login=new_login).first()
                if existing and existing.id != user.id:
                    flash(t('login_used_by_another_user'), 'error')
                    return render_template('settings.html')
                user.login = new_login or None
            user.passport_number = request.form.get('passport_number', '').strip() or None
            user.pinfl = request.form.get('pinfl', '').strip() or None
            bd_raw = request.form.get('birth_date', '').strip()
            if bd_raw:
                try:
                    user.birth_date = datetime.strptime(bd_raw, '%Y-%m-%d').date()
                except ValueError:
                    pass
            elif bd_raw == '':
                user.birth_date = None

        # Ma'lumotlarni yangilash (barcha foydalanuvchilar)
        user.phone = request.form.get('phone', user.phone)

        # Emailni o'zgartirish (xodimlar va talabalar uchun)
        new_email = request.form.get('email', '').strip()
        if new_email and new_email != user.email:
            existing_user = User.query.filter_by(email=new_email).first()
            if existing_user and existing_user.id != user.id:
                flash(t('email_used_by_another_user'), 'error')
                return render_template('settings.html')
            user.email = new_email if new_email else None

        # Parolni o'zgartirish
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')

        if new_password:
            if new_password == confirm_password:
                if len(new_password) >= 8:
                    user.set_password(new_password)
                    flash(t('password_changed_success_short'), 'success')
                else:
                    flash(t('password_min_length_8'), 'error')
                    return render_template('settings.html')
            else:
                flash(t('new_passwords_do_not_match'), 'error')
                return render_template('settings.html')

        db.session.commit()
        flash(t('profile_updated'), 'success')
        return redirect(url_for('main.settings'))

    return render_template('settings.html')

@bp.route('/chat/<int:user_id>', methods=['GET', 'POST'])
@login_required
def chat(user_id):
    """Foydalanuvchi bilan suhbat"""
    other_user = User.query.get_or_404(user_id)
    user = current_user
    
    # Ruxsatni tekshirish
    allowed = False
    if user.role in ['admin', 'dean']:
        allowed = True
    elif user.role == 'student':
        if not user.group_id:
            # Guruhsiz talaba faqat admin va accounting bilan suhbatlashishi mumkin
            allowed = other_user.role in ['admin', 'accounting']
        elif other_user.group_id == user.group_id and other_user.role == 'student':
            allowed = True
        elif other_user.role == 'teacher':
            is_teacher = TeacherSubject.query.filter_by(teacher_id=other_user.id, group_id=user.group_id).first()
            if is_teacher:
                allowed = True
        elif other_user.role == 'dean':
            if user.group and user.group.faculty_id == other_user.faculty_id:
                allowed = True
        elif other_user.role in ['admin', 'accounting']:
            allowed = True
    elif user.role == 'teacher':
        if other_user.role == 'student':
            is_my_student = TeacherSubject.query.filter_by(teacher_id=user.id, group_id=other_user.group_id).first()
            if is_my_student:
                allowed = True
        elif other_user.role in ['teacher', 'dean', 'admin', 'accounting']:
            allowed = True
            
    if not allowed and user.id != other_user.id:
        flash(t('no_permission_to_chat'), 'error')
        return redirect(url_for('main.messages'))
    
    # Xabar yuborish
    if request.method == 'POST':
        content = request.form.get('content', '').strip()
        if content:
            message = Message(
                sender_id=current_user.id,
                receiver_id=user_id,
                content=content
            )
            db.session.add(message)
            db.session.commit()
            flash(t('message_sent'), 'success')
            return redirect(url_for('main.chat', user_id=user_id))
        else:
            flash(t('message_cannot_be_empty'), 'error')
    
    # Ikki foydalanuvchi o'rtasidagi barcha xabarlar
    messages = Message.query.filter(
        ((Message.sender_id == current_user.id) & (Message.receiver_id == user_id)) |
        ((Message.sender_id == user_id) & (Message.receiver_id == current_user.id))
    ).order_by(Message.created_at.asc()).all()
    
    # Xabarlarni o'qilgan deb belgilash
    Message.query.filter_by(sender_id=user_id, receiver_id=current_user.id, is_read=False).update({'is_read': True})
    db.session.commit()
    
    return render_template('chat.html', other_user=other_user, messages=messages)


@bp.route('/api/chat/<int:user_id>/messages')
@login_required
def chat_messages_api(user_id):
    """Chat uchun yangi xabarlarni JSON qilib qaytaradi (polling). ?after_id=123 – shu id dan keyingi xabarlar."""
    after_id = request.args.get('after_id', type=int)
    if not after_id:
        return jsonify({'messages': []})
    messages = Message.query.filter(
        ((Message.sender_id == current_user.id) & (Message.receiver_id == user_id)) |
        ((Message.sender_id == user_id) & (Message.receiver_id == current_user.id)),
        Message.id > after_id
    ).order_by(Message.created_at.asc()).all()
    # O'qilgan deb belgilash
    Message.query.filter_by(sender_id=user_id, receiver_id=current_user.id, is_read=False).update({'is_read': True})
    db.session.commit()
    out = [{
        'id': m.id,
        'sender_id': m.sender_id,
        'content': m.content,
        'created_at': m.created_at.strftime('%H:%M'),
        'is_mine': m.sender_id == current_user.id
    } for m in messages]
    return jsonify({'messages': out})


@bp.route('/schedule')
@login_required
def schedule():
    """Dars jadvali sahifasi (talaba va o'qituvchilar uchun)"""
    from datetime import datetime
    import calendar
    from app.models import Group, Subject, TeacherSubject, Schedule, DirectionCurriculum
    
    user = current_user
    today = datetime.now()
    year = request.args.get('year', today.year, type=int)
    month = request.args.get('month', today.month, type=int)
    
    if month < 1:
        month = 12
        year -= 1
    elif month > 12:
        month = 1
        year += 1
    
    prev_month, prev_year = (12, year - 1) if month == 1 else (month - 1, year)
    next_month, next_year = (1, year + 1) if month == 12 else (month + 1, year)
    
    days_in_month = calendar.monthrange(year, month)[1]
    # Hafta Dushanbadan boshlanadi (0) – calendar.Calendar orqali to'g'ri joylashtirish
    cal = calendar.Calendar(firstweekday=0)
    calendar_weeks = cal.monthdatescalendar(year, month)  # har hafta: [date, ...] 7 ta
    
    today_year = today.year
    today_month = today.month
    today_day = today.day
    
    # Kalendarda ko'rinadigan barcha kunlarni qamrab olish
    first_calendar_date = calendar_weeks[0][0]
    last_calendar_date = calendar_weeks[-1][-1]
    
    # Filter parameters
    group_id = request.args.get('group_id', type=int)
    subject_id = request.args.get('subject_id', type=int)
    teacher_id = request.args.get('teacher_id', type=int)
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    start_code = int(first_calendar_date.strftime("%Y%m%d"))
    end_code = int(last_calendar_date.strftime("%Y%m%d"))
    
    # Date Range filtering
    if start_date:
        try:
            dt = datetime.strptime(start_date, "%d.%m.%Y")
            start_code = int(dt.strftime("%Y%m%d"))
        except: pass
    if end_date:
        try:
            dt = datetime.strptime(end_date, "%d.%m.%Y")
            end_code = int(dt.strftime("%Y%m%d"))
        except: pass

    query = Schedule.query.filter(Schedule.day_of_week.between(start_code, end_code))
    
    all_groups = []
    all_subjects = []
    all_teachers = []

    if user.role == 'student':
        if user.group_id:
            # Talaba faqat o'z guruhidagi va joriy semestridagi fanlarni ko'radi
            group = Group.query.get(user.group_id)
            if group and group.direction_id:
                # Joriy semestrni aniqlash
                from app.models import DirectionCurriculum
                current_semester = group.semester if group.semester else 1
                
                curr_q = DirectionCurriculum.query.filter_by(
                    direction_id=group.direction_id,
                    semester=current_semester
                )
                curr_items = DirectionCurriculum.filter_by_group_context(curr_q, group).all()
                s_ids = [item.subject_id for item in curr_items]
                all_subjects = Subject.query.filter(Subject.id.in_(s_ids)).order_by(Subject.name).all()
                # Talaba uchun o'qituvchilar ro'yxati (ushbu guruhda dars beradigan o'qituvchilar)
                ts_teachers = TeacherSubject.query.filter(
                    TeacherSubject.group_id == user.group_id,
                    TeacherSubject.subject_id.in_(s_ids)
                ).all()
                teacher_ids = list({ts.teacher_id for ts in ts_teachers if ts.teacher_id})
                all_teachers = User.query.filter(User.id.in_(teacher_ids)).order_by(User.full_name).all() if teacher_ids else []
                # Schedule query'ni ham filterlash
                query = query.filter(
                    Schedule.group_id == user.group_id,
                    Schedule.subject_id.in_(s_ids)
                )
        else:
            query = query.filter(Schedule.id == None)
            
    elif user.role == 'teacher' or user.has_role('teacher'):
        # O'qituvchi faqat o'zi biriktirilgan darslarni ko'radi
        # Ammo faqat guruhning joriy semestridagi fanlar bo'yicha
        from app.models import TeacherSubject, DirectionCurriculum, Group
        
        ts_entries = TeacherSubject.query.filter_by(teacher_id=user.id).all()
        valid_ts_ids = []
        g_ids = set()
        s_ids = set()
        
        for ts in ts_entries:
            group = Group.query.get(ts.group_id)
            if group and group.direction_id:
                current_semester = group.semester if group.semester else 1
                # Tekshirish: bu fan bu guruhda shu semestrda bormi? (yil, ta'lim shakli)
                curr_q = DirectionCurriculum.query.filter_by(
                    direction_id=group.direction_id,
                    subject_id=ts.subject_id,
                    semester=current_semester
                )
                curr_item = DirectionCurriculum.filter_by_group_context(curr_q, group).first()
                if curr_item:
                    valid_ts_ids.append(ts.id)
                    g_ids.add(ts.group_id)
                    s_ids.add(ts.subject_id)
        
        # Schedule query'ni filterlash
        if valid_ts_ids:
            query = query.filter(
                Schedule.teacher_id == user.id,
                Schedule.group_id.in_(list(g_ids)),
                Schedule.subject_id.in_(list(s_ids))
            )
        else:
            query = query.filter(Schedule.id == None)
            
        all_groups = Group.query.filter(Group.id.in_(list(g_ids))).order_by(Group.name).all() if g_ids else []
        all_subjects = Subject.query.filter(Subject.id.in_(list(s_ids))).distinct().order_by(Subject.name).all() if s_ids else []

    # Apply additional filters
    if group_id:
        query = query.filter_by(group_id=group_id)
    if subject_id:
        query = query.filter_by(subject_id=subject_id)
    if teacher_id:
        query = query.filter_by(teacher_id=teacher_id)
    
    schedules = query.order_by(Schedule.day_of_week, Schedule.start_time).all()
    
    # Sana bo'yicha guruhlash (YYYY-MM-DD formatida)
    schedule_by_date = {}
    for s in schedules:
        try:
            code_str = str(s.day_of_week)
            if len(code_str) == 8:
                date_key = f"{code_str[:4]}-{code_str[4:6]}-{code_str[6:8]}"
                if date_key not in schedule_by_date:
                    schedule_by_date[date_key] = []
                schedule_by_date[date_key].append(s)
        except: continue
    
    for date_key in schedule_by_date:
        schedule_by_date[date_key].sort(key=lambda x: x.start_time or '')
    
    # Eski format uchun moslik (faqat joriy oy kunlari)
    schedule_by_day = {i: [] for i in range(1, days_in_month + 1)}
    for i in range(1, days_in_month + 1):
        date_key = f"{year}-{month:02d}-{i:02d}"
        schedule_by_day[i] = schedule_by_date.get(date_key, [])
    
    return render_template('schedule.html',
                          year=year, month=month,
                          today_year=today_year, today_month=today_month, today_day=today_day,
                          prev_year=prev_year, prev_month=prev_month,
                          next_year=next_year, next_month=next_month,
                          days_in_month=days_in_month,
                          calendar_weeks=calendar_weeks,
                          schedule_by_day=schedule_by_day,
                          schedule_by_date=schedule_by_date,
                          all_groups=all_groups, all_subjects=all_subjects, all_teachers=all_teachers,
                          current_group_id=group_id, current_subject_id=subject_id, current_teacher_id=teacher_id)
