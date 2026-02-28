"""
Davomat va KPI xizmati – Hikvision face log asosida kunlik hisoblash.
Staff: 08:30–17:30, OnTime/Late/Serious/Absent, KPI score.
Student: Present/Absent (kamida 1 IN).
"""
from datetime import date, datetime, time, timedelta
from sqlalchemy import func, and_

from app import db
from app.models import (
    User, FaceLog, UserRole,
    StaffAttendanceDaily, StudentAttendanceDaily,
    STAFF_ROLES, STAFF_STATUS_ON_TIME, STAFF_STATUS_LATE,
    STAFF_STATUS_SERIOUS_LATE, STAFF_STATUS_ABSENT,
    STUDENT_STATUS_PRESENT, STUDENT_STATUS_ABSENT,
)

WORK_START = time(8, 30)   # 08:30
LATE_THRESHOLD_MIN = 10    # 10 min gacha = Late, undan ortiq = Serious
KPI_ON_TIME = 1
KPI_LATE = 0
KPI_SERIOUS = -1
KPI_ABSENT = -2


def _device_id_to_user(device_employee_id):
    """device_employee_id ni User ga bog'lash: employee_code, id, login, student_id."""
    if not device_employee_id:
        return None
    dev_id = str(device_employee_id).strip()
    if not dev_id:
        return None
    # 1. employee_code
    u = User.query.filter(User.employee_code == dev_id).first()
    if u:
        return u
    # 2. User.id
    try:
        uid = int(dev_id)
        u = User.query.get(uid)
        if u:
            return u
    except (ValueError, TypeError):
        pass
    # 3. login
    u = User.query.filter(User.login == dev_id).first()
    if u:
        return u
    # 4. student_id
    u = User.query.filter(User.student_id == dev_id).first()
    if u:
        return u
    return None


def _is_staff(user):
    if not user:
        return False
    roles = user.get_roles()
    return any(r in STAFF_ROLES for r in roles)


def _is_student(user):
    if not user:
        return False
    return 'student' in user.get_roles()


def compute_staff_daily(date_obj):
    """
    Kun uchun barcha staff ning davomatini hisoblab StaffAttendanceDaily ga yozadi.
    Face logs dan IN/OUT ni olish; direction bo'lmasa barcha loglar IN deb hisoblanadi.
    """
    day_start = datetime.combine(date_obj, time.min)
    day_end = datetime.combine(date_obj, time(23, 59, 59))
    work_start_dt = datetime.combine(date_obj, WORK_START)

    staff_ids = set()
    for r in UserRole.query.filter(UserRole.role.in_(STAFF_ROLES)).all():
        staff_ids.add(r.user_id)

    staff_logs = {}  # staff_id -> [(event_time, direction), ...]
    logs = FaceLog.query.filter(
        FaceLog.event_time >= day_start,
        FaceLog.event_time <= day_end,
        FaceLog.device_employee_id.isnot(None),
    ).order_by(FaceLog.event_time.asc()).all()

    for log in logs:
        user = _device_id_to_user(log.device_employee_id)
        if not user or not _is_staff(user):
            continue
        direction = (log.direction or 'IN').upper()
        if direction not in ('IN', 'OUT'):
            direction = 'IN'
        staff_logs.setdefault(user.id, []).append((log.event_time, direction))

    for staff_id in staff_ids:
        rows = staff_logs.get(staff_id, [])
        ins = [t for t, d in rows if d == 'IN']
        outs = [t for t, d in rows if d == 'OUT']

        first_entry = min(ins) if ins else None
        # last_exit: oxirgi OUT yoki agar OUT bo'lmasa oxirgi IN
        last_exit = None
        if outs:
            last_exit = max(outs)
        elif ins:
            last_exit = max(ins)

        late_minutes = 0
        status = STAFF_STATUS_ABSENT
        kpi_score = KPI_ABSENT

        if first_entry:
            work_duration = None
            if first_entry and last_exit:
                work_duration = int((last_exit - first_entry).total_seconds() / 60)

            if first_entry.time() <= WORK_START:
                status = STAFF_STATUS_ON_TIME
                kpi_score = KPI_ON_TIME
            else:
                delta = first_entry - work_start_dt
                late_minutes = max(0, int(delta.total_seconds() / 60))
                if late_minutes <= LATE_THRESHOLD_MIN:
                    status = STAFF_STATUS_LATE
                    kpi_score = KPI_LATE
                else:
                    status = STAFF_STATUS_SERIOUS_LATE
                    kpi_score = KPI_SERIOUS

            rec = StaffAttendanceDaily.query.filter_by(staff_id=staff_id, date=date_obj).first()
            if rec:
                rec.first_entry = first_entry
                rec.last_exit = last_exit
                rec.late_minutes = late_minutes
                rec.work_duration = work_duration
                rec.status = status
                rec.kpi_score = kpi_score
                rec.updated_at = datetime.utcnow()
            else:
                rec = StaffAttendanceDaily(
                    staff_id=staff_id,
                    date=date_obj,
                    first_entry=first_entry,
                    last_exit=last_exit,
                    late_minutes=late_minutes,
                    work_duration=work_duration,
                    status=status,
                    kpi_score=kpi_score,
                )
                db.session.add(rec)
        else:
            rec = StaffAttendanceDaily.query.filter_by(staff_id=staff_id, date=date_obj).first()
            if rec:
                rec.first_entry = None
                rec.last_exit = None
                rec.late_minutes = 0
                rec.work_duration = None
                rec.status = STAFF_STATUS_ABSENT
                rec.kpi_score = KPI_ABSENT
                rec.updated_at = datetime.utcnow()
            else:
                rec = StaffAttendanceDaily(
                    staff_id=staff_id,
                    date=date_obj,
                    status=STAFF_STATUS_ABSENT,
                    kpi_score=KPI_ABSENT,
                )
                db.session.add(rec)

    db.session.commit()


def compute_student_daily(date_obj):
    """Talabalar uchun kunlik davomat – kamida 1 ta IN bo'lsa Present."""
    day_start = datetime.combine(date_obj, time.min)
    day_end = datetime.combine(date_obj, time(23, 59, 59))

    student_ids = set()
    for r in UserRole.query.filter(UserRole.role == 'student').all():
        student_ids.add(r.user_id)
    # Eski role ustuniga ham qarab
    for u in User.query.filter(User.role == 'student').all():
        student_ids.add(u.id)

    student_ins = {}
    logs = FaceLog.query.filter(
        FaceLog.event_time >= day_start,
        FaceLog.event_time <= day_end,
        FaceLog.device_employee_id.isnot(None),
    ).all()

    for log in logs:
        user = _device_id_to_user(log.device_employee_id)
        if not user or not _is_student(user):
            continue
        direction = (log.direction or 'IN').upper()
        if direction == 'IN':
            student_ins.setdefault(user.id, []).append(log.event_time)

    for student_id in student_ids:
        ins = student_ins.get(student_id, [])
        first_entry = min(ins) if ins else None
        last_exit = max(ins) if ins else None
        status = STUDENT_STATUS_PRESENT if ins else STUDENT_STATUS_ABSENT

        rec = StudentAttendanceDaily.query.filter_by(student_id=student_id, date=date_obj).first()
        if rec:
            rec.first_entry = first_entry
            rec.last_exit = last_exit
            rec.status = status
            rec.updated_at = datetime.utcnow()
        else:
            rec = StudentAttendanceDaily(
                student_id=student_id,
                date=date_obj,
                first_entry=first_entry,
                last_exit=last_exit,
                status=status,
            )
            db.session.add(rec)

    db.session.commit()


def compute_daily_attendance(date_obj=None):
    """Berilgan kun uchun staff va student davomatini hisoblash. Default: kecha."""
    if date_obj is None:
        date_obj = date.today() - timedelta(days=1)
    compute_staff_daily(date_obj)
    compute_student_daily(date_obj)


def get_kpi_summary(start_date, end_date):
    """Staff KPI bo'yicha hisobot – davr uchun o'rtacha/yig'indi."""
    rows = db.session.query(
        StaffAttendanceDaily.staff_id,
        func.sum(StaffAttendanceDaily.kpi_score).label('total_kpi'),
        func.count(StaffAttendanceDaily.id).label('days_count'),
    ).filter(
        StaffAttendanceDaily.date >= start_date,
        StaffAttendanceDaily.date <= end_date,
    ).group_by(StaffAttendanceDaily.staff_id).all()

    result = []
    for r in rows:
        user = User.query.get(r.staff_id)
        if user:
            result.append({
                'staff_id': r.staff_id,
                'full_name': user.full_name or '-',
                'total_kpi': r.total_kpi or 0,
                'days_count': r.days_count or 0,
                'avg_kpi': round((r.total_kpi or 0) / max(1, r.days_count or 1), 2),
            })
    return sorted(result, key=lambda x: -x['total_kpi'])
