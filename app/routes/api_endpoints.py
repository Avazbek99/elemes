from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, send_file, Response, session
from flask_login import login_required, current_user
from app.models import User, Faculty, Group, Subject, TeacherSubject, Assignment, Direction, GradeScale, Schedule, UserRole, StudentPayment, DirectionCurriculum
from app import db
from functools import wraps
from datetime import datetime
from sqlalchemy import func, or_

from app.utils.excel_export import create_all_users_excel, create_subjects_excel
from app.utils.excel_import import (
    import_students_from_excel, generate_sample_file,
    import_directions_from_excel,
    import_staff_from_excel, generate_staff_sample_file,
    import_subjects_from_excel, generate_subjects_sample_file,
    import_curriculum_from_excel, generate_curriculum_sample_file,
    import_schedule_from_excel, generate_schedule_sample_file
)
from werkzeug.security import generate_password_hash

bp = Blueprint('admin', __name__, url_prefix='/admin')

def admin_required(f):
    """Faqat admin uchun (joriy tanlangan rol yoki asosiy rol)"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash("Sizda bu sahifaga kirish huquqi yo'q", 'error')
            return redirect(url_for('main.dashboard'))
        
        # Session'dan joriy rol ni olish
        current_role = session.get('current_role', current_user.role)
        
        # Foydalanuvchida admin roli borligini tekshirish
        if current_role == 'admin' and 'admin' in current_user.get_roles():
            return f(*args, **kwargs)
        elif current_user.has_role('admin'):
            # Agar joriy rol admin emas, lekin foydalanuvchida admin roli bor bo'lsa, ruxsat berish
            return f(*args, **kwargs)
        else:
            flash("Sizda bu sahifaga kirish huquqi yo'q", 'error')
            return redirect(url_for('main.dashboard'))
    return decorated_function


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
        'faculty_id': d.faculty_id
    } for d in directions])
