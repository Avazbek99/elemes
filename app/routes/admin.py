from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, send_file, Response, session, current_app
from flask_login import login_required, current_user
from app.models import User, Faculty, Group, Subject, TeacherSubject, TeacherDepartment, Assignment, Direction, GradeScale, Schedule, UserRole, RolePermission, StudentPayment, DirectionCurriculum, Message, Submission, Lesson, LessonView, Announcement, PasswordResetToken, SiteSetting, FlashMessage, Department, DepartmentHead, UserFaculty, SubjectDepartment, FaceLog
from app import db
from functools import wraps
from datetime import datetime, date
from pathlib import Path
from sqlalchemy import func, or_, exists, asc, desc

from app.utils.excel_export import create_all_users_excel, create_subjects_excel, create_departments_excel
from app.utils.excel_import import (
    import_students_from_excel, generate_sample_file,
    import_directions_from_excel,
    import_staff_from_excel, generate_staff_sample_file,
    import_subjects_from_excel, generate_subjects_sample_file,
    import_departments_from_excel, generate_departments_sample_file,
    import_curriculum_from_excel, generate_curriculum_sample_file,
    import_schedule_from_excel, generate_schedule_sample_file
)
from werkzeug.security import generate_password_hash
from app.utils.translations import t

bp = Blueprint('admin', __name__, url_prefix='/admin')

def admin_required(f):
    """Admin, O'quv bo'limi, Kafedra mudiri yoki superadmin uchun"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash(t('no_access_permission'), 'error')
            return redirect(url_for('main.dashboard'))
        if getattr(current_user, 'is_superadmin', False):
            return f(*args, **kwargs)
        current_role = session.get('current_role', current_user.role)
        allowed_roles = ['admin', 'edu_dept', 'department_head']
        if current_role in allowed_roles and current_user.has_role(current_role):
            return f(*args, **kwargs)
        if current_role == 'admin' and 'admin' in current_user.get_roles():
            return f(*args, **kwargs)
        if current_user.has_role('admin'):
            return f(*args, **kwargs)
        flash(t('no_access_permission'), 'error')
        return redirect(url_for('main.dashboard'))
    return decorated_function


def superadmin_required(f):
    """Faqat superadmin uchun (rollar sozlamalari va boshqalar)"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not getattr(current_user, 'is_superadmin', False):
            flash(t('no_access_permission'), 'error')
            return redirect(url_for('main.dashboard'))
        return f(*args, **kwargs)
    return decorated_function


def permission_required(permission):
    """Admin yo'lida berilgan ruxsatni tekshiradi (superadmin hammaga ruxsatli). Tanlangan rol bo'yicha tekshiradi."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if getattr(current_user, 'is_superadmin', False):
                return f(*args, **kwargs)
            current_role = session.get('current_role', getattr(current_user, 'role', None))
            if not current_user.has_permission(permission, for_role=current_role):
                flash(t('no_access_permission'), 'error')
                return redirect(url_for('main.dashboard'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator


# Barcha ruxsatlar kalitlari (superadmin rollar sozlamasida ko'rsatiladi)
ROLE_ORDER = ['admin', 'dean', 'edu_dept', 'department_head', 'teacher', 'accounting', 'student']

# Boshlang'ich (default) rol ruxsatlari – har bir ruxsat alohida belgilanadi, "Barcha huquqlar" yo'q
DEFAULT_ROLE_PERMISSIONS = [
    # Admin – barcha ruxsatlar alohida
    ('admin', 'view_admin_panel'), ('admin', 'view_users'), ('admin', 'create_user'), ('admin', 'edit_user'),
    ('admin', 'delete_user'), ('admin', 'toggle_user'), ('admin', 'reset_user_password'),
    ('admin', 'view_staff'), ('admin', 'create_staff'), ('admin', 'edit_staff'), ('admin', 'delete_staff'),
    ('admin', 'view_students'), ('admin', 'create_student'), ('admin', 'edit_student'), ('admin', 'delete_student'),
    ('admin', 'view_departments'), ('admin', 'create_department'), ('admin', 'edit_department'), ('admin', 'delete_department'),
    ('admin', 'view_faculties'), ('admin', 'create_faculty'), ('admin', 'edit_faculty'), ('admin', 'delete_faculty'),
    ('admin', 'view_directions'), ('admin', 'create_direction'), ('admin', 'edit_direction'), ('admin', 'delete_direction'),
    ('admin', 'manage_groups'), ('admin', 'create_group'), ('admin', 'edit_group'), ('admin', 'delete_group'),
    ('admin', 'view_subjects'), ('admin', 'create_subject'), ('admin', 'edit_subject'), ('admin', 'delete_subject'),
    ('admin', 'view_curriculum'), ('admin', 'edit_curriculum'),
    ('admin', 'view_schedule'), ('admin', 'create_schedule'), ('admin', 'edit_schedule'), ('admin', 'delete_schedule'),
    ('admin', 'view_reports'), ('admin', 'view_grade_scale'), ('admin', 'manage_grade_scale'),
    ('admin', 'view_teachers'), ('admin', 'assign_teachers'),
    ('admin', 'export_subjects'), ('admin', 'import_subjects'), ('admin', 'import_schedule'), ('admin', 'import_students'), ('admin', 'import_staff'),
    ('admin', 'view_announcements'), ('admin', 'send_message'), ('admin', 'view_messages'),
    ('dean', 'view_dean_panel'), ('dean', 'view_subjects'), ('dean', 'view_students'), ('dean', 'view_teachers'),
    ('dean', 'view_reports'), ('dean', 'create_announcement'), ('dean', 'manage_groups'), ('dean', 'assign_teachers'),
    ('dean', 'dean_manage_students'), ('dean', 'dean_manage_directions'), ('dean', 'dean_manage_groups'),
    ('edu_dept', 'view_directions'), ('edu_dept', 'view_curriculum'), ('edu_dept', 'edit_curriculum'),
    ('edu_dept', 'view_subjects'), ('edu_dept', 'create_subject'),
    ('department_head', 'view_admin_panel'), ('department_head', 'view_subjects'),
    ('department_head', 'create_subject'), ('department_head', 'view_teachers'), ('department_head', 'assign_teachers'),
    ('dean', 'dean_manage_curriculum'), ('dean', 'dean_manage_teachers'), ('dean', 'dean_manage_schedule'),
    ('dean', 'view_announcements'), ('dean', 'send_message'), ('dean', 'view_messages'),
    ('teacher', 'view_subjects'), ('teacher', 'view_students'), ('teacher', 'create_lesson'), ('teacher', 'edit_lesson'), ('teacher', 'delete_lesson'),
    ('teacher', 'create_assignment'), ('teacher', 'edit_assignment'), ('teacher', 'delete_assignment'),
    ('teacher', 'grade_students'), ('teacher', 'view_submissions'), ('teacher', 'create_announcement'),
    ('teacher', 'view_announcements'), ('teacher', 'send_message'), ('teacher', 'view_messages'),
    ('student', 'view_subjects'), ('student', 'view_lessons'), ('student', 'submit_assignment'), ('student', 'view_grades'),
    ('student', 'view_announcements'), ('student', 'send_message'), ('student', 'view_messages'),
    ('accounting', 'view_accounting'), ('accounting', 'view_students'), ('accounting', 'view_reports'),
    ('accounting', 'manage_payments'), ('accounting', 'manage_contracts'), ('accounting', 'view_contract_amounts'), ('accounting', 'import_payments'),
    ('accounting', 'view_announcements'), ('accounting', 'send_message'), ('accounting', 'view_messages'),
]

# Barcha ruxsatlar – modul va amal bo'yicha tartiblangan (ko'rish → yaratish → tahrirlash → o'chirish → boshqa)
ALL_PERMISSIONS = [
    # —— Admin panel ——
    ('view_admin_panel', 'Admin panelga kirish'),
    # Foydalanuvchilar: ko'rish → yaratish → tahrirlash → o'chirish → faollik, parol
    ('view_users', 'Foydalanuvchilar ro\'yxati'),
    ('create_user', 'Foydalanuvchi qo\'shish'),
    ('edit_user', 'Foydalanuvchini tahrirlash'),
    ('delete_user', 'Foydalanuvchini o\'chirish'),
    ('toggle_user', 'Foydalanuvchi faolligini o\'zgartirish'),
    ('reset_user_password', 'Parolni tiklash'),
    # Xodimlar
    ('view_staff', 'Xodimlar ro\'yxati'),
    ('create_staff', 'Xodim qo\'shish'),
    ('edit_staff', 'Xodimni tahrirlash'),
    ('delete_staff', 'Xodimni o\'chirish'),
    # Talabalar
    ('view_students', 'Talabalar ro\'yxati'),
    ('create_student', 'Talaba qo\'shish'),
    ('edit_student', 'Talabani tahrirlash'),
    ('delete_student', 'Talabani o\'chirish'),
    # Kafedralar
    ('view_departments', 'Kafedralar'),
    ('create_department', 'Kafedra qo\'shish'),
    ('edit_department', 'Kafedrani tahrirlash'),
    ('delete_department', 'Kafedrani o\'chirish'),
    # Fakultetlar
    ('view_faculties', 'Fakultetlar'),
    ('create_faculty', 'Fakultet qo\'shish'),
    ('edit_faculty', 'Fakultetni tahrirlash'),
    ('delete_faculty', 'Fakultetni o\'chirish'),
    # Yo'nalishlar
    ('view_directions', 'Yo\'nalishlar'),
    ('create_direction', 'Yo\'nalish qo\'shish'),
    ('edit_direction', 'Yo\'nalishni tahrirlash'),
    ('delete_direction', 'Yo\'nalishni o\'chirish'),
    # Guruhlar
    ('manage_groups', 'Guruhlarni boshqarish'),
    ('create_group', 'Guruh qo\'shish'),
    ('edit_group', 'Guruhni tahrirlash'),
    ('delete_group', 'Guruhni o\'chirish'),
    # Fanlar
    ('view_subjects', 'Fanlar'),
    ('create_subject', 'Fan qo\'shish'),
    ('edit_subject', 'Fanni tahrirlash'),
    ('delete_subject', 'Fanni o\'chirish'),
    # O'quv reja
    ('view_curriculum', 'O\'quv reja'),
    ('edit_curriculum', 'O\'quv rejani tahrirlash'),
    # Dars jadvali
    ('view_schedule', 'Dars jadvali'),
    ('create_schedule', 'Jadval qo\'shish'),
    ('edit_schedule', 'Jadvalni tahrirlash'),
    ('delete_schedule', 'Jadvalni o\'chirish'),
    # Hisobotlar va baholash
    ('view_reports', 'Hisobotlar'),
    ('view_grade_scale', 'Baholash tizimi'),
    ('manage_grade_scale', 'Baholash tizimini boshqarish'),
    # O'qituvchilar
    ('view_teachers', 'O\'qituvchilar ro\'yxati'),
    ('assign_teachers', 'O\'qituvchi biriktirish'),
    # Import / Eksport (har biri alohida)
    ('export_subjects', 'Fanlar eksport'),
    ('import_subjects', 'Fanlar import'),
    ('import_schedule', 'Dars jadvali import'),
    ('import_students', 'Talabalar import'),
    ('import_staff', 'Xodimlar import'),
    # —— Dekan panel ——
    ('view_dean_panel', 'Dekan panelga kirish'),
    ('dean_manage_students', 'Dekan: talabalarni boshqarish'),
    ('dean_manage_directions', 'Dekan: yo\'nalishlarni boshqarish'),
    ('dean_manage_groups', 'Dekan: guruhlarni boshqarish'),
    ('dean_manage_curriculum', 'Dekan: o\'quv reja'),
    ('dean_manage_teachers', 'Dekan: o\'qituvchilar'),
    ('dean_manage_schedule', 'Dekan: dars jadvali'),
    # —— O'qituvchi (dars va topshiriq) ——
    ('create_lesson', 'Dars yaratish'),
    ('edit_lesson', 'Darsni tahrirlash'),
    ('delete_lesson', 'Darsni o\'chirish'),
    ('create_assignment', 'Topshiriq yaratish'),
    ('edit_assignment', 'Topshiriqni tahrirlash'),
    ('delete_assignment', 'Topshiriqni o\'chirish'),
    ('grade_students', 'Javoblarni baholash'),
    ('view_submissions', 'Javoblarni ko\'rish'),
    ('create_announcement', 'E\'lon yaratish'),
    # —— Talaba ——
    ('view_lessons', 'Darslarni ko\'rish'),
    ('submit_assignment', 'Topshiriq yuborish'),
    ('view_grades', 'Baho ko\'rish'),
    # —— Buxgalteriya ——
    ('view_accounting', 'Buxgalteriya bo\'limiga kirish'),
    ('manage_payments', 'To\'lovlarni boshqarish'),
    ('manage_contracts', 'Kontraktlarni boshqarish'),
    ('view_contract_amounts', 'Kontrakt summalarini ko\'rish'),
    ('import_payments', 'To\'lovlarni import qilish'),
    # —— Umumiy (e'lon, xabar) ——
    ('view_announcements', 'E\'lonlarni ko\'rish'),
    ('send_message', 'Xabar yuborish'),
    ('view_messages', 'Xabarlarni ko\'rish'),
]


# ==================== ASOSIY SAHIFA ====================
@bp.route('/')
@login_required
@admin_required
@permission_required('view_admin_panel')
def index():
    stats = {
        'total_users': User.query.count(),
        'total_students': User.query.filter_by(role='student').count(),
        'total_teachers': db.session.query(UserRole.user_id).filter_by(role='teacher').distinct().count() or User.query.filter_by(role='teacher').count() or len([u for u in User.query.all() if 'teacher' in u.get_roles()]),
        'total_deans': User.query.filter_by(role='dean').count(),
        'total_faculties': Faculty.query.count(),
        'total_groups': Group.query.count(),
        'total_subjects': Subject.query.count(),
    }
    # Superadmin "So'nggi foydalanuvchilar" da ko'rinmasin (is_superadmin bo'yicha)
    all_recent = User.query.order_by(User.created_at.desc()).limit(15).all()
    recent_users = [u for u in all_recent if not getattr(u, 'is_superadmin', False)][:10]
    return render_template('admin/index.html', stats=stats, recent_users=recent_users)


@bp.route('/role-settings', methods=['GET', 'POST'])
@login_required
@superadmin_required
def role_settings():
    """Superadmin: barcha rollar uchun ruxsatlarni check orqali boshqarish"""
    role_labels = {
        'admin': t('administrator'),
        'dean': t('dean'),
        'edu_dept': t('edu_dept'),
        'department_head': t('department_head'),
        'teacher': t('teacher'),
        'accounting': t('accounting'),
        'student': t('student'),
    }
    if request.method == 'POST':
        if request.form.get('reset_defaults') == '1':
            RolePermission.query.delete()
            for role, perm in DEFAULT_ROLE_PERMISSIONS:
                db.session.add(RolePermission(role=role, permission=perm))
            db.session.commit()
            flash(t('role_settings_reset_to_default'), 'success')
            return redirect(url_for('admin.role_settings'))
        for role in ROLE_ORDER:
            RolePermission.query.filter_by(role=role).delete()
            checked = request.form.getlist(f'perm_{role}')
            for perm in checked:
                if perm in [p[0] for p in ALL_PERMISSIONS]:
                    db.session.add(RolePermission(role=role, permission=perm))
            if not checked:
                db.session.add(RolePermission(role=role, permission='__configured__'))
        db.session.commit()
        flash(t('role_permissions_saved'), 'success')
        return redirect(url_for('admin.role_settings'))
    perms_by_role = {}
    for role in ROLE_ORDER:
        rows = RolePermission.query.filter_by(role=role).all()
        if not rows:
            perms_by_role[role] = {perm for r, perm in DEFAULT_ROLE_PERMISSIONS if r == role}
        else:
            perms_by_role[role] = {p.permission for p in rows if getattr(p, 'permission', '') and p.permission != '__configured__'}
    return render_template(
        'admin/role_settings.html',
        role_order=ROLE_ORDER,
        role_labels=role_labels,
        all_permissions=ALL_PERMISSIONS,
        perms_by_role=perms_by_role,
    )


SITE_LANGS = ['uz', 'ru', 'en']

@bp.route('/reklamalar')
@login_required
@superadmin_required
def reklamalar():
    """Reklamalar – Flash xabarlar ro'yxati (faqat superadmin)."""
    flash_messages = FlashMessage.query.order_by(FlashMessage.sort_order.asc(), FlashMessage.id.asc()).all()
    return render_template(
        'admin/reklamalar.html',
        flash_messages=flash_messages,
        site_langs=SITE_LANGS,
    )


@bp.route('/reklamalar/flash-xabar', methods=['GET'])
@bp.route('/reklamalar/flash-xabar/<int:fm_id>', methods=['GET'])
@login_required
@superadmin_required
def flash_xabar_edit(fm_id=None):
    """Flash xabar qo'shish/tahrirlash – alohida sahifa (faqat superadmin)."""
    fm = FlashMessage.query.get(fm_id) if fm_id else None
    if fm_id and not fm:
        flash(t('not_found'), 'error')
        return redirect(url_for('admin.reklamalar'))
    return render_template(
        'admin/flash_xabar_edit.html',
        fm=fm,
        site_langs=SITE_LANGS,
    )


@bp.route('/flash-message/update', methods=['POST'])
@bp.route('/flash-message/update/<int:fm_id>', methods=['POST'])
@login_required
@superadmin_required
def update_flash_message(fm_id=None):
    """Flash xabar sozlamalarini saqlash (faqat superadmin)."""
    fm = FlashMessage.query.get(fm_id) if fm_id else None
    if fm_id and not fm:
        flash(t('not_found'), 'error')
        return redirect(url_for('admin.reklamalar'))
    if not fm:
        fm = FlashMessage()
        db.session.add(fm)
    fm.text_uz = (request.form.get('ticker_text_uz') or '').strip()
    fm.text_ru = (request.form.get('ticker_text_ru') or '').strip()
    fm.text_en = (request.form.get('ticker_text_en') or '').strip()
    fm.url = (request.form.get('ticker_url') or '').strip()
    fm.text_color = (request.form.get('ticker_text_color') or 'white').strip().lower()
    fm.enabled = request.form.get('ticker_enabled') == '1'
    df = (request.form.get('ticker_date_from') or '').strip()
    dt = (request.form.get('ticker_date_to') or '').strip()
    try:
        fm.date_from = date.fromisoformat(df) if df else None
    except (ValueError, TypeError):
        fm.date_from = None
    try:
        fm.date_to = date.fromisoformat(dt) if dt else None
    except (ValueError, TypeError):
        fm.date_to = None
    fm.sort_order = fm.sort_order or 0
    db.session.commit()
    flash(t('flash_xabar_saved'), 'success')
    return redirect(url_for('admin.reklamalar'))


@bp.route('/flash-message/toggle/<int:fm_id>', methods=['POST'])
@login_required
@superadmin_required
def toggle_flash_message(fm_id):
    """Flash xabar faolligini o'zgartirish (yoqish/o'chirish)."""
    fm = FlashMessage.query.get_or_404(fm_id)
    fm.enabled = not fm.enabled
    db.session.commit()
    flash(t('flash_xabar_saved'), 'success')
    return redirect(url_for('admin.reklamalar'))


@bp.route('/flash-message/delete/<int:fm_id>', methods=['POST'])
@login_required
@superadmin_required
def delete_flash_message(fm_id):
    """Flash xabarni butunlay o'chirish."""
    fm = FlashMessage.query.get_or_404(fm_id)
    db.session.delete(fm)
    db.session.commit()
    flash(t('flash_xabar_deleted'), 'success')
    return redirect(url_for('admin.reklamalar'))


@bp.route('/site-settings', methods=['GET', 'POST'])
@login_required
@superadmin_required
def site_settings():
    """Sayt sozlamalari – har til uchun platforma nomi, qisqacha nom, tagline va logo."""
    from werkzeug.utils import secure_filename
    import os
    UPLOAD_FOLDER = current_app.config.get('UPLOAD_FOLDER', 'uploads')
    if not os.path.isabs(UPLOAD_FOLDER):
        UPLOAD_FOLDER = os.path.join(current_app.root_path, '..', UPLOAD_FOLDER)
    UPLOAD_FOLDER = os.path.abspath(UPLOAD_FOLDER)
    SITE_UPLOAD = os.path.join(UPLOAD_FOLDER, 'site')
    ALLOWED_LOGO = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'svg'}
    if request.method == 'POST':
        upload_error = False
        removed_logo_lang = None
        for lang in SITE_LANGS:
            SiteSetting.set('institution_name_' + lang, (request.form.get('institution_name_' + lang) or '').strip())
            SiteSetting.set('site_name_short_' + lang, (request.form.get('site_name_short_' + lang) or '').strip())
            SiteSetting.set('tagline_' + lang, (request.form.get('tagline_' + lang) or '').strip())
            if request.form.get('remove_logo_' + lang) == '1':
                removed_logo_lang = lang
                old_path = SiteSetting.get('logo_path_' + lang)
                SiteSetting.set('logo_path_' + lang, '')
                if old_path:
                    try:
                        old_path_norm = old_path.replace('\\', '/').strip().lstrip('/')
                        if old_path_norm:
                            old_file = os.path.join(UPLOAD_FOLDER, old_path_norm.replace('/', os.sep))
                            if os.path.isfile(old_file):
                                os.remove(old_file)
                    except Exception:
                        pass
            else:
                logo_file = request.files.get('logo_' + lang)
                ext = ''
                if logo_file:
                    fn = (getattr(logo_file, 'filename', None) or '').strip()
                    if fn:
                        ext = (fn.rsplit('.', 1)[-1] or '').lower().strip()
                    if not ext and getattr(logo_file, 'content_type', None):
                        ct = (logo_file.content_type or '').lower()
                        if 'jpeg' in ct or 'jpg' in ct:
                            ext = 'jpg'
                        elif 'png' in ct:
                            ext = 'png'
                        elif 'gif' in ct:
                            ext = 'gif'
                        elif 'webp' in ct:
                            ext = 'webp'
                        elif 'svg' in ct:
                            ext = 'svg'
                if ext and ext in ALLOWED_LOGO:
                    try:
                        os.makedirs(SITE_UPLOAD, exist_ok=True)
                        filename = secure_filename(f'logo_{lang}.{ext}')
                        filepath = os.path.join(SITE_UPLOAD, filename)
                        logo_file.save(filepath)
                        SiteSetting.set('logo_path_' + lang, 'site/' + filename)
                    except Exception as e:
                        current_app.logger.exception('Logo upload failed')
                        flash(t('site_settings_logo_upload_error') or ('Logo yuklanmadi: %s' % str(e)), 'error')
                        upload_error = True
                elif ext and ext not in ALLOWED_LOGO:
                    flash(t('site_settings_logo_format_error') or ('Logo formati qabul qilinmaydi. Ruxsat etilgan: PNG, JPG, GIF, WebP, SVG.'), 'error')
                    upload_error = True
        if not upload_error:
            flash(t('site_settings_saved'), 'success')
        if removed_logo_lang:
            return redirect(url_for('admin.site_settings', _anchor='lang-' + removed_logo_lang))
        return redirect(url_for('admin.site_settings'))
    data = {}
    for lang in SITE_LANGS:
        logo_path = SiteSetting.get('logo_path_' + lang) or ''
        parts = (logo_path or '').replace('\\', '/').strip().split('/')
        logo_filename = parts[-1] if parts and parts[-1] else ''
        data[lang] = {
            'institution_name': SiteSetting.get('institution_name_' + lang),
            'site_name_short': SiteSetting.get('site_name_short_' + lang),
            'tagline': SiteSetting.get('tagline_' + lang),
            'logo_path': logo_path,
            'logo_filename': logo_filename,
        }
    return render_template(
        'admin/site_settings.html',
        site_langs=SITE_LANGS,
        data=data,
    )


@bp.route('/uploads/site/<path:filename>')
def serve_site_upload(filename):
    """Sayt logosi va boshqa site fayllarini berish."""
    from flask import send_from_directory
    import os
    filename = os.path.basename(filename)
    if not filename or filename.startswith('.'):
        return '', 404
    uploads = current_app.config.get('UPLOAD_FOLDER', 'uploads')
    if not os.path.isabs(uploads):
        uploads = os.path.abspath(os.path.join(current_app.root_path, '..', uploads))
    site_dir = os.path.join(uploads, 'site')
    if not os.path.isdir(site_dir):
        return '', 404
    return send_from_directory(site_dir, filename)


@bp.route('/uploads/site/favicon/<path:filename>')
def serve_site_favicon(filename):
    """Favicon uchun kvadrat (nisbat saqlangan) logo – brauzer tabida cho‘zilmasin."""
    from flask import send_file, send_from_directory
    import os
    import io
    filename = os.path.basename(filename)
    if not filename or filename.startswith('.'):
        return '', 404
    uploads = current_app.config.get('UPLOAD_FOLDER', 'uploads')
    if not os.path.isabs(uploads):
        uploads = os.path.abspath(os.path.join(current_app.root_path, '..', uploads))
    site_dir = os.path.join(uploads, 'site')
    filepath = os.path.join(site_dir, filename)
    if not os.path.isfile(filepath):
        return '', 404
    try:
        from PIL import Image
        img = Image.open(filepath)
        img = img.convert('RGBA')
        w, h = img.size
        size = 64
        if w >= h:
            new_w, new_h = size, max(1, int(h * size / w))
        else:
            new_w, new_h = max(1, int(w * size / h)), size
        try:
            resample = Image.Resampling.LANCZOS
        except AttributeError:
            resample = Image.LANCZOS
        img = img.resize((new_w, new_h), resample)
        canvas = Image.new('RGBA', (size, size), (255, 255, 255, 0))
        x = (size - new_w) // 2
        y = (size - new_h) // 2
        canvas.paste(img, (x, y), img if img.mode == 'RGBA' else None)
        buf = io.BytesIO()
        canvas.save(buf, format='PNG')
        buf.seek(0)
        return send_file(buf, mimetype='image/png')
    except Exception:
        return send_from_directory(site_dir, filename)


# ==================== SUPERADMINLAR (faqat superadmin uchun) ====================
def _superadmin_list():
    """Barcha superadmin foydalanuvchilar (config login yoki superadmin_flag)."""
    super_login = (current_app.config.get('SUPERADMIN_LOGIN') or '').strip()
    all_users = User.query.all()
    return [u for u in all_users if getattr(u, 'is_superadmin', False)]


def _is_config_superadmin(user):
    """Foydalanuvchi config dagi SUPERADMIN_LOGIN bo'lsa (o'chirib bo'lmaydi)."""
    super_login = (current_app.config.get('SUPERADMIN_LOGIN') or '').strip()
    return bool(super_login and user.login and user.login.strip() == super_login)


@bp.route('/superadmins')
@login_required
@superadmin_required
def superadmins():
    """Superadminlar ro'yxati – faqat superadmin ko'radi."""
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '')
    all_super = _superadmin_list()
    if search:
        s = search.strip().lower()
        all_super = [u for u in all_super if (u.full_name and s in u.full_name.lower())
                     or (u.login and s in u.login.lower())
                     or (u.passport_number and s in u.passport_number.lower())
                     or (u.pinfl and s in u.pinfl)
                     or (u.phone and s in u.phone)
                     or (u.email and s in (u.email or '').lower())]
    all_super = sorted(all_super, key=lambda u: (u.full_name or '').upper())
    total = len(all_super)
    per_page = 50
    start = (page - 1) * per_page
    end = start + per_page

    class Pagination:
        def __init__(self, items, page, per_page, total):
            self.items = items
            self.page = page
            self.per_page = per_page
            self.total = total
            self.pages = max(1, (total + per_page - 1) // per_page)
            self.has_prev = page > 1
            self.has_next = page < self.pages
            self.prev_num = page - 1 if self.has_prev else None
            self.next_num = page + 1 if self.has_next else None

        def iter_pages(self, left_edge=2, right_edge=2, left_current=2, right_current=2):
            last = 0
            for num in range(1, self.pages + 1):
                if num <= left_edge or (self.page - left_current - 1 < num < self.page + right_current) or num > self.pages - right_edge:
                    if last + 1 != num:
                        yield None
                    yield num
                    last = num

    users = Pagination(all_super[start:end], page, per_page, total)
    config_login = (current_app.config.get('SUPERADMIN_LOGIN') or '').strip()
    if request.args.get('partial'):
        return render_template('admin/superadmins_partial.html', users=users, search=search, current_user=current_user, config_superadmin_login=config_login)
    return render_template('admin/superadmins.html', users=users, search=search, config_superadmin_login=config_login)


@bp.route('/superadmins/create', methods=['GET', 'POST'])
@login_required
@superadmin_required
def create_superadmin():
    """Yangi superadmin qo'shish."""
    if request.method == 'POST':
        login = (request.form.get('login') or '').strip()
        full_name = (request.form.get('full_name') or '').strip().upper()
        passport_number = (request.form.get('passport_number') or '').strip()
        if not full_name:
            flash(t('full_name_required'), 'error')
            return render_template('admin/create_superadmin.html', form_data=request.form)
        if not login:
            flash(t('login_required_for_staff'), 'error')
            return render_template('admin/create_superadmin.html', form_data=request.form)
        if not passport_number:
            flash(t('passport_required'), 'error')
            return render_template('admin/create_superadmin.html', form_data=request.form)
        # Boshlang'ich parol – pasport seriya raqami (forma da parol kiritish shart emas)
        if User.query.filter_by(login=login).first():
            flash(t('login_used_by_another_user'), 'error')
            return render_template('admin/create_superadmin.html', form_data=request.form)
        email = (request.form.get('email') or '').strip() or None
        if email and User.query.filter_by(email=email).first():
            flash(t('email_already_used'), 'error')
            return render_template('admin/create_superadmin.html', form_data=request.form)
        user = User(
            login=login,
            full_name=full_name,
            role='admin',
            is_active=True,
            superadmin_flag=True,
            email=email,
            phone=(request.form.get('phone') or '').strip() or None,
            passport_number=passport_number,
            pinfl=(request.form.get('pinfl') or '').strip() or None,
            description=(request.form.get('description') or '').strip() or None,
        )
        birth_date_str = (request.form.get('birth_date') or '').strip()
        if birth_date_str:
            try:
                from datetime import datetime
                user.birth_date = datetime.strptime(birth_date_str, '%Y-%m-%d').date()
            except Exception:
                pass
        user.set_password(passport_number)  # boshlang'ich parol = pasport seriya raqami
        db.session.add(user)
        db.session.flush()
        if not UserRole.query.filter_by(user_id=user.id, role='admin').first():
            db.session.add(UserRole(user_id=user.id, role='admin'))
        db.session.commit()
        flash(t('superadmin_created', full_name=user.full_name), 'success')
        return redirect(url_for('admin.superadmins'))
    return render_template('admin/create_superadmin.html')


@bp.route('/superadmins/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@superadmin_required
def edit_superadmin(id):
    """Superadminni tahrirlash."""
    user = User.query.get_or_404(id)
    if not getattr(user, 'is_superadmin', False):
        flash(t('user_not_superadmin'), 'error')
        return redirect(url_for('admin.superadmins'))
    if request.method == 'POST':
        full_name = (request.form.get('full_name') or '').strip().upper()
        login = (request.form.get('login') or '').strip()
        if not full_name:
            flash(t('full_name_required'), 'error')
            return render_template('admin/edit_superadmin.html', user=user)
        if not login:
            flash(t('login_required_for_staff'), 'error')
            return render_template('admin/edit_superadmin.html', user=user)
        other = User.query.filter(User.login == login, User.id != user.id).first()
        if other:
            flash(t('login_used_by_another_user'), 'error')
            return render_template('admin/edit_superadmin.html', user=user)
        user.full_name = full_name
        user.login = login
        user.phone = (request.form.get('phone') or '').strip() or None
        user.email = (request.form.get('email') or '').strip() or None
        user.passport_number = (request.form.get('passport_number') or '').strip() or None
        user.pinfl = (request.form.get('pinfl') or '').strip() or None
        user.description = (request.form.get('description') or '').strip() or None
        birth_date_str = (request.form.get('birth_date') or '').strip()
        if birth_date_str:
            try:
                from datetime import datetime
                user.birth_date = datetime.strptime(birth_date_str, '%Y-%m-%d').date()
            except Exception:
                user.birth_date = None
        else:
            user.birth_date = None
        new_pass = (request.form.get('password') or '').strip()
        if new_pass:
            user.set_password(new_pass)
        db.session.commit()
        flash(t('superadmin_updated', full_name=user.full_name), 'success')
        return redirect(url_for('admin.superadmins'))
    return render_template('admin/edit_superadmin.html', user=user)


@bp.route('/superadmins/<int:id>/delete', methods=['POST'])
@login_required
@superadmin_required
def delete_superadmin(id):
    """Superadminni o'chirish – config superadmin va oxirgi superadmin o'chirilmaydi."""
    user = User.query.get_or_404(id)
    if not getattr(user, 'is_superadmin', False):
        flash(t('user_not_superadmin'), 'error')
        return redirect(url_for('admin.superadmins'))
    if _is_config_superadmin(user):
        flash(t('config_superadmin_cannot_delete'), 'error')
        return redirect(url_for('admin.superadmins'))
    super_list = _superadmin_list()
    if len(super_list) <= 1:
        flash(t('cannot_delete_last_superadmin'), 'error')
        return redirect(url_for('admin.superadmins'))
    UserRole.query.filter_by(user_id=user.id).delete()
    db.session.delete(user)
    db.session.commit()
    flash(t('superadmin_deleted'), 'success')
    return redirect(url_for('admin.superadmins'))


# ==================== HIKVISION YUZ TANILASH (faqat superadmin) ====================
@bp.route('/face-logs')
@login_required
@superadmin_required
def face_logs():
    """Hikvision yuz tanilash loglari – faqat superadmin ko'radi."""
    limit = min(request.args.get('limit', 100, type=int), 500)
    last_request_info = None
    try:
        logs_list = FaceLog.query.order_by(FaceLog.created_at.desc()).limit(limit).all()
    except Exception as e:
        try:
            db.create_all()
            logs_list = FaceLog.query.order_by(FaceLog.created_at.desc()).limit(limit).all()
            flash(t('face_logs_table_created'), "success")
        except Exception:
            logs_list = []
            flash(t('face_logs_query_error') % str(e), "error")
    try:
        path = Path(current_app.instance_path) / 'face_last_request.txt'
        if path.exists():
            lines = path.read_text(encoding='utf-8', errors='replace').strip().split('\n')
            if len(lines) >= 2:
                last_request_info = {'time': lines[0], 'ip': lines[1]}
    except Exception:
        pass
    return render_template('admin/face_logs.html', logs_list=logs_list, limit=limit, last_request_info=last_request_info)


# ==================== FOYDALANUVCHILAR ====================
@bp.route('/users')
@login_required
@admin_required
@permission_required('view_users')
def users():
    page = request.args.get('page', 1, type=int)
    role = request.args.get('role', '')
    search = request.args.get('search', '')
    
    query = User.query
    # Superadmin ro'yxatda ko'rinmasin
    from flask import current_app
    super_login = current_app.config.get('SUPERADMIN_LOGIN', '').strip()
    if super_login:
        query = query.filter(User.login != super_login)
    
    if role:
        # UserRole orqali qidirish
        role_user_ids = db.session.query(UserRole.user_id).filter_by(role=role).distinct().all()
        role_user_ids = [uid[0] for uid in role_user_ids]
        
        # Agar UserRole orqali topilmasa, eski usul bilan qidirish
        if not role_user_ids:
            users_by_role = User.query.filter_by(role=role).all()
            role_user_ids = [u.id for u in users_by_role]
        
        # Agar hali ham topilmasa, get_roles() orqali qidirish
        if not role_user_ids:
            all_users = User.query.all()
            role_user_ids = [u.id for u in all_users if role in u.get_roles()]
        
        if role_user_ids:
            query = query.filter(User.id.in_(role_user_ids))
        else:
            query = query.filter(User.id == -1)  # Hech narsa topilmasin
    
    if search:
        query = query.filter(
            (User.full_name.ilike(f'%{search}%')) |
            (User.email.ilike(f'%{search}%'))
        )
    
    users = query.order_by(User.created_at.desc()).paginate(page=page, per_page=20)
    
    # Stats uchun ham UserRole orqali qidirish
    def get_role_count(role_name):
        count = db.session.query(UserRole.user_id).filter_by(role=role_name).distinct().count()
        if count == 0:
            count = User.query.filter_by(role=role_name).count()
        if count == 0:
            count = len([u for u in User.query.all() if role_name in u.get_roles()])
        return count
    
    stats = {
        'total': User.query.count(),
        'admins': get_role_count('admin'),
        'deans': get_role_count('dean'),
        'teachers': get_role_count('teacher'),
        'students': get_role_count('student'),
    }
    
    return render_template('admin/users.html', users=users, stats=stats, current_role=role, search=search)


@bp.route('/users/create', methods=['GET', 'POST'])
@login_required
@admin_required
@permission_required('create_user')
def create_user():
    faculties = Faculty.query.all()
    groups = Group.query.all()
    
    if request.method == 'POST':
        email = request.form.get('email')
        full_name = (request.form.get('full_name') or '').strip().upper()
        password = request.form.get('password')
        role = request.form.get('role')
        login = request.form.get('login')  # Login (xodimlar uchun)
        student_id = request.form.get('student_id')  # Talaba ID (talabalar uchun)
        passport_number = request.form.get('passport_number')
        pinfl = request.form.get('pinfl')
        birth_date_str = request.form.get('birth_date')
        phone = request.form.get('phone')
        
        # Rolga qarab login yoki talaba ID majburiy
        if role != 'student':
            # Xodimlar uchun login majburiy
            if not login:
                flash(t('login_required_for_staff'), 'error')
                return render_template('admin/create_user.html', faculties=faculties, groups=groups)
            if User.query.filter_by(login=login).first():
                flash(t('login_already_exists'), 'error')
                return render_template('admin/create_user.html', faculties=faculties, groups=groups)
        else:
            # Talabalar uchun talaba ID majburiy
            if not student_id:
                flash(t('student_id_required'), 'error')
                return render_template('admin/create_user.html', faculties=faculties, groups=groups)
            if User.query.filter_by(student_id=student_id).first():
                flash(t('student_id_already_exists'), 'error')
                return render_template('admin/create_user.html', faculties=faculties, groups=groups)
        
        # Email ixtiyoriy, lekin agar kiritilgan bo'lsa, unikallikni tekshirish
        if email and User.query.filter_by(email=email).first():
            flash(t('email_already_exists'), 'error')
            return render_template('admin/create_user.html', faculties=faculties, groups=groups)
        
        # Pasport raqami majburiy
        if not passport_number:
            flash(t('passport_required'), 'error')
            return render_template('admin/create_user.html', faculties=faculties, groups=groups)
        
        # Pasport raqamini katta harfga o'zgartirish
        passport_number = passport_number.upper()
        
        user = User(
            email=email if email else None,  # Email ixtiyoriy
            login=login if role != 'student' else None,
            full_name=full_name,
            role=role,
            phone=phone,
            passport_number=passport_number,
            pinfl=pinfl,
            student_id=student_id if role == 'student' else None
        )
        
        # Tug'ilgan sana (yyyy-mm-dd)
        if birth_date_str:
            try:
                user.birth_date = datetime.strptime(birth_date_str, '%Y-%m-%d').date()
            except ValueError:
                flash(t('birthdate_invalid_format'), 'error')
                return render_template('admin/create_user.html', faculties=faculties, groups=groups)
        
        # Rolga qarab qo'shimcha ma'lumotlar
        if role == 'student':
            # student_id allaqachon yuqorida o'qilgan va tekshirilgan
            user.group_id = request.form.get('group_id', type=int)
            user.enrollment_year = request.form.get('enrollment_year', type=int)
        
        elif role == 'teacher':
            user.department = request.form.get('department')
            user.position = request.form.get('position')
        
        elif role == 'dean':
            user.faculty_id = request.form.get('faculty_id', type=int)
            user.position = request.form.get('position', 'Dekan')
        
        # Parolni pasport raqamiga o'rnatish (agar parol kiritilmagan bo'lsa)
        if password:
            user.set_password(password)
        else:
            user.set_password(passport_number)
        
        db.session.add(user)
        db.session.commit()
        
        flash(t('user_created_with_role', role=user.get_role_display()), 'success')
        return redirect(url_for('admin.users'))
    
    return render_template('admin/create_user.html', faculties=faculties, groups=groups)


@bp.route('/users/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
@permission_required('edit_user')
def edit_user(id):
    user = User.query.get_or_404(id)
    if getattr(user, 'is_superadmin', False) and not getattr(current_user, 'is_superadmin', False):
        flash(t('only_superadmin_can_modify'), 'error')
        return redirect(url_for('admin.users'))
    faculties = Faculty.query.all()
    groups = Group.query.all()
    
    # Foydalanuvchining mavjud rollarini olish
    existing_roles = [ur.role for ur in user.roles_list.all()] if user.roles_list.count() > 0 else ([user.role] if user.role else [])
    
    if request.method == 'POST':
        email = request.form.get('email')
        # Email ixtiyoriy, lekin agar kiritilgan bo'lsa, unikallikni tekshirish
        if email:
            existing_user_with_email = User.query.filter_by(email=email).first()
            if existing_user_with_email and existing_user_with_email.id != user.id:
                flash(t('email_already_exists'), 'error')
                return render_template('admin/edit_user.html', user=user, faculties=faculties, groups=groups, existing_roles=existing_roles)
        user.email = email if email else None
        user.full_name = (request.form.get('full_name') or '').strip().upper()
        user.is_active = request.form.get('is_active') == 'on'
        user.phone = request.form.get('phone')
        
        # Bir nechta rol tanlash (agar roles maydoni mavjud bo'lsa)
        selected_roles = request.form.getlist('roles')
        
        # Agar roles tanlangan bo'lsa, UserRole orqali saqlash
        if selected_roles:
            # Asosiy rol (eng yuqori darajali)
            main_role = selected_roles[0]
            if 'admin' in selected_roles:
                main_role = 'admin'
            elif 'dean' in selected_roles:
                main_role = 'dean'
            elif 'teacher' in selected_roles:
                main_role = 'teacher'
            elif 'student' in selected_roles:
                main_role = 'student'
            
            user.role = main_role
            
            # Rollarni yangilash
            # Eski rollarni o'chirish
            UserRole.query.filter_by(user_id=user.id).delete()
            
            # Yangi rollarni qo'shish
            for role in selected_roles:
                user_role = UserRole(user_id=user.id, role=role)
                db.session.add(user_role)
        else:
            # Agar roles tanlanmagan bo'lsa, faqat asosiy rolni yangilash
            user.role = request.form.get('role')
        
        # Rolga qarab qo'shimcha ma'lumotlar
        if 'student' in (selected_roles if selected_roles else [user.role]):
            user.student_id = request.form.get('student_id')
            user.group_id = request.form.get('group_id', type=int)
            user.enrollment_year = request.form.get('enrollment_year', type=int)
        if 'teacher' in (selected_roles if selected_roles else [user.role]):
            user.department = request.form.get('department')
            user.position = request.form.get('position')
        if 'dean' in (selected_roles if selected_roles else [user.role]):
            user.faculty_id = request.form.get('faculty_id', type=int)
            if not user.position:
                user.position = request.form.get('position')
        
        new_password = request.form.get('new_password')
        if new_password:
            user.set_password(new_password)
        
        db.session.commit()
        flash(t('user_updated'), 'success')
        return redirect(url_for('admin.users'))
    
    return render_template('admin/edit_user.html', user=user, faculties=faculties, groups=groups, existing_roles=existing_roles)


@bp.route('/users/<int:id>/toggle', methods=['POST'])
@login_required
@admin_required
@permission_required('toggle_user')
def toggle_user(id):
    user = User.query.get_or_404(id)
    if getattr(user, 'is_superadmin', False) and not getattr(current_user, 'is_superadmin', False):
        flash(t('only_superadmin_can_modify'), 'error')
        referer = request.referrer or url_for('admin.users')
        if 'superadmins' in referer:
            return redirect(url_for('admin.superadmins'))
        if 'staff' in referer:
            return redirect(url_for('admin.staff'))
        elif 'students' in referer:
            return redirect(url_for('admin.students'))
        return redirect(url_for('admin.users'))
    if user.id == current_user.id:
        flash(t('cannot_block_yourself'), 'error')
    else:
        user.is_active = not user.is_active
        db.session.commit()
        status = "faollashtirildi" if user.is_active else "bloklandi"
        flash(t('user_status_changed', status=status), 'success')
    
    # Qaysi sahifadan kelganini aniqlash
    referer = request.referrer or url_for('admin.users')
    if 'superadmins' in referer:
        return redirect(url_for('admin.superadmins'))
    if 'staff' in referer:
        return redirect(url_for('admin.staff'))
    elif 'students' in referer:
        return redirect(url_for('admin.students'))
    return redirect(url_for('admin.users'))


@bp.route('/users/<int:id>/delete', methods=['POST'])
@login_required
@admin_required
@permission_required('delete_user')
def delete_user(id):
    user = User.query.get_or_404(id)
    if getattr(user, 'is_superadmin', False):
        flash(t('cannot_delete_superadmin'), 'error')
        referer = request.referrer or url_for('admin.users')
        if 'superadmins' in referer:
            return redirect(url_for('admin.superadmins'))
        if 'staff' in referer:
            return redirect(url_for('admin.staff'))
        elif 'students' in referer:
            return redirect(url_for('admin.students'))
        return redirect(url_for('admin.users'))
    if user.id == current_user.id:
        flash(t('cannot_delete_yourself'), 'error')
    else:
        # Foydalanuvchi xabarlarini o'chirish (sender yoki receiver bo'lgan)
        Message.query.filter(
            (Message.sender_id == user.id) | (Message.receiver_id == user.id)
        ).delete(synchronize_session=False)
        # Foydalanuvchi topshiriq yuborishlarini o'chirish
        Submission.query.filter_by(student_id=user.id).delete(synchronize_session=False)
        # Foydalanuvchi dars ko'rish yozuvlarini o'chirish (lesson_view.student_id NOT NULL)
        LessonView.query.filter_by(student_id=user.id).delete(synchronize_session=False)
        # Foydalanuvchi yozgan e'lonlarni o'chirish (announcement.author_id NOT NULL)
        Announcement.query.filter_by(author_id=user.id).delete(synchronize_session=False)
        # Parol tiklash tokenlarini o'chirish (password_reset_token.user_id NOT NULL)
        PasswordResetToken.query.filter_by(user_id=user.id).delete(synchronize_session=False)
        # O'qituvchi uchun TeacherSubject yozuvlarini oldin o'chirish (teacher_id NOT NULL)
        TeacherSubject.query.filter_by(teacher_id=user.id).delete()
        # assigned_by bo'yicha TeacherSubject yozuvlarida NULL qo'yish (nullable)
        TeacherSubject.query.filter_by(assigned_by=user.id).update({TeacherSubject.assigned_by: None}, synchronize_session=False)
        # DepartmentHead bog'lanishlarini o'chirish
        DepartmentHead.query.filter_by(user_id=user.id).delete(synchronize_session=False)
        # TeacherDepartment bog'lanishlarini o'chirish
        TeacherDepartment.query.filter_by(teacher_id=user.id).delete(synchronize_session=False)
        # UserRole yozuvlarini o'chirish
        UserRole.query.filter_by(user_id=user.id).delete(synchronize_session=False)
        db.session.delete(user)
        db.session.commit()
        flash(t('user_deleted'), 'success')
    
    # Qaysi sahifadan kelganini aniqlash
    referer = request.referrer or url_for('admin.users')
    if 'superadmins' in referer:
        return redirect(url_for('admin.superadmins'))
    if 'staff' in referer:
        return redirect(url_for('admin.staff'))
    elif 'students' in referer:
        return redirect(url_for('admin.students'))
    return redirect(url_for('admin.users'))


@bp.route('/users/<int:id>/reset_password', methods=['POST'])
@login_required
@admin_required
@permission_required('reset_user_password')
def reset_user_password(id):
    """Parolni boshlang'ich holatga qaytarish (pasport raqami yoki default parol)"""
    user = User.query.get_or_404(id)
    if getattr(user, 'is_superadmin', False) and not getattr(current_user, 'is_superadmin', False):
        flash(t('only_superadmin_can_modify'), 'error')
        referer = request.referrer or url_for('admin.users')
        if 'superadmins' in referer:
            return redirect(url_for('admin.superadmins'))
        if 'staff' in referer:
            return redirect(url_for('admin.staff'))
        elif 'students' in referer:
            return redirect(url_for('admin.students'))
        return redirect(url_for('admin.users'))
    # Parolni pasport seriya raqamiga qaytarish (superadmin uchun pasport bo'lmasa config parolidan foydalanish)
    if user.passport_number:
        new_password = user.passport_number
    elif getattr(user, 'is_superadmin', False):
        new_password = (current_app.config.get('SUPERADMIN_PASSWORD') or '').strip() or user.login
        if not new_password:
            flash(t('passport_not_available_for_student'), 'error')
            referer = request.referrer or url_for('admin.users')
            if 'superadmins' in referer:
                return redirect(url_for('admin.superadmins'))
            return redirect(referer if referer else url_for('admin.users'))
    else:
        flash(t('passport_not_available_for_student'), 'error')
        referer = request.referrer or url_for('admin.users')
        if 'superadmins' in referer:
            return redirect(url_for('admin.superadmins'))
        if 'staff' in referer:
            return redirect(url_for('admin.staff'))
        elif 'students' in referer:
            return redirect(url_for('admin.students'))
        return redirect(url_for('admin.users'))
    
    user.set_password(new_password)
    db.session.commit()
    flash(t('user_password_reset', full_name=user.full_name, new_password=new_password), 'success')
    
    # Qaysi sahifadan kelganini aniqlash
    referer = request.referrer or url_for('admin.users')
    if 'superadmins' in referer:
        return redirect(url_for('admin.superadmins'))
    if 'staff' in referer:
        return redirect(url_for('admin.staff'))
    elif 'students' in referer:
        return redirect(url_for('admin.students'))
    return redirect(url_for('admin.users'))
# ==================== O'QITUVCHILAR ====================
@bp.route('/teachers')
@login_required
@admin_required
@permission_required('view_teachers')
def teachers():
    """O'qituvchilar ro'yxati (UserRole orqali qidirish)"""
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '')
    
    # UserRole orqali o'qituvchi roliga ega bo'lgan foydalanuvchilarni topish
    teacher_user_ids = db.session.query(UserRole.user_id).filter_by(role='teacher').distinct().all()
    teacher_user_ids = [uid[0] for uid in teacher_user_ids]
    
    # Agar UserRole orqali topilmasa, eski usul bilan qidirish (asosiy role maydoni)
    if not teacher_user_ids:
        teachers_by_role = User.query.filter_by(role='teacher').all()
        teacher_user_ids = [t.id for t in teachers_by_role]
    
    # Agar hali ham topilmasa, get_roles() orqali qidirish
    if not teacher_user_ids:
        all_users = User.query.all()
        teacher_user_ids = [u.id for u in all_users if 'teacher' in u.get_roles()]
    
    # O'qituvchilarni olish
    query = User.query.filter(User.id.in_(teacher_user_ids))
    
    if search:
        query = query.filter(
            (User.full_name.ilike(f'%{search}%')) |
            (User.email.ilike(f'%{search}%')) |
            (User.phone.ilike(f'%{search}%'))
        )
    
    teachers = query.order_by(User.full_name).paginate(page=page, per_page=20, error_out=False)
    
    return render_template('admin/teachers.html', teachers=teachers, search=search)


# ==================== XODIMLAR BAZASI ====================
@bp.route('/staff')
@login_required
@admin_required
@permission_required('view_staff')
def staff():
    """Xodimlar bazasi (talabalar bo'lmagan barcha foydalanuvchilar)"""
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '')
    
    # Barcha foydalanuvchilarni olish
    query = User.query
    
    if search:
        query = query.filter(
            (User.full_name.ilike(f'%{search}%')) |
            (User.login.ilike(f'%{search}%')) |
            (User.passport_number.ilike(f'%{search}%')) |
            (User.pinfl.ilike(f'%{search}%')) |
            (User.phone.ilike(f'%{search}%')) |
            (User.email.ilike(f'%{search}%'))
        )
    
    all_users = query.all()
    
    # Faqat student roliga ega bo'lmagan userlarni filtrlash; superadmin ro'yxatda ko'rinmasin
    staff_users = [user for user in all_users if 'student' not in user.get_roles() and not getattr(user, 'is_superadmin', False)]
    
    # Ustun bo'yicha tartiblash
    sort = request.args.get('sort', 'name')
    order = request.args.get('order', 'asc') or 'asc'
    reverse = order == 'desc'
    if sort == 'passport':
        staff_users = sorted(staff_users, key=lambda u: (u.passport_number or '').upper(), reverse=reverse)
    elif sort == 'phone':
        staff_users = sorted(staff_users, key=lambda u: ((u.phone or '') + (u.email or '')).upper(), reverse=reverse)
    else:
        staff_users = sorted(staff_users, key=lambda u: (u.full_name or '').upper(), reverse=reverse)
    
    # Pagination uchun
    total = len(staff_users)
    per_page = 50
    start = (page - 1) * per_page
    end = start + per_page
    
    # Pagination object yaratish
    class Pagination:
        def __init__(self, items, page, per_page, total):
            self.items = items
            self.page = page
            self.per_page = per_page
            self.total = total
            self.pages = max(1, (total + per_page - 1) // per_page)
            self.has_prev = page > 1
            self.has_next = page < self.pages
            self.prev_num = page - 1 if self.has_prev else None
            self.next_num = page + 1 if self.has_next else None

        def iter_pages(self, left_edge=2, right_edge=2, left_current=2, right_current=2):
            last = 0
            for num in range(1, self.pages + 1):
                if (num <= left_edge or
                        (self.page - left_current - 1 < num < self.page + right_current) or
                        num > self.pages - right_edge):
                    if last + 1 != num:
                        yield None
                    yield num
                    last = num

    users = Pagination(staff_users[start:end], page, per_page, total)

    if request.args.get('partial'):
        return render_template('admin/staff_partial.html', users=users, search=search, current_user=current_user, sort_by=sort, sort_order=order)
    return render_template('admin/staff.html', users=users, search=search, sort_by=sort, sort_order=order)


@bp.route('/staff/create', methods=['GET', 'POST'])
@login_required
@admin_required
@permission_required('create_staff')
def create_staff():
    """Yangi xodim yaratish (bir nechta rol bilan)"""
    faculties = Faculty.query.all()
    
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        login = request.form.get('login', '').strip()  # Login (xodimlar uchun majburiy)
        full_name = (request.form.get('full_name') or '').strip().upper()
        phone = request.form.get('phone', '').strip()
        passport_number = request.form.get('passport_number', '').strip()
        pinfl = request.form.get('pinfl', '').strip()
        birth_date_str = request.form.get('birth_date', '').strip()
        description = request.form.get('description', '').strip()
        
        # Bir nechta rol tanlash
        selected_roles = request.form.getlist('roles')  # ['admin', 'dean', 'teacher']
        
        if not selected_roles:
            flash(t('at_least_one_role_required'), 'error')
            faculties = Faculty.query.all()
            departments = Department.query.order_by(Department.name).all()
            return render_template('admin/create_staff.html', faculties=faculties, departments=departments)
        
        # Login majburiy (xodimlar uchun)
        if not login:
            flash(t('login_required_field'), 'error')
            faculties = Faculty.query.all()
            departments = Department.query.order_by(Department.name).all()
            return render_template('admin/create_staff.html', faculties=faculties, departments=departments)
        
        # Login unikalligi
        if User.query.filter_by(login=login).first():
            flash(t('login_already_exists'), 'error')
            faculties = Faculty.query.all()
            departments = Department.query.order_by(Department.name).all()
            return render_template('admin/create_staff.html', faculties=faculties, departments=departments)
        
        # Email ixtiyoriy, lekin agar kiritilgan bo'lsa, unikallikni tekshirish
        if email and User.query.filter_by(email=email).first():
            flash(t('email_already_exists'), 'error')
            faculties = Faculty.query.all()
            departments = Department.query.order_by(Department.name).all()
            return render_template('admin/create_staff.html', faculties=faculties, departments=departments)
        
        # Pasport raqami parol sifatida ishlatiladi
        if not passport_number:
            flash(t('passport_required'), 'error')
            faculties = Faculty.query.all()
            departments = Department.query.order_by(Department.name).all()
            return render_template('admin/create_staff.html', faculties=faculties, departments=departments)
        
        # Pasport raqamini katta harfga o'zgartirish
        passport_number = passport_number.upper()
        
        # Tug'ilgan sanani parse qilish (yyyy-mm-dd)
        birth_date = None
        if birth_date_str:
            try:
                birth_date = datetime.strptime(birth_date_str, '%Y-%m-%d').date()
            except ValueError:
                flash(t('birthdate_invalid_format'), 'error')
                faculties = Faculty.query.all()
                departments = Department.query.order_by(Department.name).all()
                return render_template('admin/create_staff.html', faculties=faculties, departments=departments)
        
        password = passport_number  # Pasport raqami parol
        
        # Asosiy rol (birinchisi yoki eng yuqori darajali)
        main_role = selected_roles[0]
        if 'admin' in selected_roles:
            main_role = 'admin'
        elif 'dean' in selected_roles:
            main_role = 'dean'
        elif 'edu_dept' in selected_roles:
            main_role = 'edu_dept'
        elif 'department_head' in selected_roles:
            main_role = 'department_head'
        elif 'teacher' in selected_roles:
            main_role = 'teacher'
        
        # Dekan roli tanlangan bo'lsa, fakultetlar ro'yxati (kamida bitta majburiy)
        faculty_ids = []
        managed_department_id = None
        if 'dean' in selected_roles:
            for raw in request.form.getlist('faculty_ids'):
                try:
                    fid = int(raw)
                    if fid and fid not in faculty_ids:
                        faculty_ids.append(fid)
                except (ValueError, TypeError):
                    pass
            if not faculty_ids:
                flash(t('faculty_required_for_dean'), 'error')
                faculties = Faculty.query.all()
                departments = Department.query.order_by(Department.name).all()
                return render_template('admin/create_staff.html', faculties=faculties, departments=departments)
            faculty_id = faculty_ids[0]  # Asosiy (oldingi kodlar uchun)
        else:
            faculty_id = None
        
        # Kafedra mudiri roli tanlangan bo'lsa, kafedralar ro'yxati (kamida bitta majburiy)
        managed_department_ids = []
        if 'department_head' in selected_roles:
            for raw in request.form.getlist('managed_department_ids'):
                try:
                    did = int(raw)
                    if did and did not in managed_department_ids:
                        managed_department_ids.append(did)
                except (ValueError, TypeError):
                    pass
            if not managed_department_ids:
                flash(t('department_required_for_department_head'), 'error')
                faculties = Faculty.query.all()
                departments = Department.query.order_by(Department.name).all()
                return render_template('admin/create_staff.html', faculties=faculties, departments=departments)
            managed_department_id = managed_department_ids[0]
        
        # Email maydonini tozalash
        email_value = email.strip() if email and email.strip() else None
        
        user = User(
            login=login,
            full_name=full_name,
            role=main_role,  # Asosiy rol (eski kodlar bilan mosligi uchun)
            phone=phone.strip() if phone and phone.strip() else None,
            passport_number=passport_number,
            pinfl=pinfl.strip() if pinfl and pinfl.strip() else None,
            birth_date=birth_date,
            faculty_id=faculty_id if 'dean' in selected_roles else None,
            managed_department_id=managed_department_id if 'department_head' in selected_roles else None,
            description=description.strip() if description and description.strip() else None
        )
        
        # Email maydonini alohida o'rnatish (agar bo'sh bo'lsa, o'rnatmaymiz)
        if email_value:
            user.email = email_value
        
        user.set_password(password)
        db.session.add(user)
        
        # Commit qilish va agar email NOT NULL xatolik bo'lsa, email maydonini bo'sh qatorga o'zgartirish
        try:
            db.session.flush()  # ID olish uchun
        except Exception as e:
            error_str = str(e).lower()
            if 'email' in error_str and ('not null' in error_str or 'constraint' in error_str):
                # Database'da email NOT NULL bo'lsa, bo'sh qator qo'yamiz
                db.session.rollback()
                user.email = ''  # Bo'sh qator (database NOT NULL constraint uchun)
                db.session.add(user)
                db.session.flush()  # ID olish uchun
            else:
                raise
        
        # Bir nechta rol qo'shish
        for role in selected_roles:
            user_role = UserRole(user_id=user.id, role=role)
            db.session.add(user_role)
        
        # Kafedra mudiri uchun DepartmentHead (bir nechta kafedra)
        if 'department_head' in selected_roles and managed_department_ids:
            for dept_id in managed_department_ids:
                if Department.query.get(dept_id):
                    db.session.add(DepartmentHead(department_id=dept_id, user_id=user.id))
        # Dekan uchun UserFaculty (bir nechta fakultet)
        if 'dean' in selected_roles and faculty_ids:
            for fid in faculty_ids:
                if Faculty.query.get(fid):
                    db.session.add(UserFaculty(user_id=user.id, faculty_id=fid))
        
        db.session.commit()
        
        flash(t('staff_created', full_name=user.full_name), 'success')
        return redirect(url_for('admin.staff'))
    
    faculties = Faculty.query.all()
    departments = Department.query.order_by(Department.name).all()
    return render_template('admin/create_staff.html', faculties=faculties, departments=departments)


@bp.route('/staff/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
@permission_required('edit_staff')
def edit_staff(id):
    """Xodimni tahrirlash (bir nechta rol bilan)"""
    user = User.query.get_or_404(id)
    if getattr(user, 'is_superadmin', False) and not getattr(current_user, 'is_superadmin', False):
        flash(t('only_superadmin_can_modify'), 'error')
        return redirect(url_for('admin.staff'))
    # Faqat xodimlar (talaba emas)
    if user.role == 'student':
        flash(t('user_not_staff'), 'error')
        return redirect(url_for('admin.students'))
    
    # Foydalanuvchining mavjud rollarini olish (DepartmentHead va UserFaculty bo'yicha ham)
    existing_roles = [ur.role for ur in user.roles_list.all()] if user.roles_list.count() > 0 else ([user.role] if user.role else [])
    if DepartmentHead.query.filter_by(user_id=user.id).count() > 0 and 'department_head' not in existing_roles:
        existing_roles.append('department_head')
    if UserFaculty.query.filter_by(user_id=user.id).count() > 0 and 'dean' not in existing_roles:
        existing_roles.append('dean')
    staff_managed_department_ids = [link.department_id for link in DepartmentHead.query.filter_by(user_id=user.id).all()]
    staff_faculty_ids = [link.faculty_id for link in UserFaculty.query.filter_by(user_id=user.id).all()]
    
    if request.method == 'POST':
        login = request.form.get('login')
        # Login majburiy (xodimlar uchun)
        if not login:
            flash(t('login_required_field'), 'error')
            faculties = Faculty.query.all()
            departments = Department.query.order_by(Department.name).all()
            return render_template('admin/edit_staff.html', user=user, existing_roles=existing_roles, faculties=faculties, departments=departments, staff_managed_department_ids=staff_managed_department_ids, staff_faculty_ids=staff_faculty_ids)
        
        # Login unikalligi (boshqa foydalanuvchida bo'lmasligi kerak)
        existing_user_with_login = User.query.filter_by(login=login).first()
        if existing_user_with_login and existing_user_with_login.id != user.id:
            flash(t('login_already_exists'), 'error')
            faculties = Faculty.query.all()
            return render_template('admin/edit_staff.html', user=user, existing_roles=existing_roles, faculties=faculties, departments=departments, staff_managed_department_ids=staff_managed_department_ids, staff_faculty_ids=staff_faculty_ids)
        
        user.login = login
        email = request.form.get('email')
        # Email ixtiyoriy, lekin agar kiritilgan bo'lsa, unikallikni tekshirish
        if email:
            existing_user_with_email = User.query.filter_by(email=email).first()
            if existing_user_with_email and existing_user_with_email.id != user.id:
                flash(t('email_already_exists'), 'error')
                faculties = Faculty.query.all()
                return render_template('admin/edit_staff.html', user=user, existing_roles=existing_roles, faculties=faculties, departments=departments, staff_managed_department_ids=staff_managed_department_ids, staff_faculty_ids=staff_faculty_ids)
        # Email maydonini tozalash va o'rnatish
        email_value = email.strip() if email and email.strip() else None
        user.email = email_value if email_value else None
        user.full_name = (request.form.get('full_name') or '').strip().upper()
        user.phone = request.form.get('phone', '').strip() or None
        passport_number = request.form.get('passport_number', '').strip()
        pinfl = request.form.get('pinfl', '').strip()
        birth_date_str = request.form.get('birth_date', '').strip()
        description = request.form.get('description', '').strip()
        
        # Pasport raqamini katta harfga o'zgartirish
        if passport_number:
            passport_number = passport_number.upper()
        user.passport_number = passport_number
        
        # Tug'ilgan sanani parse qilish (yyyy-mm-dd)
        if birth_date_str:
            try:
                user.birth_date = datetime.strptime(birth_date_str, '%Y-%m-%d').date()
            except ValueError:
                flash(t('birthdate_invalid_format'), 'error')
                faculties = Faculty.query.all()
                return render_template('admin/edit_staff.html', user=user, existing_roles=existing_roles, faculties=faculties, departments=departments, staff_managed_department_ids=staff_managed_department_ids, staff_faculty_ids=staff_faculty_ids)
        else:
            user.birth_date = None
        
        user.pinfl = pinfl if pinfl else None
        user.description = description if description else None
        
        # Bir nechta rol tanlash
        selected_roles = request.form.getlist('roles')
        
        if not selected_roles:
            flash(t('at_least_one_role_required'), 'error')
            faculties = Faculty.query.all()
            return render_template('admin/edit_staff.html', user=user, existing_roles=existing_roles, faculties=faculties, departments=departments, staff_managed_department_ids=staff_managed_department_ids, staff_faculty_ids=staff_faculty_ids)
        
        # Asosiy rol (eng yuqori darajali)
        main_role = selected_roles[0]
        if 'admin' in selected_roles:
            main_role = 'admin'
        elif 'dean' in selected_roles:
            main_role = 'dean'
        elif 'edu_dept' in selected_roles:
            main_role = 'edu_dept'
        elif 'department_head' in selected_roles:
            main_role = 'department_head'
        elif 'teacher' in selected_roles:
            main_role = 'teacher'
        
        user.role = main_role
        
        # Dekan roli tanlangan bo'lsa, fakultetlar ro'yxati (kamida bitta majburiy)
        if 'dean' in selected_roles:
            faculty_ids = []
            for raw in request.form.getlist('faculty_ids'):
                try:
                    fid = int(raw)
                    if fid and fid not in faculty_ids:
                        faculty_ids.append(fid)
                except (ValueError, TypeError):
                    pass
            if not faculty_ids:
                flash(t('faculty_required_for_dean'), 'error')
                faculties = Faculty.query.all()
                departments = Department.query.order_by(Department.name).all()
                return render_template('admin/edit_staff.html', user=user, existing_roles=existing_roles, faculties=faculties, departments=departments, staff_managed_department_ids=staff_managed_department_ids, staff_faculty_ids=staff_faculty_ids)
            user.faculty_id = faculty_ids[0]
            UserFaculty.query.filter_by(user_id=user.id).delete(synchronize_session=False)
            for fid in faculty_ids:
                if Faculty.query.get(fid):
                    db.session.add(UserFaculty(user_id=user.id, faculty_id=fid))
        else:
            user.faculty_id = None
            UserFaculty.query.filter_by(user_id=user.id).delete(synchronize_session=False)
        
        # Kafedra mudiri roli tanlangan bo'lsa, kafedralar ro'yxati (kamida bitta majburiy)
        managed_department_ids = []
        if 'department_head' in selected_roles:
            for raw in request.form.getlist('managed_department_ids'):
                try:
                    did = int(raw)
                    if did and did not in managed_department_ids:
                        managed_department_ids.append(did)
                except (ValueError, TypeError):
                    pass
            if not managed_department_ids:
                faculties = Faculty.query.all()
                departments = Department.query.order_by(Department.name).all()
                flash(t('department_required_for_department_head'), 'error')
                return render_template('admin/edit_staff.html', user=user, existing_roles=existing_roles, faculties=faculties, departments=departments, staff_managed_department_ids=staff_managed_department_ids, staff_faculty_ids=staff_faculty_ids)
            user.managed_department_id = managed_department_ids[0]
            DepartmentHead.query.filter_by(user_id=user.id).delete(synchronize_session=False)
            for dept_id in managed_department_ids:
                if Department.query.get(dept_id):
                    db.session.add(DepartmentHead(department_id=dept_id, user_id=user.id))
        else:
            user.managed_department_id = None
            DepartmentHead.query.filter_by(user_id=user.id).delete(synchronize_session=False)
        
        # Rollarni yangilash
        # Eski rollarni o'chirish
        UserRole.query.filter_by(user_id=user.id).delete()
        
        # Yangi rollarni qo'shish
        for role in selected_roles:
            user_role = UserRole(user_id=user.id, role=role)
            db.session.add(user_role)
        
        # Commit qilish va agar email NOT NULL xatolik bo'lsa, email maydonini bo'sh qatorga o'zgartirish
        try:
            db.session.commit()
        except Exception as e:
            error_str = str(e).lower()
            if 'email' in error_str and ('not null' in error_str or 'constraint' in error_str):
                # Database'da email NOT NULL bo'lsa, bo'sh qator qo'yamiz
                db.session.rollback()
                user.email = ''  # Bo'sh qator (database NOT NULL constraint uchun)
                db.session.commit()
            else:
                raise
        
        flash(t('staff_updated', full_name=user.full_name), 'success')
        return redirect(url_for('admin.staff'))
    
    faculties = Faculty.query.all()
    departments = Department.query.order_by(Department.name).all()
    return render_template('admin/edit_staff.html', user=user, existing_roles=existing_roles, faculties=faculties, departments=departments, staff_managed_department_ids=staff_managed_department_ids, staff_faculty_ids=staff_faculty_ids)


# ==================== FAKULTETLAR ====================
@bp.route('/faculties')
@login_required
@admin_required
@permission_required('view_faculties')
def faculties():
    search = request.args.get('search', '')
    faculties_query = Faculty.query
    
    if search:
        faculties_query = faculties_query.filter(
            (Faculty.name.ilike(f'%{search}%')) |
            (Faculty.code.ilike(f'%{search}%'))
        )
    
    faculties = faculties_query.order_by(Faculty.name).all()
    
    # Har bir fakultet uchun masul dekanlar va statistika
    faculty_deans = {}
    faculty_stats = {}
    for faculty in faculties:
        # Dekanlar: faculty_id yoki UserFaculty orqali shu fakultetga biriktirilgan (barcha biriktirilgan xodimlar)
        try:
            dean_ids_this_faculty = {u.id for u in User.query.filter_by(faculty_id=faculty.id).all()}
            for uf in UserFaculty.query.filter_by(faculty_id=faculty.id).all():
                dean_ids_this_faculty.add(uf.user_id)
            deans_list = list(User.query.filter(User.id.in_(dean_ids_this_faculty)).all()) if dean_ids_this_faculty else []
        except Exception:
            deans_list = []
        faculty_deans[faculty.id] = deans_list if deans_list else None
        
        # Statistika: faol yo'nalishlar, faol guruhlar, talabalar soni
        # Faol = kamida bitta talabasi bor (talabasi yo'q guruh/yo'nalish hisobga olinmaydi)
        faculty_group_ids = [g.id for g in faculty.groups.all()]
        students_count = User.query.filter(
            User.role == 'student',
            User.group_id.in_(faculty_group_ids)
        ).count() if faculty_group_ids else 0
        # Faol guruhlar: ichida kamida bitta talaba bor
        groups_count = db.session.query(Group).join(User, (User.group_id == Group.id) & (User.role == 'student')).filter(
            Group.faculty_id == faculty.id
        ).distinct().count()
        # Faol yo'nalishlar: kamida bitta talabasi bor guruhga ega bo'lgan yo'nalishlar
        directions_count = db.session.query(Direction).join(Group, Group.direction_id == Direction.id).join(
            User, (User.group_id == Group.id) & (User.role == 'student')
        ).filter(Direction.faculty_id == faculty.id).distinct().count()
        
        faculty_stats[faculty.id] = {
            'directions': directions_count,
            'groups': groups_count,
            'students': students_count
        }
    
    return render_template('admin/faculties.html', 
                         faculties=faculties, 
                         faculty_deans=faculty_deans, 
                         faculty_stats=faculty_stats,
                         search=search)


@bp.route('/faculties/create', methods=['GET', 'POST'])
@login_required
@admin_required
@permission_required('create_faculty')
def create_faculty():
    # Dekan tanlashda barcha xodimlar ko'rsatiladi (kafedra mudiri kabi)
    all_deans_list = _get_staff_for_department_heads()
    
    if request.method == 'POST':
        name_uz = (request.form.get('name_uz') or '').strip()
        name_ru = (request.form.get('name_ru') or '').strip()
        name_en = (request.form.get('name_en') or '').strip()
        name = name_uz or name_ru or name_en or ''
        code = (request.form.get('code') or '').strip().upper()
        description_uz = (request.form.get('description_uz') or '').strip()
        description_ru = (request.form.get('description_ru') or '').strip()
        description_en = (request.form.get('description_en') or '').strip()
        description = description_uz or description_ru or description_en or None
        selected_dean_ids = request.form.getlist('dean_ids')
        if not name_uz or not name_ru or not name_en:
            flash(t('faculty_name_all_languages_required'), 'error')
            return render_template('admin/create_faculty.html', all_deans=all_deans_list, name_uz=name_uz, name_ru=name_ru, name_en=name_en)
        if not code:
            code = None  # flush dan keyin F+id bilan to'ldiramiz
        elif Faculty.query.filter_by(code=code).first():
            flash(t('code_already_exists'), 'error')
            return render_template('admin/create_faculty.html', all_deans=all_deans_list, name_uz=name_uz, name_ru=name_ru, name_en=name_en)
        faculty = Faculty(name=name, name_uz=name_uz or None, name_ru=name_ru or None, name_en=name_en or None, code=code or 'F0', description=description, description_uz=description_uz or None, description_ru=description_ru or None, description_en=description_en or None)
        db.session.add(faculty)
        db.session.flush()
        if not code or faculty.code == 'F0':
            faculty.code = 'F' + str(faculty.id)
        
        # Tanlangan xodimlarni fakultet dekani sifatida biriktirish; dekan roli qo'shiladi (xodim sahifasida check)
        for dean_id in selected_dean_ids:
            user = User.query.get(dean_id)
            if user and user in all_deans_list:
                db.session.add(UserFaculty(user_id=user.id, faculty_id=faculty.id))
                if not user.faculty_id:
                    user.faculty_id = faculty.id
                _add_dean_role_if_missing(user)
        
        db.session.commit()
        
        flash(t('faculty_created'), 'success')
        return redirect(url_for('admin.faculties'))
    
    return render_template('admin/create_faculty.html', all_deans=all_deans_list)


@bp.route('/faculties/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
@permission_required('edit_faculty')
def edit_faculty(id):
    faculty = Faculty.query.get_or_404(id)
    
    # Dekan tanlashda barcha xodimlar ko'rsatiladi
    all_deans_list = _get_staff_for_department_heads()
    
    # Joriy dekanlar: UserFaculty va faculty_id orqali shu fakultetga biriktirilgan (barcha biriktirilgan xodimlar)
    dean_ids_this_faculty = {u.id for u in User.query.filter_by(faculty_id=faculty.id).all()}
    for uf in UserFaculty.query.filter_by(faculty_id=faculty.id).all():
        dean_ids_this_faculty.add(uf.user_id)
    current_dean_ids = list(dict.fromkeys(list(dean_ids_this_faculty)))
    
    if request.method == 'POST':
        # Fakultet ma'lumotlarini yangilash
        name_uz = (request.form.get('name_uz') or '').strip()
        name_ru = (request.form.get('name_ru') or '').strip()
        name_en = (request.form.get('name_en') or '').strip()
        if not name_uz or not name_ru or not name_en:
            flash(t('faculty_name_all_languages_required'), 'error')
            return render_template('admin/edit_faculty.html',
                faculty=faculty, all_deans=all_deans_list, current_dean_ids=current_dean_ids,
                name_uz=name_uz, name_ru=name_ru, name_en=name_en,
                description_uz=request.form.get('description_uz') or '', description_ru=request.form.get('description_ru') or '', description_en=request.form.get('description_en') or '')
        faculty.name = name_uz or name_ru or name_en or faculty.name
        faculty.name_uz = name_uz or None
        faculty.name_ru = name_ru or None
        faculty.name_en = name_en or None
        new_code = (request.form.get('code') or '').strip().upper()
        if new_code:
            faculty.code = new_code
        description_uz = (request.form.get('description_uz') or '').strip()
        description_ru = (request.form.get('description_ru') or '').strip()
        description_en = (request.form.get('description_en') or '').strip()
        faculty.description = description_uz or description_ru or description_en or faculty.description
        faculty.description_uz = description_uz or None
        faculty.description_ru = description_ru or None
        faculty.description_en = description_en or None
        
        # Dekanlarni o'zgartirish: UserFaculty orqali; tanlanganlarga dekan roli, olib tashlanganlardan (boshqa fakultetda dekan bo'lmasa) olib tashlanadi
        selected_dean_ids = request.form.getlist('dean_ids')
        selected_set = {int(x) for x in selected_dean_ids if str(x).isdigit()}
        removed_ids = [uid for uid in current_dean_ids if uid not in selected_set]
        UserFaculty.query.filter_by(faculty_id=faculty.id).delete(synchronize_session=False)
        for u in User.query.filter(User.id.in_(current_dean_ids)).all():
            u.faculty_id = None if u.faculty_id == faculty.id else u.faculty_id
        for uid in removed_ids:
            _remove_dean_role_if_not_used(uid)
        for dean_id in selected_dean_ids:
            user = User.query.get(dean_id)
            if user and user in all_deans_list:
                db.session.add(UserFaculty(user_id=user.id, faculty_id=faculty.id))
                if not user.faculty_id:
                    user.faculty_id = faculty.id
                _add_dean_role_if_missing(user)
        db.session.commit()
        flash(t('faculty_updated'), 'success')
        return redirect(url_for('admin.faculties'))
    
    return render_template('admin/edit_faculty.html', 
                         faculty=faculty,
                         all_deans=all_deans_list,
                         current_dean_ids=current_dean_ids)


@bp.route('/faculties/<int:id>/delete', methods=['POST'])
@login_required
@admin_required
@permission_required('delete_faculty')
def delete_faculty(id):
    faculty = Faculty.query.get_or_404(id)
    faculty_name = faculty.name

    # Fakultetda talabalar bo'lsa o'chirish mumkin emas
    faculty_group_ids = [g.id for g in Group.query.filter_by(faculty_id=faculty.id).all()]
    students_count = User.query.filter(
        User.role == 'student',
        User.group_id.in_(faculty_group_ids)
    ).count() if faculty_group_ids else 0
    if students_count > 0:
        flash(t('faculty_has_students', students_count=students_count), 'error')
        return redirect(url_for('admin.faculties'))

    # Fakultetdagi barcha guruhlarni o'chirish (kaskad): avval bog'liqlarni, keyin guruhlarni
    groups = Group.query.filter_by(faculty_id=faculty.id).all()
    for group in groups:
        # Talabalarni guruhdan chiqarish (group_id = None)
        User.query.filter_by(group_id=group.id).update({'group_id': None}, synchronize_session=False)
        # Dars jadvali
        Schedule.query.filter_by(group_id=group.id).delete(synchronize_session=False)
        # O'qituvchi–fan biriktirishlari
        TeacherSubject.query.filter_by(group_id=group.id).delete(synchronize_session=False)
        # Darslar: guruhga bog'lanishni olib tashlash
        Lesson.query.filter_by(group_id=group.id).update({'group_id': None}, synchronize_session=False)
        # Topshiriqlar: guruhga bog'lanishni olib tashlash
        Assignment.query.filter_by(group_id=group.id).update({'group_id': None}, synchronize_session=False)
        db.session.delete(group)

    # Fakultetdagi barcha yo'nalishlar va ularning bog'liqlari
    directions = Direction.query.filter_by(faculty_id=faculty.id).all()
    for direction in directions:
        # O'quv reja bandlari
        DirectionCurriculum.query.filter_by(direction_id=direction.id).delete(synchronize_session=False)
        # Topshiriqlar va darslardan yo'nalishni olib tashlash
        Assignment.query.filter_by(direction_id=direction.id).update({'direction_id': None}, synchronize_session=False)
        Lesson.query.filter_by(direction_id=direction.id).update({'direction_id': None}, synchronize_session=False)
        db.session.delete(direction)

    # Dekanlarning fakultet bog'lanishini olib tashlash
    User.query.filter_by(faculty_id=faculty.id).update({'faculty_id': None}, synchronize_session=False)
    # E'lonlardan fakultetni olib tashlash (agar nullable bo'lsa)
    Announcement.query.filter_by(faculty_id=faculty.id).update({'faculty_id': None}, synchronize_session=False)

    db.session.delete(faculty)
    db.session.commit()
    flash(t('faculty_deleted', faculty_name=faculty_name), 'success')

    return redirect(url_for('admin.faculties'))


# ==================== KAFEDRALAR ====================
@bp.route('/departments')
@login_required
@admin_required
@permission_required('view_departments')
def departments():
    search = request.args.get('search', '')
    sort_by = request.args.get('sort', 'name')
    sort_order = request.args.get('order', 'asc') or 'asc'
    reverse = sort_order == 'desc'

    departments_query = Department.query

    # Kafedra mudiri odatda faqat o'zi boshqaradigan kafedralarni ko'radi; admin/superadmin yoki create_department bor bo'lsa barcha
    if (current_user.has_role('department_head') and not current_user.has_role('admin')
            and not getattr(current_user, 'is_superadmin', False)
            and not current_user.has_permission('create_department')):
        head_dept_ids = [r.department_id for r in DepartmentHead.query.filter_by(user_id=current_user.id).all()]
        if head_dept_ids:
            departments_query = departments_query.filter(Department.id.in_(head_dept_ids))
        else:
            departments_query = departments_query.filter(False)
    if search:
        search_term = f'%{search}%'
        # Kafedra mudiri bo'yicha qidiruv: DepartmentHead orqali
        head_dept_ids_search = [
            r[0] for r in
            db.session.query(DepartmentHead.department_id).join(User).filter(
                or_(
                    User.full_name.ilike(search_term),
                    User.login.ilike(search_term)
                )
            ).distinct().all()
        ]
        if head_dept_ids_search:
            departments_query = departments_query.filter(
                or_(
                    Department.name.ilike(search_term),
                    Department.id.in_(head_dept_ids_search)
                )
            )
        else:
            departments_query = departments_query.filter(Department.name.ilike(search_term))

    try:
        departments_list = departments_query.all()
    except Exception as e:
        if 'name_uz' in str(e) or 'name_ru' in str(e) or 'no such column' in str(e).lower() or 'does not exist' in str(e).lower():
            flash(t('department_migration_required'), 'error')
            return redirect(url_for('admin.index'))
        raise

    dept_stats = {}
    for d in departments_list:
        dept_head_links = DepartmentHead.query.filter_by(department_id=d.id).join(User).order_by(User.full_name).all()
        head_names = [(link.user.full_name or link.user.login or '-') for link in dept_head_links]
        # Fanlar soni: SubjectDepartment + eski department_id
        subject_ids_from_links = {link.subject_id for link in SubjectDepartment.query.filter_by(department_id=d.id).all()}
        subject_ids_from_old = {s.id for s in Subject.query.filter_by(department_id=d.id).all()}
        subjects_count = len(subject_ids_from_links | subject_ids_from_old)
        dept_stats[d.id] = {
            'subjects': subjects_count,
            'teachers': TeacherDepartment.query.filter_by(department_id=d.id).count(),
            'head_name': ', '.join(head_names) if head_names else '-',
            'head_names': head_names if head_names else ['-']
        }

    if sort_by == 'head':
        departments_list = sorted(departments_list, key=lambda d: (dept_stats[d.id]['head_name'] or '').upper(), reverse=reverse)
    elif sort_by == 'teachers':
        departments_list = sorted(departments_list, key=lambda d: dept_stats[d.id]['teachers'], reverse=reverse)
    elif sort_by == 'subjects':
        departments_list = sorted(departments_list, key=lambda d: dept_stats[d.id]['subjects'], reverse=reverse)
    else:
        departments_list = sorted(departments_list, key=lambda d: (d.name or '').upper(), reverse=reverse)

    # Modal uchun: barcha fanlar va o'qituvchilar, kafedraga biriktirilganlar
    all_subjects = Subject.query.order_by(Subject.name).all()
    teacher_ids = {r[0] for r in db.session.query(UserRole.user_id).filter_by(role='teacher').distinct().all()}
    teacher_ids |= {u.id for u in User.query.filter_by(role='teacher').all()}
    all_teachers = User.query.filter(User.id.in_(teacher_ids)).order_by(User.full_name).all() if teacher_ids else []
    department_links = {}
    for d in departments_list:
        # SubjectDepartment + eski department_id dan fanlarni olish
        sub_ids_from_links = {link.subject_id for link in SubjectDepartment.query.filter_by(department_id=d.id).all()}
        sub_ids_from_old = {s.id for s in d.subjects.all()}
        sub_ids = list(sub_ids_from_links | sub_ids_from_old)
        teach_ids = [r.teacher_id for r in TeacherDepartment.query.filter_by(department_id=d.id).all()]
        department_links[d.id] = {'subject_ids': sub_ids, 'teacher_ids': teach_ids}
    return render_template('admin/departments.html',
                         departments=departments_list,
                         dept_stats=dept_stats,
                         search=search,
                         sort_by=sort_by,
                         sort_order=sort_order,
                         all_subjects=all_subjects,
                         all_teachers=all_teachers,
                         department_links=department_links)


def _get_staff_for_department_heads():
    """Barcha xodimlar (talabalar va superadminlarsiz) – kafedra mudiri tanlash uchun."""
    all_users = User.query.order_by(User.full_name).all()
    return [u for u in all_users if 'student' not in u.get_roles() and not getattr(u, 'is_superadmin', False)]


def _add_dean_role_if_missing(user):
    """Xodimga dekan roli qo'shish (session commit qilinmaydi)."""
    if user and not user.has_role('dean'):
        db.session.add(UserRole(user_id=user.id, role='dean'))


def _remove_dean_role_if_not_used(user_id):
    """Agar xodim hech qaysi fakultetda dekan bo'lmasa, dekan rolini olib tashlash."""
    if UserFaculty.query.filter_by(user_id=user_id).first():
        return
    u = User.query.get(user_id)
    if u and u.faculty_id is not None:
        return
    UserRole.query.filter_by(user_id=user_id, role='dean').delete(synchronize_session=False)


@bp.route('/departments/create', methods=['GET', 'POST'])
@login_required
@admin_required
@permission_required('create_department')
def create_department():
    staff_list = _get_staff_for_department_heads()
    if request.method == 'POST':
        name_uz = request.form.get('name_uz', '').strip()
        name_ru = request.form.get('name_ru', '').strip()
        name_en = request.form.get('name_en', '').strip()
        if not name_uz or not name_ru or not name_en:
            flash(t('department_name_all_languages_required'), 'error')
            return render_template('admin/create_department.html', staff_list=staff_list,
                name_uz=request.form.get('name_uz'), name_ru=request.form.get('name_ru'), name_en=request.form.get('name_en'))
        dept = Department(name=name_uz, name_uz=name_uz, name_ru=name_ru, name_en=name_en)
        db.session.add(dept)
        db.session.commit()
        head_ids = request.form.getlist('head_ids')
        seen = set()
        for uid in head_ids:
            try:
                user_id = int(uid)
            except (ValueError, TypeError):
                continue
            if user_id in seen:
                continue
            user = User.query.get(user_id)
            if user and user in staff_list:
                seen.add(user_id)
                db.session.add(DepartmentHead(department_id=dept.id, user_id=user_id))
                if not user.has_role('department_head'):
                    user.add_role('department_head')
        db.session.commit()
        flash(t('department_created', name=name_uz), 'success')
        return redirect(url_for('admin.departments'))
    return render_template('admin/create_department.html', staff_list=staff_list)


@bp.route('/api/translate-department-name', methods=['POST'])
@login_required
@admin_required
def api_translate_department_name():
    """Matnni boshqa tillarga tarjima qilish (kafedra nomi sinxronlash)."""
    data = request.get_json(silent=True) or {}
    text = (data.get('text') or '').strip()
    source_lang = (data.get('source_lang') or '').lower()
    if not text or source_lang not in ('uz', 'ru', 'en'):
        return jsonify({'ok': False, 'error': 'invalid_params'}), 400
    try:
        from deep_translator import GoogleTranslator
        result = {'uz': '', 'ru': '', 'en': ''}
        result[source_lang] = text
        targets = [l for l in ('uz', 'ru', 'en') if l != source_lang]
        for target in targets:
            try:
                result[target] = GoogleTranslator(source=source_lang, target=target).translate(text) or ''
            except Exception:
                result[target] = ''
        return jsonify({'ok': True, 'translations': result})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@bp.route('/departments/<int:id>/assign', methods=['POST'])
@login_required
@admin_required
@permission_required('edit_department')
def assign_department(id):
    """Kafedraga fan va o'qituvchilarni biriktirish/olib tashlash"""
    dept = Department.query.get_or_404(id)
    if current_user.has_role('department_head') and not current_user.has_role('admin') and not getattr(current_user, 'is_superadmin', False):
        if current_user.managed_department_id != dept.id and not DepartmentHead.query.filter_by(department_id=dept.id, user_id=current_user.id).first():
            flash(t('no_access_permission'), 'error')
            return redirect(url_for('admin.departments'))
    checked_subject_ids = set()
    for raw in request.form.getlist('subject_ids'):
        try:
            checked_subject_ids.add(int(raw))
        except (ValueError, TypeError):
            pass
    checked_teacher_ids = set()
    for raw in request.form.getlist('teacher_ids'):
        try:
            checked_teacher_ids.add(int(raw))
        except (ValueError, TypeError):
            pass
    # Fanlar: SubjectDepartment orqali qo'shish/olib tashlash
    existing_subject_ids = {link.subject_id for link in SubjectDepartment.query.filter_by(department_id=dept.id).all()}
    # Eski department_id dan ham olish
    existing_subject_ids |= {s.id for s in Subject.query.filter_by(department_id=dept.id).all()}
    to_remove_subjects = existing_subject_ids - checked_subject_ids
    to_add_subjects = checked_subject_ids - existing_subject_ids
    # Olib tashlash
    for sub_id in to_remove_subjects:
        SubjectDepartment.query.filter_by(department_id=dept.id, subject_id=sub_id).delete(synchronize_session=False)
        # Eski department_id ni ham tozalash
        sub = Subject.query.get(sub_id)
        if sub and sub.department_id == dept.id:
            sub.department_id = None
    # Qo'shish
    for sub_id in to_add_subjects:
        sub = Subject.query.get(sub_id)
        if sub:
            # SubjectDepartment ga qo'shish
            if not SubjectDepartment.query.filter_by(department_id=dept.id, subject_id=sub_id).first():
                db.session.add(SubjectDepartment(department_id=dept.id, subject_id=sub_id))
    # O'qituvchilar: TeacherDepartment orqali qo'shish/olib tashlash
    existing = {r.teacher_id for r in TeacherDepartment.query.filter_by(department_id=dept.id).all()}
    to_remove = existing - checked_teacher_ids
    to_add = checked_teacher_ids - existing
    for tid in to_remove:
        TeacherDepartment.query.filter_by(department_id=dept.id, teacher_id=tid).delete(synchronize_session=False)
    for tid in to_add:
        if User.query.get(tid):
            db.session.add(TeacherDepartment(department_id=dept.id, teacher_id=tid))
    db.session.commit()
    flash(t('assignments_saved'), 'success')
    return redirect(url_for('admin.departments'))


@bp.route('/departments/export')
@login_required
@admin_required
@permission_required('view_departments')
def export_departments():
    """Kafedralarni Excel formatida export qilish (3 til: O'z, Ru, En)."""
    try:
        departments = Department.query.order_by(Department.name).all()
        excel_file = create_departments_excel(departments)
        filename = f"kafedralar_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        return send_file(
            excel_file,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        flash(t('export_error', error=str(e)), 'error')
        return redirect(url_for('admin.departments'))


@bp.route('/departments/import', methods=['GET', 'POST'])
@login_required
@admin_required
@permission_required('edit_department')
def import_departments():
    """Excel fayldan kafedralarni import qilish (1 ustun – platforma tili va tarjima, yoki 3 ustun – barcha tillar)."""
    if request.method == 'POST':
        if 'excel_file' not in request.files:
            flash(t('file_not_selected'), 'error')
            return redirect(url_for('admin.import_departments'))
        file = request.files['excel_file']
        if file.filename == '':
            flash(t('file_not_selected'), 'error')
            return redirect(url_for('admin.import_departments'))
        if not file.filename.endswith(('.xlsx', '.xls')):
            flash(t('only_excel_files_allowed'), 'error')
            return redirect(url_for('admin.import_departments'))
        source_lang = session.get('language', 'uz') or 'uz'
        if source_lang not in ('uz', 'ru', 'en'):
            source_lang = 'uz'
        try:
            result = import_departments_from_excel(file, source_lang=source_lang)
            if result['success']:
                if result['imported'] > 0:
                    flash(t('departments_imported', imported_count=result['imported']), 'success')
                if result['updated'] > 0:
                    flash(t('departments_updated', updated_count=result['updated']), 'success')
                if result['imported'] == 0 and result['updated'] == 0 and not result.get('errors'):
                    flash(t('no_data_imported'), 'warning')
                if result.get('errors'):
                    msg = "; ".join(result['errors'][:5])
                    if len(result['errors']) > 5:
                        msg += f" ... (+{len(result['errors']) - 5})"
                    flash(msg, 'warning')
            else:
                flash(result['errors'][0] if result.get('errors') else t('import_error', error=''), 'error')
        except Exception as e:
            flash(t('import_error', error=str(e)), 'error')
        return redirect(url_for('admin.departments'))
    return render_template('admin/import_departments.html')


@bp.route('/departments/import/sample')
@login_required
@admin_required
@permission_required('edit_department')
def download_departments_sample():
    """Kafedralar import namuna faylini yuklab olish (platforma tilida)."""
    try:
        lang = session.get('language', 'uz') or 'uz'
        if lang not in ('uz', 'ru', 'en'):
            lang = 'uz'
        sample_file = generate_departments_sample_file(lang=lang)
        filename = "kafedralar_import_namuna.xlsx"
        return send_file(
            sample_file,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        flash(t('export_error', error=str(e)), 'error')
        return redirect(url_for('admin.departments'))


@bp.route('/departments/<int:id>')
@login_required
@admin_required
@permission_required('view_departments')
def department_detail(id):
    dept = Department.query.get_or_404(id)
    if current_user.has_role('department_head') and not current_user.has_role('admin') and not getattr(current_user, 'is_superadmin', False):
        heads_this = DepartmentHead.query.filter_by(department_id=dept.id, user_id=current_user.id).first()
        if not heads_this and current_user.managed_department_id != dept.id:
            flash(t('no_access_permission'), 'error')
            return redirect(url_for('admin.departments'))
    # SubjectDepartment orqali fanlarni olish (yangi ko'p-ko'pga munosabat)
    subject_ids_from_links = [link.subject_id for link in SubjectDepartment.query.filter_by(department_id=id).all()]
    # Eski department_id orqali ham qo'shish (orqaga moslik uchun)
    subject_ids_from_old = [s.id for s in Subject.query.filter_by(department_id=id).all()]
    all_subject_ids = list(set(subject_ids_from_links + subject_ids_from_old))
    subjects = Subject.query.filter(Subject.id.in_(all_subject_ids)).order_by(Subject.name).all() if all_subject_ids else []
    teacher_memberships = TeacherDepartment.query.filter_by(department_id=id).all()
    teachers = [m.teacher for m in teacher_memberships]
    # Fanlar va o'qituvchilar ro'yxati - qo'shish uchun
    all_subjects = Subject.query.order_by(Subject.name).all()
    teacher_ids_in_dept = [m.teacher_id for m in teacher_memberships]
    teacher_user_ids = [uid[0] for uid in db.session.query(UserRole.user_id).filter_by(role='teacher').distinct().all()]
    all_teachers = User.query.filter(User.id.in_(teacher_user_ids)).order_by(User.full_name).all() if teacher_user_ids else []
    return render_template('admin/department_detail.html', department=dept, subjects=subjects, teachers=teachers,
                          all_subjects=all_subjects, all_teachers=all_teachers, teacher_ids_in_dept=teacher_ids_in_dept)


@bp.route('/departments/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
@permission_required('edit_department')
def edit_department(id):
    dept = Department.query.get_or_404(id)
    if current_user.has_role('department_head') and not current_user.has_role('admin') and not getattr(current_user, 'is_superadmin', False):
        heads_this = DepartmentHead.query.filter_by(department_id=dept.id, user_id=current_user.id).first()
        if not heads_this and current_user.managed_department_id != dept.id:
            flash(t('no_access_permission'), 'error')
            return redirect(url_for('admin.departments'))
    staff_list = _get_staff_for_department_heads()
    current_head_ids = [link.user_id for link in DepartmentHead.query.filter_by(department_id=dept.id).all()]
    if request.method == 'POST':
        name_uz = request.form.get('name_uz', '').strip()
        name_ru = request.form.get('name_ru', '').strip()
        name_en = request.form.get('name_en', '').strip()
        if not name_uz or not name_ru or not name_en:
            flash(t('department_name_all_languages_required'), 'error')
            err_head_ids = [int(x) for x in request.form.getlist('head_ids') if str(x).isdigit()]
            return render_template('admin/edit_department.html', department=dept, staff_list=staff_list,
                current_head_ids=err_head_ids,
                name_uz=name_uz or dept.name_uz, name_ru=name_ru or dept.name_ru, name_en=name_en or dept.name_en)
        dept.name = name_uz
        dept.name_uz = name_uz
        dept.name_ru = name_ru
        dept.name_en = name_en
        new_head_ids = []
        for uid in request.form.getlist('head_ids'):
            try:
                new_head_ids.append(int(uid))
            except (ValueError, TypeError):
                pass
        new_head_ids = list(dict.fromkeys(new_head_ids))
        removed_user_ids = set(current_head_ids) - set(new_head_ids)
        DepartmentHead.query.filter_by(department_id=dept.id).delete(synchronize_session=False)
        for uid in removed_user_ids:
            if DepartmentHead.query.filter_by(user_id=uid).count() == 0:
                u = User.query.get(uid)
                if u:
                    u.remove_role('department_head')
        for uid in new_head_ids:
            user = User.query.get(uid)
            if user and user in staff_list:
                db.session.add(DepartmentHead(department_id=dept.id, user_id=uid))
                if not user.has_role('department_head'):
                    user.add_role('department_head')
        db.session.commit()
        flash(t('department_updated', name=name_uz), 'success')
        return redirect(url_for('admin.departments'))
    name_uz = dept.name_uz or dept.name
    name_ru = dept.name_ru or dept.name
    name_en = dept.name_en or dept.name
    return render_template('admin/edit_department.html', department=dept, staff_list=staff_list,
        current_head_ids=current_head_ids, name_uz=name_uz, name_ru=name_ru, name_en=name_en)


@bp.route('/departments/<int:id>/delete', methods=['POST'])
@login_required
@admin_required
@permission_required('delete_department')
def delete_department(id):
    dept = Department.query.get_or_404(id)
    if current_user.has_role('department_head') and not current_user.has_role('admin') and not getattr(current_user, 'is_superadmin', False):
        if not DepartmentHead.query.filter_by(department_id=dept.id, user_id=current_user.id).first() and current_user.managed_department_id != dept.id:
            flash(t('no_access_permission'), 'error')
            return redirect(url_for('admin.departments'))
    dept_name = dept.name
    Subject.query.filter_by(department_id=id).update({'department_id': None}, synchronize_session=False)
    TeacherDepartment.query.filter_by(department_id=id).delete(synchronize_session=False)
    DepartmentHead.query.filter_by(department_id=id).delete(synchronize_session=False)
    User.query.filter_by(managed_department_id=id).update({'managed_department_id': None}, synchronize_session=False)
    db.session.delete(dept)
    db.session.commit()
    flash(t('department_deleted', name=dept_name), 'success')
    return redirect(url_for('admin.departments'))


@bp.route('/departments/<int:id>/add-subject', methods=['POST'])
@login_required
@admin_required
@permission_required('edit_department')
def add_subject_to_department(id):
    dept = Department.query.get_or_404(id)
    if current_user.has_role('department_head') and not current_user.has_role('admin') and not getattr(current_user, 'is_superadmin', False):
        if not DepartmentHead.query.filter_by(department_id=dept.id, user_id=current_user.id).first() and current_user.managed_department_id != dept.id:
            flash(t('no_access_permission'), 'error')
            return redirect(url_for('admin.departments'))
    subject_id = request.form.get('subject_id', type=int)
    if not subject_id:
        flash(t('please_select_subject'), 'error')
        return redirect(url_for('admin.department_detail', id=id))
    subj = Subject.query.get(subject_id)
    if not subj:
        flash(t('subject_not_found'), 'error')
        return redirect(url_for('admin.department_detail', id=id))
    subj.department_id = id
    db.session.commit()
    flash(t('subject_added_to_department', name=subj.name), 'success')
    return redirect(url_for('admin.department_detail', id=id))


@bp.route('/departments/<int:id>/remove-subject/<int:subject_id>', methods=['POST'])
@login_required
@admin_required
@permission_required('edit_department')
def remove_subject_from_department(id, subject_id):
    dept = Department.query.get_or_404(id)
    if current_user.has_role('department_head') and not current_user.has_role('admin') and not getattr(current_user, 'is_superadmin', False):
        if not DepartmentHead.query.filter_by(department_id=dept.id, user_id=current_user.id).first() and current_user.managed_department_id != dept.id:
            flash(t('no_access_permission'), 'error')
            return redirect(url_for('admin.departments'))
    subj = Subject.query.filter_by(id=subject_id, department_id=id).first()
    if subj:
        subj.department_id = None
        db.session.commit()
        flash(t('subject_removed_from_department', name=subj.name), 'success')
    return redirect(url_for('admin.department_detail', id=id))


@bp.route('/departments/<int:id>/add-teacher', methods=['POST'])
@login_required
@admin_required
@permission_required('edit_department')
def add_teacher_to_department(id):
    dept = Department.query.get_or_404(id)
    if current_user.has_role('department_head') and not current_user.has_role('admin') and not getattr(current_user, 'is_superadmin', False):
        if not DepartmentHead.query.filter_by(department_id=dept.id, user_id=current_user.id).first() and current_user.managed_department_id != dept.id:
            flash(t('no_access_permission'), 'error')
            return redirect(url_for('admin.departments'))
    teacher_id = request.form.get('teacher_id', type=int)
    if not teacher_id:
        flash(t('please_select_teacher'), 'error')
        return redirect(url_for('admin.department_detail', id=id))
    teacher = User.query.get(teacher_id)
    if not teacher or not teacher.has_role('teacher'):
        flash(t('teacher_not_found'), 'error')
        return redirect(url_for('admin.department_detail', id=id))
    if TeacherDepartment.query.filter_by(teacher_id=teacher_id, department_id=id).first():
        flash(t('teacher_already_in_department'), 'info')
        return redirect(url_for('admin.department_detail', id=id))
    td = TeacherDepartment(teacher_id=teacher_id, department_id=id)
    db.session.add(td)
    db.session.commit()
    flash(t('teacher_added_to_department', name=teacher.full_name), 'success')
    return redirect(url_for('admin.department_detail', id=id))


@bp.route('/departments/<int:id>/remove-teacher/<int:teacher_id>', methods=['POST'])
@login_required
@admin_required
@permission_required('edit_department')
def remove_teacher_from_department(id, teacher_id):
    dept = Department.query.get_or_404(id)
    if current_user.has_role('department_head') and not current_user.has_role('admin') and not getattr(current_user, 'is_superadmin', False):
        if not DepartmentHead.query.filter_by(department_id=dept.id, user_id=current_user.id).first() and current_user.managed_department_id != dept.id:
            flash(t('no_access_permission'), 'error')
            return redirect(url_for('admin.departments'))
    td = TeacherDepartment.query.filter_by(teacher_id=teacher_id, department_id=id).first()
    if td:
        db.session.delete(td)
        db.session.commit()
        flash(t('teacher_removed_from_department'), 'success')
    return redirect(url_for('admin.department_detail', id=id))


@bp.route('/faculties/<int:id>')
@login_required
@admin_required
@permission_required('view_faculties')
def faculty_detail(id):
    """Fakultet detail sahifasi - kurs>yo'nalish>guruh>talabalar struktura"""
    faculty = Faculty.query.get_or_404(id)
    current_lang = session.get('language', 'uz')
    
    # Masul dekanlar (barcha dekanlar)
    deans_list = User.query.join(UserRole).filter(
        UserRole.role == 'dean',
        User.faculty_id == faculty.id
    ).all()
    
    # Agar UserRole orqali topilmasa, eski usul bilan qidirish (role='dean')
    if not deans_list:
        deans_list = User.query.filter(
            User.role == 'dean',
            User.faculty_id == faculty.id
        ).all()
    
    # Agar hali ham topilmasa, get_roles() orqali qidirish
    if not deans_list:
        all_users = User.query.filter_by(faculty_id=faculty.id).all()
        deans_list = [u for u in all_users if 'dean' in u.get_roles()]
    
    # Birinchi dekan (eski kodlar bilan mosligi uchun)
    dean = deans_list[0] if deans_list else None
    
    # Filtr parametrlari
    course_filter = request.args.get('course', type=int)
    direction_filter = request.args.get('direction', type=int)
    group_filter = request.args.get('group', type=int)
    search = request.args.get('search', '')
    
    # Fakultetdagi barcha yo'nalishlarni olish va kurs va semestr bo'yicha tartiblash
    all_directions = Direction.query.filter_by(faculty_id=faculty.id).order_by(
        Direction.name
    ).all()
    
    # Fakultetdagi barcha guruhlarni olish
    all_groups = faculty.groups.order_by(Group.course_year, Group.name).all()
    
    # Filtrlash
    if course_filter:
        all_groups = [g for g in all_groups if g.course_year == course_filter]
    if direction_filter:
        all_groups = [g for g in all_groups if g.direction_id == direction_filter]
    if group_filter:
        all_groups = [g for g in all_groups if g.id == group_filter]
    
    # Fakultetdagi barcha talabalarni olish
    query = User.query.filter(User.role == 'student')
    
    # Fakultetdagi guruhlar ID lari orqali filtrlash (talabalar fakultetga guruh orqali bog'langan)
    faculty_group_ids = [g.id for g in faculty.groups.all()]
    query = query.filter(User.group_id.in_(faculty_group_ids))
    
    # Qidiruv
    if search:
        query = query.filter(User.full_name.ilike(f'%{search}%'))
    
    # Barcha talabalarni olish (agregatsiya uchun)
    all_students = query.all()
    
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
                name = group.direction.get_display_name(current_lang) or group.direction.name
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
    # main_key = (year, edu_type)
    sorted_keys = sorted(courses_dict.keys(), key=lambda k: ((k[0] if k[0] is not None else 9999), str(k[1])))
    
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
            sorted_subs = sorted(list(d_data['subtitle_parts']), key=lambda x: x) 
            d_data['subtitle'] = ", ".join(sorted_subs)
            
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
        
    # courses_list = sorted(set([g.course_year for g in faculty.groups.all()])) # Removed logical error
    
    # Yo'nalishlar Modal - har bir yo'nalish uchun uning guruhlari bilan birga ko'rib chiqish
    directions_list_data = []
    used_combinations = set()  # Dublikatlarni oldini olish uchun
    
    # 1. Guruhlari bor yo'nalishlar (har bir guruh uchun alohida yo'nalish yozuvi)
    groups_with_directions = db.session.query(
        Group.direction_id, Group.enrollment_year, Group.education_type
    ).filter(
        Group.faculty_id == faculty.id, 
        Group.direction_id.isnot(None)
    ).distinct().all()
    
    for d_id, year, e_type in groups_with_directions:
        direction = Direction.query.get(d_id)
        if direction:
            combination_key = f"{d_id}_{year}_{e_type}"
            if combination_key not in used_combinations:
                # Har bir yo'nalish-guruh kombinatsiyasi uchun formatted_direction (ta'lim shakli tilda)
                year_str = str(year) if year else "____"
                et = (e_type or "").strip().lower()
                if et in ('kunduzgi', 'sirtqi', 'kechki', 'masofaviy'):
                    edu_type_str = t('education_type_' + et)
                else:
                    edu_type_str = t('education_type_not_set') if e_type else ""
                d_name = direction.get_display_name(current_lang) or direction.name
                formatted = f"{year_str} - {direction.code} - {d_name}"
                if edu_type_str:
                    formatted += f" ({edu_type_str})"
                
                directions_list_data.append({
                    'id': direction.id,
                    'name': d_name,
                    'code': direction.code,
                    'enrollment_year': year,
                    'education_type': e_type,
                    'description': direction.description,
                    'formatted_direction': formatted
                })
                used_combinations.add(combination_key)
            
    # 2. Guruhlari bo'lmagan yo'nalishlar
    all_faculty_directions = Direction.query.filter_by(faculty_id=faculty.id).all()
    for direction in all_faculty_directions:
        # Yo'nalishda hech qanday guruh yo'qligini tekshirish
        has_groups = db.session.query(Group).filter(
            Group.direction_id == direction.id,
            Group.faculty_id == faculty.id
        ).first() is not None
        
        if not has_groups:
            d_name = direction.get_display_name(current_lang) or direction.name
            directions_list_data.append({
                'id': direction.id,
                'name': d_name,
                'code': direction.code,
                'enrollment_year': None,
                'education_type': None,
                'description': direction.description,
                'formatted_direction': f"____ - {direction.code} - {d_name}"
            })
            
    # Saralash: qabul yili (oshish tartibi), keyin kod va nom
    directions_list_data.sort(key=lambda x: ((x['enrollment_year'] or 9999), x['code'] or '', x['name'] or ''))
    
    groups_list = faculty.groups.order_by(Group.name).all()
    
    return render_template('admin/faculty_detail.html',
                         faculty=faculty,
                         dean=dean,
                         deans_list=deans_list,
                         courses_list=courses_list,
                         all_directions=all_directions, # Bu filter uchun
                         directions_list=directions_list_data, # Bu modal uchun
                         groups_list=groups_list,
                         course_filter=course_filter,
                         direction_filter=direction_filter,
                         group_filter=group_filter,
                         search=search)


# ==================== O'QITUVCHI BIRIKTIRISH ====================
@bp.route('/teacher-assign')
@login_required
@admin_required
@permission_required('view_departments')
def teacher_assign():
    """Admin: Barcha kafedralar uchun o'qituvchi biriktirish."""
    from app.models import DirectionCurriculum, Direction, TeacherDepartment
    _lang = session.get('language', 'uz')
    
    # Filter parametrlari
    filter_department = request.args.get('department_id', '', type=str)
    filter_semester = request.args.get('semester', '', type=str)
    filter_direction = request.args.get('direction_id', '', type=str)
    filter_group = request.args.get('group_id', '', type=str)
    filter_subject = request.args.get('subject_id', '', type=str)
    filter_lesson_type = request.args.get('lesson_type', '', type=str)
    filter_status = request.args.get('status', '', type=str)
    search_q = request.args.get('q', '', type=str).strip()
    
    all_departments = Department.query.order_by(Department.name).all()
    all_teachers = User.query.join(TeacherDepartment, User.id == TeacherDepartment.teacher_id).distinct().order_by(User.full_name).all()
    active_groups = Group.query.filter(Group.students.any()).all()
    
    # Filtr tanlovlari uchun
    semesters_set = set()
    directions_dict = {}
    groups_dict = {}
    subjects_dict = {}
    
    rows = []
    seen_combinations = set()
    
    for group in active_groups:
        if not group.direction_id:
            continue
        curr_query = DirectionCurriculum.query.filter(
            DirectionCurriculum.direction_id == group.direction_id,
            DirectionCurriculum.semester == (group.semester or 1)
        )
        curr_items = DirectionCurriculum.filter_by_group_context(curr_query, group).all()
        direction = Direction.query.get(group.direction_id)
        if not direction:
            continue
        
        if group.semester:
            semesters_set.add(group.semester)
        if direction.id not in directions_dict:
            directions_dict[direction.id] = direction.get_display_name(_lang) or direction.name
        if group.id not in groups_dict:
            groups_dict[group.id] = group.name
        
        for item in curr_items:
            subject = item.subject
            if not subject:
                continue
            if item.subject_id not in subjects_dict:
                subjects_dict[item.subject_id] = subject.get_display_name(_lang) or subject.name
            
            department = Department.query.get(subject.department_id) if subject.department_id else None
            department_name = (department.get_display_name(_lang) or department.name) if department else ''
            
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
                subject_name = subject.get_display_name(_lang) or subject.name
                
                # Filtrlash
                if filter_department and str(subject.department_id) != filter_department:
                    continue
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
                            search_lower in teacher_name.lower() or
                            search_lower in department_name.lower()):
                        continue
                
                rows.append({
                    'curriculum_id': item.id,
                    'semester': item.semester,
                    'department_id': subject.department_id,
                    'department_name': department_name,
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
    sort_by = request.args.get('sort', 'department', type=str)
    sort_order = request.args.get('order', 'asc', type=str)
    sort_keys = {
        'department': lambda r: (r.get('department_name') or '').lower(),
        'semester': lambda r: r.get('semester', 0),
        'direction': lambda r: (r.get('direction_name') or '').lower(),
        'group': lambda r: (r.get('group_name') or '').lower(),
        'subject': lambda r: (r.get('subject_name') or '').lower(),
        'lesson_type': lambda r: (r.get('lesson_type') or '').lower(),
        'hours': lambda r: r.get('hours', 0),
        'teacher': lambda r: (r.get('teacher_name') or '').lower(),
    }
    key_fn = sort_keys.get(sort_by, sort_keys['department'])
    rows = sorted(rows, key=key_fn, reverse=(sort_order == 'desc'))
    
    semesters_list = sorted(list(semesters_set))
    directions_list = sorted(directions_dict.items(), key=lambda x: x[1].lower())
    groups_list = sorted(groups_dict.items(), key=lambda x: x[1].lower())
    subjects_list = sorted(subjects_dict.items(), key=lambda x: x[1].lower())
    
    return render_template('admin/teacher_assign.html',
        rows=rows,
        departments=all_departments,
        teachers=all_teachers,
        current_lang=_lang,
        sort_by=sort_by,
        sort_order=sort_order,
        semesters=semesters_list,
        directions=directions_list,
        groups=groups_list,
        subjects=subjects_list,
        lesson_types_choices=['maruza', 'amaliyot', 'laboratoriya', 'seminar'],
        filter_department=filter_department,
        filter_semester=filter_semester,
        filter_direction=filter_direction,
        filter_group=filter_group,
        filter_subject=filter_subject,
        filter_lesson_type=filter_lesson_type,
        filter_status=filter_status,
        search_q=search_q
    )


@bp.route('/teacher-assign/save', methods=['POST'])
@login_required
@admin_required
@permission_required('view_departments')
def teacher_assign_save():
    """Admin: O'qituvchi saqlash."""
    subject_id = request.form.get('subject_id', type=int)
    group_id = request.form.get('group_id', type=int)
    lesson_type = request.form.get('lesson_type', '')
    teacher_id = request.form.get('teacher_id', type=int)
    
    if not subject_id or not group_id or not lesson_type:
        flash(t('missing_required_fields'), 'error')
        return redirect(url_for('admin.teacher_assign'))
    
    lesson_type_map = {
        'maruza': ['maruza', 'ma\'ruza', 'lecture'],
        'amaliyot': ['amaliyot', 'laboratoriya', 'kurs_ishi', 'lab', 'practice'],
        'laboratoriya': ['laboratoriya', 'lab', 'amaliyot'],
        'seminar': ['seminar'],
    }
    lesson_type_variants = lesson_type_map.get(lesson_type, [lesson_type])
    existing_ts = TeacherSubject.query.filter(
        TeacherSubject.subject_id == subject_id,
        TeacherSubject.group_id == group_id,
        func.lower(TeacherSubject.lesson_type).in_([lt.lower() for lt in lesson_type_variants])
    ).first()
    
    if teacher_id:
        if existing_ts:
            existing_ts.teacher_id = teacher_id
        else:
            new_ts = TeacherSubject(
                teacher_id=teacher_id,
                subject_id=subject_id,
                group_id=group_id,
                lesson_type=lesson_type
            )
            db.session.add(new_ts)
        flash(t('teacher_assigned_success'), 'success')
    else:
        if existing_ts:
            db.session.delete(existing_ts)
            flash(t('teacher_removed_success'), 'success')
    
    db.session.commit()
    return redirect(url_for('admin.teacher_assign', **request.args.to_dict()))


# ==================== YO'NALISHLAR ====================



@bp.route('/directions/<int:id>/<int:year>/<string:education_type>/groups')
@login_required
@admin_required
@permission_required('manage_groups')
def direction_groups_with_params(id, year, education_type):
    """Yo'nalish guruhlari sahifasi - qabul yili va ta'lim shakli bilan"""
    direction = Direction.query.get_or_404(id)
    
    # Berilgan qabul yili va ta'lim shakli bo'yicha guruhlar
    groups = Group.query.filter_by(
        direction_id=direction.id,
        enrollment_year=year,
        education_type=education_type
    ).order_by(Group.course_year, Group.name).all()
    
    if not groups:
        flash(t('no_groups_for_year_education_type', year=year, education_type=education_type), 'error')
        return redirect(url_for('admin.direction_detail', id=id))
    
    # Har bir guruh uchun talabalar soni
    group_stats = {}
    for group in groups:
        group_stats[group.id] = group.students.count()
    
    return render_template('admin/direction_detail.html',
                         direction=direction,
                         groups=groups,
                         group_stats=group_stats,
                         enrollment_year=year,
                         education_type=education_type)


@bp.route('/directions/<int:id>/curriculum')
@bp.route('/directions/<int:id>/<int:year>/<string:education_type>/curriculum')
@login_required
@admin_required
@permission_required('view_curriculum')
def direction_curriculum(id, year=None, education_type=None):
    """Yo'nalish o'quv rejasi"""
    direction = Direction.query.get_or_404(id)
    
    # Berilgan qabul yili va ta'lim shakli bo'yicha filterlash
    if year and education_type:
        groups = Group.query.filter_by(
            direction_id=direction.id,
            enrollment_year=year,
            education_type=education_type
        ).all()
        
        if not groups:
            flash(t('no_groups_for_year_education_type', year=year, education_type=education_type), 'warning')
            # Redirect to general view if specific view has no groups
            return redirect(url_for('admin.direction_curriculum', id=id))
            
        curriculum_items = direction.curriculum_items.filter_by(
            enrollment_year=year,
            education_type=education_type
        ).join(Subject).order_by(DirectionCurriculum.semester, Subject.name).all()
        
        # Pass enrollment_year and education_type to template
        enrollment_year = year
        education_type = education_type
    else:
        # Umumiy ko'rinish (agar yili va shakli berilmagan bo'sa)
        groups = Group.query.filter_by(direction_id=direction.id).order_by(Group.name).all()
        curriculum_items = direction.curriculum_items.join(Subject).order_by(
            DirectionCurriculum.semester,
            Subject.name
        ).all()
        enrollment_year = None
        education_type = None

    # Barcha fanlar (dropdown uchun)
    all_subjects = Subject.query.order_by(Subject.name).all()
    
    # O'quv reja elementlari (semestr bo'yicha guruhlangan)
    curriculum_by_semester = {}
    semester_totals = {}
    semester_auditoriya = {}
    semester_mustaqil = {}
    total_hours = 0
    total_credits = 0
    
    for item in curriculum_items:
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
        
        item_hours = (item.hours_maruza or 0) + (item.hours_amaliyot or 0) + \
                     (item.hours_laboratoriya or 0) + (item.hours_seminar or 0) + \
                     (item.hours_mustaqil or 0)
        total_hours += item_hours
        total_credits += (item_hours / 30)
        
        # Semestr jami hisob-kitoblari
        semester_totals[semester]['hours'] += item_hours
        semester_totals[semester]['credits'] += (item_hours / 30)
        semester_mustaqil[semester] += (item.hours_mustaqil or 0)
    
    return render_template('admin/direction_curriculum.html',
                         direction=direction,
                         groups=groups,
                         all_subjects=all_subjects,
                         curriculum_items=curriculum_items,
                         curriculum_by_semester=curriculum_by_semester,
                         semester_totals=semester_totals,
                         semester_auditoriya=semester_auditoriya,
                         semester_mustaqil=semester_mustaqil,
                         total_hours=total_hours,
                         total_credits=total_credits,
                         enrollment_year=enrollment_year,
                         education_type=education_type)


@bp.route('/directions/<int:id>/curriculum/export')
@bp.route('/directions/<int:id>/<int:year>/<string:education_type>/curriculum/export')
@login_required
@admin_required
@permission_required('edit_curriculum')
def export_curriculum(id, year=None, education_type=None):
    """O'quv rejani Excel formatida export qilish"""
    from app.utils.excel_export import create_curriculum_excel
    
    direction = Direction.query.get_or_404(id)
    
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
@admin_required
@permission_required('edit_curriculum')
def import_curriculum(id, year=None, education_type=None):
    """O'quv rejani Excel fayldan import qilish"""
    from app.utils.excel_import import import_curriculum_from_excel
    
    direction = Direction.query.get_or_404(id)
    
    if request.method == 'POST':
        if 'file' not in request.files:
            flash(t('file_not_selected'), 'error')
            if year and education_type:
                return redirect(url_for('admin.direction_curriculum', id=id, year=year, education_type=education_type))
            return redirect(url_for('admin.direction_curriculum', id=id))
        
        file = request.files['file']
        if file.filename == '':
            flash(t('file_not_selected'), 'error')
            if year and education_type:
                return redirect(url_for('admin.direction_curriculum', id=id, year=year, education_type=education_type))
            return redirect(url_for('admin.direction_curriculum', id=id))
        
        if not file.filename.endswith(('.xlsx', '.xls')):
            flash(t('only_xlsx_or_xls_allowed'), 'error')
            if year and education_type:
                return redirect(url_for('admin.direction_curriculum', id=id, year=year, education_type=education_type))
            return redirect(url_for('admin.direction_curriculum', id=id))
        
        # Import funksiyasiga yil va ta'lim shaklini ham uzatish
        result = import_curriculum_from_excel(file, direction.id, enrollment_year=year, education_type=education_type)
        
        if result['success']:
            if result['imported'] > 0 or result['updated'] > 0:
                message = f"Muvaffaqiyatli! {result['imported']} ta yangi qo'shildi, {result['updated']} ta yangilandi."
                if result.get('subjects_created', 0) > 0:
                    message += f" {result['subjects_created']} ta yangi fan yaratildi."
                if result['errors']:
                    message += f" {len(result['errors'])} ta xatolik yuz berdi."
                flash(message, 'success' if not result['errors'] else 'warning')
            else:
                flash(t('no_changes_made'), 'info')
            
            if result['errors']:
                for error in result['errors'][:10]:  # Faqat birinchi 10 ta xatolikni ko'rsatish
                    flash(error, 'error')
        else:
            flash(t('import_error', error=', '.join(result['errors'])), 'error')
        
        if year and education_type:
            return redirect(url_for('admin.direction_curriculum', id=id, year=year, education_type=education_type))
        return redirect(url_for('admin.direction_curriculum', id=id))
    
    return render_template('admin/import_curriculum.html', 
                         direction=direction,
                         enrollment_year=year,
                         education_type=education_type)


@bp.route('/directions/<int:id>/curriculum/import/sample')
@login_required
@admin_required
@permission_required('edit_curriculum')
def download_curriculum_sample(id):
    """O'quv reja import uchun namuna fayl yuklab olish (tanlangan til bo'yicha)"""
    from app.utils.excel_import import generate_curriculum_sample_file
    direction = Direction.query.get_or_404(id)
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
@admin_required
@permission_required('edit_curriculum')
def direction_subjects(id, year=None, education_type=None):
    """Yo'nalish fanlari sahifasi - qabul yili va ta'lim shakli bilan (Context aware)"""
    direction = Direction.query.get_or_404(id)
    
    # Agar yil yoki ta'lim shakli berilmagan bo'lsa, redirect qilamiz
    if not year or not education_type:
        first_group = Group.query.filter_by(direction_id=id).order_by(Group.enrollment_year.desc()).first()
        if first_group and first_group.enrollment_year and first_group.education_type:
            return redirect(url_for('admin.direction_subjects', id=id, year=first_group.enrollment_year, education_type=first_group.education_type))
        else:
            # Agar guruhlar bo'lmasa, shunchaki xabar beramiz yoki empty template chiqaramiz
            flash(t('direction_no_groups'), 'warning')
            return redirect(url_for('admin.directions'))

    # Berilgan qabul yili va ta'lim shakli bo'yicha guruhlar
    # Berilgan qabul yili va ta'lim shakli bo'yicha guruhlar (faqat talabasi bor guruhlar)
    all_groups = Group.query.filter_by(
        direction_id=direction.id,
        enrollment_year=year,
        education_type=education_type
    ).all()
    
    # Talabasi bor yoki o'qituvchi biriktirilgan guruhlarni olamiz
    groups = []
    for g in all_groups:
        has_students = g.students.count() > 0
        has_teachers = TeacherSubject.query.filter_by(group_id=g.id).first() is not None
        if has_students or has_teachers:
            groups.append(g)
    
    if not groups and not all_groups:
        flash(t('no_groups_for_year_education_type', year=year, education_type=education_type), 'error')
        return redirect(url_for('admin.direction_subjects', id=id))
    
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
            return redirect(url_for('admin.direction_subjects', id=id, year=year, education_type=education_type))
        
        # Bu semestr uchun faol guruhlar
        active_semester_groups = groups_by_semester.get(semester, [])
        if not active_semester_groups:
            flash(t('no_active_groups_for_semester', semester=semester), 'error')
            return redirect(url_for('admin.direction_subjects', id=id, year=year, education_type=education_type))

        # Semestrdagi barcha fanlar uchun o'qituvchilarni yangilash
        for item in direction.curriculum_items.filter_by(
            semester=semester,
            enrollment_year=year,
            education_type=education_type
        ).all():
            # Faqat shu semestrda aktiv bo'lgan guruhlar uchun saqlash
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
                    # Agar o'qituvchi tanlanmagan bo'lsa, mavjud biriktirishni o'chirish
                    if teacher_subject:
                        db.session.delete(teacher_subject)
                
                # Amaliyot/Lobaratoriya/Kurs ishi o'qituvchisi (bitta o'qituvchi)
                if (item.hours_amaliyot or 0) > 0 or (item.hours_laboratoriya or 0) > 0 or (item.hours_kurs_ishi or 0) > 0:
                    # Bitta o'qituvchi tanlanadi (amaliyot, lobaratoriya va kurs ishi uchun)
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
                        # Agar o'qituvchi tanlanmagan bo'lsa, mavjud biriktirishni o'chirish
                        if teacher_subject:
                            db.session.delete(teacher_subject)
                
                # Seminar o'qituvchisi (faqat seminar soatlari bo'lsa)
                if (item.hours_seminar or 0) > 0:
                    seminar_teacher_id = request.form.get(f'teacher_seminar_{item.id}_{group.id}', type=int)
                    # Seminar uchun alohida TeacherSubject yaratish yoki topish
                    teacher_subject = TeacherSubject.query.filter_by(
                        subject_id=item.subject_id,
                        group_id=group.id,
                        lesson_type='seminar'
                    ).first()
                    
                    if seminar_teacher_id:
                        if teacher_subject:
                            teacher_subject.teacher_id = seminar_teacher_id
                        else:
                            # Seminar uchun 'seminar' lesson_type bilan yaratish
                            teacher_subject = TeacherSubject(
                                teacher_id=seminar_teacher_id,
                                subject_id=item.subject_id,
                                group_id=group.id,
                                lesson_type='seminar'
                            )
                            db.session.add(teacher_subject)
                    else:
                        # Agar o'qituvchi tanlanmagan bo'lsa, mavjud biriktirishni o'chirish
                        if teacher_subject:
                            db.session.delete(teacher_subject)
        
        db.session.commit()
        flash(t('semester_teachers_saved', semester=semester), 'success')
        return redirect(url_for('admin.direction_subjects', id=id, year=year, education_type=education_type))
    
    # O'quv rejadagi fanlar (semestr bo'yicha guruhlangan)
    subjects_by_semester = {}
    
    for item in direction.curriculum_items.filter_by(
        enrollment_year=year,
        education_type=education_type
    ).join(Subject).order_by(DirectionCurriculum.semester, Subject.name).all():
        semester = item.semester
        if semester not in subjects_by_semester:
            subjects_by_semester[semester] = []
        
        # Dars turlari va soatlari
        lessons = []
        if (item.hours_maruza or 0) > 0:
            lessons.append({
                'type': 'Maruza',
                'hours': item.hours_maruza
            })
            
        # Amaliyot, Laboratoriya va Kurs ishi birlashtiriladi
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
            # Kurs ishi soati qo'shilmaydi
            
        if practical_types:
            lessons.append({
                'type': ', '.join(practical_types),
                'hours': practical_hours
            })

        if (item.hours_seminar or 0) > 0:
            lessons.append({
                'type': 'Seminar',
                'hours': item.hours_seminar
            })
            
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
    
    return render_template('admin/direction_subjects.html',
                         direction=direction,
                         subjects_by_semester=subjects_by_semester,
                         groups_by_semester=groups_by_semester,
                         teachers=teachers,
                         enrollment_year=year,
                         education_type=education_type)
@bp.route('/directions/<int:id>/curriculum/<int:item_id>/delete', methods=['POST'])
@bp.route('/directions/<int:id>/<int:year>/<string:education_type>/curriculum/<int:item_id>/delete', methods=['POST'])
@login_required
@admin_required
@permission_required('edit_curriculum')
def delete_curriculum_item(id, item_id, year=None, education_type=None):
    """O'quv rejadagi fanni o'chirish"""
    direction = Direction.query.get_or_404(id)
    item = DirectionCurriculum.query.get_or_404(item_id)
    
    if item.direction_id != direction.id:
        flash(t('no_permission_for_operation'), 'error')
        return redirect(url_for('admin.faculties'))
    
    db.session.delete(item)
    db.session.commit()
    flash(t('subject_removed_from_curriculum'), 'success')
    if year and education_type:
        return redirect(url_for('admin.direction_curriculum', id=id, year=year, education_type=education_type))
    return redirect(url_for('admin.direction_curriculum', id=id))


@bp.route('/directions/<int:id>/curriculum/add', methods=['POST'])
@bp.route('/directions/<int:id>/<int:year>/<string:education_type>/curriculum/add', methods=['POST'])
@login_required
@admin_required
@permission_required('edit_curriculum')
def add_subject_to_curriculum(id, year=None, education_type=None):
    """O'quv rejaga fan qo'shish"""
    direction = Direction.query.get_or_404(id)
    
    subject_ids = request.form.getlist('subject_ids')
    semester = request.form.get('semester', type=int)
    
    if not subject_ids or not semester:
        flash(t('subject_and_semester_required'), 'error')
        if year and education_type:
            return redirect(url_for('admin.direction_curriculum', id=id, year=year, education_type=education_type))
        return redirect(url_for('admin.direction_curriculum', id=id))
    
    added = 0
    for subject_id in subject_ids:
        subject_id = int(subject_id)
        subject = Subject.query.get(subject_id)
        if not subject:
            continue
        
        # Takrorlanmasligini tekshirish (context-aware)
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
        return redirect(url_for('admin.direction_curriculum', id=id, year=year, education_type=education_type))
    return redirect(url_for('admin.direction_curriculum', id=id))


@bp.route('/directions/<int:id>/curriculum/update_semester/<int:semester>', methods=['POST'])
@bp.route('/directions/<int:id>/<int:year>/<string:education_type>/curriculum/update_semester/<int:semester>', methods=['POST'])
@login_required
@admin_required
@permission_required('edit_curriculum')
def update_semester_curriculum(id, semester, year=None, education_type=None):
    """Semestr o'quv rejasini yangilash"""
    direction = Direction.query.get_or_404(id)
    
    # Qidiruv parametrlarini aniqlash
    filters = {
        'direction_id': direction.id,
        'semester': semester
    }
    if year:
        filters['enrollment_year'] = year
    if education_type:
        filters['education_type'] = education_type
        
    curriculum_items = DirectionCurriculum.query.filter_by(**filters).all()
    
    updated_count = 0
    for item in curriculum_items:
        # Soatlarni yangilash
        hours_maruza = request.form.get(f'hours_maruza[{item.id}]')
        hours_amaliyot = request.form.get(f'hours_amaliyot[{item.id}]')
        hours_laboratoriya = request.form.get(f'hours_laboratoriya[{item.id}]')
        hours_seminar = request.form.get(f'hours_seminar[{item.id}]')
        hours_mustaqil = request.form.get(f'hours_mustaqil[{item.id}]')
        
        # Kurs ishi (checkbox)
        has_kurs_ishi = str(item.id) in request.form.getlist('hours_kurs_ishi')
        
        # Qiymatlarni yangilash
        item.hours_maruza = int(hours_maruza) if hours_maruza and hours_maruza.isdigit() else 0
        item.hours_amaliyot = int(hours_amaliyot) if hours_amaliyot and hours_amaliyot.isdigit() else 0
        item.hours_laboratoriya = int(hours_laboratoriya) if hours_laboratoriya and hours_laboratoriya.isdigit() else 0
        item.hours_seminar = int(hours_seminar) if hours_seminar and hours_seminar.isdigit() else 0
        item.hours_mustaqil = int(hours_mustaqil) if hours_mustaqil and hours_mustaqil.isdigit() else 0
        
        # Kurs ishi 1 soat (agar belgilangan bo'lsa)
        item.hours_kurs_ishi = 1 if has_kurs_ishi else 0
        
        # Soatlari 0 qilingan dars turlariga biriktirilgan o'qituvchilarni bekor qilish
        DirectionCurriculum.remove_teacher_assignments_for_zeroed_hours(item)
        
        updated_count += 1
        
    db.session.commit()
    flash(t('curriculum_updated', semester=semester), 'success')
    
    if year and education_type:
        return redirect(url_for('admin.direction_curriculum', id=id, year=year, education_type=education_type))
    return redirect(url_for('admin.direction_curriculum', id=id))


@bp.route('/directions/<int:id>/curriculum/<int:item_id>/replace', methods=['POST'])
@bp.route('/directions/<int:id>/<int:year>/<string:education_type>/curriculum/<int:item_id>/replace', methods=['POST'])
@login_required
@admin_required
@permission_required('edit_curriculum')
def replace_curriculum_item(id, item_id, year=None, education_type=None):
    """O'quv rejadagi fanni almashtirish"""
    direction = Direction.query.get_or_404(id)
    item = DirectionCurriculum.query.get_or_404(item_id)
    
    if item.direction_id != direction.id:
        flash(t('invalid_request'), 'error')
        return redirect(url_for('admin.direction_curriculum', id=id))

    new_subject_id = request.form.get('subject_id', type=int)
    if not new_subject_id:
        flash(t('new_subject_not_selected'), 'error')
    else:
        new_subject = Subject.query.get(new_subject_id)
        if new_subject:
            # Takrorlanmasligini tekshirish
            existing = DirectionCurriculum.query.filter_by(
                direction_id=direction.id,
                subject_id=new_subject_id,
                semester=item.semester,
                enrollment_year=item.enrollment_year,
                education_type=item.education_type
            ).first()
            
            if existing and existing.id != item.id:
                flash(t('subject_already_in_semester', subject_name=new_subject.name), 'error')
            else:
                item.subject_id = new_subject_id
                db.session.commit()
                flash(t('subject_replaced', subject_name=new_subject.name), 'success')
        else:
            flash(t('subject_not_found'), 'error')
            
    if year and education_type:
        return redirect(url_for('admin.direction_curriculum', id=id, year=year, education_type=education_type))
    
    if item.enrollment_year and item.education_type:
         return redirect(url_for('admin.direction_curriculum', id=id, year=item.enrollment_year, education_type=item.education_type))
         
    return redirect(url_for('admin.direction_curriculum', id=id))





@bp.route('/faculties/<int:id>/change_dean', methods=['GET', 'POST'])
@login_required
@admin_required
@permission_required('edit_faculty')
def change_faculty_dean(id):
    """Fakultet masul dekanlarini o'zgartirish (bir nechta dekan biriktirish mumkin). Dekan tanlashda barcha xodimlar ko'rsatiladi."""
    faculty = Faculty.query.get_or_404(id)
    
    # Barcha xodimlar (dekan tanlashda ko'rsatiladi)
    all_deans_list = _get_staff_for_department_heads()
    
    # Joriy dekanlar: UserFaculty va faculty_id orqali shu fakultetga biriktirilgan
    dean_ids_this_faculty = {u.id for u in User.query.filter_by(faculty_id=faculty.id).all()}
    for uf in UserFaculty.query.filter_by(faculty_id=faculty.id).all():
        dean_ids_this_faculty.add(uf.user_id)
    current_dean_ids = list(dict.fromkeys(list(dean_ids_this_faculty)))
    current_deans = [u for u in User.query.filter(User.id.in_(current_dean_ids)).all()]
    
    if request.method == 'POST':
        selected_dean_ids = request.form.getlist('dean_ids')
        selected_set = {int(x) for x in selected_dean_ids if str(x).isdigit()}
        removed_ids = [uid for uid in current_dean_ids if uid not in selected_set]
        UserFaculty.query.filter_by(faculty_id=faculty.id).delete(synchronize_session=False)
        for u in User.query.filter(User.id.in_(current_dean_ids)).all():
            u.faculty_id = None if u.faculty_id == faculty.id else u.faculty_id
        for uid in removed_ids:
            _remove_dean_role_if_not_used(uid)
        for dean_id in selected_dean_ids:
            user = User.query.get(dean_id)
            if user and user in all_deans_list:
                db.session.add(UserFaculty(user_id=user.id, faculty_id=faculty.id))
                if not user.faculty_id:
                    user.faculty_id = faculty.id
                _add_dean_role_if_missing(user)
        db.session.commit()
        flash(t('responsible_deans_changed'), 'success')
        return redirect(url_for('admin.faculty_detail', id=faculty.id))
    
    return render_template('admin/change_faculty_dean.html',
                         faculty=faculty,
                         all_deans=all_deans_list,
                         current_deans=current_deans,
                         current_dean_ids=current_dean_ids)


# ==================== FANLAR ====================
@bp.route('/subjects')
@login_required
@admin_required
@permission_required('view_subjects')
def subjects():
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '').strip()
    sort = request.args.get('sort', 'name').strip().lower()
    order = request.args.get('order', 'asc').strip().lower()
    if sort not in ('name', 'department'):
        sort = 'name'
    if order not in ('asc', 'desc'):
        order = 'asc'

    query = Subject.query
    if search:
        search_term = f'%{search}%'
        query = query.filter(
            or_(
                Subject.name.ilike(search_term),
                Subject.name_uz.ilike(search_term),
                Subject.name_ru.ilike(search_term),
                Subject.name_en.ilike(search_term),
            )
        )

    if sort == 'name':
        query = query.order_by(Subject.name.asc() if order == 'asc' else Subject.name.desc())
    else:
        # sort=department: order by first department name (from SubjectDepartment)
        subq = db.session.query(SubjectDepartment.subject_id, func.min(Department.name).label('min_dept')).join(Department, SubjectDepartment.department_id == Department.id).group_by(SubjectDepartment.subject_id).subquery()
        query = query.outerjoin(subq, Subject.id == subq.c.subject_id)
        if order == 'asc':
            query = query.order_by(subq.c.min_dept.asc(), Subject.name.asc())
        else:
            query = query.order_by(subq.c.min_dept.desc(), Subject.name.asc())

    subjects = query.paginate(page=page, per_page=50, error_out=False)

    if request.args.get('partial'):
        return render_template('admin/subjects_partial.html', subjects=subjects, search=search, sort=sort, order=order)
    return render_template('admin/subjects.html',
                         subjects=subjects,
                         search=search, sort=sort, order=order)


@bp.route('/subjects/migrate-translations', methods=['POST'])
@login_required
@admin_required
@permission_required('edit_subject')
def migrate_subject_translations():
    """Mavjud fanlarni ko'p tilli formatga o'tkazish (name -> name_uz va tarjima)."""
    try:
        from deep_translator import GoogleTranslator
        translator_ru = GoogleTranslator(source='uz', target='ru')
        translator_en = GoogleTranslator(source='uz', target='en')
    except ImportError:
        translator_ru = None
        translator_en = None
    
    updated_count = 0
    subjects = Subject.query.all()
    for subj in subjects:
        if subj.name and not subj.name_uz:
            subj.name_uz = subj.name
            if translator_ru and not subj.name_ru:
                try:
                    subj.name_ru = translator_ru.translate(subj.name) or subj.name
                except Exception:
                    subj.name_ru = subj.name
            if translator_en and not subj.name_en:
                try:
                    subj.name_en = translator_en.translate(subj.name) or subj.name
                except Exception:
                    subj.name_en = subj.name
            updated_count += 1
    db.session.commit()
    flash(t('subjects_migrated', count=updated_count) if updated_count else t('no_subjects_to_migrate'), 'success' if updated_count else 'info')
    return redirect(url_for('admin.subjects'))


@bp.route('/schedule/sample')
@login_required
@admin_required
@permission_required('import_schedule')
def download_schedule_sample():
    try:
        lang = session.get('language', 'uz')
        output = generate_schedule_sample_file(lang=lang)
        download_name = t('sample_filename_schedule') + ".xlsx"
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=download_name
        )
    except Exception as e:
        flash(t('template_file_creation_error', error=str(e)), 'danger')
        return redirect(url_for('admin.schedule'))

@bp.route('/schedule/import', methods=['GET', 'POST'])
@login_required
@admin_required
@permission_required('import_schedule')
def import_schedule():
    if request.method == 'POST':
        if 'file' not in request.files:
            flash(t('file_not_selected'), 'danger')
            return redirect(request.url)
            
        file = request.files['file']
        if file.filename == '':
            flash(t('file_not_selected'), 'danger')
            return redirect(request.url)
            
        if file and file.filename.endswith('.xlsx'):
            try:
                result = import_schedule_from_excel(file)
                
                if result.get('success'):
                    count = result.get('imported', 0)
                    errors = result.get('errors', [])
                    
                    if errors:
                        for error in errors[:10]:
                            flash(error, 'danger')
                        if count > 0:
                            flash(t('schedules_imported', count=count), 'warning')
                    else:
                        flash(t('schedules_imported', count=count), 'success')
                    return redirect(url_for('admin.schedule'))
                else:
                    for error in result.get('errors', []):
                        flash(error, 'danger')
            except Exception as e:
                flash(t('error_occurred', error=str(e)), 'danger')
        else:
            flash(t('only_xlsx_files_allowed'), 'danger')
            
    return render_template('admin/import_schedule.html')

@bp.route('/students/import/sample')
@login_required
@admin_required
@permission_required('import_students')
def download_sample_import():
    try:
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
        return redirect(url_for('admin.import_students'))

@bp.route('/subjects/create', methods=['GET', 'POST'])
@login_required
@admin_required
@permission_required('create_subject')
def create_subject():
    departments = Department.query.order_by(Department.name).all()
    if request.method == 'POST':
        name_uz = (request.form.get('name_uz') or '').strip()
        name_ru = (request.form.get('name_ru') or '').strip()
        name_en = (request.form.get('name_en') or '').strip()
        name = name_uz or name_ru or name_en
        department_ids = request.form.getlist('department_ids', type=int)
        if not name_uz or not name_ru or not name_en:
            flash(t('subject_name_all_languages_required'), 'error')
            return render_template('admin/create_subject.html',
                departments=departments, selected_dept_ids=department_ids,
                name_uz=name_uz, name_ru=name_ru, name_en=name_en)
        subject = Subject(
            name=name,
            name_uz=name_uz or None,
            name_ru=name_ru or None,
            name_en=name_en or None,
            code='',
            department_id=department_ids[0] if department_ids else None,
            credits=3,
            semester=1
        )
        db.session.add(subject)
        db.session.flush()
        for dept_id in department_ids:
            link = SubjectDepartment(subject_id=subject.id, department_id=dept_id)
            db.session.add(link)
        db.session.commit()
        flash(t('subject_created'), 'success')
        return redirect(url_for('admin.subjects'))
    return render_template('admin/create_subject.html', departments=departments, selected_dept_ids=[])


@bp.route('/subjects/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
@permission_required('edit_subject')
def edit_subject(id):
    subject = Subject.query.get_or_404(id)
    departments = Department.query.order_by(Department.name).all()
    # SubjectDepartment dan olish, bo'sh bo'lsa eski department_id dan
    current_dept_ids = [link.department_id for link in subject.department_links.all()]
    if not current_dept_ids and subject.department_id:
        current_dept_ids = [subject.department_id]
    if request.method == 'POST':
        name_uz = (request.form.get('name_uz') or '').strip()
        name_ru = (request.form.get('name_ru') or '').strip()
        name_en = (request.form.get('name_en') or '').strip()
        department_ids = request.form.getlist('department_ids', type=int)
        if not name_uz or not name_ru or not name_en:
            flash(t('subject_name_all_languages_required'), 'error')
            return render_template('admin/edit_subject.html', subject=subject, departments=departments,
                name_uz=name_uz, name_ru=name_ru, name_en=name_en, selected_dept_ids=department_ids)
        subject.name = name_uz or name_ru or name_en
        subject.name_uz = name_uz or None
        subject.name_ru = name_ru or None
        subject.name_en = name_en or None
        subject.department_id = department_ids[0] if department_ids else None
        SubjectDepartment.query.filter_by(subject_id=subject.id).delete()
        for dept_id in department_ids:
            link = SubjectDepartment(subject_id=subject.id, department_id=dept_id)
            db.session.add(link)
        db.session.commit()
        flash(t('subject_updated'), 'success')
        return redirect(url_for('admin.subjects'))
    return render_template('admin/edit_subject.html', subject=subject, departments=departments, selected_dept_ids=current_dept_ids)


@bp.route('/subjects/<int:id>/delete-blocked')
@login_required
@admin_required
@permission_required('delete_subject')
def subject_delete_blocked(id):
    """Fan o'quv rejada ishlatilayotgani uchun o'chirilmayapti – batafsil ko'rsatish va barcha rejalardan olib tashlash"""
    subject = Subject.query.get_or_404(id)
    curriculum_items = DirectionCurriculum.query.filter_by(subject_id=id).all()
    if not curriculum_items:
        flash(t('subject_not_in_curriculum'), 'success')
        return redirect(url_for('admin.subjects'))
    # Yo'nalish bo'yicha guruhlash, har birida (enrollment_year, education_type) ro'yxati
    by_direction = {}
    direction_ids = list({item.direction_id for item in curriculum_items if item.direction_id})
    directions_map = {d.id: d for d in Direction.query.filter(Direction.id.in_(direction_ids)).all()} if direction_ids else {}
    for item in curriculum_items:
        did = item.direction_id
        if did not in by_direction:
            by_direction[did] = []
        key = (item.enrollment_year, item.education_type)
        if key not in by_direction[did]:
            by_direction[did].append(key)
    details = []
    for did, keys in by_direction.items():
        d = directions_map.get(did)
        name = f"{d.code} – {d.name}" if d else f"ID {did}"
        parts = [f"{y or '—'} {t or '—'}" for y, t in sorted(keys, key=lambda x: (str(x[0]) or '', str(x[1]) or ''))]
        details.append((name, ", ".join(parts)))
    return render_template('admin/subject_delete_blocked.html', subject=subject, details=details)


@bp.route('/subjects/<int:id>/remove-from-curriculum', methods=['POST'])
@login_required
@admin_required
@permission_required('edit_curriculum')
def remove_subject_from_curriculum(id):
    """Fanni barcha yo'nalishlar o'quv rejasidan olib tashlash (keyin fanni o'chirish mumkin)"""
    subject = Subject.query.get_or_404(id)
    deleted = DirectionCurriculum.query.filter_by(subject_id=id).delete(synchronize_session=False)
    db.session.commit()
    flash(t('subject_removed_from_all_curriculums', subject_name=subject.name, deleted=deleted), 'success')
    return redirect(url_for('admin.subjects'))


@bp.route('/subjects/<int:id>/delete', methods=['POST'])
@login_required
@admin_required
@permission_required('delete_subject')
def delete_subject(id):
    subject = Subject.query.get_or_404(id)
    
    # Check if this subject is used in any curriculum
    curriculum_items = DirectionCurriculum.query.filter_by(subject_id=id).all()
    if curriculum_items:
        return redirect(url_for('admin.subject_delete_blocked', id=id))
    
    db.session.delete(subject)
    db.session.commit()
    flash(t('subject_deleted'), 'success')
    return redirect(url_for('admin.subjects'))


@bp.route('/subjects/export')
@login_required
@admin_required
@permission_required('export_subjects')
def export_subjects():
    """Fanlarni Excel formatida export qilish"""
    try:
        subjects = Subject.query.order_by(Subject.name).all()
        excel_file = create_subjects_excel(subjects)
        
        filename = f"fanlar_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        return send_file(
            excel_file,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        flash(t('export_error', error=str(e)), 'error')
        return redirect(url_for('admin.subjects'))


@bp.route('/subjects/import', methods=['GET', 'POST'])
@login_required
@admin_required
@permission_required('import_subjects')
def import_subjects():
    """Excel fayldan fanlarni import qilish"""
    if request.method == 'POST':
        if 'excel_file' not in request.files:
            flash(t('file_not_selected'), 'error')
            return redirect(url_for('admin.subjects'))
        
        file = request.files['excel_file']
        if file.filename == '':
            flash(t('file_not_selected'), 'error')
            return redirect(url_for('admin.subjects'))
        
        if not file.filename.endswith(('.xlsx', '.xls')):
            flash(t('only_excel_files_allowed'), 'error')
            return redirect(url_for('admin.subjects'))
        
        try:
            source_lang = session.get('language', 'uz') or 'uz'
            if source_lang not in ('uz', 'ru', 'en'):
                source_lang = 'uz'
            result = import_subjects_from_excel(file, source_lang=source_lang)

            if result['success']:
                if result['imported'] > 0:
                    flash(t('subjects_imported', imported_count=result['imported']), 'success')
                if result['updated'] > 0:
                    flash(t('subjects_updated', updated_count=result['updated']), 'success')
                if result['imported'] == 0 and result['updated'] == 0:
                    flash(t('no_subjects_imported'), 'warning')
                
                if result['errors']:
                    error_msg = f"Xatolar ({len(result['errors'])}): " + "; ".join(result['errors'][:5])
                    if len(result['errors']) > 5:
                        error_msg += f" va yana {len(result['errors']) - 5} ta xato"
                    flash(error_msg, 'warning')
            else:
                flash(t('import_error', error=result['errors'][0] if result['errors'] else 'Noma`lum xatolik'), 'error')
                
        except ImportError as e:
            flash(t('excel_import_not_working', error=str(e)), 'error')
        except Exception as e:
            flash(t('import_error', error=str(e)), 'error')
        
        return redirect(url_for('admin.subjects'))
    
    return render_template('admin/import_subjects.html')


@bp.route('/subjects/import/sample')
@login_required
@admin_required
@permission_required('import_subjects')
def download_subjects_sample():
    """Fanlarni import qilish uchun namuna Excel faylni yuklab berish (platforma tilida)."""
    try:
        lang = session.get('language', 'uz') or 'uz'
        if lang not in ('uz', 'ru', 'en'):
            lang = 'uz'
        sample_file = generate_subjects_sample_file(lang=lang)
        filename = "fanlar_import_namuna.xlsx"
        return send_file(
            sample_file,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        flash(t('template_file_download_error', error=str(e)), 'error')
        return redirect(url_for('admin.subjects'))


# ==================== HISOBOTLAR ====================
@bp.route('/reports')
@login_required
@admin_required
@permission_required('view_reports')
def reports():
    from sqlalchemy import func
    
    stats = {
        'total_users': User.query.count(),
        'total_students': User.query.filter_by(role='student').count(),
        'total_teachers': db.session.query(UserRole.user_id).filter_by(role='teacher').distinct().count() or User.query.filter_by(role='teacher').count() or len([u for u in User.query.all() if 'teacher' in u.get_roles()]),
        'total_faculties': Faculty.query.count(),
        'total_groups': Group.query.count(),
        'total_subjects': Subject.query.count(),
        'active_users': User.query.filter_by(is_active=True).count(),
    }
    
    # Fakultetlar bo'yicha statistika
    faculty_stats = []
    for faculty in Faculty.query.all():
        faculty_stats.append({
            'faculty': faculty,
            'groups': faculty.groups.count(),
            'subjects': Subject.query.join(TeacherSubject).join(Group).filter(
                Group.faculty_id == faculty.id
            ).distinct().count(),
            'students': User.query.join(Group).filter(Group.faculty_id == faculty.id).count()
        })
    
    # Guruhlar bo'yicha talabalar
    groups = db.session.query(
        Group.name,
        func.count(User.id)
    ).outerjoin(User, User.group_id == Group.id).group_by(Group.id).all()
    
    return render_template('admin/reports.html', stats=stats, faculty_stats=faculty_stats, groups=groups)


# ==================== BAHOLASH TIZIMI ====================
@bp.route('/grade-scale')
@login_required
@admin_required
@permission_required('view_grade_scale')
def grade_scale():
    """Baholash tizimini ko'rish"""
    grades = GradeScale.query.order_by(GradeScale.order).all()
    return render_template('admin/grade_scale.html', grades=grades)


@bp.route('/grade-scale/create', methods=['GET', 'POST'])
@login_required
@admin_required
@permission_required('manage_grade_scale')
def create_grade():
    """Yangi baho qo'shish"""
    if request.method == 'POST':
        letter = request.form.get('letter').upper()
        
        # Tekshirish: bu harf mavjudmi
        if GradeScale.query.filter_by(letter=letter).first():
            flash(t('grade_letter_already_exists'), 'error')
            return render_template('admin/create_grade.html')
        
        # Ball oralig'ini tekshirish
        min_score = request.form.get('min_score', type=float)
        max_score = request.form.get('max_score', type=float)
        
        if min_score > max_score:
            flash(t('min_score_greater_than_max'), 'error')
            return render_template('admin/create_grade.html')
        
        grade = GradeScale(
            letter=letter,
            name=request.form.get('name'),
            min_score=min_score,
            max_score=max_score,
            description=request.form.get('description'),
            gpa_value=request.form.get('gpa_value', type=float) or 0,
            color=request.form.get('color', 'gray'),
            is_passing=request.form.get('is_passing') == 'on',
            order=request.form.get('order', type=int) or GradeScale.query.count() + 1
        )
        db.session.add(grade)
        db.session.commit()
        
        flash(t('grade_added'), 'success')
        return redirect(url_for('admin.grade_scale'))
    
    return render_template('admin/create_grade.html')


@bp.route('/grade-scale/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
@permission_required('manage_grade_scale')
def edit_grade(id):
    """Bahoni tahrirlash"""
    grade = GradeScale.query.get_or_404(id)
    
    if request.method == 'POST':
        grade.letter = request.form.get('letter').upper()
        grade.name = request.form.get('name')
        grade.min_score = request.form.get('min_score', type=float)
        grade.max_score = request.form.get('max_score', type=float)
        grade.description = request.form.get('description')
        grade.gpa_value = request.form.get('gpa_value', type=float) or 0
        grade.color = request.form.get('color', 'gray')
        grade.is_passing = request.form.get('is_passing') == 'on'
        grade.order = request.form.get('order', type=int)
        
        db.session.commit()
        flash(t('grade_updated'), 'success')
        return redirect(url_for('admin.grade_scale'))
    
    return render_template('admin/edit_grade.html', grade=grade)


@bp.route('/grade-scale/<int:id>/delete', methods=['POST'])
@login_required
@admin_required
@permission_required('manage_grade_scale')
def delete_grade(id):
    """Bahoni o'chirish"""
    grade = GradeScale.query.get_or_404(id)
    db.session.delete(grade)
    db.session.commit()
    flash(t('grade_deleted'), 'success')
    return redirect(url_for('admin.grade_scale'))


@bp.route('/grade-scale/reset', methods=['POST'])
@login_required
@admin_required
@permission_required('manage_grade_scale')
def reset_grade_scale():
    """Standart baholarni tiklash"""
    # Barcha baholarni o'chirish
    GradeScale.query.delete()
    db.session.commit()
    
    # Standart baholarni qayta yaratish
    GradeScale.init_default_grades()
    
    flash(t('grading_system_reset'), 'success')
    return redirect(url_for('admin.grade_scale'))


# ==================== EXCEL IMPORT ====================
@bp.route('/import/students', methods=['GET', 'POST'])
@login_required
@admin_required
@permission_required('import_students')
def import_students():
    """Excel fayldan talabalar import qilish"""
    if request.method == 'POST':
        if 'excel_file' not in request.files:
            flash(t('file_not_selected'), 'error')
            return redirect(url_for('admin.students'))
        
        file = request.files['excel_file']
        if file.filename == '':
            flash(t('file_not_selected'), 'error')
            return redirect(url_for('admin.students'))
        
        if not file.filename.endswith(('.xlsx', '.xls')):
            flash(t('only_excel_files_allowed'), 'error')
            return redirect(url_for('admin.students'))
        
        try:
            from app.utils.excel_import import import_students_from_excel
            
            result = import_students_from_excel(file, faculty_id=None)
            
            if result['success']:
                if result['imported'] > 0:
                    flash(t('students_imported', imported_count=result['imported']), 'success')
                else:
                    flash(t('no_students_imported'), 'warning')
                
                if result['errors']:
                    error_msg = f"Xatolar ({len(result['errors'])}): " + "; ".join(result['errors'][:5])
                    if len(result['errors']) > 5:
                        error_msg += f" va yana {len(result['errors']) - 5} ta xato"
                    flash(error_msg, 'warning')
            else:
                flash(t('import_error', error=result['errors'][0] if result['errors'] else 'Noma`lum xatolik'), 'error')
                
        except ImportError as e:
            flash(t('excel_import_not_working', error=str(e)), 'error')
        except Exception as e:
            flash(t('import_error', error=str(e)), 'error')
        
        return redirect(url_for('admin.students'))
    
    return render_template('admin/import_students.html')


# ==================== EXCEL EXPORT ====================
@bp.route('/export/students')
@login_required
@admin_required
def export_students():
    """Talabalar ro'yxatini Excel formatida yuklab olish"""
    try:
        from app.utils.excel_export import create_students_excel
    except ImportError:
        flash(t('openpyxl_not_installed'), 'error')
        return redirect(url_for('admin.students'))
    
    faculty_id = request.args.get('faculty_id', type=int)
    
    if faculty_id:
        faculty = Faculty.query.get_or_404(faculty_id)
        group_ids = [g.id for g in faculty.groups.all()]
        students = User.query.filter(
            User.role == 'student',
            User.group_id.in_(group_ids)
        ).order_by(User.full_name).all()
        faculty_name = faculty.name
    else:
        students = User.query.filter_by(role='student').order_by(User.full_name).all()
        faculty_name = None
    
    excel_file = create_students_excel(students, faculty_name)
    
    filename = f"talabalar_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    if faculty_name:
        filename = f"talabalar_{faculty_name.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    
    return Response(
        excel_file,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )


@bp.route('/export/all_users')
@login_required
@admin_required
def export_all_users():
    """Xodimlarni Excel formatida yuklab olish (admin, dekan, o'qituvchi, buxgalter)"""
    try:
        from app.utils.excel_export import create_staff_excel
    except ImportError:
        flash(t('openpyxl_not_installed'), 'error')
        return redirect(url_for('admin.staff'))
    
    # Faqat xodimlar (talabalar emas) - bir nechta rollarni ham qo'shish
    staff_roles = ['admin', 'dean', 'teacher', 'accounting']
    
    # UserRole orqali bir nechta rolli xodimlarni olish
    staff_user_ids = set()
    for role in staff_roles:
        # Asosiy rol bo'yicha
        users_with_role = User.query.filter_by(role=role).all()
        staff_user_ids.update([u.id for u in users_with_role])
        
        # UserRole orqali bir nechta rolli xodimlar
        from app.models import UserRole
        multi_role_users = User.query.join(UserRole).filter(UserRole.role == role).all()
        staff_user_ids.update([u.id for u in multi_role_users])
    
    # Talabalar emas, faqat xodimlar; superadmin eksportda bo'lmasin
    staff_users = User.query.filter(
        User.id.in_(list(staff_user_ids)),
        User.role != 'student'
    ).all()
    staff_users = [u for u in staff_users if not getattr(u, 'is_superadmin', False)]
    excel_file = create_staff_excel(staff_users)
    
    filename = f"xodimlar_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    
    return Response(
        excel_file,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )


@bp.route('/import/all_users', methods=['GET', 'POST'])
@login_required
@admin_required
@permission_required('import_staff')
def import_all_users():
    """Excel fayldan barcha foydalanuvchilarni import qilish (rol bo'yicha ajratish)"""
    if request.method == 'POST':
        if 'excel_file' not in request.files:
            flash(t('file_not_selected'), 'error')
            return redirect(url_for('admin.staff'))
        
        file = request.files['excel_file']
        if file.filename == '':
            flash(t('file_not_selected'), 'error')
            return redirect(url_for('admin.staff'))
        
        if not file.filename.endswith(('.xlsx', '.xls')):
            flash(t('only_excel_files_allowed'), 'error')
            return redirect(url_for('admin.staff'))
        
        try:
            from app.utils.excel_import import import_staff_from_excel
            
            result = import_staff_from_excel(file)
            
            if result['success']:
                if result['imported'] > 0:
                    flash(t('users_imported', imported_count=result['imported']), 'success')
                else:
                    flash(t('no_users_imported'), 'warning')
                
                if result['errors']:
                    error_msg = f"Xatolar ({len(result['errors'])}): " + "; ".join(result['errors'][:5])
                    if len(result['errors']) > 5:
                        error_msg += f" va yana {len(result['errors']) - 5} ta xato"
                    flash(error_msg, 'warning')
            else:
                flash(t('import_error', error=result['errors'][0] if result['errors'] else 'Noma`lum xatolik'), 'error')
                
        except ImportError as e:
            flash(t('excel_import_not_working', error=str(e)), 'error')
        except Exception as e:
            flash(t('import_error', error=str(e)), 'error')
        
        return redirect(url_for('admin.staff'))
    
    return render_template('admin/import_all_users.html')


@bp.route('/staff/import/sample')
@login_required
@admin_required
@permission_required('import_staff')
def download_staff_sample_import():
    """Xodimlar import uchun namuna Excel faylini yuklab olish (tanlangan til bo'yicha)"""
    try:
        from app.utils.excel_import import generate_staff_sample_file
        lang = session.get('language', 'uz')
        excel_file = generate_staff_sample_file(lang=lang)
        filename = t('sample_filename_staff') + f"_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        return Response(
            excel_file,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            headers={'Content-Disposition': f'attachment; filename={filename}'}
        )
    except Exception as e:
        flash(t('template_file_creation_error', error=str(e)), 'error')
        return redirect(url_for('admin.import_all_users'))


@bp.route('/export/schedule')
@login_required
@admin_required
def export_schedule():
    """Admin uchun dars jadvalini Excel formatida yuklab olish"""
    try:
        from app.utils.excel_export import create_schedule_excel
    except ImportError:
        flash(t('openpyxl_not_installed'), 'error')
        return redirect(url_for('admin.schedule'))
    
    import calendar
    from app.models import Direction
    
    # Get all filter parameters
    faculty_id = request.args.get('faculty_id', type=int)
    course_year = request.args.get('course_year', type=int)
    semester = request.args.get('semester', type=int)
    direction_id = request.args.get('direction_id', type=int)
    group_id = request.args.get('group_id', type=int)
    teacher_id = request.args.get('teacher_id', type=int)
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    
    # Determine date range
    start_code = None
    end_code = None
    
    if start_date or end_date:
        try:
            if start_date and end_date:
                # Both dates provided
                start_dt = datetime.strptime(start_date, "%Y-%m-%d")
                end_dt = datetime.strptime(end_date, "%Y-%m-%d")
                start_code = int(start_dt.strftime("%Y%m%d"))
                end_code = int(end_dt.strftime("%Y%m%d"))
            elif start_date:
                # Only start date: from start_date to far future
                start_dt = datetime.strptime(start_date, "%Y-%m-%d")
                start_code = int(start_dt.strftime("%Y%m%d"))
                end_code = 99991231  # Far future date
            elif end_date:
                # Only end date: from far past to end_date
                end_dt = datetime.strptime(end_date, "%Y-%m-%d")
                start_code = 19000101  # Far past date
                end_code = int(end_dt.strftime("%Y%m%d"))
        except ValueError:
            flash(t('date_invalid_format'), 'error')
            return redirect(url_for('admin.schedule'))
    else:
        # Default to all schedules if no date range specified
        start_code = 19000101  # Far past
        end_code = 99991231    # Far future
    
    # Build query with all filters (mirror schedule view logic)
    query = Schedule.query.join(Group).filter(Schedule.day_of_week.between(start_code, end_code))
    
    if faculty_id:
        query = query.filter(Group.faculty_id == faculty_id)
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
    elif faculty_id:
        faculty = Faculty.query.get(faculty_id)
        if faculty:
            filename_parts.append(faculty.name.replace(' ', '_'))
    elif teacher_id:
        teacher = User.query.get(teacher_id)
        if teacher:
            filename_parts.append(teacher.full_name.replace(' ', '_'))
    
    if start_date and end_date:
        filename_parts.append(f"{start_date}_{end_date}")
    
    filename = "_".join(filter(None, filename_parts)) + ".xlsx"
    
    # Create Excel file
    group_name = schedules[0].group.name if schedules and schedules[0].group else None
    faculty_name = None
    if faculty_id:
        faculty = Faculty.query.get(faculty_id)
        faculty_name = faculty.name if faculty else None
    
    excel_file = create_schedule_excel(schedules, group_name, faculty_name)
    
    return Response(
        excel_file,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )


# ==================== GURUHLAR BOSHQARUVI ====================
@bp.route('/groups')
@login_required
@admin_required
@permission_required('manage_groups')
def groups():
    faculty_id = request.args.get('faculty_id', type=int)
    course_year = request.args.get('course_year', type=int)
    semester = request.args.get('semester', type=int)
    direction_id = request.args.get('direction_id', type=int)
    search = request.args.get('search', '')
    
    query = Group.query
    if faculty_id:
        query = query.filter_by(faculty_id=faculty_id)
    if course_year:
        query = query.filter_by(course_year=course_year)
    if semester:
        query = query.filter_by(semester=semester)
    if direction_id:
        query = query.filter_by(direction_id=direction_id)
    if search:
        query = query.filter(Group.name.ilike(f'%{search}%'))

    # Faqat talabasi bor (faol) guruhlar
    has_student = exists().where(
        User.group_id == Group.id,
        User.role == 'student'
    )
    query = query.filter(has_student)
    groups_list = query.order_by(Group.course_year, Group.semester, Group.name).all()
    
    # Filtrlar uchun ma'lumotlar
    faculties = Faculty.query.order_by(Faculty.name).all()
    active_base = Group.query.filter(has_student)
    if faculty_id:
        active_base = active_base.filter_by(faculty_id=faculty_id)
    active_list = active_base.all()
    all_courses = sorted(set([g.course_year for g in active_list if g.course_year]))
    all_semesters = sorted(set([g.semester for g in active_list if g.semester]))
    direction_ids = [g.direction_id for g in active_list if g.direction_id]
    all_directions = []
    if direction_ids:
        all_directions = Direction.query.filter(Direction.id.in_(set(direction_ids))).all()
        all_directions = sorted(all_directions, key=lambda d: ((d.code or '').lower(), (d.name or '').lower()))
    
    return render_template('admin/groups.html', 
                         groups=groups_list, 
                         faculties=faculties, 
                         all_courses=all_courses,
                         all_semesters=all_semesters,
                         all_directions=all_directions,
                         current_faculty=faculty_id, 
                         current_course_year=course_year,
                         current_semester=semester,
                         current_direction_id=direction_id,
                         search=search)


@bp.route('/groups/create', methods=['GET', 'POST'])
@login_required
@admin_required
@permission_required('create_group')
def create_group():
    faculty_id = request.args.get('faculty_id', type=int)
    direction_id = request.args.get('direction_id', type=int)
    
    if request.method == 'POST':
        name = request.form.get('name')
        faculty_id = request.form.get('faculty_id', type=int) or request.args.get('faculty_id', type=int)
        direction_id = request.form.get('direction_id', type=int)
        course_year = request.form.get('course_year', type=int)
        semester = request.form.get('semester', type=int)
        education_type = request.form.get('education_type')
        enrollment_year = request.form.get('enrollment_year', type=int)
        
        # Validatsiya
        if not name:
            flash(t('group_name_required'), 'error')
            return redirect(url_for('admin.create_group', faculty_id=faculty_id))
        
        if not faculty_id:
            flash(t('faculty_required'), 'error')
            return redirect(url_for('admin.create_group'))
        
        if not direction_id:
            flash(t('direction_required'), 'error')
            return redirect(url_for('admin.create_group', faculty_id=faculty_id))
            
        if not course_year or not semester:
            flash(t('group_course_and_semester_required'), 'error')
            return redirect(url_for('admin.create_group', faculty_id=faculty_id))
        
        # Bir yo'nalishda, kursda va semestrda bir xil guruh nomi bo'lishi mumkin emas
        if Group.query.filter_by(name=name.upper(), direction_id=direction_id, course_year=course_year, semester=semester).first():
            flash(t('group_already_exists'), 'error')
            return render_template('admin/create_group.html', 
                                 faculties=Faculty.query.all(), 
                                 directions=Direction.query.filter_by(faculty_id=faculty_id).all() if faculty_id else Direction.query.all(),
                                 faculty_id=faculty_id,
                                 direction_id=direction_id)
        
        # Yo'nalishdan mustaqil ravishda guruh yaratish
        group = Group(
            name=name.upper(),
            faculty_id=faculty_id,
            course_year=course_year,
            semester=semester,
            education_type=education_type,
            enrollment_year=enrollment_year,
            direction_id=direction_id
        )
        db.session.add(group)
        db.session.commit()
        
        flash(t('group_created'), 'success')
        # Fakultet detail sahifasiga qaytish
        if faculty_id:
            return redirect(url_for('admin.faculty_detail', id=faculty_id))
        return redirect(url_for('admin.groups'))
    
    # GET request - ma'lumotlarni tayyorlash
    faculties = Faculty.query.all()
    
    # Agar faculty_id berilgan bo'lsa, faqat shu fakultet uchun
    if faculty_id:
        faculty = Faculty.query.get(faculty_id)
        if not faculty:
            flash(t('faculty_not_found'), 'error')
            return redirect(url_for('admin.faculties'))
        
        # Yo'nalishlarni olish
        all_directions = Direction.query.filter_by(faculty_id=faculty_id).order_by(Direction.name).all()
        
        return render_template('admin/create_group.html', 
                             faculties=faculties,
                             faculty=faculty,
                             faculty_id=faculty_id,
                             all_directions=all_directions,
                             direction_id=direction_id)
    else:
        # Agar faculty_id berilmagan bo'lsa, barcha fakultetlar
        return render_template('admin/create_group.html', 
                             faculties=faculties,
                             faculty=None,
                             faculty_id=None,
                             all_directions=Direction.query.all(),
                             direction_id=direction_id)


@bp.route('/groups/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
@permission_required('edit_group')
def edit_group(id):
    group = Group.query.get_or_404(id)
    
    if request.method == 'POST':
        # Guruh nomi, kurs, semestr, ta'lim shakli, yo'nalishni o'zgartirish mumkin
        new_name = request.form.get('name').upper()
        course_year = request.form.get('course_year', type=int)
        semester = request.form.get('semester', type=int)
        education_type = request.form.get('education_type')
        enrollment_year = request.form.get('enrollment_year', type=int)
        direction_id = request.form.get('direction_id', type=int)
        
        # Validatsiya
        if not course_year or not semester or not education_type or not direction_id:
            flash(t('all_required_fields'), 'error')
            return redirect(url_for('admin.edit_group', id=group.id))
        
        # Yo'nalish tekshiruvi
        direction = Direction.query.get(direction_id)
        if not direction or direction.faculty_id != group.faculty_id:
            flash(t('direction_incorrect_selection'), 'error')
            return redirect(url_for('admin.edit_group', id=group.id))
        
        # Bir yo'nalishda, kursda va semestrda bir xil guruh nomi bo'lishi mumkin emas
        # Agar nom, yo'nalish, kurs yoki semestr o'zgarganda tekshirish kerak
        if (new_name != group.name or direction_id != group.direction_id or course_year != group.course_year or semester != group.semester):
            existing_group = Group.query.filter_by(name=new_name, direction_id=direction_id, course_year=course_year, semester=semester).first()
            if existing_group and existing_group.id != group.id:
                flash(t('group_already_exists'), 'error')
                return redirect(url_for('admin.edit_group', id=group.id))
        
        group.name = new_name
        group.direction_id = direction_id
        group.course_year = course_year
        group.semester = semester
        group.education_type = education_type
        group.enrollment_year = enrollment_year
        
        db.session.commit()
        flash(t('group_updated'), 'success')
        
        # Redireksiya
        if request.args.get('from_faculty'):
            return redirect(url_for('admin.faculty_detail', id=group.faculty_id))
        
        # Yo'nalishga qaytish (default)
        return redirect(url_for('admin.direction_detail', id=direction_id))
    
    # GET request - ma'lumotlarni tayyorlash
    faculty = group.faculty
    
    # Yo'nalishlarni olish
    all_directions = Direction.query.filter_by(faculty_id=faculty.id).order_by(Direction.name).all()
    
    return render_template('admin/edit_group.html', 
                         group=group,
                         faculty=faculty,
                         all_directions=all_directions)


@bp.route('/groups/<int:id>/students')
@login_required
@admin_required
@permission_required('view_students')
def group_students(id):
    """Guruh talabalari ro'yxati (admin uchun)"""
    group = Group.query.get_or_404(id)
    students = group.students.order_by(User.full_name).all()
    # Guruhga qo'shish uchun bo'sh talabalar
    available_students = User.query.filter(
        User.role == 'student',
        User.group_id == None
    ).order_by(User.full_name).all()
    
    return render_template('admin/group_students.html', group=group, students=students, available_students=available_students)

@bp.route('/groups/<int:id>/add-students', methods=['POST'])
@login_required
@admin_required
@permission_required('manage_groups')
def add_student_to_group(id):
    """Guruhga talaba qo'shish (admin uchun)"""
    group = Group.query.get_or_404(id)
    
    # Bir nechta talabani qo'shish
    student_ids = request.form.getlist('student_ids')
    student_ids = [int(sid) for sid in student_ids if sid]
    
    if not student_ids:
        flash(t('no_students_selected'), 'error')
        return redirect(url_for('admin.group_students', id=id))
    
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
    
    return redirect(url_for('admin.group_students', id=id))

@bp.route('/groups/<int:id>/remove-students', methods=['POST'])
@login_required
@admin_required
@permission_required('manage_groups')
def remove_students_from_group(id):
    """Bir nechta talabani bir vaqtning o'zida guruhdan chiqarish (admin uchun)"""
    group = Group.query.get_or_404(id)
    
    ids = request.form.getlist('remove_student_ids')
    student_ids = [int(sid) for sid in ids if sid]
    
    if not student_ids:
        flash(t('no_students_selected'), 'error')
        return redirect(url_for('admin.group_students', id=id))
    
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
    
    return redirect(url_for('admin.group_students', id=id))

@bp.route('/groups/<int:id>/delete', methods=['POST'])
@login_required
@admin_required
@permission_required('delete_group')
def delete_group(id):
    group = Group.query.get_or_404(id)
    faculty_id = group.faculty_id
    
    # Guruhda talabalar borligini tekshirish
    if group.students.count() > 0:
        flash(t('group_has_students'), 'error')
    else:
        # Guruhga bog'liq Schedule yozuvlarini o'chirish
        schedules = Schedule.query.filter_by(group_id=group.id).all()
        for schedule in schedules:
            db.session.delete(schedule)
        
        # Guruhga bog'liq TeacherSubject yozuvlarini o'chirish
        teacher_subjects = TeacherSubject.query.filter_by(group_id=group.id).all()
        for teacher_subject in teacher_subjects:
            db.session.delete(teacher_subject)
        
        # Guruhni o'chirish
        db.session.delete(group)
        db.session.commit()
        flash(t('group_deleted'), 'success')
    
    # Fakultet detail sahifasiga qaytish
    if request.args.get('from_faculty'):
        return redirect(url_for('admin.faculty_detail', id=faculty_id))
    return redirect(url_for('admin.groups'))


# ==================== YO'NALISHLAR ====================
@bp.route('/directions/create', methods=['GET', 'POST'])
@login_required
@admin_required
@permission_required('create_direction')
def create_direction():
    """Yangi yo'nalish yaratish (admin uchun)"""
    faculty_id = request.args.get('faculty_id', type=int)
    
    if request.method == 'POST':
        name_uz = (request.form.get('name_uz') or '').strip()
        name_ru = (request.form.get('name_ru') or '').strip()
        name_en = (request.form.get('name_en') or '').strip()
        description_uz = (request.form.get('description_uz') or '').strip()
        description_ru = (request.form.get('description_ru') or '').strip()
        description_en = (request.form.get('description_en') or '').strip()
        code = request.form.get('code', '').strip()
        faculty_id = request.form.get('faculty_id', type=int)
        name = name_uz or name_ru or name_en
        description = description_uz or description_ru or description_en
        # Validatsiya: barcha tillarda nom majburiy
        if not name_uz or not name_ru or not name_en:
            flash(t('direction_name_all_languages_required'), 'error')
            return render_template('admin/create_direction.html',
                                 faculties=Faculty.query.all(),
                                 faculty_id=faculty_id,
                                 name_uz=name_uz, name_ru=name_ru, name_en=name_en,
                                 description_uz=description_uz, description_ru=description_ru, description_en=description_en,
                                 code=code)
        if not code:
            flash(t('direction_name_and_code_required'), 'error')
            return render_template('admin/create_direction.html',
                                 faculties=Faculty.query.all(),
                                 faculty_id=faculty_id,
                                 name_uz=name_uz, name_ru=name_ru, name_en=name_en,
                                 description_uz=description_uz, description_ru=description_ru, description_en=description_en,
                                 code=code)
        if not code.isdigit():
            flash(t('direction_code_digits_only'), 'error')
            return render_template('admin/create_direction.html',
                                 faculties=Faculty.query.all(),
                                 faculty_id=faculty_id,
                                 name_uz=name_uz, name_ru=name_ru, name_en=name_en,
                                 description_uz=description_uz, description_ru=description_ru, description_en=description_en,
                                 code=code)
        if not faculty_id:
            flash(t('faculty_required'), 'error')
            return render_template('admin/create_direction.html',
                                 faculties=Faculty.query.all(),
                                 faculty_id=faculty_id,
                                 name_uz=name_uz, name_ru=name_ru, name_en=name_en,
                                 description_uz=description_uz, description_ru=description_ru, description_en=description_en,
                                 code=code)
        # Kod takrorlanmasligini tekshirish (fakultet bo'yicha)
        existing = Direction.query.filter_by(code=code, faculty_id=faculty_id).first()
        if existing:
            flash(t('direction_already_exists'), 'error')
            return render_template('admin/create_direction.html',
                                 faculties=Faculty.query.all(),
                                 faculty_id=faculty_id,
                                 name_uz=name_uz, name_ru=name_ru, name_en=name_en,
                                 description_uz=description_uz, description_ru=description_ru, description_en=description_en,
                                 code=code)
        direction = Direction(
            name=name,
            name_uz=name_uz, name_ru=name_ru, name_en=name_en,
            description=description,
            description_uz=description_uz, description_ru=description_ru, description_en=description_en,
            code=code,
            faculty_id=faculty_id
        )
        db.session.add(direction)
        db.session.commit()
        flash(t('direction_created'), 'success')
        if faculty_id:
            return redirect(url_for('admin.faculty_detail', id=faculty_id))
        return redirect(url_for('admin.directions'))
    
    return render_template('admin/create_direction.html',
                         faculties=Faculty.query.all(),
                         faculty_id=faculty_id)


@bp.route('/directions/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
@permission_required('edit_direction')
def edit_direction(id):
    """Yo'nalishni tahrirlash (admin uchun)"""
    direction = Direction.query.get_or_404(id)
    
    if request.method == 'POST':
        name_uz = (request.form.get('name_uz') or '').strip()
        name_ru = (request.form.get('name_ru') or '').strip()
        name_en = (request.form.get('name_en') or '').strip()
        description_uz = (request.form.get('description_uz') or '').strip()
        description_ru = (request.form.get('description_ru') or '').strip()
        description_en = (request.form.get('description_en') or '').strip()
        code = (request.form.get('code') or '').strip()
        faculty_id = request.form.get('faculty_id', type=int)
        if not name_uz or not name_ru or not name_en:
            flash(t('direction_name_all_languages_required'), 'error')
            return render_template('admin/edit_direction.html',
                                 direction=direction,
                                 faculties=Faculty.query.all(),
                                 name_uz=name_uz, name_ru=name_ru, name_en=name_en,
                                 description_uz=description_uz, description_ru=description_ru, description_en=description_en,
                                 code=code, faculty_id=faculty_id)
        name = name_uz or name_ru or name_en
        description = description_uz or description_ru or description_en
        direction.name = name
        direction.name_uz = name_uz
        direction.name_ru = name_ru
        direction.name_en = name_en
        direction.description = description
        direction.description_uz = description_uz
        direction.description_ru = description_ru
        direction.description_en = description_en
        direction.code = code
        direction.faculty_id = faculty_id
        existing = Direction.query.filter(
            Direction.code == direction.code,
            Direction.faculty_id == direction.faculty_id,
            Direction.id != id
        ).first()
        if existing:
            flash(t('direction_code_already_exists'), 'error')
            return render_template('admin/edit_direction.html',
                                 direction=direction,
                                 faculties=Faculty.query.all(),
                                 name_uz=name_uz, name_ru=name_ru, name_en=name_en,
                                 description_uz=description_uz, description_ru=description_ru, description_en=description_en,
                                 code=code, faculty_id=faculty_id)
        db.session.commit()
        flash(t('direction_updated'), 'success')
        if request.args.get('faculty_id'):
            return redirect(url_for('admin.faculty_detail', id=direction.faculty_id))
        return redirect(url_for('admin.directions'))
    
    return render_template('admin/edit_direction.html',
                         direction=direction,
                         faculties=Faculty.query.all())


@bp.route('/directions/<int:id>/delete', methods=['POST'])
@login_required
@admin_required
@permission_required('delete_direction')
def delete_direction(id):
    """Yo'nalishni o'chirish (admin uchun)"""
    direction = Direction.query.get_or_404(id)
    faculty_id = direction.faculty_id
    
    # Guruhlar borligini tekshirish
    groups = direction.groups.all()
    if groups:
        # Har bir guruhda talabalar borligini tekshirish
        total_students = 0
        for group in groups:
            total_students += group.students.count()
        
        if total_students > 0:
            flash(t('direction_has_groups_and_students', groups_count=len(groups), students_count=total_students), 'error')
        else:
            flash(t('direction_has_groups', groups_count=len(groups)), 'error')
    else:
        db.session.delete(direction)
        db.session.commit()
        flash(t('direction_deleted'), 'success')
    
    # Fakultet detail sahifasiga qaytish
    if request.args.get('from_faculty'):
        return redirect(url_for('admin.faculty_detail', id=faculty_id))
    return redirect(url_for('admin.directions'))


# ==================== O'QITUVCHI BIRIKTIRISH ====================
# Assignments sahifasi o'chirildi - o'qituvchi biriktirish endi yo'nalish-semestr fanlaridan amalga oshiriladi
# @bp.route('/assignments')
# @login_required
# @admin_required
# def assignments():
#     ...

# @bp.route('/assignments/create', methods=['POST'])
# @login_required
# @admin_required
# def create_assignment():
#     ...

# @bp.route('/assignments/<int:id>/delete', methods=['POST'])
# @login_required
# @admin_required
# def delete_assignment(id):
#     ...


# ==================== ADMIN UCHUN DEKAN FUNKSIYALARI ====================
# Admin uchun barcha fakultetlar bo'yicha ishlaydi

@bp.route('/directions')
@login_required
@admin_required
@permission_required('view_directions')
def directions():
    """Admin yo'nalishlar – dekandagi kabi (Yil+Ta'lim → Yo'nalish → Kurs → Semestr → Guruhlar), barcha fakultetlar."""
    course_filter = request.args.get('course', type=int)
    direction_filter = request.args.get('direction', type=int)
    faculty_filter = request.args.get('faculty_id', type=int)
    search = request.args.get('search', '')
    sort_by = request.args.get('sort', 'faculty')  # faculty, year, direction, education_type
    sort_order = request.args.get('order', 'asc')  # asc, desc

    # Faqat talabasi bor guruhlar, barcha fakultetlar
    has_student = exists().where(User.group_id == Group.id, User.role == 'student')
    all_groups = Group.query.filter(has_student).order_by(Group.course_year, Group.name).all()
    if faculty_filter:
        all_groups = [g for g in all_groups if g.faculty_id == faculty_filter]
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

    _lang = session.get('language', 'uz')
    courses_dict = {}
    for group in all_groups:
        if not group.semester:
            continue
        semester = group.semester
        course_year = group.course_year or ((group.semester + 1) // 2)
        enrollment_year = group.enrollment_year if group.enrollment_year else "Noma'lum"
        edu_type = group.education_type if group.education_type else "Noma'lum"

        students_count = group.get_students_count()
        if students_count == 0:
            continue

        main_key = (enrollment_year, edu_type)
        if main_key not in courses_dict:
            courses_dict[main_key] = {'directions': {}, 'total_groups': 0, 'total_students': 0}

        direction_key = (group.direction_id, group.education_type, group.faculty_id)
        if direction_key not in courses_dict[main_key]['directions']:
            if group.direction:
                code = group.direction.code
                name = (group.direction.get_display_name(_lang) or group.direction.name) or ''
                et = (group.education_type or '').strip().lower()
                edu_type_str = t('education_type_' + et) if et in ('kunduzgi', 'sirtqi', 'kechki', 'masofaviy') else (t('education_type_not_set') if et else '')
                if not edu_type_str:
                    edu_type_str = (group.education_type or '').capitalize()
                enrollment_year_str = str(group.enrollment_year) if group.enrollment_year else "____"
                heading = f"{enrollment_year_str} - {code} - {name} ({edu_type_str})"
            else:
                heading = "____ - Biriktirilmagan"
            courses_dict[main_key]['directions'][direction_key] = {
                'heading': heading,
                'subtitle_parts': set(),
                'subtitle': '',
                'direction': group.direction,
                'faculty': group.faculty,
                'enrollment_year': enrollment_year,
                'education_type': edu_type,
                'courses': {},
                'total_students': 0,
                'total_groups': 0,
            }

        d = courses_dict[main_key]['directions'][direction_key]
        if course_year not in d['courses']:
            d['courses'][course_year] = {'semesters': {}, 'total_students': 0, 'total_groups': 0}
        c = d['courses'][course_year]
        if semester not in c['semesters']:
            c['semesters'][semester] = {'groups': [], 'students_count': 0}
        sem = c['semesters'][semester]
        sem['groups'].append({'group': group, 'students_count': students_count})
        sem['students_count'] += students_count
        c['total_students'] += students_count
        c['total_groups'] += 1
        d['total_students'] += students_count
        d['total_groups'] += 1
        d['subtitle_parts'].add(f"{course_year}-kurs, {semester}-semestr")
        courses_dict[main_key]['total_students'] += students_count
        courses_dict[main_key]['total_groups'] += 1

    sorted_keys = sorted(courses_dict.keys(), key=lambda k: ((k[0] if k[0] != "Noma'lum" else 9999), str(k[1])))
    courses_list = []
    for key in sorted_keys:
        year, edu_type = key
        year_data = courses_dict[key]
        formatted_directions = []
        sorted_dir_keys = sorted(year_data['directions'].keys(), key=lambda k: (year_data['directions'][k]['heading'], (year_data['directions'][k].get('faculty') and year_data['directions'][k]['faculty'].name or '')))
        for d_key in sorted_dir_keys:
            d_data = year_data['directions'][d_key]
            d_data['subtitle'] = ', '.join(sorted(d_data['subtitle_parts']))
            formatted_courses = {}
            for c_year in sorted(d_data['courses'].keys()):
                c_data = d_data['courses'][c_year]
                formatted_courses[c_year] = {
                    'semesters': dict(sorted(c_data['semesters'].items())),
                    'total_students': c_data['total_students'],
                    'total_groups': c_data['total_groups'],
                }
                for sem_list in c_data['semesters'].values():
                    sem_list['groups'].sort(key=lambda x: x['group'].name)
            d_data['courses'] = formatted_courses
            formatted_directions.append(d_data)
        safe_key = f"{year}-{edu_type}".replace(' ', '_').lower()
        courses_list.append({
            'year': year,
            'edu_type': edu_type,
            'key': safe_key,
            'directions': formatted_directions,
            'total_directions': len(formatted_directions),
            'total_students': year_data['total_students'],
            'total_groups': year_data['total_groups'],
        })

    # Yo'nalishlar ro'yxati (modal va filtrlar uchun)
    groups_with_dirs = db.session.query(Group.direction_id, Group.enrollment_year, Group.education_type, Group.faculty_id).filter(
        Group.direction_id.isnot(None), has_student
    ).distinct().all()
    used = set()
    directions_list_data = []
    for d_id, yr, e_type, f_id in groups_with_dirs:
        direction = Direction.query.get(d_id)
        faculty = Faculty.query.get(f_id)
        if not direction or not faculty:
            continue
        key = (d_id, yr, e_type, f_id)
        if key in used:
            continue
        used.add(key)
        _lang = session.get('language', 'uz')
        d_name = direction.get_display_name(_lang) or direction.name
        year_str = str(yr) if yr else '____'
        edu_str = (e_type or '').capitalize()
        formatted = f"{year_str} - {direction.code} - {d_name}"
        if edu_str:
            formatted += f" ({edu_str})"
        directions_list_data.append({
            'id': direction.id,
            'name': d_name,
            'code': direction.code,
            'enrollment_year': yr,
            'education_type': e_type,
            'faculty': faculty,
            'formatted_direction': formatted,
        })
    _lang = session.get('language', 'uz')
    for direction in Direction.query.order_by(Direction.name).all():
        has_any = db.session.query(Group).filter(Group.direction_id == direction.id).first() is not None
        if has_any:
            continue
        d_name = direction.get_display_name(_lang) or direction.name
        directions_list_data.append({
            'id': direction.id,
            'name': d_name,
            'code': direction.code,
            'enrollment_year': None,
            'education_type': None,
            'faculty': direction.faculty,
            'formatted_direction': f"____ - {direction.code} - {d_name}",
        })
    directions_list_data.sort(key=lambda x: ((x['enrollment_year'] or 9999), ((x['faculty'].name if x.get('faculty') else None) or ''), (x['code'] or ''), (x['name'] or '')))

    # Faol guruhlar (modal uchun) va filtrlash uchun
    groups_list = Group.query.filter(has_student).order_by(Group.course_year, Group.name).all()
    if faculty_filter:
        groups_list = [g for g in groups_list if g.faculty_id == faculty_filter]
    faculties = Faculty.query.order_by(Faculty.name).all()
    all_courses = sorted(set(g.course_year for g in groups_list if g.course_year))

    # O'quv bo'limi uchun jadval ro'yxati (ustunlar: fakultet, qabul yili, yo'nalish kodi nomi, ta'lim shakli, amallar) – tanlangan til
    edu_directions_table = []
    for item in courses_list:
        for d in item['directions']:
            fac = d.get('faculty')
            faculty_name = (fac.get_display_name(_lang) or fac.name if fac else '') or ''
            year_val = d.get('enrollment_year') or "Noma'lum"
            edu_type = d.get('education_type') or "Noma'lum"
            direction = d.get('direction')
            code = direction.code if direction else ''
            name = (direction.get_display_name(_lang) or direction.name if direction else '') or ''
            direction_code_name = f"{code} - {name}".strip(' -') if (code or name) else '—'
            edu_directions_table.append({
                'faculty_name': faculty_name,
                'enrollment_year': year_val,
                'direction_code_name': direction_code_name,
                'education_type': edu_type,
                'direction_data': d,
            })
    # Ustun bo'yicha tartiblash
    _reverse = (sort_order == 'desc')
    _key_map = {
        'faculty': lambda x: (x['faculty_name'].lower(), str(x['enrollment_year']), x['direction_code_name'].lower(), x['education_type'].lower()),
        'year': lambda x: ((x['enrollment_year'] if x['enrollment_year'] != "Noma'lum" else 9999), x['faculty_name'].lower(), x['direction_code_name'].lower(), x['education_type'].lower()),
        'direction': lambda x: (x['direction_code_name'].lower(), x['faculty_name'].lower(), str(x['enrollment_year']), x['education_type'].lower()),
        'education_type': lambda x: (x['education_type'].lower(), x['faculty_name'].lower(), str(x['enrollment_year']), x['direction_code_name'].lower()),
    }
    edu_directions_table.sort(key=_key_map.get(sort_by, _key_map['faculty']), reverse=_reverse)

    return render_template(
        'admin/directions.html',
        courses_list=courses_list,
        all_directions=Direction.query.order_by(Direction.name).all(),
        directions_list=directions_list_data,
        groups_list=groups_list,
        faculties=faculties,
        all_courses=all_courses,
        course_filter=course_filter,
        direction_filter=direction_filter,
        faculty_filter=faculty_filter,
        search=search,
        edu_directions_table=edu_directions_table,
        sort_by=sort_by,
        sort_order=sort_order,
    )


# ==================== FANLAR BAZASI ====================
@bp.route('/curriculum-subjects')
@login_required
@admin_required
@permission_required('view_curriculum')
def curriculum_subjects():
    """Legacy route: Fanlar bazasini yagona /subjects/ sahifasiga yo'naltirish."""
    params = request.args.to_dict(flat=True)
    if 'direction_id' in params and 'direction' not in params:
        params['direction'] = params.pop('direction_id')
    return redirect(url_for('courses.index', **params))


@bp.route('/students/create', methods=['GET', 'POST'])
@login_required
@admin_required
@permission_required('create_student')
def create_student():
    """Admin uchun yangi talaba yaratish"""
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        full_name = (request.form.get('full_name') or '').strip().upper()
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
            return render_template('admin/create_student.html')
        
        if User.query.filter_by(student_id=student_id).first():
            flash(t('student_id_already_exists'), 'error')
            return render_template('admin/create_student.html')
        
        # Pasport seriyasi va raqami majburiy
        if not passport_number:
            flash(t('passport_required'), 'error')
            return render_template('admin/create_student.html')
        
        # Email ixtiyoriy, lekin agar kiritilgan bo'lsa, unikallikni tekshirish
        if email:
            if User.query.filter_by(email=email).first():
                flash(t('email_already_exists'), 'error')
                return render_template('admin/create_student.html')
        
        # Pasport raqamini katta harfga o'zgartirish
        passport_number = passport_number.upper()
        
        # Tug'ilgan sanani parse qilish (yyyy-mm-dd)
        parsed_birth_date = None
        if birth_date:
            try:
                parsed_birth_date = datetime.strptime(birth_date, '%Y-%m-%d').date()
            except ValueError:
                flash(t('birthdate_invalid_format'), 'error')
                return render_template('admin/create_student.html')
        
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
        if passport_number:
            student.set_password(passport_number)
        else:
            student.set_password('student123')
        
        # Guruh biriktirish
        group_id = request.form.get('group_id')
        manual_group_name = request.form.get('manual_group_name', '').strip()
        
        if manual_group_name:
            # Yangi guruh yaratish uchun kerakli ma'lumotlar
            faculty_id = request.form.get('faculty_id')
            direction_id = request.form.get('direction_id')
            course_year = request.form.get('course_year')
            semester = request.form.get('semester')
            education_type = request.form.get('education_type')
            # Use same enrollment year for group if provided, or student's enrollment year
            group_enrollment_year = enrollment_year
            
            if faculty_id and direction_id and course_year and semester and education_type:
                # Guruh mavjudligini tekshirish
                existing_group = Group.query.filter_by(
                    name=manual_group_name,
                    faculty_id=int(faculty_id),
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
                        faculty_id=int(faculty_id),
                        direction_id=int(direction_id),
                        course_year=int(course_year),
                        semester=int(semester),
                        education_type=education_type,
                        enrollment_year=group_enrollment_year
                    )
                    db.session.add(new_group)
                    db.session.flush() # ID olish uchun
                    student.group_id = new_group.id
                    student.semester = new_group.semester  # Sync student semester with group
        elif group_id:
            student.group_id = int(group_id)
            # Sync student semester with selected group
            selected_group = Group.query.get(int(group_id))
            if selected_group:
                student.semester = selected_group.semester
            
        db.session.add(student)
        
        # ... (db.session.commit logic as before)
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
        return redirect(url_for('admin.students'))
    
    faculties = Faculty.query.all()
    # Edit/Create sahifalarida dinamik tanlovlar uchun barcha yo'nalishlar (ixtiyoriy, keyinroq filter qilinadi)
    return render_template('admin/create_student.html', faculties=faculties)


@bp.route('/students/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
@permission_required('edit_student')
def edit_student(id):
    """Admin uchun talabani tahrirlash"""
    student = User.query.get_or_404(id)
    if student.role != 'student':
        flash(t('user_not_staff'), 'error')
        return redirect(url_for('admin.students'))
    
    if request.method == 'POST':
        student_id = request.form.get('student_id', '').strip()
        full_name = (request.form.get('full_name') or '').strip().upper()
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
            return render_template('admin/edit_student.html', student=student)
        
        # Talaba ID unikalligi (boshqa talabada bo'lmasligi kerak)
        existing_student = User.query.filter_by(student_id=student_id).first()
        if existing_student and existing_student.id != student.id:
            flash(t('student_id_already_exists'), 'error')
            return render_template('admin/edit_student.html', student=student)
        
        # Pasport seriyasi va raqami majburiy
        if not passport_number:
            flash(t('passport_required'), 'error')
            return render_template('admin/edit_student.html', student=student)
        
        # Email ixtiyoriy, lekin agar kiritilgan bo'lsa, unikallikni tekshirish
        if email:
            existing_student_with_email = User.query.filter_by(email=email).first()
            if existing_student_with_email and existing_student_with_email.id != student.id:
                flash(t('email_already_exists'), 'error')
                return render_template('admin/edit_student.html', student=student)
        
        # Pasport raqamini katta harfga o'zgartirish
        passport_number = passport_number.upper()
        
        # Tug'ilgan sanani parse qilish (yyyy-mm-dd)
        if birth_date_str:
            try:
                student.birth_date = datetime.strptime(birth_date_str, '%Y-%m-%d').date()
            except ValueError:
                flash(t('birthdate_invalid_format'), 'error')
                return render_template('admin/edit_student.html', student=student)
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
            selected_group = Group.query.get(int(group_id))
            if selected_group:
                student.semester = selected_group.semester
        elif manual_group_name:
            # Yangi guruh yaratish uchun kerakli ma'lumotlar
            faculty_id = request.form.get('faculty_id')
            direction_id = request.form.get('direction_id')
            course_year = request.form.get('course_year')
            semester = request.form.get('semester')
            education_type = request.form.get('education_type')
            group_enrollment_year = enrollment_year
            
            if faculty_id and direction_id and course_year and semester and education_type:
                # Guruh mavjudligini tekshirish
                existing_group = Group.query.filter_by(
                    name=manual_group_name,
                    faculty_id=int(faculty_id),
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
                        faculty_id=int(faculty_id),
                        direction_id=int(direction_id),
                        course_year=int(course_year),
                        semester=int(semester),
                        education_type=education_type,
                        enrollment_year=group_enrollment_year
                    )
                    db.session.add(new_group)
                    db.session.flush() # ID olish uchun
                    student.group_id = new_group.id
                    student.semester = new_group.semester  # Sync student semester with group
        else:
            student.group_id = None
            
        db.session.commit()
        flash(t('student_updated', full_name=student.full_name), 'success')
        return redirect(url_for('admin.students'))
    
    faculties = Faculty.query.all()
    all_directions = []
    if student.group:
        all_directions = Direction.query.filter_by(faculty_id=student.group.faculty_id).all()
    
    return render_template('admin/edit_student.html', student=student, faculties=faculties, all_directions=all_directions)


@bp.route('/students')
@login_required
@admin_required
@permission_required('view_students')
def students():
    """Admin uchun barcha talabalar"""
    from app.models import Direction
    
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '')
    faculty_id = request.args.get('faculty', type=int)
    course_year = request.args.get('course', type=int)
    semester = request.args.get('semester', type=int)
    education_type = request.args.get('education_type', '') or None
    direction_id = request.args.get('direction', type=int)
    group_id = request.args.get('group', type=int)
    
    query = User.query.filter(User.role == 'student')
    
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
    
    # Filtrlash - barcha tanlangan filtrlar birga qo'llaniladi (AND)
    if group_id:
        query = query.filter(User.group_id == group_id)
    else:
        # Guruh bo'yicha filtrlash (direction, faculty, course, education_type)
        group_filters = {}
        if faculty_id:
            group_filters['faculty_id'] = faculty_id
        if direction_id:
            group_filters['direction_id'] = direction_id
        if course_year:
            group_filters['course_year'] = course_year
        if education_type:
            group_filters['education_type'] = education_type

        if group_filters:
            groups_list = Group.query.filter_by(**group_filters).all()
            group_ids = [g.id for g in groups_list]
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
    
    # Filtrlar uchun ma'lumotlar (A–Z)
    faculties = Faculty.query.all()
    faculties = sorted(faculties, key=lambda f: (f.name or '').lower())
    
    has_student = exists().where(User.group_id == Group.id, User.role == 'student')
    
    # Faqat ichida talaba bor bo'lgan yo'nalishlar (filtrda ko'rsatish uchun, A–Z)
    direction_ids_with_students = set(g.direction_id for g in Group.query.filter(has_student).all() if g.direction_id)
    directions = Direction.query.filter(Direction.id.in_(direction_ids_with_students)).all() if direction_ids_with_students else []
    directions = sorted(directions, key=lambda d: ((d.code or '').lower(), (d.name or '').lower()))
    
    # Faqat ichida talaba bor bo'lgan guruhlar
    all_groups = Group.query.order_by(Group.name).all()
    groups_with_students = Group.query.filter(has_student).order_by(Group.name).all()
    
    # Bir xil nomli guruhlarni umumlashtirish (faqat filtr uchun), A–Z tartibida
    unique_group_names = {}
    for g in groups_with_students:
        if g.name not in unique_group_names:
            unique_group_names[g.name] = g
    groups = sorted(unique_group_names.values(), key=lambda g: (g.name or '').lower())
    
    # JavaScript uchun guruhlar ma'lumotlari (JSON formatida)
    groups_json = [{
        'id': g.id,
        'name': g.name,
        'faculty_id': g.faculty_id,
        'course_year': g.course_year,
        'direction_id': g.direction_id,
        'education_type': g.education_type
    } for g in groups]
    
    # JavaScript uchun ma'lumotlar (JSON formatida)
    # Fakultet -> Kurslar
    faculty_courses = {}
    for faculty in faculties:
        courses_set = set()
        for group in Group.query.filter_by(faculty_id=faculty.id).all():
            if group.course_year:
                courses_set.add(group.course_year)
        faculty_courses[faculty.id] = sorted(list(courses_set))
    
    # Fakultet + Kurs -> Semestrlar
    faculty_course_semesters = {}
    for faculty in faculties:
        faculty_course_semesters[faculty.id] = {}
        for course in range(1, 8):
            semesters_set = set()
            for group in Group.query.filter_by(faculty_id=faculty.id, course_year=course).all():
                if group.semester:
                    semesters_set.add(group.semester)
            if semesters_set:
                faculty_course_semesters[faculty.id][course] = sorted(list(semesters_set))
    
    # Fakultet + Kurs + Semestr -> Ta'lim shakllari
    faculty_course_semester_education_types = {}
    for faculty in faculties:
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
                faculty_course_semester_education_types[faculty.id][course][semester] = sorted(list(faculty_course_semester_education_types[faculty.id][course][semester]))
    
    # Fakultet + Kurs + Semestr + Ta'lim shakli -> Yo'nalishlar (faqat ichida talaba bor bo'lgan yo'nalishlar)
    faculty_course_semester_education_directions = {}
    for faculty in faculties:
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
                    
                direction = group.direction
                if direction and not any(d['id'] == direction.id for d in faculty_course_semester_education_directions[faculty.id][course][semester][education_type]):
                    _lang = session.get('language', 'uz')
                    faculty_course_semester_education_directions[faculty.id][course][semester][education_type].append({
                        'id': direction.id,
                        'code': direction.code,
                        'name': (direction.get_display_name(_lang) or direction.name) or '',
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
    
    # Teskari filtrlash uchun qo'shimcha ma'lumotlar
    # Kurs -> Fakultetlar (kurs tanlanganda fakultetlarni filtrlash)
    course_faculties = {}
    for course in range(1, 8):
        faculties_set = set()
        for group in Group.query.filter_by(course_year=course).all():
            if group.faculty_id:
                faculties_set.add(group.faculty_id)
        course_faculties[course] = sorted(list(faculties_set))
    
    # Semestr -> Kurslar (semestr tanlanganda kurslarni filtrlash)
    semester_courses = {}
    # Use groups as source of truth
    all_groups_for_filter = Group.query.all()
    # JavaScript uchun guruhlar ma'lumotlari (JSON formatida)
    # Move this here to use all_groups_for_filter if needed, or just define it here
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
    for group in all_groups_for_filter:
        semester = group.semester if group.semester else 1
        course = group.course_year
        if semester not in semester_courses:
            semester_courses[semester] = set()
        semester_courses[semester].add(course)
    for semester in semester_courses:
        semester_courses[semester] = sorted(list(semester_courses[semester]))
    
    # Fakultet + Semestr -> Kurslar
    faculty_semester_courses = {}
    for faculty in faculties:
        faculty_semester_courses[faculty.id] = {}
        for group in Group.query.filter_by(faculty_id=faculty.id).all():
            semester = group.semester if group.semester else 1
            course = group.course_year
            if semester not in faculty_semester_courses[faculty.id]:
                faculty_semester_courses[faculty.id][semester] = set()
            faculty_semester_courses[faculty.id][semester].add(course)
        for semester in faculty_semester_courses[faculty.id]:
            faculty_semester_courses[faculty.id][semester] = sorted(list(faculty_semester_courses[faculty.id][semester]))
    
    # Ta'lim shakli -> Semestrlar (ta'lim shakli tanlanganda semestrlarni filtrlash)
    education_type_semesters = {}
    for group in all_groups_for_filter:
        education_type = group.education_type if group.education_type else 'kunduzgi'
        semester = group.semester if group.semester else 1
        if education_type not in education_type_semesters:
            education_type_semesters[education_type] = set()
        education_type_semesters[education_type].add(semester)
    for et in education_type_semesters:
        education_type_semesters[et] = sorted(list(education_type_semesters[et]))
    
    # Fakultet + Kurs + Ta'lim shakli -> Semestrlar
    faculty_course_education_semesters = {}
    for faculty in faculties:
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
    
    # Yo'nalish -> Ta'lim shakllari (yo'nalish tanlanganda ta'lim shakllarini filtrlash)
    # Direction no longer has education_type, so we derive it from groups
    direction_education_types = {}
    for group in all_groups_for_filter:
        if not group.direction_id:
            continue
        if group.direction_id not in direction_education_types:
            direction_education_types[group.direction_id] = set()
        direction_education_types[group.direction_id].add(group.education_type)
    
    # Convert sets to sorted lists/single values if frontend expects single value (this might be a breaking change for frontend if it expects string)
    # If the frontend expects a single string, this implies a direction ONLY has one education type.
    # But now it can have multiple. For backward compatibility if the frontend logic isn't updated yet,
    # we might need to change how this is used. 
    # Let's assume for now we might send a list or just one representative if the frontend only handles one.
    # Actually, looking at previous code: `direction_education_types[direction.id] = direction.education_type`
    # It was a string.
    # I'll update it to be a list so I can fix the frontend later if needed, or if the template iterates it.
    # Wait, if I change it to a list, it might break existing JS.
    # But since existing JS probably just uses it to populate a dropdown, unique values are needed.
    # I'll store it as list.
    for d_id in direction_education_types:
        direction_education_types[d_id] = sorted(list(direction_education_types[d_id]), key=lambda x: (x or '').lower())
    
    # Fakultet + Kurs + Semestr -> Ta'lim shakllari (ta'lim shakli tanlashda)
    # (Bu allaqachon faculty_course_semester_education_types da mavjud)
    
    # Fakultet + Kurs + Semestr + Ta'lim shakli -> Yo'nalishlar (yo'nalish tanlashda)
    # (Bu allaqachon faculty_course_semester_education_directions da mavjud)
    
    # Fakultet + Kurs -> Guruhlar (guruh tanlashda, bir xil nomli guruhlarni umumlashtirish)
    faculty_course_groups = {}
    for faculty in faculties:
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
    
    # Fakultet + Kurs + Semestr -> Guruhlar (bir xil nomli guruhlarni umumlashtirish)
    faculty_course_semester_groups = {}
    for faculty in faculties:
        faculty_course_semester_groups[faculty.id] = {}
        for course in range(1, 8):
            # Fakultet + Kurs + Semestr -> Guruhlar
            faculty_course_semester_groups[faculty.id][course] = {}
            # Faqat ichida talaba bor bo'lgan guruhlar
            groups_with_students = Group.query.filter(
                Group.faculty_id == faculty.id,
                Group.course_year == course,
                has_student
            ).all()
            
            for group in groups_with_students:
                semester = group.semester if group.semester else 1
                if semester not in faculty_course_semester_groups[faculty.id][course]:
                    faculty_course_semester_groups[faculty.id][course][semester] = {}
                
                # Bir xil nomli guruhlarni umumlashtirish
                if group.name not in faculty_course_semester_groups[faculty.id][course][semester]:
                    faculty_course_semester_groups[faculty.id][course][semester][group.name] = group.id
            
            # Dictionary'ni list'ga o'tkazish
            for semester in faculty_course_semester_groups[faculty.id][course]:
                faculty_course_semester_groups[faculty.id][course][semester] = [
                    {'id': group_id, 'name': group_name}
                    for group_name, group_id in faculty_course_semester_groups[faculty.id][course][semester].items()
                ]
                faculty_course_semester_groups[faculty.id][course][semester].sort(key=lambda x: (x['name'] or '').lower())
    
    # Fakultet + Kurs + Semestr + Ta'lim shakli -> Guruhlar (bir xil nomli guruhlarni umumlashtirish)
    faculty_course_semester_education_groups = {}
    for faculty in faculties:
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
                semester = group.semester if group.semester else 1
                education_type = group.education_type if group.education_type else 'kunduzgi'
                
                if semester not in faculty_course_semester_education_groups[faculty.id][course]:
                    faculty_course_semester_education_groups[faculty.id][course][semester] = {}
                if education_type not in faculty_course_semester_education_groups[faculty.id][course][semester]:
                    faculty_course_semester_education_groups[faculty.id][course][semester][education_type] = {}
                
                # Bir xil nomli guruhlarni umumlashtirish
                if group.name not in faculty_course_semester_education_groups[faculty.id][course][semester][education_type]:
                    faculty_course_semester_education_groups[faculty.id][course][semester][education_type][group.name] = group.id
            
            # Dictionary'ni list'ga o'tkazish
            for semester in faculty_course_semester_education_groups[faculty.id][course]:
                for et in faculty_course_semester_education_groups[faculty.id][course][semester]:
                    faculty_course_semester_education_groups[faculty.id][course][semester][et] = [
                        {'id': group_id, 'name': group_name}
                        for group_name, group_id in faculty_course_semester_education_groups[faculty.id][course][semester][et].items()
                    ]
                    faculty_course_semester_education_groups[faculty.id][course][semester][et].sort(key=lambda x: (x['name'] or '').lower())
    
    # Fakultet + Kurs + Semestr + Ta'lim shakli + Yo'nalish -> Guruhlar
    # (Bu allaqachon direction_groups da mavjud)
    
    # Guruh -> Yo'nalish, Ta'lim shakli, Semestr, Kurs, Fakultet (guruh tanlashda teskari filtrlash)
    group_info = {}
    for group in groups:
        group_info[group.id] = {
            'faculty_id': group.faculty_id,
            'course_year': group.course_year,
            'education_type': group.education_type,
            'direction_id': group.direction_id
        }
    
    # Yo'nalish ma'lumotlari (yo'nalish tanlashda teskari filtrlash)
    direction_info = {}
    for direction in directions:
        direction_info[direction.id] = {
            'faculty_id': direction.faculty_id
        }
    
    # Kurslar ro'yxati (1-4)
    courses = list(range(1, 8))
    
    # Semestrlarni guruhlardan olish
    semesters = sorted(list(set([g.semester for g in Group.query.filter(Group.semester != None).all() if g.semester])))
    
    # Ta'lim shakllari
    education_types = sorted(set([g.education_type for g in Group.query.filter(Group.education_type != None).all() if g.education_type]), key=lambda x: (x or '').lower())
    
    if request.args.get('partial'):
        return render_template('admin/students_partial.html',
                             students=students,
                             search=search,
                             current_faculty=faculty_id,
                             current_course=course_year,
                             current_semester=semester,
                             current_education_type=education_type,
                             current_direction=direction_id,
                             current_group=group_id,
                             sort_by=sort,
                             sort_order=order)
    return render_template('admin/students.html', 
                         students=students,
                         groups=groups,
                         faculties=faculties,
                         directions=directions,
                         courses=courses,
                         semesters=semesters,
                         education_types=education_types,
                         current_group=group_id,
                         current_faculty=faculty_id,
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

@bp.route('/students/<int:id>/delete', methods=['POST'])
@login_required
@admin_required
@permission_required('delete_student')
def delete_student(id):
    """Admin uchun talabani o'chirish"""
    student = User.query.get_or_404(id)
    if getattr(student, 'is_superadmin', False):
        flash(t('cannot_delete_superadmin'), 'error')
        return redirect(url_for('admin.students'))
    if student.role != 'student':
        flash(t('user_not_staff'), 'error')
        return redirect(url_for('admin.students'))
    
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
    return redirect(url_for('admin.students'))

@bp.route('/students/<int:id>/reset-password', methods=['POST'])
@login_required
@admin_required
@permission_required('reset_user_password')
def reset_student_password(id):
    """Admin uchun talaba parolini boshlang'ich holatga qaytarish (pasport raqami)"""
    student = User.query.get_or_404(id)
    if student.role != 'student':
        flash(t('user_not_staff'), 'error')
        return redirect(url_for('admin.students'))
    
    # Parolni pasport seriya raqamiga qaytarish
    if not student.passport_number:
        flash(t('passport_not_available_for_student'), 'error')
        return redirect(url_for('admin.students'))
    
    new_password = student.passport_number
    student.set_password(new_password)
    db.session.commit()
    flash(t('user_password_reset', full_name=student.full_name, new_password=new_password), 'success')
    return redirect(url_for('admin.students'))

@bp.route('/api/schedule/filters')
@login_required
@admin_required
def api_schedule_filters():
    """Dars jadvali uchun dinamik filtrlarni qaytarish"""
    from app.models import Direction, Subject, TeacherSubject
    
    # Guruh tanlanganda unga biriktirilgan fanlarni olish
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
                _lang = session.get('language', 'uz')
                subjects_data[a.subject_id] = {
                    'id': a.subject.id,
                    'name': (a.subject.get_display_name(_lang) or a.subject.name) or '',
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
    
    if group_id and subject_id and teacher_id:
        # O'qituvchi, fan va guruh uchun dars turlari
        assignments = TeacherSubject.query.filter_by(
            group_id=group_id, 
            subject_id=subject_id, 
            teacher_id=teacher_id
        ).all()
        types = list(set([a.lesson_type for a in assignments if a.lesson_type]))
        return jsonify(sorted(types))
        
    return jsonify([])

@bp.route('/schedule')
@login_required
@admin_required
@permission_required('view_schedule')
def schedule():
    """Admin uchun dars jadvali"""
    from datetime import datetime
    import calendar
    
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
    
    if month == 1:
        prev_month, prev_year = 12, year - 1
    else:
        prev_month, prev_year = month - 1, year
    if month == 12:
        next_month, next_year = 1, year + 1
    else:
        next_month, next_year = month + 1, year
    
    today_year = today.year
    today_month = today.month
    today_day = today.day
    
    # Kalendarda ko'rinadigan barcha kunlarni qamrab olish (oldingi va keyingi oy kunlari ham)
    first_calendar_date = calendar_weeks[0][0]  # Birinchi hafta, birinchi kun
    last_calendar_date = calendar_weeks[-1][-1]  # Oxirgi hafta, oxirgi kun
    start_code = int(first_calendar_date.strftime("%Y%m%d"))
    end_code = int(last_calendar_date.strftime("%Y%m%d"))
    
    # Advanced Filters
    faculty_id = request.args.get('faculty_id', type=int)
    course_year = request.args.get('course_year', type=int)
    semester = request.args.get('semester', type=int)
    direction_id = request.args.get('direction_id', type=int)
    group_id = request.args.get('group_id', type=int)
    teacher_id = request.args.get('teacher_id', type=int)
    
    faculties = Faculty.query.order_by(Faculty.name).all()

    all_teachers = User.query.outerjoin(UserRole).filter(
        or_(User.role == 'teacher', UserRole.role == 'teacher')
    ).distinct().order_by(User.full_name).all()
    
    # Mirror the data structure logic from create_schedule
    from app.models import Direction
    # Optimized robust mapping
    faculty_courses = {f.id: set() for f in faculties}
    faculty_course_semesters = {f.id: {} for f in faculties}
    faculty_course_semester_education_directions = {f.id: {} for f in faculties}
    direction_groups = {}
    
    all_groups = Group.query.all()
    for g in all_groups:
        print(f"DEBUG: Processing g: {g}, type: {type(g)}")
        fid = g.faculty_id
        if fid not in faculty_courses: continue
        
        c = g.course_year
        if not c: continue
        
        faculty_courses[fid].add(c)
        
        if g.direction:
            d = g.direction
            s = g.semester
            
            if c not in faculty_course_semesters[fid]:
                faculty_course_semesters[fid][c] = set()
            faculty_course_semesters[fid][c].add(s)
            
            if s not in faculty_course_semester_education_directions[fid]:
                faculty_course_semester_education_directions[fid][s] = {}
            if c not in faculty_course_semester_education_directions[fid][s]:
                faculty_course_semester_education_directions[fid][s][c] = {}
            
            etype = g.education_type or 'kunduzgi'
            if etype not in faculty_course_semester_education_directions[fid][s][c]:
                faculty_course_semester_education_directions[fid][s][c][etype] = []
            
            if not any(item['id'] == d.id for item in faculty_course_semester_education_directions[fid][s][c][etype]):
                _lang = session.get('language', 'uz')
                faculty_course_semester_education_directions[fid][s][c][etype].append({
                    'id': d.id,
                    'name': (d.get_display_name(_lang) or d.name) or '',
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
    for fid in faculty_courses:
        faculty_courses[fid] = sorted(list(faculty_courses[fid]))
        for c in faculty_course_semesters[fid]:
            faculty_course_semesters[fid][c] = sorted(list(faculty_course_semesters[fid][c]))


    # Filter groups that have students
    active_groups_all = [g for g in Group.query.all() if g.get_students_count() > 0]
    all_courses = sorted(list(set(g.course_year for g in active_groups_all if g.course_year)))
    all_semesters = sorted(list(set(g.semester for g in active_groups_all if g.semester)))
    all_directions = sorted(list(set(g.direction for g in active_groups_all if g.direction)), key=lambda x: x.name)
    all_groups = sorted(active_groups_all, key=lambda x: x.name)

    # Base query
    query = Schedule.query.join(Group).filter(Schedule.day_of_week.between(start_code, end_code))
    
    # Apply additive filters
    if faculty_id:
        query = query.filter(Group.faculty_id == faculty_id)
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
            # YYYYMMDD dan YYYY-MM-DD ga o'tkazish
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
    
    return render_template('admin/schedule.html', 
                         faculties=faculties,
                         faculty_courses=faculty_courses,
                         faculty_course_semesters=faculty_course_semesters,
                         faculty_course_semester_education_directions=faculty_course_semester_education_directions,
                         direction_groups=direction_groups,
                         all_courses=all_courses,
                         all_semesters=all_semesters,
                         all_directions=all_directions,
                         all_groups=all_groups,
                         all_teachers=all_teachers,
                         current_faculty_id=faculty_id,
                         current_course_year=course_year,
                         current_semester=semester,
                         current_direction_id=direction_id,
                         current_group_id=group_id,
                         current_teacher_id=teacher_id,
                         schedule_by_day=schedule_by_day,
                         schedule_by_date=schedule_by_date,
                         days_in_month=days_in_month,
                         calendar_weeks=calendar_weeks,
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
@admin_required
@permission_required('create_schedule')
def create_schedule():
    """Admin uchun dars jadvaliga qo'shish"""
    from app.models import Direction
    
    faculties = Faculty.query.order_by(Faculty.name).all()
    # Optimized robust mapping
    faculty_courses = {f.id: set() for f in faculties}
    faculty_course_semesters = {f.id: {} for f in faculties}
    faculty_course_semester_education_directions = {f.id: {} for f in faculties}
    direction_groups = {}
    
    all_groups = Group.query.all()
    for g in all_groups:
        if g.get_students_count() == 0: continue # Skip empty groups
        
        fid = g.faculty_id
        if fid not in faculty_courses: continue
        
        c = g.course_year
        if not c: continue
        
        faculty_courses[fid].add(c)
        
        if g.direction:
            d = g.direction
            s = g.semester
            
            if c not in faculty_course_semesters[fid]:
                faculty_course_semesters[fid][c] = set()
            faculty_course_semesters[fid][c].add(s)
            
            if s not in faculty_course_semester_education_directions[fid]:
                faculty_course_semester_education_directions[fid][s] = {}
            if c not in faculty_course_semester_education_directions[fid][s]:
                faculty_course_semester_education_directions[fid][s][c] = {}
            
            etype = g.education_type or 'kunduzgi'
            if etype not in faculty_course_semester_education_directions[fid][s][c]:
                faculty_course_semester_education_directions[fid][s][c][etype] = []
            
            if not any(item['id'] == d.id for item in faculty_course_semester_education_directions[fid][s][c][etype]):
                _lang = session.get('language', 'uz')
                faculty_course_semester_education_directions[fid][s][c][etype].append({
                    'id': d.id,
                    'name': (d.get_display_name(_lang) or d.name) or '',
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
    for fid in faculty_courses:
        faculty_courses[fid] = sorted(list(faculty_courses[fid]))
        for c in faculty_course_semesters[fid]:
            faculty_course_semesters[fid][c] = sorted(list(faculty_course_semesters[fid][c]))


    # GET parametrlar orqali kelgan default sana
    default_date = request.args.get('date')
    
    if request.method == 'POST':
        date_str = request.form.get('schedule_date')
        date_code = None
        if date_str:
            try:
                parsed_date = datetime.strptime(date_str, "%Y-%m-%d")
                date_code = int(parsed_date.strftime("%Y%m%d"))
            except ValueError:
                flash(t('date_invalid_format'), 'error')
                return redirect(url_for('admin.create_schedule'))
        
        if not date_code:
            flash(t('date_required'), 'error')
            return redirect(url_for('admin.create_schedule'))
        
        subject_id = request.form.get('subject_id', type=int)
        group_id = request.form.get('group_id', type=int)
        teacher_id = request.form.get('teacher_id', type=int)
        start_time = request.form.get('start_time')
        link = request.form.get('link')
        # O'qituvchiga biriktirilgan barcha dars turlarini topish
        from app.models import TeacherSubject
        assignments = TeacherSubject.query.filter_by(
            group_id=group_id,
            subject_id=subject_id,
            teacher_id=teacher_id
        ).all()
        
        if not assignments:
            flash(t('teacher_not_assigned_to_lesson_type'), 'error')
            return redirect(url_for('admin.create_schedule'))
        
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
        
        # Takrorlanishni tekshirish
        existing = Schedule.query.filter_by(
            group_id=group_id,
            day_of_week=date_code,
            start_time=start_time
        ).first()
        
        if existing:
            flash(t('lesson_already_exists_at_time', start_time=start_time, subject_name=existing.subject.name), 'warning')
            return redirect(url_for('admin.schedule', year=parsed_date.year, month=parsed_date.month, group=group_id))

        # Zoom meeting avtomatik yaratish (link bo'sh bo'lsa va Zoom sozlangan bo'lsa)
        if not link or not link.strip():
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

        schedule_entry = Schedule(
            subject_id=subject_id,
            group_id=group_id,
            teacher_id=teacher_id,
            day_of_week=date_code,
            start_time=start_time,
            end_time=None,
            link=link,
            lesson_type=lesson_type_display[:20] # Model limitiga moslash
        )

        db.session.add(schedule_entry)
        db.session.commit()
        
        flash(t('schedule_added'), 'success')
            
        return redirect(url_for('admin.schedule', year=parsed_date.year, month=parsed_date.month, group=group_id))
    
    return render_template('admin/create_schedule.html',
                         faculties=faculties,
                         faculty_courses=faculty_courses,
                         faculty_course_semesters=faculty_course_semesters,
                         faculty_course_semester_education_directions=faculty_course_semester_education_directions,
                         direction_groups=direction_groups,
                         default_date=default_date)


@bp.route('/schedule/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
@permission_required('edit_schedule')
def edit_schedule(id):
    """Admin uchun dars jadvalini tahrirlash"""
    schedule = Schedule.query.get_or_404(id)
    
    faculties = Faculty.query.order_by(Faculty.name).all()
    
    # Mirror the data structure logic from create_schedule
    from app.models import Direction
    faculty_courses = {}
    faculty_course_semesters = {}
    faculty_course_semester_education_directions = {}
    direction_groups = {}
    
    # Optimized robust mapping
    faculty_courses = {f.id: set() for f in faculties}
    faculty_course_semesters = {f.id: {} for f in faculties}
    faculty_course_semester_education_directions = {f.id: {} for f in faculties}
    direction_groups = {}
    
    all_groups = Group.query.all()
    for g in all_groups:
        if g.get_students_count() == 0: continue # Skip empty groups
        
        fid = g.faculty_id
        if fid not in faculty_courses: continue
        
        c = g.course_year
        if not c: continue
        
        faculty_courses[fid].add(c)
        
        if g.direction:
            d = g.direction
            s = g.semester
            
            if c not in faculty_course_semesters[fid]:
                faculty_course_semesters[fid][c] = set()
            faculty_course_semesters[fid][c].add(s)
            
            if s not in faculty_course_semester_education_directions[fid]:
                faculty_course_semester_education_directions[fid][s] = {}
            if c not in faculty_course_semester_education_directions[fid][s]:
                faculty_course_semester_education_directions[fid][s][c] = {}
            
            etype = g.education_type or 'kunduzgi'
            if etype not in faculty_course_semester_education_directions[fid][s][c]:
                faculty_course_semester_education_directions[fid][s][c][etype] = []
            
            if not any(item['id'] == d.id for item in faculty_course_semester_education_directions[fid][s][c][etype]):
                _lang = session.get('language', 'uz')
                faculty_course_semester_education_directions[fid][s][c][etype].append({
                    'id': d.id,
                    'name': (d.get_display_name(_lang) or d.name) or '',
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
    for fid in faculty_courses:
        faculty_courses[fid] = sorted(list(faculty_courses[fid]))
        for c in faculty_course_semesters[fid]:
            faculty_course_semesters[fid][c] = sorted(list(faculty_course_semesters[fid][c]))

    
    # Prepare pre-population data
    current_group = schedule.group
    current_faculty_id = current_group.faculty_id
    current_direction = current_group.direction
    current_course_year = current_group.course_year
    current_semester = current_group.semester if current_group.semester else 1
    
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
                flash(t('date_invalid_format_use_calendar'), 'error')
                return redirect(url_for('admin.edit_schedule', id=id))
        
        if not date_code:
            flash(t('date_required_select'), 'error')
            return redirect(url_for('admin.edit_schedule', id=id))
        
        schedule.subject_id = request.form.get('subject_id', type=int)
        schedule.group_id = request.form.get('group_id', type=int)
        schedule.teacher_id = request.form.get('teacher_id', type=int)
        schedule.day_of_week = date_code
        schedule.start_time = request.form.get('start_time')
        schedule.end_time = None # User request: remove end time
        schedule.link = request.form.get('link')
        
        # O'qituvchiga biriktirilgan barcha dars turlarini topish
        from app.models import TeacherSubject
        assignments = TeacherSubject.query.filter_by(
            group_id=schedule.group_id,
            subject_id=schedule.subject_id,
            teacher_id=schedule.teacher_id
        ).all()
        
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
        schedule.lesson_type = "/".join(found_types)[:20] if found_types else 'Ma\'ruza'

        
        db.session.commit()
        
        flash(t('schedule_updated'), 'success')
        return redirect(url_for(
            'admin.schedule',
            year=parsed_date.year,
            month=parsed_date.month,
            group=schedule.group_id
        ))
    
    schedule_date = existing_date.strftime("%Y-%m-%d")
    year = existing_date.year
    month = existing_date.month
    
    return render_template(
        'admin/edit_schedule.html',
        faculties=faculties,
        faculty_courses=faculty_courses,
        faculty_course_semesters=faculty_course_semesters,
        faculty_course_semester_education_directions=faculty_course_semester_education_directions,
        direction_groups=direction_groups,
        schedule=schedule,
        schedule_date=schedule_date,
        current_faculty_id=current_faculty_id,
        current_course_year=current_course_year,
        current_semester=current_semester,
        current_direction_id=current_direction.id if current_direction else None,
        year=year,
        month=month)


@bp.route('/schedule/<int:id>/delete', methods=['POST'])
@login_required
@admin_required
@permission_required('delete_schedule')
def delete_schedule(id):
    """Admin uchun dars jadvalini o'chirish"""
    schedule = Schedule.query.get_or_404(id)
    
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
    
    return redirect(url_for('admin.schedule', year=schedule_year, month=schedule_month))


# ==================== API ENDPOINTS ====================

@bp.route('/api/groups')
@login_required
def api_groups():
    """Get groups with optional filters"""
    query = Group.query
    
    # Apply filters
    faculty_id = request.args.get('faculty_id')
    direction_id = request.args.get('direction_id')
    course_year = request.args.get('course_year')
    semester = request.args.get('semester')
    education_type = request.args.get('education_type')
    enrollment_year = request.args.get('enrollment_year')
    
    if faculty_id:
        query = query.filter(Group.faculty_id == int(faculty_id))
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
    
    groups = query.all()
    
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
def api_group_detail(group_id):
    """Get detailed information about a specific group"""
    group = Group.query.get_or_404(group_id)
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
def api_directions():
    """Get directions with optional faculty filter"""
    faculty_id = request.args.get('faculty_id')
    
    query = Direction.query
    if faculty_id:
        query = query.filter(Direction.faculty_id == int(faculty_id))
    
    directions = query.all()
    
    return jsonify([{
        'id': d.id,
        'code': d.code,
        'name': d.name,
        'formatted_direction': d.formatted_direction,
        'faculty_id': d.faculty_id
    } for d in directions])

