import os
import uuid
import json
import random
import re
import html
import requests
from urllib.parse import urlparse, parse_qs, unquote
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, send_from_directory, jsonify, Response, session
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from app.models import Subject, Lesson, Assignment, Submission, User, TeacherSubject, Group, LessonView, GradeScale, DirectionCurriculum, Direction, UserRole, Faculty, Test, TestQuestion, TestOption, TestSubmission
from app import db
from sqlalchemy import or_, cast, String
from datetime import datetime, timedelta
from collections import defaultdict
from app.utils.translations import t

def get_tashkent_time():
    """Toshkent vaqtini qaytaradi (UTC+5)"""
    return datetime.utcnow() + timedelta(hours=5)


def _teacher_lesson_type_variants(lesson_type):
    """Dars turi uchun o'qituvchi biriktirilganida ruxsat beradigan TeacherSubject.lesson_type qiymatlari"""
    if not lesson_type:
        return []
    lt = (lesson_type or '').strip().lower()
    variants_map = {
        'laboratoriya': ['laboratoriya', 'lab', 'lob', 'amaliyot'],
        'kurs_ishi': ['kurs_ishi', 'kurs', 'amaliyot'],
        'maruza': ['maruza'],
        'amaliyot': ['amaliyot'],
        'seminar': ['seminar'],
    }
    return variants_map.get(lt, [lt])


def allowed_video(filename):
    """Video fayl tekshirish"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in current_app.config.get('ALLOWED_VIDEO_EXTENSIONS', {'mp4', 'webm', 'ogg'})

def allowed_submission_file(filename):
    """Topshiriq fayl tekshirish"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in current_app.config.get('ALLOWED_SUBMISSION_EXTENSIONS', {'pdf', 'doc', 'docx', 'xls', 'xlsx', 'jpg', 'jpeg', 'png'})


def extract_youtube_video_id(video_url):
    """YouTube URL dan video ID ni olish"""
    if not video_url:
        return None

    raw_url = (video_url or '').strip()
    if not raw_url:
        return None

    if '://' not in raw_url:
        raw_url = f'https://{raw_url}'

    try:
        parsed = urlparse(raw_url)
    except Exception:
        return None

    host = (parsed.netloc or '').lower()
    if host.startswith('www.'):
        host = host[4:]
    path = (parsed.path or '').strip('/')
    query = parse_qs(parsed.query or '')

    if host == 'youtu.be':
        return path.split('/')[0] if path else None

    if host.endswith('youtube.com'):
        if path == 'watch':
            values = query.get('v') or []
            return values[0] if values else None

        path_parts = path.split('/')
        if len(path_parts) >= 2 and path_parts[0] in ('embed', 'shorts', 'live'):
            return path_parts[1]

    return None


def check_youtube_embed_playability(video_id):
    """YouTube videoni saytda embed qilib ko'rish mumkinligini tekshirish"""
    if not video_id:
        return False, 'Invalid YouTube URL'

    watch_url = f'https://www.youtube.com/watch?v={video_id}'
    try:
        response = requests.get(
            watch_url,
            timeout=10,
            allow_redirects=True,
            headers={'User-Agent': 'Mozilla/5.0 (ELMS Video URL Checker)'}
        )
    except requests.exceptions.RequestException as e:
        return False, str(e)

    if response.status_code != 200 or not response.text:
        return False, f'YouTube status: {response.status_code}'

    try:
        match = re.search(r'ytInitialPlayerResponse\s*=\s*(\{.+?\});', response.text, re.IGNORECASE | re.DOTALL)
        if not match:
            # Aniqlab bo'lmasa, rad etmaymiz
            return True, None

        player_data = json.loads(match.group(1))
        playability = player_data.get('playabilityStatus', {}) or {}
        status = str(playability.get('status') or '').upper()
        playable_in_embed = playability.get('playableInEmbed')
        reason = playability.get('reason') or ''

        # YouTube tomonidan bloklangan holatlar
        if playable_in_embed is False:
            return False, reason or 'Embedding disabled for this video'

        # OK bo'lmasa ko'pincha modalda ham ochilmaydi
        if status and status not in ('OK',):
            return False, reason or status

        return True, None
    except Exception:
        # Parser xatosida noto'g'ri rad qilmaslik uchun
        return True, None


def extract_resource_display_name(resource_url, content_disposition=''):
    """URL yoki response header asosida ko'rsatish nomini olish"""
    cd = (content_disposition or '').strip()
    if cd:
        lower_cd = cd.lower()
        if 'filename*=' in lower_cd:
            part = cd.split('filename*=', 1)[1].split(';', 1)[0].strip().strip('"').strip("'")
            if "''" in part:
                part = part.split("''", 1)[1]
            decoded = unquote(part).strip()
            if decoded:
                return decoded
        if 'filename=' in lower_cd:
            part = cd.split('filename=', 1)[1].split(';', 1)[0].strip().strip('"').strip("'")
            decoded = unquote(part).strip()
            if decoded:
                return decoded

    raw_url = (resource_url or '').strip()
    if not raw_url:
        return 'URL fayl'

    if '://' not in raw_url:
        raw_url = f'https://{raw_url}'

    try:
        parsed = urlparse(raw_url)
    except Exception:
        return 'URL fayl'

    host = (parsed.netloc or '').lower()
    path = (parsed.path or '').strip('/')

    if 'docs.google.com' in host:
        if '/spreadsheets/' in parsed.path:
            return 'Google Sheets'
        if '/document/' in parsed.path:
            return 'Google Docs'
        if '/presentation/' in parsed.path:
            return 'Google Slides'
        if '/forms/' in parsed.path:
            return 'Google Forms'
        return 'Google Docs'

    if 'drive.google.com' in host:
        return 'Google Drive fayli'

    if path:
        name = unquote(path.split('/')[-1]).strip()
        if name:
            return name

    return parsed.netloc or 'URL fayl'


def extract_google_doc_title(resource_url):
    """Google Docs/Sheets/Slides URL dan sarlavhani olishga urinish"""
    raw_url = (resource_url or '').strip()
    if not raw_url:
        return None

    if '://' not in raw_url:
        raw_url = f'https://{raw_url}'

    try:
        response = requests.get(
            raw_url,
            timeout=10,
            allow_redirects=True,
            headers={'User-Agent': 'Mozilla/5.0 (ELMS File URL Checker)'}
        )
    except requests.exceptions.RequestException:
        return None

    if response.status_code != 200 or not response.text:
        return None

    match = re.search(r'<title[^>]*>(.*?)</title>', response.text, re.IGNORECASE | re.DOTALL)
    if not match:
        return None

    title = html.unescape(match.group(1) or '').strip()
    title = re.sub(r'\s+', ' ', title).strip()
    if not title:
        return None

    for suffix in [
        ' - Google Sheets',
        ' - Google Docs',
        ' - Google Slides',
        ' - Google Forms',
        ' - Google Drive'
    ]:
        if title.endswith(suffix):
            title = title[:-len(suffix)].strip()
            break

    disallowed_titles = {
        'google sheets',
        'google docs',
        'google slides',
        'google forms',
        'google drive',
        'sign in - google accounts',
        'google accounts'
    }
    if not title or title.lower() in disallowed_titles:
        return None

    return title


def parse_lesson_file_data(file_url_value):
    """lesson.file_url ni parse qilib (uploaded_files, external_urls) qaytaradi"""
    uploaded_files = []
    external_urls = []
    raw = (file_url_value or '').strip()

    if not raw:
        return uploaded_files, external_urls

    if raw.startswith('[') and raw.endswith(']'):
        try:
            parsed_items = json.loads(raw)
        except Exception:
            parsed_items = []

        if isinstance(parsed_items, list):
            for item in parsed_items:
                if isinstance(item, dict):
                    # Yangi format: {'type': 'url', 'url': '...'}
                    if item.get('type') == 'url' and item.get('url'):
                        url_value = str(item.get('url')).strip()
                        if url_value and url_value not in external_urls:
                            external_urls.append(url_value)
                        continue

                    # Moslashuvchan: {'url': '...'} ko'rinishi
                    if item.get('url') and not item.get('filename'):
                        url_value = str(item.get('url')).strip()
                        if url_value and url_value not in external_urls:
                            external_urls.append(url_value)
                        continue

                    filename = item.get('filename')
                    if filename:
                        uploaded_files.append({
                            'filename': filename,
                            'original_name': item.get('original_name') or filename
                        })
                elif isinstance(item, str):
                    item_value = item.strip()
                    if item_value.startswith('http://') or item_value.startswith('https://'):
                        if item_value not in external_urls:
                            external_urls.append(item_value)
                    else:
                        uploaded_files.append({'filename': item_value, 'original_name': item_value})

        return uploaded_files, external_urls

    if raw.startswith('http://') or raw.startswith('https://'):
        external_urls = [raw]
    else:
        uploaded_files = [{'filename': raw, 'original_name': raw}]

    return uploaded_files, external_urls


def build_lesson_file_data(uploaded_files, external_urls):
    """uploaded_files va external_urls asosida DB uchun lesson.file_url qiymatini yaratadi"""
    file_items = [f for f in (uploaded_files or []) if isinstance(f, dict) and f.get('filename')]
    urls = []
    for url_value in (external_urls or []):
        normalized = str(url_value).strip()
        if normalized and normalized not in urls:
            urls.append(normalized)

    if file_items and urls:
        mixed = [{'type': 'url', 'url': u} for u in urls] + file_items
        return json.dumps(mixed)
    if file_items:
        return json.dumps(file_items)
    if len(urls) == 1:
        return urls[0]
    if len(urls) > 1:
        return json.dumps([{'type': 'url', 'url': u} for u in urls])
    return None


def _get_active_lesson_types_for_subject_group(subject_id, group):
    """O'quv rejada soatlari > 0 bo'lgan dars turlarini qaytaradi.
    O'quv reja o'zgarganida soatlari o'chirilgan dars turlaridagi o'qituvchilar fan kartasida ko'rsatilmasin."""
    if not group or not group.direction_id:
        return set()
    curr_q = DirectionCurriculum.query.filter_by(
        direction_id=group.direction_id,
        subject_id=subject_id,
        semester=group.semester or 1
    )
    curr_item = DirectionCurriculum.filter_by_group_context(curr_q, group).first()
    if not curr_item:
        return set()
    active = set()
    if (curr_item.hours_maruza or 0) > 0:
        active.add('maruza')
    if (curr_item.hours_amaliyot or 0) > 0:
        active.add('amaliyot')
    if (curr_item.hours_laboratoriya or 0) > 0:
        active.add('laboratoriya')
    if (curr_item.hours_seminar or 0) > 0:
        active.add('seminar')
    if (curr_item.hours_kurs_ishi or 0) > 0:
        active.add('kurs_ishi')
    return active


def _normalize_lesson_type_to_canonical(raw):
    """TeacherSubject.lesson_type ni kanonik formatga o'tkazish (lab->laboratoriya, amal->amaliyot, ...)"""
    if not raw:
        return None
    lt = (raw or '').strip().lower()
    if not lt:
        return None
    if lt in ('maruza', 'amaliyot', 'laboratoriya', 'seminar', 'kurs_ishi'):
        return lt
    if 'maru' in lt or 'lect' in lt:
        return 'maruza'
    if 'sem' in lt:
        return 'seminar'
    if 'lab' in lt or 'lob' in lt:
        return 'laboratoriya'
    if 'kurs' in lt or 'course' in lt:
        return 'kurs_ishi'
    if 'amal' in lt or 'prac' in lt:
        return 'amaliyot'
    return lt


def student_can_access_assignment(assignment, user):
    """Talaba topshiriqni ko'rish/topshirish huquqiga egami?"""
    if not user.group_id or not user.group:
        return False
    if assignment.group_id is not None:
        return assignment.group_id == user.group_id
    # Yo'nalish darajasidagi topshiriq (group_id=None)
    if assignment.direction_id is not None:
        return user.group.direction_id == assignment.direction_id
    return True  # Umumiy topshiriq (group_id va direction_id None)


def _compute_display_order_in_type_for_lessons(lessons, subject_id, direction_id, group=None):
    """Har bir mavzu uchun dars turi ichidagi tartib raqamini (display_order_in_type) hisoblash.
    group berilsa – faqat shu guruh kontekstidagi mavzular hisobga olinadi (semester, enrollment_year, education_type)."""
    if not lessons or direction_id is None:
        return
    # Guruh kontekstidagi guruh ID lari (group berilsa – faqat bir xil semester/yil/ta'lim shaklidagi guruhlar)
    direction_group_ids = [g.id for g in Group.query.filter_by(direction_id=direction_id).all()]
    if group and direction_group_ids:
        cohort_group_ids = [
            g.id for g in Group.query.filter(
                Group.direction_id == direction_id,
                Group.semester == group.semester,
                Group.enrollment_year == group.enrollment_year,
                Group.education_type == group.education_type
            ).all()
        ]
        if cohort_group_ids:
            direction_group_ids = cohort_group_ids
    # Yo'nalish bo'yicha: direction_id to'g'ridan-to'g'ri yoki guruh orqali
    raw_by_dir = Lesson.query.filter_by(
        subject_id=subject_id,
        direction_id=direction_id
    ).order_by(Lesson.order).all()
    raw_by_group = []
    if direction_group_ids:
        raw_by_group = Lesson.query.filter(
            Lesson.subject_id == subject_id,
            Lesson.group_id.in_(direction_group_ids)
        ).order_by(Lesson.order).all()
    seen_ids = {l.id for l in raw_by_dir}
    raw_lessons = list(raw_by_dir)
    for l in raw_by_group:
        if l.id not in seen_ids:
            seen_ids.add(l.id)
            raw_lessons.append(l)
    # group berilsa – direction-level mavzularni saqlaymiz, lekin group-level faqat cohort guruhlardan
    if group and direction_group_ids:
        cohort_set = set(direction_group_ids)
        raw_lessons = [
            l for l in raw_lessons
            if l.group_id is None or l.group_id in cohort_set
        ]
    raw_lessons.sort(key=lambda x: (x.order or 0, x.id))
    type_counters = defaultdict(int)
    display_order_map = {}
    for lesson in raw_lessons:
        lt = _normalize_lesson_type_to_canonical(lesson.lesson_type) or (lesson.lesson_type or '').strip().lower() or ''
        type_counters[lt] += 1
        display_order_map[lesson.id] = type_counters[lt]
    for lesson in lessons:
        lesson.display_order_in_type = display_order_map.get(lesson.id, lesson.order)


bp = Blueprint('courses', __name__, url_prefix='/subjects')

@bp.route('/')
@login_required
def index():
    """Fanlar ro'yxati"""
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '')
    
    # Tanlangan rol
    current_role = session.get('current_role', current_user.role)

    # Admin va o'quv bo'limi uchun /subjects/ da Fanlar bazasi ko'rinishi (bir xil)
    if current_role in ('admin', 'edu_dept'):
        faculty_filter = request.args.get('faculty', type=int)
        course_filter = request.args.get('course', type=int)
        semester_filter = request.args.get('semester', type=int)
        education_type_filter = request.args.get('education_type', '') or None
        direction_filter = request.args.get('direction', type=int)
        group_filter = request.args.get('group', type=int)

        query = DirectionCurriculum.query.join(Direction).join(Subject)

        if faculty_filter:
            query = query.filter(Direction.faculty_id == faculty_filter)
        if direction_filter:
            query = query.filter(DirectionCurriculum.direction_id == direction_filter)
        if semester_filter:
            query = query.filter(DirectionCurriculum.semester == semester_filter)
        if education_type_filter:
            query = query.filter(DirectionCurriculum.education_type == education_type_filter)
        if course_filter:
            min_semester = (course_filter - 1) * 2 + 1
            max_semester = course_filter * 2
            query = query.filter(DirectionCurriculum.semester >= min_semester, DirectionCurriculum.semester <= max_semester)
        if search:
            query = query.filter(
                or_(
                    Subject.name.ilike(f'%{search}%'),
                    Subject.description.ilike(f'%{search}%'),
                    cast(DirectionCurriculum.enrollment_year, String).ilike(f'%{search}%'),
                    Direction.name.ilike(f'%{search}%'),
                    Direction.code.ilike(f'%{search}%'),
                    DirectionCurriculum.education_type.ilike(f'%{search}%')
                )
            )

        curriculum_items = query.order_by(
            DirectionCurriculum.semester,
            Subject.name,
            Direction.name
        ).all()

        if search and not curriculum_items:
            matching_teachers = User.query.filter(
                or_(User.full_name.ilike(f'%{search}%'), User.login.ilike(f'%{search}%'))
            ).all()
            if matching_teachers:
                teacher_ids = [t.id for t in matching_teachers]
                ts_list = TeacherSubject.query.filter(TeacherSubject.teacher_id.in_(teacher_ids)).all()
                seen_curr_ids = set()
                for ts in ts_list:
                    gr = Group.query.get(ts.group_id) if ts.group_id else None
                    if not gr or not gr.enrollment_year or not gr.education_type:
                        continue
                    curr_q = DirectionCurriculum.query.join(Direction).filter(
                        DirectionCurriculum.direction_id == gr.direction_id,
                        DirectionCurriculum.subject_id == ts.subject_id,
                        DirectionCurriculum.semester == gr.semester,
                        DirectionCurriculum.enrollment_year == gr.enrollment_year,
                        DirectionCurriculum.education_type == gr.education_type
                    )
                    if faculty_filter:
                        curr_q = curr_q.filter(Direction.faculty_id == faculty_filter)
                    if direction_filter:
                        curr_q = curr_q.filter(DirectionCurriculum.direction_id == direction_filter)
                    if semester_filter:
                        curr_q = curr_q.filter(DirectionCurriculum.semester == semester_filter)
                    if education_type_filter:
                        curr_q = curr_q.filter(DirectionCurriculum.education_type == education_type_filter)
                    if course_filter:
                        min_sem = (course_filter - 1) * 2 + 1
                        max_sem = course_filter * 2
                        curr_q = curr_q.filter(DirectionCurriculum.semester >= min_sem, DirectionCurriculum.semester <= max_sem)
                    curr = curr_q.first()
                    if curr and curr.id not in seen_curr_ids:
                        seen_curr_ids.add(curr.id)
                        curriculum_items.append(curr)
                if curriculum_items:
                    curriculum_items = sorted(
                        curriculum_items,
                        key=lambda c: (
                            c.semester,
                            (c.subject.name or '').lower() if c.subject else '',
                            (c.direction.name or '').lower() if c.direction else ''
                        )
                    )

        subjects_data = []
        search_lower = search.lower() if search else ''
        for item in curriculum_items:
            direction = item.direction
            subject = item.subject
            if not item.enrollment_year or not item.education_type:
                continue

            group_filters = {
                'direction_id': direction.id,
                'semester': item.semester,
                'enrollment_year': item.enrollment_year,
                'education_type': item.education_type,
            }
            if group_filter:
                group_filters['id'] = group_filter
            groups = Group.query.filter_by(**group_filters).all()
            active_groups = [g for g in groups if g.get_students_count() > 0]
            if not active_groups:
                continue

            group_teachers = {}
            unique_teachers = []
            seen_teacher_ids = set()
            for group in active_groups:
                teacher_subjects = TeacherSubject.query.filter_by(
                    subject_id=subject.id,
                    group_id=group.id
                ).all()
                teachers = []
                for ts in teacher_subjects:
                    if ts.teacher_id and ts.teacher_id not in seen_teacher_ids:
                        teacher = User.query.get(ts.teacher_id)
                        if teacher:
                            teachers.append(teacher)
                            unique_teachers.append(teacher)
                            seen_teacher_ids.add(ts.teacher_id)
                if teachers:
                    group_teachers[group.id] = teachers

            if search_lower:
                matching_groups = [g for g in active_groups if search_lower in g.name.lower()]
                matching_teachers = [t for t in unique_teachers if search_lower in (t.full_name or '').lower() or search_lower in (t.login or '').lower()]
                if matching_groups or matching_teachers:
                    if matching_groups:
                        active_groups = matching_groups
                    if matching_teachers:
                        teacher_ids = {t.id for t in matching_teachers}
                        filtered_groups = []
                        for group in active_groups:
                            group_teacher_ids = {t.id for t in (group_teachers.get(group.id, []))}
                            if group_teacher_ids & teacher_ids:
                                filtered_groups.append(group)
                        if filtered_groups:
                            active_groups = filtered_groups

            subjects_data.append({
                'curriculum_item': item,
                'subject': subject,
                'direction': direction,
                'semester': item.semester,
                'course_year': ((item.semester - 1) // 2) + 1,
                'groups': active_groups,
                'group_teachers': group_teachers,
                'unique_teachers': unique_teachers,
                'enrollment_year': item.enrollment_year,
                'education_type': item.education_type,
                'curriculum_check': subject.check_curriculum_completion(
                    direction.id if direction else None,
                    None,
                    True,
                    active_groups[0] if active_groups else None
                ),
            })

        subjects_by_semester = {}
        for data in subjects_data:
            sem = data['semester']
            if sem not in subjects_by_semester:
                subjects_by_semester[sem] = []
            subjects_by_semester[sem].append(data)
        for sem in subjects_by_semester:
            subjects_by_semester[sem] = sorted(
                subjects_by_semester[sem],
                key=lambda d: (
                    (d['subject'].name or '').lower() if d.get('subject') else '',
                    (d['direction'].name or '').lower() if d.get('direction') else ''
                )
            )

        faculties = Faculty.query.order_by(Faculty.name).all()
        all_directions = Direction.query.order_by(Direction.name).all()
        if faculty_filter:
            all_directions = [d for d in all_directions if d.faculty_id == faculty_filter]

        all_groups = Group.query.filter(Group.students.any()).all()
        courses = sorted(set([g.course_year for g in all_groups if g.course_year]))
        semesters = sorted(set([g.semester for g in all_groups if g.semester]))
        education_types = sorted(set([g.education_type for g in all_groups if g.education_type and g.education_type.strip()]))

        groups = []
        if direction_filter:
            groups = Group.query.filter_by(direction_id=direction_filter).filter(Group.students.any()).order_by(Group.name).all()
        elif faculty_filter:
            direction_ids = [d.id for d in all_directions]
            if direction_ids:
                groups = Group.query.filter(Group.direction_id.in_(direction_ids)).filter(Group.students.any()).order_by(Group.name).all()
        else:
            groups = Group.query.filter(Group.students.any()).order_by(Group.name).all()

        return render_template(
            'admin/curriculum_subjects.html',
            subjects_by_semester=subjects_by_semester,
            search=search,
            faculties=faculties,
            directions=all_directions,
            courses=courses,
            semesters=semesters,
            education_types=education_types,
            groups=groups,
            current_faculty=faculty_filter,
            current_course=course_filter,
            current_semester=semester_filter,
            current_education_type=education_type_filter,
            current_direction=direction_filter,
            current_group=group_filter,
            clear_url=url_for('courses.index'),
            lock_faculty_filter=False
        )

    # Dekan uchun /subjects/ da admindagi kabi to'liq "Fanlar bazasi" ko'rinishi,
    # lekin fakultet dekanning o'z fakultetiga avtomatik fiks bo'ladi.
    if current_role == 'dean':
        faculty = Faculty.query.get(current_user.faculty_id)
        if not faculty:
            flash(t('faculty_not_assigned'), 'error')
            return redirect(url_for('main.dashboard'))

        faculty_filter = faculty.id
        course_filter = request.args.get('course', type=int)
        semester_filter = request.args.get('semester', type=int)
        education_type_filter = request.args.get('education_type', '') or None
        direction_filter = request.args.get('direction', type=int)
        group_filter = request.args.get('group', type=int)

        allowed_directions = Direction.query.filter_by(faculty_id=faculty.id).order_by(Direction.name).all()
        allowed_direction_ids = {d.id for d in allowed_directions}
        if direction_filter and direction_filter not in allowed_direction_ids:
            direction_filter = None

        if group_filter:
            selected_group = Group.query.filter_by(id=group_filter, faculty_id=faculty.id).first()
            if not selected_group:
                group_filter = None
            elif direction_filter and selected_group.direction_id != direction_filter:
                group_filter = None

        query = DirectionCurriculum.query.join(Direction).join(Subject).filter(
            Direction.faculty_id == faculty.id
        )
        if direction_filter:
            query = query.filter(DirectionCurriculum.direction_id == direction_filter)
        if semester_filter:
            query = query.filter(DirectionCurriculum.semester == semester_filter)
        if education_type_filter:
            query = query.filter(DirectionCurriculum.education_type == education_type_filter)
        if course_filter:
            min_semester = (course_filter - 1) * 2 + 1
            max_semester = course_filter * 2
            query = query.filter(DirectionCurriculum.semester >= min_semester, DirectionCurriculum.semester <= max_semester)
        if search:
            query = query.filter(
                or_(
                    Subject.name.ilike(f'%{search}%'),
                    Subject.description.ilike(f'%{search}%'),
                    cast(DirectionCurriculum.enrollment_year, String).ilike(f'%{search}%'),
                    Direction.name.ilike(f'%{search}%'),
                    Direction.code.ilike(f'%{search}%'),
                    DirectionCurriculum.education_type.ilike(f'%{search}%')
                )
            )

        curriculum_items = query.order_by(
            DirectionCurriculum.semester,
            Subject.name,
            Direction.name
        ).all()

        if search and not curriculum_items:
            matching_teachers = User.query.filter(
                or_(User.full_name.ilike(f'%{search}%'), User.login.ilike(f'%{search}%'))
            ).all()
            if matching_teachers:
                teacher_ids = [t.id for t in matching_teachers]
                ts_list = TeacherSubject.query.filter(TeacherSubject.teacher_id.in_(teacher_ids)).all()
                seen_curr_ids = set()
                for ts in ts_list:
                    gr = Group.query.get(ts.group_id) if ts.group_id else None
                    if not gr or gr.faculty_id != faculty.id or not gr.enrollment_year or not gr.education_type:
                        continue
                    curr_q = DirectionCurriculum.query.join(Direction).filter(
                        DirectionCurriculum.direction_id == gr.direction_id,
                        DirectionCurriculum.subject_id == ts.subject_id,
                        DirectionCurriculum.semester == gr.semester,
                        DirectionCurriculum.enrollment_year == gr.enrollment_year,
                        DirectionCurriculum.education_type == gr.education_type,
                        Direction.faculty_id == faculty.id
                    )
                    if direction_filter:
                        curr_q = curr_q.filter(DirectionCurriculum.direction_id == direction_filter)
                    if semester_filter:
                        curr_q = curr_q.filter(DirectionCurriculum.semester == semester_filter)
                    if education_type_filter:
                        curr_q = curr_q.filter(DirectionCurriculum.education_type == education_type_filter)
                    if course_filter:
                        min_sem = (course_filter - 1) * 2 + 1
                        max_sem = course_filter * 2
                        curr_q = curr_q.filter(DirectionCurriculum.semester >= min_sem, DirectionCurriculum.semester <= max_sem)
                    curr = curr_q.first()
                    if curr and curr.id not in seen_curr_ids:
                        seen_curr_ids.add(curr.id)
                        curriculum_items.append(curr)
                if curriculum_items:
                    curriculum_items = sorted(
                        curriculum_items,
                        key=lambda c: (
                            c.semester,
                            (c.subject.name or '').lower() if c.subject else '',
                            (c.direction.name or '').lower() if c.direction else ''
                        )
                    )

        subjects_data = []
        search_lower = search.lower() if search else ''
        for item in curriculum_items:
            direction = item.direction
            subject = item.subject
            if not item.enrollment_year or not item.education_type:
                continue

            group_filters = {
                'direction_id': direction.id,
                'semester': item.semester,
                'faculty_id': faculty.id,
                'enrollment_year': item.enrollment_year,
                'education_type': item.education_type,
            }
            if group_filter:
                group_filters['id'] = group_filter
            groups = Group.query.filter_by(**group_filters).all()
            active_groups = [g for g in groups if g.get_students_count() > 0]
            if not active_groups:
                continue

            group_teachers = {}
            unique_teachers = []
            seen_teacher_ids = set()
            for group in active_groups:
                teacher_subjects = TeacherSubject.query.filter_by(
                    subject_id=subject.id,
                    group_id=group.id
                ).all()
                teachers = []
                for ts in teacher_subjects:
                    if ts.teacher_id and ts.teacher_id not in seen_teacher_ids:
                        teacher = User.query.get(ts.teacher_id)
                        if teacher:
                            teachers.append(teacher)
                            unique_teachers.append(teacher)
                            seen_teacher_ids.add(ts.teacher_id)
                if teachers:
                    group_teachers[group.id] = teachers

            if search_lower:
                matching_groups = [g for g in active_groups if search_lower in g.name.lower()]
                matching_teachers = [t for t in unique_teachers if search_lower in (t.full_name or '').lower() or search_lower in (t.login or '').lower()]
                if matching_groups or matching_teachers:
                    if matching_groups:
                        active_groups = matching_groups
                    if matching_teachers:
                        teacher_ids = {t.id for t in matching_teachers}
                        filtered_groups = []
                        for group in active_groups:
                            group_teacher_ids = {t.id for t in (group_teachers.get(group.id, []))}
                            if group_teacher_ids & teacher_ids:
                                filtered_groups.append(group)
                        if filtered_groups:
                            active_groups = filtered_groups

            subjects_data.append({
                'curriculum_item': item,
                'subject': subject,
                'direction': direction,
                'semester': item.semester,
                'course_year': ((item.semester - 1) // 2) + 1,
                'groups': active_groups,
                'group_teachers': group_teachers,
                'unique_teachers': unique_teachers,
                'enrollment_year': item.enrollment_year,
                'education_type': item.education_type,
                'curriculum_check': subject.check_curriculum_completion(
                    direction.id if direction else None,
                    None,
                    True,
                    active_groups[0] if active_groups else None
                ),
            })

        subjects_by_semester = {}
        for data in subjects_data:
            sem = data['semester']
            if sem not in subjects_by_semester:
                subjects_by_semester[sem] = []
            subjects_by_semester[sem].append(data)
        for sem in subjects_by_semester:
            subjects_by_semester[sem] = sorted(
                subjects_by_semester[sem],
                key=lambda d: (
                    (d['subject'].name or '').lower() if d.get('subject') else '',
                    (d['direction'].name or '').lower() if d.get('direction') else ''
                )
            )

        all_groups = Group.query.filter(
            Group.faculty_id == faculty.id,
            Group.students.any()
        ).all()
        courses = sorted(set([g.course_year for g in all_groups if g.course_year]))
        semesters = sorted(set([g.semester for g in all_groups if g.semester]))
        education_types = sorted(set([g.education_type for g in all_groups if g.education_type and g.education_type.strip()]))

        if direction_filter:
            groups = Group.query.filter_by(
                direction_id=direction_filter,
                faculty_id=faculty.id
            ).filter(Group.students.any()).order_by(Group.name).all()
        else:
            groups = Group.query.filter_by(
                faculty_id=faculty.id
            ).filter(Group.students.any()).order_by(Group.name).all()

        return render_template(
            'admin/curriculum_subjects.html',
            subjects_by_semester=subjects_by_semester,
            search=search,
            faculties=[faculty],
            directions=allowed_directions,
            courses=courses,
            semesters=semesters,
            education_types=education_types,
            groups=groups,
            current_faculty=faculty_filter,
            current_course=course_filter,
            current_semester=semester_filter,
            current_education_type=education_type_filter,
            current_direction=direction_filter,
            current_group=group_filter,
            clear_url=url_for('courses.index'),
            lock_faculty_filter=True
        )

    if current_role == 'student':
        # Talaba faqat o'z guruhiga biriktirilgan va joriy semestrdagi fanlarni ko'radi
        if current_user.group_id:
            group = Group.query.get(current_user.group_id)
            if group and group.direction_id:
                current_semester = group.semester if group.semester else 1
                # Joriy semestrdagi fanlarni olish (yo'nalish + semestr; yil/ta'lim shakli mos kelganda)
                curriculum_query = DirectionCurriculum.query.filter_by(
                    direction_id=group.direction_id,
                    semester=current_semester
                )
                curriculum_query = DirectionCurriculum.filter_by_group_context(curriculum_query, group)
                curriculum_items = curriculum_query.all()
                subject_ids = [item.subject_id for item in curriculum_items]
                query = Subject.query.filter(Subject.id.in_(subject_ids)) if subject_ids else Subject.query.filter(False)
            else:
                query = Subject.query.filter(False)  # Bo'sh
        else:
            query = Subject.query.filter(False)  # Bo'sh
    elif current_role == 'teacher':
        # O'qituvchi faqat joriy semestrdagi fanlarni ko'radi
        teacher_subjects = TeacherSubject.query.filter_by(teacher_id=current_user.id).all()
        valid_subject_ids = set()
        
        for ts in teacher_subjects:
            group = Group.query.get(ts.group_id)
            if group and group.direction_id and group.get_students_count() > 0:
                current_semester = group.semester if group.semester else 1
                # Tekshirish: bu fan bu guruhda shu semestrda bormi? (yo'nalish, yil, ta'lim shakli)
                curr_query = DirectionCurriculum.query.filter_by(
                    direction_id=group.direction_id,
                    subject_id=ts.subject_id,
                    semester=current_semester
                )
                curr_item = DirectionCurriculum.filter_by_group_context(curr_query, group).first()
                if curr_item:
                    valid_subject_ids.add(ts.subject_id)
        
        query = Subject.query.filter(Subject.id.in_(list(valid_subject_ids))) if valid_subject_ids else Subject.query.filter(False)
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
        current_semester = current_user.semester
        group = Group.query.get(current_user.group_id)
        if group and group.direction:
            current_semester = group.semester
        
        if group and group.direction_id:
            # DirectionCurriculum orqali faqat joriy semestrdagi fanlarni olish (yo'nalish, yil, ta'lim shakli bo'yicha)
            curriculum_query = DirectionCurriculum.query.filter_by(
                direction_id=group.direction_id,
                semester=current_semester
            ).join(Subject).order_by(Subject.name)
            curriculum_query = DirectionCurriculum.filter_by_group_context(curriculum_query, group)
            curriculum_items = curriculum_query.all()
            
            for item in curriculum_items:
                semester = item.semester
                if semester not in subjects_by_semester:
                    subjects_by_semester[semester] = []
                # Takrorlanuvchi fanlarni tekshirish
                existing_subjects = [s['subject'].id for s in subjects_by_semester[semester]]
                if item.subject.id not in existing_subjects:
                    if search and search.strip() and search.lower() not in item.subject.name.lower():
                        continue
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
                    
                    # Bu fanga biriktirilgan o'qituvchilarni olish – faqat o'quv rejada soatlari bo'lgan dars turlaridagilarni
                    teacher_subjects = TeacherSubject.query.filter_by(
                        subject_id=item.subject.id,
                        group_id=current_user.group_id
                    ).all()
                    active_types = _get_active_lesson_types_for_subject_group(item.subject.id, group)
                    teachers_list = []
                    seen_teachers = set()
                    for ts in teacher_subjects:
                        if not ts.teacher_id or ts.teacher_id in seen_teachers:
                            continue
                        lt = _normalize_lesson_type_to_canonical(ts.lesson_type)
                        if not lt or lt not in active_types:
                            continue  # O'quv rejada bu dars turi yo'q yoki soatlari o'chirilgan – ko'rsatmaslik
                        teacher = User.query.get(ts.teacher_id)
                        if teacher:
                            teachers_list.append(teacher)
                            seen_teachers.add(ts.teacher_id)
                    
                    # Direction ma'lumotini olish
                    direction = Direction.query.get(group.direction_id) if group.direction_id else None
                    
                    subjects_by_semester[semester].append({
                        'subject': item.subject,
                        'semester': semester,
                        'course_year': course_year,
                        'credits': credits,
                        'lessons_count': lessons_count,
                        'assignments_count': assignments_count,
                        'teachers': teachers_list,
                        'direction': direction,
                        'group_id': current_user.group_id  # Talaba uchun bitta guruh
                    })
                    if item.subject not in all_subjects_list:
                        all_subjects_list.append(item.subject)
        else:
            # Agar yo'nalish bo'lmasa, oddiy tartibda
            subjects = query.order_by(Subject.name).paginate(page=page, per_page=12)
            all_subjects_list = list(subjects.items)
    elif current_role == 'teacher':
        # O'qituvchi uchun - yo'nalish bo'yicha guruhlash
        # Har bir yo'nalish uchun alohida fan card ko'rsatiladi
        teacher_subjects = TeacherSubject.query.filter_by(teacher_id=current_user.id).all()
        
        # Har bir fan+yo'nalish kombinatsiyasi uchun ma'lumotlar
        # {semester: [{subject, direction, groups, credits, semester}, ...]}
        subject_direction_data = {}  # {(subject_id, direction_id): {'subject': ..., 'direction': ..., 'groups': [...], 'semester': ..., 'credits': ...}}
        
        for ts in teacher_subjects:
            group = Group.query.get(ts.group_id)
            if group and group.direction_id:
                # Guruh ma'lumotlarini olish
                
                direction = Direction.query.get(group.direction_id)
                if not direction:
                    continue
                
                # Check current semester of the group
                current_semester = group.semester if group.semester else 1
                
                # Bu guruh uchun bu fanga tegishli o'quv reja ma'lumotlarini olish (joriy semestrda, yil, ta'lim shakli)
                curr_q = DirectionCurriculum.query.filter_by(
                    direction_id=group.direction_id,
                    subject_id=ts.subject_id,
                    semester=current_semester
                )
                curriculum_item = DirectionCurriculum.filter_by_group_context(curr_q, group).first()
                
                if curriculum_item:
                    semester = curriculum_item.semester
                    key = (ts.subject_id, group.direction_id)
                    
                    if key not in subject_direction_data:
                        subject = Subject.query.get(ts.subject_id)
                        if not subject:
                            continue
                        if search and search.strip() and search.lower() not in subject.name.lower():
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
                            'group_id': None,  # Birinchi guruh bilan to'ldiriladi
                            'semester': semester,
                            'credits': credits,
                            'lessons_count': lessons_count,
                            'assignments_count': assignments_count
                        }
                    
                    # Guruhni qo'shish (takrorlanmasligi uchun)
                    if group not in subject_direction_data[key]['groups']:
                        subject_direction_data[key]['groups'].append(group)
                        if subject_direction_data[key]['group_id'] is None:
                            subject_direction_data[key]['group_id'] = group.id
        
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
    elif current_role in ['admin', 'dean', 'edu_dept']:
        # Admin va dekan uchun - barcha fanlarni yo'nalish bo'yicha guruhlash
        # Admin uchun kurs filterini qo'llash (agar tanlangan bo'lsa)
        # Hozircha barcha guruhlar
        
        # Har bir fan+yo'nalish kombinatsiyasi uchun ma'lumotlar
        subject_direction_data = {}
        
        # Barcha faol guruhlarni olish (admin uchun) — alifbo bo'yicha tartiblangan
        if current_user.role == 'dean':
            all_groups = Group.query.filter_by(faculty_id=current_user.faculty_id).all()
        else:
            all_groups = Group.query.all()
        admin_groups = sorted(
            [g for g in all_groups if g.get_students_count() > 0],
            key=lambda g: (g.name or '').upper()
        )
            
        for group in admin_groups:
            if group and group.direction_id:
                # Guruh ma'lumotlarini olish
                
                direction = Direction.query.get(group.direction_id)
                if not direction:
                    continue
                
                # Check current semester of the group
                current_semester = group.semester if group.semester else 1
                
                # Bu guruh uchun barcha fanlarni olish (guruh kontekstiga mos)
                curr_q = DirectionCurriculum.query.filter_by(
                    direction_id=group.direction_id,
                    semester=current_semester
                )
                curriculum_items = DirectionCurriculum.filter_by_group_context(curr_q, group).all()
                
                for curriculum_item in curriculum_items:
                    semester = curriculum_item.semester
                    # Guruh kontekstini kalitga qo'shish – turli yillar/ta'lim shaklidagi guruhlar aralashmasin
                    key = (curriculum_item.subject_id, group.direction_id, group.enrollment_year, (group.education_type or '').strip() or None)
                    
                    if key not in subject_direction_data:
                        subject = Subject.query.get(curriculum_item.subject_id)
                        if not subject:
                            continue
                        
                        # Search query filter
                        if search and search.lower() not in subject.name.lower():
                            continue
                            
                        # Kreditni yo'nalish o'quv rejasidagi soatlar bo'yicha hisoblash
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
                        
                        # O'qituvchilar post-processing da filtr bilan qo'shiladi (o'quv rejaga mos)
                        # curriculum_item saqlanadi – post-processing da xuddi shu o'quv rejadan foydalaniladi
                        subject_direction_data[key] = {
                            'subject': subject,
                            'direction': direction,
                            'groups': [],
                            'group_id': group.id,
                            'semester': semester,
                            'credits': credits,
                            'lessons_count': lessons_count,
                            'assignments_count': assignments_count,
                            'teachers': [],
                            '_curriculum_item': curriculum_item
                        }
                    
                    # Guruhni qo'shish
                    # Guruh allaqachon qo'shilmaganligini tekshirish (id bo'yicha)
                    existing_group_ids = [g.id for g in subject_direction_data[key]['groups']]
                    if group.id not in existing_group_ids:
                        subject_direction_data[key]['groups'].append(group)
                        # O'qituvchilarni faqat asosiy guruh (group_id) uchun saqlash – boshqa guruhlardan qo'shilmasin

        # Semestr bo'yicha guruhlash
        for key, data in subject_direction_data.items():
            # Fan kartasida faqat asosiy guruh (group_id) uchun biriktirilgan o'qituvchilarni ko'rsatish
            # va faqat o'quv rejada soatlari bo'lgan dars turlariga biriktirilganlarni (o'chirilgan turlar ko'rinmasin)
            primary_group_id = data.get('group_id')
            curr_item = data.pop('_curriculum_item', None)  # O'quv reja (loop da saqlangan)
            if primary_group_id:
                # Active types: saqlangan curriculum_item dan yoki qayta so'rovdan
                if curr_item:
                    active_types = set()
                    if (curr_item.hours_maruza or 0) > 0:
                        active_types.add('maruza')
                    if (curr_item.hours_amaliyot or 0) > 0:
                        active_types.add('amaliyot')
                    if (curr_item.hours_laboratoriya or 0) > 0:
                        active_types.add('laboratoriya')
                    if (curr_item.hours_seminar or 0) > 0:
                        active_types.add('seminar')
                    if (curr_item.hours_kurs_ishi or 0) > 0:
                        active_types.add('kurs_ishi')
                else:
                    primary_group = Group.query.get(primary_group_id)
                    active_types = _get_active_lesson_types_for_subject_group(data['subject'].id, primary_group)
                ts_list = TeacherSubject.query.filter_by(
                    subject_id=data['subject'].id,
                    group_id=primary_group_id
                ).all()
                teachers_filtered = []
                seen_ids = set()
                for ts in ts_list:
                    if not ts.teacher:
                        continue
                    lt = _normalize_lesson_type_to_canonical(ts.lesson_type)
                    if not lt or lt not in active_types:
                        continue  # O'quv rejada bu dars turi yo'q yoki soatlari o'chirilgan – ko'rsatmaslik
                    if ts.teacher.id not in seen_ids:
                        teachers_filtered.append(ts.teacher)
                        seen_ids.add(ts.teacher.id)
                data['teachers'] = teachers_filtered
            else:
                data['teachers'] = []
            semester = data['semester']
            if semester not in subjects_by_semester:
                subjects_by_semester[semester] = []
            
            subjects_by_semester[semester].append(data)
            if data['subject'] not in all_subjects_list:
                all_subjects_list.append(data['subject'])
        
        # Har bir semestr uchun tartiblash
        for semester in subjects_by_semester:
            subjects_by_semester[semester].sort(key=lambda x: (
                x['subject'].name,
                sorted([g.name for g in x['groups']])[0] if x['groups'] else ''
            ))
            
        # Pagination logikasini saqlash (subjects_by_semester borligi sababli pastdagi blok ishlaydi)
    
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
            current_semester_for_lesson_types = group.semester if group.semester else 1
            for subject in subjects_for_processing:
                curriculum_item = DirectionCurriculum.query.filter_by(
                    direction_id=group.direction_id,
                    subject_id=subject.id,
                    semester=current_semester_for_lesson_types
                ).filter(
                    or_(DirectionCurriculum.enrollment_year.is_(None), DirectionCurriculum.enrollment_year == group.enrollment_year),
                    or_(DirectionCurriculum.education_type.is_(None), DirectionCurriculum.education_type == group.education_type)
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
                # Talaba uchun topshiriq bo'yicha eng yuqori ball (topshirmasa 0)
                all_subs = Submission.query.filter_by(
                    student_id=current_user.id,
                    assignment_id=assignment.id
                ).all()
                scores = [s.score for s in all_subs if s.score is not None]
                best_score = max(scores) if scores else 0
                
                # Barcha topshiriqlar (topshirgan ham, topshirmagan ham) hisobga olinadi
                lesson_type = assignment.lesson_type
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
                        lesson_type = 'maruza'
                
                # Har bir topshiriq uchun max ga qo'shamiz; ballga best_score (yoki 0)
                if lesson_type in ['laboratoriya', 'kurs_ishi']:
                    if lesson_type in grades_by_type:
                        grades_by_type[lesson_type]['score'] += best_score
                        grades_by_type[lesson_type]['max'] += (assignment.max_score or 0)
                    elif not assignment.lesson_type:
                        assignment_creator = User.query.get(assignment.created_by) if assignment.created_by else None
                        if assignment_creator:
                            amaliyot_teacher = TeacherSubject.query.filter_by(
                                subject_id=subject.id,
                                group_id=current_user.group_id,
                                teacher_id=assignment_creator.id,
                                lesson_type='amaliyot'
                            ).first()
                            if amaliyot_teacher and 'amaliyot' in grades_by_type:
                                grades_by_type['amaliyot']['score'] += best_score
                                grades_by_type['amaliyot']['max'] += (assignment.max_score or 0)
                            elif lesson_type in grades_by_type:
                                grades_by_type[lesson_type]['score'] += best_score
                                grades_by_type[lesson_type]['max'] += (assignment.max_score or 0)
                else:
                    if lesson_type in grades_by_type:
                        grades_by_type[lesson_type]['score'] += best_score
                        grades_by_type[lesson_type]['max'] += (assignment.max_score or 0)
            
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


@bp.route('/<int:id>/<int:dir_id>/<int:group_id>/<int:semester>', methods=['GET', 'POST'])
@bp.route('/<int:id>/<int:dir_id>/<int:group_id>', methods=['GET', 'POST'], defaults={'semester': None})
@bp.route('/<int:id>/<int:dir_id>', methods=['GET', 'POST'], defaults={'group_id': None, 'semester': None})
@bp.route('/<int:id>', methods=['GET', 'POST'], defaults={'dir_id': None, 'group_id': None, 'semester': None})
@login_required
def detail(id, dir_id=None, group_id=None, semester=None):
    """Fan tafsilotlari (URL: /subjects/21/1/5 yoki /subjects/21/1/5/2 - semestr path da)"""
    subject = Subject.query.get_or_404(id)
    
    # Tanlangan rol
    current_role = session.get('current_role', current_user.role)
    is_admin_or_dean_mode = (
        current_role in ['admin', 'dean', 'edu_dept'] and
        (current_user.has_role(current_role) or getattr(current_user, 'is_superadmin', False))
    )
    
    # Yo'nalish ID - path dan (/subjects/21/1/5) yoki query dan (?direction_id=1) yoki talaba guruhidan
    direction_id_raw = request.args.get('direction_id')
    direction_id = dir_id  # Path dan: /subjects/21/1/5
    requested_semester = semester or request.args.get('semester', type=int)
    requested_group_name = None
    requested_type_code = None
    requested_lesson_type = None

    # Dars turi kodlarini xaritasi (kengaytirilgan)
    type_code_map = {
        'm': 'maruza',
        'a': 'amaliyot',
        'p': 'amaliyot',  # P - Practical
        's': 'seminar',
        'l': 'laboratoriya',
        'k': 'kurs_ishi'
    }

    if direction_id is None and direction_id_raw:
        if '/' in str(direction_id_raw):
            try:
                parts = str(direction_id_raw).split('/')
                direction_id = int(parts[0])
                if len(parts) > 1 and parts[1]:
                    requested_semester = int(parts[1])
                if len(parts) > 2 and parts[2]:
                    requested_group_name = parts[2]
                if len(parts) > 3 and parts[3]:
                    requested_type_code = parts[3].lower()
                    requested_lesson_type = type_code_map.get(requested_type_code)
            except (ValueError, IndexError):
                pass
        else:
            try:
                direction_id = int(direction_id_raw)
            except ValueError:
                pass

    # dir_id va group_id bor lekin semester yo'q bo'lsa - /subjects/17/5/12/{semester} formatiga yo'naltirish
    if direction_id and group_id and semester is None:
        gr = Group.query.get(group_id)
        inferred_sem = (gr.semester if gr and gr.semester else 1)
        return redirect(url_for('courses.detail', id=id, dir_id=direction_id, group_id=group_id, semester=inferred_sem))

    # group_id berilgan bo'lsa, yo'nalishga tegishliligi va ruxsatni tekshirish
    if direction_id and group_id:
        gr = Group.query.get(group_id)
        if not gr or gr.direction_id != direction_id:
            flash(t('invalid_request'), 'error')
            group_id = None  # Keyin redirect qiladi
        elif current_role == 'teacher' and current_user.role == 'teacher':
            ts_check = TeacherSubject.query.filter_by(teacher_id=current_user.id, subject_id=subject.id, group_id=group_id).first()
            if not ts_check:
                ts_check = TeacherSubject.query.filter(
                    TeacherSubject.teacher_id == current_user.id,
                    TeacherSubject.subject_id == subject.id,
                    TeacherSubject.group_id.in_([g.id for g in Group.query.filter_by(direction_id=direction_id).all()])
                ).first()
                if ts_check and ts_check.group_id != group_id:
                    gr = Group.query.get(ts_check.group_id)
                    sem = requested_semester or (gr.semester if gr and gr.semester else 1)
                    return redirect(url_for('courses.detail', id=id, dir_id=direction_id, group_id=ts_check.group_id, semester=sem))
                elif not ts_check:
                    group_id = None
    
    # direction_id bor lekin group_id yo'q bo'lsa - mos guruhni aniqlab redirect
    if direction_id and group_id is None:
        target_group_id = None
        if current_role == 'student' and current_user.group_id:
            gr = Group.query.get(current_user.group_id)
            if gr and gr.direction_id == direction_id:
                target_group_id = current_user.group_id
        elif current_role == 'teacher':
            ts_list = TeacherSubject.query.filter_by(teacher_id=current_user.id, subject_id=subject.id).all()
            for ts in ts_list:
                if ts.group_id:
                    g = Group.query.get(ts.group_id)
                    if g and g.direction_id == direction_id:
                        target_group_id = ts.group_id
                        break
        if not target_group_id:
            direction_groups = Group.query.filter_by(direction_id=direction_id).all()
            active_groups = sorted(
                [g for g in direction_groups if g.get_students_count() > 0],
                key=lambda g: (g.name or '').upper()
            )
            first_gr = active_groups[0] if active_groups else None
            if first_gr:
                target_group_id = first_gr.id
        if target_group_id:
            gr = Group.query.get(target_group_id)
            sem = requested_semester or (gr.semester if gr and gr.semester else 1)
            return redirect(url_for('courses.detail', id=id, dir_id=direction_id, group_id=target_group_id, semester=sem))

    # POST so'rovini qayta ishlash (o'qituvchi biriktirish)
    is_authorized = current_user.role in ['admin', 'dean', 'edu_dept'] or \
                    any(r in ['admin', 'dean', 'edu_dept'] for r in current_user.get_roles())

    if request.method == 'POST' and is_authorized:
        assign_teacher_id = request.form.get('assign_teacher_id', type=int)
        assign_group_id = request.form.get('assign_group_id', type=int)
        assign_lesson_type = request.form.get('assign_lesson_type')
        
        # O'quv yilini aniqlash (default: 2024-2025)
        # Kelajakda buni sozlamalardan olish mumkin
        academic_year = '2024-2025'
        
        print(f"DEBUG: Teacher Assignment POST - teacher:{assign_teacher_id}, group:{assign_group_id}, type:{assign_lesson_type}, sem:{requested_semester}")
        
        if assign_teacher_id and assign_group_id and assign_lesson_type:
            try:
                # Mavjud biriktirishni tekshirish (o'quv yili bilan birga)
                ts = TeacherSubject.query.filter_by(
                    subject_id=subject.id,
                    group_id=assign_group_id,
                    lesson_type=assign_lesson_type,
                    academic_year=academic_year
                ).first()
                
                # Agar o'quv yili bilan topilmasa, unsiz qidirib ko'rish (migration uchun)
                if not ts:
                    ts = TeacherSubject.query.filter_by(
                        subject_id=subject.id,
                        group_id=assign_group_id,
                        lesson_type=assign_lesson_type
                    ).first()
                
                if ts:
                    print(f"DEBUG: Updating existing assignment ID:{ts.id}")
                    ts.teacher_id = assign_teacher_id
                    ts.academic_year = academic_year
                    if requested_semester:
                        ts.semester = requested_semester
                    ts.assigned_at = datetime.utcnow()
                    ts.assigned_by = current_user.id
                else:
                    print("DEBUG: Creating new assignment")
                    ts = TeacherSubject(
                        subject_id=subject.id,
                        group_id=assign_group_id,
                        lesson_type=assign_lesson_type,
                        teacher_id=assign_teacher_id,
                        academic_year=academic_year,
                        semester=requested_semester if requested_semester else 1,
                        assigned_by=current_user.id
                    )
                    db.session.add(ts)
                
                db.session.commit()
                print("DEBUG: Assignment committed successfully")
                flash(t('no_permission_for_operation'), 'success')  # Note: Teacher assignment success - may need new translation key
            except Exception as e:
                db.session.rollback()
                print(f"DEBUG: Assignment error: {str(e)}")
                flash(t('error_occurred', error=str(e)), 'error')
            
            return redirect(request.url)
        else:
            print("DEBUG: Missing data in POST form")
    
    # Barcha rollar uchun direction va groups ma'lumotlarini olish
    direction = None
    direction_groups = []
    direction_semester = requested_semester
    direction_course = None
    direction_credits = None
    
    # O'qituvchi, Admin yoki Dekan uchun (direction_id bo'lsa)
    if (current_role in ['teacher', 'admin', 'dean', 'edu_dept']) and direction_id:
        direction = Direction.query.get(direction_id)
        if direction:
            # O'qituvchiga biriktirilgan guruhlar
            teacher_groups_query = TeacherSubject.query.filter_by(
                teacher_id=current_user.id,
                subject_id=subject.id
            )
            # Faqat ushbu yo'nalishdagi guruhlar (boshqa yo'nalishlar kirmasin)
            direction_group_ids = [g.id for g in Group.query.filter_by(direction_id=direction_id).all()]
            teacher_groups = teacher_groups_query.filter(TeacherSubject.group_id.in_(direction_group_ids)).all()
            # Guruhlarni unique qilish (takrorlanmasligi uchun) - avval id bo'yicha, keyin name bo'yicha
            seen_group_ids = set()
            seen_group_names = set()
            direction_groups = []
            for tg in teacher_groups:
                if tg.group and tg.group.id not in seen_group_ids and tg.group.name not in seen_group_names:
                    direction_groups.append(tg.group)
                    seen_group_ids.add(tg.group.id)
                    seen_group_names.add(tg.group.name)
            
            # Semestr va kredit ma'lumotlarini olish (guruh kontekstiga mos)
            context_group = None
            if group_id and direction_groups:
                context_group = next((g for g in direction_groups if g.id == group_id), direction_groups[0] if direction_groups else None)
            elif direction_groups:
                context_group = direction_groups[0]
            curriculum_query = DirectionCurriculum.query.filter_by(
                direction_id=direction_id,
                subject_id=subject.id
            )
            if context_group:
                curriculum_query = DirectionCurriculum.filter_by_group_context(curriculum_query, context_group)
            sem = requested_semester or (context_group.semester if context_group and context_group.semester else None)
            if sem:
                curriculum_query = curriculum_query.filter_by(semester=sem)
            
            curriculum_item = curriculum_query.first()
            if curriculum_item:
                direction_semester = curriculum_item.semester
                # Kreditni hisoblash (jami soat / 30) - yaxlitlamasdan
                total_hours = (curriculum_item.hours_maruza or 0) + (curriculum_item.hours_amaliyot or 0) + \
                             (curriculum_item.hours_laboratoriya or 0) + (curriculum_item.hours_seminar or 0) + \
                             (curriculum_item.hours_mustaqil or 0)
                direction_credits = total_hours / 30 if total_hours > 0 else 0
    # Talaba uchun - ularning guruhidan direction olish
    elif current_role == 'student' and current_user.group_id:
        group = Group.query.get(current_user.group_id)
        if group and group.direction_id:
            if direction_id is None:
                direction_id = group.direction_id  # Talaba uchun guruh yo'nalishidan
            direction = Direction.query.get(group.direction_id)
            if direction:
                # Talabaning guruhini ko'rsatish
                direction_groups = [group] if group else []
                
                # Semestr va kredit ma'lumotlarini olish (guruh kontekstiga mos)
                curriculum_query = DirectionCurriculum.query.filter_by(
                    direction_id=group.direction_id,
                    subject_id=subject.id
                )
                curriculum_query = DirectionCurriculum.filter_by_group_context(curriculum_query, group)
                if group.semester:
                    curriculum_query = curriculum_query.filter_by(semester=group.semester)
                
                curriculum_item = curriculum_query.first()
                if curriculum_item:
                    direction_semester = curriculum_item.semester
                    # Kreditni hisoblash (jami soat / 30) - yaxlitlamasdan
                    total_hours = (curriculum_item.hours_maruza or 0) + (curriculum_item.hours_amaliyot or 0) + \
                                 (curriculum_item.hours_laboratoriya or 0) + (curriculum_item.hours_seminar or 0) + \
                                 (curriculum_item.hours_mustaqil or 0)
                    direction_credits = total_hours / 30 if total_hours > 0 else 0
    
    # Guruhlarni to'ldirish (agar hali to'lmagan bo'lsa - admin yoki teacher uchun)
    if not direction_groups:
        if current_role in ['admin', 'dean', 'edu_dept']:
            # Admin yoki dekan uchun: faqat direction_id bo'lsa shu yo'nalish, aks holda fanga bog'langan barcha
            base_query_cur = Group.query.join(DirectionCurriculum, Group.direction_id == DirectionCurriculum.direction_id)\
                                        .filter(DirectionCurriculum.subject_id == subject.id)
            base_query_ts = Group.query.join(TeacherSubject, Group.id == TeacherSubject.group_id)\
                                      .filter(TeacherSubject.subject_id == subject.id)
            if direction_id:
                base_query_cur = base_query_cur.filter(Group.direction_id == direction_id)
                base_query_ts = base_query_ts.filter(Group.direction_id == direction_id)
            curriculum_groups = base_query_cur.all()
            ts_groups = base_query_ts.all()
            unique_groups = {g.id: g for g in curriculum_groups + ts_groups}.values()
            direction_groups = [g for g in list(unique_groups) if g.get_students_count() > 0]
        elif current_role == 'teacher':
            # O'qituvchi uchun: faqat ushbu yo'nalishdagi guruhlar (direction_id bo'lsa)
            teacher_subjects = TeacherSubject.query.filter_by(teacher_id=current_user.id, subject_id=subject.id).all()
            seen_ids = set()
            for ts in teacher_subjects:
                if ts.group and ts.group.id not in seen_ids and ts.group.get_students_count() > 0:
                    if not direction_id or ts.group.direction_id == direction_id:
                        direction_groups.append(ts.group)
                        seen_ids.add(ts.group.id)
    
    # Faqat ushbu yo'nalishning ushbu semestridagi guruhlarni ko'rsatish
    if direction_id:
        direction_groups = [g for g in direction_groups if g.direction_id == direction_id]
    filter_semester = requested_semester or direction_semester
    if not filter_semester and group_id:
        gr = Group.query.get(group_id)
        if gr and gr.semester:
            filter_semester = gr.semester
    if direction_groups and filter_semester is not None:
        direction_groups = [g for g in direction_groups if g.semester == filter_semester]
    
    # Tanlangan rol
    current_role = session.get('current_role', current_user.role)
    
    # Tekshirish: foydalanuvchi bu fanni ko'rishi mumkinmi
    can_view = False
    is_teacher = False
    my_group = None
    
    if current_role in ['admin', 'dean', 'edu_dept']:
        can_view = True
    elif current_role == 'teacher':
        # O'qituvchi faqat joriy semestrdagi fanlarni ko'rishi mumkin
        teacher_assignments = TeacherSubject.query.filter_by(
            teacher_id=current_user.id,
            subject_id=subject.id
        ).all()
        
        # Har bir biriktirilgan guruhni tekshirish
        for ta in teacher_assignments:
            group = Group.query.get(ta.group_id)
            if group and group.direction_id and group.get_students_count() > 0:
                current_semester = group.semester if group.semester else 1
                # Tekshirish: bu fan bu guruhda shu semestrda bormi? (yil, ta'lim shakli)
                curr_item = DirectionCurriculum.query.filter_by(
                    direction_id=group.direction_id,
                    subject_id=subject.id,
                    semester=current_semester
                ).filter(
                    or_(DirectionCurriculum.enrollment_year.is_(None), DirectionCurriculum.enrollment_year == group.enrollment_year),
                    or_(DirectionCurriculum.education_type.is_(None), DirectionCurriculum.education_type == group.education_type)
                ).first()
                if curr_item:
                    can_view = True
                    break
    elif current_user.role == 'student' and current_user.group_id:
        # Talaba faqat joriy semestrdagi fanlarni ko'rishi mumkin (o'z yo'nalishi, yili, ta'lim shakli)
        group = Group.query.get(current_user.group_id)
        if group and group.direction_id:
            current_semester = group.semester if group.semester else 1
            curr_item = DirectionCurriculum.query.filter_by(
                direction_id=group.direction_id,
                subject_id=subject.id,
                semester=current_semester
            ).filter(
                or_(DirectionCurriculum.enrollment_year.is_(None), DirectionCurriculum.enrollment_year == group.enrollment_year),
                or_(DirectionCurriculum.education_type.is_(None), DirectionCurriculum.education_type == group.education_type)
            ).first()
            can_view = curr_item is not None
        my_group = current_user.group
    
    if not can_view:
        flash(t('no_permission_to_view_course'), 'error')
        return redirect(url_for('courses.index'))

    # O'qituvchi /subjects/<id> ga kirganda yo'nalish/guruh tanlanmagan bo'ladi – dars va topshiriqlar ko'rinmaydi. Birinchi biriktirilgan guruhga yo'naltirish (TeacherSubject orqali).
    if current_role == 'teacher' and direction_id is None:
        first_ts = TeacherSubject.query.filter_by(
            teacher_id=current_user.id,
            subject_id=subject.id
        ).filter(TeacherSubject.group_id.isnot(None)).first()
        if first_ts and first_ts.group_id:
            first_gr = Group.query.get(first_ts.group_id)
            if first_gr and first_gr.direction_id:
                sem = requested_semester or (first_gr.semester if first_gr.semester else 1)
                return redirect(url_for('courses.detail', id=id, dir_id=first_gr.direction_id, group_id=first_gr.id, semester=sem))

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
    if (current_user.role in ['admin', 'dean', 'edu_dept']) and current_role != 'teacher':
        can_manage_subject = True
    elif is_teacher:
        can_manage_subject = True
    
    # Darslarni group_id va direction_id bo'yicha filtrlash
    # Admin uchun har doim barcha darslar (current_role ga qaramay)
    if (current_user.role in ['admin', 'dean', 'edu_dept']) and current_role != 'teacher':
        # Admin va dekan uchun barcha darslar
        if direction_id:
            # Agar yo'nalish tanlangan bo'lsa, shu yo'nalishdagi va umumiy darslar
            lessons_query = subject.lessons.filter(
                (Lesson.direction_id == direction_id) | (Lesson.direction_id.is_(None))
            )
            if requested_semester:
                # Lesson da semester yo'q, shuning uchun Group orqali join qilamiz
                lessons_query = lessons_query.outerjoin(Group, Lesson.group_id == Group.id).filter(
                    (Group.semester == requested_semester) | (Lesson.group_id.is_(None))
                )
            all_lessons = lessons_query.order_by(Lesson.order).all()
        else:
            all_lessons = subject.lessons.order_by(Lesson.order).all()
    elif current_role == 'student' and current_user.group_id:
        # Talaba uchun o'z guruhiga va yo'nalish darajasidagi (group_id=None) darslarni ko'rsatish
        group = Group.query.get(current_user.group_id)
        
        # Valid teachers: guruh uchun VA yo'nalishdagi barcha guruhlar uchun (direction-level darslar uchun)
        valid_teachers = TeacherSubject.query.filter_by(
            group_id=current_user.group_id,
            subject_id=subject.id
        ).all()
        valid_teacher_ids = [t.teacher_id for t in valid_teachers]
        if group and group.direction_id:
            direction_teachers = TeacherSubject.query.join(Group).filter(
                TeacherSubject.subject_id == subject.id,
                Group.direction_id == group.direction_id
            ).all()
            valid_teacher_ids = list(set(valid_teacher_ids + [t.teacher_id for t in direction_teachers]))

        # Helper: faqat ushbu guruhga/yo'nalishga biriktirilgan o'qituvchining darslari
        def is_visible_to_student(item):
            if item.created_by in valid_teacher_ids:
                return True
            if item.creator and item.creator.role in ['admin', 'dean', 'edu_dept']:
                return True
            if not item.created_by:
                return True
            return False

        # Talaba o'z guruhiga biriktirilgan VA yo'nalish darajasidagi (group_id=None) darslarni ko'radi
        if group and group.direction_id:
            all_lessons_query = subject.lessons.filter(
                (Lesson.group_id == current_user.group_id) | (Lesson.group_id.is_(None)),
                (Lesson.direction_id == group.direction_id) | (Lesson.direction_id.is_(None))
            ).order_by(Lesson.order).all()
        else:
            all_lessons_query = subject.lessons.filter(
                (Lesson.group_id == current_user.group_id) | (Lesson.group_id.is_(None))
            ).order_by(Lesson.order).all()
        
        # Faqat ushbu guruhga/yo'nalishga biriktirilgan o'qituvchining darslari
        all_lessons = [l for l in all_lessons_query if is_visible_to_student(l)]

    elif current_role == 'teacher':
        # O'qituvchi uchun - group_id bo'lsa faqat shu guruh darslari
        teacher_groups = TeacherSubject.query.filter_by(
            teacher_id=current_user.id,
            subject_id=subject.id
        ).all()
        group_ids = [tg.group_id for tg in teacher_groups if tg.group_id]
        
        if direction_id:
            # Shu yo'nalishdagi darslar va o'qituvchiga biriktirilgan barcha guruhlar (tanlangan bitta guruh emas)
            # – bitta guruhda ko'rilsa ham boshqa guruh uchun kiritilgan darslar chiqadi
            lessons_query = subject.lessons.filter(
                (Lesson.direction_id == direction_id) | (Lesson.direction_id.is_(None)),
                (Lesson.group_id.in_(group_ids)) | (Lesson.group_id.is_(None)) if group_ids else Lesson.group_id.is_(None)
            )
            if requested_semester:
                lessons_query = lessons_query.outerjoin(Group, Lesson.group_id == Group.id).filter(
                    (Group.semester == requested_semester) | (Lesson.group_id.is_(None))
                )
            all_lessons = lessons_query.order_by(Lesson.order).all()
        else:
            # direction_id berilmagan bo'lsa: o'ziga biriktirilgan guruhlar va shu yo'nalishlardagi barcha dars turlari
            if group_ids:
                teacher_groups_objs = Group.query.filter(Group.id.in_(group_ids)).all()
                teacher_direction_ids = list({g.direction_id for g in teacher_groups_objs if g.direction_id})
                # Biriktirilgan guruhlar + yo'nalish darajasi (group_id=None) + shu yo'nalishlardagi barcha darslar
                if teacher_direction_ids:
                    all_lessons = subject.lessons.filter(
                        (Lesson.group_id.in_(group_ids)) | (Lesson.group_id.is_(None)) |
                        (Lesson.direction_id.in_(teacher_direction_ids))
                    ).order_by(Lesson.order).all()
                else:
                    all_lessons = subject.lessons.filter(
                        (Lesson.group_id.in_(group_ids)) | (Lesson.group_id.is_(None))
                    ).order_by(Lesson.order).all()
            else:
                # Guruh biriktirilmagan: fanda bor barcha yo'nalishlardagi darslar (barcha dars turlari)
                curriculum_direction_ids = list({dc.direction_id for dc in DirectionCurriculum.query.filter_by(subject_id=subject.id).all() if dc.direction_id})
                if curriculum_direction_ids:
                    all_lessons = subject.lessons.filter(
                        (Lesson.direction_id.in_(curriculum_direction_ids)) | (Lesson.direction_id.is_(None))
                    ).order_by(Lesson.order).all()
                else:
                    all_lessons = subject.lessons.order_by(Lesson.order).all()
    
    # Barcha dars turlari bo'yicha ajratish (registrdan mustaqil: Amaliyot / amaliyot)
    def _lesson_type_eq(lesson, name):
        return (lesson.lesson_type or '').strip().lower() == (name or '').strip().lower()
    maruza_lessons = [l for l in all_lessons if _lesson_type_eq(l, 'maruza')]
    amaliyot_lessons = [l for l in all_lessons if _lesson_type_eq(l, 'amaliyot')]
    laboratoriya_lessons = [l for l in all_lessons if _lesson_type_eq(l, 'laboratoriya')]
    seminar_lessons = [l for l in all_lessons if _lesson_type_eq(l, 'seminar')]
    kurs_ishi_lessons = [l for l in all_lessons if _lesson_type_eq(l, 'kurs_ishi')]
    
    # Talaba uchun: qaysi darslar qulflanganligini aniqlash
    lesson_locked_status = {}
    if current_role == 'student' and current_user.group_id:
        group = Group.query.get(current_user.group_id)
        for lesson in all_lessons:
            # Faqat videoga ega darslar uchun qulf tekshiruvi
            if lesson.video_file or lesson.video_url:
                # Bir xil fan, dars turi, yo'nalish va guruhdagi oldingi darslarni olish (all_lessons bilan mos)
                previous_lessons_query = Lesson.query.filter(
                    Lesson.subject_id == subject.id,
                    Lesson.lesson_type == lesson.lesson_type,
                    Lesson.order < lesson.order,
                    ((Lesson.group_id == current_user.group_id) | (Lesson.group_id.is_(None)))
                )
                if group and group.direction_id:
                    previous_lessons_query = previous_lessons_query.filter(
                        (Lesson.direction_id == group.direction_id) | (Lesson.direction_id.is_(None))
                    )
                previous_lessons = previous_lessons_query.order_by(Lesson.order).all()
                
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



    if (current_user.role in ['admin', 'dean', 'edu_dept']) and current_role != 'teacher':
        # Admin va dekan uchun barcha topshiriqlar
        assignments_query = subject.assignments
        if direction_id:
            assignments_query = assignments_query.filter(
                (Assignment.direction_id == direction_id) | (Assignment.direction_id.is_(None))
            )
            if requested_semester:
                assignments_query = assignments_query.outerjoin(Group, Assignment.group_id == Group.id).filter(
                    (Group.semester == requested_semester) | (Assignment.group_id.is_(None))
                )
        assignments = assignments_query.order_by(Assignment.created_at.desc()).all()
    elif current_role == 'student' and current_user.group_id:
        # Talaba uchun - faqat o'z guruhining topshiriqlari
        # Include generic assignments (group_id is None)
        assignments_query = subject.assignments.filter(
            (Assignment.group_id == current_user.group_id) | (Assignment.group_id.is_(None))
        )
        
        # Agar direction_id berilgan bo'lsa, shu yo'nalishga tegishli topshiriqlar
        if direction_id:
            assignments_query = assignments_query.filter(
                (Assignment.direction_id == direction_id) | (Assignment.direction_id.is_(None))
            )
            if requested_semester:
                assignments_query = assignments_query.outerjoin(Group, Assignment.group_id == Group.id).filter(
                    (Group.semester == requested_semester) | (Assignment.group_id.is_(None))
                )
        
        assignments_list = assignments_query.all()
        
        # Re-use valid_teacher_ids from lesson logic if available, or fetch again
        if 'valid_teacher_ids' not in locals():
            valid_teachers_ass = TeacherSubject.query.filter_by(
                group_id=current_user.group_id,
                subject_id=subject.id
            ).all()
            valid_teacher_ids = [t.teacher_id for t in valid_teachers_ass]
            
            def is_visible_to_student(item):
                if item.created_by in valid_teacher_ids:
                    return True
                if item.creator and item.creator.role in ['admin', 'dean', 'edu_dept']:
                    return True
                if not item.created_by:
                    return True
                return False

        assignments = [a for a in assignments_list if is_visible_to_student(a)]

    elif current_role == 'teacher':
        # O'qituvchi o'zi dars beradigan guruhlarning topshiriqlarini ko'radi
        # Agar direction_id berilgan bo'lsa, faqat shu yo'nalishdagi guruhlar
        teacher_groups_query = TeacherSubject.query.filter_by(
            teacher_id=current_user.id,
            subject_id=subject.id
        )
        
        if direction_id:
            # Faqat shu yo'nalishdagi guruhlar
            direction_groups_filter = Group.query.filter_by(direction_id=direction_id)
            if requested_semester:
                direction_groups_filter = direction_groups_filter.filter_by(semester=requested_semester)
            direction_group_ids = [g.id for g in direction_groups_filter.all()]
            teacher_groups = teacher_groups_query.filter(TeacherSubject.group_id.in_(direction_group_ids)).all()
        else:
            teacher_groups = teacher_groups_query.all()
        
        group_ids = [ts.group_id for ts in teacher_groups if ts.group_id]
        if group_ids:
            # O'ziga biriktirilgan guruhlar + yo'nalish darajasi + shu yo'nalishlardagi barcha topshiriqlar
            if group_id and group_id in group_ids:
                assignments_query = subject.assignments.filter(
                    (Assignment.group_id == group_id) | (Assignment.group_id.is_(None))
                )
            else:
                teacher_groups_objs = Group.query.filter(Group.id.in_(group_ids)).all()
                teacher_direction_ids = list({g.direction_id for g in teacher_groups_objs if g.direction_id})
                if teacher_direction_ids:
                    assignments_query = subject.assignments.filter(
                        (Assignment.group_id.in_(group_ids)) | (Assignment.group_id.is_(None)) |
                        (Assignment.direction_id.in_(teacher_direction_ids))
                    )
                else:
                    assignments_query = subject.assignments.filter(
                        (Assignment.group_id.in_(group_ids)) | (Assignment.group_id.is_(None))
                    )
            if direction_id:
                assignments_query = assignments_query.filter(
                    (Assignment.direction_id == direction_id) | (Assignment.direction_id.is_(None))
                )
                if requested_semester:
                    assignments_query = assignments_query.outerjoin(Group, Assignment.group_id == Group.id).filter(
                        (Group.semester == requested_semester) | (Assignment.group_id.is_(None))
                    )
            assignments = assignments_query.order_by(Assignment.created_at.desc()).all()
        else:
            # Guruh biriktirilmagan: fanda bor barcha yo'nalishlardagi topshiriqlar (barcha dars turlari)
            curriculum_direction_ids = list({dc.direction_id for dc in DirectionCurriculum.query.filter_by(subject_id=subject.id).all() if dc.direction_id})
            if curriculum_direction_ids:
                assignments_query = subject.assignments.filter(
                    (Assignment.direction_id.in_(curriculum_direction_ids)) | (Assignment.direction_id.is_(None))
                )
            else:
                assignments_query = subject.assignments
            assignments = assignments_query.order_by(Assignment.created_at.desc()).all()

    # Testlar ro'yxati (assignments logikasiga o'xshash)
    tests = []
    if (current_user.role in ['admin', 'dean', 'edu_dept']) and current_role != 'teacher':
        tests_query = Test.query.filter_by(subject_id=subject.id)
        if direction_id:
            tests_query = tests_query.filter(
                (Test.direction_id == direction_id) | (Test.direction_id.is_(None))
            )
        if requested_semester:
            tests_query = tests_query.outerjoin(Group, Test.group_id == Group.id).filter(
                (Group.semester == requested_semester) | (Test.group_id.is_(None))
            )
        tests = tests_query.order_by(Test.created_at.desc()).all()
    elif current_role == 'student' and current_user.group_id:
        tests_query = Test.query.filter_by(subject_id=subject.id).filter(
            (Test.group_id == current_user.group_id) | (Test.group_id.is_(None))
        )
        if direction_id:
            tests_query = tests_query.filter(
                (Test.direction_id == direction_id) | (Test.direction_id.is_(None))
            )
        if requested_semester:
            tests_query = tests_query.outerjoin(Group, Test.group_id == Group.id).filter(
                (Group.semester == requested_semester) | (Test.group_id.is_(None))
            )
        tests = tests_query.order_by(Test.created_at.desc()).all()
    elif current_role == 'teacher':
        teacher_groups_ts = TeacherSubject.query.filter_by(
            teacher_id=current_user.id,
            subject_id=subject.id
        ).all()
        group_ids_ts = [tg.group_id for tg in teacher_groups_ts if tg.group_id]
        if group_ids_ts:
            if direction_id:
                dir_gr_ids = [g.id for g in Group.query.filter_by(direction_id=direction_id).all()]
                target_gr = [g for g in group_ids_ts if g in dir_gr_ids]
            else:
                target_gr = group_ids_ts
            tests_query = Test.query.filter_by(subject_id=subject.id).filter(
                (Test.group_id.in_(target_gr)) | (Test.group_id.is_(None))
            )
            if direction_id:
                tests_query = tests_query.filter(
                    (Test.direction_id == direction_id) | (Test.direction_id.is_(None))
                )
            if requested_semester:
                tests_query = tests_query.outerjoin(Group, Test.group_id == Group.id).filter(
                    (Group.semester == requested_semester) | (Test.group_id.is_(None))
                )
            tests = tests_query.order_by(Test.created_at.desc()).all()
    
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
            # Ball hisoblash uchun eng yuqori baholangan javob
            graded_subs = [s for s in all_subs if s.score is not None]
            best_sub = max(graded_subs, key=lambda s: s.score) if graded_subs else None
            is_any_graded = any(s.score is not None for s in all_subs)
            remaining_attempts = 3 - len(all_subs)
            if remaining_attempts < 0: remaining_attempts = 0
            
            assignment_status[assignment.id] = {
                'latest_sub': latest_sub,
                'best_sub': best_sub,
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
            if status_dict and status_dict.get('best_sub'):
                submission = status_dict['best_sub']
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

    def _normalize_lesson_type_to_canonical(raw):
        """TeacherSubject.lesson_type ni kanonik allowed_lesson_types formatiga o'tkazish (lab->laboratoriya, amal->amaliyot, ...)"""
        if not raw:
            return None
        lt = (raw or '').strip().lower()
        if not lt:
            return None
        if lt in ('maruza', 'amaliyot', 'laboratoriya', 'seminar', 'kurs_ishi'):
            return lt
        if 'maru' in lt or 'lect' in lt:
            return 'maruza'
        if 'sem' in lt:
            return 'seminar'
        if 'lab' in lt or 'lob' in lt:
            return 'laboratoriya'
        if 'kurs' in lt or 'course' in lt:
            return 'kurs_ishi'
        if 'amal' in lt or 'prac' in lt:
            return 'amaliyot'
        return lt
    
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
            group_query = Group.query.filter_by(direction_id=direction_id)
            if requested_semester:
                group_query = group_query.filter_by(semester=requested_semester)
            direction_group_ids = [g.id for g in group_query.all()]
            
            # Guruh tanlangan bo'lsa (group_id) — faqat shu guruhdagi o'qituvchilar; aks holda yo'nalishdagi barcha
            if group_id:
                gr = Group.query.get(group_id)
                if gr and gr.direction_id == direction_id:
                    target_group_ids = [group_id]
                else:
                    target_group_ids = direction_group_ids
            else:
                target_group_ids = direction_group_ids
            all_teacher_assignments = TeacherSubject.query.filter_by(
                subject_id=subject.id
            ).filter(TeacherSubject.group_id.in_(target_group_ids)).all()
            is_direction_filtered = True  # Allaqachon filtr qilingan
        else:
            # direction_id bo'lmasa, barcha o'qituvchilar
            all_teacher_assignments = subject.teacher_assignments.all()
        
    # O'quv rejadan qaysi dars turlari mavjud ekanligini aniqlash (guruh kontekstiga mos)
    allowed_lesson_types = set()  # O'quv rejada mavjud dars turlari
    curriculum_item = None
    
    if target_direction_id:
        # Kontekst guruhi — qaysi guruh uchun curriculum ko'rsatilishi kerak
        context_group_for_teachers = None
        if current_user.role == 'student' and current_user.group_id:
            context_group_for_teachers = Group.query.get(current_user.group_id)
        elif group_id:
            context_group_for_teachers = Group.query.get(group_id)
        elif direction_groups:
            context_group_for_teachers = direction_groups[0] if direction_groups else None
        
        curriculum_query = DirectionCurriculum.query.filter_by(
            direction_id=target_direction_id,
            subject_id=subject.id
        )
        if context_group_for_teachers:
            curriculum_query = DirectionCurriculum.filter_by_group_context(curriculum_query, context_group_for_teachers)
        sem = requested_semester or (context_group_for_teachers.semester if context_group_for_teachers and context_group_for_teachers.semester else None)
        if sem:
            curriculum_query = curriculum_query.filter_by(semester=sem)
        curriculum_item = curriculum_query.first()
        
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
        # Yo'nalish tanlanmagan bo'lsa yoki o'quv reja topilmasa, barcha dars turlarini ruxsat berish
        allowed_lesson_types = {'maruza', 'amaliyot', 'laboratoriya', 'seminar', 'kurs_ishi'}
    
    # Agar yo'nalish tanlangan bo'lsa-yu, lekin o'quv reja topilmasa (curriculum_item is None)
    # unda allowed_lesson_types bo'sh bo'lib qoladi. Uni to'ldirishimiz kerak.
    if target_direction_id and not allowed_lesson_types:
        allowed_lesson_types = {'maruza', 'amaliyot', 'laboratoriya', 'seminar', 'kurs_ishi'}

    # allowed_lesson_types faqat o'quv rejadagi soatlardan aniqlanadi. O'qituvchi biriktirilgan
    # dars turlarini bu yerga qo'shmaslik – rejadan soat o'chirilsa (masalan seminar), kartochkada ham ko'rinmasin.

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
        
        # Dars turini ko'rsatish - faqat o'quv rejada soat kiritilgan dars turlarini ko'rsatish
        if should_add_lesson_type:
            lt_canonical = _normalize_lesson_type_to_canonical(ta.lesson_type)
            if not lt_canonical:
                pass
            elif target_direction_id and curriculum_item and lt_canonical not in allowed_lesson_types:
                pass  # O'quv rejada bu dars turi uchun soat yo'q - ko'rsatmaslik
            else:
                lesson_type_name = lesson_type_names.get(lt_canonical, (ta.lesson_type or '').capitalize())
                if lesson_type_name and lesson_type_name not in teacher_lesson_types[ta.teacher_id]:
                    teacher_lesson_types[ta.teacher_id].append(lesson_type_name)
    
    # Agar yo'nalish tanlangan bo'lsa, DirectionCurriculum jadvalidan "laboratoriya" va "kurs_ishi" soatlarini tekshirish
    # va agar bu dars turlari uchun o'qituvchi biriktirilgan bo'lsa, ularni ham ko'rsatish
    if target_direction_id and curriculum_item:
            # Talaba uchun faqat uning guruhini; group_id tanlangan bo'lsa faqat shu guruh; aks holda yo'nalishdagi barcha
            if current_user.role == 'student' and current_user.group_id:
                target_group_ids = [current_user.group_id]
            elif group_id:
                gr = Group.query.get(group_id)
                target_group_ids = [group_id] if (gr and gr.direction_id == target_direction_id) else []
            else:
                target_group_ids = []
            if not target_group_ids:
                # Bu yo'nalish uchun guruhlarni olish (va semestr bo'yicha filterlash)
                direction_groups_query = Group.query.filter_by(direction_id=target_direction_id)
                if requested_semester:
                    direction_groups_query = direction_groups_query.filter_by(semester=requested_semester)
                elif curriculum_item:
                    direction_groups_query = direction_groups_query.filter_by(semester=curriculum_item.semester)
                
                # Faqat talabasi bor faol guruhlarni olish
                all_possible_groups = direction_groups_query.all()
                direction_groups = [g for g in all_possible_groups if g.get_students_count() > 0]
                target_group_ids = [g.id for g in direction_groups]
                
                # Agar guruhlar topilgan bo'lsa, semestrni birincisidan olish (user request: guruhdan oladi)
                if direction_groups:
                    if not requested_semester:
                        direction_semester = direction_groups[0].semester
                    direction_course = direction_groups[0].course_year
            
            # Laboratoriya va Kurs ishi uchun o'qituvchi biriktirishlarini bir marta olish
            dir_teacher_assignments = TeacherSubject.query.filter(
                TeacherSubject.subject_id == subject.id,
                TeacherSubject.group_id.in_(target_group_ids)
            ).all() if target_group_ids else []

            # Laboratoriya tekshiruvi
            if (curriculum_item.hours_laboratoriya or 0) > 0:
                # Laboratoriya uchun o'qituvchini qidirish (lab, lob, laboratoriya variantlarini ham qamrab olish)
                lab_teacher_assignment = None
                for a in dir_teacher_assignments:
                    if _normalize_lesson_type_to_canonical(a.lesson_type) == 'laboratoriya':
                        lab_teacher_assignment = a
                        break
                if not lab_teacher_assignment:
                    # Agar alohida laboratoriya biriktirishi yo'q bo'lsa, amaliyot o'qituvchisini qidirish
                    for a in dir_teacher_assignments:
                        if _normalize_lesson_type_to_canonical(a.lesson_type) == 'amaliyot':
                            lab_teacher_assignment = a
                            break
                
                if lab_teacher_assignment and lab_teacher_assignment.teacher_id in seen_teacher_ids:
                    if 'Laboratoriya' not in teacher_lesson_types[lab_teacher_assignment.teacher_id]:
                        teacher_lesson_types[lab_teacher_assignment.teacher_id].append('Laboratoriya')
            
            # Kurs ishi tekshiruvi
            if (curriculum_item.hours_kurs_ishi or 0) > 0:
                # Kurs ishi uchun o'qituvchini qidirish (kurs_ishi, kurs ishi, kurs variantlarini ham qamrab olish)
                kurs_teacher_assignment = None
                for a in dir_teacher_assignments:
                    if _normalize_lesson_type_to_canonical(a.lesson_type) == 'kurs_ishi':
                        kurs_teacher_assignment = a
                        break
                if not kurs_teacher_assignment:
                    for a in dir_teacher_assignments:
                        if _normalize_lesson_type_to_canonical(a.lesson_type) == 'amaliyot':
                            kurs_teacher_assignment = a
                            break
                
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
    
    # Agar direction_id bo'lsa, aynan shu yo'nalish uchun dars turlarini olish (guruh kontekstiga mos)
    if direction and direction_id:
        context_group_lt = None
        if group_id and direction_groups:
            context_group_lt = next((g for g in direction_groups if g.id == group_id), direction_groups[0] if direction_groups else None)
        elif direction_groups:
            context_group_lt = direction_groups[0]
        curriculum_query = DirectionCurriculum.query.filter_by(
            direction_id=direction_id,
            subject_id=subject.id
        )
        if context_group_lt:
            curriculum_query = DirectionCurriculum.filter_by_group_context(curriculum_query, context_group_lt)
        if direction_semester:
            curriculum_query = curriculum_query.filter_by(semester=direction_semester)
            
        curriculum_item = curriculum_query.first()
        
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
            
            # Kurs ishi - bor bo'lsa "bor" ko'rsatiladi, soat emas
            if curriculum_item.hours_kurs_ishi and curriculum_item.hours_kurs_ishi > 0:
                direction_lesson_types.append({
                    'type': 'Kurs ishi',
                    'hours': 0
                })
    
    # Talaba uchun ham dars turlarini ko'rsatish (guruh kontekstiga mos)
    elif current_user.role == 'student' and direction:
        student_group = Group.query.get(current_user.group_id) if current_user.group_id else None
        curriculum_query = DirectionCurriculum.query.filter_by(
            direction_id=direction.id,
            subject_id=subject.id
        )
        if student_group:
            curriculum_query = DirectionCurriculum.filter_by_group_context(curriculum_query, student_group)
        if direction_semester:
            curriculum_query = curriculum_query.filter_by(semester=direction_semester)
            
        curriculum_item = curriculum_query.first()

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

            # Kurs ishi - bor bo'lsa "bor" ko'rsatiladi, soat emas
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
    elif current_role in ['admin', 'dean', 'edu_dept'] and direction_id:
        # Admin yoki dekan uchun (direction_id bo'lsa) - o'quv rejadagi barcha dars turlarini ko'rsatish
        curriculum_items = DirectionCurriculum.query.filter_by(
            direction_id=direction_id,
            subject_id=subject.id
        ).all()
        
        for item in curriculum_items:
            # Maruza
            if item.hours_maruza and item.hours_maruza > 0:
                lesson_types.append({
                    'type': 'Maruza',
                    'hours': item.hours_maruza,
                    'is_admin': True
                })
            
            # Amaliyot
            amaliyot_hours = (item.hours_amaliyot or 0) + (item.hours_laboratoriya or 0)
            if amaliyot_hours > 0:
                lesson_types.append({
                    'type': 'Amaliyot',
                    'hours': amaliyot_hours,
                    'is_admin': True
                })
            
            # Seminar
            if item.hours_seminar and item.hours_seminar > 0:
                lesson_types.append({
                    'type': 'Seminar',
                    'hours': item.hours_seminar,
                    'is_admin': True
                })
            
            # Kurs ishi
            if item.hours_kurs_ishi and item.hours_kurs_ishi > 0:
                lesson_types.append({
                    'type': 'Kurs ishi',
                    'hours': 0,
                    'is_admin': True
                })
    
    # Javoblar va baholanmaganlar soni: o'qituvchi, admin, dekan, o'quv bo'limi uchun
    assignment_submission_stats = {}
    if (current_user.role == 'teacher' or current_user.has_role('teacher')) or current_user.role == 'admin' or current_role in ['dean', 'edu_dept']:
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
    if (current_user.role in ['admin', 'dean', 'edu_dept']) and current_role != 'teacher' and current_role != 'edu_dept':
        # Admin/Dekan barcha darslarni edit qila oladi; o'quv bo'limi faqat ko'rish
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
                lt = _normalize_lesson_type_to_canonical(ta.lesson_type) or (ta.lesson_type or '').strip().lower()
                if lt:
                    teacher_assigned_lesson_types.add(lt)
        
        # Amaliyot biriktirilgan o'qituvchi laboratoriya va kurs_ishi darslarini ham tahrirlashi mumkin
        if 'amaliyot' in teacher_assigned_lesson_types:
            teacher_assigned_lesson_types.add('laboratoriya')
            teacher_assigned_lesson_types.add('kurs_ishi')
        
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
    if (current_user.role in ['admin', 'dean', 'edu_dept']) and current_role != 'teacher' and current_role != 'edu_dept':
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

    # O'quv reja tekshiruvi (admin, dekan va o'qituvchi uchun)
    curriculum_check = None
    if direction_id and current_role in ['admin', 'dean', 'edu_dept', 'teacher']:
        teacher_id = current_user.id if current_role == 'teacher' else None
        is_admin = (current_role in ['admin', 'dean', 'edu_dept'])
        curriculum_check = subject.check_curriculum_completion(direction_id, teacher_id, is_admin)

    # Ierarxik URL orqali so'ralgan guruhni olish
    requested_group = None
    if direction_id and requested_semester and requested_group_name:
        requested_group = Group.query.filter_by(
            direction_id=direction_id,
            semester=requested_semester,
            name=requested_group_name
        ).first()
        
        # Fallback: Agar yo'nalish/semestr bo'yicha topilmasa, nomi bo'yicha qidirish
        if not requested_group:
            requested_group = Group.query.filter_by(name=requested_group_name).first()

    # O'quv rejada soat kiritilgan YOKI o'qituvchi biriktirilgan dars turlari (tab ko'rsatish uchun)
    type_to_key = {'Maruza': 'maruza', 'Amaliyot': 'amaliyot', 'Laboratoriya': 'laboratoriya',
                   'Seminar': 'seminar', 'Kurs ishi': 'kurs_ishi'}
    curriculum_lesson_type_keys = {type_to_key.get(d['type']) for d in direction_lesson_types if type_to_key.get(d['type'])}

    # O'qituvchi direction_id siz kirganda ham o'quv rejadagi dars turlarini ko'rsatish
    if not curriculum_lesson_type_keys and (current_role == 'teacher' or current_user.has_role('teacher')) and subject.id:
        teacher_ts = TeacherSubject.query.filter_by(teacher_id=current_user.id, subject_id=subject.id).all()
        seen_dir_ids = set()
        for ts in teacher_ts:
            if ts.group_id and ts.group and ts.group.direction_id and ts.group.direction_id not in seen_dir_ids:
                seen_dir_ids.add(ts.group.direction_id)
                dc_list = DirectionCurriculum.query.filter_by(
                    direction_id=ts.group.direction_id,
                    subject_id=subject.id
                ).all()
                for dc in dc_list:
                    if (dc.hours_maruza or 0) > 0:
                        curriculum_lesson_type_keys.add('maruza')
                    if (dc.hours_amaliyot or 0) > 0:
                        curriculum_lesson_type_keys.add('amaliyot')
                    if (dc.hours_laboratoriya or 0) > 0:
                        curriculum_lesson_type_keys.add('laboratoriya')
                    if (dc.hours_seminar or 0) > 0:
                        curriculum_lesson_type_keys.add('seminar')
                    if (dc.hours_kurs_ishi or 0) > 0:
                        curriculum_lesson_type_keys.add('kurs_ishi')

    # curriculum_lesson_type_keys faqat o'quv rejada soati > 0 bo'lgan dars turlarini o'z ichiga oladi.
    # O'qituvchi biriktirilgan lekin rejada soati yo'q turlarni qo'shmaslik – tab va header mos bo'ladi.
    # O'qituvchi biriktirilgan lekin rejada soati yo'q turlarni (soat 0 bilan) qo'shmaslik –
    # ular "Amaliyot: Mavjud" kabi noto'g'ri ko'rinishga olib keladi.

    # Faqat o'quv rejada biriktirilgan dars turlariga ega o'qituvchilarni ko'rsatish (bo'sh teacher_lesson_types li o'qituvchilarni olib tashlash)
    all_teachers_list = [t for t in all_teachers_list if teacher_lesson_types.get(t.id)]

    # Barcha o'qituvchilar (biriktirish uchun)
    all_available_teachers = []
    if current_user.role in ['admin', 'dean', 'edu_dept']:
        # O'qituvchi, dekan yoki admin rollaridan biriga ega barcha foydalanuvchilar
        all_available_teachers = User.query.filter(
            (User.role.in_(['teacher', 'dean', 'admin'])) |
            (User.id.in_(db.session.query(UserRole.user_id).filter(UserRole.role.in_(['teacher', 'dean', 'admin']))))
        ).distinct().all()

    return render_template('courses/detail.html',
                         subject=subject,
                         lessons=all_lessons,
                         maruza_lessons=maruza_lessons,
                         amaliyot_lessons=amaliyot_lessons,
                         laboratoriya_lessons=laboratoriya_lessons,
                         seminar_lessons=seminar_lessons,
                         kurs_ishi_lessons=kurs_ishi_lessons,
                         assignments=assignments,
                         tests=tests,
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
                         group_id=group_id,
                         direction=direction,
                         direction_groups=direction_groups,
                         direction_semester=direction_semester,
                         direction_course=direction_course,
                         direction_credits=direction_credits,
                         direction_lesson_types=direction_lesson_types,
                         curriculum_lesson_type_keys=curriculum_lesson_type_keys,
                         all_teachers_list=all_teachers_list,
                         teacher_lesson_types=teacher_lesson_types,
                         allowed_lesson_types=allowed_lesson_types,
                         lesson_edit_permissions=lesson_edit_permissions,
                         assignment_manage_permissions=assignment_manage_permissions,
                         assignment_submission_stats=assignment_submission_stats,
                         assignment_highest_scores=assignment_highest_scores,
                         assignment_is_overdue=assignment_is_overdue,
                         curriculum_check=curriculum_check,
                         requested_group=requested_group,
                         requested_lesson_type=requested_lesson_type,
                         all_available_teachers=all_available_teachers)


@bp.route('/<int:id>/lessons/create', methods=['GET', 'POST'])
@login_required
def create_lesson(id):
    """Yangi dars yaratish"""
    subject = Subject.query.get_or_404(id)
    
    # Yo'nalish va guruh ID (path parametrlaridan)
    direction_id = request.args.get('direction_id', type=int)
    group_id_param = request.args.get('group_id', type=int)
    
    # Tanlangan rol
    current_role = session.get('current_role', current_user.role)
    has_admin_or_dean_account = (
        current_user.has_role('admin') or
        current_user.has_role('dean') or
        current_user.has_role('edu_dept') or
        (current_user.role in ['admin', 'dean', 'edu_dept']) or
        getattr(current_user, 'is_superadmin', False)
    )
    is_admin_or_dean_mode = (
        current_role in ['admin', 'dean'] and has_admin_or_dean_account
    )
    
    # Faqat o'qituvchi rolida va o'ziga biriktirilgan fanlar uchun
    is_teacher = TeacherSubject.query.filter_by(
        teacher_id=current_user.id,
        subject_id=subject.id
    ).first() is not None
    
    # Bir nechta rol belgilangan o'qituvchilar faqatgina o'qituvchi rolida o'ziga biriktirilgan fan uchun mavzu yarata olishi kerak
    if current_role != 'teacher' or not is_teacher:
        if not is_admin_or_dean_mode:
            flash(t('no_permission_for_operation'), 'error')
            return redirect(url_for('courses.detail', id=id, dir_id=direction_id))
    
    # O'qituvchiga biriktirilgan guruhlar
    # Agar direction_id berilgan bo'lsa, faqat shu yo'nalishdagi guruhlar
    teacher_groups_query = TeacherSubject.query.filter_by(
        teacher_id=current_user.id,
        subject_id=subject.id
    )
    
    if direction_id:
        direction_group_ids = [g.id for g in Group.query.filter_by(direction_id=direction_id).all()]
        groups_without_direction = [g.id for g in Group.query.filter(Group.direction_id.is_(None)).all()]
        allowed_group_ids = direction_group_ids + groups_without_direction
        teacher_groups = teacher_groups_query.filter(TeacherSubject.group_id.in_(allowed_group_ids)).all()
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
    # Faqat aynan teacher rolida ishlaganda o'qituvchi cheklovlarini qo'llash.
    is_acting_as_teacher = (current_role == 'teacher')
    
    if is_acting_as_teacher:
        lesson_types_set = set()
        if direction_id:
            direction_group_ids = [g.id for g in Group.query.filter_by(direction_id=direction_id).all()]
            groups_without_direction = [g.id for g in Group.query.filter(Group.direction_id.is_(None)).all()]
            allowed_group_ids = direction_group_ids + groups_without_direction
            teacher_assignments = TeacherSubject.query.filter(
                TeacherSubject.teacher_id == current_user.id,
                TeacherSubject.subject_id == subject.id,
                TeacherSubject.group_id.in_(allowed_group_ids)
            ).all()
            for ta in teacher_assignments:
                if ta.lesson_type:
                    canonical = _normalize_lesson_type_to_canonical(ta.lesson_type)
                    if canonical:
                        lesson_types_set.add(canonical)
            
            context_group = Group.query.get(group_id_param) if group_id_param else None
            if not context_group and direction_group_ids:
                context_group = Group.query.get(direction_group_ids[0])
            curr_query = DirectionCurriculum.query.filter_by(
                direction_id=direction_id,
                subject_id=subject.id
            )
            if context_group and context_group.semester:
                curr_query = curr_query.filter_by(semester=context_group.semester)
            curriculum_item = DirectionCurriculum.filter_by_group_context(curr_query, context_group).first() if context_group else curr_query.first()
            if curriculum_item:
                curriculum_lesson_types = set()
                if (curriculum_item.hours_maruza or 0) > 0:
                    curriculum_lesson_types.add('maruza')
                if (curriculum_item.hours_amaliyot or 0) > 0:
                    curriculum_lesson_types.add('amaliyot')
                if (curriculum_item.hours_laboratoriya or 0) > 0:
                    curriculum_lesson_types.add('laboratoriya')
                if (curriculum_item.hours_seminar or 0) > 0:
                    curriculum_lesson_types.add('seminar')
                if (curriculum_item.hours_kurs_ishi or 0) > 0:
                    curriculum_lesson_types.add('kurs_ishi')
                if curriculum_lesson_types:
                    lesson_types_set &= curriculum_lesson_types
                has_lab_hours = (curriculum_item.hours_laboratoriya or 0) > 0
                lab_teacher_assignment = TeacherSubject.query.filter(
                    TeacherSubject.subject_id == subject.id,
                    TeacherSubject.group_id.in_(allowed_group_ids),
                    TeacherSubject.teacher_id == current_user.id,
                    db.func.lower(TeacherSubject.lesson_type).in_(['laboratoriya', 'amaliyot', 'lab', 'amal'])
                ).first()
                if lab_teacher_assignment and has_lab_hours:
                    lesson_types_set.add('laboratoriya')
                if (curriculum_item.hours_kurs_ishi or 0) > 0:
                    kurs_teacher_assignment = TeacherSubject.query.filter(
                        TeacherSubject.subject_id == subject.id,
                        TeacherSubject.group_id.in_(allowed_group_ids),
                        TeacherSubject.teacher_id == current_user.id,
                        db.func.lower(TeacherSubject.lesson_type).in_(['kurs_ishi', 'amaliyot', 'kurs'])
                    ).first()
                    if kurs_teacher_assignment:
                        lesson_types_set.add('kurs_ishi')
        else:
            teacher_assignments = TeacherSubject.query.filter_by(
                teacher_id=current_user.id,
                subject_id=subject.id
            ).all()
            for ta in teacher_assignments:
                if ta.lesson_type:
                    canonical = _normalize_lesson_type_to_canonical(ta.lesson_type)
                    if canonical:
                        lesson_types_set.add(canonical)
        
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
    else:
        if is_admin_or_dean_mode and current_role != 'teacher' and direction_id:
            context_group = Group.query.get(group_id_param) if group_id_param else None
            direction_groups_for_curr = Group.query.filter_by(direction_id=direction_id).all()
            if not context_group and direction_groups_for_curr:
                context_group = direction_groups_for_curr[0]
            curr_query = DirectionCurriculum.query.filter_by(
                direction_id=direction_id,
                subject_id=subject.id
            )
            if context_group and context_group.semester:
                curr_query = curr_query.filter_by(semester=context_group.semester)
            curriculum_item = DirectionCurriculum.filter_by_group_context(curr_query, context_group).first() if context_group else curr_query.first()
            if curriculum_item:
                if (curriculum_item.hours_maruza or 0) > 0:
                    allowed_lesson_types.append({'value': 'maruza', 'name': 'Maruza'})
                if (curriculum_item.hours_amaliyot or 0) > 0:
                    allowed_lesson_types.append({'value': 'amaliyot', 'name': 'Amaliyot'})
                if (curriculum_item.hours_laboratoriya or 0) > 0:
                    allowed_lesson_types.append({'value': 'laboratoriya', 'name': 'Laboratoriya'})
                if (curriculum_item.hours_seminar or 0) > 0:
                    allowed_lesson_types.append({'value': 'seminar', 'name': 'Seminar'})
                if (curriculum_item.hours_kurs_ishi or 0) > 0:
                    allowed_lesson_types.append({'value': 'kurs_ishi', 'name': 'Kurs ishi'})
            if not allowed_lesson_types:
                allowed_lesson_types = [
                    {'value': 'maruza', 'name': 'Maruza'},
                    {'value': 'amaliyot', 'name': 'Amaliyot'},
                    {'value': 'laboratoriya', 'name': 'Laboratoriya'},
                    {'value': 'seminar', 'name': 'Seminar'},
                    {'value': 'kurs_ishi', 'name': 'Kurs ishi'}
                ]
        elif is_admin_or_dean_mode and current_role != 'teacher':
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
                flash(t('no_permission_for_operation'), 'error')
                return render_template('courses/create_lesson.html', subject=subject, groups=groups, direction_id=direction_id, group_id=group_id_param, allowed_lesson_types=allowed_lesson_types)
            
            # Tanlangan dars turining ruxsat berilgan ro'yxatda borligini tekshirish
            allowed_values = [lt['value'] for lt in allowed_lesson_types]
            if selected_lesson_type not in allowed_values:
                flash(t('teacher_not_assigned_to_lesson_type_direction'), 'error')
                return render_template('courses/create_lesson.html', subject=subject, groups=groups, direction_id=direction_id, group_id=group_id_param, allowed_lesson_types=allowed_lesson_types)
            
            # Qo'shimcha tekshiruv: tanlangan dars turi shu yo'nalishda biriktirilganligini tekshirish
            if direction_id:
                direction_group_ids = [g.id for g in Group.query.filter_by(direction_id=direction_id).all()]
                groups_without_direction = [g.id for g in Group.query.filter(Group.direction_id.is_(None)).all()]
                allowed_group_ids = direction_group_ids + groups_without_direction
                teacher_assignment_exists = TeacherSubject.query.filter(
                    TeacherSubject.teacher_id == current_user.id,
                    TeacherSubject.subject_id == subject.id,
                    TeacherSubject.group_id.in_(allowed_group_ids),
                    db.func.lower(TeacherSubject.lesson_type) == selected_lesson_type.lower()
                ).first()
                
                if not teacher_assignment_exists and selected_lesson_type in ['laboratoriya', 'kurs_ishi']:
                    context_group = Group.query.get(group_id_param) if group_id_param else None
                    if not context_group and direction_group_ids:
                        context_group = Group.query.get(direction_group_ids[0])
                    curr_q = DirectionCurriculum.query.filter_by(
                        direction_id=direction_id,
                        subject_id=subject.id
                    )
                    if context_group and context_group.semester:
                        curr_q = curr_q.filter_by(semester=context_group.semester)
                    curriculum_item = DirectionCurriculum.filter_by_group_context(curr_q, context_group).first() if context_group else curr_q.first()
                    if curriculum_item:
                        if selected_lesson_type == 'laboratoriya' and ((curriculum_item.hours_laboratoriya or 0) > 0 or (curriculum_item.hours_amaliyot or 0) > 0):
                            teacher_assignment_exists = TeacherSubject.query.filter(
                                TeacherSubject.teacher_id == current_user.id,
                                TeacherSubject.subject_id == subject.id,
                                TeacherSubject.group_id.in_(allowed_group_ids),
                                db.func.lower(TeacherSubject.lesson_type).in_(['amaliyot', 'laboratoriya', 'lab', 'amal'])
                            ).first()
                        elif selected_lesson_type == 'kurs_ishi' and (curriculum_item.hours_kurs_ishi or 0) > 0:
                            teacher_assignment_exists = TeacherSubject.query.filter(
                                TeacherSubject.teacher_id == current_user.id,
                                TeacherSubject.subject_id == subject.id,
                                TeacherSubject.group_id.in_(allowed_group_ids),
                                db.func.lower(TeacherSubject.lesson_type).in_(['amaliyot', 'kurs_ishi', 'kurs'])
                            ).first()
                
                if not teacher_assignment_exists:
                    flash(t('teacher_not_assigned_to_lesson_type_direction'), 'error')
                    return render_template('courses/create_lesson.html', subject=subject, groups=groups, direction_id=direction_id, group_id=group_id_param, allowed_lesson_types=allowed_lesson_types)
        
        # Agar direction_id berilgan bo'lsa, avtomatik ravishda shu yo'nalishdagi barcha guruhlar uchun yaratiladi
        # Lekin agar guruh direction_id ga ega bo'lmasa yoki boshqa yo'nalishga tegishli bo'lsa ham, 
        # agar u o'qituvchiga biriktirilgan bo'lsa, u ham tanlanadi
        if direction_id:
            if is_admin_or_dean_mode and current_role != 'teacher':
                # Admin/dekan yo'nalish bo'yicha bitta umumiy dars yaratadi (group_id=None).
                # Bu holatda teacher assignment bo'yicha guruh tekshiruvi talab qilinmaydi.
                selected_group_ids = []
            else:
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
                    flash(t('no_permission_for_operation'), 'error')
                    return render_template('courses/create_lesson.html', subject=subject, groups=groups, direction_id=direction_id, group_id=group_id_param, allowed_lesson_types=allowed_lesson_types)
        else:
            # Admin uchun guruh tanlash ixtiyoriy (agar tanlanmagan bo'lsa, group_id None bo'ladi)
            selected_group_ids = request.form.getlist('group_ids')
            if not selected_group_ids and is_admin_or_dean_mode:
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
                flash(t('all_required_fields'), 'error')
                return render_template('courses/create_lesson.html', subject=subject, groups=groups, direction_id=direction_id, group_id=group_id_param, allowed_lesson_types=allowed_lesson_types)
        
        # Video URL faqat YouTube link bo'lishi kerak (kanonik ko'rinishda saqlanadi)
        video_url = request.form.get('video_url', '').strip()
        if video_url:
            video_id = extract_youtube_video_id(video_url)
            if not video_id:
                flash(t('invalid_request'), 'error')
                return render_template('courses/create_lesson.html', subject=subject, groups=groups, direction_id=direction_id, group_id=group_id_param, allowed_lesson_types=allowed_lesson_types)
            video_url = f'https://www.youtube.com/watch?v={video_id}'
        
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
                        flash(t('invalid_file_format', filename=lesson_file.filename), 'error')
                        return render_template('courses/create_lesson.html', subject=subject, groups=groups, direction_id=direction_id, group_id=group_id_param, allowed_lesson_types=allowed_lesson_types)
                    
                    # Faylni saqlash
                    filename = f"{uuid.uuid4().hex}.{ext}"
                    file_path = os.path.join(files_folder, filename)
                    lesson_file.save(file_path)
                    uploaded_files.append({
                        'filename': filename,
                        'original_name': lesson_file.filename
                    })
        
        # Fayl URL(lar)
        file_url_inputs = []
        for url_value in request.form.getlist('file_urls'):
            normalized = (url_value or '').strip()
            if normalized and normalized not in file_url_inputs:
                file_url_inputs.append(normalized)
        # Orqaga moslik: eski single input nomi
        legacy_file_url = request.form.get('file_url', '').strip()
        if legacy_file_url and legacy_file_url not in file_url_inputs:
            file_url_inputs.append(legacy_file_url)
            
            # O'qituvchi uchun fayl majburiy
        if current_role == 'teacher' or is_admin_or_dean_mode:
            # Agar hech qanday fayl yuklanmagan va URL ham bo'lmasa
            if not uploaded_files and not file_url_inputs:
                flash(t('all_required_fields'), 'error')
                return render_template('courses/create_lesson.html', subject=subject, groups=groups, direction_id=direction_id, group_id=group_id_param, allowed_lesson_types=allowed_lesson_types)
        
        # Fayl URL(lar)i yoki yuklangan fayllarni saqlash
        lesson_file_url = build_lesson_file_data(uploaded_files, file_url_inputs)
        
        # Har bir tanlangan guruh uchun alohida dars yaratish
        created_count = 0
        
        # Yo'nalish bo'yicha birlashtirish (One Lesson per Direction)
        if direction_id:
            # Agar direction_id bo'lsa, faqat bitta dars yaratiladi (group_id = None)
            # Bu dars ushbu yo'nalishdagi barcha guruhlar uchun ko'rinadi
            
            # Bu yo'nalish uchun maximal tartib raqamini topish
            max_order = db.session.query(db.func.max(Lesson.order)).filter(
                Lesson.subject_id == id,
                Lesson.direction_id == direction_id
            ).scalar() or 0
            
            lesson = Lesson(
                title=request.form.get('title'),
                content=request.form.get('content'),
                video_url=video_url if video_url else None,
                video_file=video_filename,
                file_url=lesson_file_url,
                duration=int(request.form.get('duration', 0) or 0),
                order=max_order + 1,
                lesson_type=request.form.get('lesson_type', 'maruza'),
                subject_id=id,
                group_id=None,  # Yo'nalish darajasidagi dars
                direction_id=direction_id,
                created_by=current_user.id
            )
            db.session.add(lesson)
            created_count = 1
        else:
            # direction_id bo'lmasa (masalan, admin tomonidan guruh tanlanganda), eski uslubda guruhlar uchun alohida yaratish
            for group_id_str in selected_group_ids:
                group_id = int(group_id_str) if group_id_str and group_id_str != 'None' else None
                
                # Bu guruh uchun direction_id ni aniqlash
                lesson_direction_id = None
                if group_id:
                    group = Group.query.get(group_id)
                    if group and group.direction_id:
                        lesson_direction_id = group.direction_id
                
                # Maximal tartib raqamini topish
                max_order_query = db.session.query(db.func.max(Lesson.order)).filter(Lesson.subject_id == id)
                if lesson_direction_id:
                    max_order_query = max_order_query.filter(Lesson.direction_id == lesson_direction_id)
                else:
                    max_order_query = max_order_query.filter(Lesson.direction_id.is_(None), Lesson.group_id == group_id)
                
                max_order = max_order_query.scalar() or 0
                
                lesson = Lesson(
                    title=request.form.get('title'),
                    content=request.form.get('content'),
                    video_url=video_url if video_url else None,
                    video_file=video_filename,
                    file_url=lesson_file_url,
                    duration=int(request.form.get('duration', 0) or 0),
                    order=max_order + 1,
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
            flash(t('lesson_created_for_groups', created_count=created_count), 'success')
        else:
            flash(t('error_occurred', error=''), 'error')
        
        if direction_id and group_id_param:
            return redirect(url_for('courses.detail', id=id, dir_id=direction_id, group_id=group_id_param))
        return redirect(url_for('courses.detail', id=id, dir_id=direction_id))
    
    return render_template('courses/create_lesson.html', subject=subject, groups=groups, direction_id=direction_id, group_id=group_id_param, allowed_lesson_types=allowed_lesson_types)


@bp.route('/check-file-url', methods=['POST'])
@login_required
def check_file_url():
    """Fayl URL da fayl bor-yo'qligini tekshirish"""
    data = request.get_json(silent=True) or {}
    file_url = data.get('url', '').strip()
    
    if not file_url:
        return jsonify({'success': False, 'has_file': False, 'error': 'URL kiritilmagan'})
    
    try:
        # Google Drive/Sheets/Docs linklarini aniqlash
        is_google_drive = 'docs.google.com' in file_url or 'drive.google.com' in file_url
        
        if is_google_drive:
            # Google Drive linklari uchun - ular har doim mavjud deb hisoblanadi
            # chunki ular HTML sahifani qaytaradi, lekin fayl mavjud
            google_title = extract_google_doc_title(file_url)
            display_name = google_title or extract_resource_display_name(file_url)
            return jsonify({
                'success': True,
                'has_file': True,
                'status_code': 200,
                'content_type': 'application/vnd.google-apps.document',
                'is_google_drive': True,
                'display_name': display_name,
                'resolved_url': file_url,
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
            'is_google_drive': False,
            'display_name': extract_resource_display_name(response.url or file_url, response.headers.get('Content-Disposition', '')),
            'resolved_url': response.url or file_url
        })
    except requests.exceptions.RequestException as e:
        # Xatolik bo'lsa, fayl topilmadi deb hisoblaymiz
        return jsonify({
            'success': False,
            'has_file': False,
            'error': str(e)
        })


@bp.route('/check-video-url', methods=['POST'])
@login_required
def check_video_url():
    """Video URL ko'rishga yaroqliligini tekshirish"""
    try:
        data = request.get_json(silent=True) or {}
        video_url = (data.get('url') or '').strip()

        if not video_url:
            return jsonify({'success': False, 'is_playable': False, 'error': 'URL kiritilmagan'})

        video_id = extract_youtube_video_id(video_url)
        if not video_id:
            return jsonify({'success': True, 'is_playable': False, 'error': 'Invalid YouTube URL'})

        watch_url = f'https://www.youtube.com/watch?v={video_id}'
        embed_url = f'https://www.youtube.com/embed/{video_id}'

        response = requests.get(
            'https://www.youtube.com/oembed',
            params={'url': watch_url, 'format': 'json'},
            headers={'User-Agent': 'Mozilla/5.0 (ELMS Video URL Checker)'},
            timeout=10
        )
    except requests.exceptions.RequestException as e:
        return jsonify({'success': False, 'is_playable': False, 'error': str(e)})
    except Exception as e:
        return jsonify({'success': False, 'is_playable': False, 'error': str(e)})

    if response.status_code == 200:
        try:
            payload = response.json() if response.content else {}
        except ValueError:
            # Ba'zi muhitlarda YouTube proxy/captcha sahifasini qaytarishi mumkin
            return jsonify({
                'success': True,
                'is_playable': False,
                'video_id': video_id,
                'watch_url': watch_url,
                'status_code': 200,
                'error': 'Non-JSON response from YouTube'
            })

        can_embed, embed_reason = check_youtube_embed_playability(video_id)
        if not can_embed:
            return jsonify({
                'success': True,
                'is_playable': False,
                'video_id': video_id,
                'watch_url': watch_url,
                'embed_url': embed_url,
                'title': payload.get('title', ''),
                'error': embed_reason or 'Video cannot be played inside embedded player'
            })

        return jsonify({
            'success': True,
            'is_playable': True,
            'video_id': video_id,
            'watch_url': watch_url,
            'embed_url': embed_url,
            'title': payload.get('title', '')
        })

    return jsonify({
        'success': True,
        'is_playable': False,
        'video_id': video_id,
        'watch_url': watch_url,
        'status_code': response.status_code
    })


@bp.route('/lessons/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit_lesson(id):
    """Darsni tahrirlash"""
    lesson = Lesson.query.get_or_404(id)
    subject = lesson.subject
    
    # Yo'nalish va guruh ID (query parametrdan)
    direction_id = request.args.get('direction_id', type=int)
    group_id_param = request.args.get('group_id', type=int)
    
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
    if (current_user.role in ['admin', 'dean']) and current_role != 'teacher' and current_role != 'edu_dept':
        can_edit = True
    elif current_role == 'teacher' and is_teacher:
        # Check if teacher is assigned to this lesson type and direction
        if direction_id and lesson.direction_id and lesson.direction_id != direction_id:
            # Explicit direction mismatch
            can_edit = False
        else:
            # Check assignment to lesson type (lab, laboratoriya, amaliyot va hokazo variantlarini hisobga olish)
            check_direction_id = direction_id or lesson.direction_id
            allowed_ts_types = _teacher_lesson_type_variants(lesson.lesson_type)
            
            if allowed_ts_types:
                lower_types = [t.lower() for t in allowed_ts_types]
                teacher_assignments_query = TeacherSubject.query.filter(
                    TeacherSubject.teacher_id == current_user.id,
                    TeacherSubject.subject_id == subject.id,
                    db.func.lower(TeacherSubject.lesson_type).in_(lower_types)
                )
            else:
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
        flash(t('no_permission_to_edit_lesson'), 'error')
        if direction_id and group_id_param:
            return redirect(url_for('courses.detail', id=subject.id, dir_id=direction_id, group_id=group_id_param))
        return redirect(url_for('courses.detail', id=subject.id, dir_id=direction_id))
    
    # Dars turlarini filtrlash: faqat o'quv rejada soati bor turlar + o'qituvchi biriktirilgan
    allowed_lesson_types = []
    
    check_dir_id = direction_id or lesson.direction_id
    if check_dir_id:
        direction_group_ids_calc = [g.id for g in Group.query.filter_by(direction_id=check_dir_id).all()]
        groups_without_direction = [g.id for g in Group.query.filter(Group.direction_id.is_(None)).all()]
        allowed_group_ids_calc = direction_group_ids_calc + groups_without_direction
        # Create bilan bir xil: guruh konteksti bo'yicha o'quv rejasini olish (semester, enrollment_year, education_type)
        context_group_calc = Group.query.get(group_id_param) if group_id_param else None
        if not context_group_calc and lesson.group_id:
            context_group_calc = Group.query.get(lesson.group_id)
        if not context_group_calc and direction_group_ids_calc:
            context_group_calc = Group.query.get(direction_group_ids_calc[0])
        curr_query_calc = DirectionCurriculum.query.filter_by(
            direction_id=check_dir_id,
            subject_id=subject.id
        )
        if context_group_calc and context_group_calc.semester:
            curr_query_calc = curr_query_calc.filter_by(semester=context_group_calc.semester)
        curriculum_item_calc = DirectionCurriculum.filter_by_group_context(curr_query_calc, context_group_calc).first() if context_group_calc else curr_query_calc.first()
        
        # O'quv rejada qaysi dars turlariga soat berilgan
        curriculum_lesson_types = set()
        if curriculum_item_calc:
            if (curriculum_item_calc.hours_maruza or 0) > 0:
                curriculum_lesson_types.add('maruza')
            if (curriculum_item_calc.hours_amaliyot or 0) > 0:
                curriculum_lesson_types.add('amaliyot')
            if (curriculum_item_calc.hours_laboratoriya or 0) > 0:
                curriculum_lesson_types.add('laboratoriya')
            if (curriculum_item_calc.hours_seminar or 0) > 0:
                curriculum_lesson_types.add('seminar')
            if (curriculum_item_calc.hours_kurs_ishi or 0) > 0:
                curriculum_lesson_types.add('kurs_ishi')
        
        lesson_types_set = set()
        teacher_assignments_calc = TeacherSubject.query.filter(
            TeacherSubject.teacher_id == current_user.id,
            TeacherSubject.subject_id == subject.id,
            TeacherSubject.group_id.in_(allowed_group_ids_calc)
        ).all()
        for ta in teacher_assignments_calc:
            canonical = _normalize_lesson_type_to_canonical(ta.lesson_type)
            if canonical:
                lesson_types_set.add(canonical)
        
        # Faqat o'quv rejada soati bor dars turlarini qoldirish (rejadan o'chirilgan tur ko'rinmasin)
        if curriculum_lesson_types:
            lesson_types_set &= curriculum_lesson_types
        if curriculum_item_calc:
            if (curriculum_item_calc.hours_laboratoriya or 0) > 0:
                lab_teacher_calc = TeacherSubject.query.filter(
                    TeacherSubject.subject_id == subject.id,
                    TeacherSubject.group_id.in_(allowed_group_ids_calc),
                    TeacherSubject.teacher_id == current_user.id,
                    db.func.lower(TeacherSubject.lesson_type).in_(['laboratoriya', 'amaliyot', 'lab', 'amal'])
                ).first()
                if lab_teacher_calc:
                    lesson_types_set.add('laboratoriya')
            if (curriculum_item_calc.hours_kurs_ishi or 0) > 0:
                kurs_teacher_calc = TeacherSubject.query.filter(
                    TeacherSubject.subject_id == subject.id,
                    TeacherSubject.group_id.in_(allowed_group_ids_calc),
                    TeacherSubject.teacher_id == current_user.id,
                    db.func.lower(TeacherSubject.lesson_type).in_(['kurs_ishi', 'amaliyot', 'kurs'])
                ).first()
                if kurs_teacher_calc:
                    lesson_types_set.add('kurs_ishi')
        
        lesson_type_names_map = {
            'maruza': 'Maruza',
            'amaliyot': 'Amaliyot',
            'laboratoriya': 'Laboratoriya',
            'seminar': 'Seminar',
            'kurs_ishi': 'Kurs ishi'
        }
        sorted_types = ['maruza', 'amaliyot', 'laboratoriya', 'seminar', 'kurs_ishi']
        allowed_lesson_types = []
        for l_type in sorted_types:
            if l_type in lesson_types_set:
                allowed_lesson_types.append({
                    'value': l_type,
                    'name': lesson_type_names_map.get(l_type, l_type.capitalize())
                })
        
        # Admin uchun: yo'nalish bo'lsa faqat o'quv rejadagi turlarni ko'rsatish (o'qituvchi biriktirishisiz)
        if (current_user.role in ['admin', 'dean', 'edu_dept']) and current_role != 'teacher' and curriculum_lesson_types and not allowed_lesson_types:
            allowed_lesson_types = [{'value': t, 'name': lesson_type_names_map.get(t, t.capitalize())} for t in sorted_types if t in curriculum_lesson_types]
        
        # O'qituvchi darsni tahrirlay oladi lekin dars turi ro'yxatda yo'q bo'lsa – joriy dars turini qo'shish (yaratgan darsini ko'rsatish uchun)
        if current_role == 'teacher' and lesson.lesson_type:
            lt_normalized = _normalize_lesson_type_to_canonical(lesson.lesson_type)
            if lt_normalized and lt_normalized in ('maruza', 'amaliyot', 'laboratoriya', 'seminar', 'kurs_ishi'):
                if not any(a['value'] == lt_normalized for a in allowed_lesson_types):
                    allowed_lesson_types.append({'value': lt_normalized, 'name': lesson_type_names_map.get(lt_normalized, lt_normalized.capitalize())})
    
    # Yo'nalish bo'lmaganda yoki allowed_lesson_types bo'sh bo'lsa – o'qituvchi o'z darsining turini ko'rsatish uchun qo'shish
    if (not allowed_lesson_types or not check_dir_id) and current_role == 'teacher' and lesson.lesson_type:
        lt = _normalize_lesson_type_to_canonical(lesson.lesson_type)
        if lt and lt in ('maruza', 'amaliyot', 'laboratoriya', 'seminar', 'kurs_ishi'):
            lesson_type_names_map = {'maruza': 'Maruza', 'amaliyot': 'Amaliyot', 'laboratoriya': 'Laboratoriya', 'seminar': 'Seminar', 'kurs_ishi': 'Kurs ishi'}
            if not any(a['value'] == lt for a in allowed_lesson_types):
                allowed_lesson_types.append({'value': lt, 'name': lesson_type_names_map.get(lt, lt.capitalize())})

    # Edit sahifasida joriy mavzu fayl(lar)ni ko'rsatish uchun ro'yxat
    lesson_files_list, current_file_urls = parse_lesson_file_data(lesson.file_url)

    if request.method == 'POST':
        old_video_file = lesson.video_file
        video_filename = lesson.video_file
        video_url = lesson.video_url
        lesson_file_url = lesson.file_url

        remove_video = request.form.get('remove_video') == '1'

        # Video fayl yuklash
        if 'video_file' in request.files:
            video = request.files['video_file']
            if video and video.filename and allowed_video(video.filename):
                ext = video.filename.rsplit('.', 1)[1].lower()
                video_filename = f"{uuid.uuid4().hex}.{ext}"
                video_path = os.path.join(current_app.config['UPLOAD_FOLDER'], 'videos', video_filename)
                video.save(video_path)
                video_url = None
                remove_video = False

        # Video URL faqat YouTube link bo'lishi kerak (kanonik ko'rinishda saqlanadi)
        video_url_input = request.form.get('video_url', '').strip()
        if video_url_input:
            video_id = extract_youtube_video_id(video_url_input)
            if not video_id:
                flash(t('invalid_request'), 'error')
                return render_template('courses/edit_lesson.html', lesson=lesson, subject=subject, direction_id=direction_id, group_id=group_id_param, allowed_lesson_types=allowed_lesson_types, lesson_files_list=lesson_files_list, current_file_urls=current_file_urls)
            video_url = f'https://www.youtube.com/watch?v={video_id}'
            video_filename = None
            remove_video = False
        elif remove_video:
            video_filename = None
            video_url = None

        # Eski video faylni faqat almashtirilsa yoki olib tashlansa o'chirish
        if old_video_file and old_video_file != video_filename:
            old_video_path = os.path.join(current_app.config['UPLOAD_FOLDER'], 'videos', old_video_file)
            if os.path.exists(old_video_path):
                try:
                    os.remove(old_video_path)
                except:
                    pass

        # Mavzu fayllari: eski fayllar/URL avtomatik o'chmasin, faqat "X" orqali olib tashlansin
        existing_uploaded_files, existing_urls = parse_lesson_file_data(lesson.file_url)

        keep_existing_files = set(request.form.getlist('keep_existing_files'))
        keep_existing_urls = set(request.form.getlist('keep_existing_urls'))

        kept_existing_files = [f for f in existing_uploaded_files if f.get('filename') in keep_existing_files]
        removed_existing_files = [f for f in existing_uploaded_files if f.get('filename') not in keep_existing_files]
        kept_existing_urls = [u for u in existing_urls if u in keep_existing_urls]

        lesson_files = request.files.getlist('lesson_files')
        uploaded_files = []
        allowed_extensions = {'pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'txt', 'zip', 'rar'}

        for lesson_file in lesson_files:
            if lesson_file and lesson_file.filename:
                ext = lesson_file.filename.rsplit('.', 1)[1].lower() if '.' in lesson_file.filename else ''
                if ext not in allowed_extensions:
                    flash(t('invalid_file_format', filename=lesson_file.filename), 'error')
                    return render_template('courses/edit_lesson.html', lesson=lesson, subject=subject, direction_id=direction_id, group_id=group_id_param, allowed_lesson_types=allowed_lesson_types, lesson_files_list=lesson_files_list, current_file_urls=current_file_urls)

                filename = f"{uuid.uuid4().hex}.{ext}"
                files_folder = os.path.join(current_app.config['UPLOAD_FOLDER'], 'lesson_files')
                os.makedirs(files_folder, exist_ok=True)
                lesson_file.save(os.path.join(files_folder, filename))
                uploaded_files.append({'filename': filename, 'original_name': lesson_file.filename})

        file_url_inputs = []
        for url_value in request.form.getlist('file_urls'):
            normalized = (url_value or '').strip()
            if normalized and normalized not in file_url_inputs:
                file_url_inputs.append(normalized)
        # Orqaga moslik: eski single input nomi
        legacy_file_url = request.form.get('file_url', '').strip()
        if legacy_file_url and legacy_file_url not in file_url_inputs:
            file_url_inputs.append(legacy_file_url)

        # Eski saqlangan URL(lar) + yangi qo'shilgan URL(lar)
        final_external_urls = list(kept_existing_urls)
        for url_value in file_url_inputs:
            if url_value not in final_external_urls:
                final_external_urls.append(url_value)

        final_uploaded_files = kept_existing_files + uploaded_files
        lesson_file_url = build_lesson_file_data(final_uploaded_files, final_external_urls)

        # X orqali olib tashlangan eski fayllarni diskdan o'chirish
        for removed_file in removed_existing_files:
            removed_filename = removed_file.get('filename')
            if not removed_filename:
                continue
            removed_path = os.path.join(current_app.config['UPLOAD_FOLDER'], 'lesson_files', removed_filename)
            if os.path.exists(removed_path):
                try:
                    os.remove(removed_path)
                except:
                    pass

        if (current_user.role == 'teacher' or current_user.role == 'admin') and not lesson_file_url:
            flash(t('all_required_fields'), 'error')
            return render_template('courses/edit_lesson.html', lesson=lesson, subject=subject, direction_id=direction_id, group_id=group_id_param, allowed_lesson_types=allowed_lesson_types, lesson_files_list=lesson_files_list, current_file_urls=current_file_urls)
        
        # Dars turini o'zgartirishdan oldin ruxsat tekshiruvi (o'qituvchi uchun)
        new_lesson_type = request.form.get('lesson_type', lesson.lesson_type)
        if new_lesson_type == 'maruza' and not (video_filename or video_url):
            flash(t('video_required_for_lecture'), 'error')
            return render_template('courses/edit_lesson.html', lesson=lesson, subject=subject, direction_id=direction_id, group_id=group_id_param, allowed_lesson_types=allowed_lesson_types, lesson_files_list=lesson_files_list, current_file_urls=current_file_urls)

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
                
                    pass # Error paths will fall through to the final render_template at the end of the function
                
                if not teacher_assignment:
                    flash(t('teacher_not_assigned_to_new_lesson_type', lesson_type=new_lesson_type), 'error')
        
        # Dars ma'lumotlarini yangilash
        lesson.title = request.form.get('title')
        lesson.content = request.form.get('content')
        lesson.video_url = video_url if video_url else None
        lesson.video_file = video_filename
        lesson.file_url = lesson_file_url
        lesson.duration = int(request.form.get('duration', 0) or 0)
        lesson.lesson_type = new_lesson_type
        
        db.session.commit()
        
        flash(t('lesson_updated'), 'success')
        if direction_id and group_id_param:
            return redirect(url_for('courses.detail', id=subject.id, dir_id=direction_id, group_id=group_id_param))
        return redirect(url_for('courses.detail', id=subject.id, dir_id=direction_id))
    
    return render_template('courses/edit_lesson.html', lesson=lesson, subject=subject, direction_id=direction_id, group_id=group_id_param, allowed_lesson_types=allowed_lesson_types, lesson_files_list=lesson_files_list, current_file_urls=current_file_urls)


@bp.route('/lessons/<int:id>/delete', methods=['POST'])
@login_required
def delete_lesson(id):
    """Darsni o'chirish"""
    lesson = Lesson.query.get_or_404(id)
    subject = lesson.subject
    
    # Yo'nalish va guruh ID
    direction_id = request.args.get('direction_id', type=int)
    group_id_param = request.args.get('group_id', type=int)
    
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
    if (current_user.role in ['admin', 'dean']) and current_role != 'teacher' and current_role != 'edu_dept':
        can_delete = True
    elif current_role == 'teacher' and is_teacher:
        # O'qituvchining fanga biriktirilganligini (guruh va dars turi bo'yicha) tekshirish
        
        # direction_id tekshiruvi (edit dagi kabi)
        if direction_id and lesson.direction_id and lesson.direction_id != direction_id:
            can_delete = False
        else:
            check_direction_id = direction_id or lesson.direction_id
            allowed_ts_types = _teacher_lesson_type_variants(lesson.lesson_type)
            
            if allowed_ts_types:
                lower_types = [t.lower() for t in allowed_ts_types]
                teacher_assignments_query = TeacherSubject.query.filter(
                    TeacherSubject.teacher_id == current_user.id,
                    TeacherSubject.subject_id == subject.id,
                    db.func.lower(TeacherSubject.lesson_type).in_(lower_types)
                )
            else:
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
        flash(t('no_permission_to_delete_lesson'), 'error')
        if direction_id and group_id_param:
            return redirect(url_for('courses.detail', id=subject.id, dir_id=direction_id, group_id=group_id_param))
        return redirect(url_for('courses.detail', id=subject.id, dir_id=direction_id))
    
    # Mavzuga biriktirilgan topshiriqlar borligini tekshirish
    assignments_with_lesson = Assignment.query.filter_by(subject_id=subject.id).all()
    linked_assignments = []
    for assignment in assignments_with_lesson:
        lesson_ids = assignment.get_lesson_ids_list() if hasattr(assignment, 'get_lesson_ids_list') else []
        if lesson.id in lesson_ids:
            linked_assignments.append(assignment.title)
    
    if linked_assignments:
        flash(t('lesson_cannot_delete_has_assignments', assignments_list=', '.join(linked_assignments)), 'error')
        if direction_id and group_id_param:
            return redirect(url_for('courses.detail', id=subject.id, dir_id=direction_id, group_id=group_id_param))
        return redirect(url_for('courses.detail', id=subject.id, dir_id=direction_id))
    
    # Video faylni o'chirish
    if lesson.video_file:
        video_path = os.path.join(current_app.config['UPLOAD_FOLDER'], 'videos', lesson.video_file)
        if os.path.exists(video_path):
            try:
                os.remove(video_path)
            except:
                pass
    
    # Yuklangan mavzu fayl(lar)ini o'chirish (external URL'lar o'chirilmaydi)
    uploaded_files, _ = parse_lesson_file_data(lesson.file_url)
    for file_item in uploaded_files:
        filename = file_item.get('filename')
        if not filename:
            continue
        file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], 'lesson_files', filename)
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except:
                pass
    
    # Darsni o'chirish
    subject_id = lesson.subject_id
    direction_id_val = lesson.direction_id
    group_id_val = lesson.group_id
    lesson_type_val = lesson.lesson_type
    
    db.session.delete(lesson)
    db.session.commit()
    
    # Qolgan darslarni tartiblash (global tartiblash)
    remaining_lessons_query = Lesson.query.filter_by(
        subject_id=subject_id,
        direction_id=direction_id_val
    )
    
    # Guruhlar bo'yicha ham tartiblaymiz (agar darslar ma'lum bir guruhga tegishli bo'lsa)
    remaining_lessons = remaining_lessons_query.order_by(Lesson.order).all()
    
    for i, l in enumerate(remaining_lessons, start=1):
        l.order = i
    
    db.session.commit()
    
    flash(t('lesson_deleted'), 'success')
    group_id_redirect = group_id_param or group_id_val
    if direction_id_val and group_id_redirect:
        return redirect(url_for('courses.detail', id=subject_id, dir_id=direction_id_val, group_id=group_id_redirect))
    return redirect(url_for('courses.detail', id=subject_id, dir_id=direction_id_val))


@bp.route('/uploads/videos/<filename>')
@login_required
def serve_video(filename):
    """Video faylni uzatish"""
    videos_folder = os.path.join(current_app.config['UPLOAD_FOLDER'], 'videos')
    download = request.args.get('download') == '1'
    return send_from_directory(videos_folder, filename, as_attachment=download)

@bp.route('/uploads/lesson_files/<filename>')
@login_required
def serve_lesson_file(filename):
    """Dars faylini uzatish"""
    files_folder = os.path.join(current_app.config['UPLOAD_FOLDER'], 'lesson_files')
    file_path = os.path.join(files_folder, filename)
    
    # Fayl mavjudligini tekshirish
    if not os.path.exists(file_path):
        flash(t('error_occurred', error='File not found'), 'error')
        return redirect(url_for('courses.index'))
    
    # Ruxsatni tekshirish
    # Lessonni qidirish (JSON formatini ham hisobga olgan holda)
    lesson = Lesson.query.filter(
        (Lesson.file_url == filename) | 
        (Lesson.file_url.like(f'%"{filename}"%'))
    ).first()
    
    if not lesson:
        # URL bo'lsa, to'g'ridan-to'g'ri qaytarish (masalan, e'lonlardagi fayllar yoki boshqa yerda)
        return send_from_directory(files_folder, filename, as_attachment=True)
    
    subject = lesson.subject
    
    # Ruxsatni tekshirish
    if current_user.role == 'student':
        # Qulflanganligini tekshirish
        is_locked = False
        if lesson.video_file or lesson.video_url:
            previous_lessons_query = Lesson.query.filter(
                Lesson.subject_id == lesson.subject_id,
                Lesson.lesson_type == lesson.lesson_type,
                Lesson.direction_id == lesson.direction_id,
                Lesson.order < lesson.order
            )
            if current_user.group_id:
                previous_lessons_query = previous_lessons_query.filter(
                    (Lesson.group_id == current_user.group_id) | (Lesson.group_id.is_(None))
                )
            previous_lessons = previous_lessons_query.order_by(Lesson.order).all()
            
            for prev_lesson in previous_lessons:
                if prev_lesson.video_file or prev_lesson.video_url:
                    view = LessonView.query.filter_by(
                        lesson_id=prev_lesson.id,
                        student_id=current_user.id
                    ).first()
                    if not view or not view.is_completed:
                        is_locked = True
                        break
        
        if is_locked:
            flash(t('no_permission_for_operation'), 'error')
            return redirect(url_for('courses.lesson_detail', id=lesson.id))

    return send_from_directory(files_folder, filename, as_attachment=True)

@bp.route('/uploads/submissions/<filename>')
@login_required
def serve_submission_file(filename):
    """Topshiriq faylini ko'rsatish"""
    submissions_folder = os.path.join(current_app.config['UPLOAD_FOLDER'], 'submissions')
    file_path = os.path.join(submissions_folder, filename)
    
    # Fayl mavjudligini tekshirish
    if not os.path.exists(file_path):
        flash(t('error_occurred', error='File not found'), 'error')
        return redirect(url_for('courses.index'))
    
    # Ruxsatni tekshirish - faqat fayl egasi yoki o'qituvchi ko'ra oladi
    submission = Submission.query.filter_by(file_url=filename).first()
    if not submission:
        flash(t('error_occurred', error='File not found'), 'error')
        return redirect(url_for('courses.index'))
    
    # Talaba o'z faylini ko'ra oladi
    if current_user.role == 'student' and submission.student_id != current_user.id:
        flash(t('no_permission_for_operation'), 'error')
        return redirect(url_for('courses.index'))
    
    # O'qituvchi o'z guruhlaridagi talabalarning fayllarini ko'ra oladi
    if current_user.role == 'teacher':
        assignment = submission.assignment
        has_permission = False
        if assignment.group_id:
            teaching = TeacherSubject.query.filter_by(
                teacher_id=current_user.id,
                subject_id=assignment.subject_id,
                group_id=assignment.group_id
            ).first()
            has_permission = teaching is not None
        elif assignment.direction_id and assignment.lesson_type:
            direction_group_ids = [g.id for g in Group.query.filter_by(direction_id=assignment.direction_id).all()]
            teacher_assignment = TeacherSubject.query.filter(
                TeacherSubject.teacher_id == current_user.id,
                TeacherSubject.subject_id == assignment.subject_id,
                TeacherSubject.group_id.in_(direction_group_ids),
                TeacherSubject.lesson_type == assignment.lesson_type
            ).first()
            if not teacher_assignment and assignment.lesson_type in ['laboratoriya', 'kurs_ishi']:
                teacher_assignment = TeacherSubject.query.filter(
                    TeacherSubject.teacher_id == current_user.id,
                    TeacherSubject.subject_id == assignment.subject_id,
                    TeacherSubject.group_id.in_(direction_group_ids),
                    TeacherSubject.lesson_type == 'amaliyot'
                ).first()
            has_permission = teacher_assignment is not None
        if not has_permission:
            flash(t('no_permission_for_operation'), 'error')
            return redirect(url_for('courses.index'))
    
    return send_from_directory(submissions_folder, filename, as_attachment=True)



@bp.route('/<int:subject_id>/<int:direction_id>/<int:group_id>/<int:semester>/<string:type_code>/<int:order>')
@login_required
def hierarchical_lesson_detail(subject_id, direction_id, group_id, semester, type_code, order):
    """Ierarxik dars tafsilotlari - URL /subjects/21/1/5/2/M/1 formatida. `order` – dars TURI bo'yicha tartib (1, 2, 3...), global order emas."""
    type_map = {
        'M': 'maruza',
        'A': 'amaliyot',
        'L': 'laboratoriya',
        'S': 'seminar',
        'K': 'kurs_ishi'
    }
    lesson_type = type_map.get(type_code.upper())
    if not lesson_type:
        from flask import abort
        abort(404)
    
    # Shu turdagi darslarni Lesson.order bo'yicha olish, keyin N-chi (order 1-based) ni tanlash
    lessons_of_type = Lesson.query.filter(
        Lesson.subject_id == subject_id,
        Lesson.lesson_type == lesson_type,
        (Lesson.group_id == group_id) | (Lesson.group_id.is_(None)),
        (Lesson.direction_id == direction_id) | (Lesson.direction_id.is_(None))
    ).order_by(Lesson.order).all()
    
    if order < 1 or order > len(lessons_of_type):
        from flask import abort
        abort(404)
    lesson = lessons_of_type[order - 1]
    
    return _render_lesson_detail(lesson, direction_id=direction_id, group_id=group_id)


@bp.route('/<int:subject_id>/<int:direction_id>/<int:group_id>/<string:type_code>/<int:order>')
@login_required
def hierarchical_lesson_detail_legacy(subject_id, direction_id, group_id, type_code, order):
    """Eski URL (semestersiz) – semestr bilan yangi URL ga yo'naltirish."""
    gr = Group.query.get(group_id)
    sem = (gr.semester if gr and gr.semester else 1)
    return redirect(url_for('courses.hierarchical_lesson_detail',
                           subject_id=subject_id, direction_id=direction_id, group_id=group_id,
                           semester=sem, type_code=type_code, order=order))


def _render_lesson_detail(lesson, direction_id=None, group_id=None):
    """Dars tafsilotlarini render qilish (hierarchical va lesson_detail uchun)"""
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
        flash(t('no_permission_to_view_lesson'), 'error')
        return redirect(url_for('courses.index'))
    
    # Talaba uchun ko'rish yozuvi va qulflanganligini tekshirish
    lesson_view = None
    is_locked = False
    if current_user.role == 'student':
        lesson_view = LessonView.query.filter_by(
            lesson_id=lesson.id,
            student_id=current_user.id
        ).first()
        
        # Agar ko'rish yozuvi bo'lmasa, yangi yaratish
        if not lesson_view:
            lesson_view = LessonView(
                lesson_id=lesson.id,
                student_id=current_user.id
            )
            db.session.add(lesson_view)
            db.session.commit()
        
        # Video yo'q, faqat fayl/material bo'lsa – sahifani ko'rganida avtomatik "tugallangan" deb belgilash
        # (Keyingi dars ochilishi uchun; tekshiruv faqat videoda mavjud)
        if not (lesson.video_file or lesson.video_url) and (lesson.file_url or lesson.content):
            if not lesson_view.is_completed:
                lesson_view.is_completed = True
                lesson_view.completed_at = datetime.utcnow()
                db.session.commit()
        
        # Oldingi darslar to'liq ko'rilganligini tekshirish (faqat videoga ega darslar uchun)
        if lesson.video_file or lesson.video_url:
            previous_lessons_query = Lesson.query.filter(
                Lesson.subject_id == subject.id,
                Lesson.lesson_type == lesson.lesson_type,
                Lesson.direction_id == lesson.direction_id,
                Lesson.order < lesson.order
            )
            if current_user.group_id:
                previous_lessons_query = previous_lessons_query.filter(
                    (Lesson.group_id == current_user.group_id) | (Lesson.group_id.is_(None))
                )
            previous_lessons = previous_lessons_query.order_by(Lesson.order).all()
            
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
    if (current_user.role in ['admin', 'dean', 'edu_dept']) and current_role != 'teacher':
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

    # Mavzu fayllari (ko'p fayllarni qo'llab-quvvatlash uchun)
    lesson_files_list, current_file_urls = parse_lesson_file_data(lesson.file_url)
    lesson_video_id = extract_youtube_video_id(lesson.video_url) if lesson.video_url else None
    
    return render_template('courses/lesson_detail.html', 
                         lesson=lesson, 
                         subject=subject, 
                         lesson_view=lesson_view, 
                         is_locked=is_locked,
                         can_edit_lesson=can_edit_lesson,
                         lesson_files_list=lesson_files_list,
                         current_file_urls=current_file_urls,
                         lesson_video_id=lesson_video_id,
                         direction_id=direction_id if direction_id is not None else (request.args.get('direction_id') or lesson.direction_id),
                         group_id=group_id or request.args.get('group_id', type=int))


@bp.route('/lessons/<int:id>')
@login_required
def lesson_detail(id):
    """Dars tafsilotlari (URL: /subjects/lessons/123)"""
    lesson = Lesson.query.get_or_404(id)
    return _render_lesson_detail(lesson)





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
            'url': url_for('courses.lesson_detail', id=next_lesson.id)
        }
    
    return jsonify(response)


@bp.route('/lessons/<int:id>/update-watch-time', methods=['POST'])
@login_required
def update_watch_time(id):
    """Ko'rish vaqtini yangilash API. Video ~90%+ ko'rilganda dars avtomatik tugallangan hisoblanadi (keyingi dars ochilishi uchun)."""
    if current_user.role != 'student':
        return jsonify({'success': False}), 403
    
    lesson_view = LessonView.query.filter_by(
        lesson_id=id,
        student_id=current_user.id
    ).first()
    
    if lesson_view:
        watch_duration = request.json.get('watch_duration', 0)
        lesson_view.watch_duration = max(lesson_view.watch_duration, watch_duration)
        
        # Video to'liq yoki deyarli to'liq ko'rilganda (90%+) darsni tugallangan deb belgilash – keyingi dars ochilishi uchun
        if not lesson_view.is_completed:
            lesson = Lesson.query.get(id)
            if lesson and (lesson.video_file or lesson.video_url):
                video_seconds = (lesson.duration or 0) * 60  # duration daqiqada
                if video_seconds > 0 and lesson_view.watch_duration >= 0.9 * video_seconds:
                    lesson_view.is_completed = True
                    lesson_view.completed_at = datetime.utcnow()
                    if lesson_view.attention_checks_passed < 3:
                        lesson_view.attention_checks_passed = 3
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'watch_duration': lesson_view.watch_duration,
            'is_completed': lesson_view.is_completed
        })
    
    return jsonify({'success': True, 'watch_duration': 0})


@bp.route('/<int:id>/tests/create', methods=['GET', 'POST'])
@login_required
def create_test(id):
    """Test yaratish – matn formatida savollar (=====, #, +++++)"""
    subject = Subject.query.get_or_404(id)
    direction_id = request.args.get('direction_id', type=int) or request.form.get('direction_id', type=int)
    group_id = request.args.get('group_id', type=int) or request.form.get('group_id', type=int)
    current_role = session.get('current_role', current_user.role)
    is_teacher = TeacherSubject.query.filter_by(teacher_id=current_user.id, subject_id=subject.id).first() is not None
    has_admin_dean = current_role in ['admin', 'dean', 'edu_dept'] and (current_user.has_role('admin') or current_user.has_role('dean') or current_user.has_role('edu_dept') or getattr(current_user, 'is_superadmin', False))
    if not is_teacher and not has_admin_dean:
        flash(t('no_permission_for_operation'), 'error')
        return redirect(url_for('courses.detail', id=id, dir_id=direction_id, group_id=group_id))

    if request.method == 'POST':
        from app.utils.test_parser import parse_test_content
        title = request.form.get('title', '').strip()
        content = request.form.get('content', '').strip()
        if not title:
            flash(t('enter_title_please'), 'error')
            return render_template('courses/create_test.html', subject=subject, direction_id=direction_id, group_id=group_id, content=content, title=title)
        questions_data = parse_test_content(content)
        if not questions_data:
            flash(t('enter_test_questions_please'), 'error')
            return render_template('courses/create_test.html', subject=subject, direction_id=direction_id, group_id=group_id, content=content, title=title)

        test = Test(
            title=title,
            subject_id=subject.id,
            direction_id=direction_id,
            group_id=group_id,
            created_by=current_user.id
        )
        db.session.add(test)
        db.session.flush()
        for i, qd in enumerate(questions_data):
            q = TestQuestion(test_id=test.id, text=qd['question'], order=i + 1)
            db.session.add(q)
            db.session.flush()
            for j, opt in enumerate(qd['options']):
                o = TestOption(question_id=q.id, text=opt['text'], is_correct=opt['correct'], order=j + 1)
                db.session.add(o)
        db.session.commit()
        flash(t('test_created_success'), 'success')
        return redirect(url_for('courses.detail', id=id, dir_id=direction_id, group_id=group_id))

    return render_template('courses/create_test.html', subject=subject, direction_id=direction_id, group_id=group_id)


@bp.route('/tests/<int:id>', methods=['GET', 'POST'])
@login_required
def take_test(id):
    """Test yechish – talabalar uchun"""
    test = Test.query.get_or_404(id)
    subject = test.subject
    direction_id = test.direction_id
    group_id = test.group_id

    # Ruxsat: talaba, o'qituvchi yoki admin
    current_role = session.get('current_role', current_user.role)
    is_student = current_user.role == 'student'
    is_teacher = TeacherSubject.query.filter_by(teacher_id=current_user.id, subject_id=subject.id).first() is not None
    has_admin_dean = current_role in ['admin', 'dean', 'edu_dept'] and (current_user.has_role('admin') or current_user.has_role('dean') or current_user.has_role('edu_dept') or getattr(current_user, 'is_superadmin', False))

    if not (is_student or is_teacher or has_admin_dean):
        flash(t('no_permission_for_operation'), 'error')
        return redirect(url_for('courses.detail', id=subject.id, dir_id=direction_id, group_id=group_id))

    if request.method == 'POST' and is_student:
        answers = {}
        for key in request.form:
            if key.startswith('q_') and key[2:].isdigit():
                qid = int(key[2:])
                vals = request.form.getlist(key)
                try:
                    answers[qid] = [int(v) for v in vals if v]
                except (ValueError, TypeError):
                    answers[qid] = []
        answers_json = json.dumps(answers)

        # Ball hisoblash (birnechta to'g'ri javob – tanlangan va to'g'ri variantlar to'plami mos bo'lishi kerak)
        correct_count = 0
        total_questions = 0
        for q in test.questions.order_by(TestQuestion.order).all():
            total_questions += 1
            correct_ids = set(o.id for o in q.options if o.is_correct)
            selected_ids = set(answers.get(q.id, []))
            if correct_ids == selected_ids:
                correct_count += 1
        max_score = test.max_score or 100.0
        score = (correct_count / total_questions * max_score) if total_questions else 0

        sub = TestSubmission(test_id=test.id, student_id=current_user.id, score=score, answers_json=answers_json)
        db.session.add(sub)
        db.session.commit()
        flash(t('test_submitted_success'), 'success')
        return redirect(url_for('courses.detail', id=subject.id, dir_id=direction_id, group_id=group_id))

    questions = list(test.questions.order_by(TestQuestion.order).all())
    random.shuffle(questions)
    for q in questions:
        opts = list(q.options)
        random.shuffle(opts)
        q.display_options = opts
    return render_template('courses/take_test.html', test=test, subject=subject, questions=questions,
                          direction_id=direction_id, group_id=group_id)


@bp.route('/<int:id>/assignments/create', methods=['GET', 'POST'])
@login_required
def create_assignment(id):
    """Yangi topshiriq yaratish"""
    subject = Subject.query.get_or_404(id)
    
    # Yo'nalish va guruh ID (query parametrdan)
    direction_id = request.args.get('direction_id', type=int)
    group_id_param = request.args.get('group_id', type=int)
    
    # Tanlangan rol
    current_role = session.get('current_role', current_user.role)
    if current_role == 'edu_dept':
        flash(t('no_permission_for_operation'), 'error')
        return redirect(url_for('courses.detail', id=id, dir_id=direction_id, group_id=group_id_param))
    is_acting_as_teacher = (current_role == 'teacher') or (current_user.role == 'teacher')
    
    # O'qituvchiga biriktirilgan dars turlarini topish; faqat o'quv rejada soati bor turlar
    allowed_lesson_types = []
    lesson_type_names_map = {
        'maruza': 'Maruza',
        'amaliyot': 'Amaliyot',
        'laboratoriya': 'Laboratoriya',
        'seminar': 'Seminar',
        'kurs_ishi': 'Kurs ishi'
    }
    lesson_type_order = ['maruza', 'amaliyot', 'laboratoriya', 'seminar', 'kurs_ishi']
    
    if is_acting_as_teacher:
        lesson_types_set = set()
        curriculum_lesson_types = set()
        
        if direction_id:
            direction_group_ids = [g.id for g in Group.query.filter_by(direction_id=direction_id).all()]
            groups_without_direction = [g.id for g in Group.query.filter(Group.direction_id.is_(None)).all()]
            allowed_group_ids = direction_group_ids + groups_without_direction
            teacher_assignments = TeacherSubject.query.filter(
                TeacherSubject.teacher_id == current_user.id,
                TeacherSubject.subject_id == subject.id,
                TeacherSubject.group_id.in_(allowed_group_ids)
            ).all()
            for ta in teacher_assignments:
                if ta.lesson_type:
                    canonical = _normalize_lesson_type_to_canonical(ta.lesson_type)
                    if canonical:
                        lesson_types_set.add(canonical)
            
            context_group = Group.query.get(group_id_param) if group_id_param else None
            if not context_group and direction_group_ids:
                context_group = Group.query.get(direction_group_ids[0])
            curr_query = DirectionCurriculum.query.filter_by(
                direction_id=direction_id,
                subject_id=subject.id
            )
            if context_group and context_group.semester:
                curr_query = curr_query.filter_by(semester=context_group.semester)
            curriculum_item = DirectionCurriculum.filter_by_group_context(curr_query, context_group).first() if context_group else curr_query.first()
            if curriculum_item:
                if (curriculum_item.hours_maruza or 0) > 0:
                    curriculum_lesson_types.add('maruza')
                if (curriculum_item.hours_amaliyot or 0) > 0:
                    curriculum_lesson_types.add('amaliyot')
                if (curriculum_item.hours_laboratoriya or 0) > 0:
                    curriculum_lesson_types.add('laboratoriya')
                if (curriculum_item.hours_seminar or 0) > 0:
                    curriculum_lesson_types.add('seminar')
                if (curriculum_item.hours_kurs_ishi or 0) > 0:
                    curriculum_lesson_types.add('kurs_ishi')
                
                if curriculum_lesson_types:
                    lesson_types_set &= curriculum_lesson_types
                
                has_lab_hours = (curriculum_item.hours_laboratoriya or 0) > 0
                has_amal_hours = (curriculum_item.hours_amaliyot or 0) > 0
                lab_teacher_assignment = TeacherSubject.query.filter(
                    TeacherSubject.subject_id == subject.id,
                    TeacherSubject.group_id.in_(allowed_group_ids),
                    TeacherSubject.teacher_id == current_user.id,
                    db.func.lower(TeacherSubject.lesson_type).in_(['laboratoriya', 'amaliyot', 'lab', 'amal'])
                ).first()
                if lab_teacher_assignment and (has_lab_hours or has_amal_hours):
                    lesson_types_set.add('laboratoriya')
                if (curriculum_item.hours_kurs_ishi or 0) > 0:
                    kurs_teacher_assignment = TeacherSubject.query.filter(
                        TeacherSubject.subject_id == subject.id,
                        TeacherSubject.group_id.in_(allowed_group_ids),
                        TeacherSubject.teacher_id == current_user.id,
                        db.func.lower(TeacherSubject.lesson_type).in_(['kurs_ishi', 'amaliyot', 'kurs'])
                    ).first()
                    if kurs_teacher_assignment:
                        lesson_types_set.add('kurs_ishi')
        
        for lesson_type_key in lesson_type_order:
            if lesson_type_key in lesson_types_set:
                allowed_lesson_types.append({
                    'value': lesson_type_key,
                    'name': lesson_type_names_map.get(lesson_type_key, lesson_type_key.capitalize())
                })
    else:
        # Admin/dekan: yo'nalish bo'lsa faqat o'quv rejadagi dars turlari
        if current_user.role in ['admin', 'dean', 'edu_dept'] and current_role != 'teacher' and direction_id:
            direction_groups_for_curr = Group.query.filter_by(direction_id=direction_id).all()
            context_group = Group.query.get(group_id_param) if group_id_param else None
            if not context_group and direction_groups_for_curr:
                context_group = direction_groups_for_curr[0]
            curr_query = DirectionCurriculum.query.filter_by(
                direction_id=direction_id,
                subject_id=subject.id
            )
            if context_group and context_group.semester:
                curr_query = curr_query.filter_by(semester=context_group.semester)
            curriculum_item = DirectionCurriculum.filter_by_group_context(curr_query, context_group).first() if context_group else curr_query.first()
            if curriculum_item:
                if (curriculum_item.hours_maruza or 0) > 0:
                    allowed_lesson_types.append({'value': 'maruza', 'name': 'Maruza'})
                if (curriculum_item.hours_amaliyot or 0) > 0:
                    allowed_lesson_types.append({'value': 'amaliyot', 'name': 'Amaliyot'})
                if (curriculum_item.hours_laboratoriya or 0) > 0:
                    allowed_lesson_types.append({'value': 'laboratoriya', 'name': 'Laboratoriya'})
                if (curriculum_item.hours_seminar or 0) > 0:
                    allowed_lesson_types.append({'value': 'seminar', 'name': 'Seminar'})
                if (curriculum_item.hours_kurs_ishi or 0) > 0:
                    allowed_lesson_types.append({'value': 'kurs_ishi', 'name': 'Kurs ishi'})
            if not allowed_lesson_types:
                allowed_lesson_types = [
                    {'value': 'maruza', 'name': 'Maruza'},
                    {'value': 'amaliyot', 'name': 'Amaliyot'},
                    {'value': 'laboratoriya', 'name': 'Laboratoriya'},
                    {'value': 'seminar', 'name': 'Seminar'},
                    {'value': 'kurs_ishi', 'name': 'Kurs ishi'}
                ]
        elif current_user.role == 'admin' and current_role != 'teacher':
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
    
    # Darslar (mavzular) ro'yxati — har bir dars turi ichida tartib raqami 1, 2, 3...
    lessons = []
    if direction_id:
        raw_lessons = Lesson.query.filter_by(
            subject_id=subject.id,
            direction_id=direction_id
        ).order_by(Lesson.order).all()
        type_counters = defaultdict(int)
        for lesson in raw_lessons:
            type_counters[lesson.lesson_type or ''] += 1
            lesson.display_order_in_type = type_counters[lesson.lesson_type or '']
        lessons = raw_lessons
    
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
            flash(t('no_permission_to_edit_assignment'), 'error')
            if direction_id and group_id_param:
                return redirect(url_for('courses.detail', id=id, dir_id=direction_id, group_id=group_id_param))
            return redirect(url_for('courses.detail', id=id, dir_id=direction_id))
    
    if request.method == 'POST':
        # Dars turi majburiy
        selected_lesson_type = request.form.get('lesson_type', '').strip()
        if not selected_lesson_type:
            flash(t('all_required_fields'), 'error')
            return render_template('courses/create_assignment.html', subject=subject, groups=groups, direction_id=direction_id, group_id=group_id_param, allowed_lesson_types=allowed_lesson_types, lessons=lessons, scale_max=GradeScale.get_scale_max())
        
        # O'qituvchi uchun tanlangan dars turini tekshirish
        if is_acting_as_teacher:
            allowed_values = [lt['value'] for lt in allowed_lesson_types]
            if selected_lesson_type not in allowed_values:
                flash(t('teacher_not_assigned_to_assignment_lesson_type'), 'error')
                return render_template('courses/create_assignment.html', subject=subject, groups=groups, direction_id=direction_id, group_id=group_id_param, allowed_lesson_types=allowed_lesson_types, lessons=lessons, scale_max=GradeScale.get_scale_max())
        
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
            flash(t('invalid_request'), 'error')
            return render_template('courses/create_assignment.html', subject=subject, groups=groups, direction_id=direction_id, group_id=group_id_param, allowed_lesson_types=allowed_lesson_types, lessons=lessons, scale_max=GradeScale.get_scale_max())
        
        # Yo'nalish bo'yicha birlashtirish (One Assignment per Direction)
        if direction_id:
            # Agar direction_id bo'lsa, faqat bitta topshiriq yaratiladi (group_id = None)
            scale_max = GradeScale.get_scale_max()
            assignment = Assignment(
                title=request.form.get('title'),
                description=request.form.get('description'),
                max_score=scale_max,
                due_date=due_date,
                subject_id=id,
                group_id=None,  # Yo'nalish darajasidagi topshiriq
                direction_id=direction_id,
                lesson_type=selected_lesson_type,
                lesson_ids=lesson_ids_json,
                file_required=bool(request.form.get('file_required')),
                created_by=current_user.id
            )
            db.session.add(assignment)
            created_count = 1
        else:
            scale_max = GradeScale.get_scale_max()
            # direction_id bo'lmasa, guruhlar uchun alohida yaratish
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
                    max_score=scale_max,
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
            flash(t('assignment_created_for_groups', created_count=created_count), 'success')
        else:
            flash(t('error_occurred', error=''), 'error')
        
        if direction_id and group_id_param:
            return redirect(url_for('courses.detail', id=id, dir_id=direction_id, group_id=group_id_param))
        return redirect(url_for('courses.detail', id=id, dir_id=direction_id))
    
    return render_template('courses/create_assignment.html', subject=subject, groups=groups, direction_id=direction_id, group_id=group_id_param, allowed_lesson_types=allowed_lesson_types, lessons=lessons, scale_max=GradeScale.get_scale_max())


@bp.route('/assignments/<int:id>')
@login_required
def assignment_detail(id):
    """Topshiriq tafsilotlari"""
    assignment = Assignment.query.get_or_404(id)
    subject = assignment.subject
    
    # O'qituvchi yoki adminmi? Guruh darajasidagi topshiriqda – shu guruhga biriktirilgan; yo'nalish darajasida (group_id None) – shu yo'nalishdagi istalgan guruhga biriktirilgan bo'lsa ko'ra oladi
    is_teacher = False
    if assignment.group_id is not None:
        is_teacher = TeacherSubject.query.filter_by(
            teacher_id=current_user.id,
            subject_id=subject.id,
            group_id=assignment.group_id
        ).first() is not None
    else:
        # Yo'nalish darajasidagi topshiriq – o'qituvchi shu yo'nalishdagi biror guruhga biriktirilgan bo'lsa ko'ra oladi
        if assignment.direction_id:
            direction_group_ids = [g.id for g in Group.query.filter_by(direction_id=assignment.direction_id).all()]
            is_teacher = TeacherSubject.query.filter(
                TeacherSubject.teacher_id == current_user.id,
                TeacherSubject.subject_id == subject.id,
                TeacherSubject.group_id.in_(direction_group_ids)
            ).first() is not None
    
    current_role = session.get('current_role', current_user.role)
    is_edu_dept_or_dean_view = current_role in ['edu_dept', 'dean'] and (
        current_user.role in ['admin', 'dean', 'edu_dept'] or
        current_user.has_role('admin') or current_user.has_role('dean') or current_user.has_role('edu_dept') or
        getattr(current_user, 'is_superadmin', False)
    )
    
    if is_teacher or current_user.role == 'admin' or is_edu_dept_or_dean_view:
        # Barcha submissions (history uchun)
        all_assignment_submissions = assignment.submissions.order_by(Submission.submitted_at.asc()).all()
        
        # Faol submissions (table uchun) – alifbo tartibida
        submissions = sorted(
            [s for s in all_assignment_submissions if s.is_active],
            key=lambda s: (s.student.full_name or '').upper()
        )
        
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
        if current_role == 'edu_dept':
            # O'quv bo'limi javoblarni ko'ra oladi, baholash mumkin emas
            can_manage_assignment = False
            for sub in submissions:
                can_grade_submissions[sub.id] = False
        elif current_user.role == 'admin':
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
        
        # Guruh talabalari – faqat o'qituvchi biriktirilgan va faol (talabasi bor) guruhlar
        teacher_group_ids = None
        if current_role == 'edu_dept':
            pass  # O'quv bo'limi barcha guruhlarni ko'radi (admin kabi)
        elif current_user.role != 'admin':
            ts_list = TeacherSubject.query.filter_by(
                teacher_id=current_user.id,
                subject_id=subject.id
            ).all()
            teacher_group_ids = list({ts.group_id for ts in ts_list if ts.group_id})
            # Faqat talabasi bor guruhlar
            teacher_group_ids = [gid for gid in teacher_group_ids
                                if Group.query.get(gid) and Group.query.get(gid).get_students_count() > 0]

        if assignment.group_id is not None:
            group_students = User.query.filter_by(role='student', group_id=assignment.group_id).order_by(User.full_name.asc()).all()
            grp = assignment.group
            is_active = grp and grp.get_students_count() > 0
            # O'qituvchi uchun: faqat o'zi biriktirilgan guruh bo'lsa ko'rsatish
            if teacher_group_ids is not None and assignment.group_id not in teacher_group_ids:
                assignment_groups = []
                group_students = []
            # Faqat faol guruhlar – admin uchun ham
            elif not is_active:
                assignment_groups = []
                group_students = []
            else:
                assignment_groups = [grp] if grp else []
        else:
            # Yo'nalish darajasidagi topshiriq
            if assignment.direction_id:
                direction_groups = Group.query.filter_by(direction_id=assignment.direction_id).all()
                # Faqat faol guruhlar (talabasi bor) – admin va o'qituvchi uchun
                active_group_ids = [g.id for g in direction_groups if g.get_students_count() > 0]
                # O'qituvchi uchun: faqat o'zi biriktirilgan guruhlar
                if teacher_group_ids is not None:
                    allowed_group_ids = [gid for gid in teacher_group_ids if gid in active_group_ids]
                else:
                    allowed_group_ids = active_group_ids
                group_students = User.query.filter(
                    User.role == 'student',
                    User.group_id.in_(allowed_group_ids)
                ).order_by(User.full_name.asc()).all() if allowed_group_ids else []
                if allowed_group_ids:
                    groups_raw = Group.query.filter(Group.id.in_(list(set(allowed_group_ids)))).order_by(Group.name).all()
                    # Bir xil nomli guruhlarni takrorlamaslik
                    seen_names = set()
                    assignment_groups = []
                    for g in groups_raw:
                        name_key = (g.name or '').strip().upper()
                        if name_key and name_key not in seen_names:
                            seen_names.add(name_key)
                            assignment_groups.append(g)
                else:
                    assignment_groups = []
            else:
                group_students = []
                assignment_groups = []
        
        # Topshirmagan talabalar – alifbo tartibida (group_students allaqachon tartiblangan)
        submitted_ids = [s.student_id for s in submissions]
        not_submitted = sorted(
            [s for s in group_students if s.id not in submitted_ids],
            key=lambda s: (s.full_name or '').upper()
        )
        
        # Tegishli mavzular – dars turi bo'yicha tartib raqamini hisoblash
        lesson_ids = assignment.get_lesson_ids_list() if assignment.lesson_ids else []
        related_lessons = []
        if lesson_ids:
            related_lessons = Lesson.query.filter(Lesson.id.in_(lesson_ids)).all()
            dir_id = assignment.direction_id or (assignment.group.direction_id if assignment.group else None)
            if related_lessons and dir_id:
                _compute_display_order_in_type_for_lessons(related_lessons, assignment.subject_id, dir_id, group=assignment.group)
                related_lessons = sorted(related_lessons, key=lambda l: ((l.lesson_type or ''), getattr(l, 'display_order_in_type', l.order or 0)))
        
        # Har bir talaba uchun eng yuqori ballni hisoblash
        student_highest_scores = {}
        for student_id, history in submission_history.items():
            scores = [h.score for h in history if h.score is not None]
            student_highest_scores[student_id] = max(scores) if scores else 0

        # Mavzu havolalari uchun: group_id va semester (/subjects/id/dir_id/group_id/semester/TYPE/order)
        _gr = assignment.group
        _dir_first = Group.query.filter_by(direction_id=assignment.direction_id).first() if assignment.direction_id else None
        _assignment_group_id = assignment.group_id or (_dir_first.id if _dir_first else None)
        _assignment_semester = (_gr.semester if _gr and _gr.semester else None) or (_dir_first.semester if _dir_first and _dir_first.semester else None) or 1

        return render_template('courses/assignment_submissions.html',
                             assignment=assignment,
                             submissions=submissions,
                             not_submitted=not_submitted,
                             assignment_groups=assignment_groups,
                             total_submissions=total_submissions,
                             ungraded_count=ungraded_count,
                             can_grade_submissions=can_grade_submissions,
                             can_manage_assignment=can_manage_assignment,
                             related_lessons=related_lessons,
                             submission_history=submission_history,
                             student_highest_scores=student_highest_scores,
                             direction_id=assignment.direction_id,
                             assignment_group_id=_assignment_group_id,
                             assignment_semester=_assignment_semester)

    else:
        # Talaba uchun – topshiriqni ko'rish/topshirish huquqini tekshirish
        if not student_can_access_assignment(assignment, current_user):
            flash(t('no_permission_to_view_assignment'), 'error')
            return redirect(url_for('courses.index'))

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
        waiting_for_grade = False  # Baholanmagan javob bor – keyingi yuborish bloklangan
        if submission:
            resubmission_count = submission.resubmission_count
            can_resubmit = submission.can_resubmit(max_resubmissions=3)
            if submission.score is None:
                waiting_for_grade = True
            
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
        
        # Tegishli mavzular – dars turi bo'yicha tartib raqamini hisoblash
        lesson_ids = assignment.get_lesson_ids_list() if assignment.lesson_ids else []
        related_lessons = []
        if lesson_ids:
            related_lessons = Lesson.query.filter(Lesson.id.in_(lesson_ids)).all()
            dir_id = assignment.direction_id or (assignment.group.direction_id if assignment.group else None) or (related_lessons[0].direction_id if related_lessons else None)
            if related_lessons and dir_id:
                _compute_display_order_in_type_for_lessons(related_lessons, assignment.subject_id, dir_id, group=assignment.group)
                related_lessons = sorted(related_lessons, key=lambda l: ((l.lesson_type or ''), getattr(l, 'display_order_in_type', l.order or 0)))
        
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

        # Mavzu havolalari uchun: group_id va semester (/subjects/id/dir_id/group_id/semester/TYPE/order)
        _gr = assignment.group
        _dir_first = Group.query.filter_by(direction_id=assignment.direction_id).first() if assignment.direction_id else None
        _assignment_group_id = assignment.group_id or (_dir_first.id if _dir_first else None)
        _assignment_semester = (_gr.semester if _gr and _gr.semester else None) or (_dir_first.semester if _dir_first and _dir_first.semester else None) or 1

        return render_template('courses/assignment_detail.html',
                             assignment=assignment,
                             submission=submission,
                             student_submissions=student_submissions,
                             highest_score=highest_score,
                             remaining_attempts=remaining_attempts,
                             can_resubmit=can_resubmit,
                             resubmission_count=resubmission_count,
                             waiting_for_grade=waiting_for_grade,
                             is_overdue=is_overdue,
                             related_lessons=related_lessons,
                             total_submissions=total_submissions,
                             ungraded_count=ungraded_count,
                             is_viewer_teacher=is_viewer_teacher,
                             can_manage_assignment=can_manage_assignment,
                             direction_id=assignment.direction_id,
                             assignment_group_id=_assignment_group_id,
                             assignment_semester=_assignment_semester)


@bp.route('/assignments/<int:id>/submit', methods=['POST'])
@login_required
def submit_assignment(id):
    """Topshiriq topshirish"""
    if current_user.role != 'student':
        flash(t('no_permission_for_operation'), 'error')
        return redirect(url_for('courses.assignment_detail', id=id))
    
    assignment = Assignment.query.get_or_404(id)
    
    # Talaba topshiriqni topshirish huquqiga egami?
    if not student_can_access_assignment(assignment, current_user):
        flash(t('no_permission_to_view_assignment'), 'error')
        return redirect(url_for('courses.index'))
    
    content = request.form.get('content', '').strip()
    file_url = None
    
    # Fayl yuklash
    if 'file' in request.files:
        file = request.files['file']
        if file and file.filename:
            # Fayl formatini tekshirish
            if not allowed_submission_file(file.filename):
                flash(t('invalid_file_format', filename=file.filename if file and file.filename else ''), 'error')
                return redirect(url_for('courses.assignment_detail', id=id))
            
            # Fayl hajmini tekshirish (2 MB)
            file.seek(0, os.SEEK_END)
            file_size = file.tell()
            file.seek(0)
            
            max_size = current_app.config.get('MAX_SUBMISSION_SIZE', 2 * 1024 * 1024)
            if file_size > max_size:
                flash(t('file_size_limit', max_size=int(max_size / (1024 * 1024))), 'error')
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
        flash(t('all_required_fields'), 'error')
        return redirect(url_for('courses.assignment_detail', id=id))
    
    # Agar na content, na file bo'lmasa
    if not content and not file_url:
        flash(t('submission_text_required'), 'error')
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
            flash(t('no_permission_for_operation'), 'error')
            return redirect(url_for('courses.assignment_detail', id=id))
    
    # Faol submission topish (oxirgi yuborilgan)
    active_submission = Submission.query.filter_by(
        student_id=current_user.id,
        assignment_id=id,
        is_active=True
    ).first()
    
    # O'qituvchi baholaguniga qadar keyingi javob yuborish mumkin emas
    if active_submission and active_submission.score is None:
        flash(t('submission_wait_for_grade'), 'error')
        return redirect(url_for('courses.assignment_detail', id=id))
    
    if active_submission:
        # Qayta topshirish imkoniyati tekshiruvi
        if not active_submission.can_resubmit(max_resubmissions=3):
            flash(t('no_permission_for_operation'), 'error')
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
        flash(t('submission_resubmitted', resubmission_count=new_submission.resubmission_count), 'success')
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
        flash(t('submission_submitted'), 'success')
    
    db.session.commit()
    return redirect(url_for('courses.assignment_detail', id=id))


@bp.route('/submissions/<int:id>/edit', methods=['POST'])
@login_required
def edit_submission(id):
    """Javobni tahrirlash (faqat baholanmagan bo'sa)"""
    submission = Submission.query.get_or_404(id)
    
    if submission.student_id != current_user.id:
        flash(t('no_permission_to_edit_submission'), 'error')
        return redirect(url_for('courses.assignment_detail', id=submission.assignment_id))
    
    if submission.score is not None:
        flash(t('no_permission_to_edit_submission'), 'error')
        return redirect(url_for('courses.assignment_detail', id=submission.assignment_id))
    
    content = request.form.get('content', '').strip()
    file_url = submission.file_url
    
    # Fayl yangilash
    if 'file' in request.files:
        file = request.files['file']
        if file and file.filename:
            if not allowed_submission_file(file.filename):
                flash(t('invalid_file_format', filename=''), 'error')
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
        flash(t('submission_text_required'), 'error')
        return redirect(url_for('courses.assignment_detail', id=submission.assignment_id))
    
    submission.content = content
    submission.file_url = file_url
    db.session.commit()
    
    flash(t('submission_updated'), 'success')
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
        flash(t('no_permission_for_operation'), 'error')
        return redirect(url_for('courses.assignment_detail', id=assignment.id))
    
    # Qayta topshirish imkonini berish
    submission.allow_resubmission = True
    db.session.commit()
    
    flash(t('no_permission_for_operation'), 'success')  # Note: Resubmission allowed - may need new translation key
    return redirect(url_for('courses.assignment_detail', id=assignment.id))


@bp.route('/submissions/<int:id>/grade', methods=['POST'])
@login_required
def grade_submission(id):
    """Bahoni qo'yish"""
    submission = Submission.query.get_or_404(id)
    assignment = submission.assignment
    subject = assignment.subject
    
    current_role = session.get('current_role', current_user.role)
    if current_role == 'edu_dept':
        flash(t('no_permission_for_operation'), 'error')
        return redirect(url_for('courses.assignment_detail', id=assignment.id))
    
    # Admin uchun ruxsat tekshiruvi
    if current_user.role == 'admin':
        # Baholash
        try:
            score_val = request.form.get('score', '0')
            submission.score = float(score_val)
        except ValueError:
            submission.score = 0.0
        submission.feedback = request.form.get('feedback')
        submission.graded_at = datetime.utcnow()
        submission.graded_by = current_user.id
        db.session.commit()
        flash(t('grade_assigned'), 'success')
        return redirect(url_for('courses.assignment_detail', id=assignment.id))
    
    # O'qituvchi uchun - yo'nalish va dars turi bo'yicha tekshiruv
    if not assignment.direction_id or not assignment.lesson_type:
        flash(t('invalid_request'), 'error')
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
        flash(t('teacher_not_assigned_for_grading', lesson_type=assignment.lesson_type), 'error')
        return redirect(url_for('courses.assignment_detail', id=assignment.id))
    
    # Baholash
    try:
        score_val = request.form.get('score', '0')
        submission.score = float(score_val)
    except ValueError:
        submission.score = 0.0
    submission.feedback = request.form.get('feedback')
    submission.graded_at = datetime.utcnow()
    submission.graded_by = current_user.id
    db.session.commit()
    
    flash(t('grade_assigned'), 'success')
    return redirect(url_for('courses.assignment_detail', id=assignment.id))


@bp.route('/grades')
@login_required
def grades():
    """Baholar"""
    if current_user.role == 'student':
        # Talabaning guruhi, yo'nalishi va joriy semestrini aniqlash
        group = Group.query.get(current_user.group_id) if current_user.group_id else None
        direction_id = group.direction_id if group else None
        current_semester = current_user.semester
        if group and group.direction:
            current_semester = group.semester
        
        # Talabaning yo'nalishi va joriy semestri bo'yicha barcha fanlarini olish
        # Faqat yo'nalish o'quv rejasiga (DirectionCurriculum) biriktirilgan fanlar
        all_subjects = []
        if direction_id and group:
            # DirectionCurriculum orqali faqat joriy semestr, qabul yili va ta'lim shakli bo'yicha fanlarni olish
            curriculum_query = DirectionCurriculum.query.filter_by(
                direction_id=direction_id,
                semester=current_semester
            )
            curriculum_query = DirectionCurriculum.filter_by_group_context(curriculum_query, group)
            curriculum_items = curriculum_query.all()
            subject_ids = [item.subject_id for item in curriculum_items]
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
        # Faqat yo'nalish o'quv rejasidagi fanlarni ko'rsatamiz (allowed_subject_ids)
        for assignment in all_assignments:
            subject = assignment.subject
            if subject.id not in allowed_subject_ids:
                continue  # Yo'nalishga biriktirilmagan fan - o'tkazib yuboramiz
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
        scale_max = GradeScale.get_scale_max()
        for data in grades_by_subject.values():
            data['percent'] = (data['total_score'] / data['max_score']) * scale_max if data['max_score'] > 0 else 0
            data['grade'] = GradeScale.get_grade(data['percent'], 100)
        
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
        overall_percent = (total_score / max_score) * scale_max if max_score > 0 else 0
        overall_grade = GradeScale.get_grade(overall_percent, 100)
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
            max_score=max_score,
            scale_max=scale_max
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
    
    if not is_teacher and current_user.role not in ['admin', 'dean', 'edu_dept']:
        flash(t('no_permission_for_operation'), 'error')
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
    
    scale_max = GradeScale.get_scale_max()
    return render_template('courses/group_grades.html',
                         subject=subject,
                         group=group,
                         students=students,
                         assignments=assignments,
                         student_grades=student_grades,
                         scale_max=scale_max)


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
    if not is_teacher and current_user.role not in ['admin', 'dean', 'edu_dept']:
        flash(t('no_permission_for_operation'), 'error')
        return redirect(url_for('courses.group_grades', subject_id=subject_id, group_id=group_id))
    
    assignments = Assignment.query.filter_by(subject_id=subject_id, group_id=group_id).all()
    # Baholanmagan javob bo'lsa eksport qilish mumkin emas
    if assignments:
        assignment_ids = [a.id for a in assignments]
        ungraded = Submission.query.filter(
            Submission.assignment_id.in_(assignment_ids),
            Submission.score.is_(None)
        ).limit(1).first()
        if ungraded:
            flash(t('export_ungraded_blocked'), 'error')
            return redirect(url_for('courses.group_grades', subject_id=subject_id, group_id=group_id))
    
    # Ma'lumotlarni tayyorlash
    students = User.query.filter_by(role='student', group_id=group_id).order_by(User.full_name).all()
    
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
        scale_max = GradeScale.get_scale_max()
        percent = (total / max_total) * scale_max if max_total > 0 else 0
        grade = GradeScale.get_grade(percent, 100)
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
        flash(t('openpyxl_not_installed'), 'error')
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
    if not is_teacher and current_user.role not in ['admin', 'dean', 'edu_dept']:
        flash(t('no_permission_for_operation'), 'error')
        return redirect(url_for('courses.detail', id=subject_id, dir_id=group.direction_id, group_id=group_id, semester=group.semester or 1))
    
    # Ma'lumotlarni tayyorlash
    students = User.query.filter_by(role='student', group_id=group_id).order_by(User.full_name).all()
    assignments = Assignment.query.filter_by(subject_id=subject_id, group_id=group_id).order_by(Assignment.due_date).all()
    
    # Agar guruh uchun topshiriqlar bo'lmasa, umumiy fanda yo'nalishsiz bo'lgan topshiriqlarni ham olishi mumkin
    if not assignments:
        assignments = Assignment.query.filter_by(subject_id=subject_id, group_id=None).order_by(Assignment.due_date).all()
    
    # Baholanmagan javob bo'lsa eksport qilish mumkin emas
    if assignments:
        assignment_ids = [a.id for a in assignments]
        ungraded = Submission.query.filter(
            Submission.assignment_id.in_(assignment_ids),
            Submission.score.is_(None)
        ).limit(1).first()
        if ungraded:
            flash(t('export_ungraded_blocked'), 'error')
            return redirect(url_for('courses.detail', id=subject_id, dir_id=group.direction_id, group_id=group_id, semester=group.semester or 1))
    
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
        
        scale_max = GradeScale.get_scale_max()
        row['percent'] = (row['total_score'] / row['max_total']) * scale_max if row['max_total'] > 0 else 0
        matrix.append(row)
    
    try:
        from app.utils.excel_export import create_detailed_assignment_export_excel
    except ImportError:
        flash(t('openpyxl_not_installed'), 'error')
        return redirect(url_for('courses.detail', id=subject_id, dir_id=group.direction_id, group_id=group_id, semester=group.semester or 1))
    
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
        flash(t('export_grades_error', error=str(e)), 'error')
        return redirect(url_for('courses.detail', id=subject_id, dir_id=group.direction_id, group_id=group_id, semester=group.semester or 1))


@bp.route('/assignments/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit_assignment(id):
    """Topshiriqni tahrirlash"""
    assignment = Assignment.query.get_or_404(id)
    subject = assignment.subject
    direction_id = request.args.get('direction_id', type=int) or assignment.direction_id
    group_id_param = request.args.get('group_id', type=int) or assignment.group_id
    
    # Tanlangan rol
    current_role = session.get('current_role', current_user.role)
    
    # Ruxsat tekshiruvi: Admin yoki biriktirilgan dars turi bo'yicha o'qituvchi
    can_edit = False
    if (current_user.role in ['admin', 'dean']) and current_role != 'teacher' and current_role != 'edu_dept':
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
        flash(t('no_permission_to_edit_assignment'), 'error')
        return redirect(url_for('courses.assignment_detail', id=id))
    
    # Tanlangan rol
    current_role = session.get('current_role', current_user.role)
    is_acting_as_teacher = (current_role == 'teacher') or (current_user.role == 'teacher')
    
    # Dars turlari: faqat o'quv rejada soati bor turlar
    allowed_lesson_types = []
    lesson_type_names_map = {
        'maruza': 'Maruza',
        'amaliyot': 'Amaliyot',
        'laboratoriya': 'Laboratoriya',
        'seminar': 'Seminar',
        'kurs_ishi': 'Kurs ishi'
    }
    lesson_type_order = ['maruza', 'amaliyot', 'laboratoriya', 'seminar', 'kurs_ishi']
    
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
                curriculum_lesson_types = set()
                if (curriculum_item.hours_maruza or 0) > 0:
                    curriculum_lesson_types.add('maruza')
                if (curriculum_item.hours_amaliyot or 0) > 0:
                    curriculum_lesson_types.add('amaliyot')
                if (curriculum_item.hours_laboratoriya or 0) > 0:
                    curriculum_lesson_types.add('laboratoriya')
                if (curriculum_item.hours_seminar or 0) > 0:
                    curriculum_lesson_types.add('seminar')
                if (curriculum_item.hours_kurs_ishi or 0) > 0:
                    curriculum_lesson_types.add('kurs_ishi')
                if curriculum_lesson_types:
                    lesson_types_set &= curriculum_lesson_types
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
        for lt_key in lesson_type_order:
            if lt_key in lesson_types_set:
                allowed_lesson_types.append({'value': lt_key, 'name': lesson_type_names_map.get(lt_key, lt_key.capitalize())})
    elif current_user.role in ['admin', 'dean', 'edu_dept'] and current_role != 'teacher' and direction_id:
        curriculum_item = DirectionCurriculum.query.filter_by(
            direction_id=direction_id,
            subject_id=subject.id
        ).first()
        if curriculum_item:
            if (curriculum_item.hours_maruza or 0) > 0:
                allowed_lesson_types.append({'value': 'maruza', 'name': 'Maruza'})
            if (curriculum_item.hours_amaliyot or 0) > 0:
                allowed_lesson_types.append({'value': 'amaliyot', 'name': 'Amaliyot'})
            if (curriculum_item.hours_laboratoriya or 0) > 0:
                allowed_lesson_types.append({'value': 'laboratoriya', 'name': 'Laboratoriya'})
            if (curriculum_item.hours_seminar or 0) > 0:
                allowed_lesson_types.append({'value': 'seminar', 'name': 'Seminar'})
            if (curriculum_item.hours_kurs_ishi or 0) > 0:
                allowed_lesson_types.append({'value': 'kurs_ishi', 'name': 'Kurs ishi'})
        if not allowed_lesson_types:
            allowed_lesson_types = [
                {'value': 'maruza', 'name': 'Maruza'},
                {'value': 'amaliyot', 'name': 'Amaliyot'},
                {'value': 'laboratoriya', 'name': 'Laboratoriya'},
                {'value': 'seminar', 'name': 'Seminar'},
                {'value': 'kurs_ishi', 'name': 'Kurs ishi'}
            ]
    elif current_user.role in ['admin', 'dean', 'edu_dept'] and current_role != 'teacher':
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
    
    # Darslar ro'yxati — har bir dars turi ichida tartib raqami 1, 2, 3...
    lessons = []
    if direction_id:
        raw_lessons = Lesson.query.filter_by(
            subject_id=subject.id,
            direction_id=direction_id
        ).order_by(Lesson.order).all()
        type_counters = defaultdict(int)
        for lesson in raw_lessons:
            type_counters[lesson.lesson_type or ''] += 1
            lesson.display_order_in_type = type_counters[lesson.lesson_type or '']
        lessons = raw_lessons
    
    if request.method == 'POST':
        # Topshiriq ma'lumotlarini yangilash
        assignment.title = request.form.get('title')
        assignment.description = request.form.get('description')
        assignment.lesson_type = request.form.get('lesson_type')
        assignment.max_score = GradeScale.get_scale_max()
        
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
        flash(t('assignment_updated'), 'success')
        if direction_id and group_id_param:
            return redirect(url_for('courses.detail', id=subject.id, dir_id=direction_id, group_id=group_id_param))
        return redirect(url_for('courses.detail', id=subject.id, dir_id=direction_id))
    
    # Tanlangan mavzular
    lesson_ids = assignment.get_lesson_ids_list() if assignment.lesson_ids else []
    
    return render_template('courses/edit_assignment.html',
                         assignment=assignment,
                         subject=subject,
                         lessons=lessons,
                         selected_lesson_ids=lesson_ids,
                         allowed_lesson_types=allowed_lesson_types,
                         direction_id=direction_id,
                         group_id=group_id_param,
                         scale_max=GradeScale.get_scale_max())


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
    
    if (current_user.role in ['admin', 'dean']) and current_role != 'teacher' and current_role != 'edu_dept':
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
        flash(t('no_permission_to_delete_assignment'), 'error')
        return redirect(url_for('courses.assignment_detail', id=id))
    
    db.session.delete(assignment)
    db.session.commit()
    flash(t('assignment_deleted'), 'success')
    if assignment.direction_id and assignment.group_id:
        return redirect(url_for('courses.detail', id=subject.id, dir_id=assignment.direction_id, group_id=assignment.group_id))
    return redirect(url_for('courses.detail', id=subject.id, dir_id=assignment.direction_id))
