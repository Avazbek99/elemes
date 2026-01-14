import os
import uuid
import json
import requests
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, send_from_directory, jsonify, Response, session
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from app.models import Subject, Lesson, Assignment, Submission, User, TeacherSubject, Group, LessonView, GradeScale, DirectionCurriculum, Direction
from app import db
from datetime import datetime, timedelta

def get_tashkent_time():
    """Toshkent vaqtini qaytaradi (UTC+5)"""
    return datetime.utcnow() + timedelta(hours=5)


def allowed_video(filename):
    """Video fayl tekshirish"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in current_app.config.get('ALLOWED_VIDEO_EXTENSIONS', {'mp4', 'webm', 'ogg'})

def allowed_submission_file(filename):
    """Topshiriq fayl tekshirish"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in current_app.config.get('ALLOWED_SUBMISSION_EXTENSIONS', {'pdf', 'doc', 'docx', 'xls', 'xlsx', 'jpg', 'jpeg', 'png'})

bp = Blueprint('courses', __name__, url_prefix='/subjects')

@bp.route('/')
@login_required
def index():
    """Fanlar ro'yxati"""
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '')
    
    if current_user.role == 'student' or current_user.has_role('student'):
        # Talaba faqat o'z guruhiga biriktirilgan fanlarni ko'radi
        if current_user.group_id:
            subject_ids = [ts.subject_id for ts in TeacherSubject.query.filter_by(group_id=current_user.group_id).all()]
            query = Subject.query.filter(Subject.id.in_(subject_ids))
        else:
            query = Subject.query.filter(False)  # Bo'sh
    elif current_user.role == 'teacher' or current_user.has_role('teacher'):
        # O'qituvchi faqat o'ziga biriktirilgan fanlarni ko'radi
        subject_ids = [ts.subject_id for ts in TeacherSubject.query.filter_by(teacher_id=current_user.id).all()]
        query = Subject.query.filter(Subject.id.in_(subject_ids)) if subject_ids else Subject.query.filter(False)
    else:
        # Admin va dekan barcha fanlarni ko'radi
        query = Subject.query
    
    if search:
        query = query.filter(
            Subject.name.ilike(f'%{search}%')
        )
    
    # Semestr bo'yicha guruhlash va tartiblash (o'qituvchi va talaba uchun)
    subjects_by_semester = {}
    all_subjects_list = []
    
    if current_user.role == 'student' and current_user.group_id:
        # Talaba uchun - faqat joriy semestrdagi fanlarni ko'rsatish
        group = Group.query.get(current_user.group_id)
        current_semester = current_user.semester if current_user.semester else 1
        
        if group and group.direction_id:
            # DirectionCurriculum orqali faqat joriy semestrdagi fanlarni olish
            curriculum_items = DirectionCurriculum.query.filter_by(
                direction_id=group.direction_id,
                semester=current_semester
            ).join(Subject).order_by(Subject.name).all()
            
            for item in curriculum_items:
                semester = item.semester
                if semester not in subjects_by_semester:
                    subjects_by_semester[semester] = []
                # Takrorlanuvchi fanlarni tekshirish
                existing_subjects = [s['subject'].id for s in subjects_by_semester[semester]]
                if item.subject.id not in existing_subjects:
                    # Talaba uchun yo'nalish bo'yicha dars va topshiriqlar sonini hisoblash
                    lessons_count = Lesson.query.filter_by(
                        subject_id=item.subject.id,
                        direction_id=group.direction_id
                    ).count()
                    
                    assignments_count = Assignment.query.filter_by(
                        subject_id=item.subject.id,
                        direction_id=group.direction_id
                    ).count()
                    
                    # Kursni hisoblash
                    course_year = ((semester - 1) // 2) + 1
                    # Kreditni o'quv rejasidagi soatlar bo'yicha hisoblash (maruza + amaliyot + laboratoriya + seminar + mustaqil) / 30
                    # Kurs ishi kreditga kiritilmaydi
                    total_hours = (item.hours_maruza or 0) + (item.hours_amaliyot or 0) + \
                                 (item.hours_laboratoriya or 0) + (item.hours_seminar or 0) + \
                                 (item.hours_mustaqil or 0)
                    credits = total_hours / 30 if total_hours > 0 else (item.subject.credits if item.subject.credits else 0)
                    
                    # Bu fanga biriktirilgan o'qituvchilarni olish
                    teacher_subjects = TeacherSubject.query.filter_by(
                        subject_id=item.subject.id,
                        group_id=current_user.group_id
                    ).all()
                    
                    # O'qituvchilarni olish (takrorlanmasligi uchun)
                    teachers_list = []
                    seen_teachers = set()
                    for ts in teacher_subjects:
                        if ts.teacher_id and ts.teacher_id not in seen_teachers:
                            teacher = User.query.get(ts.teacher_id)
                            if teacher:
                                teachers_list.append(teacher)
                                seen_teachers.add(ts.teacher_id)
                    
                    # Direction ma'lumotini olish
                    from app.models import Direction
                    direction = Direction.query.get(group.direction_id) if group.direction_id else None
                    
                    subjects_by_semester[semester].append({
                        'subject': item.subject,
                        'semester': semester,
                        'course_year': course_year,
                        'credits': credits,
                        'lessons_count': lessons_count,
                        'assignments_count': assignments_count,
                        'teachers': teachers_list,
                        'direction': direction
                    })
                    if item.subject not in all_subjects_list:
                        all_subjects_list.append(item.subject)
        else:
            # Agar yo'nalish bo'lmasa, oddiy tartibda
            subjects = query.order_by(Subject.name).paginate(page=page, per_page=12)
            all_subjects_list = list(subjects.items)
    elif current_user.role == 'teacher' or current_user.has_role('teacher'):
        # O'qituvchi uchun - yo'nalish bo'yicha guruhlash
        # Har bir yo'nalish uchun alohida fan card ko'rsatiladi
        from app.models import Direction
        
        teacher_subjects = TeacherSubject.query.filter_by(teacher_id=current_user.id).all()
        
        # Har bir fan+yo'nalish kombinatsiyasi uchun ma'lumotlar
        # {semester: [{subject, direction, groups, credits, semester}, ...]}
        subject_direction_data = {}  # {(subject_id, direction_id): {'subject': ..., 'direction': ..., 'groups': [...], 'semester': ..., 'credits': ...}}
        
        for ts in teacher_subjects:
            group = Group.query.get(ts.group_id)
            if group and group.direction_id:
                direction = Direction.query.get(group.direction_id)
                if not direction:
                    continue
                
                # Bu guruh uchun bu fanga tegishli o'quv reja ma'lumotlarini olish
                curriculum_item = DirectionCurriculum.query.filter_by(
                    direction_id=group.direction_id,
                    subject_id=ts.subject_id
                ).first()
                
                if curriculum_item:
                    semester = curriculum_item.semester
                    key = (ts.subject_id, group.direction_id)
                    
                    if key not in subject_direction_data:
                        subject = Subject.query.get(ts.subject_id)
                        if not subject:
                            continue
                        
                        # Kreditni yo'nalish o'quv rejasidagi soatlar bo'yicha hisoblash
                        # (maruza + amaliyot + lobaratoriya + seminar + mustaqil) / 30
                        # Kurs ishi kreditga kiritilmaydi
                        total_hours = (curriculum_item.hours_maruza or 0) + \
                                     (curriculum_item.hours_amaliyot or 0) + \
                                     (curriculum_item.hours_laboratoriya or 0) + \
                                     (curriculum_item.hours_seminar or 0) + \
                                     (curriculum_item.hours_mustaqil or 0)
                        credits = total_hours / 30 if total_hours > 0 else subject.credits
                        
                        # Yo'nalish bo'yicha dars va topshiriqlar sonini hisoblash
                        lessons_count = Lesson.query.filter_by(
                            subject_id=subject.id,
                            direction_id=direction.id
                        ).count()
                        
                        assignments_count = Assignment.query.filter_by(
                            subject_id=subject.id,
                            direction_id=direction.id
                        ).count()
                        
                        subject_direction_data[key] = {
                            'subject': subject,
                            'direction': direction,
                            'groups': [],
                            'semester': semester,
                            'credits': credits,
                            'lessons_count': lessons_count,
                            'assignments_count': assignments_count
                        }
                    
                    # Guruhni qo'shish (takrorlanmasligi uchun)
                    if group not in subject_direction_data[key]['groups']:
                        subject_direction_data[key]['groups'].append(group)
        
        # Semestr bo'yicha guruhlash va fan nomi bo'yicha tartiblash
        for key, data in subject_direction_data.items():
            semester = data['semester']
            if semester not in subjects_by_semester:
                subjects_by_semester[semester] = []
            
            subjects_by_semester[semester].append(data)
            if data['subject'] not in all_subjects_list:
                all_subjects_list.append(data['subject'])
        
        # Har bir semestr uchun tartiblash: avval fan nomi, keyin guruhlar bo'yicha
        for semester in subjects_by_semester:
            subjects_by_semester[semester].sort(key=lambda x: (
                x['subject'].name,  # 1-navbatda fan nomi
                sorted([g.name for g in x['groups']])[0] if x['groups'] else ''  # Keyin birinchi guruh nomi
            ))
        
        # Agar semestr bo'yicha guruhlash bo'lmasa, oddiy tartibda
        if not subjects_by_semester:
            subjects = query.order_by(Subject.semester, Subject.name).paginate(page=page, per_page=12)
            all_subjects_list = list(subjects.items)
    else:
        # Admin va dekan uchun oddiy tartib - semestr va nomi bo'yicha
        subjects = query.order_by(Subject.semester, Subject.name).paginate(page=page, per_page=12)
        all_subjects_list = list(subjects.items)
    
    # Pagination uchun
    if subjects_by_semester:
        # Semestr bo'yicha guruhlangan fanlar uchun pagination
        total_subjects = len(all_subjects_list)
        per_page = 12
        start = (page - 1) * per_page
        end = start + per_page
        paginated_subjects = all_subjects_list[start:end]
        
        # Pagination obyekti yaratish
        from math import ceil
        class Pagination:
            def __init__(self, items, page, per_page, total):
                self.items = items
                self.page = page
                self.per_page = per_page
                self.total = total
                self.pages = ceil(total / per_page) if total > 0 else 1
                self.has_prev = page > 1
                self.has_next = page < self.pages
                self.prev_num = page - 1 if self.has_prev else None
                self.next_num = page + 1 if self.has_next else None
        
        subjects = Pagination(paginated_subjects, page, per_page, total_subjects)
        subjects_for_processing = subjects.items
    else:
        subjects = query.order_by(Subject.name).paginate(page=page, per_page=12)
        subjects_for_processing = subjects.items
    
    # Har bir fan uchun dars turlarini olish (o'qituvchi va talaba uchun)
    subject_lesson_types = {}
    if current_user.role == 'student' and current_user.group_id:
        # Talaba uchun - guruh va yo'nalish orqali
        group = Group.query.get(current_user.group_id)
        if group and group.direction_id:
            for subject in subjects_for_processing:
                curriculum_item = DirectionCurriculum.query.filter_by(
                    direction_id=group.direction_id,
                    subject_id=subject.id
                ).first()
                
                lessons = []
                if curriculum_item:
                    # Maruza
                    if curriculum_item.hours_maruza and curriculum_item.hours_maruza > 0:
                        lessons.append({
                            'type': 'Maruza',
                            'hours': curriculum_item.hours_maruza
                        })
                    
                    # Amaliyot
                    if curriculum_item.hours_amaliyot and curriculum_item.hours_amaliyot > 0:
                        lessons.append({
                            'type': 'Amaliyot',
                            'hours': curriculum_item.hours_amaliyot
                        })
                    
                    # Laboratoriya - alohida ko'rsatish
                    if curriculum_item.hours_laboratoriya and curriculum_item.hours_laboratoriya > 0:
                        lessons.append({
                            'type': 'Laboratoriya',
                            'hours': curriculum_item.hours_laboratoriya
                        })
                    
                    # Seminar
                    if curriculum_item.hours_seminar and curriculum_item.hours_seminar > 0:
                        lessons.append({
                            'type': 'Seminar',
                            'hours': curriculum_item.hours_seminar
                        })
                    
                    # Kurs ishi
                    if curriculum_item.hours_kurs_ishi and curriculum_item.hours_kurs_ishi > 0:
                        lessons.append({
                            'type': 'Kurs ishi',
                            'hours': 0  # Kurs ishi uchun soat ko'rsatilmaydi
                        })
                
                if lessons:
                    subject_lesson_types[subject.id] = lessons
    elif current_user.role == 'teacher' or current_user.has_role('teacher'):
        # O'qituvchi uchun - har bir yo'nalish uchun alohida dars turlari
        # subject_lesson_types endi {(subject_id, direction_id): [lessons]} formatida
        teacher_subjects = TeacherSubject.query.filter_by(teacher_id=current_user.id).all()
        
        for subject_data_item in subjects_for_processing:
            if isinstance(subject_data_item, dict) and 'direction' in subject_data_item:
                # O'qituvchi uchun - yo'nalish bo'yicha
                subject = subject_data_item['subject']
                direction = subject_data_item['direction']
                
                # Bu yo'nalish uchun o'quv rejadan dars turlarini olish
                curriculum_item = DirectionCurriculum.query.filter_by(
                    direction_id=direction.id,
                    subject_id=subject.id
                ).first()
                
                if curriculum_item:
                    lessons = []
                    
                    # Maruza - o'quv rejadan
                    if curriculum_item.hours_maruza and curriculum_item.hours_maruza > 0:
                        lessons.append({
                            'type': 'Maruza',
                            'hours': curriculum_item.hours_maruza
                        })
                    
                    # Amaliyot - o'quv rejadan
                    if curriculum_item.hours_amaliyot and curriculum_item.hours_amaliyot > 0:
                        lessons.append({
                            'type': 'Amaliyot',
                            'hours': curriculum_item.hours_amaliyot
                        })
                    
                    # Laboratoriya - alohida ko'rsatish
                    if curriculum_item.hours_laboratoriya and curriculum_item.hours_laboratoriya > 0:
                        lessons.append({
                            'type': 'Laboratoriya',
                            'hours': curriculum_item.hours_laboratoriya
                        })
                    
                    # Seminar - o'quv rejadan
                    if curriculum_item.hours_seminar and curriculum_item.hours_seminar > 0:
                        lessons.append({
                            'type': 'Seminar',
                            'hours': curriculum_item.hours_seminar
                        })
                    
                    # Kurs ishi - o'quv rejadan (faqat ko'rsatish uchun, soat emas)
                    if curriculum_item.hours_kurs_ishi and curriculum_item.hours_kurs_ishi > 0:
                        lessons.append({
                            'type': 'Kurs ishi',
                            'hours': 0  # Kurs ishi uchun soat ko'rsatilmaydi
                        })
                    
                    if lessons:
                        # Har bir yo'nalish uchun alohida key (string formatida)
                        key = f"{subject.id}_{direction.id}"
                        subject_lesson_types[key] = lessons
            else:
                # Talaba uchun - oddiy format
                subject = subject_data_item if not isinstance(subject_data_item, dict) else subject_data_item.get('subject', subject_data_item)
                # Talaba uchun kod allaqachon yuqorida bajarilgan
    
    # Talaba uchun har bir fan bo'yicha ballar (barcha dars turlari uchun)
    subject_grades = {}
    if current_user.role == 'student' and current_user.group_id:
        group = Group.query.get(current_user.group_id)
        for subject in subjects_for_processing:
            # Fan bo'yicha barcha topshiriqlar
            assignments_query = Assignment.query.filter_by(
                subject_id=subject.id
            )
            if group and group.direction_id:
                assignments_query = assignments_query.filter(
                    (Assignment.group_id == current_user.group_id) | (Assignment.group_id.is_(None)),
                    (Assignment.direction_id == group.direction_id) | (Assignment.direction_id.is_(None))
                )
            else:
                assignments_query = assignments_query.filter_by(group_id=current_user.group_id)
            
            assignments = assignments_query.all()
            
            # Fanda mavjud bo'lgan dars turlarini aniqlash
            available_lesson_types = set()
            if group and group.direction_id:
                curriculum_item = DirectionCurriculum.query.filter_by(
                    direction_id=group.direction_id,
                    subject_id=subject.id
            ).first()
                if curriculum_item:
                    if curriculum_item.hours_maruza and curriculum_item.hours_maruza > 0:
                        available_lesson_types.add('maruza')
                    if curriculum_item.hours_amaliyot and curriculum_item.hours_amaliyot > 0:
                        available_lesson_types.add('amaliyot')
                    if curriculum_item.hours_laboratoriya and curriculum_item.hours_laboratoriya > 0:
                        available_lesson_types.add('laboratoriya')
                    if curriculum_item.hours_seminar and curriculum_item.hours_seminar > 0:
                        available_lesson_types.add('seminar')
                    if curriculum_item.hours_kurs_ishi and curriculum_item.hours_kurs_ishi > 0:
                        available_lesson_types.add('kurs_ishi')
            
            # Faqat mavjud bo'lgan dars turlari uchun ballarni hisoblash
            grades_by_type = {}
            for lesson_type in ['maruza', 'amaliyot', 'laboratoriya', 'seminar', 'kurs_ishi']:
                if lesson_type in available_lesson_types:
                    grades_by_type[lesson_type] = {'score': 0, 'max': 0}
            
            for assignment in assignments:
                submission = Submission.query.filter_by(
                    student_id=current_user.id,
                    assignment_id=assignment.id,
                    is_active=True
                ).first()
                
                if submission and submission.score is not None:
                    # Topshiriqning dars turini aniqlash
                    lesson_type = assignment.lesson_type
                    
                    # Agar lesson_type bo'sh bo'lsa, o'qituvchi biriktirishiga qarab aniqlash
                    if not lesson_type:
                        assignment_creator = User.query.get(assignment.created_by) if assignment.created_by else None
                        if assignment_creator:
                            teacher_subject = TeacherSubject.query.filter_by(
                                subject_id=subject.id,
                                group_id=current_user.group_id,
                                teacher_id=assignment_creator.id
                            ).first()
                            if teacher_subject:
                                lesson_type = teacher_subject.lesson_type
                    
                    # Agar hali ham aniqlanmagan bo'lsa, topshiriq nomiga qarab
                    if not lesson_type:
                        assignment_title_lower = assignment.title.lower()
                        if 'amaliy' in assignment_title_lower or 'amaliyot' in assignment_title_lower:
                            lesson_type = 'amaliyot'
                        elif 'laboratoriya' in assignment_title_lower or 'lab' in assignment_title_lower:
                            lesson_type = 'laboratoriya'
                        elif 'seminar' in assignment_title_lower:
                            lesson_type = 'seminar'
                        elif 'kurs' in assignment_title_lower or 'kurs ishi' in assignment_title_lower:
                            lesson_type = 'kurs_ishi'
                        else:
                            lesson_type = 'maruza'  # Default
                    
                    # Laboratoriya va kurs_ishi uchun amaliyot o'qituvchisidan ham baholanishi mumkin
                    if lesson_type in ['laboratoriya', 'kurs_ishi']:
                        # Avval to'g'ridan-to'g'ri lesson_type bo'yicha qidirish
                        if lesson_type in grades_by_type:
                            grades_by_type[lesson_type]['score'] += submission.score
                            grades_by_type[lesson_type]['max'] += assignment.max_score
                        # Agar assignment.lesson_type bo'sh bo'lsa va amaliyot o'qituvchisi baholagan bo'lsa
                        elif not assignment.lesson_type:
                            # Amaliyot o'qituvchisi bilan tekshirish
                            assignment_creator = User.query.get(assignment.created_by) if assignment.created_by else None
                            if assignment_creator:
                                amaliyot_teacher = TeacherSubject.query.filter_by(
                                    subject_id=subject.id,
                                    group_id=current_user.group_id,
                                    teacher_id=assignment_creator.id,
                                    lesson_type='amaliyot'
                                ).first()
                                if amaliyot_teacher:
                                    grades_by_type['amaliyot']['score'] += submission.score
                                    grades_by_type['amaliyot']['max'] += assignment.max_score
                                else:
                                    grades_by_type[lesson_type]['score'] += submission.score
                                    grades_by_type[lesson_type]['max'] += assignment.max_score
                    else:
                        # Boshqa dars turlari uchun
                        if lesson_type in grades_by_type:
                            grades_by_type[lesson_type]['score'] += submission.score
                            grades_by_type[lesson_type]['max'] += assignment.max_score
            
            # Jami ballarni hisoblash
            total_score = sum(g['score'] for g in grades_by_type.values())
            total_max = sum(g['max'] for g in grades_by_type.values())
            
            # Faqat mavjud bo'lgan dars turlarini qo'shish
            subject_grades[subject.id] = {
                'available_types': list(available_lesson_types),  # Set ni list ga o'zgartirish
                'total': {'score': total_score, 'max': total_max}
            }
            # Har bir mavjud dars turi uchun baholarni qo'shish
            for lesson_type in ['maruza', 'amaliyot', 'laboratoriya', 'seminar', 'kurs_ishi']:
                if lesson_type in grades_by_type:
                    subject_grades[subject.id][lesson_type] = grades_by_type[lesson_type]
    
    return render_template('courses/index.html', 
                         subjects=subjects, 
                         search=search, 
                         subject_grades=subject_grades, 
                         subject_lesson_types=subject_lesson_types,
                         subjects_by_semester=subjects_by_semester)


@bp.route('/<int:id>')
@login_required
def detail(id):
    """Fan tafsilotlari"""
    subject = Subject.query.get_or_404(id)
    
    # Yo'nalish ID (o'qituvchi uchun)
    direction_id = request.args.get('direction_id', type=int)
    
    # Barcha rollar uchun direction va groups ma'lumotlarini olish
    direction = None
    direction_groups = []
    direction_semester = None
    direction_credits = None
    
    # O'qituvchi uchun
    if (current_user.role == 'teacher' or current_user.has_role('teacher')) and direction_id:
        direction = Direction.query.get(direction_id)
        if direction:
            # O'qituvchiga biriktirilgan guruhlar
            teacher_groups_query = TeacherSubject.query.filter_by(
                teacher_id=current_user.id,
                subject_id=subject.id
            )
            direction_group_ids = [g.id for g in Group.query.filter_by(direction_id=direction_id).all()]
            groups_without_direction = [g.id for g in Group.query.filter(Group.direction_id.is_(None)).all()]
            allowed_group_ids = direction_group_ids + groups_without_direction
            teacher_groups = teacher_groups_query.filter(TeacherSubject.group_id.in_(allowed_group_ids)).all()
            # Guruhlarni unique qilish (takrorlanmasligi uchun) - avval id bo'yicha, keyin name bo'yicha
            seen_group_ids = set()
            seen_group_names = set()
            direction_groups = []
            for tg in teacher_groups:
                if tg.group and tg.group.id not in seen_group_ids and tg.group.name not in seen_group_names:
                    direction_groups.append(tg.group)
                    seen_group_ids.add(tg.group.id)
                    seen_group_names.add(tg.group.name)
            
            # Semestr va kredit ma'lumotlarini olish
            curriculum_item = DirectionCurriculum.query.filter_by(
                direction_id=direction_id,
                subject_id=subject.id
            ).first()
            if curriculum_item:
                direction_semester = curriculum_item.semester
                # Kreditni hisoblash (jami soat / 30) - yaxlitlamasdan
                total_hours = (curriculum_item.hours_maruza or 0) + (curriculum_item.hours_amaliyot or 0) + \
                             (curriculum_item.hours_laboratoriya or 0) + (curriculum_item.hours_seminar or 0) + \
                             (curriculum_item.hours_mustaqil or 0)
                direction_credits = total_hours / 30 if total_hours > 0 else 0
    # Talaba uchun - ularning guruhidan direction olish
    elif current_user.role == 'student' and current_user.group_id:
        group = Group.query.get(current_user.group_id)
        if group and group.direction_id:
            direction = Direction.query.get(group.direction_id)
            if direction:
                # Talabaning guruhini ko'rsatish
                direction_groups = [group] if group else []
                
                # Semestr va kredit ma'lumotlarini olish
                curriculum_item = DirectionCurriculum.query.filter_by(
                    direction_id=group.direction_id,
                    subject_id=subject.id
                ).first()
                if curriculum_item:
                    direction_semester = curriculum_item.semester
                    # Kreditni hisoblash (jami soat / 30) - yaxlitlamasdan
                    total_hours = (curriculum_item.hours_maruza or 0) + (curriculum_item.hours_amaliyot or 0) + \
                                 (curriculum_item.hours_laboratoriya or 0) + (curriculum_item.hours_seminar or 0) + \
                                 (curriculum_item.hours_mustaqil or 0)
                    direction_credits = total_hours / 30 if total_hours > 0 else 0
    
    # Guruhlarni to'ldirish (agar hali to'lmagan bo'lsa - admin yoki teacher uchun direction_id'siz)
    if not direction_groups:
        if current_user.role in ['admin', 'dean']:
            # Admin yoki dekan uchun fanga biriktirilgan barcha guruhlar
            # 1. O'quv rejasida bor guruhlar
            curriculum_groups = Group.query.join(DirectionCurriculum, Group.direction_id == DirectionCurriculum.direction_id)\
                                           .filter(DirectionCurriculum.subject_id == subject.id).all()
            # 2. To'g'ridan-to'g'ri biriktirilgan guruhlar (TeacherSubject orqali)
            ts_groups = Group.query.join(TeacherSubject, Group.id == TeacherSubject.group_id)\
                                   .filter(TeacherSubject.subject_id == subject.id).all()
            
            unique_groups = {g.id: g for g in curriculum_groups + ts_groups}.values()
            direction_groups = list(unique_groups)
        elif current_user.role == 'teacher' or current_user.has_role('teacher'):
            # O'qituvchi uchun o'zi dars beradigan barcha guruhlar
            teacher_subjects = TeacherSubject.query.filter_by(teacher_id=current_user.id, subject_id=subject.id).all()
            seen_ids = set()
            for ts in teacher_subjects:
                if ts.group and ts.group.id not in seen_ids:
                    direction_groups.append(ts.group)
                    seen_ids.add(ts.group.id)
    
    # Tanlangan rol
    current_role = session.get('current_role', current_user.role)
    
    # Tekshirish: foydalanuvchi bu fanni ko'rishi mumkinmi
    can_view = False
    is_teacher = False
    my_group = None
    
    if current_user.role == 'admin' or current_user.role == 'dean':
        can_view = True
    elif current_user.role == 'teacher' or current_user.has_role('teacher'):
        teaching = TeacherSubject.query.filter_by(
            teacher_id=current_user.id,
            subject_id=subject.id
        ).first()
        can_view = teaching is not None
    elif current_user.role == 'student' and current_user.group_id:
        teaching = TeacherSubject.query.filter_by(
            group_id=current_user.group_id,
            subject_id=subject.id
        ).first()
        can_view = teaching is not None
        my_group = current_user.group
    
    if not can_view:
        flash("Sizda bu fanni ko'rish huquqi yo'q", 'error')
        return redirect(url_for('courses.index'))

    # Acting role check for permissions
    is_teacher = False
    if current_role == 'teacher':
        # Verify they are actually assigned to this subject (regardless of their base role)
        teaching = TeacherSubject.query.filter_by(
            teacher_id=current_user.id,
            subject_id=subject.id
        ).first()
        if teaching:
            is_teacher = True

    # Fan bo'yicha boshqaruv huquqi (Dars/Topshiriq qo'shish)
    can_manage_subject = False
    if (current_user.role == 'admin' or current_user.role == 'dean') and current_role != 'teacher':
        can_manage_subject = True
    elif is_teacher:
        can_manage_subject = True
    
    # Darslarni group_id va direction_id bo'yicha filtrlash
    if current_user.role == 'student' and current_user.group_id:
        # Talaba uchun faqat o'z guruhining darslarini ko'rsatish
        group = Group.query.get(current_user.group_id)
        if group and group.direction_id:
            # Agar guruh yo'nalishga biriktirilgan bo'lsa, faqat shu yo'nalishdagi darslar
            all_lessons = subject.lessons.filter(
                ((Lesson.group_id == current_user.group_id) | (Lesson.group_id.is_(None))) &
                ((Lesson.direction_id == group.direction_id) | (Lesson.direction_id.is_(None)))
            ).order_by(Lesson.order).all()
        else:
            # Agar guruh yo'nalishga biriktirilmagan bo'lsa, faqat guruh bo'yicha
            all_lessons = subject.lessons.filter(
                (Lesson.group_id == current_user.group_id) | (Lesson.group_id.is_(None))
            ).order_by(Lesson.order).all()
    elif current_user.role == 'teacher' or current_user.has_role('teacher'):
        # O'qituvchi uchun faqat o'ziga biriktirilgan guruhlarning darslarini ko'rsatish
        # Agar direction_id berilgan bo'lsa, faqat shu yo'nalishdagi darslar
        teacher_groups = TeacherSubject.query.filter_by(
            teacher_id=current_user.id,
            subject_id=subject.id
        ).all()
        group_ids = [tg.group_id for tg in teacher_groups if tg.group_id]
        
        if direction_id:
            # Faqat shu yo'nalishdagi darslar
            if group_ids:
                all_lessons = subject.lessons.filter(
                    ((Lesson.group_id.in_(group_ids)) | (Lesson.group_id.is_(None))) &
                    ((Lesson.direction_id == direction_id) | (Lesson.direction_id.is_(None)))
                ).order_by(Lesson.order).all()
            else:
                all_lessons = subject.lessons.filter(
                    (Lesson.direction_id == direction_id) | (Lesson.direction_id.is_(None))
                ).order_by(Lesson.order).all()
        else:
            # direction_id berilmagan bo'lsa, faqat guruh bo'yicha
            if group_ids:
                all_lessons = subject.lessons.filter(
                    (Lesson.group_id.in_(group_ids)) | (Lesson.group_id.is_(None))
                ).order_by(Lesson.order).all()
            else:
                all_lessons = subject.lessons.filter(Lesson.group_id.is_(None)).order_by(Lesson.order).all()
    else:
        # Admin va dekan uchun barcha darslar
        all_lessons = subject.lessons.order_by(Lesson.order).all()
    
    # Barcha dars turlari bo'yicha ajratish
    maruza_lessons = [l for l in all_lessons if l.lesson_type == 'maruza']
    amaliyot_lessons = [l for l in all_lessons if l.lesson_type == 'amaliyot']
    laboratoriya_lessons = [l for l in all_lessons if l.lesson_type == 'laboratoriya']
    seminar_lessons = [l for l in all_lessons if l.lesson_type == 'seminar']
    kurs_ishi_lessons = [l for l in all_lessons if l.lesson_type == 'kurs_ishi']
    
    # Talaba uchun: qaysi darslar qulflanganligini aniqlash
    lesson_locked_status = {}
    if current_user.role == 'student' and current_user.group_id:
        for lesson in all_lessons:
            # Faqat videoga ega darslar uchun qulf tekshiruvi
            if lesson.video_file or lesson.video_url:
                # Bir xil fan, dars turi va guruhdagi oldingi darslarni olish
                previous_lessons = Lesson.query.filter(
                    Lesson.subject_id == subject.id,
                    Lesson.lesson_type == lesson.lesson_type,
                    Lesson.order < lesson.order,
                    ((Lesson.group_id == current_user.group_id) | (Lesson.group_id.is_(None)))
                ).order_by(Lesson.order).all()
                
                is_locked = False
                for prev_lesson in previous_lessons:
                    if prev_lesson.video_file or prev_lesson.video_url:
                        prev_lesson_view = LessonView.query.filter_by(
                            lesson_id=prev_lesson.id,
                            student_id=current_user.id
                        ).first()
                        
                        if not prev_lesson_view or not prev_lesson_view.is_completed:
                            is_locked = True
                            break
                
                lesson_locked_status[lesson.id] = is_locked
            else:
                lesson_locked_status[lesson.id] = False
    
    # Topshiriqlar
    if current_user.role == 'student' and current_user.group_id:
        # Talaba uchun - faqat o'z guruhining topshiriqlari
        assignments_query = subject.assignments.filter_by(group_id=current_user.group_id)
        # Agar direction_id berilgan bo'lsa, shu yo'nalishga tegishli topshiriqlar
        if direction_id:
            assignments_query = assignments_query.filter(
                (Assignment.direction_id == direction_id) | (Assignment.direction_id.is_(None))
            )
        assignments = assignments_query.all()
    elif current_user.role == 'teacher' or current_user.has_role('teacher'):
        # O'qituvchi o'zi dars beradigan guruhlarning topshiriqlarini ko'radi
        # Agar direction_id berilgan bo'lsa, faqat shu yo'nalishdagi guruhlar
        teacher_groups_query = TeacherSubject.query.filter_by(
            teacher_id=current_user.id,
            subject_id=subject.id
        )
        
        if direction_id:
            # Faqat shu yo'nalishdagi guruhlar
            direction_group_ids = [g.id for g in Group.query.filter_by(direction_id=direction_id).all()]
            teacher_groups = teacher_groups_query.filter(TeacherSubject.group_id.in_(direction_group_ids)).all()
        else:
            teacher_groups = teacher_groups_query.all()
        
        group_ids = [ts.group_id for ts in teacher_groups if ts.group_id]
        if group_ids:
            assignments_query = subject.assignments.filter(
                (Assignment.group_id.in_(group_ids)) | (Assignment.group_id.is_(None))
            )
            # Agar direction_id berilgan bo'lsa, shu yo'nalishga tegishli topshiriqlar
            if direction_id:
                assignments_query = assignments_query.filter(
                    (Assignment.direction_id == direction_id) | (Assignment.direction_id.is_(None))
                )
            assignments = assignments_query.all()
        else:
            assignments_query = subject.assignments.filter(Assignment.group_id.is_(None))
            if direction_id:
                assignments_query = assignments_query.filter(
                    (Assignment.direction_id == direction_id) | (Assignment.direction_id.is_(None))
                )
            assignments = assignments_query.all()
    else:
        assignments_query = subject.assignments
        # Agar direction_id berilgan bo'lsa, shu yo'nalishga tegishli topshiriqlar
        if direction_id:
            assignments_query = assignments_query.filter(
                (Assignment.direction_id == direction_id) | (Assignment.direction_id.is_(None))
            )
        assignments = assignments_query.all()
    
    # Talaba uchun topshiriqlar holati va ballar
    assignment_status = {}
    assignment_hours_left = {}  # Topshiriqlar uchun qolgan soatlar
    student_grades = None
    now_dt = get_tashkent_time()
    if current_user.role == 'student':
        for assignment in assignments:
            # Batafsil ma'lumot olish
            all_subs = Submission.query.filter_by(
                student_id=current_user.id,
                assignment_id=assignment.id
            ).order_by(Submission.submitted_at.desc()).all()
            
            latest_sub = all_subs[0] if all_subs else None
            is_any_graded = any(s.score is not None for s in all_subs)
            remaining_attempts = 3 - len(all_subs)
            if remaining_attempts < 0: remaining_attempts = 0
            
            assignment_status[assignment.id] = {
                'latest_sub': latest_sub,
                'is_any_graded': is_any_graded,
                'remaining_attempts': remaining_attempts,
                'has_subs': bool(all_subs)
            }
            
            # Qolgan soatlarni hisoblash
            if assignment.due_date:
                assignment_due = assignment.due_date.replace(tzinfo=None) if assignment.due_date.tzinfo else assignment.due_date
                now_clean = now_dt.replace(tzinfo=None) if now_dt.tzinfo else now_dt
                # Deadline kun oxirigacha (23:59:59) hisoblanadi
                if isinstance(assignment_due, datetime):
                    deadline_end = assignment_due.replace(hour=23, minute=59, second=59)
                else:
                    from datetime import time as dt_time
                    deadline_end = datetime.combine(assignment_due, dt_time(23, 59, 59))
                time_left = deadline_end - now_clean
                hours_left = time_left.total_seconds() / 3600
                if hours_left < 0:
                    hours_left = 0
                assignment_hours_left[assignment.id] = hours_left
            else:
                assignment_hours_left[assignment.id] = None
        
        # Ballarni hisoblash: amaliy, maruza va jami
        # O'qituvchi biriktirishlari bo'yicha
        maruza_teacher = TeacherSubject.query.filter_by(
            subject_id=subject.id,
            group_id=current_user.group_id,
            lesson_type='maruza'
        ).first()
        
        amaliyot_teacher = TeacherSubject.query.filter_by(
            subject_id=subject.id,
            group_id=current_user.group_id,
            lesson_type='amaliyot'
        ).first()
        
        maruza_score = 0
        maruza_max = 0
        amaliyot_score = 0
        amaliyot_max = 0
        
        for assignment in assignments:
            status_dict = assignment_status.get(assignment.id)
            if status_dict and status_dict.get('latest_sub') and status_dict['latest_sub'].score is not None:
                submission = status_dict['latest_sub']
                # Topshiriq qaysi o'qituvchiga tegishli ekanligini aniqlash
                assignment_creator = User.query.get(assignment.created_by) if assignment.created_by else None
                
                is_maruza = False
                is_amaliyot = False
                
                if maruza_teacher and assignment_creator and assignment_creator.id == maruza_teacher.teacher_id:
                    is_maruza = True
                elif amaliyot_teacher and assignment_creator and assignment_creator.id == amaliyot_teacher.teacher_id:
                    is_amaliyot = True
                else:
                    # Agar o'qituvchi biriktirilmagan bo'lsa, topshiriq nomiga qarab aniqlash
                    assignment_title_lower = assignment.title.lower()
                    if 'amaliy' in assignment_title_lower or 'amaliyot' in assignment_title_lower:
                        is_amaliyot = True
                    else:
                        is_maruza = True
                
                if is_maruza:
                    maruza_score += submission.score
                    maruza_max += assignment.max_score
                elif is_amaliyot:
                    amaliyot_score += submission.score
                    amaliyot_max += assignment.max_score
        
        student_grades = {
            'maruza': {'score': maruza_score, 'max': maruza_max},
            'amaliyot': {'score': amaliyot_score, 'max': amaliyot_max},
            'total': {'score': maruza_score + amaliyot_score, 'max': maruza_max + amaliyot_max}
        }
    
    # Fan bo'yicha o'qituvchilar - barcha o'qituvchilar bitta ro'yxatda (takrorlanmas)
    all_teachers_list = []
    teacher_lesson_types = {}  # Har bir o'qituvchi uchun biriktirilgan dars turlari (faqat tanlangan yo'nalish uchun)
    
    lesson_type_names = {
        'maruza': 'Maruza',
        'amaliyot': 'Amaliyot',
        'laboratoriya': 'Laboratoriya',
        'seminar': 'Seminar',
        'kurs_ishi': 'Kurs ishi'
    }
    
    # Yo'nalish bo'yicha filtrlash uchun guruh ID'lari
    target_direction_id = direction_id
    if not target_direction_id and current_user.role == 'student' and current_user.group_id:
        # Talaba uchun - uning guruhining yo'nalishini olish
        group = Group.query.get(current_user.group_id)
        if group and group.direction_id:
            target_direction_id = group.direction_id
    
    # all_teacher_assignments filtrlash - yo'nalish bo'yicha
    is_direction_filtered = False  # Agar allaqachon yo'nalish bo'yicha filtr qilingan bo'lsa
    
    if current_user.role == 'student' and current_user.group_id:
        # Talaba uchun faqat o'z guruhidagi o'qituvchilar
        all_teacher_assignments = TeacherSubject.query.filter_by(
            subject_id=subject.id,
            group_id=current_user.group_id
        ).all()
        # Agar talabaning guruhi yo'nalishga biriktirilgan bo'lsa, filtr qilingan deb hisoblaymiz
        if target_direction_id:
            group = Group.query.get(current_user.group_id)
            if group and group.direction_id == target_direction_id:
                is_direction_filtered = True
    else:
        # O'qituvchi, dekan, admin uchun o'qituvchilar
        # Agar direction_id bo'lsa, faqat shu yo'nalishdagi guruhlarga biriktirilgan o'qituvchilar
        if direction_id:
            # Shu yo'nalishdagi guruhlar
            direction_group_ids = [g.id for g in Group.query.filter_by(direction_id=direction_id).all()]
            
            # Faqat shu yo'nalishdagi guruhlarga biriktirilgan o'qituvchilar
            all_teacher_assignments = TeacherSubject.query.filter_by(
                subject_id=subject.id
            ).filter(TeacherSubject.group_id.in_(direction_group_ids)).all()
            is_direction_filtered = True  # Allaqachon filtr qilingan
        else:
            # direction_id bo'lmasa, barcha o'qituvchilar
            all_teacher_assignments = subject.teacher_assignments.all()
        
    # O'quv rejadan qaysi dars turlari mavjud ekanligini aniqlash
    allowed_lesson_types = set()  # O'quv rejada mavjud dars turlari
    curriculum_item = None
    
    if target_direction_id:
        curriculum_item = DirectionCurriculum.query.filter_by(
            direction_id=target_direction_id,
            subject_id=subject.id
        ).first()
        
        if curriculum_item:
            # O'quv rejada qaysi dars turlari bor ekanligini tekshirish
            if (curriculum_item.hours_maruza or 0) > 0:
                allowed_lesson_types.add('maruza')
            if (curriculum_item.hours_amaliyot or 0) > 0:
                allowed_lesson_types.add('amaliyot')
            if (curriculum_item.hours_laboratoriya or 0) > 0:
                allowed_lesson_types.add('laboratoriya')
            if (curriculum_item.hours_seminar or 0) > 0:
                allowed_lesson_types.add('seminar')
            if (curriculum_item.hours_kurs_ishi or 0) > 0:
                allowed_lesson_types.add('kurs_ishi')
    else:
        # Yo'nalish tanlanmagan bo'lsa, barcha dars turlarini ruxsat berish
        allowed_lesson_types = {'maruza', 'amaliyot', 'laboratoriya', 'seminar', 'kurs_ishi'}
    
    # Barcha o'qituvchilarni to'plash va takrorlanmas qilish
    seen_teacher_ids = set()
    for ta in all_teacher_assignments:
        if ta.teacher_id not in seen_teacher_ids:
            seen_teacher_ids.add(ta.teacher_id)
            all_teachers_list.append(ta.teacher)
            teacher_lesson_types[ta.teacher_id] = []
        
        # Agar yo'nalish bo'yicha filtr qilingan bo'lsa, barcha biriktirishlar allaqachon shu yo'nalishga tegishli
        # Agar yo'nalish bo'yicha filtr qilinmagan bo'lsa yoki qayta tekshirish kerak bo'lsa
        should_add_lesson_type = False
        
        if is_direction_filtered:
            # Allaqachon filtr qilingan, barcha biriktirishlar shu yo'nalishga tegishli
            should_add_lesson_type = True
        elif target_direction_id:
            # Yo'nalish tanlangan, lekin filtr qilinmagan - qayta tekshirish kerak
            group = Group.query.get(ta.group_id) if ta.group_id else None
            if group and group.direction_id == target_direction_id:
                should_add_lesson_type = True
        else:
            # Yo'nalish tanlanmagan, barcha dars turlarini qo'shish
            should_add_lesson_type = True
        
        # Faqat o'quv rejada mavjud bo'lgan dars turlarini ko'rsatish
        if should_add_lesson_type and ta.lesson_type in allowed_lesson_types:
            lesson_type_name = lesson_type_names.get(ta.lesson_type, ta.lesson_type.capitalize())
            if lesson_type_name not in teacher_lesson_types[ta.teacher_id]:
                teacher_lesson_types[ta.teacher_id].append(lesson_type_name)
    
    # Agar yo'nalish tanlangan bo'lsa, DirectionCurriculum jadvalidan "laboratoriya" va "kurs_ishi" soatlarini tekshirish
    # va agar bu dars turlari uchun o'qituvchi biriktirilgan bo'lsa, ularni ham ko'rsatish
    if target_direction_id and curriculum_item:
            # Talaba uchun faqat uning guruhini, boshqalar uchun barcha yo'nalish guruhlarini olish
            if current_user.role == 'student' and current_user.group_id:
                target_group_ids = [current_user.group_id]
            else:
                # Bu yo'nalish uchun guruhlarni olish
                direction_groups = Group.query.filter_by(direction_id=target_direction_id).all()
                target_group_ids = [g.id for g in direction_groups]
            
            # Laboratoriya tekshiruvi
            if (curriculum_item.hours_laboratoriya or 0) > 0:
                # Laboratoriya uchun o'qituvchini qidirish
                lab_teacher_assignment = TeacherSubject.query.filter(
                    TeacherSubject.subject_id == subject.id,
                    TeacherSubject.group_id.in_(target_group_ids),
                    TeacherSubject.lesson_type == 'laboratoriya'
                ).first()
                
                if not lab_teacher_assignment:
                    # Agar alohida laboratoriya biriktirishi yo'q bo'lsa, amaliyot o'qituvchisini qidirish
                    lab_teacher_assignment = TeacherSubject.query.filter(
                        TeacherSubject.subject_id == subject.id,
                        TeacherSubject.group_id.in_(target_group_ids),
                        TeacherSubject.lesson_type == 'amaliyot'
                    ).first()
                
                if lab_teacher_assignment and lab_teacher_assignment.teacher_id in seen_teacher_ids:
                    if 'Laboratoriya' not in teacher_lesson_types[lab_teacher_assignment.teacher_id]:
                        teacher_lesson_types[lab_teacher_assignment.teacher_id].append('Laboratoriya')
            
            # Kurs ishi tekshiruvi
            if (curriculum_item.hours_kurs_ishi or 0) > 0:
                # Kurs ishi uchun o'qituvchini qidirish
                kurs_teacher_assignment = TeacherSubject.query.filter(
                    TeacherSubject.subject_id == subject.id,
                    TeacherSubject.group_id.in_(target_group_ids),
                    TeacherSubject.lesson_type == 'kurs_ishi'
                ).first()
                
                if not kurs_teacher_assignment:
                    # Agar alohida kurs_ishi biriktirishi yo'q bo'lsa, amaliyot o'qituvchisini qidirish
                    kurs_teacher_assignment = TeacherSubject.query.filter(
                        TeacherSubject.subject_id == subject.id,
                        TeacherSubject.group_id.in_(target_group_ids),
                        TeacherSubject.lesson_type == 'amaliyot'
                    ).first()
                
                if kurs_teacher_assignment and kurs_teacher_assignment.teacher_id in seen_teacher_ids:
                    if 'Kurs ishi' not in teacher_lesson_types[kurs_teacher_assignment.teacher_id]:
                        teacher_lesson_types[kurs_teacher_assignment.teacher_id].append('Kurs ishi')
    
    # Eski formatni saqlash (template uchun)
    maruza_teachers = []
    amaliyot_teachers = []
    laboratoriya_teachers = []
    seminar_teachers = []
    kurs_ishi_teachers = []
    
    # Dars turlarini olish (o'qituvchi va talaba uchun)
    lesson_types = []
    direction_lesson_types = []  # Yo'nalish uchun dars turlari (header'da ko'rsatish uchun)
    
    # Agar direction_id bo'lsa, aynan shu yo'nalish uchun dars turlarini olish
    if direction and direction_id:
        curriculum_item = DirectionCurriculum.query.filter_by(
            direction_id=direction_id,
            subject_id=subject.id
        ).first()
        
        if curriculum_item:
            # Maruza
            if curriculum_item.hours_maruza and curriculum_item.hours_maruza > 0:
                direction_lesson_types.append({
                    'type': 'Maruza',
                    'hours': curriculum_item.hours_maruza
                })
            
            # Amaliyot
            if curriculum_item.hours_amaliyot and curriculum_item.hours_amaliyot > 0:
                direction_lesson_types.append({
                    'type': 'Amaliyot',
                    'hours': curriculum_item.hours_amaliyot
                })
            
            # Laboratoriya - alohida ko'rsatish
            if curriculum_item.hours_laboratoriya and curriculum_item.hours_laboratoriya > 0:
                direction_lesson_types.append({
                    'type': 'Laboratoriya',
                    'hours': curriculum_item.hours_laboratoriya
                })
            
            # Seminar
            if curriculum_item.hours_seminar and curriculum_item.hours_seminar > 0:
                direction_lesson_types.append({
                    'type': 'Seminar',
                    'hours': curriculum_item.hours_seminar
                })
            
            # Kurs ishi
            if curriculum_item.hours_kurs_ishi and curriculum_item.hours_kurs_ishi > 0:
                direction_lesson_types.append({
                    'type': 'Kurs ishi',
                    'hours': 0
                })
    
    # Talaba uchun ham dars turlarini ko'rsatish
    elif current_user.role == 'student' and direction:
        curriculum_item = DirectionCurriculum.query.filter_by(
            direction_id=direction.id,
            subject_id=subject.id
        ).first()

        if curriculum_item:
            # Maruza
            if curriculum_item.hours_maruza and curriculum_item.hours_maruza > 0:
                direction_lesson_types.append({
                    'type': 'Maruza',
                    'hours': curriculum_item.hours_maruza
                })

            # Amaliyot
            if curriculum_item.hours_amaliyot and curriculum_item.hours_amaliyot > 0:
                direction_lesson_types.append({
                    'type': 'Amaliyot',
                    'hours': curriculum_item.hours_amaliyot
                })

            # Laboratoriya - alohida ko'rsatish
            if curriculum_item.hours_laboratoriya and curriculum_item.hours_laboratoriya > 0:
                direction_lesson_types.append({
                    'type': 'Laboratoriya',
                    'hours': curriculum_item.hours_laboratoriya
                })

            # Seminar
            if curriculum_item.hours_seminar and curriculum_item.hours_seminar > 0:
                direction_lesson_types.append({
                    'type': 'Seminar',
                    'hours': curriculum_item.hours_seminar
                })

            # Kurs ishi
            if curriculum_item.hours_kurs_ishi and curriculum_item.hours_kurs_ishi > 0:
                direction_lesson_types.append({
                    'type': 'Kurs ishi',
                    'hours': 0
                })
    
    if current_user.role == 'student' and current_user.group_id:
        # Talaba uchun
        group = Group.query.get(current_user.group_id)
        if group and group.direction_id:
            curriculum_items = DirectionCurriculum.query.filter_by(
                direction_id=group.direction_id,
                subject_id=subject.id
            ).all()
            
            for item in curriculum_items:
                # Maruza
                if item.hours_maruza and item.hours_maruza > 0:
                    teacher_subject = TeacherSubject.query.filter_by(
                        subject_id=subject.id,
                        group_id=current_user.group_id,
                        lesson_type='maruza'
                    ).first()
                    lesson_types.append({
                        'type': 'Maruza',
                        'hours': item.hours_maruza,
                        'teacher': teacher_subject.teacher if teacher_subject else None
                    })
                
                # Amaliyot
                amaliyot_hours = (item.hours_amaliyot or 0) + (item.hours_laboratoriya or 0)
                if amaliyot_hours > 0:
                    teacher_subject = TeacherSubject.query.filter_by(
                        subject_id=subject.id,
                        group_id=current_user.group_id,
                        lesson_type='amaliyot'
                    ).first()
                    lesson_types.append({
                        'type': 'Amaliyot',
                        'hours': amaliyot_hours,
                        'teacher': teacher_subject.teacher if teacher_subject else None
                    })
                elif (item.hours_laboratoriya or 0) > 0:
                    teacher_subject = TeacherSubject.query.filter_by(
                        subject_id=subject.id,
                        group_id=current_user.group_id,
                        lesson_type='amaliyot'
                    ).first()
                    lesson_types.append({
                        'type': 'Amaliyot',
                        'hours': item.hours_laboratoriya,
                        'teacher': teacher_subject.teacher if teacher_subject else None
                    })
                
                # Seminar
                if item.hours_seminar and item.hours_seminar > 0:
                    teacher_subject = TeacherSubject.query.filter_by(
                        subject_id=subject.id,
                        group_id=current_user.group_id,
                        lesson_type='seminar'
                    ).first()
                    if not teacher_subject:
                        teacher_subject = TeacherSubject.query.filter_by(
                            subject_id=subject.id,
                            group_id=current_user.group_id,
                            lesson_type='amaliyot'
                        ).first()
                    lesson_types.append({
                        'type': 'Seminar',
                        'hours': item.hours_seminar,
                        'teacher': teacher_subject.teacher if teacher_subject else None
                    })
    elif current_user.role == 'teacher' or current_user.has_role('teacher'):
        # O'qituvchi uchun
        teacher_subjects = TeacherSubject.query.filter_by(
            teacher_id=current_user.id,
            subject_id=subject.id
        ).all()
        
        for ts in teacher_subjects:
            group = Group.query.get(ts.group_id)
            if group and group.direction_id:
                curriculum_items = DirectionCurriculum.query.filter_by(
                    direction_id=group.direction_id,
                    subject_id=subject.id
                ).all()
                
                for item in curriculum_items:
                    # Maruza
                    if item.hours_maruza and item.hours_maruza > 0 and ts.lesson_type == 'maruza':
                        lesson_types.append({
                            'type': 'Maruza',
                            'hours': item.hours_maruza,
                            'teacher': current_user,
                            'group': group
                        })
                    
                    # Amaliyot
                    amaliyot_hours = (item.hours_amaliyot or 0) + (item.hours_laboratoriya or 0)
                    if amaliyot_hours > 0 and ts.lesson_type == 'amaliyot':
                        lesson_types.append({
                            'type': 'Amaliyot',
                            'hours': amaliyot_hours,
                            'teacher': current_user,
                            'group': group
                        })
                    elif (item.hours_laboratoriya or 0) > 0 and ts.lesson_type == 'amaliyot':
                        lesson_types.append({
                            'type': 'Amaliyot',
                            'hours': item.hours_laboratoriya,
                            'teacher': current_user,
                            'group': group
                        })
                    
                    # Seminar
                    if item.hours_seminar and item.hours_seminar > 0 and ts.lesson_type == 'seminar':
                        lesson_types.append({
                            'type': 'Seminar',
                            'hours': item.hours_seminar,
                            'teacher': current_user,
                            'group': group
                        })
    
    # O'qituvchi uchun har bir topshiriq uchun submission statistika
    assignment_submission_stats = {}
    if (current_user.role == 'teacher' or current_user.has_role('teacher')) or current_user.role == 'admin':
        for assignment in assignments:
            # Faol submissions (oxirgi yuborilgan)
            active_submissions = assignment.submissions.filter_by(is_active=True).all()
            total_subs = len(active_submissions)
            ungraded_subs = len([s for s in active_submissions if s.score is None])
            assignment_submission_stats[assignment.id] = {
                'total': total_subs,
                'ungraded': ungraded_subs
            }
    
    lesson_edit_permissions = {}
    if (current_user.role == 'admin' or current_user.role == 'dean') and current_role != 'teacher':
        # Admin barcha darslarni edit qila oladi (agar o'qituvchi rolida bo'lmasa)
        for lesson in all_lessons:
            lesson_edit_permissions[lesson.id] = True
    elif is_teacher:
        # O'qituvchi rejimi (va o'qituvchi rolidagi admin/dekan)
        # Faqat o'ziga biriktirilgan dars turlarini edit qila oladi
        teacher_assigned_lesson_types = set()
        
        # O'qituvchining barcha biriktirishlarini olish
        teacher_assignments_query = TeacherSubject.query.filter_by(
            teacher_id=current_user.id,
            subject_id=subject.id
        )
        
        if direction_id:
            direction_group_ids = [g.id for g in Group.query.filter_by(direction_id=direction_id).all()]
            teacher_assignments_query = teacher_assignments_query.filter(TeacherSubject.group_id.in_(direction_group_ids))
            
        teacher_assignments = teacher_assignments_query.all()
        
        for ta in teacher_assignments:
            if ta.lesson_type:
                teacher_assigned_lesson_types.add(ta.lesson_type)
        
        # Laboratoriya va kurs_ishi uchun amaliyot orqali tekshirish (faqat direction_id bo'lsa)
        if direction_id:
            curriculum_item = DirectionCurriculum.query.filter_by(
                direction_id=direction_id,
                subject_id=subject.id
            ).first()
            
            if curriculum_item:
                if (curriculum_item.hours_laboratoriya or 0) > 0:
                    lab_teacher = TeacherSubject.query.filter(
                        TeacherSubject.subject_id == subject.id,
                        TeacherSubject.group_id.in_(direction_group_ids),
                        TeacherSubject.teacher_id == current_user.id,
                        TeacherSubject.lesson_type.in_(['laboratoriya', 'amaliyot'])
                    ).first()
                    if lab_teacher:
                        teacher_assigned_lesson_types.add('laboratoriya')
                
                if (curriculum_item.hours_kurs_ishi or 0) > 0:
                    kurs_teacher = TeacherSubject.query.filter(
                        TeacherSubject.subject_id == subject.id,
                        TeacherSubject.group_id.in_(direction_group_ids),
                        TeacherSubject.teacher_id == current_user.id,
                        TeacherSubject.lesson_type.in_(['kurs_ishi', 'amaliyot'])
                    ).first()
                    if kurs_teacher:
                        teacher_assigned_lesson_types.add('kurs_ishi')
        
        # Har bir dars uchun ruxsat tekshiruvi
        for lesson in all_lessons:
            can_edit = False
            # direction_id tekshiruvi: 
            # 1. Agar request direction_id bo'lsa, lesson.direction_id mos kelishi yoki None bo'lishi kerak
            # 2. Agar request direction_id bo'lmasa, lesson.lesson_type teacher_assigned_lesson_types ichida bo'lsa bo'ldi
            
            if direction_id:
                if lesson.direction_id == direction_id or lesson.direction_id is None:
                     if lesson.lesson_type in teacher_assigned_lesson_types:
                        can_edit = True
            else:
                # direction_id yo'q bo'lsa, dars turi o'qituvchiga biriktirilgan bo'lsa ruxsat beramiz
                # (Ehtimoliy muammo: Teacher Group A da Maruza o'qiydi, Group B da yo'q. Dars Group B uchun bo'lsa?)
                # Lekin all_lessons allaqachon filtrlangan (lines 660+).
                if lesson.lesson_type in teacher_assigned_lesson_types:
                    can_edit = True
                    
            lesson_edit_permissions[lesson.id] = can_edit
    else:
        # Boshqa rollar edit qila olmaydi
        for lesson in all_lessons:
            lesson_edit_permissions[lesson.id] = False
    
    # Topshiriqlar uchun ruxsatlar
    assignment_manage_permissions = {}
    # Topshiriqlar uchun ruxsatlar
    assignment_manage_permissions = {}
    if (current_user.role == 'admin' or current_user.role == 'dean') and current_role != 'teacher':
        for assignment in assignments:
            assignment_manage_permissions[assignment.id] = True
    elif is_teacher:
        # O'qituvchining fanga biriktirilgan guruh va dars turlari
        teacher_assignments = TeacherSubject.query.filter_by(
            teacher_id=current_user.id,
            subject_id=subject.id
        ).all()
        
        # (group_id, lesson_type) bo'yicha ruxsatlarni to'plash
        allowed_pairs = set()
        for ta in teacher_assignments:
            allowed_pairs.add((ta.group_id, ta.lesson_type))
            
        for assignment in assignments:
            # Ruxsat: Agar o'qituvchi o'zi yaratgan bo'lsa
            is_creator = (assignment.created_by == current_user.id)
            
            # Yoki biriktirilgan guruh va dars turi bo'yicha
            is_assigned_to_group = (assignment.group_id, assignment.lesson_type) in allowed_pairs
            
            # Global topshiriq bo'lsa (group_id is None), o'qituvchi fanga biriktirilgan bo'lsa ruxsat beramiz
            is_assigned_to_subject = False
            if assignment.group_id is None:
                is_assigned_to_subject = any(p[1] == assignment.lesson_type for p in allowed_pairs)
                # Laboratoriya va kurs_ishi uchun amaliyot orqali tekshirish
                if not is_assigned_to_subject and assignment.lesson_type in ['laboratoriya', 'kurs_ishi']:
                    is_assigned_to_subject = any(p[1] == 'amaliyot' for p in allowed_pairs)

            has_permission = is_creator or is_assigned_to_group or is_assigned_to_subject
            
            # Laboratoriya va kurs_ishi uchun amaliyot orqali tekshirish (guruh bo'yicha)
            if not has_permission and assignment.group_id is not None and assignment.lesson_type in ['laboratoriya', 'kurs_ishi']:
                has_permission = (assignment.group_id, 'amaliyot') in allowed_pairs
                
            assignment_manage_permissions[assignment.id] = has_permission
    else:
        for assignment in assignments:
            assignment_manage_permissions[assignment.id] = False

    # Talaba uchun topshiriqlar bo'yicha eng yuqori ballar
    assignment_highest_scores = {}
    if current_user.role == 'student':
        for assignment in assignments:
            scores = [s.score for s in assignment.submissions if s.student_id == current_user.id and s.score is not None]
            assignment_highest_scores[assignment.id] = max(scores) if scores else 0
    
    # Topshiriqlar muddati o'tganligini tekshirish (barcha rollar uchun)
    assignment_is_overdue = {}
    for assignment in assignments:
        if assignment.due_date:
            assignment_is_overdue[assignment.id] = datetime.utcnow() > assignment.due_date
        else:
            assignment_is_overdue[assignment.id] = False

    return render_template('courses/detail.html',
                         subject=subject,
                         lessons=all_lessons,
                         maruza_lessons=maruza_lessons,
                         amaliyot_lessons=amaliyot_lessons,
                         laboratoriya_lessons=laboratoriya_lessons,
                         seminar_lessons=seminar_lessons,
                         kurs_ishi_lessons=kurs_ishi_lessons,
                         assignments=assignments,
                         assignment_status=assignment_status,
                         assignment_hours_left=assignment_hours_left,
                         maruza_teachers=maruza_teachers,
                         amaliyot_teachers=amaliyot_teachers,
                         laboratoriya_teachers=laboratoriya_teachers,
                         seminar_teachers=seminar_teachers,
                         kurs_ishi_teachers=kurs_ishi_teachers,
                         is_teacher=is_teacher,
                         my_group=my_group,
                         student_grades=student_grades,
                         lesson_locked_status=lesson_locked_status,
                         lesson_types=lesson_types,
                         direction_id=direction_id,
                         direction=direction,
                         direction_groups=direction_groups,
                         direction_semester=direction_semester,
                         direction_credits=direction_credits,
                         direction_lesson_types=direction_lesson_types,
                         all_teachers_list=all_teachers_list,
                         teacher_lesson_types=teacher_lesson_types,
                         allowed_lesson_types=allowed_lesson_types,
                         lesson_edit_permissions=lesson_edit_permissions,
                         assignment_manage_permissions=assignment_manage_permissions,
                         assignment_submission_stats=assignment_submission_stats,
                         assignment_highest_scores=assignment_highest_scores,
                         assignment_is_overdue=assignment_is_overdue)


@bp.route('/<int:id>/lessons/create', methods=['GET', 'POST'])
@login_required
def create_lesson(id):
    """Yangi dars yaratish"""
    subject = Subject.query.get_or_404(id)
    
    # Yo'nalish ID (o'qituvchi uchun)
    direction_id = request.args.get('direction_id', type=int)
    
    # Tanlangan rol
    current_role = session.get('current_role', current_user.role)
    
    # Faqat o'qituvchi rolida va o'ziga biriktirilgan fanlar uchun
    is_teacher = TeacherSubject.query.filter_by(
        teacher_id=current_user.id,
        subject_id=subject.id
    ).first() is not None
    
    # Bir nechta rol belgilangan o'qituvchilar faqatgina o'qituvchi rolida o'ziga biriktirilgan fan uchun mavzu yarata olishi kerak
    if current_role != 'teacher' or not is_teacher:
        if current_user.role != 'admin':
            flash("Sizda dars yaratish uchun ruxsat yo'q. Faqat o'qituvchi rolida va o'ziga biriktirilgan fanlar uchun mavzu yarata olasiz.", 'error')
            return redirect(url_for('courses.detail', id=id, direction_id=direction_id))
    
    # O'qituvchiga biriktirilgan guruhlar
    # Agar direction_id berilgan bo'lsa, faqat shu yo'nalishdagi guruhlar
    teacher_groups_query = TeacherSubject.query.filter_by(
        teacher_id=current_user.id,
        subject_id=subject.id
    )
    
    if direction_id:
        # Faqat shu yo'nalishdagi guruhlar (groups_without_direction olib tashlandi)
        direction_group_ids = [g.id for g in Group.query.filter_by(direction_id=direction_id).all()]
        teacher_groups = teacher_groups_query.filter(TeacherSubject.group_id.in_(direction_group_ids)).all()
    else:
        teacher_groups = teacher_groups_query.all()
    
    # Takrorlanmas guruhlar
    seen_group_ids = set()
    groups = []
    for tg in teacher_groups:
        if tg.group and tg.group_id not in seen_group_ids:
            seen_group_ids.add(tg.group_id)
            groups.append(tg.group)
    
    # O'qituvchiga biriktirilgan dars turlarini topish (detail sahifadagi mantiq bilan bir xil)
    # Agar o'qituvchi roliga ega bo'lsa (admin ham o'qituvchi roliga ega bo'lishi mumkin), faqat biriktirilgan dars turlarini ko'rsatish
    allowed_lesson_types = []
    # Agar tanlangan rol o'qituvchi bo'lsa yoki asosiy rol o'qituvchi bo'lsa, biriktirilgan dars turlarini ko'rsatish
    is_acting_as_teacher = (current_role == 'teacher') or (current_user.role == 'teacher')
    
    if is_acting_as_teacher:
        # O'qituvchi uchun - faqat ushbu yo'nalishga biriktirilgan dars turlarini ko'rsatish
        lesson_types_set = set()
        
        if direction_id:
            # Faqat shu yo'nalishdagi guruhlar
            direction_group_ids = [g.id for g in Group.query.filter_by(direction_id=direction_id).all()]
            
            # Faqat shu yo'nalishdagi guruhlarga biriktirilgan TeacherSubject'lar
            teacher_assignments = TeacherSubject.query.filter(
                TeacherSubject.teacher_id == current_user.id,
                TeacherSubject.subject_id == subject.id,
                TeacherSubject.group_id.in_(direction_group_ids)
            ).all()
            
            # Barcha biriktirilgan dars turlarini to'plash
            for ta in teacher_assignments:
                if ta.lesson_type:
                    lesson_types_set.add(ta.lesson_type)
            
            # DirectionCurriculum jadvalidan "laboratoriya" va "kurs_ishi" tekshiruvi
            curriculum_item = DirectionCurriculum.query.filter_by(
                direction_id=direction_id,
                subject_id=subject.id
            ).first()
            
            if curriculum_item:
                # Laboratoriya tekshiruvi
                if (curriculum_item.hours_laboratoriya or 0) > 0:
                    # Laboratoriya uchun o'qituvchini qidirish
                    lab_teacher_assignment = TeacherSubject.query.filter(
                        TeacherSubject.subject_id == subject.id,
                        TeacherSubject.group_id.in_(direction_group_ids),
                        TeacherSubject.teacher_id == current_user.id,
                        TeacherSubject.lesson_type == 'laboratoriya'
                    ).first()
                    
                    if not lab_teacher_assignment:
                        # Agar alohida laboratoriya biriktirishi yo'q bo'lsa, amaliyot o'qituvchisini qidirish
                        lab_teacher_assignment = TeacherSubject.query.filter(
                            TeacherSubject.subject_id == subject.id,
                            TeacherSubject.group_id.in_(direction_group_ids),
                            TeacherSubject.teacher_id == current_user.id,
                            TeacherSubject.lesson_type == 'amaliyot'
                        ).first()
                    
                    if lab_teacher_assignment:
                        lesson_types_set.add('laboratoriya')
                
                # Kurs ishi tekshiruvi
                if (curriculum_item.hours_kurs_ishi or 0) > 0:
                    # Kurs ishi uchun o'qituvchini qidirish
                    kurs_teacher_assignment = TeacherSubject.query.filter(
                        TeacherSubject.subject_id == subject.id,
                        TeacherSubject.group_id.in_(direction_group_ids),
                        TeacherSubject.teacher_id == current_user.id,
                        TeacherSubject.lesson_type == 'kurs_ishi'
                    ).first()
                    
                    if not kurs_teacher_assignment:
                        # Agar alohida kurs_ishi biriktirishi yo'q bo'lsa, amaliyot o'qituvchisini qidirish
                        kurs_teacher_assignment = TeacherSubject.query.filter(
                            TeacherSubject.subject_id == subject.id,
                            TeacherSubject.group_id.in_(direction_group_ids),
                            TeacherSubject.teacher_id == current_user.id,
                            TeacherSubject.lesson_type == 'amaliyot'
                        ).first()
                    
                    if kurs_teacher_assignment:
                        lesson_types_set.add('kurs_ishi')
        else:
            # direction_id bo'lmasa, barcha biriktirishlar
            teacher_assignments = TeacherSubject.query.filter_by(
                teacher_id=current_user.id,
                subject_id=subject.id
            ).all()
            
            # Barcha biriktirilgan dars turlarini to'plash
            for ta in teacher_assignments:
                if ta.lesson_type:
                    lesson_types_set.add(ta.lesson_type)
        
        # Dars turlari nomlari
        lesson_type_names_map = {
            'maruza': 'Maruza',
            'amaliyot': 'Amaliyot',
            'laboratoriya': 'Laboratoriya',
            'seminar': 'Seminar',
            'kurs_ishi': 'Kurs ishi'
        }
        
        # Tartib bo'yicha dars turlarini yaratish
        lesson_type_order = ['maruza', 'amaliyot', 'laboratoriya', 'seminar', 'kurs_ishi']
        for lesson_type_key in lesson_type_order:
            if lesson_type_key in lesson_types_set:
                allowed_lesson_types.append({
                    'value': lesson_type_key,
                    'name': lesson_type_names_map.get(lesson_type_key, lesson_type_key.capitalize())
                })
    else:
        # Faqat admin roli bo'lsa va o'qituvchi roli bo'lmasa, barcha dars turlari
        if current_user.role == 'admin' and current_role != 'teacher':
            allowed_lesson_types = [
                {'value': 'maruza', 'name': 'Maruza'},
                {'value': 'amaliyot', 'name': 'Amaliyot'},
                {'value': 'laboratoriya', 'name': 'Laboratoriya'},
                {'value': 'seminar', 'name': 'Seminar'},
                {'value': 'kurs_ishi', 'name': 'Kurs ishi'}
            ]
    
    if request.method == 'POST':
        # O'qituvchi uchun tanlangan dars turini tekshirish
        selected_lesson_type = request.form.get('lesson_type', 'maruza')
        # Agar o'qituvchi roliga ega bo'lsa (admin ham o'qituvchi roliga ega bo'lishi mumkin), tekshiruv qilish
        # Agar o'qituvchi roliga ega bo'lsa (admin ham o'qituvchi roliga ega bo'lishi mumkin), tekshiruv qilish
        if is_acting_as_teacher:
            # Agar allowed_lesson_types bo'sh bo'lsa, dars yaratishga ruxsat berilmaydi
            if not allowed_lesson_types or len(allowed_lesson_types) == 0:
                flash("Sizga bu fanga (ushbu yo'nalishda) hech qanday dars turi biriktirilmagan. Dars yarata olmaysiz.", 'error')
                return render_template('courses/create_lesson.html', subject=subject, groups=groups, direction_id=direction_id, allowed_lesson_types=allowed_lesson_types)
            
            # Tanlangan dars turining ruxsat berilgan ro'yxatda borligini tekshirish
            allowed_values = [lt['value'] for lt in allowed_lesson_types]
            if selected_lesson_type not in allowed_values:
                flash(f"Siz tanlagan dars turiga ushbu yo'nalishda biriktirilmagansiz. Faqat o'zingizga biriktirilgan dars turlari uchun dars yarata olasiz.", 'error')
                return render_template('courses/create_lesson.html', subject=subject, groups=groups, direction_id=direction_id, allowed_lesson_types=allowed_lesson_types)
            
            # Qo'shimcha tekshiruv: tanlangan dars turi shu yo'nalishda biriktirilganligini tekshirish
            if direction_id:
                direction_group_ids = [g.id for g in Group.query.filter_by(direction_id=direction_id).all()]
                # Tanlangan dars turi shu yo'nalishdagi guruhlarga biriktirilganligini tekshirish
                teacher_assignment_exists = TeacherSubject.query.filter(
                    TeacherSubject.teacher_id == current_user.id,
                    TeacherSubject.subject_id == subject.id,
                    TeacherSubject.group_id.in_(direction_group_ids),
                    TeacherSubject.lesson_type == selected_lesson_type
                ).first()
                
                # Agar to'g'ridan-to'g'ri biriktirish topilmasa, "laboratoriya" va "kurs_ishi" uchun amaliyot orqali tekshirish
                if not teacher_assignment_exists:
                    if selected_lesson_type in ['laboratoriya', 'kurs_ishi']:
                        # Amaliyot orqali biriktirilganligini tekshirish
                        curriculum_item = DirectionCurriculum.query.filter_by(
                            direction_id=direction_id,
                            subject_id=subject.id
                        ).first()
                        
                        if curriculum_item:
                            if selected_lesson_type == 'laboratoriya' and (curriculum_item.hours_laboratoriya or 0) > 0:
                                teacher_assignment_exists = TeacherSubject.query.filter(
                                    TeacherSubject.teacher_id == current_user.id,
                                    TeacherSubject.subject_id == subject.id,
                                    TeacherSubject.group_id.in_(direction_group_ids),
                                    TeacherSubject.lesson_type == 'amaliyot'
                                ).first()
                            elif selected_lesson_type == 'kurs_ishi' and (curriculum_item.hours_kurs_ishi or 0) > 0:
                                teacher_assignment_exists = TeacherSubject.query.filter(
                                    TeacherSubject.teacher_id == current_user.id,
                                    TeacherSubject.subject_id == subject.id,
                                    TeacherSubject.group_id.in_(direction_group_ids),
                                    TeacherSubject.lesson_type == 'amaliyot'
                                ).first()
                
                if not teacher_assignment_exists:
                    flash(f"Siz tanlagan dars turiga ushbu yo'nalishda biriktirilmagansiz. Faqat o'zingizga biriktirilgan dars turlari uchun dars yarata olasiz.", 'error')
                    return render_template('courses/create_lesson.html', subject=subject, groups=groups, direction_id=direction_id, allowed_lesson_types=allowed_lesson_types)
        
        # Agar direction_id berilgan bo'lsa, avtomatik ravishda shu yo'nalishdagi barcha guruhlar uchun yaratiladi
        # Lekin agar guruh direction_id ga ega bo'lmasa yoki boshqa yo'nalishga tegishli bo'lsa ham, 
        # agar u o'qituvchiga biriktirilgan bo'lsa, u ham tanlanadi
        if direction_id:
            # Shu yo'nalishdagi barcha guruhlar
            direction_groups = Group.query.filter_by(direction_id=direction_id).all()
            direction_group_ids = [g.id for g in direction_groups]
            # O'qituvchiga biriktirilgan guruhlar ichidan:
            # 1. Shu yo'nalishdagi guruhlar
            # 2. direction_id ga ega bo'lmagan guruhlar (agar o'qituvchiga biriktirilgan bo'lsa)
            selected_group_ids = []
            seen_selected_group_ids = set()
            for tg in teacher_groups:
                if tg.group_id:
                    group = Group.query.get(tg.group_id)
                    if group:
                        # Agar guruh shu yo'nalishga tegishli bo'lsa yoki direction_id ga ega bo'lmasa
                        if (group.direction_id == direction_id or group.direction_id is None) and tg.group_id not in seen_selected_group_ids:
                            selected_group_ids.append(str(tg.group_id))
                            seen_selected_group_ids.add(tg.group_id)
            
            # Agar hech qanday guruh tanlanmagan bo'lsa, xatolik
            if not selected_group_ids:
                flash("Bu yo'nalishda sizga biriktirilgan guruhlar mavjud emas", 'error')
                return render_template('courses/create_lesson.html', subject=subject, groups=groups, direction_id=direction_id, allowed_lesson_types=allowed_lesson_types)
        else:
            # Admin uchun guruh tanlash ixtiyoriy (agar tanlanmagan bo'lsa, group_id None bo'ladi)
            selected_group_ids = request.form.getlist('group_ids')
            if not selected_group_ids and current_user.role == 'admin':
                selected_group_ids = [None]  # Bitta None yaratish uchun
        
        video_filename = None
        lesson_file_url = None
        
        # Video fayl yuklash
        if 'video_file' in request.files:
            video = request.files['video_file']
            if video and video.filename and allowed_video(video.filename):
                # Unique fayl nomi
                ext = video.filename.rsplit('.', 1)[1].lower()
                video_filename = f"{uuid.uuid4().hex}.{ext}"
                video_path = os.path.join(current_app.config['UPLOAD_FOLDER'], 'videos', video_filename)
                video.save(video_path)
        
        # Maruza uchun video majburiy tekshiruvi
        selected_lesson_type = request.form.get('lesson_type', 'maruza')
        if selected_lesson_type == 'maruza':
            video_url_input = request.form.get('video_url', '').strip()
            has_video_file = 'video_file' in request.files and request.files['video_file'].filename
            has_video_url = bool(video_url_input)
            
            if not has_video_file and not has_video_url:
                flash("Maruza dars turi uchun video majburiy! Video fayl yuklang yoki video URL kiriting.", 'error')
                return render_template('courses/create_lesson.html', subject=subject, groups=groups, direction_id=direction_id, allowed_lesson_types=allowed_lesson_types)
        
        # Video URL faqat YouTube link bo'lishi kerak
        video_url = request.form.get('video_url', '').strip()
        if video_url:
            # YouTube link tekshiruvi
            if 'youtube.com' not in video_url and 'youtu.be' not in video_url:
                flash("Video URL faqat YouTube link bo'lishi kerak (youtube.com yoki youtu.be)", 'error')
                return render_template('courses/create_lesson.html', subject=subject, groups=groups, direction_id=direction_id, allowed_lesson_types=allowed_lesson_types)
        
        # Bir nechta fayl yuklash yoki fayl URL
        lesson_file_url = None
        uploaded_files = []
        
        # Bir nechta fayl yuklash
        if 'lesson_files' in request.files:
            lesson_files = request.files.getlist('lesson_files')
            allowed_extensions = {'pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'txt', 'zip', 'rar'}
            files_folder = os.path.join(current_app.config['UPLOAD_FOLDER'], 'lesson_files')
            os.makedirs(files_folder, exist_ok=True)
            
            for lesson_file in lesson_files:
                if lesson_file and lesson_file.filename:
                    # Fayl formatini tekshirish
                    ext = lesson_file.filename.rsplit('.', 1)[1].lower() if '.' in lesson_file.filename else ''
                    if ext not in allowed_extensions:
                        flash(f"Ruxsat berilmagan fayl formati: {lesson_file.filename}. Ruxsatli formatlar: PDF, DOC, DOCX, XLS, XLSX, PPT, PPTX, TXT, ZIP, RAR", 'error')
                        return render_template('courses/create_lesson.html', subject=subject, groups=groups, direction_id=direction_id, allowed_lesson_types=allowed_lesson_types)
                    
                    # Faylni saqlash
                    filename = f"{uuid.uuid4().hex}.{ext}"
                    file_path = os.path.join(files_folder, filename)
                    lesson_file.save(file_path)
                    uploaded_files.append({
                        'filename': filename,
                        'original_name': lesson_file.filename
                    })
        
        # Fayl URL
                    file_url_input = request.form.get('file_url', '').strip()
            
            # O'qituvchi uchun fayl majburiy
        if current_role == 'teacher' or current_user.role == 'admin':
            # Agar hech qanday fayl yuklanmagan va URL ham bo'lmasa
            if not uploaded_files and not file_url_input:
                flash("O'qituvchilar uchun mavzu faylini yuklash majburiy! Fayl yuklang yoki fayl URL kiriting.", 'error')
                return render_template('courses/create_lesson.html', subject=subject, groups=groups, direction_id=direction_id, allowed_lesson_types=allowed_lesson_types)
        
        # Fayl URL yoki yuklangan fayllarni saqlash (JSON formatida)
        if uploaded_files:
            # Bir nechta fayl bo'lsa, JSON formatida saqlash
            lesson_file_url = json.dumps(uploaded_files)
        elif file_url_input:
            # Agar faqat URL bo'lsa
            lesson_file_url = file_url_input
        
        # Har bir tanlangan guruh uchun alohida dars yaratish
        created_count = 0
        for group_id_str in selected_group_ids:
            # Admin uchun group_id None bo'lishi mumkin
            group_id = int(group_id_str) if group_id_str and group_id_str != 'None' else None
            
            if group_id:
                group = Group.query.get(group_id)
                if not group:
                    continue
            else:
                group = None
            
            # direction_id ni aniqlash
            lesson_direction_id = None
            if direction_id:
                lesson_direction_id = direction_id
            elif group_id and group and group.direction_id:
                lesson_direction_id = group.direction_id
            
            # Bu guruh va yo'nalish uchun darslar sonini hisoblash
            if group_id and lesson_direction_id:
                group_lessons_count = Lesson.query.filter_by(
                    subject_id=id,
                    group_id=group_id,
                    direction_id=lesson_direction_id,
                    lesson_type=request.form.get('lesson_type', 'maruza')
                ).count()
            elif group_id:
                group_lessons_count = Lesson.query.filter_by(
                    subject_id=id,
                    group_id=group_id,
                    lesson_type=request.form.get('lesson_type', 'maruza')
                ).count()
            elif lesson_direction_id:
                group_lessons_count = Lesson.query.filter_by(
                    subject_id=id,
                    direction_id=lesson_direction_id,
                    lesson_type=request.form.get('lesson_type', 'maruza')
                ).count()
            else:
                # Admin uchun group_id None bo'lsa
                group_lessons_count = Lesson.query.filter_by(
                    subject_id=id,
                    group_id=None,
                    direction_id=None,
                    lesson_type=request.form.get('lesson_type', 'maruza')
                ).count()
            
            lesson = Lesson(
                title=request.form.get('title'),
                content=request.form.get('content'),
                video_url=video_url if video_url else None,
                video_file=video_filename,
                file_url=lesson_file_url,
                duration=int(request.form.get('duration', 0) or 0),
                order=group_lessons_count + 1,
                lesson_type=request.form.get('lesson_type', 'maruza'),
                subject_id=id,
                group_id=group_id,
                direction_id=lesson_direction_id,
                created_by=current_user.id
            )
            db.session.add(lesson)
            created_count += 1
        
        db.session.commit()
        
        if created_count > 0:
            flash(f"Dars {created_count} ta guruh uchun muvaffaqiyatli qo'shildi", 'success')
        else:
            flash("Dars qo'shilmadi", 'error')
        
        return redirect(url_for('courses.detail', id=id, direction_id=direction_id))
    
    return render_template('courses/create_lesson.html', subject=subject, groups=groups, direction_id=direction_id, allowed_lesson_types=allowed_lesson_types)


@bp.route('/check-file-url', methods=['POST'])
@login_required
def check_file_url():
    """Fayl URL da fayl bor-yo'qligini tekshirish"""
    data = request.get_json()
    file_url = data.get('url', '').strip()
    
    if not file_url:
        return jsonify({'success': False, 'has_file': False, 'error': 'URL kiritilmagan'})
    
    try:
        # Google Drive/Sheets/Docs linklarini aniqlash
        is_google_drive = 'docs.google.com' in file_url or 'drive.google.com' in file_url
        
        if is_google_drive:
            # Google Drive linklari uchun - ular har doim mavjud deb hisoblanadi
            # chunki ular HTML sahifani qaytaradi, lekin fayl mavjud
            return jsonify({
                'success': True,
                'has_file': True,
                'status_code': 200,
                'content_type': 'application/vnd.google-apps.document',
                'is_google_drive': True,
                'message': 'Google Drive/Sheets/Docs linki aniqlandi. Link mavjud deb hisoblanadi.'
            })
        
        # Boshqa URL'lar uchun HEAD request yuborish
        response = requests.head(file_url, timeout=10, allow_redirects=True)
        
        # Agar 405 (Method Not Allowed) bo'lsa, GET so'rovi yuborish
        if response.status_code == 405:
            response = requests.get(file_url, timeout=10, allow_redirects=True, stream=True)
            response.close()
        
        # Content-Type va Content-Length ni tekshirish
        content_type = response.headers.get('Content-Type', '').lower()
        content_length = response.headers.get('Content-Length', '0')
        
        # Agar Content-Type fayl formatlarini ko'rsatsa yoki Content-Length > 0 bo'lsa
        file_content_types = ['application/', 'text/', 'image/', 'video/', 'audio/']
        html_content_types = ['text/html', 'application/xhtml']
        
        # Agar HTML qaytarsa, bu sahifa bo'lishi mumkin, lekin fayl ham bo'lishi mumkin
        is_html = any(html_ct in content_type for html_ct in html_content_types)
        has_file_content = any(ct in content_type for ct in file_content_types) or int(content_length or 0) > 0
        
        # Agar 200 OK va fayl content type yoki content length > 0 bo'lsa, fayl mavjud
        has_file = (response.status_code == 200 and has_file_content) or (response.status_code == 200 and not is_html and int(content_length or 0) > 0)
        
        # Agar 404, 403, 401 bo'lsa, fayl yo'q
        if response.status_code in [404, 403, 401]:
            has_file = False
        
        return jsonify({
            'success': True,
            'has_file': has_file,
            'status_code': response.status_code,
            'content_type': content_type,
            'is_google_drive': False
        })
    except requests.exceptions.RequestException as e:
        # Xatolik bo'lsa, fayl topilmadi deb hisoblaymiz
        return jsonify({
            'success': False,
            'has_file': False,
            'error': str(e)
        })


@bp.route('/lessons/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit_lesson(id):
    """Darsni tahrirlash"""
    lesson = Lesson.query.get_or_404(id)
    subject = lesson.subject
    
    # Yo'nalish ID (o'qituvchi uchun)
    direction_id = request.args.get('direction_id', type=int)
    
    # Tanlangan rol
    current_role = session.get('current_role', current_user.role)
    
    # Faqat o'qituvchi rolida va o'ziga biriktirilgan fanlar uchun
    is_teacher = TeacherSubject.query.filter_by(
        teacher_id=current_user.id,
        subject_id=subject.id
    ).first() is not None
    
    # Bir nechta rol belgilangan o'qituvchilar faqatgina o'qituvchi rolida o'ziga biriktirilgan fan uchun mavzuni tahrirlay olishi kerak
    # O'qituvchi faqat o'zi yaratgan darslarni tahrirlay oladi
    can_edit = False
    if (current_user.role == 'admin' or current_user.role == 'dean') and current_role != 'teacher':
        can_edit = True
    elif current_role == 'teacher' and is_teacher:
        # Check if teacher is assigned to this lesson type and direction
        if direction_id and lesson.direction_id and lesson.direction_id != direction_id:
            # Explicit direction mismatch
            can_edit = False
        else:
            # Check assignment to lesson type
            # Use provided direction_id or fallback to lesson.direction_id
            check_direction_id = direction_id or lesson.direction_id
            
            teacher_assignments_query = TeacherSubject.query.filter(
                TeacherSubject.teacher_id == current_user.id,
                TeacherSubject.subject_id == subject.id,
                TeacherSubject.lesson_type == lesson.lesson_type
            )
            
            if check_direction_id:
                direction_group_ids = [g.id for g in Group.query.filter_by(direction_id=check_direction_id).all()]
                teacher_assignments_query = teacher_assignments_query.filter(TeacherSubject.group_id.in_(direction_group_ids))
            
            teacher_assignment = teacher_assignments_query.first()
            
            if teacher_assignment:
                can_edit = True
            else:
                 # Laboratoriya va kurs_ishi uchun amaliyot orqali tekshirish
                 # Bu tekshiruv uchun aniq direction kerak (curriculum uchun)
                 target_direction_id = check_direction_id
                 if target_direction_id:
                    curriculum_item = DirectionCurriculum.query.filter_by(
                        direction_id=target_direction_id,
                        subject_id=subject.id
                    ).first()
                    
                    if curriculum_item:
                         target_group_ids = [g.id for g in Group.query.filter_by(direction_id=target_direction_id).all()]
                         
                         if lesson.lesson_type == 'laboratoriya' and (curriculum_item.hours_laboratoriya or 0) > 0:
                            amaliyot_assignment = TeacherSubject.query.filter(
                                TeacherSubject.teacher_id == current_user.id,
                                TeacherSubject.subject_id == subject.id,
                                TeacherSubject.group_id.in_(target_group_ids),
                                TeacherSubject.lesson_type == 'amaliyot'
                            ).first()
                            if amaliyot_assignment:
                                can_edit = True
                         elif lesson.lesson_type == 'kurs_ishi' and (curriculum_item.hours_kurs_ishi or 0) > 0:
                            amaliyot_assignment = TeacherSubject.query.filter(
                                TeacherSubject.teacher_id == current_user.id,
                                TeacherSubject.subject_id == subject.id,
                                TeacherSubject.group_id.in_(target_group_ids),
                                TeacherSubject.lesson_type == 'amaliyot'
                            ).first()
                            if amaliyot_assignment:
                                can_edit = True
                                
    if not can_edit:
        flash("Sizda darsni tahrirlash uchun ruxsat yo'q. Faqat o'qituvchi rolida o'zingizga biriktirilgan darslarni tahrirlay olasiz.", 'error')
        return redirect(url_for('courses.detail', id=subject.id, direction_id=direction_id))
        
        # Yo'nalish bo'yicha tekshiruv - o'qituvchi faqat ushbu yo'nalishdagi darslarni tahrirlay oladi
    
    if request.method == 'POST':
        video_filename = lesson.video_file  # Eski faylni saqlash
        lesson_file_url = lesson.file_url  # Eski faylni saqlash
        
        # Video fayl yuklash (yangi fayl yuklansa, eski o'rniga yangisini qo'yish)
        if 'video_file' in request.files:
            video = request.files['video_file']
            if video and video.filename and allowed_video(video.filename):
                # Eski video faylni o'chirish
                if lesson.video_file:
                    old_video_path = os.path.join(current_app.config['UPLOAD_FOLDER'], 'videos', lesson.video_file)
                    if os.path.exists(old_video_path):
                        try:
                            os.remove(old_video_path)
                        except:
                            pass
                
                # Yangi video faylni saqlash
                ext = video.filename.rsplit('.', 1)[1].lower()
                video_filename = f"{uuid.uuid4().hex}.{ext}"
                video_path = os.path.join(current_app.config['UPLOAD_FOLDER'], 'videos', video_filename)
                video.save(video_path)
        
        # Video URL faqat YouTube link bo'lishi kerak
        video_url = request.form.get('video_url', '').strip()
        if video_url:
            # YouTube link tekshiruvi
            if 'youtube.com' not in video_url and 'youtu.be' not in video_url:
                flash("Video URL faqat YouTube link bo'lishi kerak (youtube.com yoki youtu.be)", 'error')
                return render_template('courses/edit_lesson.html', lesson=lesson, subject=subject, direction_id=direction_id)
            # Agar yangi URL kiritilgan bo'lsa, video_file ni None qilish va eski faylni o'chirish
            if lesson.video_file:
                old_video_path = os.path.join(current_app.config['UPLOAD_FOLDER'], 'videos', lesson.video_file)
                if os.path.exists(old_video_path):
                    try:
                        os.remove(old_video_path)
                    except:
                        pass
            video_filename = None
        elif not video_filename:
            # Agar yangi video yuklanmagan bo'lsa, eski videoni saqlash
            video_filename = lesson.video_file
            video_url = lesson.video_url
        
        # O'qituvchi uchun fayl yuklash
        if current_user.role == 'teacher' or current_user.role == 'admin':
            # Fayl yuklash
            if 'lesson_file' in request.files:
                lesson_file = request.files['lesson_file']
                if lesson_file and lesson_file.filename:
                    # Eski faylni o'chirish (agar yuklangan bo'lsa)
                    if lesson.file_url and not ('http://' in lesson.file_url or 'https://' in lesson.file_url):
                        old_file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], 'lesson_files', lesson.file_url)
                        if os.path.exists(old_file_path):
                            try:
                                os.remove(old_file_path)
                            except:
                                pass
                    
                    # Fayl formatini tekshirish
                    allowed_extensions = {'pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'txt', 'zip', 'rar'}
                    ext = lesson_file.filename.rsplit('.', 1)[1].lower() if '.' in lesson_file.filename else ''
                    if ext not in allowed_extensions:
                        flash("Ruxsat berilmagan fayl formati. Ruxsatli formatlar: PDF, DOC, DOCX, XLS, XLSX, PPT, PPTX, TXT, ZIP, RAR", 'error')
                        return render_template('courses/edit_lesson.html', lesson=lesson, subject=subject, direction_id=direction_id)
                    
                    # Faylni saqlash
                    filename = f"{uuid.uuid4().hex}.{ext}"
                    files_folder = os.path.join(current_app.config['UPLOAD_FOLDER'], 'lesson_files')
                    os.makedirs(files_folder, exist_ok=True)
                    file_path = os.path.join(files_folder, filename)
                    lesson_file.save(file_path)
                    lesson_file_url = filename
                else:
                    # URL orqali fayl
                    file_url_input = request.form.get('file_url', '').strip()
                    if file_url_input:
                        # Agar eski fayl yuklangan bo'lsa, o'chirish
                        if lesson.file_url and not ('http://' in lesson.file_url or 'https://' in lesson.file_url):
                            old_file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], 'lesson_files', lesson.file_url)
                            if os.path.exists(old_file_path):
                                try:
                                    os.remove(old_file_path)
                                except:
                                    pass
                        lesson_file_url = file_url_input
                    else:
                        # Agar yangi fayl yoki URL kiritilmagan bo'lsa, eski faylni saqlash
                        lesson_file_url = lesson.file_url
                        if not lesson_file_url:
                            # Agar hech qanday fayl bo'lmasa, majburiy
                            flash("O'qituvchilar uchun mavzu faylini yuklash majburiy!", 'error')
                            return render_template('courses/edit_lesson.html', lesson=lesson, subject=subject, direction_id=direction_id)
        else:
            # Boshqa rollar uchun ixtiyoriy
            file_url_input = request.form.get('file_url', '').strip()
            if file_url_input:
                # Agar eski fayl yuklangan bo'lsa, o'chirish
                if lesson.file_url and not ('http://' in lesson.file_url or 'https://' in lesson.file_url):
                    old_file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], 'lesson_files', lesson.file_url)
                    if os.path.exists(old_file_path):
                        try:
                            os.remove(old_file_path)
                        except:
                            pass
                lesson_file_url = file_url_input
            else:
                lesson_file_url = lesson.file_url  # Eski faylni saqlash
        
        # Dars turini o'zgartirishdan oldin ruxsat tekshiruvi (o'qituvchi uchun)
        new_lesson_type = request.form.get('lesson_type', lesson.lesson_type)
        if current_role == 'teacher' and direction_id:
            # O'qituvchi uchun - faqat o'ziga biriktirilgan dars turlarini o'zgartirish mumkin
            if new_lesson_type != lesson.lesson_type:
                # Yangi dars turini tekshirish
                direction_group_ids = [g.id for g in Group.query.filter_by(direction_id=direction_id).all()]
                
                # Ushbu yo'nalishda ushbu dars turiga biriktirilganligini tekshirish
                teacher_assignment = TeacherSubject.query.filter(
                    TeacherSubject.teacher_id == current_user.id,
                    TeacherSubject.subject_id == subject.id,
                    TeacherSubject.group_id.in_(direction_group_ids),
                    TeacherSubject.lesson_type == new_lesson_type
                ).first()
                
                # Agar to'g'ridan-to'g'ri biriktirish topilmasa, "laboratoriya" va "kurs_ishi" uchun amaliyot orqali tekshirish
                if not teacher_assignment:
                    if new_lesson_type in ['laboratoriya', 'kurs_ishi']:
                        curriculum_item = DirectionCurriculum.query.filter_by(
                            direction_id=direction_id,
                            subject_id=subject.id
                        ).first()
                        
                        if curriculum_item:
                            if new_lesson_type == 'laboratoriya' and (curriculum_item.hours_laboratoriya or 0) > 0:
                                teacher_assignment = TeacherSubject.query.filter(
                                    TeacherSubject.teacher_id == current_user.id,
                                    TeacherSubject.subject_id == subject.id,
                                    TeacherSubject.group_id.in_(direction_group_ids),
                                    TeacherSubject.lesson_type == 'amaliyot'
                                ).first()
                            elif new_lesson_type == 'kurs_ishi' and (curriculum_item.hours_kurs_ishi or 0) > 0:
                                teacher_assignment = TeacherSubject.query.filter(
                                    TeacherSubject.teacher_id == current_user.id,
                                    TeacherSubject.subject_id == subject.id,
                                    TeacherSubject.group_id.in_(direction_group_ids),
                                    TeacherSubject.lesson_type == 'amaliyot'
                                ).first()
                
                if not teacher_assignment:
                    flash(f"Siz ushbu yo'nalishda '{new_lesson_type}' dars turiga biriktirilmagansiz. Faqat o'zingizga biriktirilgan dars turlarini o'zgartira olasiz.", 'error')
                    allowed_lesson_types = []
                    is_acting_as_teacher = (current_role == 'teacher') or (current_user.role == 'teacher')
                    # allowed_lesson_types ni qayta hisoblash
                    if is_acting_as_teacher and direction_id:
                        lesson_types_set = set()
                        direction_group_ids = [g.id for g in Group.query.filter_by(direction_id=direction_id).all()]
                        teacher_assignments = TeacherSubject.query.filter(
                            TeacherSubject.teacher_id == current_user.id,
                            TeacherSubject.subject_id == subject.id,
                            TeacherSubject.group_id.in_(direction_group_ids)
                        ).all()
                        for ta in teacher_assignments:
                            if ta.lesson_type:
                                lesson_types_set.add(ta.lesson_type)
                        
                        curriculum_item = DirectionCurriculum.query.filter_by(
                            direction_id=direction_id,
                            subject_id=subject.id
                        ).first()
                        
                        if curriculum_item:
                            if (curriculum_item.hours_laboratoriya or 0) > 0:
                                lab_teacher = TeacherSubject.query.filter(
                                    TeacherSubject.subject_id == subject.id,
                                    TeacherSubject.group_id.in_(direction_group_ids),
                                    TeacherSubject.teacher_id == current_user.id,
                                    TeacherSubject.lesson_type.in_(['laboratoriya', 'amaliyot'])
                                ).first()
                                if lab_teacher:
                                    lesson_types_set.add('laboratoriya')
                            
                            if (curriculum_item.hours_kurs_ishi or 0) > 0:
                                kurs_teacher = TeacherSubject.query.filter(
                                    TeacherSubject.subject_id == subject.id,
                                    TeacherSubject.group_id.in_(direction_group_ids),
                                    TeacherSubject.teacher_id == current_user.id,
                                    TeacherSubject.lesson_type.in_(['kurs_ishi', 'amaliyot'])
                                ).first()
                                if kurs_teacher:
                                    lesson_types_set.add('kurs_ishi')
                        
                        lesson_type_names_map = {
                            'maruza': 'Maruza',
                            'amaliyot': 'Amaliyot',
                            'laboratoriya': 'Laboratoriya',
                            'seminar': 'Seminar',
                            'kurs_ishi': 'Kurs ishi'
                        }
                        
                        lesson_type_order = ['maruza', 'amaliyot', 'laboratoriya', 'seminar', 'kurs_ishi']
                        for lesson_type_key in lesson_type_order:
                            if lesson_type_key in lesson_types_set:
                                allowed_lesson_types.append({
                                    'value': lesson_type_key,
                                    'name': lesson_type_names_map.get(lesson_type_key, lesson_type_key.capitalize())
                                })
                    elif current_user.role == 'admin':
                        allowed_lesson_types = [
                            {'value': 'maruza', 'name': 'Maruza'},
                            {'value': 'amaliyot', 'name': 'Amaliyot'},
                            {'value': 'laboratoriya', 'name': 'Laboratoriya'},
                            {'value': 'seminar', 'name': 'Seminar'},
                            {'value': 'kurs_ishi', 'name': 'Kurs ishi'}
                        ]
                    
                    return render_template('courses/edit_lesson.html', lesson=lesson, subject=subject, direction_id=direction_id, allowed_lesson_types=allowed_lesson_types)
        
        # Dars ma'lumotlarini yangilash
        lesson.title = request.form.get('title')
        lesson.content = request.form.get('content')
        lesson.video_url = video_url if video_url else None
        lesson.video_file = video_filename
        lesson.file_url = lesson_file_url
        lesson.duration = int(request.form.get('duration', 0) or 0)
        lesson.lesson_type = new_lesson_type
        
        db.session.commit()
        
        flash("Dars muvaffaqiyatli yangilandi", 'success')
        return redirect(url_for('courses.detail', id=subject.id, direction_id=direction_id))
    
    # allowed_lesson_types ni olish (create_lesson funksiyasidagi kabi)
    allowed_lesson_types = []
    is_acting_as_teacher = (current_role == 'teacher') or (current_user.role == 'teacher')
    
    if is_acting_as_teacher and direction_id:
        lesson_types_set = set()
        direction_group_ids = [g.id for g in Group.query.filter_by(direction_id=direction_id).all()]
        teacher_assignments = TeacherSubject.query.filter(
            TeacherSubject.teacher_id == current_user.id,
            TeacherSubject.subject_id == subject.id,
            TeacherSubject.group_id.in_(direction_group_ids)
        ).all()
        for ta in teacher_assignments:
            if ta.lesson_type:
                lesson_types_set.add(ta.lesson_type)
        
        curriculum_item = DirectionCurriculum.query.filter_by(
            direction_id=direction_id,
            subject_id=subject.id
        ).first()
        
        if curriculum_item:
            if (curriculum_item.hours_laboratoriya or 0) > 0:
                lab_teacher = TeacherSubject.query.filter(
                    TeacherSubject.subject_id == subject.id,
                    TeacherSubject.group_id.in_(direction_group_ids),
                    TeacherSubject.teacher_id == current_user.id,
                    TeacherSubject.lesson_type.in_(['laboratoriya', 'amaliyot'])
                ).first()
                if lab_teacher:
                    lesson_types_set.add('laboratoriya')
            
            if (curriculum_item.hours_kurs_ishi or 0) > 0:
                kurs_teacher = TeacherSubject.query.filter(
                    TeacherSubject.subject_id == subject.id,
                    TeacherSubject.group_id.in_(direction_group_ids),
                    TeacherSubject.teacher_id == current_user.id,
                    TeacherSubject.lesson_type.in_(['kurs_ishi', 'amaliyot'])
                ).first()
                if kurs_teacher:
                    lesson_types_set.add('kurs_ishi')
        
        lesson_type_names_map = {
            'maruza': 'Maruza',
            'amaliyot': 'Amaliyot',
            'laboratoriya': 'Laboratoriya',
            'seminar': 'Seminar',
            'kurs_ishi': 'Kurs ishi'
        }
        
        lesson_type_order = ['maruza', 'amaliyot', 'laboratoriya', 'seminar', 'kurs_ishi']
        for lesson_type_key in lesson_type_order:
            if lesson_type_key in lesson_types_set:
                allowed_lesson_types.append({
                    'value': lesson_type_key,
                    'name': lesson_type_names_map.get(lesson_type_key, lesson_type_key.capitalize())
                })
    elif current_user.role == 'admin':
        allowed_lesson_types = [
            {'value': 'maruza', 'name': 'Maruza'},
            {'value': 'amaliyot', 'name': 'Amaliyot'},
            {'value': 'laboratoriya', 'name': 'Laboratoriya'},
            {'value': 'seminar', 'name': 'Seminar'},
            {'value': 'kurs_ishi', 'name': 'Kurs ishi'}
        ]
    
    return render_template('courses/edit_lesson.html', lesson=lesson, subject=subject, direction_id=direction_id, allowed_lesson_types=allowed_lesson_types)


@bp.route('/lessons/<int:id>/delete', methods=['POST'])
@login_required
def delete_lesson(id):
    """Darsni o'chirish"""
    lesson = Lesson.query.get_or_404(id)
    subject = lesson.subject
    
    # Yo'nalish ID (o'qituvchi uchun)
    direction_id = request.args.get('direction_id', type=int)
    
    # Tanlangan rol
    current_role = session.get('current_role', current_user.role)
    
    # Faqat o'qituvchi rolida va o'ziga biriktirilgan fanlar uchun
    is_teacher = TeacherSubject.query.filter_by(
        teacher_id=current_user.id,
        subject_id=subject.id
    ).first() is not None
    
    # Bir nechta rol belgilangan o'qituvchilar faqatgina o'qituvchi rolida o'ziga biriktirilgan fan uchun mavzuni o'chira olishi kerak
    # O'qituvchi faqat o'zi yaratgan darslarni o'chira oladi
    can_delete = False
    if (current_user.role == 'admin' or current_user.role == 'dean') and current_role != 'teacher':
        can_delete = True
    elif current_role == 'teacher' and is_teacher:
        # O'qituvchining fanga biriktirilganligini (guruh va dars turi bo'yicha) tekshirish
        
        # direction_id tekshiruvi (edit dagi kabi)
        if direction_id and lesson.direction_id and lesson.direction_id != direction_id:
            can_delete = False
        else:
            check_direction_id = direction_id or lesson.direction_id
            
            teacher_assignments_query = TeacherSubject.query.filter(
                TeacherSubject.teacher_id == current_user.id,
                TeacherSubject.subject_id == subject.id,
                TeacherSubject.lesson_type == lesson.lesson_type
            )
            
            if check_direction_id:
                direction_group_ids = [g.id for g in Group.query.filter_by(direction_id=check_direction_id).all()]
                teacher_assignments_query = teacher_assignments_query.filter(TeacherSubject.group_id.in_(direction_group_ids))
            
            teacher_assignment = teacher_assignments_query.first()
            
            if teacher_assignment:
                can_delete = True
            else:
                 # Laboratoriya va kurs_ishi uchun amaliyot orqali tekshirish
                target_direction_id = check_direction_id
                if target_direction_id:
                    curriculum_item = DirectionCurriculum.query.filter_by(
                        direction_id=target_direction_id,
                        subject_id=subject.id
                    ).first()
                    if curriculum_item:
                        target_group_ids = [g.id for g in Group.query.filter_by(direction_id=target_direction_id).all()]
                        
                        if lesson.lesson_type == 'laboratoriya' and (curriculum_item.hours_laboratoriya or 0) > 0:
                            lab_teacher = TeacherSubject.query.filter(
                                TeacherSubject.subject_id == subject.id,
                                TeacherSubject.group_id.in_(target_group_ids),
                                TeacherSubject.teacher_id == current_user.id,
                                TeacherSubject.lesson_type.in_(['laboratoriya', 'amaliyot'])
                            ).first()
                            if lab_teacher:
                                 can_delete = True
                        elif lesson.lesson_type == 'kurs_ishi' and (curriculum_item.hours_kurs_ishi or 0) > 0:
                            kurs_teacher = TeacherSubject.query.filter(
                                TeacherSubject.subject_id == subject.id,
                                TeacherSubject.group_id.in_(target_group_ids),
                                TeacherSubject.teacher_id == current_user.id,
                                TeacherSubject.lesson_type.in_(['kurs_ishi', 'amaliyot'])
                            ).first()
                            if kurs_teacher:
                                can_delete = True
        
    if not can_delete:
        flash("Sizda darsni o'chirish uchun ruxsat yo'q. Faqat o'qituvchi rolida o'zingizga biriktirilgan darslarni o'chira olasiz.", 'error')
        return redirect(url_for('courses.detail', id=subject.id, direction_id=direction_id))
    
    # Mavzuga biriktirilgan topshiriqlar borligini tekshirish
    assignments_with_lesson = Assignment.query.filter_by(subject_id=subject.id).all()
    linked_assignments = []
    for assignment in assignments_with_lesson:
        lesson_ids = assignment.get_lesson_ids_list() if hasattr(assignment, 'get_lesson_ids_list') else []
        if lesson.id in lesson_ids:
            linked_assignments.append(assignment.title)
    
    if linked_assignments:
        flash(f"Bu mavzuni o'chirib bo'lmaydi! Quyidagi topshiriqlar bu mavzuga bog'langan: {', '.join(linked_assignments)}", 'error')
        return redirect(url_for('courses.detail', id=subject.id, direction_id=direction_id))
    
    # Video faylni o'chirish
    if lesson.video_file:
        video_path = os.path.join(current_app.config['UPLOAD_FOLDER'], 'videos', lesson.video_file)
        if os.path.exists(video_path):
            try:
                os.remove(video_path)
            except:
                pass
    
    # Faylni o'chirish (agar yuklangan bo'lsa)
    if lesson.file_url and not ('http://' in lesson.file_url or 'https://' in lesson.file_url):
        file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], 'lesson_files', lesson.file_url)
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except:
                pass
    
    # Darsni o'chirish
    db.session.delete(lesson)
    db.session.commit()
    
    flash("Dars muvaffaqiyatli o'chirildi", 'success')
    return redirect(url_for('courses.detail', id=subject.id, direction_id=direction_id))


@bp.route('/uploads/videos/<filename>')
@login_required
def serve_video(filename):
    """Video faylni uzatish"""
    videos_folder = os.path.join(current_app.config['UPLOAD_FOLDER'], 'videos')
    return send_from_directory(videos_folder, filename)

@bp.route('/uploads/lesson_files/<filename>')
@login_required
def serve_lesson_file(filename):
    """Dars faylini uzatish"""
    files_folder = os.path.join(current_app.config['UPLOAD_FOLDER'], 'lesson_files')
    file_path = os.path.join(files_folder, filename)
    
    # Fayl mavjudligini tekshirish
    if not os.path.exists(file_path):
        flash("Fayl topilmadi", 'error')
        return redirect(url_for('courses.index'))
    
    # Ruxsatni tekshirish
    lesson = Lesson.query.filter_by(file_url=filename).first()
    if not lesson:
        # URL bo'lsa, to'g'ridan-to'g'ri qaytarish
        return send_from_directory(files_folder, filename, as_attachment=True)
    
    subject = lesson.subject
    
    # Tekshirish
    can_view = False
    if current_user.role == 'admin':
        can_view = True
    elif current_user.role == 'teacher':
        can_view = TeacherSubject.query.filter_by(
            teacher_id=current_user.id,
            subject_id=subject.id
        ).first() is not None
    elif current_user.role == 'student' and current_user.group_id:
        can_view = TeacherSubject.query.filter_by(
            group_id=current_user.group_id,
            subject_id=subject.id
        ).first() is not None
    
    if not can_view:
        flash("Sizda bu faylni ko'rish huquqi yo'q", 'error')
        return redirect(url_for('courses.index'))
    
    return send_from_directory(files_folder, filename, as_attachment=True)

@bp.route('/uploads/submissions/<filename>')
@login_required
def serve_submission_file(filename):
    """Topshiriq faylini ko'rsatish"""
    submissions_folder = os.path.join(current_app.config['UPLOAD_FOLDER'], 'submissions')
    file_path = os.path.join(submissions_folder, filename)
    
    # Fayl mavjudligini tekshirish
    if not os.path.exists(file_path):
        flash("Fayl topilmadi", 'error')
        return redirect(url_for('courses.index'))
    
    # Ruxsatni tekshirish - faqat fayl egasi yoki o'qituvchi ko'ra oladi
    submission = Submission.query.filter_by(file_url=filename).first()
    if not submission:
        flash("Fayl topilmadi", 'error')
        return redirect(url_for('courses.index'))
    
    # Talaba o'z faylini ko'ra oladi
    if current_user.role == 'student' and submission.student_id != current_user.id:
        flash("Sizda bu faylni ko'rish huquqi yo'q", 'error')
        return redirect(url_for('courses.index'))
    
    # O'qituvchi o'z guruhlaridagi talabalarning fayllarini ko'ra oladi
    if current_user.role == 'teacher':
        assignment = submission.assignment
        teaching = TeacherSubject.query.filter_by(
            teacher_id=current_user.id,
            subject_id=assignment.subject_id,
            group_id=assignment.group_id
        ).first()
        if not teaching:
            flash("Sizda bu faylni ko'rish huquqi yo'q", 'error')
            return redirect(url_for('courses.index'))
    
    return send_from_directory(submissions_folder, filename, as_attachment=True)


@bp.route('/lessons/<int:id>')
@login_required
def lesson_detail(id):
    """Dars tafsilotlari"""
    lesson = Lesson.query.get_or_404(id)
    subject = lesson.subject
    
    # Tekshirish
    can_view = False
    if current_user.role == 'admin':
        can_view = True
    elif current_user.role == 'dean':
        # Dekan o'z fakultetidagi guruhlar uchun fanlarni ko'rishi mumkin
        if current_user.faculty_id:
            can_view = TeacherSubject.query.join(Group).filter(
                TeacherSubject.subject_id == subject.id,
                Group.faculty_id == current_user.faculty_id
            ).first() is not None
        else:
            can_view = True  # Agar fakultet belgilanmagan bo'lsa, barcha fanlarni ko'rish
    elif current_user.role == 'teacher':
        can_view = TeacherSubject.query.filter_by(
            teacher_id=current_user.id,
            subject_id=subject.id
        ).first() is not None
    elif current_user.role == 'student' and current_user.group_id:
        can_view = TeacherSubject.query.filter_by(
            group_id=current_user.group_id,
            subject_id=subject.id
        ).first() is not None
    
    if not can_view:
        flash("Sizda bu darsni ko'rish huquqi yo'q", 'error')
        return redirect(url_for('courses.index'))
    
    # Talaba uchun ko'rish yozuvi va qulflanganligini tekshirish
    lesson_view = None
    is_locked = False
    if current_user.role == 'student':
        lesson_view = LessonView.query.filter_by(
            lesson_id=lesson.id,
            student_id=current_user.id
        ).first()
        
        # Oldingi darslar to'liq ko'rilganligini tekshirish (faqat videoga ega darslar uchun)
        if lesson.video_file or lesson.video_url:
            previous_lessons = Lesson.query.filter(
                Lesson.subject_id == subject.id,
                Lesson.lesson_type == lesson.lesson_type,
                Lesson.order < lesson.order
            ).order_by(Lesson.order).all()
            
            for prev_lesson in previous_lessons:
                if prev_lesson.video_file or prev_lesson.video_url:
                    prev_lesson_view = LessonView.query.filter_by(
                        lesson_id=prev_lesson.id,
                        student_id=current_user.id
                    ).first()
                    
                    if not prev_lesson_view or not prev_lesson_view.is_completed:
                        is_locked = True
                        break
    
    # Tahrirlash huquqini tekshirish
    can_edit_lesson = False
    current_role = session.get('current_role', current_user.role)
    if (current_user.role == 'admin' or current_user.role == 'dean') and current_role != 'teacher':
        can_edit_lesson = True
    elif current_role == 'teacher':
        # O'qituvchi o'ziga biriktirilgan darsni tahrirlay oladi
        # Avval guruh/yo'nalishni topamiz. Lesson da direction_id bor.
        if lesson.direction_id:
            direction_group_ids = [g.id for g in Group.query.filter_by(direction_id=lesson.direction_id).all()]
            
            teacher_assignment = TeacherSubject.query.filter(
                TeacherSubject.teacher_id == current_user.id,
                TeacherSubject.subject_id == subject.id,
                TeacherSubject.group_id.in_(direction_group_ids),
                TeacherSubject.lesson_type == lesson.lesson_type
            ).first()
            
            if teacher_assignment:
                can_edit_lesson = True
            else:
                 # Check lab/kurs_ishi logic here too if needed, but keeping it simple for now or replicating strict logic
                 # Replicating strict logic briefly for consistency:
                 curriculum_item = DirectionCurriculum.query.filter_by(
                    direction_id=lesson.direction_id,
                    subject_id=subject.id
                 ).first()
                 if curriculum_item:
                    if lesson.lesson_type == 'laboratoriya' and (curriculum_item.hours_laboratoriya or 0) > 0:
                        lab_teacher = TeacherSubject.query.filter(
                            TeacherSubject.subject_id == subject.id,
                            TeacherSubject.group_id.in_(direction_group_ids),
                            TeacherSubject.teacher_id == current_user.id,
                            TeacherSubject.lesson_type.in_(['laboratoriya', 'amaliyot'])
                        ).first()
                        if lab_teacher:
                            can_edit_lesson = True
                    elif lesson.lesson_type == 'kurs_ishi' and (curriculum_item.hours_kurs_ishi or 0) > 0:
                        kurs_teacher = TeacherSubject.query.filter(
                            TeacherSubject.subject_id == subject.id,
                            TeacherSubject.group_id.in_(direction_group_ids),
                            TeacherSubject.teacher_id == current_user.id,
                            TeacherSubject.lesson_type.in_(['kurs_ishi', 'amaliyot'])
                        ).first()
                        if kurs_teacher:
                            can_edit_lesson = True

    return render_template('courses/lesson_detail.html', 
                         lesson=lesson, 
                         subject=subject,
                         lesson_view=lesson_view,
                         is_locked=is_locked,
                         can_edit_lesson=can_edit_lesson,
                         direction_id=lesson.direction_id)


@bp.route('/lessons/<int:id>/watch')
@login_required
def watch_video(id):
    """Video ko'rish sahifasi - diqqat tekshiruvi bilan"""
    lesson = Lesson.query.get_or_404(id)
    subject = lesson.subject
    
    if not lesson.video_file and not lesson.video_url:
        flash("Bu darsda video mavjud emas", 'warning')
        return redirect(url_for('courses.lesson_detail', id=id))
    
    # Tekshirish
    can_view = False
    if current_user.role == 'admin':
        can_view = True
    elif current_user.role == 'teacher':
        can_view = TeacherSubject.query.filter_by(
            teacher_id=current_user.id,
            subject_id=subject.id
        ).first() is not None
    elif current_user.role == 'student' and current_user.group_id:
        can_view = TeacherSubject.query.filter_by(
            group_id=current_user.group_id,
            subject_id=subject.id
        ).first() is not None
    
    if not can_view:
        flash("Sizda bu darsni ko'rish huquqi yo'q", 'error')
        return redirect(url_for('courses.index'))
    
    # Talaba uchun: oldingi darslar to'liq ko'rilganligini tekshirish
    is_locked = False
    if current_user.role == 'student':
        # Bir xil fan va dars turidagi oldingi darslarni olish
        previous_lessons = Lesson.query.filter(
            Lesson.subject_id == subject.id,
            Lesson.lesson_type == lesson.lesson_type,
            Lesson.order < lesson.order
        ).order_by(Lesson.order).all()
        
        # Har bir oldingi dars to'liq ko'rilganligini tekshirish
        for prev_lesson in previous_lessons:
            if prev_lesson.video_file or prev_lesson.video_url:  # Faqat videoga ega darslar
                prev_lesson_view = LessonView.query.filter_by(
                    lesson_id=prev_lesson.id,
                    student_id=current_user.id
                ).first()
                
                if not prev_lesson_view or not prev_lesson_view.is_completed:
                    is_locked = True
                    break
    
    if is_locked and current_user.role == 'student':
        flash("Avval oldingi videolarni to'liq ko'rib chiqing!", 'warning')
        return redirect(url_for('courses.lesson_detail', id=id))
    
    # Talaba uchun ko'rish yozuvini yaratish yoki olish
    lesson_view = None
    next_lesson = None
    if current_user.role == 'student':
        lesson_view = LessonView.query.filter_by(
            lesson_id=lesson.id,
            student_id=current_user.id
        ).first()
        
        if not lesson_view:
            lesson_view = LessonView(
                lesson_id=lesson.id,
                student_id=current_user.id
            )
            db.session.add(lesson_view)
            db.session.commit()
        
        # Keyingi darsni topish (bir xil fan va dars turida)
        next_lesson = Lesson.query.filter(
            Lesson.subject_id == subject.id,
            Lesson.lesson_type == lesson.lesson_type,
            Lesson.order > lesson.order,
            (Lesson.video_file != None) | (Lesson.video_url != None)
        ).order_by(Lesson.order).first()
    
    return render_template('courses/watch_video.html',
                         lesson=lesson,
                         subject=subject,
                         lesson_view=lesson_view,
                         next_lesson=next_lesson)


@bp.route('/lessons/<int:id>/attention-check', methods=['POST'])
@login_required
def attention_check(id):
    """Diqqat tekshiruvi API"""
    if current_user.role != 'student':
        return jsonify({'success': False, 'error': 'Faqat talabalar uchun'}), 403
    
    lesson = Lesson.query.get_or_404(id)
    
    lesson_view = LessonView.query.filter_by(
        lesson_id=lesson.id,
        student_id=current_user.id
    ).first()
    
    if not lesson_view:
        return jsonify({'success': False, 'error': 'Ko\'rish yozuvi topilmadi'}), 404
    
    # Diqqat tekshiruvidan o'tdi
    lesson_view.attention_checks_passed += 1
    
    # 3 ta tekshiruvdan o'tganmi?
    was_completed = lesson_view.is_completed
    if lesson_view.attention_checks_passed >= 3:
        lesson_view.is_completed = True
        lesson_view.completed_at = datetime.utcnow()
    
    db.session.commit()
    
    # Keyingi darsni topish (bir xil fan va dars turida)
    next_lesson = None
    if lesson_view.is_completed and not was_completed:
        next_lesson = Lesson.query.filter(
            Lesson.subject_id == lesson.subject_id,
            Lesson.lesson_type == lesson.lesson_type,
            Lesson.order > lesson.order,
            (Lesson.video_file != None) | (Lesson.video_url != None)
        ).order_by(Lesson.order).first()
    
    response = {
        'success': True,
        'checks_passed': lesson_view.attention_checks_passed,
        'is_completed': lesson_view.is_completed
    }
    
    if next_lesson:
        response['next_lesson'] = {
            'id': next_lesson.id,
            'title': next_lesson.title,
            'url': url_for('courses.watch_video', id=next_lesson.id)
        }
    
    return jsonify(response)


@bp.route('/lessons/<int:id>/update-watch-time', methods=['POST'])
@login_required
def update_watch_time(id):
    """Ko'rish vaqtini yangilash API"""
    if current_user.role != 'student':
        return jsonify({'success': False}), 403
    
    lesson_view = LessonView.query.filter_by(
        lesson_id=id,
        student_id=current_user.id
    ).first()
    
    if lesson_view:
        watch_duration = request.json.get('watch_duration', 0)
        lesson_view.watch_duration = max(lesson_view.watch_duration, watch_duration)
        db.session.commit()
        
        # Maksimal ko'rilgan vaqtni qaytarish
        return jsonify({
            'success': True,
            'watch_duration': lesson_view.watch_duration,
            'is_completed': lesson_view.is_completed
        })
    
    return jsonify({'success': True, 'watch_duration': 0})


@bp.route('/<int:id>/assignments/create', methods=['GET', 'POST'])
@login_required
def create_assignment(id):
    """Yangi topshiriq yaratish"""
    subject = Subject.query.get_or_404(id)
    
    # Yo'nalish ID (query parametrdan)
    direction_id = request.args.get('direction_id', type=int)
    
    # Tanlangan rol
    current_role = session.get('current_role', current_user.role)
    is_acting_as_teacher = (current_role == 'teacher') or (current_user.role == 'teacher')
    
    # O'qituvchiga biriktirilgan dars turlarini topish (dars qo'shish funksiyasidagi mantiq bilan bir xil)
    allowed_lesson_types = []
    if is_acting_as_teacher:
        lesson_types_set = set()
        
        if direction_id:
            # Faqat shu yo'nalishdagi guruhlar
            direction_group_ids = [g.id for g in Group.query.filter_by(direction_id=direction_id).all()]
            
            # Faqat shu yo'nalishdagi guruhlarga biriktirilgan TeacherSubject'lar
            teacher_assignments = TeacherSubject.query.filter(
                TeacherSubject.teacher_id == current_user.id,
                TeacherSubject.subject_id == subject.id,
                TeacherSubject.group_id.in_(direction_group_ids)
            ).all()
            
            # Barcha biriktirilgan dars turlarini to'plash
            for ta in teacher_assignments:
                if ta.lesson_type:
                    lesson_types_set.add(ta.lesson_type)
            
            # DirectionCurriculum jadvalidan "laboratoriya" va "kurs_ishi" tekshiruvi
            curriculum_item = DirectionCurriculum.query.filter_by(
                direction_id=direction_id,
        subject_id=subject.id
            ).first()
            
            if curriculum_item:
                # Laboratoriya tekshiruvi
                if (curriculum_item.hours_laboratoriya or 0) > 0:
                    lab_teacher_assignment = TeacherSubject.query.filter(
                        TeacherSubject.subject_id == subject.id,
                        TeacherSubject.group_id.in_(direction_group_ids),
                        TeacherSubject.teacher_id == current_user.id,
                        TeacherSubject.lesson_type == 'laboratoriya'
                    ).first()
                    
                    if not lab_teacher_assignment:
                        lab_teacher_assignment = TeacherSubject.query.filter(
                            TeacherSubject.subject_id == subject.id,
                            TeacherSubject.group_id.in_(direction_group_ids),
                            TeacherSubject.teacher_id == current_user.id,
                            TeacherSubject.lesson_type == 'amaliyot'
                        ).first()
                    
                    if lab_teacher_assignment:
                        lesson_types_set.add('laboratoriya')
                
                # Kurs ishi tekshiruvi
                if (curriculum_item.hours_kurs_ishi or 0) > 0:
                    kurs_teacher_assignment = TeacherSubject.query.filter(
                        TeacherSubject.subject_id == subject.id,
                        TeacherSubject.group_id.in_(direction_group_ids),
                        TeacherSubject.teacher_id == current_user.id,
                        TeacherSubject.lesson_type == 'kurs_ishi'
                    ).first()
                    
                    if not kurs_teacher_assignment:
                        kurs_teacher_assignment = TeacherSubject.query.filter(
                            TeacherSubject.subject_id == subject.id,
                            TeacherSubject.group_id.in_(direction_group_ids),
                            TeacherSubject.teacher_id == current_user.id,
                            TeacherSubject.lesson_type == 'amaliyot'
                        ).first()
                    
                    if kurs_teacher_assignment:
                        lesson_types_set.add('kurs_ishi')
        
        # Dars turlari nomlari
        lesson_type_names_map = {
            'maruza': 'Maruza',
            'amaliyot': 'Amaliyot',
            'laboratoriya': 'Laboratoriya',
            'seminar': 'Seminar',
            'kurs_ishi': 'Kurs ishi'
        }
        
        # Tartib bo'yicha dars turlarini yaratish
        lesson_type_order = ['maruza', 'amaliyot', 'laboratoriya', 'seminar', 'kurs_ishi']
        for lesson_type_key in lesson_type_order:
            if lesson_type_key in lesson_types_set:
                allowed_lesson_types.append({
                    'value': lesson_type_key,
                    'name': lesson_type_names_map.get(lesson_type_key, lesson_type_key.capitalize())
                })
    else:
        # Faqat admin roli bo'lsa va o'qituvchi roli bo'lmasa, barcha dars turlari
        if current_user.role == 'admin' and current_role != 'teacher':
            allowed_lesson_types = [
                {'value': 'maruza', 'name': 'Maruza'},
                {'value': 'amaliyot', 'name': 'Amaliyot'},
                {'value': 'laboratoriya', 'name': 'Laboratoriya'},
                {'value': 'seminar', 'name': 'Seminar'},
                {'value': 'kurs_ishi', 'name': 'Kurs ishi'}
            ]
    
    # Ushbu yo'nalishdagi barcha guruhlar (avtomatik yaratish uchun)
    direction_groups = Group.query.filter_by(direction_id=direction_id).all() if direction_id else []
    
    # O'qituvchiga biriktirilgan guruhlar
    if is_acting_as_teacher and direction_id:
        direction_group_ids = [g.id for g in direction_groups]
        teacher_groups_query = TeacherSubject.query.filter(
            TeacherSubject.teacher_id == current_user.id,
            TeacherSubject.subject_id == subject.id,
            TeacherSubject.group_id.in_(direction_group_ids)
    ).all()
    
        # Takrorlanmas guruhlar
        seen_group_ids = set()
        groups = []
        for tg in teacher_groups_query:
            if tg.group and tg.group_id not in seen_group_ids:
                seen_group_ids.add(tg.group_id)
                groups.append(tg.group)
    else:
        groups = direction_groups if direction_id else []
    
    # Darslar (mavzular) ro'yxati
    lessons = []
    if direction_id:
        lessons = Lesson.query.filter_by(
            subject_id=subject.id,
            direction_id=direction_id
        ).order_by(Lesson.order).all()
    
    # Faqat mavzulari mavjud bo'lgan dars turlarini ko'rsatish
    if lessons and allowed_lesson_types:
        # Har bir dars turi uchun mavzular bor-yo'qligini tekshirish
        lesson_types_with_lessons = set()
        for lesson in lessons:
            if lesson.lesson_type:
                lesson_types_with_lessons.add(lesson.lesson_type)
        
        # Faqat mavzulari bo'lgan dars turlarini qoldirish
        filtered_lesson_types = []
        for lt in allowed_lesson_types:
            if lt['value'] in lesson_types_with_lessons:
                filtered_lesson_types.append(lt)
        allowed_lesson_types = filtered_lesson_types
    
    # Admin uchun ham faqat mavzulari bo'lgan dars turlarini ko'rsatish
    if current_user.role == 'admin' and current_role != 'teacher' and lessons:
        lesson_types_with_lessons = set()
        for lesson in lessons:
            if lesson.lesson_type:
                lesson_types_with_lessons.add(lesson.lesson_type)
        
        filtered_lesson_types = []
        for lt in allowed_lesson_types:
            if lt['value'] in lesson_types_with_lessons:
                filtered_lesson_types.append(lt)
        allowed_lesson_types = filtered_lesson_types
    
    # Ruxsat tekshiruvi
    if is_acting_as_teacher and not allowed_lesson_types and not groups:
        if current_user.role != 'admin':
            flash("Sizda topshiriq yaratish uchun ruxsat yo'q. Faqat o'ziga biriktirilgan fanlar uchun topshiriq yarata olasiz.", 'error')
            return redirect(url_for('courses.detail', id=id, direction_id=direction_id))
    
    if request.method == 'POST':
        # Dars turi majburiy
        selected_lesson_type = request.form.get('lesson_type', '').strip()
        if not selected_lesson_type:
            flash("Dars turini tanlash majburiy!", 'error')
            return render_template('courses/create_assignment.html', subject=subject, groups=groups, direction_id=direction_id, allowed_lesson_types=allowed_lesson_types, lessons=lessons)
        
        # O'qituvchi uchun tanlangan dars turini tekshirish
        if is_acting_as_teacher:
            allowed_values = [lt['value'] for lt in allowed_lesson_types]
            if selected_lesson_type not in allowed_values:
                flash(f"Siz tanlagan dars turiga ushbu yo'nalishda biriktirilmagansiz.", 'error')
                return render_template('courses/create_assignment.html', subject=subject, groups=groups, direction_id=direction_id, allowed_lesson_types=allowed_lesson_types, lessons=lessons)
        
        # Tanlangan mavzular (lesson_ids)
        selected_lesson_ids = request.form.getlist('lesson_ids')
        lesson_ids_json = json.dumps([int(lesson_id) for lesson_id in selected_lesson_ids]) if selected_lesson_ids else None
        
        due_date_str = request.form.get('due_date')
        if due_date_str:
            # Sana 23:59:59 ga o'rnatiladi (Toshkent vaqti)
            # UTC ga o'tkazish uchun 5 soat ayiramiz (18:59:59 UTC)
            due_date = datetime.strptime(due_date_str, '%Y-%m-%d')
            due_date = due_date.replace(hour=18, minute=59, second=59)
        else:
            due_date = None
        
        # Avtomatik ravishda ushbu yo'nalishdagi barcha guruhlar uchun yaratish
        if direction_id and groups:
            # Ushbu yo'nalishdagi barcha guruhlar
            selected_group_ids = [str(g.id) for g in groups]
        else:
            flash("Guruhlar topilmadi yoki yo'nalish tanlanmagan", 'error')
            return render_template('courses/create_assignment.html', subject=subject, groups=groups, direction_id=direction_id, allowed_lesson_types=allowed_lesson_types, lessons=lessons)
        
        # Har bir tanlangan guruh uchun alohida topshiriq yaratish
        created_count = 0
        for group_id_str in selected_group_ids:
            group_id = int(group_id_str) if group_id_str and group_id_str != 'None' else None
            
            if group_id:
                group = Group.query.get(group_id)
                if not group:
                    continue
            else:
                continue
            
            assignment = Assignment(
                title=request.form.get('title'),
                description=request.form.get('description'),
                max_score=int(request.form.get('max_score', 100)),
                due_date=due_date,
                subject_id=id,
                group_id=group_id,
                direction_id=direction_id,
                lesson_type=selected_lesson_type,
                lesson_ids=lesson_ids_json,
                file_required=bool(request.form.get('file_required')),
                created_by=current_user.id
            )
            db.session.add(assignment)
            created_count += 1
        
        db.session.commit()
        
        if created_count > 0:
            flash(f"Topshiriq {created_count} ta guruh uchun muvaffaqiyatli yaratildi", 'success')
        else:
            flash("Topshiriq yaratilmadi", 'error')
        
        return redirect(url_for('courses.detail', id=id, direction_id=direction_id))
    
    return render_template('courses/create_assignment.html', subject=subject, groups=groups, direction_id=direction_id, allowed_lesson_types=allowed_lesson_types, lessons=lessons)


@bp.route('/assignments/<int:id>')
@login_required
def assignment_detail(id):
    """Topshiriq tafsilotlari"""
    assignment = Assignment.query.get_or_404(id)
    subject = assignment.subject
    
    # O'qituvchi yoki adminmi?
    is_teacher = TeacherSubject.query.filter_by(
        teacher_id=current_user.id,
        subject_id=subject.id,
        group_id=assignment.group_id
    ).first() is not None
    
    if is_teacher or current_user.role == 'admin':
        # Barcha submissions (history uchun)
        all_assignment_submissions = assignment.submissions.order_by(Submission.submitted_at.asc()).all()
        
        # Faol submissions (table uchun)
        submissions = [s for s in all_assignment_submissions if s.is_active]
        
        # Talaba bo'yicha guruhlash (modal uchun)
        submission_history = {}
        for s in all_assignment_submissions:
            if s.student_id not in submission_history:
                submission_history[s.student_id] = []
            submission_history[s.student_id].append(s)
        
        # Javoblar soni va tekshirilmagan javoblar soni
        total_submissions = len(submissions)
        ungraded_count = len([s for s in submissions if s.score is None])
        
        # Har bir submission uchun baholash ruxsati
        can_grade_submissions = {}
        if current_user.role == 'admin':
            # Admin barcha javoblarni baholay oladi
            can_manage_assignment = True
            for sub in submissions:
                can_grade_submissions[sub.id] = True
        else:
            # O'qituvchi uchun - yo'nalish va dars turi bo'yicha tekshiruv
            if assignment.direction_id and assignment.lesson_type:
                direction_group_ids = [g.id for g in Group.query.filter_by(direction_id=assignment.direction_id).all()]
                
                # Ushbu yo'nalishda ushbu dars turiga biriktirilganligini tekshirish
                teacher_assignment = TeacherSubject.query.filter(
                    TeacherSubject.teacher_id == current_user.id,
                    TeacherSubject.subject_id == subject.id,
                    TeacherSubject.group_id.in_(direction_group_ids),
                    TeacherSubject.lesson_type == assignment.lesson_type
                ).first()
                
                # Agar to'g'ridan-to'g'ri biriktirish topilmasa, "laboratoriya" va "kurs_ishi" uchun amaliyot orqali tekshirish
                if not teacher_assignment:
                    if assignment.lesson_type in ['laboratoriya', 'kurs_ishi']:
                        teacher_assignment = TeacherSubject.query.filter(
                            TeacherSubject.teacher_id == current_user.id,
                            TeacherSubject.subject_id == subject.id,
                            TeacherSubject.group_id.in_(direction_group_ids),
                            TeacherSubject.lesson_type == 'amaliyot'
                        ).first()
                
                has_permission = teacher_assignment is not None
                can_manage_assignment = has_permission or current_user.role == 'admin'
                for sub in submissions:
                    can_grade_submissions[sub.id] = has_permission
            else:
                can_manage_assignment = current_user.role == 'admin'
                # Agar yo'nalish yoki dars turi yo'q bo'lsa, ruxsat yo'q
                for sub in submissions:
                    can_grade_submissions[sub.id] = False
        
        # Guruh talabalari
        group_students = User.query.filter_by(
            role='student',
            group_id=assignment.group_id
        ).all()
        
        # Topshirmagan talabalar
        submitted_ids = [s.student_id for s in submissions]
        not_submitted = [s for s in group_students if s.id not in submitted_ids]
        
        # Tegishli mavzular
        lesson_ids = assignment.get_lesson_ids_list() if assignment.lesson_ids else []
        related_lessons = []
        if lesson_ids:
            related_lessons = Lesson.query.filter(Lesson.id.in_(lesson_ids)).all()
        
        # Har bir talaba uchun eng yuqori ballni hisoblash
        student_highest_scores = {}
        for student_id, history in submission_history.items():
            scores = [h.score for h in history if h.score is not None]
            student_highest_scores[student_id] = max(scores) if scores else 0

        return render_template('courses/assignment_submissions.html',
                             assignment=assignment,
                             submissions=submissions,
                             not_submitted=not_submitted,
                             total_submissions=total_submissions,
                             ungraded_count=ungraded_count,
                             can_grade_submissions=can_grade_submissions,
                             can_manage_assignment=can_manage_assignment,
                             related_lessons=related_lessons,
                             submission_history=submission_history,
                             student_highest_scores=student_highest_scores,
                             direction_id=assignment.direction_id)

    else:
        # Talaba uchun - barcha javoblar (oxirgi yuborilgan birinchi)
        is_overdue = False
        student_submissions = Submission.query.filter_by(
            student_id=current_user.id,
            assignment_id=id
        ).order_by(Submission.submitted_at.asc()).all()
        
        # Faol submission (agar mavjud bo'lsa)
        submission = None
        if student_submissions:
            # Birinchisi faol bo'lishi kerak (sorting bo'yicha), lekin tekshiramiz
            for sub in student_submissions:
                if sub.is_active:
                    submission = sub
                    break
            
            # Agar faol topilmasa, eng oxirgisini olamiz
            if not submission:
                submission = student_submissions[0]
        
        # Qayta topshirish imkoniyati
        remaining_attempts = 3 - len(student_submissions)
        if remaining_attempts < 0: remaining_attempts = 0
        
        can_resubmit = True
        resubmission_count = 0
        if submission:
            resubmission_count = submission.resubmission_count
            can_resubmit = submission.can_resubmit(max_resubmissions=3)
            
        # Eng yuqori ballni hisoblash
        highest_score = 0
        if student_submissions:
            scores = [s.score for s in student_submissions if s.score is not None]
            highest_score = max(scores) if scores else 0
        
        # Muddat o'tganligini tekshirish
        if assignment.due_date:
            is_overdue = datetime.utcnow() > assignment.due_date
        else:
            is_overdue = False
        
        # Tegishli mavzular
        lesson_ids = assignment.get_lesson_ids_list() if assignment.lesson_ids else []
        related_lessons = []
        if lesson_ids:
            related_lessons = Lesson.query.filter(Lesson.id.in_(lesson_ids)).all()
        
        # O'qituvchi yoki admin uchun statistika
        is_viewer_teacher = TeacherSubject.query.filter_by(
            teacher_id=current_user.id,
            subject_id=subject.id,
            group_id=assignment.group_id
        ).first() is not None
        
        total_submissions = None
        ungraded_count = None
        can_manage_assignment = False
        if current_user.role == 'admin':
            can_manage_assignment = True
        elif is_viewer_teacher:
            # Dars turi bo'yicha ruxsatni tekshirish
            ts = TeacherSubject.query.filter_by(
                teacher_id=current_user.id,
                subject_id=subject.id,
                group_id=assignment.group_id,
                lesson_type=assignment.lesson_type
            ).first()
            if ts:
                can_manage_assignment = True
            elif assignment.lesson_type in ['laboratoriya', 'kurs_ishi']:
                # Amaliyot orqali ruxsat berish
                ts_amaliyot = TeacherSubject.query.filter_by(
                    teacher_id=current_user.id,
                    subject_id=subject.id,
                    group_id=assignment.group_id,
                    lesson_type='amaliyot'
                ).first()
                if ts_amaliyot:
                    can_manage_assignment = True
        
        return render_template('courses/assignment_detail.html',
                             assignment=assignment,
                             submission=submission,
                             student_submissions=student_submissions,
                             highest_score=highest_score,
                             remaining_attempts=remaining_attempts,
                             can_resubmit=can_resubmit,
                             resubmission_count=resubmission_count,
                             is_overdue=is_overdue,
                             related_lessons=related_lessons,
                             total_submissions=total_submissions,
                             ungraded_count=ungraded_count,
                             is_viewer_teacher=is_viewer_teacher,
                             can_manage_assignment=can_manage_assignment,
                             direction_id=assignment.direction_id)


@bp.route('/assignments/<int:id>/submit', methods=['POST'])
@login_required
def submit_assignment(id):
    """Topshiriq topshirish"""
    if current_user.role != 'student':
        flash("Faqat talabalar topshiriq yuborishi mumkin", 'error')
        return redirect(url_for('courses.assignment_detail', id=id))
    
    assignment = Assignment.query.get_or_404(id)
    
    # Talaba shu guruhga tegishlimi?
    if assignment.group_id != current_user.group_id:
        flash("Bu topshiriq sizning guruhingiz uchun emas", 'error')
        return redirect(url_for('courses.index'))
    
    content = request.form.get('content', '').strip()
    file_url = None
    
    # Fayl yuklash
    if 'file' in request.files:
        file = request.files['file']
        if file and file.filename:
            # Fayl formatini tekshirish
            if not allowed_submission_file(file.filename):
                flash("Ruxsat berilmagan fayl formati. Ruxsatli formatlar: PDF, DOC, DOCX, XLS, XLSX, JPG, JPEG, PNG, GIF, BMP, TXT, RTF", 'error')
                return redirect(url_for('courses.assignment_detail', id=id))
            
            # Fayl hajmini tekshirish (2 MB)
            file.seek(0, os.SEEK_END)
            file_size = file.tell()
            file.seek(0)
            
            max_size = current_app.config.get('MAX_SUBMISSION_SIZE', 2 * 1024 * 1024)
            if file_size > max_size:
                flash(f"Fayl hajmi {max_size / (1024 * 1024):.0f} MB dan oshmasligi kerak", 'error')
                return redirect(url_for('courses.assignment_detail', id=id))
            
            # Faylni saqlash
            ext = file.filename.rsplit('.', 1)[1].lower()
            filename = f"{uuid.uuid4().hex}.{ext}"
            submissions_folder = os.path.join(current_app.config['UPLOAD_FOLDER'], 'submissions')
            file_path = os.path.join(submissions_folder, filename)
            file.save(file_path)
            file_url = filename
    
    # Fayl majburiy bo'lsa tekshirish
    if assignment.file_required and not file_url:
        flash("Bu topshiriq uchun fayl yuklash majburiy!", 'error')
        return redirect(url_for('courses.assignment_detail', id=id))
    
    # Agar na content, na file bo'lmasa
    if not content and not file_url:
        flash("Javob yoki fayl yuborishingiz kerak", 'error')
        return redirect(url_for('courses.assignment_detail', id=id))
    
    # Muddat tekshiruvi
    # Deadline tekshiruvi (kun oxirigacha - 23:59:59)
    if assignment.due_date:
        if isinstance(assignment.due_date, datetime):
            deadline_end = assignment.due_date.replace(hour=23, minute=59, second=59)
        else:
            from datetime import time as dt_time
            deadline_end = datetime.combine(assignment.due_date, dt_time(23, 59, 59))
        if get_tashkent_time() > deadline_end:
            flash("Topshiriq muddati o'tgan. Qayta topshirish mumkin emas.", 'error')
            return redirect(url_for('courses.assignment_detail', id=id))
    
    # Faol submission topish (oxirgi yuborilgan)
    active_submission = Submission.query.filter_by(
        student_id=current_user.id,
        assignment_id=id,
        is_active=True
    ).first()
    
    if active_submission:
        # Qayta topshirish imkoniyati tekshiruvi
        if not active_submission.can_resubmit(max_resubmissions=3):
            flash("Siz allaqachon 3 marta topshirdingiz. Qo'shimcha imkoniyat uchun o'qituvchi bilan bog'laning.", 'error')
            return redirect(url_for('courses.assignment_detail', id=id))
        
        # Eski submission'ni faol emas qilish
        active_submission.is_active = False
        
        # Yangi submission yaratish
        new_submission = Submission(
            student_id=current_user.id,
            assignment_id=id,
            content=content,
            file_url=file_url,
            resubmission_count=active_submission.resubmission_count + 1,
            is_active=True
        )
        db.session.add(new_submission)
        flash(f"Javobingiz qayta yuborildi ({new_submission.resubmission_count}/3)", 'success')
    else:
        # Birinchi marta topshirish
        submission = Submission(
            student_id=current_user.id,
            assignment_id=id,
            content=content,
            file_url=file_url,
            resubmission_count=0,
            is_active=True
        )
        db.session.add(submission)
        flash("Javobingiz qabul qilindi", 'success')
    
    db.session.commit()
    return redirect(url_for('courses.assignment_detail', id=id))


@bp.route('/submissions/<int:id>/edit', methods=['POST'])
@login_required
def edit_submission(id):
    """Javobni tahrirlash (faqat baholanmagan bo'sa)"""
    submission = Submission.query.get_or_404(id)
    
    if submission.student_id != current_user.id:
        flash("Siz faqat o'z javobingizni tahrirlay olasiz", 'error')
        return redirect(url_for('courses.assignment_detail', id=submission.assignment_id))
    
    if submission.score is not None:
        flash("Baholangan topshiriqni tahrirlab bo'lmaydi", 'error')
        return redirect(url_for('courses.assignment_detail', id=submission.assignment_id))
    
    content = request.form.get('content', '').strip()
    file_url = submission.file_url
    
    # Fayl yangilash
    if 'file' in request.files:
        file = request.files['file']
        if file and file.filename:
            if not allowed_submission_file(file.filename):
                flash("Ruxsat berilmagan fayl formati", 'error')
                return redirect(url_for('courses.assignment_detail', id=submission.assignment_id))
            
            # Eski faylni o'chirish (ixtiyoriy, lekin yaxshi amaliyot)
            # if submission.file_url:
            #     try:
            #         os.remove(os.path.join(current_app.config['UPLOAD_FOLDER'], 'submissions', submission.file_url))
            #     except: pass

            ext = file.filename.rsplit('.', 1)[1].lower()
            filename = f"{uuid.uuid4().hex}.{ext}"
            submissions_folder = os.path.join(current_app.config['UPLOAD_FOLDER'], 'submissions')
            file.save(os.path.join(submissions_folder, filename))
            file_url = filename
    
    # Agar na content, na file bo'lmasa
    if not content and not file_url:
        flash("Javob yoki fayl bo'lishi kerak", 'error')
        return redirect(url_for('courses.assignment_detail', id=submission.assignment_id))
    
    submission.content = content
    submission.file_url = file_url
    db.session.commit()
    
    flash("Javobingiz muvaffaqiyatli yangilandi", 'success')
    return redirect(url_for('courses.assignment_detail', id=submission.assignment_id))


@bp.route('/submissions/<int:id>/allow-resubmission', methods=['POST'])
@login_required
def allow_resubmission(id):
    """O'qituvchi qayta topshirish imkonini berish"""
    submission = Submission.query.get_or_404(id)
    assignment = submission.assignment
    subject = assignment.subject
    
    # O'qituvchi yoki adminmi?
    is_teacher = TeacherSubject.query.filter_by(
        teacher_id=current_user.id,
        subject_id=subject.id,
        group_id=assignment.group_id
    ).first() is not None
    
    if not (is_teacher or current_user.role == 'admin'):
        flash("Sizda bu amalni bajarish uchun ruxsat yo'q", 'error')
        return redirect(url_for('courses.assignment_detail', id=assignment.id))
    
    # Qayta topshirish imkonini berish
    submission.allow_resubmission = True
    db.session.commit()
    
    flash("Talabaga qayta topshirish imkoni berildi", 'success')
    return redirect(url_for('courses.assignment_detail', id=assignment.id))


@bp.route('/submissions/<int:id>/grade', methods=['POST'])
@login_required
def grade_submission(id):
    """Bahoni qo'yish"""
    submission = Submission.query.get_or_404(id)
    assignment = submission.assignment
    subject = assignment.subject
    
    # Admin uchun ruxsat tekshiruvi
    if current_user.role == 'admin':
        submission.score = int(request.form.get('score', 0))
        submission.feedback = request.form.get('feedback')
        submission.graded_at = datetime.utcnow()
        submission.graded_by = current_user.id
        db.session.commit()
        flash("Baho muvaffaqiyatli qo'yildi", 'success')
        return redirect(url_for('courses.assignment_detail', id=assignment.id))
    
    # O'qituvchi uchun - yo'nalish va dars turi bo'yicha tekshiruv
    if not assignment.direction_id or not assignment.lesson_type:
        flash("Topshiriq yo'nalish yoki dars turiga biriktirilmagan", 'error')
        return redirect(url_for('courses.assignment_detail', id=assignment.id))
    
    # Ushbu yo'nalishdagi guruhlar
    direction_group_ids = [g.id for g in Group.query.filter_by(direction_id=assignment.direction_id).all()]
    
    # Ushbu yo'nalishda ushbu dars turiga biriktirilganligini tekshirish
    teacher_assignment = TeacherSubject.query.filter(
        TeacherSubject.teacher_id == current_user.id,
        TeacherSubject.subject_id == subject.id,
        TeacherSubject.group_id.in_(direction_group_ids),
        TeacherSubject.lesson_type == assignment.lesson_type
    ).first()
    
    # Agar to'g'ridan-to'g'ri biriktirish topilmasa, "laboratoriya" va "kurs_ishi" uchun amaliyot orqali tekshirish
    if not teacher_assignment:
        if assignment.lesson_type in ['laboratoriya', 'kurs_ishi']:
            curriculum_item = DirectionCurriculum.query.filter_by(
                direction_id=assignment.direction_id,
                subject_id=subject.id
            ).first()
            
            if curriculum_item:
                if assignment.lesson_type == 'laboratoriya' and (curriculum_item.hours_laboratoriya or 0) > 0:
                    teacher_assignment = TeacherSubject.query.filter(
                        TeacherSubject.teacher_id == current_user.id,
                        TeacherSubject.subject_id == subject.id,
                        TeacherSubject.group_id.in_(direction_group_ids),
                        TeacherSubject.lesson_type == 'amaliyot'
                    ).first()
                elif assignment.lesson_type == 'kurs_ishi' and (curriculum_item.hours_kurs_ishi or 0) > 0:
                    teacher_assignment = TeacherSubject.query.filter(
                        TeacherSubject.teacher_id == current_user.id,
                        TeacherSubject.subject_id == subject.id,
                        TeacherSubject.group_id.in_(direction_group_ids),
                        TeacherSubject.lesson_type == 'amaliyot'
                    ).first()
    
    if not teacher_assignment:
        flash(f"Sizda ushbu yo'nalishda '{assignment.lesson_type}' dars turiga biriktirilganligi yo'q. Faqat o'zingizga biriktirilgan dars turlari uchun baho qo'yishingiz mumkin.", 'error')
        return redirect(url_for('courses.assignment_detail', id=assignment.id))
    
    submission.score = int(request.form.get('score', 0))
    submission.feedback = request.form.get('feedback')
    submission.graded_at = datetime.utcnow()
    submission.graded_by = current_user.id
    db.session.commit()
    
    flash("Baho muvaffaqiyatli qo'yildi", 'success')
    return redirect(url_for('courses.assignment_detail', id=assignment.id))


@bp.route('/grades')
@login_required
def grades():
    """Baholar"""
    if current_user.role == 'student':
        # Talabaning guruhi, yo'nalishi va joriy semestrini aniqlash
        group = Group.query.get(current_user.group_id) if current_user.group_id else None
        direction_id = group.direction_id if group else None
        current_semester = current_user.semester or 1
        
        # Talabaning yo'nalishi va joriy semestri bo'yicha barcha fanlarini olish
        all_subjects = []
        if direction_id:
            # DirectionCurriculum orqali faqat joriy semestr uchun fanlarni olish
            curriculum_items = DirectionCurriculum.query.filter_by(
                direction_id=direction_id,
                semester=current_semester
            ).all()
            subject_ids = [item.subject_id for item in curriculum_items]
            all_subjects = Subject.query.filter(Subject.id.in_(subject_ids)).order_by(Subject.name).all()
        elif current_user.group_id:
            # Guruhga biriktirilgan fanlar (TeacherSubject orqali)
            subject_ids = [ts.subject_id for ts in TeacherSubject.query.filter_by(group_id=current_user.group_id).all()]
            all_subjects = Subject.query.filter(Subject.id.in_(subject_ids)).order_by(Subject.name).all()

        # Talabaga tegishli barcha topshiriqlarni olish
        assignments_query = Assignment.query
        if group and direction_id:
            assignments_query = assignments_query.filter(
                (Assignment.group_id == current_user.group_id) | (Assignment.group_id.is_(None)),
                (Assignment.direction_id == direction_id) | (Assignment.direction_id.is_(None))
            )
        elif current_user.group_id:
            assignments_query = assignments_query.filter(
                (Assignment.group_id == current_user.group_id) | (Assignment.group_id.is_(None))
            )
        else:
            assignments_query = assignments_query.filter(False)
            
        # Faqat hozir topilgan fanlarga tegishli topshiriqlarni filtrlash
        allowed_subject_ids = [s.id for s in all_subjects]
        all_assignments = assignments_query.filter(Assignment.subject_id.in_(allowed_subject_ids)).all()
        
        # Talabaning barcha topshiriqlari uchun eng yuqori baholarni olish
        user_submissions = Submission.query.filter_by(student_id=current_user.id).all()
        all_submissions_map = {}
        for s in user_submissions:
            if s.assignment_id not in all_submissions_map:
                all_submissions_map[s.assignment_id] = s
            else:
                # Agar joriy submission bahosi mavjud bo'lsa va u oldingisidan yuqori bo'lsa
                current_max = all_submissions_map[s.assignment_id]
                if s.score is not None:
                    if current_max.score is None or s.score > current_max.score:
                        all_submissions_map[s.assignment_id] = s
                # Agar ikkalasi ham None bo'lsa, is_active=True bo'lganini saqlab qolamiz (yoki shunchaki oxirgisini)
                elif current_max.score is None and s.is_active:
                    all_submissions_map[s.assignment_id] = s
        
        # Fanlar bo'yicha guruhlash
        grades_by_subject = {}
        
        # Avval joriy semestrdagi barcha fanlarni grades_by_subject ga qo'shib chiqamiz
        for subject in all_subjects:
            grades_by_subject[subject.id] = {
                'subject': subject,
                'submissions': [],
                'total_score': 0,
                'max_score': 0,
                'percent': 0,
                'grade': None
            }

        # Keyin topshiriqlarni tegishli fanlarga joylashtiramiz
        for assignment in all_assignments:
            subject = assignment.subject
            # Agar fan grades_by_subject da bo'lmasa (masalan, yo'nalishdan tashqari fan bo'lsa), qo'shamiz
            if subject.id not in grades_by_subject:
                grades_by_subject[subject.id] = {
                    'subject': subject,
                    'submissions': [],
                    'total_score': 0,
                    'max_score': 0,
                    'percent': 0,
                    'grade': None
                }
            
            submission = all_submissions_map.get(assignment.id)
            score = submission.score if (submission and submission.score is not None) else 0
            
            # Dictionary sifatida qo'shamiz
            grades_by_subject[subject.id]['submissions'].append({
                'assignment': assignment,
                'submission': submission,
                'score': score,
                'feedback': submission.feedback if submission else None,
                'graded_at': submission.graded_at if submission else None
            })
            
            # Har bir topshiriqning max_score sini jami max_score ga qo'shamiz
            # (talaba topshirgan yoki topshirmaganligidan qat'iy nazar)
            grades_by_subject[subject.id]['max_score'] += assignment.max_score
            
            # Agar baholangan bo'lsa, ballni qo'shamiz
            if submission and submission.score is not None:
                grades_by_subject[subject.id]['total_score'] += score
        
        # Baholarni foiz va harfga o'girish (admindagi baholash tizimi asosida)
        for data in grades_by_subject.values():
            data['percent'] = round((data['total_score'] / data['max_score']) * 100) if data['max_score'] > 0 else 0
            data['grade'] = GradeScale.get_grade(data['percent'])
        
        def grade_classes(color: str):
            return {
                'bar': 'bg-green-500' if color == 'green' else
                       'bg-blue-500' if color == 'blue' else
                       'bg-yellow-500' if color == 'yellow' else
                       'bg-orange-500' if color == 'orange' else
                       'bg-red-500' if color == 'red' else
                       'bg-gray-400',
                'light': 'bg-green-100' if color == 'green' else
                         'bg-blue-100' if color == 'blue' else
                         'bg-yellow-100' if color == 'yellow' else
                         'bg-orange-100' if color == 'orange' else
                         'bg-red-100' if color == 'red' else
                         'bg-gray-100',
                'text': 'text-green-700' if color == 'green' else
                        'text-blue-700' if color == 'blue' else
                        'text-yellow-700' if color == 'yellow' else
                        'text-orange-700' if color == 'orange' else
                        'text-red-700' if color == 'red' else
                        'text-gray-800',
            }
        
        for data in grades_by_subject.values():
            color = data['grade'].color if data['grade'] else None
            data['classes'] = grade_classes(color)
        
        # Umumiy natija
        total_score = sum(d['total_score'] for d in grades_by_subject.values())
        max_score = sum(d['max_score'] for d in grades_by_subject.values())
        overall_percent = round((total_score / max_score) * 100) if max_score > 0 else 0
        overall_grade = GradeScale.get_grade(overall_percent)
        overall_classes = grade_classes(overall_grade.color if overall_grade else None)
        
        grade_scales = GradeScale.get_all_ordered()
        
        return render_template(
            'courses/grades.html',
            grades_by_subject=grades_by_subject,
            overall_percent=overall_percent,
            overall_grade=overall_grade,
            overall_classes=overall_classes,
            grade_scales=grade_scales,
            total_score=total_score,
            max_score=max_score
        )
    
    elif current_user.role == 'teacher':
        # O'qituvchining fanlari va guruhlari
        teacher_assignments = TeacherSubject.query.filter_by(teacher_id=current_user.id).all()
        
        subject_groups = {}
        for ta in teacher_assignments:
            if ta.subject.id not in subject_groups:
                subject_groups[ta.subject.id] = {
                    'subject': ta.subject,
                    'groups': []
                }
            subject_groups[ta.subject.id]['groups'].append(ta.group)
        
        return render_template('courses/teacher_grades.html', subject_groups=subject_groups)
    
    else:
        return redirect(url_for('main.dashboard'))


@bp.route('/grades/<int:subject_id>/<int:group_id>')
@login_required
def group_grades(subject_id, group_id):
    """Guruh baholari"""
    subject = Subject.query.get_or_404(subject_id)
    group = Group.query.get_or_404(group_id)
    
    # Tekshirish
    is_teacher = TeacherSubject.query.filter_by(
        teacher_id=current_user.id,
        subject_id=subject_id,
        group_id=group_id
    ).first() is not None
    
    if not is_teacher and current_user.role not in ['admin', 'dean']:
        flash("Sizda bu sahifani ko'rish huquqi yo'q", 'error')
        return redirect(url_for('courses.grades'))
    
    # Guruh talabalari
    students = User.query.filter_by(role='student', group_id=group_id).order_by(User.full_name).all()
    
    # Fan topshiriqlari
    assignments = Assignment.query.filter_by(subject_id=subject_id, group_id=group_id).all()
    
    # Har bir talabaning baholari
    student_grades = {}
    for student in students:
        student_grades[student.id] = {
            'student': student,
            'submissions': {},
            'total': 0,
            'max_total': 0
        }
        for assignment in assignments:
            student_submissions = Submission.query.filter_by(
                student_id=student.id,
                assignment_id=assignment.id
            ).all()
            
            best_sub = None
            if student_submissions:
                # Eng yuqori baholi submissionni topish
                for s in student_submissions:
                    if best_sub is None:
                        best_sub = s
                    elif s.score is not None:
                        if best_sub.score is None or s.score > best_sub.score:
                            best_sub = s
                    elif best_sub.score is None and s.is_active:
                        best_sub = s
            
            student_grades[student.id]['submissions'][assignment.id] = best_sub
            if best_sub and best_sub.score:
                student_grades[student.id]['total'] += best_sub.score
            student_grades[student.id]['max_total'] += assignment.max_score
    
    return render_template('courses/group_grades.html',
                         subject=subject,
                         group=group,
                         students=students,
                         assignments=assignments,
                         student_grades=student_grades)


@bp.route('/grades/<int:subject_id>/<int:group_id>/export')
@login_required
def export_group_grades(subject_id, group_id):
    """Guruh baholarini Excelga eksport (har bir talaba uchun umumiy)"""
    subject = Subject.query.get_or_404(subject_id)
    group = Group.query.get_or_404(group_id)
    
    # Ruxsat: o'qituvchi (tegishli fan+guruh), dekan, admin
    is_teacher = TeacherSubject.query.filter_by(
        teacher_id=current_user.id,
        subject_id=subject_id,
        group_id=group_id
    ).first() is not None
    if not is_teacher and current_user.role not in ['admin', 'dean']:
        flash("Eksport qilish uchun ruxsatingiz yo'q", 'error')
        return redirect(url_for('courses.group_grades', subject_id=subject_id, group_id=group_id))
    
    # Ma'lumotlarni tayyorlash
    students = User.query.filter_by(role='student', group_id=group_id).order_by(User.full_name).all()
    assignments = Assignment.query.filter_by(subject_id=subject_id, group_id=group_id).all()
    
    student_rows = []
    for student in students:
        total = 0
        max_total = 0
        for assignment in assignments:
            student_submissions = Submission.query.filter_by(
                student_id=student.id,
                assignment_id=assignment.id
            ).all()
            
            best_score = 0
            if student_submissions:
                scores = [s.score for s in student_submissions if s.score is not None]
                best_score = max(scores) if scores else 0
                
            total += best_score
            max_total += assignment.max_score
        percent = round((total / max_total) * 100) if max_total > 0 else 0
        grade = GradeScale.get_grade(percent)
        student_rows.append({
            'student': student,
            'total': total,
            'max_total': max_total,
            'percent': percent,
            'grade': grade
        })
    
    try:
        from app.utils.excel_export import create_group_grades_excel
    except ImportError:
        flash("Excel export uchun 'openpyxl' o'rnatilmagan. 'pip install openpyxl' bajaring.", 'error')
        return redirect(url_for('courses.group_grades', subject_id=subject_id, group_id=group_id))
    
    excel_file = create_group_grades_excel(subject, group, student_rows)
    curriculum = DirectionCurriculum.query.filter_by(direction_id=group.direction_id, subject_id=subject.id).first()
    semester_text = f", {curriculum.semester}-semestr" if curriculum else ""
    filename = f"{subject.name}, {group.name}{semester_text}.xlsx"
    
    return Response(
        excel_file,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'}
    )


@bp.route('/grades/<int:subject_id>/<int:group_id>/export-detailed')
@login_required
def export_detailed_group_grades(subject_id, group_id):
    """Guruh baholarini batafsil (har bir topshiriq bilan) Excelga eksport qilish"""
    subject = Subject.query.get_or_404(subject_id)
    group = Group.query.get_or_404(group_id)
    
    # Ruxsat: o'qituvchi (tegishli fan+guruh), dekan, admin
    is_teacher = TeacherSubject.query.filter_by(
        teacher_id=current_user.id,
        subject_id=subject_id,
        group_id=group_id
    ).first() is not None
    if not is_teacher and current_user.role not in ['admin', 'dean']:
        flash("Eksport qilish uchun ruxsatingiz yo'q", 'error')
        return redirect(url_for('courses.detail', id=subject_id))
    
    # Ma'lumotlarni tayyorlash
    students = User.query.filter_by(role='student', group_id=group_id).order_by(User.full_name).all()
    assignments = Assignment.query.filter_by(subject_id=subject_id, group_id=group_id).order_by(Assignment.due_date).all()
    
    # Agar guruh uchun topshiriqlar bo'lmasa, umumiy fanda yo'nalishsiz bo'lgan topshiriqlarni ham olishi mumkin
    if not assignments:
        assignments = Assignment.query.filter_by(subject_id=subject_id, group_id=None).order_by(Assignment.due_date).all()
    
    matrix = []
    for student in students:
        row = {
            'student_id': student.student_id or '-',
            'student_name': student.full_name.upper() if student.full_name else '-',
            'scores': [],
            'total_score': 0,
            'max_total': 0
        }
        for assignment in assignments:
            # Har bir topshiriq uchun eng yuqori bahoni topish
            student_submissions = Submission.query.filter_by(
                student_id=student.id,
                assignment_id=assignment.id
            ).all()
            
            submission = None
            if student_submissions:
                # Eng yuqori baholi submissionni topish
                for s in student_submissions:
                    if submission is None:
                        submission = s
                    elif s.score is not None:
                        if submission.score is None or s.score > submission.score:
                            submission = s
                    elif submission.score is None and s.is_active:
                        submission = s
            score = submission.score if submission and submission.score is not None else 0
            row['scores'].append(score)
            row['total_score'] += score
            row['max_total'] += (assignment.max_score or 0)
        
        row['percent'] = round((row['total_score'] / row['max_total']) * 100) if row['max_total'] > 0 else 0
        matrix.append(row)
    
    try:
        from app.utils.excel_export import create_detailed_assignment_export_excel
    except ImportError:
        flash("Excel export uchun 'openpyxl' o'rnatilmagan.", 'error')
        return redirect(url_for('courses.detail', id=subject_id))
    
    try:
        excel_file = create_detailed_assignment_export_excel(subject, group, assignments, matrix)
        curriculum = DirectionCurriculum.query.filter_by(direction_id=group.direction_id, subject_id=subject.id).first()
        semester_text = f", {curriculum.semester}-semestr" if curriculum else ""
        filename = f"{subject.name}, {group.name}{semester_text} (Batafsil).xlsx"
        
        return Response(
            excel_file,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            headers={'Content-Disposition': f'attachment; filename="{filename}"'}
        )
    except Exception as e:
        flash(f"Eksport qilishda xatolik yuz berdi: {str(e)}", 'error')
        return redirect(url_for('courses.detail', id=subject_id))


@bp.route('/assignments/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit_assignment(id):
    """Topshiriqni tahrirlash"""
    assignment = Assignment.query.get_or_404(id)
    subject = assignment.subject
    direction_id = assignment.direction_id
    
    # Tanlangan rol
    current_role = session.get('current_role', current_user.role)
    
    # Ruxsat tekshiruvi: Admin yoki biriktirilgan dars turi bo'yicha o'qituvchi
    can_edit = False
    if (current_user.role == 'admin' or current_user.role == 'dean') and current_role != 'teacher':
        can_edit = True
    else:
        # Ruxsat: Agar o'qituvchi o'zi yaratgan bo'lsa
        if assignment.created_by == current_user.id:
            can_edit = True
        else:
            # O'qituvchining biriktirilganligini tekshirish (guruh va dars turi bo'yicha)
            is_assigned = TeacherSubject.query.filter_by(
                teacher_id=current_user.id,
                subject_id=subject.id,
                group_id=assignment.group_id,
                lesson_type=assignment.lesson_type
            ).first() is not None
            
            # Laboratoriya va kurs_ishi uchun amaliyot orqali tekshirish
            if not is_assigned and assignment.lesson_type in ['laboratoriya', 'kurs_ishi']:
                is_assigned = TeacherSubject.query.filter_by(
                    teacher_id=current_user.id,
                    subject_id=subject.id,
                    group_id=assignment.group_id,
                    lesson_type='amaliyot'
                ).first() is not None
            
            # Global topshiriq bo'lsa (group_id is None)
            if not is_assigned and assignment.group_id is None:
                is_assigned = TeacherSubject.query.filter_by(
                    teacher_id=current_user.id,
                    subject_id=subject.id,
                    lesson_type=assignment.lesson_type
                ).first() is not None
                
                # Laboratoriya va kurs_ishi uchun amaliyot orqali tekshirish
                if not is_assigned and assignment.lesson_type in ['laboratoriya', 'kurs_ishi']:
                    is_assigned = TeacherSubject.query.filter_by(
                        teacher_id=current_user.id,
                        subject_id=subject.id,
                        lesson_type='amaliyot'
                    ).first() is not None
                
            if is_assigned:
                can_edit = True
            
    if not can_edit:
        flash("Sizda topshiriqni tahrirlash uchun ruxsat yo'q", 'error')
        return redirect(url_for('courses.assignment_detail', id=id))
    
    # Tanlangan rol
    current_role = session.get('current_role', current_user.role)
    is_acting_as_teacher = (current_role == 'teacher') or (current_user.role == 'teacher')
    
    # O'qituvchiga biriktirilgan dars turlarini topish
    allowed_lesson_types = []
    if is_acting_as_teacher:
        lesson_types_set = set()
        if direction_id:
            direction_group_ids = [g.id for g in Group.query.filter_by(direction_id=direction_id).all()]
            teacher_assignments = TeacherSubject.query.filter(
                TeacherSubject.teacher_id == current_user.id,
                TeacherSubject.subject_id == subject.id,
                TeacherSubject.group_id.in_(direction_group_ids)
            ).all()
            for ta in teacher_assignments:
                if ta.lesson_type:
                    lesson_types_set.add(ta.lesson_type)
            
            curriculum_item = DirectionCurriculum.query.filter_by(
                direction_id=direction_id,
                subject_id=subject.id
            ).first()
            if curriculum_item:
                if (curriculum_item.hours_laboratoriya or 0) > 0:
                    lab_teacher = TeacherSubject.query.filter(
                        TeacherSubject.subject_id == subject.id,
                        TeacherSubject.group_id.in_(direction_group_ids),
                        TeacherSubject.teacher_id == current_user.id,
                        TeacherSubject.lesson_type.in_(['laboratoriya', 'amaliyot'])
                    ).first()
                    if lab_teacher:
                        lesson_types_set.add('laboratoriya')
                
                if (curriculum_item.hours_kurs_ishi or 0) > 0:
                    kurs_teacher = TeacherSubject.query.filter(
                        TeacherSubject.subject_id == subject.id,
                        TeacherSubject.group_id.in_(direction_group_ids),
                        TeacherSubject.teacher_id == current_user.id,
                        TeacherSubject.lesson_type.in_(['kurs_ishi', 'amaliyot'])
                    ).first()
                    if kurs_teacher:
                        lesson_types_set.add('kurs_ishi')
        
        lesson_type_names_map = {
            'maruza': 'Maruza',
            'amaliyot': 'Amaliyot',
            'laboratoriya': 'Laboratoriya',
            'seminar': 'Seminar',
            'kurs_ishi': 'Kurs ishi'
        }
        lesson_type_order = ['maruza', 'amaliyot', 'laboratoriya', 'seminar', 'kurs_ishi']
        for lt_key in lesson_type_order:
            if lt_key in lesson_types_set:
                allowed_lesson_types.append({'value': lt_key, 'name': lesson_type_names_map.get(lt_key, lt_key.capitalize())})
    elif (current_user.role == 'admin' or current_user.role == 'dean') and current_role != 'teacher':
        allowed_lesson_types = [
            {'value': 'maruza', 'name': 'Maruza'},
            {'value': 'amaliyot', 'name': 'Amaliyot'},
            {'value': 'laboratoriya', 'name': 'Laboratoriya'},
            {'value': 'seminar', 'name': 'Seminar'},
            {'value': 'kurs_ishi', 'name': 'Kurs ishi'}
        ]
    
    # Xavfsizlik uchun: joriy topshiriqning dars turi har doim ro'yxatda bo'lishi kerak
    if assignment.lesson_type:
        is_present = any(lt['value'] == assignment.lesson_type for lt in allowed_lesson_types)
        if not is_present:
            lesson_type_names_map = {'maruza': 'Maruza', 'amaliyot': 'Amaliyot', 'laboratoriya': 'Laboratoriya', 'seminar': 'Seminar', 'kurs_ishi': 'Kurs ishi'}
            allowed_lesson_types.append({'value': assignment.lesson_type, 'name': lesson_type_names_map.get(assignment.lesson_type, assignment.lesson_type.capitalize())})
    
    # Darslar ro'yxati
    lessons = []
    if direction_id:
        lessons = Lesson.query.filter_by(
            subject_id=subject.id,
            direction_id=direction_id
        ).order_by(Lesson.order).all()
    
    if request.method == 'POST':
        # Topshiriq ma'lumotlarini yangilash
        assignment.title = request.form.get('title')
        assignment.description = request.form.get('description')
        assignment.lesson_type = request.form.get('lesson_type')
        assignment.max_score = int(request.form.get('max_score', 100))
        
        due_date_str = request.form.get('due_date')
        if due_date_str:
            # Sana 23:59:59 ga o'rnatiladi (Toshkent vaqti)
            # UTC ga o'tkazish uchun 5 soat ayiramiz (18:59:59 UTC)
            assignment.due_date = datetime.strptime(due_date_str, '%Y-%m-%d')
            assignment.due_date = assignment.due_date.replace(hour=18, minute=59, second=59)
        else:
            assignment.due_date = None
        
        selected_lesson_ids = request.form.getlist('lesson_ids')
        assignment.lesson_ids = json.dumps([int(lesson_id) for lesson_id in selected_lesson_ids]) if selected_lesson_ids else None
        
        assignment.file_required = bool(request.form.get('file_required'))
        
        db.session.commit()
        flash("Topshiriq muvaffaqiyatli yangilandi", 'success')
        return redirect(url_for('courses.detail', id=subject.id, direction_id=direction_id))
    
    # Tanlangan mavzular
    lesson_ids = assignment.get_lesson_ids_list() if assignment.lesson_ids else []
    
    return render_template('courses/edit_assignment.html',
                         assignment=assignment,
                         subject=subject,
                         lessons=lessons,
                         selected_lesson_ids=lesson_ids,
                         allowed_lesson_types=allowed_lesson_types,
                         direction_id=direction_id)


@bp.route('/assignments/<int:id>/delete', methods=['POST'])
@login_required
def delete_assignment(id):
    """Topshiriqni o'chirish"""
    assignment = Assignment.query.get_or_404(id)
    subject = assignment.subject
    
    # Ruxsat tekshiruvi: Admin yoki biriktirilgan dars turi bo'yicha o'qituvchi
    can_delete = False
    # Tanlangan rol
    current_role = session.get('current_role', current_user.role)
    
    if (current_user.role == 'admin' or current_user.role == 'dean') and current_role != 'teacher':
        can_delete = True
    else:
        # Ruxsat: Agar o'qituvchi o'zi yaratgan bo'lsa
        if assignment.created_by == current_user.id:
            can_delete = True
        else:
            # O'qituvchining biriktirilganligini tekshirish (guruh va dars turi bo'yicha)
            is_assigned = TeacherSubject.query.filter_by(
                teacher_id=current_user.id,
                subject_id=subject.id,
                group_id=assignment.group_id,
                lesson_type=assignment.lesson_type
            ).first() is not None
            
            # Laboratoriya va kurs_ishi uchun amaliyot orqali tekshirish
            if not is_assigned and assignment.lesson_type in ['laboratoriya', 'kurs_ishi']:
                is_assigned = TeacherSubject.query.filter_by(
                    teacher_id=current_user.id,
                    subject_id=subject.id,
                    group_id=assignment.group_id,
                    lesson_type='amaliyot'
                ).first() is not None
            
            # Global topshiriq bo'lsa (group_id is None)
            if not is_assigned and assignment.group_id is None:
                is_assigned = TeacherSubject.query.filter_by(
                    teacher_id=current_user.id,
                    subject_id=subject.id,
                    lesson_type=assignment.lesson_type
                ).first() is not None
                
                # Laboratoriya va kurs_ishi uchun amaliyot orqali tekshirish
                if not is_assigned and assignment.lesson_type in ['laboratoriya', 'kurs_ishi']:
                    is_assigned = TeacherSubject.query.filter_by(
                        teacher_id=current_user.id,
                        subject_id=subject.id,
                        lesson_type='amaliyot'
                    ).first() is not None
                
            if is_assigned:
                can_delete = True
            
    if not can_delete:
        flash("Sizda topshiriqni o'chirish uchun ruxsat yo'q", 'error')
        return redirect(url_for('courses.assignment_detail', id=id))
    
    db.session.delete(assignment)
    db.session.commit()
    flash("Topshiriq muvaffaqiyatli o'chirildi", 'success')
    return redirect(url_for('courses.detail', id=subject.id, direction_id=assignment.direction_id))
