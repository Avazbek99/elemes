from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from flask_login import login_required, current_user
from app.models import User, Subject, Assignment, Announcement, Schedule, Submission, Message, Group, Faculty, TeacherSubject, StudentPayment
from app import db
from datetime import datetime, timedelta, date

def get_tashkent_time():
    """Toshkent vaqtini qaytaradi (UTC+5)"""
    return datetime.utcnow() + timedelta(hours=5)
from sqlalchemy import func
from app.utils.translations import get_translation, get_current_language
import calendar

bp = Blueprint('main', __name__)

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
    
    # Rol nomlarini o'zbek tilida
    role_names = {
        'admin': 'Administrator',
        'dean': 'Dekan',
        'teacher': "O'qituvchi",
        'student': 'Talaba',
        'accounting': 'Buxgalter'
    }
    
    if role in user_roles:
        session['current_role'] = role
        role_name = role_names.get(role, role)
        flash(f"Profil {role_name} roliga o'zgartirildi. Endi siz {role_name} sifatida ishlayapsiz.", 'success')
        return redirect(url_for('main.dashboard'))
    else:
        flash("Sizda bu rolga kirish huquqi yo'q", 'error')
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
    
    # Salomlashuv va bugungi sana
    now = get_tashkent_time()
    today = now.strftime('%d.%m.%Y')
    
    hour = now.hour
    if 5 <= hour < 10:
        greeting = "Xayrli tong"
    elif 10 <= hour < 18:
        greeting = "Xayrli kun"
    elif 18 <= hour < 22:
        greeting = "Xayrli kecha"
    else:
        greeting = "Xayrli tun"
    
    if active_role == 'student':
        from app.models import DirectionCurriculum
        current_semester = user.semester
        my_subjects_info = {}
        current_semester_subjects_count = 0
        total_semester_credits = 0.0
        direction_id = None
        
        if user.group_id:
            group = Group.query.get(user.group_id)
            if group:
                direction_id = group.direction_id
                if group.direction:
                    current_semester = group.semester
            
            # Fetch curriculum items for all subjects in the current semester
            curriculum_list = []
            if direction_id:
                curriculum_list = DirectionCurriculum.query.join(Subject).filter(
                    DirectionCurriculum.direction_id == direction_id,
                    DirectionCurriculum.semester == current_semester
                ).order_by(Subject.name).all()
            
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
                my_subjects_info[item.subject_id] = {
                    'semester': item.semester,
                    'course_year': course_year,
                    'credits': credits,
                    'progress': 0,
                    'graded_count': 0,
                    'total_assignments': 0,
                    'progress_score': 0,
                    'progress_max': 100
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
                # Joriy semestrdagi fanlar
                curriculum_items = DirectionCurriculum.query.filter_by(
                    direction_id=group.direction_id,
                    semester=current_semester
                ).all()
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
        
        # To'lov ma'lumotlari
        payment_info = None
        student_payments = StudentPayment.query.filter_by(student_id=user.id).order_by(StudentPayment.created_at.desc()).all()
        if student_payments:
            # Oxirgi to'lov ma'lumotlarini olish
            latest_payment = student_payments[0]
            total_contract = float(latest_payment.contract_amount)
            total_paid = sum(float(p.paid_amount) for p in student_payments)
            payment_percentage = (total_paid / total_contract * 100) if total_contract > 0 else 0
            
            payment_info = {
                'contract': total_contract,
                'paid': total_paid,
                'remaining': total_contract - total_paid,
                'percentage': payment_percentage
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
                # Only show subjects that belong to the group's current semester
                current_semester = group.semester if group.semester else 1
                curriculum_item = DirectionCurriculum.query.filter_by(
                    direction_id=group.direction_id,
                    subject_id=ts.subject_id,
                    semester=current_semester
                ).first()
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
                        
                        # 2. Yaratilgan mavzularni sanash
                        created_lessons_count = 0
                        if search_lesson_types:
                            created_lessons_count = Lesson.query.filter(
                                Lesson.subject_id == subject.id,
                                Lesson.created_by == user.id,
                                Lesson.lesson_type.in_(search_lesson_types),
                                (Lesson.group_id == group.id) | (Lesson.group_id == None)
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
        
        # Topshiriqlar ro'yxati (Assignments)
        teacher_assignments_list = []
        if subject_ids:
            # Teacher assigned subjects are in subject_ids
            # Filter logic: Show assignments for these subjects AND created by THIS teacher
            assignments_query = Assignment.query.filter(
                Assignment.subject_id.in_(subject_ids),
                Assignment.created_by == user.id
            ).order_by(Assignment.due_date.desc()).all()
            
            for asm in assignments_query:
                # Yangi javoblarni sanash (Submission.score == None)
                # Count submissions associated with this assignment
                pending_query = asm.submissions.filter(Submission.score == None)
                pending_count = pending_query.count()
                resubmitted_count = pending_query.filter(Submission.resubmission_count > 0).count()
                
                item = {
                    'id': asm.id,
                    'title': asm.title,
                    'subject_name': asm.subject.name,
                    'group_name': asm.group.name if asm.group else "Barcha guruhlar",
                    'due_date': asm.due_date,
                    'lesson_type': asm.lesson_type,
                    'pending_count': pending_count,
                    'resubmitted_count': resubmitted_count
                }
                teacher_assignments_list.append(item)
            
            # Pending topshiriqlar ro'yxati (Tekshirilmagan)
            teacher_pending_assignments_list = [a for a in teacher_assignments_list if a['pending_count'] > 0]


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
                curriculum_item = DirectionCurriculum.query.filter_by(
                    direction_id=group.direction_id,
                    subject_id=ts.subject_id
                ).first()
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
                'group_name': assignment.group.name if assignment.group else "Barcha guruhlar",
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

    return render_template('dashboard.html', stats=stats, **stats, announcements=announcements, 
                         recent_assignments=recent_assignments, upcoming_schedules=upcoming_schedules,
                         my_subjects=my_subjects, today_schedule=today_schedule, my_subjects_info=my_subjects_info,
                         pending_assignments=pending_assignments if 'pending_assignments' in locals() else [],
                         semester_progress=semester_progress if 'semester_progress' in locals() else 0,
                         total_semester_score=total_semester_score if 'total_semester_score' in locals() else 0,
                         total_semester_max_score=total_semester_max_score if 'total_semester_max_score' in locals() else 0,
                         semester_grade=semester_grade if 'semester_grade' in locals() else None,
                         payment_info=payment_info if 'payment_info' in locals() else None,
                         upcoming_due_assignments=upcoming_due_assignments if 'upcoming_due_assignments' in locals() else [],
                         greeting=greeting, today=today, role=active_role, direction_id=direction_id,
                         teacher_assignments_list=teacher_assignments_list if 'teacher_assignments_list' in locals() else [],
                         teacher_pending_assignments_list=teacher_pending_assignments_list if 'teacher_pending_assignments_list' in locals() else [])

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
        flash("Sizda e'lon yaratish huquqi yo'q", 'error')
        return redirect(url_for('main.announcements'))
    
    if request.method == 'POST':
        title = request.form.get('title')
        content = request.form.get('content')
        target_roles = request.form.getlist('target_roles')
        is_important = request.form.get('is_important') == 'on'
        
        if not title or not content:
            flash("Sarlavha va matn majburiy", 'error')
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
        
        flash("E'lon muvaffaqiyatli yaratildi", 'success')
        return redirect(url_for('main.announcements'))
    
    return render_template('create_announcement.html')

@bp.route('/announcements/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit_announcement(id):
    """E'lonni tahrirlash"""
    announcement = Announcement.query.get_or_404(id)
    
    # Joriy rolni olish (session'dan yoki asosiy roldan)
    current_role = session.get('current_role', current_user.role)
    
    # Ruxsat tekshiruvi
    # Admin faqat admin roli tanlangan bo'lsa barcha e'lonlarni tahrirlay oladi
    # Boshqa foydalanuvchilar faqat o'z e'lonlarini tahrirlay oladi
    is_admin_with_admin_role = current_user.has_role('admin') and current_role == 'admin'
    
    if not is_admin_with_admin_role and announcement.author_id != current_user.id:
        flash("Sizda bu e'lonni tahrirlash huquqi yo'q", 'error')
        return redirect(url_for('main.announcements'))
    
    if request.method == 'POST':
        title = request.form.get('title')
        content = request.form.get('content')
        target_roles = request.form.getlist('target_roles')
        is_important = request.form.get('is_important') == 'on'
        
        if not title or not content:
            flash("Sarlavha va matn majburiy", 'error')
            return render_template('edit_announcement.html', announcement=announcement)
        
        # Target roles ni string sifatida saqlash
        target_roles_str = ','.join(target_roles) if target_roles else None
        
        announcement.title = title
        announcement.content = content
        announcement.target_roles = target_roles_str
        announcement.is_important = is_important
        
        db.session.commit()
        
        flash("E'lon muvaffaqiyatli yangilandi", 'success')
        return redirect(url_for('main.announcements'))
    
    return render_template('edit_announcement.html', announcement=announcement)

@bp.route('/announcements/<int:id>/delete', methods=['POST'])
@login_required
def delete_announcement(id):
    """E'lonni o'chirish"""
    announcement = Announcement.query.get_or_404(id)
    
    # Joriy rolni olish (session'dan yoki asosiy roldan)
    current_role = session.get('current_role', current_user.role)
    
    # Admin faqat admin roli tanlangan bo'lsa barcha e'lonlarni o'chira oladi
    # Boshqa foydalanuvchilar faqat o'z e'lonlarini o'chira oladi
    is_admin_with_admin_role = current_user.has_role('admin') and current_role == 'admin'
    
    if not is_admin_with_admin_role and announcement.author_id != current_user.id:
        flash("Sizda bu e'lonni o'chirish huquqi yo'q", 'error')
        return redirect(url_for('main.announcements'))
    
    try:
        db.session.delete(announcement)
        db.session.commit()
        flash("E'lon o'chirildi", 'success')
    except Exception as e:
        db.session.rollback()
        flash(f"E'lonni o'chirishda xatolik yuz berdi: {str(e)}", 'error')
    
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
        flash("Sizda barcha e'lonlarni o'chirish huquqi yo'q", 'error')
        return redirect(url_for('main.announcements'))
    
    try:
        # Barcha e'lonlarni olish va o'chirish
        all_announcements = Announcement.query.all()
        count = len(all_announcements)
        
        for announcement in all_announcements:
            db.session.delete(announcement)
        
        db.session.commit()
        flash(f"Barcha {count} ta e'lon o'chirildi", 'success')
    except Exception as e:
        db.session.rollback()
        flash(f"E'lonlarni o'chirishda xatolik yuz berdi: {str(e)}", 'error')
    
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
            all_users = []
        else:
            # Talaba uchun: o'z guruhi, dars beradigan o'qituvchilari va O'Z dekani + admin/accounting
            faculty_id = user.group.faculty_id if user.group else None
            teacher_ids = [ts.teacher_id for ts in TeacherSubject.query.filter_by(group_id=user.group_id).all()]
            
            from sqlalchemy import or_
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
        
        from sqlalchemy import or_
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
        
    available_users = [u for u in all_users if u.id not in chats_dict.keys()]
    
    return render_template('messages.html', chats=chats, available_users=available_users)

@bp.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    """Profil sozlamalari"""
    if request.method == 'POST':
        user = current_user
        
        # Ma'lumotlarni yangilash
        # To'liq ism o'zgartirilmaydi (faqat telefon va email)
        user.phone = request.form.get('phone', user.phone)
        
        # Emailni o'zgartirish (xodimlar va talabalar uchun)
        new_email = request.form.get('email', '').strip()
        if new_email and new_email != user.email:
            # Email unikalligini tekshirish
            existing_user = User.query.filter_by(email=new_email).first()
            if existing_user and existing_user.id != user.id:
                flash("Bu email allaqachon boshqa foydalanuvchi tomonidan ishlatilmoqda", 'error')
                return render_template('settings.html')
            user.email = new_email if new_email else None
        
        # Parolni o'zgartirish
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        
        if new_password:
            # Yangi parolni tekshirish
            if new_password == confirm_password:
                if len(new_password) >= 8:
                    user.set_password(new_password)
                    flash("Parol muvaffaqiyatli o'zgartirildi", 'success')
                else:
                    flash("Parol kamida 8 ta belgidan iborat bo'lishi kerak", 'error')
                    return render_template('settings.html')
            else:
                flash("Yangi parollar mos kelmaydi", 'error')
                return render_template('settings.html')
        
        db.session.commit()
        flash("Ma'lumotlar muvaffaqiyatli yangilandi", 'success')
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
            allowed = False
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
        flash("Sizda ushbu foydalanuvchi bilan suhbatlashish uchun ruxsat yo'q", 'error')
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
            flash("Xabar yuborildi", 'success')
            return redirect(url_for('main.chat', user_id=user_id))
        else:
            flash("Xabar bo'sh bo'lishi mumkin emas", 'error')
    
    # Ikki foydalanuvchi o'rtasidagi barcha xabarlar
    messages = Message.query.filter(
        ((Message.sender_id == current_user.id) & (Message.receiver_id == user_id)) |
        ((Message.sender_id == user_id) & (Message.receiver_id == current_user.id))
    ).order_by(Message.created_at.asc()).all()
    
    # Xabarlarni o'qilgan deb belgilash
    Message.query.filter_by(sender_id=user_id, receiver_id=current_user.id, is_read=False).update({'is_read': True})
    db.session.commit()
    
    return render_template('chat.html', other_user=other_user, messages=messages)

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
    start_weekday = datetime(year, month, 1).weekday()
    
    # Filter parameters
    group_id = request.args.get('group_id', type=int)
    subject_id = request.args.get('subject_id', type=int)
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    start_code = int(f"{year}{month:02d}01")
    end_code = int(f"{year}{month:02d}{days_in_month:02d}")
    
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

    if user.role == 'student':
        if user.group_id:
            # Talaba faqat o'z guruhidagi va joriy semestridagi fanlarni ko'radi
            group = Group.query.get(user.group_id)
            if group and group.direction_id:
                # Joriy semestrni aniqlash
                from app.models import DirectionCurriculum
                current_semester = group.semester if group.semester else 1
                
                curr_items = DirectionCurriculum.query.filter_by(
                    direction_id=group.direction_id,
                    semester=current_semester
                ).all()
                s_ids = [item.subject_id for item in curr_items]
                all_subjects = Subject.query.filter(Subject.id.in_(s_ids)).order_by(Subject.name).all()
                
                # Shcedule query'ni ham filterlash
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
                # Tekshirish: bu fan bu guruhda shu semestrda bormi?
                curr_item = DirectionCurriculum.query.filter_by(
                    direction_id=group.direction_id,
                    subject_id=ts.subject_id,
                    semester=current_semester
                ).first()
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
    
    schedules = query.order_by(Schedule.day_of_week, Schedule.start_time).all()
    
    schedule_by_day = {i: [] for i in range(1, days_in_month + 1)}
    for s in schedules:
        try:
            code_str = str(s.day_of_week)
            if len(code_str) == 8:
                s_year = int(code_str[:4])
                s_month = int(code_str[4:6])
                if s_year == year and s_month == month:
                    day = int(code_str[6:8])
                    if 1 <= day <= days_in_month:
                        schedule_by_day[day].append(s)
        except: continue
        
    for day in schedule_by_day:
        schedule_by_day[day].sort(key=lambda x: x.start_time or '')
    
    return render_template('schedule.html',
                          year=year, month=month,
                          today_year=today.year, today_month=today.month, today_day=today.day,
                          prev_year=prev_year, prev_month=prev_month,
                          next_year=next_year, next_month=next_month,
                          days_in_month=days_in_month, start_weekday=start_weekday,
                          schedule_by_day=schedule_by_day,
                          all_groups=all_groups, all_subjects=all_subjects,
                          current_group_id=group_id, current_subject_id=subject_id)
