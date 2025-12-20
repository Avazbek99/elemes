from flask import Blueprint, render_template, request, redirect, url_for, flash, session, url_for as flask_url_for
from flask_login import login_required, current_user
from app.models import User, Subject, Assignment, Announcement, Schedule, Submission, Message, Group, Faculty, TeacherSubject
from app import db
from datetime import datetime, timedelta
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
    
    if role in user_roles:
        session['current_role'] = role
        flash(f"Rol {role} ga o'zgartirildi", 'success')
    else:
        flash("Sizda bu rolga kirish huquqi yo'q", 'error')
    
    return redirect(request.referrer or url_for('main.dashboard'))

@bp.route('/')
def index():
    """Asosiy sahifa"""
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    return redirect(url_for('auth.login'))

@bp.route('/dashboard')
@login_required
def dashboard():
    from flask import current_app
    import os
    print("=" * 50)
    print("🔍 DEBUG: Flask Template Configuration")
    print("=" * 50)
    print("TEMPLATE FOLDER:", current_app.template_folder)
    print("ROOT PATH:", current_app.root_path)
    template_path = os.path.join(current_app.root_path, current_app.template_folder)
    print("FULL TEMPLATE PATH:", template_path)
    print("Dashboard exists:", os.path.exists(os.path.join(template_path, 'dashboard.html')))
    print("Base exists:", os.path.exists(os.path.join(template_path, 'base.html')))
    print("=" * 50)
    """Dashboard sahifasi"""
    user = current_user
    
    # Foydalanuvchi rollariga qarab turli ma'lumotlar
    stats = {}
    announcements = []
    recent_assignments = []
    upcoming_schedules = []
    
    if user.role == 'student':
        # Talaba uchun
        stats = {
            'subjects': user.get_subjects(),
            'assignments': Assignment.query.join(Subject).join(TeacherSubject).filter(
                TeacherSubject.group_id == user.group_id
            ).count(),
            'submissions': Submission.query.filter_by(student_id=user.id).count(),
            'completed_assignments': Submission.query.filter_by(student_id=user.id).filter(Submission.score != None).count()
        }
        
        # E'lonlar
        announcements = Announcement.query.filter(
            (Announcement.target_roles.contains('student')) |
            (Announcement.target_roles == None)
        ).order_by(Announcement.created_at.desc()).limit(5).all()
        
        # Yaqin topshiriqlar
        recent_assignments = Assignment.query.join(Subject).join(TeacherSubject).filter(
            TeacherSubject.group_id == user.group_id
        ).order_by(Assignment.due_date.desc()).limit(5).all()
        
        # Dars jadvali
        if user.group_id:
            upcoming_schedules = Schedule.query.filter_by(group_id=user.group_id).all()
    
    elif user.role == 'teacher':
        # O'qituvchi uchun
        teacher_subjects = TeacherSubject.query.filter_by(teacher_id=user.id).all()
        subject_ids = [ts.subject_id for ts in teacher_subjects]
        
        stats = {
            'subjects': Subject.query.filter(Subject.id.in_(subject_ids)).all() if subject_ids else [],
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
    
    elif user.role == 'dean':
        # Dekan uchun
        faculty = Faculty.query.get(user.faculty_id) if user.faculty_id else None
        
        if faculty:
            stats = {
                'total_students': User.query.join(Group).filter(Group.faculty_id == faculty.id, User.role == 'student').count(),
                'total_teachers': User.query.filter_by(role='teacher').count(),
                'total_subjects': Subject.query.filter_by(faculty_id=faculty.id).count(),
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
    
    return render_template('dashboard.html', stats=stats, announcements=announcements, 
                         recent_assignments=recent_assignments, upcoming_schedules=upcoming_schedules)

@bp.route('/announcements')
@login_required
def announcements():
    """E'lonlar sahifasi"""
    user = current_user
    
    # Foydalanuvchi roliga qarab e'lonlarni filtrlash
    query = Announcement.query
    
    if user.role == 'student':
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
    
    announcements = query.order_by(Announcement.created_at.desc()).all()
    
    return render_template('announcements.html', announcements=announcements)

@bp.route('/messages')
@login_required
def messages():
    """Xabarlar sahifasi"""
    # Foydalanuvchiga kelgan xabarlar
    received_messages = Message.query.filter_by(receiver_id=current_user.id).order_by(Message.created_at.desc()).all()
    
    # Foydalanuvchi yuborgan xabarlar
    sent_messages = Message.query.filter_by(sender_id=current_user.id).order_by(Message.created_at.desc()).all()
    
    return render_template('messages.html', received_messages=received_messages, sent_messages=sent_messages)

@bp.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    """Profil sozlamalari"""
    if request.method == 'POST':
        user = current_user
        
        # Ma'lumotlarni yangilash
        user.full_name = request.form.get('full_name', user.full_name)
        user.email = request.form.get('email', user.email)
        user.phone = request.form.get('phone', user.phone)
        
        # Parolni o'zgartirish
        old_password = request.form.get('old_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        
        if old_password and new_password:
            if user.check_password(old_password):
                if new_password == confirm_password:
                    user.set_password(new_password)
                    flash("Parol muvaffaqiyatli o'zgartirildi", 'success')
                else:
                    flash("Yangi parollar mos kelmaydi", 'error')
                    return render_template('settings.html')
            else:
                flash("Eski parol noto'g'ri", 'error')
                return render_template('settings.html')
        
        db.session.commit()
        flash("Ma'lumotlar muvaffaqiyatli yangilandi", 'success')
        return redirect(url_for('main.settings'))
    
    return render_template('settings.html')
