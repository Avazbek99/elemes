"""
Davomat va KPI sahifalari – staff, student, KPI hisoboti, live monitor.
"""
from datetime import date, datetime, timedelta
from app.attendance import attendance_bp
from flask import render_template, redirect, url_for, request, flash, jsonify
from flask_login import login_required, current_user

from app import db
from app.models import (
    User, UserRole,
    StaffAttendanceDaily, StudentAttendanceDaily,
    FaceLog,
    STAFF_ROLES, STAFF_STATUS_ON_TIME, STAFF_STATUS_LATE,
    STAFF_STATUS_SERIOUS_LATE, STAFF_STATUS_ABSENT,
    STUDENT_STATUS_PRESENT, STUDENT_STATUS_ABSENT,
)
from app.services.attendance_service import (
    compute_daily_attendance,
    get_kpi_summary,
    _device_id_to_user,
    _is_staff,
    _is_student,
)
from app.utils.translations import get_translation


def _t(key):
    from flask import session
    lang = session.get('language', 'uz') if current_user and current_user.is_authenticated else 'uz'
    return get_translation(key, lang)


def _require_superadmin():
    if not current_user.is_authenticated or not getattr(current_user, 'is_superadmin', False):
        from flask import abort
        abort(403)


@attendance_bp.route('/staff-attendance', methods=['GET'])
@login_required
def staff_attendance():
    _require_superadmin()
    target_date = request.args.get('date')
    try:
        d = date.fromisoformat(target_date) if target_date else date.today()
    except (ValueError, TypeError):
        d = date.today()
    rows = StaffAttendanceDaily.query.filter_by(date=d).order_by(
        StaffAttendanceDaily.first_entry.desc().nullslast(),
        StaffAttendanceDaily.staff_id
    ).all()
    return render_template(
        'attendance/staff_attendance.html',
        rows=rows,
        target_date=d,
    )


@attendance_bp.route('/student-attendance', methods=['GET'])
@login_required
def student_attendance():
    _require_superadmin()
    target_date = request.args.get('date')
    try:
        d = date.fromisoformat(target_date) if target_date else date.today()
    except (ValueError, TypeError):
        d = date.today()
    rows = StudentAttendanceDaily.query.filter_by(date=d).order_by(
        StudentAttendanceDaily.first_entry.desc().nullslast(),
        StudentAttendanceDaily.student_id
    ).all()
    return render_template(
        'attendance/student_attendance.html',
        rows=rows,
        target_date=d,
    )


@attendance_bp.route('/kpi-report', methods=['GET'])
@login_required
def kpi_report():
    _require_superadmin()
    start = request.args.get('start')
    end = request.args.get('end')
    try:
        start_date = date.fromisoformat(start) if start else date.today() - timedelta(days=30)
        end_date = date.fromisoformat(end) if end else date.today()
    except (ValueError, TypeError):
        start_date = date.today() - timedelta(days=30)
        end_date = date.today()
    if start_date > end_date:
        start_date, end_date = end_date, start_date
    summary = get_kpi_summary(start_date, end_date)
    return render_template(
        'attendance/kpi_report.html',
        summary=summary,
        start_date=start_date,
        end_date=end_date,
    )


# live-monitor at /live-monitor - registered in main.bp


@attendance_bp.route('/compute-daily', methods=['POST'])
@login_required
def compute_daily():
    _require_superadmin()
    target = request.form.get('date') or request.args.get('date')
    try:
        d = date.fromisoformat(target) if target else date.today() - timedelta(days=1)
    except (ValueError, TypeError):
        d = date.today() - timedelta(days=1)
    try:
        compute_daily_attendance(d)
        flash(_t('attendance_computed') or f"Davomat hisoblandi: {d}", "success")
    except Exception as e:
        flash(str(e), "error")
    return redirect(request.referrer or url_for('attendance.staff_attendance'))


# Flask-SocketIO events will be in a separate module if used
