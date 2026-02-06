from flask import Blueprint, render_template, request, redirect, url_for, flash, Response, session
from flask_login import login_required, current_user
from app.models import User, StudentPayment, Group, Faculty, Direction, DirectionContractAmount
from app import db
from functools import wraps
from datetime import datetime, date
from sqlalchemy import func, or_, exists
from collections import defaultdict
from app.utils.translations import t
from app.utils.excel_import import _parse_academic_year
from app.utils.date_utils import _parse_date

bp = Blueprint('accounting', __name__, url_prefix='/accounting')

def accounting_required(f):
    """Faqat buxgalteriya uchun (joriy tanlangan rol yoki asosiy rol)"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash(t('no_access_permission'), 'error')
            return redirect(url_for('main.dashboard'))
        
        # Session'dan joriy rol ni olish
        current_role = session.get('current_role', current_user.role)
        
        # Foydalanuvchida accounting roli borligini tekshirish
        if current_role == 'accounting' and 'accounting' in current_user.get_roles():
            return f(*args, **kwargs)
        elif current_user.has_role('accounting'):
            # Agar joriy rol accounting emas, lekin foydalanuvchida accounting roli bor bo'lsa, ruxsat berish
            return f(*args, **kwargs)
        else:
            flash(t('no_access_permission'), 'error')
            return redirect(url_for('main.dashboard'))
    return decorated_function


def _get_effective_contract_for_student(student, payments_for_student):
    """Talaba uchun umumiy kontrakt: maxsus (StudentPayment) + yo'nalish (DirectionContractAmount).
    Maxsus kontrakt bo'lgan o'quv yillari uchun yo'nalish summasini o'rniga maxsus qo'llanadi."""
    custom_dict = {}
    for p in payments_for_student:
        if p.contract_amount and float(p.contract_amount) > 0 and p.academic_year:
            ay = (p.academic_year or '').strip()
            if not ay:
                continue
            if ay not in custom_dict:
                custom_dict[ay] = float(p.contract_amount)
    latest_custom_year = max(custom_dict.keys()) if custom_dict else None

    total = 0
    # Yo'nalishdan: maxsus yil va undan oldingilarni o'tkazib yuboramiz
    if student and student.group and student.group.direction_id:
        g = student.group
        grp_et = (g.education_type or '').strip() or None
        base_year = g.enrollment_year or 0
        for a in DirectionContractAmount.query.filter(
            DirectionContractAmount.direction_id == g.direction_id,
            DirectionContractAmount.enrollment_year >= base_year
        ).all():
            a_et = (a.education_type or '').strip() or None
            if a_et is None or a_et == grp_et:
                ay_key = f"{a.enrollment_year}-{a.enrollment_year + 1}"
                if latest_custom_year and ay_key <= latest_custom_year:
                    continue
                total += float(a.contract_amount)
    # Maxsus kontraktlarni qo'shamiz
    total += sum(custom_dict.values())
    return total


def _get_current_year_payment_info(student, payments_for_student):
    """Talaba uchun joriy o'quv yili bo'yicha to'lov ma'lumotlari: kontrakt, to'langan, qolgan, ortiqcha.
    To'lovlar ketma-ket taqsimlanadi (avval oldingi yillar, keyin joriy yil)."""
    from app.utils.date_utils import get_tashkent_time
    custom_dict = {}
    for p in payments_for_student:
        if p.contract_amount and float(p.contract_amount) > 0 and p.academic_year:
            ay = (p.academic_year or '').strip()
            if not ay:
                continue
            ps, pe = getattr(p, 'period_start', None), getattr(p, 'period_end', None)
            entry = {'amount': float(p.contract_amount), 'payment_id': p.id, 'period_start': ps, 'period_end': pe}
            if ay not in custom_dict:
                custom_dict[ay] = entry
            elif (ps and pe) and (not custom_dict[ay].get('period_start') or not custom_dict[ay].get('period_end')):
                custom_dict[ay] = entry
    latest_custom_year = max(custom_dict.keys()) if custom_dict else None

    contract_by_year = []
    if student and student.group and student.group.direction_id:
        g = student.group
        grp_et = (g.education_type or '').strip() or None
        base_year = g.enrollment_year or 0
        for a in DirectionContractAmount.query.filter(
            DirectionContractAmount.direction_id == g.direction_id,
            DirectionContractAmount.enrollment_year >= base_year
        ).all():
            a_et = (a.education_type or '').strip() or None
            if a_et is None or a_et == grp_et:
                ay_key = f"{a.enrollment_year}-{a.enrollment_year + 1}"
                if latest_custom_year and ay_key <= latest_custom_year:
                    continue
                contract_by_year.append({'academic_year': ay_key, 'amount': float(a.contract_amount), 'paid_amount': 0})
    for ay in sorted(custom_dict.keys()):
        info = custom_dict[ay]
        contract_by_year.append({'academic_year': ay, 'amount': info['amount'], 'paid_amount': 0})
    contract_by_year.sort(key=lambda x: x['academic_year'])

    remaining_per_row = [float(row['amount']) for row in contract_by_year]
    payments_sorted = sorted(payments_for_student, key=lambda p: (p.created_at or p.updated_at or datetime.min))
    row_idx = 0
    for p in payments_sorted:
        amt = float(p.paid_amount or 0)
        if amt <= 0:
            continue
        while amt > 0 and row_idx < len(contract_by_year):
            need = remaining_per_row[row_idx]
            if need <= 0:
                row_idx += 1
                continue
            take = min(amt, need)
            contract_by_year[row_idx]['paid_amount'] = contract_by_year[row_idx].get('paid_amount', 0) + take
            remaining_per_row[row_idx] = need - take
            amt -= take
            if remaining_per_row[row_idx] <= 0:
                row_idx += 1

    now_tz = get_tashkent_time()
    current_ay = f"{now_tz.year}-{now_tz.year + 1}" if now_tz.month >= 9 else f"{now_tz.year - 1}-{now_tz.year}"
    current_row = next((r for r in contract_by_year if r.get('academic_year') == current_ay), None)
    contract = float(current_row['amount']) if current_row else 0
    paid = float(current_row.get('paid_amount', 0)) if current_row else 0
    remaining = max(0, contract - paid)
    # Ortiqcha to'lov: jami to'lagan - (joriy o'quv yiligacha barcha kontraktlar yig'indisi)
    total_paid = sum(float(p.paid_amount or 0) for p in payments_for_student)
    total_contract_through_current = sum(float(r['amount']) for r in contract_by_year if r.get('academic_year', '') <= current_ay)
    overpayment = max(0, total_paid - total_contract_through_current)
    percentage = (min(paid, contract) / contract * 100) if contract > 0 else 0
    return {'contract': contract, 'paid': paid, 'remaining': remaining, 'overpayment': overpayment, 'percentage': percentage, 'first_id': payments_for_student[0].id if payments_for_student else None}


def _accounting_index_all_students(page, search, group_id, faculty_id, course_year, semester,
                                   education_type, direction_id, faculty_restrict=None,
                                   faculty=None, now_dt=None, is_admin=False):
    """Barcha talabalar ro'yxati, to'liq filtrlash, payment_map bilan."""
    query = User.query.filter(User.role == 'student')

    if faculty_restrict:
        faculty_group_ids = [g.id for g in Group.query.filter_by(faculty_id=faculty_restrict).all()]
        query = query.filter(User.group_id.in_(faculty_group_ids))

    if search and search.strip():
        search = search.strip()
        query = query.filter(or_(
            User.full_name.ilike(f'%{search}%'),
            User.login.ilike(f'%{search}%'),
            User.passport_number.ilike(f'%{search}%'),
            User.pinfl.ilike(f'%{search}%'),
            User.phone.ilike(f'%{search}%'),
            User.email.ilike(f'%{search}%'),
            User.student_id.ilike(f'%{search}%')
        ))

    if group_id:
        query = query.filter(User.group_id == group_id)
    else:
        group_filters = {}
        if faculty_id and not faculty_restrict:
            group_filters['faculty_id'] = faculty_id
        if faculty_restrict:
            group_filters['faculty_id'] = faculty_restrict
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

    if semester:
        query = query.join(Group, User.group_id == Group.id).filter(Group.semester == semester)

    students = query.order_by(User.full_name).paginate(page=page, per_page=50, error_out=False)

    student_ids = [s.id for s in students.items]
    all_payments = StudentPayment.query.filter(StudentPayment.student_id.in_(student_ids)).all() if student_ids else []
    payments_by_student = defaultdict(list)
    for p in all_payments:
        payments_by_student[p.student_id].append(p)

    payment_map = {}
    for s in students.items:
        sp = payments_by_student.get(s.id, [])
        cy_info = _get_current_year_payment_info(s, sp)
        payment_map[s.id] = cy_info

    total_contract = db.session.query(func.sum(StudentPayment.contract_amount)).scalar() or 0
    total_paid = db.session.query(func.sum(StudentPayment.paid_amount)).scalar() or 0
    if faculty_restrict:
        fid_students = [s.id for s in User.query.filter(User.role == 'student', User.group_id.in_(
            [g.id for g in Group.query.filter_by(faculty_id=faculty_restrict).all()]
        )).all()]
        total_contract = db.session.query(func.sum(StudentPayment.contract_amount)).filter(
            StudentPayment.student_id.in_(fid_students)).scalar() or 0
        total_paid = db.session.query(func.sum(StudentPayment.paid_amount)).filter(
            StudentPayment.student_id.in_(fid_students)).scalar() or 0

    payment_stats_by_course = defaultdict(lambda: {'0%': 0, '25%': 0, '50%': 0, '75%': 0, '100%': 0, 'total': 0})
    all_payments_for_stats = StudentPayment.query.all()
    payments_by_sid = defaultdict(list)
    for x in all_payments_for_stats:
        payments_by_sid[x.student_id].append(x)
    seen_students = set()
    for p in StudentPayment.query.join(User).join(Group).all():
        if not p.student or not p.student.group or (faculty_restrict and p.student.group.faculty_id != faculty_restrict):
            continue
        sid = p.student_id
        if sid in seen_students:
            continue
        seen_students.add(sid)
        cy = p.student.group.course_year
        sp = payments_by_sid.get(sid, [])
        contract = _get_effective_contract_for_student(p.student, sp)
        if contract == 0:
            contract = sum(float(x.contract_amount or 0) for x in sp)
        paid = sum(float(x.paid_amount or 0) for x in sp)
        pc = (paid / contract * 100) if contract > 0 else 0
        if pc == 0 or pc <= 25:
            payment_stats_by_course[cy]['0%'] += 1
        elif pc <= 50:
            payment_stats_by_course[cy]['25%'] += 1
        elif pc <= 75:
            payment_stats_by_course[cy]['50%'] += 1
        elif pc < 100:
            payment_stats_by_course[cy]['75%'] += 1
        else:
            payment_stats_by_course[cy]['100%'] += 1
        payment_stats_by_course[cy]['total'] += 1
    payment_stats_by_course = dict(sorted(payment_stats_by_course.items()))

    has_student = exists().where(User.group_id == Group.id, User.role == 'student')
    faculties = Faculty.query.all()
    faculties = sorted(faculties, key=lambda f: (f.name or '').lower())
    direction_ids_ws = set(g.direction_id for g in Group.query.filter(has_student).all() if g.direction_id)
    directions = Direction.query.filter(Direction.id.in_(direction_ids_ws)).all() if direction_ids_ws else []
    directions = sorted(directions, key=lambda d: ((d.code or '').lower(), (d.name or '').lower()))
    groups_ws = Group.query.filter(has_student).order_by(Group.name).all()
    unique_gn = {}
    for g in groups_ws:
        if g.name not in unique_gn:
            unique_gn[g.name] = g
    groups = sorted(unique_gn.values(), key=lambda g: (g.name or '').lower())
    courses = sorted(set(g.course_year for g in Group.query.all() if g.course_year))
    semesters = sorted(set(g.semester for g in Group.query.all() if g.semester))
    education_types = sorted(set(g.education_type for g in Group.query.all() if g.education_type))

    if faculty_restrict:
        groups = [g for g in groups if g.faculty_id == faculty_restrict]
        directions = [d for d in directions if any(g.faculty_id == faculty_restrict and g.direction_id == d.id for g in Group.query.filter_by(faculty_id=faculty_restrict).all())]
        courses = sorted(set(g.course_year for g in Group.query.filter_by(faculty_id=faculty_restrict).all() if g.course_year))
        semesters = sorted(set(g.semester for g in Group.query.filter_by(faculty_id=faculty_restrict).all() if g.semester))
        education_types = sorted(set(g.education_type for g in Group.query.filter_by(faculty_id=faculty_restrict).all() if g.education_type))

    return render_template('accounting/index.html',
        students=students, payment_map=payment_map,
        groups=groups, faculties=faculties, directions=directions,
        courses=courses, semesters=semesters, education_types=education_types,
        current_group=group_id, current_faculty=faculty_id,
        current_course=course_year, current_semester=semester,
        current_education_type=education_type, current_direction=direction_id,
        search=search,
        total_contract=float(total_contract), total_paid=float(total_paid),
        payment_stats_by_course=payment_stats_by_course,
        faculty=faculty if faculty_restrict else None, now_dt=now_dt, is_admin=is_admin)


@bp.route('/')
@login_required
def index():
    """Buxgalteriya asosiy sahifasi"""
    # Talaba faqat o'z ma'lumotlarini ko'radi
    if current_user.role == 'student':
        return redirect(url_for('accounting.student_payments', student_id=current_user.id))
    
    # Buxgalteriya, dekan va admin uchun
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '')
    group_id = request.args.get('group', type=int)
    faculty_id = request.args.get('faculty', type=int)
    course_year = request.args.get('course', type=int)
    semester = request.args.get('semester', type=int)
    education_type = request.args.get('education_type', '') or None
    direction_id = request.args.get('direction', type=int)
    
    if current_user.role == 'dean':
        faculty = Faculty.query.get(current_user.faculty_id)
        if not faculty:
            flash(t('faculty_not_assigned'), 'error')
            return redirect(url_for('main.dashboard'))
        return _accounting_index_all_students(
            page=page, search=search, group_id=group_id, faculty_id=faculty_id,
            course_year=course_year, semester=semester, education_type=education_type,
            direction_id=direction_id, faculty_restrict=current_user.faculty_id,
            now_dt=datetime.now(), faculty=faculty)
    
    elif current_user.role == 'accounting':
        return _accounting_index_all_students(
            page=page, search=search, group_id=group_id, faculty_id=faculty_id,
            course_year=course_year, semester=semester, education_type=education_type,
            direction_id=direction_id, faculty_restrict=None, faculty=None, now_dt=datetime.now())
    
    elif current_user.role == 'admin':
        return _accounting_index_all_students(
            page=page, search=search, group_id=group_id, faculty_id=faculty_id,
            course_year=course_year, semester=semester, education_type=education_type,
            direction_id=direction_id, faculty_restrict=None, faculty=None, now_dt=datetime.now(), is_admin=True)
    
    else:
        # Boshqa rollar uchun ruxsat yo'q
        flash(t('no_access_permission'), 'error')
        return redirect(url_for('main.dashboard'))


@bp.route('/import', methods=['GET', 'POST'])
@login_required
@accounting_required
def import_payments():
    """Excel fayldan to'lov ma'lumotlarini import qilish"""
    if request.method == 'POST':
        if 'excel_file' not in request.files:
            flash(t('file_not_selected'), 'error')
            return redirect(url_for('accounting.import_payments'))
        
        file = request.files['excel_file']
        if file.filename == '':
            flash(t('file_not_selected'), 'error')
            return redirect(url_for('accounting.import_payments'))
        
        if not file.filename.endswith(('.xlsx', '.xls')):
            flash(t('only_excel_files_allowed'), 'error')
            return redirect(url_for('accounting.import_payments'))
        
        try:
            from app.utils.excel_import import import_payments_from_excel
            
            result = import_payments_from_excel(file)
            
            if result['success']:
                if result['imported'] > 0:
                    flash(t('records_imported', imported_count=result['imported']), 'success')
                else:
                    flash(t('no_records_imported'), 'warning')
                
                if result['errors']:
                    errors_list = "; ".join(result['errors'][:5])
                    if len(result['errors']) > 5:
                        errors_list += f" va yana {len(result['errors']) - 5} ta xato"
                    flash(t('import_error_with_details', errors=errors_list), 'warning')
            else:
                flash(t('import_error', error=result['errors'][0] if result['errors'] else 'Noma`lum xatolik'), 'error')
                
        except ImportError as e:
            flash(t('excel_import_not_working', error=str(e)), 'error')
        except Exception as e:
            flash(t('import_error', error=str(e)), 'error')
        
        return redirect(url_for('accounting.index'))
    
    return render_template('accounting/import_payments.html')


@bp.route('/import/sample')
@login_required
@accounting_required
def download_sample_contracts():
    """Kontrakt import uchun namuna Excel fayl yuklab olish (tanlangan til bo'yicha fayl nomi)"""
    try:
        from app.utils.excel_export import create_sample_contracts_excel
    except ImportError:
        flash(t('openpyxl_not_installed'), 'error')
        return redirect(url_for('accounting.import_payments'))
    lang = session.get('language', 'uz')
    excel_file = create_sample_contracts_excel(lang=lang)
    filename = t('sample_filename_contracts') + f"_{datetime.now().strftime('%Y%m%d')}.xlsx"
    return Response(
        excel_file,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )


# ==================== TO'LOV SUMMALARI (Yo'nalish bo'yicha kontrakt) ====================
@bp.route('/contract-amounts')
@login_required
def contract_amounts():
    """To'lov summasi bo'limi - yo'nalish va o'quv yili bo'yicha kontrakt summalari"""
    if current_user.role not in ('admin', 'accounting', 'dean'):
        flash(t('no_access_permission'), 'error')
        return redirect(url_for('main.dashboard'))
    faculty_restrict = current_user.faculty_id if current_user.role == 'dean' else None
    enrollment_year = request.args.get('enrollment_year', type=int)
    faculty_id = request.args.get('faculty_id', type=int)
    direction_id = request.args.get('direction_id', type=int)
    education_type = (request.args.get('education_type') or '').strip() or None
    search = (request.args.get('search') or '').strip()

    query = DirectionContractAmount.query.join(Direction)
    if faculty_restrict:
        query = query.filter(Direction.faculty_id == faculty_restrict)
    if faculty_id:
        query = query.filter(Direction.faculty_id == faculty_id)
    if direction_id:
        query = query.filter(DirectionContractAmount.direction_id == direction_id)
    if education_type:
        query = query.filter(DirectionContractAmount.education_type == education_type)
    if enrollment_year:
        query = query.filter(DirectionContractAmount.enrollment_year == enrollment_year)
    if search:
        query = query.filter(or_(
            Direction.name.ilike(f'%{search}%'),
            Direction.code.ilike(f'%{search}%')
        ))
    query = query.join(Faculty, Direction.faculty_id == Faculty.id)
    items = query.order_by(Faculty.name, Direction.name, DirectionContractAmount.education_type, DirectionContractAmount.enrollment_year).all()

    faculties = Faculty.query.order_by(Faculty.name).all()
    if faculty_restrict:
        faculties = [f for f in faculties if f.id == faculty_restrict]
    directions = Direction.query.order_by(Direction.name).all()
    if faculty_restrict:
        directions = [d for d in directions if d.faculty_id == faculty_restrict]
    elif faculty_id:
        directions = [d for d in directions if d.faculty_id == faculty_id]
    # O'quv yillari faqat qo'shilgan kontrakt summalaridan, kichikdan kattaga
    enrollment_years = sorted(set(r.enrollment_year for r in DirectionContractAmount.query.all()))
    et_from_groups = {g.education_type for g in Group.query.filter(Group.education_type.isnot(None)).all() if g.education_type}
    et_from_contracts = {r.education_type for r in DirectionContractAmount.query.filter(DirectionContractAmount.education_type.isnot(None)).all() if r.education_type}
    education_types = sorted(et_from_groups | et_from_contracts)

    return render_template('accounting/contract_amounts.html',
        items=items, faculties=faculties, directions=directions, enrollment_years=enrollment_years, education_types=education_types,
        current_faculty=faculty_id, current_direction=direction_id, current_year=enrollment_year, current_education_type=education_type,
        search=search, faculty_restrict=faculty_restrict)


def _enrollment_year_options():
    """O'quv yili variantlari: hozirgi yil asosida, keng oralik (30 yil keyin), kichikdan kattaga tartib"""
    from datetime import datetime
    now = datetime.now().year
    existing = set(r.enrollment_year for r in DirectionContractAmount.query.all())
    base_years = list(range(now - 20, now + 31))  # 20 yil oldin, 30 yil keyin
    combined = sorted(existing | set(base_years))
    return combined


@bp.route('/contract-amounts/create', methods=['GET', 'POST'])
@login_required
def create_contract_amount():
    """Yangi o'quv yili uchun kontrakt summa kiritish"""
    if current_user.role not in ('admin', 'accounting', 'dean'):
        flash(t('no_access_permission'), 'error')
        return redirect(url_for('main.dashboard'))
    faculty_restrict = current_user.faculty_id if current_user.role == 'dean' else None
    faculties = Faculty.query.order_by(Faculty.name).all()
    if faculty_restrict:
        faculties = [f for f in faculties if f.id == faculty_restrict]
    faculty_id = request.args.get('faculty_id', type=int) or (request.form.get('faculty_id', type=int) if request.method == 'POST' else None)
    directions = Direction.query.order_by(Direction.name).all()
    if faculty_restrict:
        directions = [d for d in directions if d.faculty_id == faculty_restrict]
    elif faculty_id:
        directions = [d for d in directions if d.faculty_id == faculty_id]
    enrollment_years = _enrollment_year_options()
    et_from_groups = {g.education_type for g in Group.query.filter(Group.education_type.isnot(None)).all() if g.education_type}
    et_standard = {'kunduzgi', 'sirtqi', 'kechki', 'masofaviy'}
    education_types = sorted(et_from_groups | et_standard)

    if request.method == 'POST':
        from datetime import datetime as dt
        direction_id = request.form.get('direction_id', type=int)
        enrollment_year = request.form.get('enrollment_year', type=int)
        education_type = (request.form.get('education_type') or '').strip() or None
        contract_amount = request.form.get('contract_amount', type=float)
        period_start_str = request.form.get('period_start', '').strip()
        period_end_str = request.form.get('period_end', '').strip()
        period_start = None
        period_end = None
        if period_start_str:
            try:
                period_start = dt.strptime(period_start_str, '%Y-%m-%d').date()
            except ValueError:
                pass
        if period_end_str:
            try:
                period_end = dt.strptime(period_end_str, '%Y-%m-%d').date()
            except ValueError:
                pass
        if not direction_id or not enrollment_year or not education_type or contract_amount is None or contract_amount < 0:
            flash(t('fill_required_fields'), 'error')
            return render_template('accounting/create_contract_amount.html',
                faculties=faculties, directions=directions, enrollment_years=enrollment_years, education_types=education_types,
                faculty_restrict=faculty_restrict, selected_faculty=faculty_id, current_year_base=dt.now().year)
        if not period_start or not period_end:
            flash(t('period_dates_required'), 'error')
            return render_template('accounting/create_contract_amount.html',
                faculties=faculties, directions=directions, enrollment_years=enrollment_years, education_types=education_types,
                faculty_restrict=faculty_restrict, selected_faculty=faculty_id, current_year_base=dt.now().year)
        if period_start >= period_end:
            flash(t('period_end_must_be_after_start'), 'error')
            return render_template('accounting/create_contract_amount.html',
                faculties=faculties, directions=directions, enrollment_years=enrollment_years, education_types=education_types,
                faculty_restrict=faculty_restrict, selected_faculty=faculty_id, current_year_base=dt.now().year)
        direction = Direction.query.get(direction_id)
        if not direction or (faculty_restrict and direction.faculty_id != faculty_restrict):
            flash(t('no_access_permission'), 'error')
            return redirect(url_for('accounting.contract_amounts'))
        rec = DirectionContractAmount(
            direction_id=direction_id, enrollment_year=enrollment_year,
            education_type=education_type, contract_amount=contract_amount,
            period_start=period_start, period_end=period_end
        )
        db.session.add(rec)
        db.session.commit()
        flash(t('contract_amount_created'), 'success')
        return redirect(url_for('accounting.contract_amounts'))

    from datetime import datetime
    current_year_base = datetime.now().year
    return render_template('accounting/create_contract_amount.html',
        faculties=faculties, directions=directions, enrollment_years=enrollment_years, education_types=education_types,
        faculty_restrict=faculty_restrict, selected_faculty=faculty_id, current_year_base=current_year_base)


@bp.route('/contract-amounts/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit_contract_amount(id):
    """Kontrakt summani tahrirlash"""
    if current_user.role not in ('admin', 'accounting', 'dean'):
        flash(t('no_access_permission'), 'error')
        return redirect(url_for('main.dashboard'))
    rec = DirectionContractAmount.query.get_or_404(id)
    faculty_restrict = current_user.faculty_id if current_user.role == 'dean' else None
    if faculty_restrict and rec.direction.faculty_id != faculty_restrict:
        flash(t('no_access_permission'), 'error')
        return redirect(url_for('accounting.contract_amounts'))

    if request.method == 'POST':
        from datetime import datetime as dt
        direction_id = request.form.get('direction_id', type=int)
        enrollment_year = request.form.get('enrollment_year', type=int)
        education_type = (request.form.get('education_type') or '').strip() or None
        contract_amount = request.form.get('contract_amount', type=float)
        period_start_str = request.form.get('period_start', '').strip()
        period_end_str = request.form.get('period_end', '').strip()
        period_start = None
        period_end = None
        if period_start_str:
            try:
                period_start = dt.strptime(period_start_str, '%Y-%m-%d').date()
            except ValueError:
                pass
        if period_end_str:
            try:
                period_end = dt.strptime(period_end_str, '%Y-%m-%d').date()
            except ValueError:
                pass
        if not direction_id or not enrollment_year or not education_type:
            flash(t('fill_required_fields'), 'error')
        elif contract_amount is None or contract_amount < 0:
            flash(t('fill_required_fields'), 'error')
        elif not period_start or not period_end:
            flash(t('period_dates_required'), 'error')
        elif period_start >= period_end:
            flash(t('period_end_must_be_after_start'), 'error')
        else:
            direction = Direction.query.get(direction_id)
            if not direction or (faculty_restrict and direction.faculty_id != faculty_restrict):
                flash(t('no_access_permission'), 'error')
            else:
                rec.direction_id = direction_id
                rec.enrollment_year = enrollment_year
                rec.education_type = education_type
                rec.contract_amount = contract_amount
                rec.period_start = period_start
                rec.period_end = period_end
                db.session.commit()
                flash(t('contract_amount_updated'), 'success')
                return redirect(url_for('accounting.contract_amounts'))

    faculties = Faculty.query.order_by(Faculty.name).all()
    if faculty_restrict:
        faculties = [f for f in faculties if f.id == faculty_restrict]
    directions = Direction.query.order_by(Direction.name).all()
    if faculty_restrict:
        directions = [d for d in directions if d.faculty_id == faculty_restrict]
    # Admin uchun barcha yo'nalishlar (JS faculty bo'yicha filtrlash uchun)
    enrollment_years = _enrollment_year_options()
    et_from_groups = {g.education_type for g in Group.query.filter(Group.education_type.isnot(None)).all() if g.education_type}
    et_standard = {'kunduzgi', 'sirtqi', 'kechki', 'masofaviy'}
    education_types = sorted(et_from_groups | et_standard)
    selected_faculty = rec.direction.faculty_id if rec.direction else None
    from datetime import datetime
    current_year_base = datetime.now().year

    return render_template('accounting/edit_contract_amount.html',
        rec=rec, faculty_restrict=faculty_restrict,
        faculties=faculties, directions=directions, enrollment_years=enrollment_years,
        education_types=education_types, selected_faculty=selected_faculty, current_year_base=current_year_base)


@bp.route('/contract-amounts/<int:id>/delete', methods=['POST'])
@login_required
def delete_contract_amount(id):
    """Kontrakt summani o'chirish"""
    if current_user.role not in ('admin', 'accounting', 'dean'):
        flash(t('no_access_permission'), 'error')
        return redirect(url_for('main.dashboard'))
    rec = DirectionContractAmount.query.get_or_404(id)
    faculty_restrict = current_user.faculty_id if current_user.role == 'dean' else None
    if faculty_restrict and rec.direction.faculty_id != faculty_restrict:
        flash(t('no_access_permission'), 'error')
        return redirect(url_for('accounting.contract_amounts'))
    db.session.delete(rec)
    db.session.commit()
    flash(t('contract_amount_deleted'), 'success')
    return redirect(url_for('accounting.contract_amounts'))


@bp.route('/contract-amounts/export')
@login_required
def export_contract_amounts():
    """To'lov summasi (yo'nalish bo'yicha kontrakt) Excel export"""
    if current_user.role not in ('admin', 'accounting', 'dean'):
        flash(t('no_access_permission'), 'error')
        return redirect(url_for('main.dashboard'))
    faculty_restrict = current_user.faculty_id if current_user.role == 'dean' else None
    faculty_id = request.args.get('faculty_id', type=int)
    direction_id = request.args.get('direction_id', type=int)
    education_type = (request.args.get('education_type') or '').strip() or None
    enrollment_year = request.args.get('enrollment_year', type=int)
    query = DirectionContractAmount.query.join(Direction).join(Faculty, Direction.faculty_id == Faculty.id)
    if faculty_restrict:
        query = query.filter(Direction.faculty_id == faculty_restrict)
    if faculty_id:
        query = query.filter(Direction.faculty_id == faculty_id)
    if direction_id:
        query = query.filter(DirectionContractAmount.direction_id == direction_id)
    if education_type:
        query = query.filter(DirectionContractAmount.education_type == education_type)
    if enrollment_year:
        query = query.filter(DirectionContractAmount.enrollment_year == enrollment_year)
    items = query.order_by(Faculty.name, Direction.name, DirectionContractAmount.education_type, DirectionContractAmount.enrollment_year).all()
    try:
        from app.utils.excel_export import create_contract_amounts_excel
        excel_file = create_contract_amounts_excel(items)
        fn = f"tolov_summasi_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
        return Response(excel_file, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                       headers={'Content-Disposition': f'attachment; filename={fn}'})
    except ImportError:
        flash(t('openpyxl_not_installed'), 'error')
    except Exception as e:
        flash(t('export_error', error=str(e)), 'error')
    return redirect(url_for('accounting.contract_amounts'))


@bp.route('/contract-amounts/import', methods=['GET', 'POST'])
@login_required
def import_contract_amounts():
    """To'lov summasi (yo'nalish bo'yicha kontrakt) Excel import"""
    if current_user.role not in ('admin', 'accounting', 'dean'):
        flash(t('no_access_permission'), 'error')
        return redirect(url_for('main.dashboard'))
    if request.method == 'POST':
        if 'excel_file' not in request.files:
            flash(t('file_not_selected'), 'error')
            return redirect(url_for('accounting.import_contract_amounts'))
        file = request.files['excel_file']
        if file.filename == '':
            flash(t('file_not_selected'), 'error')
            return redirect(url_for('accounting.import_contract_amounts'))
        if not file.filename.endswith(('.xlsx', '.xls')):
            flash(t('only_excel_files_allowed'), 'error')
            return redirect(url_for('accounting.import_contract_amounts'))
        try:
            from app.utils.excel_import import import_contract_amounts_from_excel
            result = import_contract_amounts_from_excel(file, faculty_restrict=current_user.faculty_id if current_user.role == 'dean' else None)
            if result['success']:
                if result['imported'] > 0:
                    flash(t('records_imported', imported_count=result['imported']), 'success')
                else:
                    flash(t('no_records_imported'), 'warning')
                if result.get('errors'):
                    err_preview = "; ".join(result['errors'][:5])
                    if len(result['errors']) > 5:
                        err_preview += f" va yana {len(result['errors']) - 5} ta"
                    flash(t('import_error_with_details', errors=err_preview), 'warning')
            else:
                flash(t('import_error', error=result['errors'][0] if result['errors'] else 'Noma\'lum xatolik'), 'error')
        except ImportError as e:
            flash(t('excel_import_not_working', error=str(e)), 'error')
        except Exception as e:
            flash(t('import_error', error=str(e)), 'error')
        return redirect(url_for('accounting.contract_amounts'))
    return render_template('accounting/import_contract_amounts.html')


@bp.route('/contract-amounts/import/sample')
@login_required
def download_sample_contract_amounts():
    """To'lov summasi import uchun namuna Excel"""
    if current_user.role not in ('admin', 'accounting', 'dean'):
        flash(t('no_access_permission'), 'error')
        return redirect(url_for('accounting.contract_amounts'))
    try:
        from app.utils.excel_export import create_sample_contract_amounts_excel
        lang = session.get('language', 'uz')
        excel_file = create_sample_contract_amounts_excel(lang=lang)
        fn = f"tolov_summasi_namuna_{datetime.now().strftime('%Y%m%d')}.xlsx"
        return Response(excel_file, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                       headers={'Content-Disposition': f'attachment; filename={fn}'})
    except ImportError:
        flash(t('openpyxl_not_installed'), 'error')
    except Exception as e:
        flash(t('import_error', error=str(e)), 'error')
    return redirect(url_for('accounting.import_contract_amounts'))


@bp.route('/student/<int:student_id>')
@login_required
def student_payments(student_id):
    """Talaba to'lov ma'lumotlari"""
    student = User.query.get_or_404(student_id)
    
    # Ruxsat tekshiruvi
    if current_user.role == 'student' and current_user.id != student_id:
        flash(t('no_access_permission'), 'error')
        return redirect(url_for('main.dashboard'))
    
    if current_user.role == 'dean':
        if not student.group or student.group.faculty_id != current_user.faculty_id:
            flash(t('no_access_permission'), 'error')
            return redirect(url_for('main.dashboard'))
    
    # Admin va accounting barcha ma'lumotlarni ko'radi
    
    payments = StudentPayment.query.filter_by(student_id=student_id).order_by(StudentPayment.created_at.desc()).all()
    
    # Kontrakt: DirectionContractAmount dan (yo'nalish, qabul yili, ta'lim shakli bo'yicha), paid: StudentPayment
    total_contract = DirectionContractAmount.get_contract_for_student(student)
    if total_contract == 0:
        total_contract = sum(float(p.contract_amount) for p in payments)
    total_paid = sum(float(p.paid_amount) for p in payments)
    total_remaining = total_contract - total_paid
    percentage = (total_paid / total_contract * 100) if total_contract > 0 else 0
    overpayment = max(0, total_paid - total_contract) if total_contract > 0 else 0
    
    # Maxsus o'quv yili bo'lsa: shu yil va undan oldingilari uchun yo'nalishdan olmaymiz, faqat maxsus
    # Keyingi o'quv yillardan boshlab odatdagidek yo'nalishdan olamiz
    custom_dict = {}  # academic_year -> {amount, payment_id, period_start, period_end}
    for p in payments:
        if p.contract_amount and float(p.contract_amount) > 0 and p.academic_year:
            ay = (p.academic_year or '').strip()
            if not ay:
                continue
            ps, pe = getattr(p, 'period_start', None), getattr(p, 'period_end', None)
            entry = {
                'amount': float(p.contract_amount),
                'payment_id': p.id,
                'period_start': ps,
                'period_end': pe
            }
            if ay not in custom_dict:
                custom_dict[ay] = entry
            elif (ps and pe) and (not custom_dict[ay].get('period_start') or not custom_dict[ay].get('period_end')):
                custom_dict[ay] = entry
    latest_custom_year = max(custom_dict.keys()) if custom_dict else None

    contract_by_year = []
    if student.group and student.group.direction_id:
        g = student.group
        grp_et = (g.education_type or '').strip() or None
        base_year = g.enrollment_year or 0
        dca_list = DirectionContractAmount.query.filter(
            DirectionContractAmount.direction_id == g.direction_id,
            DirectionContractAmount.enrollment_year >= base_year
        ).all()
        for a in dca_list:
            a_et = (a.education_type or '').strip() or None
            if a_et is None or a_et == grp_et:
                ay_key = f"{a.enrollment_year}-{a.enrollment_year + 1}"
                if latest_custom_year and ay_key <= latest_custom_year:
                    continue  # maxsus yil va oldingilari uchun yo'nalishdan olmaymiz
                period_display = '—'
                if a.period_start and a.period_end:
                    period_display = f"{a.period_start.strftime('%d.%m.%Y')} – {a.period_end.strftime('%d.%m.%Y')}"
                elif a.period_start:
                    period_display = a.period_start.strftime('%d.%m.%Y') + ' – …'
                elif a.period_end:
                    period_display = '… – ' + a.period_end.strftime('%d.%m.%Y')
                contract_by_year.append({
                    'academic_year': ay_key,
                    'amount': float(a.contract_amount),
                    'is_custom': False,
                    'period_display': period_display,
                    'paid_amount': 0
                })
    for ay in sorted(custom_dict.keys()):
        info = custom_dict[ay]
        pid = info.get('payment_id')
        ps, pe = info.get('period_start'), info.get('period_end')
        if pid and (not ps or not pe):
            pm = StudentPayment.query.get(pid)
            if pm:
                ps = ps or pm.period_start
                pe = pe or pm.period_end
        if not ps or not pe:
            try:
                parts = ay.replace(' ', '').split('-')
                if len(parts) >= 2:
                    y1 = int(parts[0])
                    y2 = int(parts[1]) if len(parts[1]) == 4 else y1 + 1
                    ps = ps or date(y1, 9, 1)
                    pe = pe or date(y2, 6, 30)
            except (ValueError, IndexError):
                pass
        period_display = '—'
        if ps and pe:
            period_display = f"{ps.strftime('%d.%m.%Y')} – {pe.strftime('%d.%m.%Y')}"
        elif ps:
            period_display = ps.strftime('%d.%m.%Y') + ' – …'
        elif pe:
            period_display = '… – ' + pe.strftime('%d.%m.%Y')
        contract_by_year.append({
            'academic_year': ay,
            'amount': info['amount'],
            'is_custom': True,
            'period_display': period_display,
            'period_start': ps,
            'period_end': pe,
            'paid_amount': 0,
            'payment_id': info['payment_id']
        })
    contract_by_year.sort(key=lambda x: x['academic_year'])

    # Kontrakt jadvali bo'yicha umumiy kontrakt va qolgan summani qayta hisoblash
    if contract_by_year:
        total_contract = sum(float(row['amount']) for row in contract_by_year)
        total_remaining = total_contract - total_paid
        percentage = (total_paid / total_contract * 100) if total_contract > 0 else 0
        overpayment = max(0, total_paid - total_contract) if total_contract > 0 else 0

    # To'lovlarni qatorlar bo'yicha ketma-ket taqsimlash (payments created_at tartibida)
    # Har bir qator to'lguncha, ortiqcha keyingi qatorga o'tadi
    remaining_per_row = [float(row['amount']) for row in contract_by_year]
    payments_sorted = sorted(payments, key=lambda p: (p.created_at or p.updated_at or datetime.min))
    row_idx = 0
    for p in payments_sorted:
        amt = float(p.paid_amount or 0)
        if amt <= 0:
            continue
        while amt > 0 and row_idx < len(contract_by_year):
            need = remaining_per_row[row_idx]
            if need <= 0:
                row_idx += 1
                continue
            take = min(amt, need)
            contract_by_year[row_idx]['paid_amount'] = contract_by_year[row_idx].get('paid_amount', 0) + take
            remaining_per_row[row_idx] = need - take
            amt -= take
            if remaining_per_row[row_idx] <= 0:
                row_idx += 1
    
    # Joriy o'quv yili (Toshkent vaqti bo'yicha: sentabr–iyun)
    from app.utils.date_utils import get_tashkent_time
    now_tz = get_tashkent_time()
    if now_tz.month >= 9:
        current_ay = f"{now_tz.year}-{now_tz.year + 1}"
    else:
        current_ay = f"{now_tz.year - 1}-{now_tz.year}"
    current_year_row = next((r for r in contract_by_year if r.get('academic_year') == current_ay), None)
    current_year_contract = float(current_year_row['amount']) if current_year_row else 0
    current_year_paid = float(current_year_row.get('paid_amount', 0)) if current_year_row else 0
    current_year_remaining = current_year_contract - current_year_paid if current_year_row else 0

    payments_history = [p for p in payments if float(p.paid_amount or 0) > 0 or not (p.contract_amount and float(p.contract_amount) > 0 and (p.academic_year or '').strip())]
    return render_template('accounting/student_payments.html', 
                         payments=payments_history, 
                         student=student,
                         total_contract=total_contract,
                         total_paid=total_paid,
                         total_remaining=total_remaining,
                         percentage=percentage,
                         overpayment=overpayment,
                         contract_by_year=contract_by_year,
                         current_academic_year=current_ay,
                         current_year_contract=current_year_contract,
                         current_year_paid=current_year_paid,
                         current_year_remaining=current_year_remaining)


@bp.route('/export/contracts')
@login_required
def export_contracts():
    """Kontrakt ma'lumotlarini Excel formatida yuklab olish (kurs bo'yicha)"""
    try:
        from app.utils.excel_export import create_contracts_excel
    except ImportError:
        flash(t('openpyxl_not_installed'), 'error')
        return redirect(url_for('accounting.index'))
    
    course_year = request.args.get('course', type=int)
    group_id = request.args.get('group', type=int)
    faculty_id = request.args.get('faculty', type=int)
    
    query = StudentPayment.query.join(User).join(Group)
    
    # Foydalanuvchi roliga qarab filtrlash
    if current_user.role == 'dean':
        faculty = Faculty.query.get(current_user.faculty_id)
        if not faculty:
            flash(t('faculty_not_assigned'), 'error')
            return redirect(url_for('main.dashboard'))
        
        faculty_group_ids = [g.id for g in faculty.groups.all()]
        student_ids = [s.id for s in User.query.filter(
            User.role == 'student',
            User.group_id.in_(faculty_group_ids)
        ).all()]
        query = query.filter(StudentPayment.student_id.in_(student_ids))
    
    if group_id:
        group_student_ids = [s.id for s in User.query.filter_by(role='student', group_id=group_id).all()]
        query = query.filter(StudentPayment.student_id.in_(group_student_ids))
    
    if faculty_id:
        faculty = Faculty.query.get(faculty_id)
        if faculty:
            faculty_group_ids = [g.id for g in faculty.groups.all()]
            faculty_student_ids = [s.id for s in User.query.filter(
                User.role == 'student',
                User.group_id.in_(faculty_group_ids)
            ).all()]
            query = query.filter(StudentPayment.student_id.in_(faculty_student_ids))
    
    if course_year:
        query = query.filter(Group.course_year == course_year)
    
    payments = query.all()
    
    if not payments:
        flash(t('contract_not_found'), 'warning')
        return redirect(url_for('accounting.index'))
    
    excel_file = create_contracts_excel(payments, course_year)
    
    filename = f"kontraktlar_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    if course_year:
        filename = f"kontraktlar_{course_year}-kurs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    
    return Response(
        excel_file,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )


@bp.route('/student/<int:student_id>/add-custom-contract', methods=['POST'])
@login_required
def add_custom_contract(student_id):
    """Talabaga maxsus kontrakt summasi qo'shish (student_payments sahifasidan modal orqali)"""
    if current_user.role not in ('admin', 'dean', 'accounting') and not current_user.has_role('accounting'):
        flash(t('no_access_permission'), 'error')
        return redirect(url_for('main.dashboard'))
    student = User.query.get_or_404(student_id)
    if student.role != 'student':
        flash(t('no_access_permission'), 'error')
        return redirect(url_for('accounting.index'))
    if current_user.role == 'dean' and student.group and student.group.faculty_id != current_user.faculty_id:
        flash(t('no_access_permission'), 'error')
        return redirect(url_for('accounting.index'))

    from datetime import datetime as dt
    academic_year = (request.form.get('academic_year') or '').strip()
    contract_amount = request.form.get('contract_amount', type=float)
    period_start_str = request.form.get('period_start', '').strip()
    period_end_str = request.form.get('period_end', '').strip()
    if not academic_year:
        flash(t('fill_required_fields'), 'error')
        return redirect(url_for('accounting.student_payments', student_id=student_id))
    if contract_amount is None or contract_amount < 0:
        flash(t('fill_required_fields'), 'error')
        return redirect(url_for('accounting.student_payments', student_id=student_id))
    period_start, period_end = None, None
    if period_start_str:
        try:
            period_start = dt.strptime(period_start_str, '%Y-%m-%d').date()
        except ValueError:
            pass
    if period_end_str:
        try:
            period_end = dt.strptime(period_end_str, '%Y-%m-%d').date()
        except ValueError:
            pass
    if not period_start or not period_end:
        flash(t('period_dates_required'), 'error')
        return redirect(url_for('accounting.student_payments', student_id=student_id))
    if period_start >= period_end:
        flash(t('period_end_must_be_after_start'), 'error')
        return redirect(url_for('accounting.student_payments', student_id=student_id))

    academic_year = _parse_academic_year(academic_year) or academic_year
    payment = StudentPayment(
        student_id=student.id,
        contract_amount=contract_amount,
        paid_amount=0,
        academic_year=academic_year,
        semester=1,
        notes=None,
        period_start=period_start,
        period_end=period_end
    )
    db.session.add(payment)
    db.session.commit()
    flash(t('payment_created_success'), 'success')
    return redirect(url_for('accounting.student_payments', student_id=student_id))


@bp.route('/student/<int:student_id>/edit-custom-contract/<int:payment_id>', methods=['POST'])
@login_required
def edit_custom_contract(student_id, payment_id):
    """Maxsus kontraktni tahrirlash (modal orqali, qo'shish bilan bir xil ko'rinishda)"""
    if current_user.role not in ('admin', 'dean', 'accounting') and not current_user.has_role('accounting'):
        flash(t('no_access_permission'), 'error')
        return redirect(url_for('main.dashboard'))
    student = User.query.get_or_404(student_id)
    payment = StudentPayment.query.get_or_404(payment_id)
    if payment.student_id != student_id or not payment.contract_amount or float(payment.contract_amount) <= 0 or not payment.academic_year:
        flash(t('no_access_permission'), 'error')
        return redirect(url_for('accounting.student_payments', student_id=student_id))
    if current_user.role == 'dean' and student.group and student.group.faculty_id != current_user.faculty_id:
        flash(t('no_access_permission'), 'error')
        return redirect(url_for('accounting.student_payments', student_id=student_id))

    academic_year = (request.form.get('academic_year') or '').strip()
    contract_amount = request.form.get('contract_amount', type=float)
    period_start = _parse_date(request.form.get('period_start', ''))
    period_end = _parse_date(request.form.get('period_end', ''))
    if not academic_year:
        flash(t('fill_required_fields'), 'error')
        return redirect(url_for('accounting.student_payments', student_id=student_id))
    if contract_amount is None or contract_amount < 0:
        flash(t('fill_required_fields'), 'error')
        return redirect(url_for('accounting.student_payments', student_id=student_id))
    if not period_start or not period_end:
        flash(t('period_dates_required'), 'error')
        return redirect(url_for('accounting.student_payments', student_id=student_id))
    if period_start >= period_end:
        flash(t('period_end_must_be_after_start'), 'error')
        return redirect(url_for('accounting.student_payments', student_id=student_id))

    academic_year = _parse_academic_year(academic_year) or academic_year
    payment.academic_year = academic_year
    payment.contract_amount = contract_amount
    payment.period_start = period_start
    payment.period_end = period_end
    db.session.commit()
    flash(t('payment_info_updated'), 'success')
    return redirect(url_for('accounting.student_payments', student_id=student_id))


@bp.route('/payment/create/<int:student_id>', methods=['GET', 'POST'])
@login_required
def create_payment(student_id):
    """Talaba uchun to'lov ma'lumotini qo'lda kiritish (sahifa yoki modal orqali)"""
    if current_user.role not in ('admin', 'dean', 'accounting') and not current_user.has_role('accounting'):
        flash(t('no_access_permission'), 'error')
        return redirect(url_for('main.dashboard'))
    student = User.query.get_or_404(student_id)
    if student.role != 'student':
        flash(t('no_access_permission'), 'error')
        return redirect(url_for('accounting.index'))
    if current_user.role == 'dean' and student.group and student.group.faculty_id != current_user.faculty_id:
        flash(t('no_access_permission'), 'error')
        return redirect(url_for('accounting.index'))
    
    if request.method == 'POST':
        paid_amount = request.form.get('paid_amount', type=float)
        notes = (request.form.get('notes') or '').strip()
        if paid_amount is None or paid_amount < 0:
            flash(t('paid_amount_required'), 'error')
            return redirect(url_for('accounting.student_payments', student_id=student_id))
        payment = StudentPayment(
            student_id=student.id,
            contract_amount=0,
            paid_amount=paid_amount,
            academic_year=None,
            semester=1,
            notes=notes or None
        )
        db.session.add(payment)
        db.session.commit()
        flash(t('payment_created_success'), 'success')
        return redirect(url_for('accounting.student_payments', student_id=student_id))
    return redirect(url_for('accounting.student_payments', student_id=student_id))


@bp.route('/payment/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit_payment(id):
    """To'lov ma'lumotlarini tahrirlash"""
    payment = StudentPayment.query.get_or_404(id)
    student = payment.student
    
    # Ruxsat tekshiruvi
    if current_user.role == 'student':
        flash(t('no_access_permission'), 'error')
        return redirect(url_for('main.dashboard'))
    
    if current_user.role == 'dean':
        if not student.group or student.group.faculty_id != current_user.faculty_id:
            flash(t('no_access_permission'), 'error')
            return redirect(url_for('main.dashboard'))
    
    # Admin va accounting barcha ma'lumotlarni tahrirlashi mumkin
    
    if request.method == 'POST':
        payment.contract_amount = request.form.get('contract_amount', type=float) or 0
        payment.paid_amount = request.form.get('paid_amount', type=float) or 0
        payment.academic_year = (request.form.get('academic_year') or '').strip() or None
        payment.semester = request.form.get('semester', type=int) or 1
        payment.notes = request.form.get('notes', '')
        period_start = _parse_date(request.form.get('period_start', ''))
        period_end = _parse_date(request.form.get('period_end', ''))
        if period_start and period_end and period_start < period_end:
            payment.period_start = period_start
            payment.period_end = period_end

        db.session.commit()
        flash(t('payment_info_updated'), 'success')
        if request.args.get('next') == 'student_payments' or (payment.contract_amount and float(payment.contract_amount) > 0 and payment.academic_year):
            return redirect(url_for('accounting.student_payments', student_id=payment.student_id))
        return redirect(url_for('accounting.index'))
    
    return render_template('accounting/edit_payment.html', payment=payment, student=student)


@bp.route('/payment/<int:id>/delete', methods=['POST'])
@login_required
def delete_payment(id):
    """To'lov yozuvini o'chirish"""
    payment = StudentPayment.query.get_or_404(id)
    student = payment.student
    student_id = student.id

    if current_user.role == 'student':
        flash(t('no_access_permission'), 'error')
        return redirect(url_for('main.dashboard'))

    if current_user.role == 'dean':
        if not student.group or student.group.faculty_id != current_user.faculty_id:
            flash(t('no_access_permission'), 'error')
            return redirect(url_for('main.dashboard'))

    db.session.delete(payment)
    db.session.commit()
    flash(t('payment_deleted'), 'success')
    return redirect(url_for('accounting.student_payments', student_id=student_id))

