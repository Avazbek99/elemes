from flask import Blueprint, render_template, request, redirect, url_for, flash, Response, session
from flask_login import login_required, current_user
from app.models import User, StudentPayment, Group, Faculty
from app import db
from functools import wraps
from datetime import datetime
from sqlalchemy import func
from app.utils.translations import t

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


@bp.route('/')
@login_required
def index():
    """Buxgalteriya asosiy sahifasi"""
    # Talaba faqat o'z ma'lumotlarini ko'radi
    if current_user.role == 'student':
        payments = StudentPayment.query.filter_by(student_id=current_user.id).order_by(StudentPayment.created_at.desc()).all()
        return render_template('accounting/student_payments.html', payments=payments, student=current_user)
    
    # Buxgalteriya, dekan va admin uchun
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '')
    group_id = request.args.get('group', type=int)
    faculty_id = request.args.get('faculty', type=int)
    
    if current_user.role == 'dean':
        # Dekan faqat o'z fakultetidagi talabalarni ko'radi
        faculty = Faculty.query.get(current_user.faculty_id)
        if not faculty:
            flash(t('faculty_not_assigned'), 'error')
            return redirect(url_for('main.dashboard'))
        
        faculty_group_ids = [g.id for g in faculty.groups.all()]
        student_ids = [s.id for s in User.query.filter(
            User.role == 'student',
            User.group_id.in_(faculty_group_ids)
        ).all()]
        
        query = StudentPayment.query.filter(StudentPayment.student_id.in_(student_ids))
        
        if search:
            query = query.join(User).filter(
                (User.full_name.ilike(f'%{search}%')) |
                (User.student_id.ilike(f'%{search}%'))
            )
        
        if group_id:
            group_student_ids = [s.id for s in User.query.filter_by(role='student', group_id=group_id).all()]
            query = query.filter(StudentPayment.student_id.in_(group_student_ids))
        
        payments = query.order_by(StudentPayment.created_at.desc()).paginate(page=page, per_page=20)
        groups = faculty.groups.order_by(Group.name).all()
        
        # Statistika
        total_contract = db.session.query(func.sum(StudentPayment.contract_amount)).filter(
            StudentPayment.student_id.in_(student_ids)
        ).scalar() or 0
        total_paid = db.session.query(func.sum(StudentPayment.paid_amount)).filter(
            StudentPayment.student_id.in_(student_ids)
        ).scalar() or 0
        
        # Kurs bo'yicha to'lov foizi statistikasi
        from collections import defaultdict
        payment_stats_by_course = defaultdict(lambda: {
            '0%': 0, '25%': 0, '50%': 0, '75%': 0, '100%': 0, 'total': 0
        })
        
        # Fakultet talabalari to'lov ma'lumotlari
        faculty_payments = StudentPayment.query.filter(
            StudentPayment.student_id.in_(student_ids)
        ).join(User).join(Group).all()
        
        for payment in faculty_payments:
            if payment.student and payment.student.group:
                course_year = payment.student.group.course_year
                percentage = payment.get_payment_percentage()
                
                # To'lov foiziga qarab guruhlash
                if percentage == 0:
                    payment_stats_by_course[course_year]['0%'] += 1
                elif 0 < percentage <= 25:
                    payment_stats_by_course[course_year]['0%'] += 1
                elif 25 < percentage <= 50:
                    payment_stats_by_course[course_year]['25%'] += 1
                elif 50 < percentage <= 75:
                    payment_stats_by_course[course_year]['50%'] += 1
                elif 75 < percentage < 100:
                    payment_stats_by_course[course_year]['75%'] += 1
                else:  # 100% va yuqori
                    payment_stats_by_course[course_year]['100%'] += 1
                
                payment_stats_by_course[course_year]['total'] += 1
        
        # Kurs bo'yicha tartiblash
        payment_stats_by_course = dict(sorted(payment_stats_by_course.items()))
        
        return render_template('accounting/index.html', 
                             payments=payments, 
                             faculty=faculty,
                             groups=groups,
                             current_group=group_id,
                             search=search,
                             total_contract=float(total_contract),
                             total_paid=float(total_paid),
                             payment_stats_by_course=payment_stats_by_course)
    
    elif current_user.role == 'accounting':
        # Buxgalteriya barcha ma'lumotlarni ko'radi va boshqaradi
        query = StudentPayment.query
        
        if search:
            query = query.join(User).filter(
                (User.full_name.ilike(f'%{search}%')) |
                (User.student_id.ilike(f'%{search}%'))
            )
        
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
        
        payments = query.order_by(StudentPayment.created_at.desc()).paginate(page=page, per_page=20)
        groups = Group.query.order_by(Group.name).all()
        faculties = Faculty.query.all()
        
        # Statistika
        total_contract = db.session.query(func.sum(StudentPayment.contract_amount)).scalar() or 0
        total_paid = db.session.query(func.sum(StudentPayment.paid_amount)).scalar() or 0
        
        # Kurs bo'yicha to'lov foizi statistikasi
        from collections import defaultdict
        payment_stats_by_course = defaultdict(lambda: {
            '0%': 0, '25%': 0, '50%': 0, '75%': 0, '100%': 0, 'total': 0
        })
        
        # Barcha to'lov ma'lumotlarini olish
        all_payments = StudentPayment.query.join(User).join(Group).all()
        
        for payment in all_payments:
            if payment.student and payment.student.group:
                course_year = payment.student.group.course_year
                percentage = payment.get_payment_percentage()
                
                # To'lov foiziga qarab guruhlash
                if percentage == 0:
                    payment_stats_by_course[course_year]['0%'] += 1
                elif 0 < percentage <= 25:
                    payment_stats_by_course[course_year]['0%'] += 1
                elif 25 < percentage <= 50:
                    payment_stats_by_course[course_year]['25%'] += 1
                elif 50 < percentage <= 75:
                    payment_stats_by_course[course_year]['50%'] += 1
                elif 75 < percentage < 100:
                    payment_stats_by_course[course_year]['75%'] += 1
                else:  # 100% va yuqori
                    payment_stats_by_course[course_year]['100%'] += 1
                
                payment_stats_by_course[course_year]['total'] += 1
        
        # Kurs bo'yicha tartiblash
        payment_stats_by_course = dict(sorted(payment_stats_by_course.items()))
        
        return render_template('accounting/index.html', 
                             payments=payments, 
                             groups=groups,
                             faculties=faculties,
                             current_group=group_id,
                             current_faculty=faculty_id,
                             search=search,
                             total_contract=float(total_contract),
                             total_paid=float(total_paid),
                             payment_stats_by_course=payment_stats_by_course,
                             now_dt=datetime.now())
    
    elif current_user.role == 'admin':
        # Admin barcha fakultetlarning to'lov ma'lumotlarini ko'radi
        query = StudentPayment.query
        
        if search:
            query = query.join(User).filter(
                (User.full_name.ilike(f'%{search}%')) |
                (User.student_id.ilike(f'%{search}%'))
            )
        
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
        
        payments = query.order_by(StudentPayment.created_at.desc()).paginate(page=page, per_page=20)
        groups = Group.query.order_by(Group.name).all()
        faculties = Faculty.query.all()
        
        # Statistika
        total_contract = db.session.query(func.sum(StudentPayment.contract_amount)).scalar() or 0
        total_paid = db.session.query(func.sum(StudentPayment.paid_amount)).scalar() or 0
        
        # Kurs bo'yicha to'lov foizi statistikasi
        from collections import defaultdict
        payment_stats_by_course = defaultdict(lambda: {
            '0%': 0, '25%': 0, '50%': 0, '75%': 0, '100%': 0, 'total': 0
        })
        
        # Barcha to'lov ma'lumotlarini olish
        all_payments = StudentPayment.query.join(User).join(Group).all()
        
        for payment in all_payments:
            if payment.student and payment.student.group:
                course_year = payment.student.group.course_year
                percentage = payment.get_payment_percentage()
                
                # To'lov foiziga qarab guruhlash
                if percentage == 0:
                    payment_stats_by_course[course_year]['0%'] += 1
                elif 0 < percentage <= 25:
                    payment_stats_by_course[course_year]['0%'] += 1
                elif 25 < percentage <= 50:
                    payment_stats_by_course[course_year]['25%'] += 1
                elif 50 < percentage <= 75:
                    payment_stats_by_course[course_year]['50%'] += 1
                elif 75 < percentage < 100:
                    payment_stats_by_course[course_year]['75%'] += 1
                else:  # 100% va yuqori
                    payment_stats_by_course[course_year]['100%'] += 1
                
                payment_stats_by_course[course_year]['total'] += 1
        
        # Kurs bo'yicha tartiblash
        payment_stats_by_course = dict(sorted(payment_stats_by_course.items()))
        
        return render_template('accounting/index.html', 
                             payments=payments, 
                             groups=groups,
                             faculties=faculties,
                             current_group=group_id,
                             current_faculty=faculty_id,
                             search=search,
                             total_contract=float(total_contract),
                             total_paid=float(total_paid),
                             payment_stats_by_course=payment_stats_by_course,
                             is_admin=True)
    
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
    """Kontrakt import uchun namuna Excel fayl yuklab olish"""
    try:
        from app.utils.excel_export import create_sample_contracts_excel
    except ImportError:
        flash(t('openpyxl_not_installed'), 'error')
        return redirect(url_for('accounting.import_payments'))
    
    excel_file = create_sample_contracts_excel()
    filename = f"kontrakt_namuna_{datetime.now().strftime('%Y%m%d')}.xlsx"
    
    return Response(
        excel_file,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )


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
    
    # Statistika hisoblash
    total_contract = 0
    total_paid = 0
    if payments:
        total_contract = float(payments[0].contract_amount)
        total_paid = sum(float(p.paid_amount) for p in payments)
    total_remaining = total_contract - total_paid
    percentage = (total_paid / total_contract * 100) if total_contract > 0 else 0
    
    return render_template('accounting/student_payments.html', 
                         payments=payments, 
                         student=student,
                         total_contract=total_contract,
                         total_paid=total_paid,
                         total_remaining=total_remaining,
                         percentage=percentage)


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
        payment.contract_amount = request.form.get('contract_amount', type=float)
        payment.paid_amount = request.form.get('paid_amount', type=float)
        payment.academic_year = request.form.get('academic_year')
        payment.semester = request.form.get('semester', type=int)
        payment.notes = request.form.get('notes', '')
        
        db.session.commit()
        flash(t('payment_info_updated'), 'success')
        return redirect(url_for('accounting.student_payments', student_id=student.id))
    
    return render_template('accounting/edit_payment.html', payment=payment, student=student)

