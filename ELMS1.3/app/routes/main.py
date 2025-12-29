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
    
    # Foydalanuvchi rollariga qarab turli ma'lumotlar
    stats = {}
    announcements = []
    recent_assignments = []
    upcoming_schedules = []
    
    # my_subjects o'zgaruvchisini barcha rollar uchun yaratish
    my_subjects = []
    semester_progress = 0
    semester_grade = None
    payment_info = None
    
    if user.role == 'student':
        # Talaba uchun
        from app.models import DirectionCurriculum
        current_semester = user.semester if user.semester else 1
        
        # Faqat joriy semestrdagi fanlarni olish
        my_subjects = []
        current_semester_subjects_count = 0
        my_subjects_info = {}
        
        if user.group_id:
            group = Group.query.get(user.group_id)
            if group and group.direction_id:
                # Faqat joriy semestrdagi fanlarni olish
                curriculum_items = DirectionCurriculum.query.filter_by(
                    direction_id=group.direction_id,
                    semester=current_semester
                ).all()
                
                # Fanlarni olish
                subject_ids = [item.subject_id for item in curriculum_items]
                my_subjects = Subject.query.filter(Subject.id.in_(subject_ids)).all() if subject_ids else []
                
                for item in curriculum_items:
                    course_year = ((item.semester - 1) // 2) + 1
                    # Kreditni hisoblash (jami soat / 30) - Fanlar bo'limidagi kabi yaxlitlamasdan
                    # (maruza + amaliyot + laboratoriya + seminar + mustaqil) / 30
                    # Kurs ishi kreditga kiritilmaydi
                    total_hours = (item.hours_maruza or 0) + (item.hours_amaliyot or 0) + \
                                 (item.hours_laboratoriya or 0) + (item.hours_seminar or 0) + \
                                 (item.hours_mustaqil or 0)
                    # Fanlar bo'limidagi kabi: yaxlitlamasdan va subject.credits fallback
                    subject = Subject.query.get(item.subject_id)
                    # Fanlar bo'limidagi kabi: total_hours > 0 bo'lsa total_hours/30, aks holda subject.credits
                    if total_hours > 0:
                        credits = total_hours / 30
                    else:
                        # Agar total_hours 0 bo'lsa, subject.credits dan olamiz
                        if subject and subject.credits:
                            credits = subject.credits
                        else:
                            credits = None
                    
                    # Kreditni dictionary'ga qo'shish (None bo'lsa ham qo'shamiz, lekin template'da tekshiramiz)
                    my_subjects_info[item.subject_id] = {
                        'semester': item.semester,
                        'course_year': course_year,
                        'credits': credits
                    }
                
                current_semester_subjects_count = len(curriculum_items)
                
                # Har bir fan uchun o'zlashtirish ko'rsatkichini hisoblash
                if group and group.direction_id:
                    for subject_id in subject_ids:
                        # Ushbu fan bo'yicha barcha topshiriqlar
                        subject_assignments = Assignment.query.filter(
                            Assignment.subject_id == subject_id,
                            Assignment.direction_id == group.direction_id,
                            (Assignment.group_id == user.group_id) | (Assignment.group_id.is_(None))
                        ).all()
                        
                        total_assignments = len(subject_assignments)
                        graded_count = 0
                        total_score = 0.0
                        total_max_score = 0.0
                        
                        if subject_assignments:
                            assignment_ids = [a.id for a in subject_assignments]
                            # Barcha topshiriqlarning maksimal ball yig'indisi
                            for assignment in subject_assignments:
                                if assignment.max_score:
                                    total_max_score += assignment.max_score
                            
                            # Baholangan topshiriqlar
                            graded_submissions = Submission.query.filter(
                                Submission.student_id == user.id,
                                Submission.assignment_id.in_(assignment_ids),
                                Submission.is_active == True,
                                Submission.score != None
                            ).all()
                            graded_count = len(graded_submissions)
                            
                            # Jami ball hisoblash (faqat baholangan topshiriqlar)
                            for submission in graded_submissions:
                                if submission.score is not None:
                                    total_score += submission.score
                        
                        # O'zlashtirish foizi - talabaning olgan ballaridan hisoblanadi
                        # total_score / total_max_score * 100
                        progress_percent = 0.0
                        if total_max_score > 0:
                            progress_percent = round((total_score / total_max_score) * 100, 1)
                        
                        # my_subjects_info ga qo'shish - progress har doim qo'shiladi (0 bo'lsa ham)
                        progress_score_value = round(total_score, 0)
                        progress_max_value = round(total_max_score, 0) if total_max_score > 0 else 100
                        
                        if subject_id in my_subjects_info:
                            my_subjects_info[subject_id]['progress'] = progress_percent
                            my_subjects_info[subject_id]['graded_count'] = graded_count
                            my_subjects_info[subject_id]['total_assignments'] = total_assignments
                            my_subjects_info[subject_id]['progress_score'] = progress_score_value
                            my_subjects_info[subject_id]['progress_max'] = progress_max_value
                        else:
                            # Agar subject_id my_subjects_info da yo'q bo'lsa, yaratish
                            my_subjects_info[subject_id] = {
                                'progress': progress_percent,
                                'graded_count': graded_count,
                                'total_assignments': total_assignments,
                                'progress_score': progress_score_value,
                                'progress_max': progress_max_value,
                                'semester': None,
                                'course_year': None
                            }
            else:
                my_subjects = user.get_subjects() if hasattr(user, 'get_subjects') else []
        else:
            my_subjects = user.get_subjects() if hasattr(user, 'get_subjects') else []
        
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
            upcoming_schedules = Schedule.query.filter_by(group_id=user.group_id).all()
            # Bugungi dars jadvali (Toshkent vaqti bo'yicha)
            today = get_tashkent_time().date()
            today_weekday = today.weekday()  # 0 = Monday, 6 = Sunday
            today_schedule = Schedule.query.filter_by(group_id=user.group_id).filter(
                Schedule.day_of_week == today_weekday
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
        
        # Semestr bo'yicha o'zlashtirish ko'rsatkichi
        from app.models import DirectionCurriculum, GradeScale
        
        semester_progress = 0
        semester_grade = None
        
        if user.group_id:
            group = Group.query.get(user.group_id)
            if group and group.direction_id:
                # Faqat joriy semestrdagi fanlar
                curriculum_items = DirectionCurriculum.query.filter_by(
                    direction_id=group.direction_id,
                    semester=current_semester
                ).all()
                
                total_semester_score = 0
                total_semester_max_score = 0
                
                for item in curriculum_items:
                    # Ushbu fan bo'yicha barcha topshiriqlarni olish
                    subject_assignments = Assignment.query.filter(
                        Assignment.subject_id == item.subject_id,
                        (Assignment.group_id == user.group_id) | (Assignment.group_id.is_(None)),
                        (Assignment.direction_id == group.direction_id) | (Assignment.direction_id.is_(None))
                    ).all()
                    
                    for assignment in subject_assignments:
                        # Jami max_score ga har doim qo'shamiz
                        total_semester_max_score += assignment.max_score
                        
                        # Baholangan topshiriqni qidiramiz
                        submission = Submission.query.filter_by(
                            student_id=user.id,
                            assignment_id=assignment.id,
                            is_active=True
                        ).first()
                        
                        if submission and submission.score is not None:
                            total_semester_score += submission.score
                
                if total_semester_max_score > 0:
                    semester_progress = round((total_semester_score / total_semester_max_score) * 100)
                    semester_grade = GradeScale.get_grade(semester_progress)
        
        # To'lov ma'lumotlari
        payment_info = None
        student_payments = StudentPayment.query.filter_by(student_id=user.id).order_by(StudentPayment.created_at.desc()).all()
        if student_payments:
            # Oxirgi to'lov ma'lumotlarini olish
            latest_payment = student_payments[0]
            total_contract = float(latest_payment.contract_amount)
            total_paid = sum(float(p.paid_amount) for p in student_payments)
            payment_percentage = round((total_paid / total_contract * 100), 1) if total_contract > 0 else 0
            
            payment_info = {
                'contract': total_contract,
                'paid': total_paid,
                'remaining': total_contract - total_paid,
                'percentage': payment_percentage
            }
    
    elif user.role == 'teacher' or user.has_role('teacher'):
        # O'qituvchi uchun
        from app.models import DirectionCurriculum, Direction
        teacher_subjects = TeacherSubject.query.filter_by(teacher_id=user.id).all()
        subject_ids = [ts.subject_id for ts in teacher_subjects]
        
        # Fanlarni semester va kurs ma'lumotlari bilan yig'ish
        my_subjects_data = []
        for ts in teacher_subjects:
            group = Group.query.get(ts.group_id)
            if group and group.direction_id:
                curriculum_item = DirectionCurriculum.query.filter_by(
                    direction_id=group.direction_id,
                    subject_id=ts.subject_id
                ).first()
                if curriculum_item:
                    subject = Subject.query.get(ts.subject_id)
                    if subject:
                        course_year = ((curriculum_item.semester - 1) // 2) + 1
                        my_subjects_data.append({
                            'subject': subject,
                            'semester': curriculum_item.semester,
                            'course_year': course_year,
                            'direction': Direction.query.get(group.direction_id)
                        })
        
        # Takrorlanmas fanlar (birinchi topilgan ma'lumotlar bilan)
        seen_subject_ids = set()
        my_subjects_list = []
        for item in my_subjects_data:
            if item['subject'].id not in seen_subject_ids:
                seen_subject_ids.add(item['subject'].id)
                my_subjects_list.append(item)
        
        my_subjects = [item['subject'] for item in my_subjects_list]
        my_subjects_info = {item['subject'].id: item for item in my_subjects_list}
        
        stats = {
            'subjects': my_subjects,
            'assignments': Assignment.query.filter(Assignment.subject_id.in_(subject_ids)).count() if subject_ids else 0,
            'submissions': Submission.query.join(Assignment).filter(Assignment.subject_id.in_(subject_ids)).count() if subject_ids else 0,
            'pending_grades': Submission.query.join(Assignment).filter(
                Assignment.subject_id.in_(subject_ids),
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
        
        # Dars jadvali (o'qituvchi uchun) - Toshkent vaqti
        today = get_tashkent_time().date()
        today_weekday = today.weekday()  # 0 = Monday, 6 = Sunday
        # O'qituvchining guruhlari
        teacher_groups = [ts.group_id for ts in teacher_subjects]
        if teacher_groups:
            today_schedule = Schedule.query.filter(
                Schedule.group_id.in_(teacher_groups),
                Schedule.teacher_id == user.id,
                Schedule.day_of_week == today_weekday
            ).order_by(Schedule.start_time).all()
        else:
            today_schedule = []
    
    elif user.role == 'dean':
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
    
    elif user.role == 'admin':
        # Admin uchun
        stats = {
            'total_users': User.query.count(),
            'total_students': User.query.filter_by(role='student').count(),
            'total_teachers': User.query.filter_by(role='teacher').count(),
            'total_faculties': Faculty.query.count(),
            'total_subjects': Subject.query.count()
        }
        
        # E'lonlar
        announcements = Announcement.query.order_by(Announcement.created_at.desc()).limit(5).all()
    
    # today_schedule o'zgaruvchisini barcha rollar uchun yaratish (agar yaratilmagan bo'lsa)
    if 'today_schedule' not in locals():
        today_schedule = []
    
    # O'qituvchi uchun fanlar ma'lumotlari
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
                    my_subjects_info[ts.subject_id] = {
                        'semester': curriculum_item.semester,
                        'course_year': course_year
                    }
    
    # pending_assignments ni boshqa rollar uchun ham yaratish (agar mavjud bo'lmasa)
    if user.role != 'student':
        if 'pending_assignments' not in locals():
            pending_assignments = []
            if recent_assignments:
                for assignment in recent_assignments[:5]:
                    pending_assignments.append({
                        'assignment': assignment,
                        'status': 'not_submitted',
                        'submission': None
                    })
    
    # now o'zgaruvchisini barcha rollar uchun aniqlash (Toshkent vaqti)
    if 'now_dt' not in locals():
        now_dt = get_tashkent_time()
    
    return render_template('dashboard.html', stats=stats, announcements=announcements, 
                         recent_assignments=recent_assignments, upcoming_schedules=upcoming_schedules,
                         my_subjects=my_subjects, today_schedule=today_schedule, my_subjects_info=my_subjects_info,
                         pending_assignments=pending_assignments if 'pending_assignments' in locals() else [],
                         semester_progress=semester_progress if 'semester_progress' in locals() else 0,
                         semester_grade=semester_grade if 'semester_grade' in locals() else None,
                         payment_info=payment_info if 'payment_info' in locals() else None,
                         upcoming_due_assignments=upcoming_due_assignments if 'upcoming_due_assignments' in locals() else [])

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
    # Barcha foydalanuvchilar, lekin o'zini va allaqachon suhbat bo'lganlarini olib tashlash
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
    from datetime import datetime, timedelta
    import calendar
    
    # Joriy sana
    today = datetime.now()
    today_year = today.year
    today_month = today.month
    today_day = today.day
    
    # URL parametrlaridan oy va yilni olish
    year = request.args.get('year', today_year, type=int)
    month = request.args.get('month', today_month, type=int)
    
    # Oy va yilni tekshirish
    if month < 1:
        month = 12
        year -= 1
    elif month > 12:
        month = 1
        year += 1
    
    # Oldingi va keyingi oylar
    if month == 1:
        prev_month = 12
        prev_year = year - 1
    else:
        prev_month = month - 1
        prev_year = year
    
    if month == 12:
        next_month = 1
        next_year = year + 1
    else:
        next_month = month + 1
        next_year = year
    
    # Oyning birinchi kuni va kunlar soni
    first_day = datetime(year, month, 1)
    days_in_month = calendar.monthrange(year, month)[1]
    start_weekday = first_day.weekday()  # 0 = Monday, 6 = Sunday
    
    # Jadvalni olish
    user = current_user
    
    # Joriy oy uchun sanalar diapazoni (YYYYMMDD ko'rinishida)
    start_code = int(f"{year}{month:02d}01")
    end_code = int(f"{year}{month:02d}{days_in_month:02d}")
    
    query = Schedule.query.filter(
        Schedule.day_of_week.between(start_code, end_code)
    )
    
    if user.role == 'student':
        # Talaba uchun - faqat o'z guruhidagi darslar
        if user.group_id:
            query = query.filter_by(group_id=user.group_id)
        else:
            query = query.filter_by(id=None)  # Guruh yo'q bo'lsa, hech narsa ko'rsatma
    elif user.role == 'teacher' or user.has_role('teacher'):
        # O'qituvchi uchun - o'z o'qitayotgan guruhlardagi darslar
        teacher_groups = Group.query.join(TeacherSubject).filter(
            TeacherSubject.teacher_id == user.id
        ).all()
        if teacher_groups:
            group_ids = [g.id for g in teacher_groups]
            query = query.filter(Schedule.group_id.in_(group_ids))
        else:
            query = query.filter_by(id=None)  # Guruhlar yo'q bo'lsa, hech narsa ko'rsatma
    
    # Barcha darslarni olish (day_of_week asosida)
    schedules = query.order_by(Schedule.day_of_week, Schedule.start_time).all()
    
    # Kunlar bo'yicha guruhlash (har bir dars aniq sana bo'yicha)
    schedule_by_day = {i: [] for i in range(1, days_in_month + 1)}
    for s in schedules:
        try:
            # day_of_week YYYYMMDD formatida (masalan: 20251210)
            code_str = str(s.day_of_week)
            if len(code_str) == 8:  # YYYYMMDD formatida
                day = int(code_str[-2:])  # Oxirgi 2 raqam - kun
            else:
                # Eski format (hafta kuni 0-6) - o'tkazib yuborish
                continue
        except (TypeError, ValueError):
            continue
        if 1 <= day <= days_in_month:
            schedule_by_day[day].append(s)
    
    # Har bir kun uchun vaqt bo'yicha tartiblash
    for day in schedule_by_day:
        schedule_by_day[day].sort(key=lambda x: x.start_time or '')
    
    return render_template('schedule.html',
                          year=year,
                          month=month,
                          today_year=today_year,
                          today_month=today_month,
                          today_day=today_day,
                          prev_year=prev_year,
                          prev_month=prev_month,
                          next_year=next_year,
                          next_month=next_month,
                          days_in_month=days_in_month,
                          start_weekday=start_weekday,
                          schedule_by_day=schedule_by_day)