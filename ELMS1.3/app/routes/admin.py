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


# ==================== ASOSIY SAHIFA ====================
@bp.route('/')
@login_required
@admin_required
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
    recent_users = User.query.order_by(User.created_at.desc()).limit(10).all()
    return render_template('admin/index.html', stats=stats, recent_users=recent_users)


# ==================== FOYDALANUVCHILAR ====================
@bp.route('/users')
@login_required
@admin_required
def users():
    page = request.args.get('page', 1, type=int)
    role = request.args.get('role', '')
    search = request.args.get('search', '')
    
    query = User.query
    
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
def create_user():
    faculties = Faculty.query.all()
    groups = Group.query.all()
    
    if request.method == 'POST':
        email = request.form.get('email')
        full_name = request.form.get('full_name')
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
                flash("Login majburiy maydon (xodimlar uchun)", 'error')
                return render_template('admin/create_user.html', faculties=faculties, groups=groups)
            if User.query.filter_by(login=login).first():
                flash("Bu login allaqachon mavjud", 'error')
                return render_template('admin/create_user.html', faculties=faculties, groups=groups)
        else:
            # Talabalar uchun talaba ID majburiy
            if not student_id:
                flash("Talaba ID majburiy maydon (talabalar uchun)", 'error')
                return render_template('admin/create_user.html', faculties=faculties, groups=groups)
            if User.query.filter_by(student_id=student_id).first():
                flash("Bu talaba ID allaqachon mavjud", 'error')
                return render_template('admin/create_user.html', faculties=faculties, groups=groups)
        
        # Email ixtiyoriy, lekin agar kiritilgan bo'lsa, unikallikni tekshirish
        if email and User.query.filter_by(email=email).first():
            flash("Bu email allaqachon mavjud", 'error')
            return render_template('admin/create_user.html', faculties=faculties, groups=groups)
        
        # Pasport raqami majburiy
        if not passport_number:
            flash("Pasport seriyasi va raqami majburiy", 'error')
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
                flash("Tug'ilgan sana noto'g'ri formatda (yyyy-mm-dd)", 'error')
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
        
        flash(f"{user.get_role_display()} muvaffaqiyatli yaratildi", 'success')
        return redirect(url_for('admin.users'))
    
    return render_template('admin/create_user.html', faculties=faculties, groups=groups)


@bp.route('/users/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_user(id):
    user = User.query.get_or_404(id)
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
                flash("Bu email allaqachon boshqa foydalanuvchida mavjud", 'error')
                return render_template('admin/edit_user.html', user=user, faculties=faculties, groups=groups, existing_roles=existing_roles)
        user.email = email if email else None
        user.full_name = request.form.get('full_name')
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
        flash("Foydalanuvchi muvaffaqiyatli yangilandi", 'success')
        return redirect(url_for('admin.users'))
    
    return render_template('admin/edit_user.html', user=user, faculties=faculties, groups=groups, existing_roles=existing_roles)


@bp.route('/users/<int:id>/toggle', methods=['POST'])
@login_required
@admin_required
def toggle_user(id):
    user = User.query.get_or_404(id)
    
    if user.id == current_user.id:
        flash("O'zingizni bloklashingiz mumkin emas", 'error')
    else:
        user.is_active = not user.is_active
        db.session.commit()
        status = "faollashtirildi" if user.is_active else "bloklandi"
        flash(f"Foydalanuvchi {status}", 'success')
    
    # Qaysi sahifadan kelganini aniqlash
    referer = request.referrer or url_for('admin.users')
    if 'staff' in referer:
        return redirect(url_for('admin.staff'))
    elif 'students' in referer:
        return redirect(url_for('admin.students'))
    return redirect(url_for('admin.users'))


@bp.route('/users/<int:id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_user(id):
    user = User.query.get_or_404(id)
    
    if user.id == current_user.id:
        flash("O'zingizni o'chirishingiz mumkin emas", 'error')
    else:
        db.session.delete(user)
        db.session.commit()
        flash("Foydalanuvchi o'chirildi", 'success')
    
    # Qaysi sahifadan kelganini aniqlash
    referer = request.referrer or url_for('admin.users')
    if 'staff' in referer:
        return redirect(url_for('admin.staff'))
    elif 'students' in referer:
        return redirect(url_for('admin.students'))
    return redirect(url_for('admin.users'))


@bp.route('/users/<int:id>/reset_password', methods=['POST'])
@login_required
@admin_required
def reset_user_password(id):
    """Parolni boshlang'ich holatga qaytarish (pasport raqami yoki default parol)"""
    user = User.query.get_or_404(id)
    
    # Parolni pasport seriya raqamiga qaytarish
    if not user.passport_number:
        flash("Bu foydalanuvchida pasport seriya raqami mavjud emas", 'error')
        referer = request.referrer or url_for('admin.users')
        if 'staff' in referer:
            return redirect(url_for('admin.staff'))
        elif 'students' in referer:
            return redirect(url_for('admin.students'))
        return redirect(url_for('admin.users'))
    
    new_password = user.passport_number
    
    user.set_password(new_password)
    db.session.commit()
    flash(f"{user.full_name} paroli boshlang'ich holatga qaytarildi. Yangi parol: {new_password}", 'success')
    
    # Qaysi sahifadan kelganini aniqlash
    referer = request.referrer or url_for('admin.users')
    if 'staff' in referer:
        return redirect(url_for('admin.staff'))
    elif 'students' in referer:
        return redirect(url_for('admin.students'))
    return redirect(url_for('admin.users'))
# ==================== O'QITUVCHILAR ====================
@bp.route('/teachers')
@login_required
@admin_required
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
def staff():
    """Xodimlar bazasi (talabalar bo'lmagan barcha foydalanuvchilar)"""
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '')
    
    # Talabalar bo'lmagan barcha foydalanuvchilar (UserRole orqali)
    # Avval student roliga ega bo'lmagan user ID'larni topish
    student_user_ids = db.session.query(UserRole.user_id).filter_by(role='student').distinct().all()
    student_user_ids = [uid[0] for uid in student_user_ids]
    
    # Agar UserRole orqali topilmasa, eski usul bilan qidirish
    if not student_user_ids:
        students_by_role = User.query.filter_by(role='student').all()
        student_user_ids = [u.id for u in students_by_role]
    
    # Agar hali ham topilmasa, get_roles() orqali qidirish
    if not student_user_ids:
        all_users = User.query.all()
        student_user_ids = [u.id for u in all_users if 'student' in u.get_roles()]
    
    # Talabalar bo'lmagan foydalanuvchilar
    if student_user_ids:
        query = User.query.filter(~User.id.in_(student_user_ids))
    else:
        # Agar student roliga ega bo'lganlar topilmasa, faqat asosiy role maydoniga qarab qidirish
        query = User.query.filter(User.role != 'student')
    
    if search:
        query = query.filter(
            (User.full_name.ilike(f'%{search}%')) |
            (User.login.ilike(f'%{search}%')) |
            (User.passport_number.ilike(f'%{search}%')) |
            (User.pinfl.ilike(f'%{search}%')) |
            (User.phone.ilike(f'%{search}%')) |
            (User.email.ilike(f'%{search}%'))
        )
    
    users = query.order_by(User.created_at.desc()).paginate(page=page, per_page=50, error_out=False)
    
    return render_template('admin/staff.html', users=users, search=search)


@bp.route('/staff/create', methods=['GET', 'POST'])
@login_required
@admin_required
def create_staff():
    """Yangi xodim yaratish (bir nechta rol bilan)"""
    faculties = Faculty.query.all()
    
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        login = request.form.get('login', '').strip()  # Login (xodimlar uchun majburiy)
        full_name = request.form.get('full_name', '').strip()
        phone = request.form.get('phone', '').strip()
        passport_number = request.form.get('passport_number', '').strip()
        pinfl = request.form.get('pinfl', '').strip()
        birth_date_str = request.form.get('birth_date', '').strip()
        description = request.form.get('description', '').strip()
        
        # Bir nechta rol tanlash
        selected_roles = request.form.getlist('roles')  # ['admin', 'dean', 'teacher']
        
        if not selected_roles:
            flash("Kamida bitta rol tanlanishi kerak", 'error')
            faculties = Faculty.query.all()
            return render_template('admin/create_staff.html', faculties=faculties)
        
        # Login majburiy (xodimlar uchun)
        if not login:
            flash("Login majburiy maydon", 'error')
            faculties = Faculty.query.all()
            return render_template('admin/create_staff.html', faculties=faculties)
        
        # Login unikalligi
        if User.query.filter_by(login=login).first():
            flash("Bu login allaqachon mavjud", 'error')
            faculties = Faculty.query.all()
            return render_template('admin/create_staff.html', faculties=faculties)
        
        # Email ixtiyoriy, lekin agar kiritilgan bo'lsa, unikallikni tekshirish
        if email and User.query.filter_by(email=email).first():
            flash("Bu email allaqachon mavjud", 'error')
            faculties = Faculty.query.all()
            return render_template('admin/create_staff.html', faculties=faculties)
        
        # Pasport raqami parol sifatida ishlatiladi
        if not passport_number:
            flash("Pasport seriyasi va raqami majburiy", 'error')
            faculties = Faculty.query.all()
            return render_template('admin/create_staff.html', faculties=faculties)
        
        # Pasport raqamini katta harfga o'zgartirish
        passport_number = passport_number.upper()
        
        # Tug'ilgan sanani parse qilish (yyyy-mm-dd)
        birth_date = None
        if birth_date_str:
            try:
                birth_date = datetime.strptime(birth_date_str, '%Y-%m-%d').date()
            except ValueError:
                flash("Tug'ilgan sana noto'g'ri formatda (yyyy-mm-dd)", 'error')
                faculties = Faculty.query.all()
                return render_template('admin/create_staff.html', faculties=faculties)
        
        password = passport_number  # Pasport raqami parol
        
        # Asosiy rol (birinchisi yoki eng yuqori darajali)
        main_role = selected_roles[0]
        if 'admin' in selected_roles:
            main_role = 'admin'
        elif 'dean' in selected_roles:
            main_role = 'dean'
        elif 'teacher' in selected_roles:
            main_role = 'teacher'
        
        # Dekan roli tanlangan bo'lsa, fakultetni aniqlash (majburiy)
        faculty_id = None
        if 'dean' in selected_roles:
            faculty_id_str = request.form.get('faculty_id', '').strip()
            if not faculty_id_str:
                flash("Dekan roli tanlangan bo'lsa, fakultet tanlash majburiy", 'error')
                faculties = Faculty.query.all()
                return render_template('admin/create_staff.html', faculties=faculties)
            try:
                faculty_id = int(faculty_id_str)
                # Fakultet mavjudligini tekshirish
                faculty = Faculty.query.get(faculty_id)
                if not faculty:
                    flash("Tanlangan fakultet topilmadi", 'error')
                    faculties = Faculty.query.all()
                    return render_template('admin/create_staff.html', faculties=faculties)
            except (ValueError, TypeError):
                flash("Fakultet noto'g'ri tanlangan", 'error')
                faculties = Faculty.query.all()
                return render_template('admin/create_staff.html', faculties=faculties)
        
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
        
        db.session.commit()
        
        flash(f"Xodim {user.full_name} muvaffaqiyatli yaratildi", 'success')
        return redirect(url_for('admin.staff'))
    
    return render_template('admin/create_staff.html', faculties=faculties)


@bp.route('/staff/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_staff(id):
    """Xodimni tahrirlash (bir nechta rol bilan)"""
    user = User.query.get_or_404(id)
    
    # Faqat xodimlar (talaba emas)
    if user.role == 'student':
        flash("Bu talaba, xodim emas", 'error')
        return redirect(url_for('admin.students'))
    
    # Foydalanuvchining mavjud rollarini olish
    existing_roles = [ur.role for ur in user.roles_list.all()] if user.roles_list.count() > 0 else ([user.role] if user.role else [])
    
    if request.method == 'POST':
        login = request.form.get('login')
        # Login majburiy (xodimlar uchun)
        if not login:
            flash("Login majburiy maydon", 'error')
            faculties = Faculty.query.all()
            return render_template('admin/edit_staff.html', user=user, existing_roles=existing_roles, faculties=faculties)
        
        # Login unikalligi (boshqa foydalanuvchida bo'lmasligi kerak)
        existing_user_with_login = User.query.filter_by(login=login).first()
        if existing_user_with_login and existing_user_with_login.id != user.id:
            flash("Bu login allaqachon boshqa foydalanuvchida mavjud", 'error')
            faculties = Faculty.query.all()
            return render_template('admin/edit_staff.html', user=user, existing_roles=existing_roles, faculties=faculties)
        
        user.login = login
        email = request.form.get('email')
        # Email ixtiyoriy, lekin agar kiritilgan bo'lsa, unikallikni tekshirish
        if email:
            existing_user_with_email = User.query.filter_by(email=email).first()
            if existing_user_with_email and existing_user_with_email.id != user.id:
                flash("Bu email allaqachon boshqa foydalanuvchida mavjud", 'error')
                faculties = Faculty.query.all()
                return render_template('admin/edit_staff.html', user=user, existing_roles=existing_roles, faculties=faculties)
        # Email maydonini tozalash va o'rnatish
        email_value = email.strip() if email and email.strip() else None
        user.email = email_value if email_value else None
        user.full_name = request.form.get('full_name', '').strip()
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
                flash("Tug'ilgan sana noto'g'ri formatda (yyyy-mm-dd)", 'error')
                faculties = Faculty.query.all()
                return render_template('admin/edit_staff.html', user=user, existing_roles=existing_roles, faculties=faculties)
        else:
            user.birth_date = None
        
        user.pinfl = pinfl if pinfl else None
        user.description = description if description else None
        
        # Bir nechta rol tanlash
        selected_roles = request.form.getlist('roles')
        
        if not selected_roles:
            flash("Kamida bitta rol tanlanishi kerak", 'error')
            faculties = Faculty.query.all()
            return render_template('admin/edit_staff.html', user=user, existing_roles=existing_roles, faculties=faculties)
        
        # Asosiy rol (eng yuqori darajali)
        main_role = selected_roles[0]
        if 'admin' in selected_roles:
            main_role = 'admin'
        elif 'dean' in selected_roles:
            main_role = 'dean'
        elif 'teacher' in selected_roles:
            main_role = 'teacher'
        
        user.role = main_role
        
        # Dekan roli tanlangan bo'lsa, fakultetni aniqlash (majburiy)
        if 'dean' in selected_roles:
            faculty_id_str = request.form.get('faculty_id', '').strip()
            if not faculty_id_str:
                flash("Dekan roli tanlangan bo'lsa, fakultet tanlash majburiy", 'error')
                faculties = Faculty.query.all()
                return render_template('admin/edit_staff.html', user=user, existing_roles=existing_roles, faculties=faculties)
            try:
                faculty_id = int(faculty_id_str)
                # Fakultet mavjudligini tekshirish
                faculty = Faculty.query.get(faculty_id)
                if not faculty:
                    flash("Tanlangan fakultet topilmadi", 'error')
                    faculties = Faculty.query.all()
                    return render_template('admin/edit_staff.html', user=user, existing_roles=existing_roles, faculties=faculties)
                user.faculty_id = faculty_id
            except (ValueError, TypeError):
                flash("Fakultet noto'g'ri tanlangan", 'error')
                faculties = Faculty.query.all()
                return render_template('admin/edit_staff.html', user=user, existing_roles=existing_roles, faculties=faculties)
        else:
            user.faculty_id = None
        
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
        
        flash(f"Xodim {user.full_name} ma'lumotlari yangilandi", 'success')
        return redirect(url_for('admin.staff'))
    
    faculties = Faculty.query.all()
    return render_template('admin/edit_staff.html', user=user, existing_roles=existing_roles, faculties=faculties)


# ==================== FAKULTETLAR ====================
@bp.route('/faculties')
@login_required
@admin_required
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
        # Bir nechta rolda dekan bo'lishi mumkin, shuning uchun UserRole orqali qidirish
        # Barcha dekanlarni olish
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
        
        faculty_deans[faculty.id] = deans_list if deans_list else None
        
        # Statistika: yo'nalishlar, guruhlar, talabalar soni
        # Faqat guruhlari bo'lgan yo'nalishlarni hisoblash (semestrlarda ko'rinadigan yo'nalishlar)
        directions_count = db.session.query(Direction).join(Group).filter(
            Direction.faculty_id == faculty.id,
            Group.direction_id == Direction.id
        ).distinct().count()
        groups_count = faculty.groups.count()
        # Talabalar soni (fakultetdagi barcha guruhlardagi talabalar)
        faculty_group_ids = [g.id for g in faculty.groups.all()]
        students_count = User.query.filter(
            User.role == 'student',
            User.group_id.in_(faculty_group_ids) if faculty_group_ids else False
        ).count()
        
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
def create_faculty():
    # Barcha dekanlar (bir nechta rolda bo'lishi mumkin)
    all_deans_query = User.query.join(UserRole).filter(UserRole.role == 'dean')
    # Agar UserRole orqali topilmasa, eski usul bilan qidirish
    if all_deans_query.count() == 0:
        all_deans_query = User.query.filter(User.role == 'dean')
    # Agar hali ham topilmasa, get_roles() orqali qidirish
    if all_deans_query.count() == 0:
        all_users = User.query.all()
        all_deans_list = [u for u in all_users if 'dean' in u.get_roles()]
    else:
        all_deans_list = all_deans_query.all()
    
    if request.method == 'POST':
        name = request.form.get('name')
        code = request.form.get('code').upper()
        description = request.form.get('description')
        selected_dean_ids = request.form.getlist('dean_ids')  # List of dean IDs
        
        if Faculty.query.filter_by(code=code).first():
            flash("Bu kod allaqachon mavjud", 'error')
            return render_template('admin/create_faculty.html', all_deans=all_deans_list)
        
        faculty = Faculty(name=name, code=code, description=description)
        db.session.add(faculty)
        db.session.flush()  # ID ni olish uchun
        
        # Tanlangan dekanlarni fakultetga biriktirish
        for dean_id in selected_dean_ids:
            dean = User.query.get(dean_id)
            if dean and 'dean' in dean.get_roles():
                dean.faculty_id = faculty.id
        
        db.session.commit()
        
        flash("Fakultet muvaffaqiyatli yaratildi", 'success')
        return redirect(url_for('admin.faculties'))
    
    return render_template('admin/create_faculty.html', all_deans=all_deans_list)


@bp.route('/faculties/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_faculty(id):
    faculty = Faculty.query.get_or_404(id)
    
    # Barcha dekanlar (bir nechta rolda bo'lishi mumkin)
    all_deans_query = User.query.join(UserRole).filter(UserRole.role == 'dean')
    # Agar UserRole orqali topilmasa, eski usul bilan qidirish
    if all_deans_query.count() == 0:
        all_deans_query = User.query.filter(User.role == 'dean')
    # Agar hali ham topilmasa, get_roles() orqali qidirish
    if all_deans_query.count() == 0:
        all_users = User.query.all()
        all_deans_list = [u for u in all_users if 'dean' in u.get_roles()]
    else:
        all_deans_list = all_deans_query.all()
    
    # Joriy dekanlar (barcha dekanlar)
    current_deans = User.query.join(UserRole).filter(
        UserRole.role == 'dean',
        User.faculty_id == faculty.id
    ).all()
    
    # Agar UserRole orqali topilmasa, eski usul bilan qidirish
    if not current_deans:
        current_deans = User.query.filter(
            User.role == 'dean',
            User.faculty_id == faculty.id
        ).all()
    
    # Agar hali ham topilmasa, get_roles() orqali qidirish
    if not current_deans:
        all_users = User.query.filter_by(faculty_id=faculty.id).all()
        current_deans = [u for u in all_users if 'dean' in u.get_roles()]
    
    # Joriy dekanlar ID'lari ro'yxati (template uchun)
    current_dean_ids = [d.id for d in current_deans] if current_deans else []
    
    if request.method == 'POST':
        # Fakultet ma'lumotlarini yangilash
        faculty.name = request.form.get('name')
        faculty.code = request.form.get('code').upper()
        faculty.description = request.form.get('description')
        
        # Dekanlarni o'zgartirish
        selected_dean_ids = request.form.getlist('dean_ids')  # List of dean IDs
        
        # Barcha joriy dekanlarning faculty_id ni None qilish
        for current_dean in current_deans:
            current_dean.faculty_id = None
        
        # Tanlangan dekanlarni fakultetga biriktirish
        for dean_id in selected_dean_ids:
            dean = User.query.get(dean_id)
            if dean and 'dean' in dean.get_roles():
                dean.faculty_id = faculty.id
        
        db.session.commit()
        flash("Fakultet muvaffaqiyatli yangilandi", 'success')
        return redirect(url_for('admin.faculties'))
    
    return render_template('admin/edit_faculty.html', 
                         faculty=faculty,
                         all_deans=all_deans_list,
                         current_dean_ids=current_dean_ids)


@bp.route('/faculties/<int:id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_faculty(id):
    faculty = Faculty.query.get_or_404(id)
    
    # Faqat guruhlari bo'lgan yo'nalishlarni tekshirish
    # Agar yo'nalish ichida guruh bo'lmasa, u mavjud emas deb hisoblanadi
    directions_with_groups = db.session.query(Direction).join(Group).filter(
        Direction.faculty_id == faculty.id,
        Group.direction_id == Direction.id
    ).distinct().count()
    
    if directions_with_groups > 0:
        flash("Fakultetda guruhlari bo'lgan yo'nalishlar mavjud. Avval guruhlarni o'chiring", 'error')
        return redirect(url_for('admin.faculties'))
    
    # Guruhlari bo'lmagan yo'nalishlarni o'chirish (chunki ular mavjud emas deb hisoblanadi)
    directions_without_groups = Direction.query.filter_by(faculty_id=faculty.id).all()
    for direction in directions_without_groups:
        # Agar yo'nalishda guruhlar yo'q bo'lsa, o'chirish
        if direction.groups.count() == 0:
            db.session.delete(direction)
    
    # Fanlar endi fakultetga bog'liq emas, shuning uchun ularni alohida tekshirish shart emas
    db.session.delete(faculty)
    db.session.commit()
    flash("Fakultet o'chirildi", 'success')
    
    return redirect(url_for('admin.faculties'))


@bp.route('/faculties/<int:id>')
@login_required
@admin_required
def faculty_detail(id):
    """Fakultet detail sahifasi - kurs>yo'nalish>guruh>talabalar struktura"""
    faculty = Faculty.query.get_or_404(id)
    
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
        Direction.course_year, 
        Direction.semester, 
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
    
    # Kurslar bo'yicha guruhlash (yo'nalishlarning course_year bo'yicha)
    courses_dict = {}
    
    # Avval barcha kurslarni yaratish (1-4 kurslar)
    # Fakultetdagi barcha kurslarni topish (guruhlar yoki yo'nalishlar orqali)
    all_course_years = set()
    for group in all_groups:
        all_course_years.add(group.course_year)
    for direction in all_directions:
        all_course_years.add(direction.course_year)
    
    # Har doim 1-5 kurslarni yaratish (guruhlar yoki yo'nalishlar bo'lmasa ham)
    all_course_years.update({1, 2, 3, 4, 5})
    
    # Barcha kurslarni yaratish
    for course_year in all_course_years:
        if course_year not in courses_dict:
            courses_dict[course_year] = {}
    
    # Barcha yo'nalishlarni kurs va semestr bo'yicha guruhlash
    for direction in all_directions:
        course_year = direction.course_year
        semester = direction.semester
        
        # Semestr bo'yicha guruhlash (1-semestr, 2-semestr, ...)
        if semester not in courses_dict[course_year]:
            courses_dict[course_year][semester] = {}
        
        # Bu yo'nalishga tegishli guruhlarni topish
        direction_groups = [g for g in all_groups if g.direction_id == direction.id]
        
        # Faqat guruhlari bo'lgan yo'nalishlarni ko'rsatish
        if not direction_groups:
            continue
        
        # Yo'nalishni semestr ichiga qo'shish
        direction_id = direction.id
        if direction_id not in courses_dict[course_year][semester]:
            courses_dict[course_year][semester][direction_id] = {
                'direction': direction,
                'direction_name': direction.name,
                'groups': direction_groups
            }
    
    # Biriktirilmagan guruhlarni qo'shish
    for group in all_groups:
        if not group.direction_id:
            course_year = group.course_year
            if course_year not in courses_dict:
                courses_dict[course_year] = {}
            
            # Biriktirilmagan guruhlar uchun 1-semestr bo'limiga qo'shish
            if 1 not in courses_dict[course_year]:
                courses_dict[course_year][1] = {}
            
            direction_id = None
            if direction_id not in courses_dict[course_year][1]:
                courses_dict[course_year][1][direction_id] = {
                    'direction': None,
                    'direction_name': "Biriktirilmagan",
                    'groups': []
                }
            
            courses_dict[course_year][1][direction_id]['groups'].append(group)
    
    # Har bir kurs uchun statistika hisoblash
    for course_year, course_data in courses_dict.items():
        # course_data endi semestrlar bo'yicha guruhlangan {1: {direction_id: {...}}, 2: {...}}
        total_directions = 0
        total_groups = 0
        total_students = 0
        
        # Har bir semestr uchun statistika
        for semester, semester_data in course_data.items():
            # Har bir yo'nalish uchun statistika
            for direction_id, direction_data in semester_data.items():
                direction_data['students_count'] = User.query.filter(
                    User.group_id.in_([g.id for g in direction_data['groups']]),
                    User.role == 'student'
                ).count() if direction_data['groups'] else 0
                
                if direction_data['direction']:
                    # Yo'nalishdagi fanlar sonini o'quv rejasi orqali hisoblash (unique subject_id lar soni)
                    direction_data['subjects_count'] = db.session.query(
                        func.count(func.distinct(DirectionCurriculum.subject_id))
                    ).filter_by(direction_id=direction_data['direction'].id).scalar() or 0
                else:
                    direction_data['subjects_count'] = 0
                
                total_directions += 1
                total_groups += len(direction_data['groups'])
                total_students += direction_data['students_count']
        
        course_data['total_directions'] = total_directions
        course_data['total_groups'] = total_groups
        course_data['total_students'] = total_students
    
    # Kurslarni tartiblash
    sorted_courses = sorted(courses_dict.items())
    
    # Template uchun courses_dict'ni to'g'rilash
    # courses_dict strukturasini template'ga moslashtirish
    # course_data endi {semester: {direction_id: {...}}} formatida
    formatted_courses_dict = {}
    for course_year, course_data in dict(sorted_courses).items():
        # Semestrlar bo'yicha guruhlangan yo'nalishlarni birlashtirish
        # Avval 1-semestr, keyin 2-semestr va hokazo
        all_directions = {}
        
        # Semestrlar ro'yxatini tartiblash (faqat int bo'lganlar)
        semesters_list = sorted([s for s in course_data.keys() if isinstance(s, int)])
        
        # Semestrlar bo'yicha yo'nalishlarni birlashtirish (faqat guruhlari bo'lganlar)
        for semester in semesters_list:
            for direction_id, direction_data in course_data[semester].items():
                # Faqat guruhlari bo'lgan yo'nalishlarni qo'shish
                if direction_data.get('groups'):
                    all_directions[direction_id] = direction_data
        
        # Semestrlar bo'yicha ajratilgan struktura (template uchun)
        # Faqat yo'nalishlari bo'lgan semestrlarni qo'shish
        semesters_dict = {}
        for semester in semesters_list:
            # Faqat guruhlari bo'lgan yo'nalishlar bo'lishi kerak
            filtered_directions = {
                direction_id: direction_data 
                for direction_id, direction_data in course_data[semester].items()
                if direction_data.get('groups')  # Guruhlari bo'lgan yo'nalishlar
            }
            if filtered_directions:  # Faqat bo'sh bo'lmagan semestrlarni qo'shish
                semesters_dict[semester] = filtered_directions
        
        # semesters_list ni faqat semesters_dict da mavjud bo'lgan semestrlar bilan yangilash
        filtered_semesters_list = sorted([s for s in semesters_list if s in semesters_dict])
        
        formatted_courses_dict[course_year] = {
            'directions': all_directions,  # Barcha semestrlar birlashtirilgan
            'semesters': semesters_dict,  # Semestrlar bo'yicha ajratilgan (template uchun)
            'semesters_list': filtered_semesters_list,  # Faqat guruhlari bo'lgan semestrlar ro'yxati
            'total_directions': course_data.get('total_directions', len(all_directions)),
            'total_groups': course_data.get('total_groups', 0),
            'total_students': course_data.get('total_students', 0)
        }
    
    # Filtrlar uchun ma'lumotlar
    courses_list = sorted(set([g.course_year for g in faculty.groups.all()]))
    directions_list = Direction.query.filter_by(faculty_id=faculty.id).order_by(
        Direction.course_year, 
        Direction.semester, 
        Direction.name
    ).all()
    groups_list = faculty.groups.order_by(Group.name).all()
    
    return render_template('admin/faculty_detail.html',
                         faculty=faculty,
                         dean=dean,
                         deans_list=deans_list,
                         courses_dict=formatted_courses_dict,
                         courses_list=courses_list,
                         directions_list=directions_list,
                         groups_list=groups_list,
                         course_filter=course_filter,
                         direction_filter=direction_filter,
                         group_filter=group_filter,
                         search=search)


# ==================== YO'NALISHLAR ====================
@bp.route('/directions/<int:id>')
@login_required
@admin_required
def direction_detail(id):
    """Yo'nalish detail sahifasi - ichidagi guruhlar"""
    direction = Direction.query.get_or_404(id)
    
    # Bu yo'nalishga biriktirilgan guruhlar
    groups = Group.query.filter_by(direction_id=direction.id).order_by(Group.course_year, Group.name).all()
    
    # Har bir guruh uchun talabalar soni
    group_stats = {}
    for group in groups:
        group_stats[group.id] = group.students.count()
    
    return render_template('admin/direction_detail.html',
                         direction=direction,
                         groups=groups,
                         group_stats=group_stats)


@bp.route('/directions/<int:id>/curriculum')
@login_required
@admin_required
def direction_curriculum(id):
    """Yo'nalish o'quv rejasi"""
    direction = Direction.query.get_or_404(id)
    
    # Barcha fanlar
    all_subjects = Subject.query.order_by(Subject.name).all()
    
    # O'quv rejadagi fanlar (semestr bo'yicha guruhlangan)
    curriculum_by_semester = {}
    semester_totals = {}  # Har bir semestr uchun jami soat va kredit
    semester_auditoriya = {}  # Har bir semestr uchun auditoriya soatlari
    semester_mustaqil = {}  # Har bir semestr uchun mustaqil ta'lim soatlari
    total_hours = 0
    total_credits = 0
    
    for item in direction.curriculum_items.join(Subject).order_by(
        DirectionCurriculum.semester,
        Subject.name
    ).all():
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
        semester_auditoriya[semester]['k'] += (item.hours_kurs_ishi or 0)
        
        # Mustaqil ta'lim
        semester_mustaqil[semester] += (item.hours_mustaqil or 0)
        
        # Semestr jami soat va kreditni hisoblash (K qo'shilmaydi)
        item_hours = (item.hours_maruza or 0) + (item.hours_amaliyot or 0) + \
                    (item.hours_laboratoriya or 0) + (item.hours_seminar or 0) + \
                    (item.hours_mustaqil or 0)
        item_credits = item_hours / 30
        
        semester_totals[semester]['hours'] += item_hours
        semester_totals[semester]['credits'] += item_credits
        
        # Umumiy yuklamani hisoblash
        total_hours += item_hours
        total_credits += item_credits
    
    return render_template('admin/direction_curriculum.html',
                         direction=direction,
                         all_subjects=all_subjects,
                         curriculum_by_semester=curriculum_by_semester,
                         semester_totals=semester_totals,
                         semester_auditoriya=semester_auditoriya,
                         semester_mustaqil=semester_mustaqil,
                         total_hours=total_hours,
                         total_credits=total_credits)


@bp.route('/directions/<int:id>/curriculum/export')
@login_required
@admin_required
def export_curriculum(id):
    """O'quv rejani Excel formatida export qilish"""
    from app.utils.excel_export import create_curriculum_excel
    
    direction = Direction.query.get_or_404(id)
    
    # O'quv rejadagi barcha elementlar
    curriculum_items = direction.curriculum_items.join(Subject).order_by(
        DirectionCurriculum.semester,
        Subject.name
    ).all()
    
    excel_file = create_curriculum_excel(direction, curriculum_items)
    
    filename = f"oquv_reja_{direction.code}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return send_file(
        excel_file,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=filename
    )


@bp.route('/directions/<int:id>/curriculum/import', methods=['GET', 'POST'])
@login_required
@admin_required
def import_curriculum(id):
    """O'quv rejani Excel fayldan import qilish"""
    from app.utils.excel_import import import_curriculum_from_excel
    
    direction = Direction.query.get_or_404(id)
    
    if request.method == 'POST':
        if 'file' not in request.files:
            flash("Fayl tanlanmagan", 'error')
            return redirect(url_for('admin.direction_curriculum', id=id))
        
        file = request.files['file']
        if file.filename == '':
            flash("Fayl tanlanmagan", 'error')
            return redirect(url_for('admin.direction_curriculum', id=id))
        
        if not file.filename.endswith(('.xlsx', '.xls')):
            flash("Faqat .xlsx yoki .xls formatidagi fayllar qabul qilinadi", 'error')
            return redirect(url_for('admin.direction_curriculum', id=id))
        
        result = import_curriculum_from_excel(file, direction.id)
        
        result = import_curriculum_from_excel(file, direction.id)
        
        if result['success']:
            if result['imported'] > 0 or result['updated'] > 0:
                message = f"Muvaffaqiyatli! {result['imported']} ta yangi qo'shildi, {result['updated']} ta yangilandi."
                if result.get('subjects_created', 0) > 0:
                    message += f" {result['subjects_created']} ta yangi fan yaratildi."
                if result['errors']:
                    message += f" {len(result['errors'])} ta xatolik yuz berdi."
                flash(message, 'success' if not result['errors'] else 'warning')
            else:
                flash("Hech qanday o'zgarish kiritilmadi", 'info')
            
            if result['errors']:
                for error in result['errors'][:10]:  # Faqat birinchi 10 ta xatolikni ko'rsatish
                    flash(error, 'error')
        else:
            flash(f"Import qilishda xatolik: {', '.join(result['errors'])}", 'error')
        
        return redirect(url_for('admin.direction_curriculum', id=id))
    
    return render_template('admin/import_curriculum.html', direction=direction)


@bp.route('/directions/<int:id>/curriculum/import/sample')
@login_required
@admin_required
def download_curriculum_sample(id):
    """O'quv reja import uchun namuna fayl yuklab olish"""
    from app.utils.excel_import import generate_curriculum_sample_file
    
    direction = Direction.query.get_or_404(id)
    
    excel_file = generate_curriculum_sample_file()
    
    filename = f"oquv_reja_import_namuna_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return send_file(
        excel_file,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=filename
    )


@bp.route('/directions/<int:id>/subjects', methods=['GET', 'POST'])
@login_required
@admin_required
def direction_subjects(id):
    """Yo'nalish fanlari sahifasi - jadval ko'rinishida"""
    direction = Direction.query.get_or_404(id)
    
    # POST so'rov - o'qituvchilarni saqlash
    if request.method == 'POST':
        semester = request.form.get('semester', type=int)
        if not semester:
            flash("Semestr tanlanmagan", 'error')
            return redirect(url_for('admin.direction_subjects', id=id))
        
        # Yo'nalishga biriktirilgan guruhlar
        groups = Group.query.filter_by(direction_id=direction.id).all()
        if not groups:
            flash("Yo'nalishda guruhlar mavjud emas", 'error')
            return redirect(url_for('admin.direction_subjects', id=id))
        
        # Semestrdagi barcha fanlar uchun o'qituvchilarni yangilash
        for item in direction.curriculum_items.filter_by(semester=semester).all():
            # Maruza o'qituvchisi
            maruza_teacher_id = request.form.get(f'teacher_maruza_{item.id}', type=int)
            teacher_subject = TeacherSubject.query.filter_by(
                subject_id=item.subject_id,
                group_id=groups[0].id,
                lesson_type='maruza'
            ).first()
            
            if maruza_teacher_id:
                if teacher_subject:
                    teacher_subject.teacher_id = maruza_teacher_id
                else:
                    teacher_subject = TeacherSubject(
                        teacher_id=maruza_teacher_id,
                        subject_id=item.subject_id,
                        group_id=groups[0].id,
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
                practical_teacher_id = request.form.get(f'teacher_practical_{item.id}', type=int)
                teacher_subject = TeacherSubject.query.filter_by(
                    subject_id=item.subject_id,
                    group_id=groups[0].id,
                    lesson_type='amaliyot'
                ).first()
                
                if practical_teacher_id:
                    if teacher_subject:
                        teacher_subject.teacher_id = practical_teacher_id
                    else:
                        teacher_subject = TeacherSubject(
                            teacher_id=practical_teacher_id,
                            subject_id=item.subject_id,
                            group_id=groups[0].id,
                            lesson_type='amaliyot'
                        )
                        db.session.add(teacher_subject)
                else:
                    # Agar o'qituvchi tanlanmagan bo'lsa, mavjud biriktirishni o'chirish
                    if teacher_subject:
                        db.session.delete(teacher_subject)
            
            # Seminar o'qituvchisi (faqat seminar soatlari bo'lsa)
            if (item.hours_seminar or 0) > 0:
                seminar_teacher_id = request.form.get(f'teacher_seminar_{item.id}', type=int)
                # Seminar uchun alohida TeacherSubject yaratish yoki topish
                teacher_subject = TeacherSubject.query.filter_by(
                    subject_id=item.subject_id,
                    group_id=groups[0].id,
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
                            group_id=groups[0].id,
                            lesson_type='seminar'
                        )
                        db.session.add(teacher_subject)
                else:
                    # Agar o'qituvchi tanlanmagan bo'lsa, mavjud biriktirishni o'chirish
                    if teacher_subject:
                        db.session.delete(teacher_subject)
        
        db.session.commit()
        flash(f"{semester}-semestr o'qituvchilari muvaffaqiyatli saqlandi", 'success')
        return redirect(url_for('admin.direction_subjects', id=id))
    
    # Yo'nalishga biriktirilgan guruhlar
    groups = Group.query.filter_by(direction_id=direction.id).all()
    
    # O'quv rejadagi fanlar (semestr bo'yicha guruhlangan)
    subjects_by_semester = {}
    
    for item in direction.curriculum_items.join(Subject).order_by(DirectionCurriculum.semester, Subject.name).all():
        semester = item.semester
        if semester not in subjects_by_semester:
            subjects_by_semester[semester] = []
        
        # Har bir fan uchun dars turlarini va o'qituvchilarni olish
        subject_data = {
            'subject': item.subject,
            'curriculum_item': item,  # Curriculum item ID uchun
            'lessons': []
        }
        
        # Maruza
        if item.hours_maruza and item.hours_maruza > 0:
            # O'qituvchini topish (birinchi guruhdan)
            teacher = None
            if groups:
                teacher_subject = TeacherSubject.query.filter_by(
                    subject_id=item.subject_id,
                    group_id=groups[0].id,
                    lesson_type='maruza'
                ).first()
                if teacher_subject:
                    teacher = teacher_subject.teacher
            
            subject_data['lessons'].append({
                'type': 'Maruza',
                'hours': item.hours_maruza,
                'teacher': teacher
            })
        
        # Amaliyot, Lobaratoriya va Kurs ishi bitta yacheykada
        amaliyot_hours = item.hours_amaliyot or 0
        lobaratoriya_hours = item.hours_laboratoriya or 0
        kurs_ishi_hours = item.hours_kurs_ishi or 0
        # Kurs ishi soatlari umumiy soatlar yig'indisiga qo'shilmaydi
        total_practical_hours = amaliyot_hours + lobaratoriya_hours
        
        if total_practical_hours > 0 or kurs_ishi_hours > 0:
            # O'qituvchini topish
            teacher = None
            if groups:
                teacher_subject = TeacherSubject.query.filter_by(
                    subject_id=item.subject_id,
                    group_id=groups[0].id,
                    lesson_type='amaliyot'
                ).first()
                if teacher_subject:
                    teacher = teacher_subject.teacher
            
            # Dars turlarini tartib bilan yig'ish
            lesson_types = []
            if amaliyot_hours > 0:
                lesson_types.append('Amaliyot')
            if lobaratoriya_hours > 0:
                lesson_types.append('Lobaratoriya')
            if kurs_ishi_hours > 0:
                lesson_types.append('Kurs ishi')
            
            lesson_type_name = ', '.join(lesson_types)
            # Kurs ishi soatlari ko'rsatiladi, lekin umumiy soatlar yig'indisiga qo'shilmaydi
            # Ko'rsatiladigan soatlar: amaliyot + lobaratoriya (kurs ishi qo'shilmaydi)
            display_hours = total_practical_hours
            
            subject_data['lessons'].append({
                'type': lesson_type_name,
                'hours': display_hours,
                'teacher': teacher,
                'curriculum_item_id': item.id
            })
        
        # Seminar
        if item.hours_seminar and item.hours_seminar > 0:
            teacher = None
            if groups:
                # Seminar uchun alohida qidirish
                teacher_subject = TeacherSubject.query.filter_by(
                    subject_id=item.subject_id,
                    group_id=groups[0].id,
                    lesson_type='seminar'
                ).first()
                # Agar topilmasa, amaliyot turidagini qidirish (eski ma'lumotlar uchun)
                if not teacher_subject:
                    teacher_subject = TeacherSubject.query.filter_by(
                        subject_id=item.subject_id,
                        group_id=groups[0].id,
                        lesson_type='amaliyot'
                    ).first()
                    # Agar amaliyot topilsa va fanda faqat seminar bo'lsa, uni seminar deb hisoblash
                    if teacher_subject and (item.hours_amaliyot or 0) == 0 and (item.hours_laboratoriya or 0) == 0:
                        pass  # Bu seminar o'qituvchisi
                    elif teacher_subject:
                        teacher_subject = None  # Bu amaliyot o'qituvchisi, seminar emas
                if teacher_subject:
                    teacher = teacher_subject.teacher
            
            subject_data['lessons'].append({
                'type': 'Seminar',
                'hours': item.hours_seminar,
                'teacher': teacher
            })
        
        subjects_by_semester[semester].append(subject_data)
    
    # Tizimdagi barcha o'qituvchilar
    # UserRole orqali o'qituvchi roliga ega bo'lgan foydalanuvchilarni topish
    teacher_user_ids = db.session.query(UserRole.user_id).filter_by(role='teacher').distinct().all()
    teacher_user_ids = [uid[0] for uid in teacher_user_ids]
    
    # Agar UserRole orqali topilmasa, eski usul bilan qidirish
    if not teacher_user_ids:
        teachers_by_role = User.query.filter_by(role='teacher').all()
        teacher_user_ids = [t.id for t in teachers_by_role]
    
    # Agar hali ham topilmasa, get_roles() orqali qidirish
    if not teacher_user_ids:
        all_users = User.query.all()
        teacher_user_ids = [u.id for u in all_users if 'teacher' in u.get_roles()]
    
    # Barcha o'qituvchilar (fakultet cheklovi yo'q)
    if teacher_user_ids:
        teachers = User.query.filter(
            User.id.in_(teacher_user_ids)
        ).order_by(User.full_name).all()
    else:
        teachers = []
    
    return render_template('admin/direction_subjects.html',
                         direction=direction,
                         subjects_by_semester=subjects_by_semester,
                         groups=groups,
                         teachers=teachers)


@bp.route('/directions/<int:id>/curriculum/semester/<int:semester>/update', methods=['POST'])
@login_required
@admin_required
def update_semester_curriculum(id, semester):
    """Semestr bo'yicha barcha fanlarni yangilash"""
    direction = Direction.query.get_or_404(id)
    
    # Bu semestr uchun barcha fanlarni olish
    items = DirectionCurriculum.query.filter_by(
        direction_id=direction.id,
        semester=semester
    ).all()
    
    updated = 0
    for item in items:
        item_id = str(item.id)
        
        # Soatlarni yangilash
        item.hours_maruza = request.form.get(f'hours_maruza[{item_id}]', type=int) or 0
        item.hours_amaliyot = request.form.get(f'hours_amaliyot[{item_id}]', type=int) or 0
        item.hours_laboratoriya = request.form.get(f'hours_laboratoriya[{item_id}]', type=int) or 0
        item.hours_seminar = request.form.get(f'hours_seminar[{item_id}]', type=int) or 0
        item.hours_mustaqil = request.form.get(f'hours_mustaqil[{item_id}]', type=int) or 0
        
        # Kurs ishi checkbox - agar belgilangan bo'lsa 1, aks holda 0
        kurs_ishi_values = request.form.getlist('hours_kurs_ishi')
        item.hours_kurs_ishi = 1 if item_id in kurs_ishi_values else 0
        
        updated += 1
    
    db.session.commit()
    flash(f"{updated} ta fan yangilandi", 'success')
    return redirect(url_for('admin.direction_curriculum', id=id))


@bp.route('/directions/<int:id>/curriculum/<int:item_id>/replace', methods=['POST'])
@login_required
@admin_required
def replace_curriculum_subject(id, item_id):
    """O'quv rejadagi fanni boshqa fan bilan almashtirish"""
    direction = Direction.query.get_or_404(id)
    item = DirectionCurriculum.query.get_or_404(item_id)
    
    if item.direction_id != direction.id:
        flash("Sizda bu amal uchun ruxsat yo'q", 'error')
        return redirect(url_for('admin.faculties'))
    
    new_subject_id = request.form.get('subject_id', type=int)
    if not new_subject_id:
        flash("Fan tanlash majburiy", 'error')
        return redirect(url_for('admin.direction_curriculum', id=id))
    
    # Takrorlanmasligini tekshirish
    existing = DirectionCurriculum.query.filter_by(
        direction_id=direction.id,
        subject_id=new_subject_id,
        semester=item.semester
    ).filter(DirectionCurriculum.id != item_id).first()
    
    if existing:
        flash("Bu semestrda bu fan allaqachon mavjud", 'error')
        return redirect(url_for('admin.direction_curriculum', id=id))
    
    item.subject_id = new_subject_id
    db.session.commit()
    flash("Fan almashtirildi", 'success')
    return redirect(url_for('admin.direction_curriculum', id=id))


@bp.route('/directions/<int:id>/curriculum/<int:item_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_curriculum_item(id, item_id):
    """O'quv rejadagi fanni o'chirish"""
    direction = Direction.query.get_or_404(id)
    item = DirectionCurriculum.query.get_or_404(item_id)
    
    if item.direction_id != direction.id:
        flash("Sizda bu amal uchun ruxsat yo'q", 'error')
        return redirect(url_for('admin.faculties'))
    
    db.session.delete(item)
    db.session.commit()
    flash("Fan o'quv rejasidan o'chirildi", 'success')
    return redirect(url_for('admin.direction_curriculum', id=id))


@bp.route('/directions/<int:id>/curriculum/add', methods=['POST'])
@login_required
@admin_required
def add_subject_to_curriculum(id):
    """O'quv rejaga fan qo'shish"""
    direction = Direction.query.get_or_404(id)
    
    subject_ids = request.form.getlist('subject_ids')
    semester = request.form.get('semester', type=int)
    
    if not subject_ids or not semester:
        flash("Fan va semestr tanlash majburiy", 'error')
        return redirect(url_for('admin.direction_curriculum', id=id))
    
    added = 0
    for subject_id in subject_ids:
        subject_id = int(subject_id)
        subject = Subject.query.get(subject_id)
        if not subject:
            continue
        
        # Takrorlanmasligini tekshirish
        existing = DirectionCurriculum.query.filter_by(
            direction_id=direction.id,
            subject_id=subject_id,
            semester=semester
        ).first()
        
        if not existing:
            curriculum_item = DirectionCurriculum(
                direction_id=direction.id,
                subject_id=subject_id,
                semester=semester
            )
            db.session.add(curriculum_item)
            added += 1
    
    db.session.commit()
    flash(f"{added} ta fan o'quv rejaga qo'shildi", 'success')
    return redirect(url_for('admin.direction_curriculum', id=id))


@bp.route('/faculties/<int:id>/change_dean', methods=['GET', 'POST'])
@login_required
@admin_required
def change_faculty_dean(id):
    """Fakultet masul dekanlarini o'zgartirish (bir nechta dekan biriktirish mumkin)"""
    faculty = Faculty.query.get_or_404(id)
    
    # Barcha dekanlar (bir nechta rolda bo'lishi mumkin)
    all_deans_query = User.query.join(UserRole).filter(UserRole.role == 'dean')
    # Agar UserRole orqali topilmasa, eski usul bilan qidirish
    if all_deans_query.count() == 0:
        all_deans_query = User.query.filter(User.role == 'dean')
    # Agar hali ham topilmasa, get_roles() orqali qidirish
    if all_deans_query.count() == 0:
        all_users = User.query.all()
        all_deans_list = [u for u in all_users if 'dean' in u.get_roles()]
    else:
        all_deans_list = all_deans_query.all()
    
    # Joriy dekanlar (barcha dekanlar)
    current_deans = User.query.join(UserRole).filter(
        UserRole.role == 'dean',
        User.faculty_id == faculty.id
    ).all()
    
    # Agar UserRole orqali topilmasa, eski usul bilan qidirish
    if not current_deans:
        current_deans = User.query.filter(
            User.role == 'dean',
            User.faculty_id == faculty.id
        ).all()
    
    # Agar hali ham topilmasa, get_roles() orqali qidirish
    if not current_deans:
        all_users = User.query.filter_by(faculty_id=faculty.id).all()
        current_deans = [u for u in all_users if 'dean' in u.get_roles()]
    
    # Joriy dekanlar ID'lari ro'yxati (template uchun)
    current_dean_ids = [d.id for d in current_deans] if current_deans else []
    
    if request.method == 'POST':
        # Bir nechta dekan tanlash mumkin
        selected_dean_ids = request.form.getlist('dean_ids')  # List of dean IDs
        
        # Barcha joriy dekanlarning faculty_id ni None qilish
        for current_dean in current_deans:
            current_dean.faculty_id = None
        
        # Tanlangan dekanlarni fakultetga biriktirish
        for dean_id in selected_dean_ids:
            dean = User.query.get(dean_id)
            if dean and 'dean' in dean.get_roles():
                dean.faculty_id = faculty.id
        
        db.session.commit()
        flash("Masul dekanlar muvaffaqiyatli o'zgartirildi", 'success')
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
def subjects():
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '').strip()
    
    query = Subject.query
    if search:
        query = query.filter(
            Subject.name.ilike(f'%{search}%')
        )
    
    subjects = query.order_by(Subject.name).paginate(page=page, per_page=50, error_out=False)
    
    return render_template('admin/subjects.html', subjects=subjects, search=search)


@bp.route('/schedule/sample')
@login_required
@admin_required
def download_schedule_sample():
    try:
        output = generate_schedule_sample_file()
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name='dars_jadvali_namuna.xlsx'
        )
    except Exception as e:
        flash(f'Namuna fayl yaratishda xatolik: {str(e)}', 'danger')
        return redirect(url_for('admin.schedule'))

@bp.route('/schedule/import', methods=['GET', 'POST'])
@login_required
@admin_required
def import_schedule():
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('Fayl tanlanmagan', 'danger')
            return redirect(request.url)
            
        file = request.files['file']
        if file.filename == '':
            flash('Fayl tanlanmagan', 'danger')
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
                            flash(f"{count} ta dars jadvali muvaffaqiyatli import qilindi", 'warning')
                    else:
                        flash(f"{count} ta dars jadvali muvaffaqiyatli import qilindi", 'success')
                    return redirect(url_for('admin.schedule'))
                else:
                    for error in result.get('errors', []):
                        flash(error, 'danger')
            except Exception as e:
                flash(f"Xatolik yuz berdi: {str(e)}", 'danger')
        else:
            flash("Faqat .xlsx formatidagi fayllarni yuklash mumkin", 'danger')
            
    return render_template('admin/import_schedule.html')

@bp.route('/students/import/sample')
@login_required
@admin_required
def download_sample_import():
    try:
        file_stream = generate_sample_file()
        return send_file(
            file_stream,
            as_attachment=True,
            download_name='talabalar_import_namuna.xlsx',
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
    except Exception as e:
        flash(f"Namuna fayl yaratishda xatolik: {str(e)}", 'error')
        return redirect(url_for('admin.import_students'))

@bp.route('/subjects/create', methods=['GET', 'POST'])
@login_required
@admin_required
def create_subject():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()
        
        if not name:
            flash("Fan nomi majburiy maydon", 'error')
            return render_template('admin/create_subject.html')
        
        subject = Subject(
            name=name,
            code='',  # Bo'sh kod (kerak emas)
            description=description if description else None,
            credits=3,  # Default value
            semester=1  # Default value
        )
        db.session.add(subject)
        db.session.commit()
        
        flash("Fan muvaffaqiyatli yaratildi", 'success')
        return redirect(url_for('admin.subjects'))
    
    return render_template('admin/create_subject.html')


@bp.route('/subjects/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_subject(id):
    subject = Subject.query.get_or_404(id)
    
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()
        
        if not name:
            flash("Fan nomi majburiy maydon", 'error')
            return render_template('admin/edit_subject.html', subject=subject)
        
        subject.name = name
        subject.description = description if description else None
        
        db.session.commit()
        flash("Fan yangilandi", 'success')
        return redirect(url_for('admin.subjects'))
    
    return render_template('admin/edit_subject.html', subject=subject)


@bp.route('/subjects/<int:id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_subject(id):
    subject = Subject.query.get_or_404(id)
    db.session.delete(subject)
    db.session.commit()
    flash("Fan o'chirildi", 'success')
    return redirect(url_for('admin.subjects'))


@bp.route('/subjects/export')
@login_required
@admin_required
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
        flash(f"Export xatosi: {str(e)}", 'error')
        return redirect(url_for('admin.subjects'))


@bp.route('/subjects/import', methods=['GET', 'POST'])
@login_required
@admin_required
def import_subjects():
    """Excel fayldan fanlarni import qilish"""
    if request.method == 'POST':
        if 'excel_file' not in request.files:
            flash("Fayl tanlanmagan", 'error')
            return redirect(url_for('admin.subjects'))
        
        file = request.files['excel_file']
        if file.filename == '':
            flash("Fayl tanlanmagan", 'error')
            return redirect(url_for('admin.subjects'))
        
        if not file.filename.endswith(('.xlsx', '.xls')):
            flash("Faqat Excel fayllar (.xlsx, .xls) qo'llab-quvvatlanadi", 'error')
            return redirect(url_for('admin.subjects'))
        
        try:
            result = import_subjects_from_excel(file)
            
            if result['success']:
                if result['imported'] > 0:
                    flash(f"{result['imported']} ta fan muvaffaqiyatli import qilindi", 'success')
                if result['updated'] > 0:
                    flash(f"{result['updated']} ta fan yangilandi", 'success')
                if result['imported'] == 0 and result['updated'] == 0:
                    flash("Hech qanday fan import qilinmadi", 'warning')
                
                if result['errors']:
                    error_msg = f"Xatolar ({len(result['errors'])}): " + "; ".join(result['errors'][:5])
                    if len(result['errors']) > 5:
                        error_msg += f" va yana {len(result['errors']) - 5} ta xato"
                    flash(error_msg, 'warning')
            else:
                flash(f"Import xatosi: {result['errors'][0] if result['errors'] else 'Noma`lum xatolik'}", 'error')
                
        except ImportError as e:
            flash(f"Excel import funksiyasi ishlamayapti: {str(e)}", 'error')
        except Exception as e:
            flash(f"Import xatosi: {str(e)}", 'error')
        
        return redirect(url_for('admin.subjects'))
    
    return render_template('admin/import_subjects.html')


@bp.route('/subjects/import/sample')
@login_required
@admin_required
def download_subjects_sample():
    """Fanlarni import qilish uchun namuna Excel faylni yuklab berish"""
    try:
        sample_file = generate_subjects_sample_file()
        filename = "fanlar_import_namuna.xlsx"
        return send_file(
            sample_file,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        flash(f"Namuna fayl yuklab olishda xatolik: {str(e)}", 'error')
        return redirect(url_for('admin.subjects'))


# ==================== HISOBOTLAR ====================
@bp.route('/reports')
@login_required
@admin_required
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
def grade_scale():
    """Baholash tizimini ko'rish"""
    grades = GradeScale.query.order_by(GradeScale.order).all()
    return render_template('admin/grade_scale.html', grades=grades)


@bp.route('/grade-scale/create', methods=['GET', 'POST'])
@login_required
@admin_required
def create_grade():
    """Yangi baho qo'shish"""
    if request.method == 'POST':
        letter = request.form.get('letter').upper()
        
        # Tekshirish: bu harf mavjudmi
        if GradeScale.query.filter_by(letter=letter).first():
            flash("Bu baho harfi allaqachon mavjud", 'error')
            return render_template('admin/create_grade.html')
        
        # Ball oralig'ini tekshirish
        min_score = request.form.get('min_score', type=float)
        max_score = request.form.get('max_score', type=float)
        
        if min_score > max_score:
            flash("Minimal ball maksimaldan katta bo'lishi mumkin emas", 'error')
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
        
        flash("Baho muvaffaqiyatli qo'shildi", 'success')
        return redirect(url_for('admin.grade_scale'))
    
    return render_template('admin/create_grade.html')


@bp.route('/grade-scale/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
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
        flash("Baho yangilandi", 'success')
        return redirect(url_for('admin.grade_scale'))
    
    return render_template('admin/edit_grade.html', grade=grade)


@bp.route('/grade-scale/<int:id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_grade(id):
    """Bahoni o'chirish"""
    grade = GradeScale.query.get_or_404(id)
    db.session.delete(grade)
    db.session.commit()
    flash("Baho o'chirildi", 'success')
    return redirect(url_for('admin.grade_scale'))


@bp.route('/grade-scale/reset', methods=['POST'])
@login_required
@admin_required
def reset_grade_scale():
    """Standart baholarni tiklash"""
    # Barcha baholarni o'chirish
    GradeScale.query.delete()
    db.session.commit()
    
    # Standart baholarni qayta yaratish
    GradeScale.init_default_grades()
    
    flash("Baholash tizimi standart holatga qaytarildi", 'success')
    return redirect(url_for('admin.grade_scale'))


# ==================== EXCEL IMPORT ====================
@bp.route('/import/students', methods=['GET', 'POST'])
@login_required
@admin_required
def import_students():
    """Excel fayldan talabalar import qilish"""
    if request.method == 'POST':
        if 'excel_file' not in request.files:
            flash("Fayl tanlanmagan", 'error')
            return redirect(url_for('admin.students'))
        
        file = request.files['excel_file']
        if file.filename == '':
            flash("Fayl tanlanmagan", 'error')
            return redirect(url_for('admin.students'))
        
        if not file.filename.endswith(('.xlsx', '.xls')):
            flash("Faqat Excel fayllar (.xlsx, .xls) qo'llab-quvvatlanadi", 'error')
            return redirect(url_for('admin.students'))
        
        try:
            from app.utils.excel_import import import_students_from_excel
            
            result = import_students_from_excel(file, faculty_id=None)
            
            if result['success']:
                if result['imported'] > 0:
                    flash(f"{result['imported']} ta talaba muvaffaqiyatli import qilindi", 'success')
                else:
                    flash("Hech qanday talaba import qilinmadi", 'warning')
                
                if result['errors']:
                    error_msg = f"Xatolar ({len(result['errors'])}): " + "; ".join(result['errors'][:5])
                    if len(result['errors']) > 5:
                        error_msg += f" va yana {len(result['errors']) - 5} ta xato"
                    flash(error_msg, 'warning')
            else:
                flash(f"Import xatosi: {result['errors'][0] if result['errors'] else 'Noma`lum xatolik'}", 'error')
                
        except ImportError as e:
            flash(f"Excel import funksiyasi ishlamayapti: {str(e)}", 'error')
        except Exception as e:
            flash(f"Import xatosi: {str(e)}", 'error')
        
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
        flash("Excel export funksiyasi ishlamayapti. Iltimos, 'pip install openpyxl' buyrug'ini bajaring.", 'error')
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
        flash("Excel export funksiyasi ishlamayapti. Iltimos, 'pip install openpyxl' buyrug'ini bajaring.", 'error')
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
    
    # Talabalar emas, faqat xodimlar
    staff_users = User.query.filter(
        User.id.in_(list(staff_user_ids)),
        User.role != 'student'
    ).all()
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
def import_all_users():
    """Excel fayldan barcha foydalanuvchilarni import qilish (rol bo'yicha ajratish)"""
    if request.method == 'POST':
        if 'excel_file' not in request.files:
            flash("Fayl tanlanmagan", 'error')
            return redirect(url_for('admin.staff'))
        
        file = request.files['excel_file']
        if file.filename == '':
            flash("Fayl tanlanmagan", 'error')
            return redirect(url_for('admin.staff'))
        
        if not file.filename.endswith(('.xlsx', '.xls')):
            flash("Faqat Excel fayllar (.xlsx, .xls) qo'llab-quvvatlanadi", 'error')
            return redirect(url_for('admin.staff'))
        
        try:
            from app.utils.excel_import import import_staff_from_excel
            
            result = import_staff_from_excel(file)
            
            if result['success']:
                if result['imported'] > 0:
                    flash(f"{result['imported']} ta foydalanuvchi muvaffaqiyatli import qilindi", 'success')
                else:
                    flash("Hech qanday foydalanuvchi import qilinmadi", 'warning')
                
                if result['errors']:
                    error_msg = f"Xatolar ({len(result['errors'])}): " + "; ".join(result['errors'][:5])
                    if len(result['errors']) > 5:
                        error_msg += f" va yana {len(result['errors']) - 5} ta xato"
                    flash(error_msg, 'warning')
            else:
                flash(f"Import xatosi: {result['errors'][0] if result['errors'] else 'Noma`lum xatolik'}", 'error')
                
        except ImportError as e:
            flash(f"Excel import funksiyasi ishlamayapti: {str(e)}", 'error')
        except Exception as e:
            flash(f"Import xatosi: {str(e)}", 'error')
        
        return redirect(url_for('admin.staff'))
    
    return render_template('admin/import_all_users.html')


@bp.route('/staff/import/sample')
@login_required
@admin_required
def download_staff_sample_import():
    """Xodimlar import uchun namuna Excel faylini yuklab olish"""
    try:
        from app.utils.excel_import import generate_staff_sample_file
        
        excel_file = generate_staff_sample_file()
        filename = f"xodimlar_import_namuna_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        
        return Response(
            excel_file,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            headers={'Content-Disposition': f'attachment; filename={filename}'}
        )
    except Exception as e:
        flash(f"Namuna fayl yaratishda xatolik: {str(e)}", 'error')
        return redirect(url_for('admin.import_all_users'))


@bp.route('/export/schedule')
@login_required
@admin_required
def export_schedule():
    """Admin uchun dars jadvalini Excel formatida yuklab olish"""
    try:
        from app.utils.excel_export import create_schedule_excel
    except ImportError:
        flash("Excel export funksiyasi ishlamayapti. Iltimos, 'pip install openpyxl' buyrug'ini bajaring.", 'error')
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
            flash("Sana formati noto'g'ri", 'error')
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
        query = query.join(Direction, Group.direction_id == Direction.id).filter(Direction.semester == semester)
    
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
def groups():
    faculty_id = request.args.get('faculty_id', type=int)
    search = request.args.get('search', '')
    
    query = Group.query
    if faculty_id:
        query = query.filter_by(faculty_id=faculty_id)
        
    if search:
        query = query.filter(Group.name.ilike(f'%{search}%'))
        
    groups_list = query.order_by(Group.name).all()
    faculties = Faculty.query.all()
    
    return render_template('admin/groups.html', groups=groups_list, faculties=faculties, current_faculty=faculty_id, search=search)


@bp.route('/groups/create', methods=['GET', 'POST'])
@login_required
@admin_required
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
        
        # Validatsiya
        if not name:
            flash("Guruh nomi majburiy", 'error')
            return redirect(url_for('admin.create_group', faculty_id=faculty_id))
        
        if not faculty_id:
            flash("Fakultet tanlash majburiy", 'error')
            return redirect(url_for('admin.create_group'))
        
        if not direction_id:
            flash("Yo'nalish tanlash majburiy", 'error')
            return redirect(url_for('admin.create_group', faculty_id=faculty_id))
        
        # Yo'nalish tekshiruvi
        direction = Direction.query.get(direction_id)
        if not direction or direction.faculty_id != faculty_id:
            flash("Noto'g'ri yo'nalish tanlandi", 'error')
            return redirect(url_for('admin.create_group', faculty_id=faculty_id))
        
        # Kurs, semestr va ta'lim shaklini yo'nalishdan olish
        if not course_year:
            course_year = direction.course_year
        if not semester:
            semester = direction.semester
        if not education_type:
            education_type = direction.education_type
        
        # Bir yo'nalishda bir xil guruh nomi bo'lishi mumkin emas
        if Group.query.filter_by(name=name.upper(), direction_id=direction_id).first():
            flash("Bu yo'nalishda bunday nomli guruh allaqachon mavjud", 'error')
            return render_template('admin/create_group.html', 
                                 faculties=Faculty.query.all(), 
                                 directions=Direction.query.filter_by(faculty_id=faculty_id).all() if faculty_id else Direction.query.all(),
                                 faculty_id=faculty_id,
                                 direction_id=direction_id)
        
        # Yo'nalishdan kurs, semestr va ta'lim shaklini olish
        description = request.form.get('description', '').strip()
        course_year = request.form.get('course_year', type=int) or direction.course_year
        education_type = request.form.get('education_type') or direction.education_type
        
        group = Group(
            name=name.upper(),
            faculty_id=faculty_id,
            course_year=course_year,
            education_type=education_type,  # Yo'nalishdan olinadi
            direction_id=direction_id,
            description=description if description else None
        )
        db.session.add(group)
        db.session.commit()
        
        flash("Guruh muvaffaqiyatli yaratildi", 'success')
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
            flash("Fakultet topilmadi", 'error')
            return redirect(url_for('admin.faculties'))
        
        # Fakultetdagi barcha kurslarni olish
        courses = db.session.query(Direction.course_year).filter_by(faculty_id=faculty_id).distinct().order_by(Direction.course_year).all()
        courses = [c[0] for c in courses]
        
        # Barcha yo'nalishlarni ma'lumotlar bazasi sifatida yuborish (JavaScript uchun)
        all_directions = Direction.query.filter_by(faculty_id=faculty_id).order_by(Direction.course_year, Direction.semester, Direction.name).all()
        
        return render_template('admin/create_group.html', 
                             faculties=faculties,
                             faculty=faculty,
                             faculty_id=faculty_id,
                             courses=courses,
                             all_directions=all_directions,
                             direction_id=direction_id)
    else:
        # Agar faculty_id berilmagan bo'lsa, barcha fakultetlar
        return render_template('admin/create_group.html', 
                             faculties=faculties,
                             faculty=None,
                             faculty_id=None,
                             courses=[],
                             all_directions=[],
                             direction_id=direction_id)


@bp.route('/groups/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_group(id):
    group = Group.query.get_or_404(id)
    
    if request.method == 'POST':
        # Guruh nomi, kurs, semestr, ta'lim shakli, yo'nalish va tavsifni o'zgartirish mumkin
        new_name = request.form.get('name').upper()
        course_year = request.form.get('course_year', type=int)
        semester = request.form.get('semester', type=int)
        education_type = request.form.get('education_type')
        direction_id = request.form.get('direction_id', type=int)
        description = request.form.get('description', '').strip()
        
        # Validatsiya
        if not course_year or not semester or not education_type or not direction_id:
            flash("Barcha maydonlar to'ldirilishi kerak", 'error')
            return redirect(url_for('admin.edit_group', id=group.id))
        
        # Yo'nalish tekshiruvi
        direction = Direction.query.get(direction_id)
        if not direction or direction.faculty_id != group.faculty_id:
            flash("Noto'g'ri yo'nalish tanlandi", 'error')
            return redirect(url_for('admin.edit_group', id=group.id))
        
        # Bir yo'nalishda bir xil guruh nomi bo'lishi mumkin emas
        # Agar nom yoki yo'nalish o'zgarganda tekshirish kerak
        if (new_name != group.name or direction_id != group.direction_id):
            existing_group = Group.query.filter_by(name=new_name, direction_id=direction_id).first()
            if existing_group and existing_group.id != group.id:
                flash("Bu yo'nalishda bunday nomli guruh allaqachon mavjud", 'error')
                return redirect(url_for('admin.edit_group', id=group.id))
        
        group.name = new_name
        group.direction_id = direction_id
        group.course_year = course_year
        group.education_type = education_type
        group.description = description if description else None
        
        db.session.commit()
        flash("Guruh yangilandi", 'success')
        # Yo'nalishga qaytish
        return redirect(url_for('admin.direction_detail', id=direction_id))
    
    # GET request - ma'lumotlarni tayyorlash
    faculty = group.faculty
    
    # Fakultetdagi barcha kurslarni olish
    courses = db.session.query(Direction.course_year).filter_by(faculty_id=faculty.id).distinct().order_by(Direction.course_year).all()
    courses = [c[0] for c in courses]
    
    # Barcha yo'nalishlarni ma'lumotlar bazasi sifatida yuborish (JavaScript uchun)
    all_directions = Direction.query.filter_by(faculty_id=faculty.id).order_by(Direction.course_year, Direction.semester, Direction.name).all()
    
    return render_template('admin/edit_group.html', 
                         group=group,
                         faculty=faculty,
                         courses=courses,
                         all_directions=all_directions)


@bp.route('/groups/<int:id>/students')
@login_required
@admin_required
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
def add_student_to_group(id):
    """Guruhga talaba qo'shish (admin uchun)"""
    group = Group.query.get_or_404(id)
    
    # Bir nechta talabani qo'shish
    student_ids = request.form.getlist('student_ids')
    student_ids = [int(sid) for sid in student_ids if sid]
    
    if not student_ids:
        flash("Hech qanday talaba tanlanmagan", 'error')
        return redirect(url_for('admin.group_students', id=id))
    
    added_count = 0
    for student_id in student_ids:
        student = User.query.get(student_id)
        if student and student.role == 'student' and student.group_id is None:
            student.group_id = group.id
            added_count += 1
    
    db.session.commit()
    
    if added_count > 0:
        flash(f"{added_count} ta talaba guruhga qo'shildi", 'success')
    else:
        flash("Hech qanday talaba qo'shilmadi. Tanlangan talabalar allaqachon boshqa guruhga biriktirilgan bo'lishi mumkin", 'warning')
    
    return redirect(url_for('admin.group_students', id=id))

@bp.route('/groups/<int:id>/remove-students', methods=['POST'])
@login_required
@admin_required
def remove_students_from_group(id):
    """Bir nechta talabani bir vaqtning o'zida guruhdan chiqarish (admin uchun)"""
    group = Group.query.get_or_404(id)
    
    ids = request.form.getlist('remove_student_ids')
    student_ids = [int(sid) for sid in ids if sid]
    
    if not student_ids:
        flash("Hech qanday talaba tanlanmagan", 'error')
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
        flash(f"{count} ta talaba guruhdan chiqarildi", 'success')
    else:
        flash("Hech qanday talaba guruhdan chiqarilmadi", 'warning')
    
    return redirect(url_for('admin.group_students', id=id))

@bp.route('/groups/<int:id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_group(id):
    group = Group.query.get_or_404(id)
    faculty_id = group.faculty_id
    
    # Guruhda talabalar borligini tekshirish
    if group.students.count() > 0:
        flash("Guruhda talabalar bor. O'chirish mumkin emas", 'error')
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
        flash("Guruh o'chirildi", 'success')
    
    # Fakultet detail sahifasiga qaytish
    if request.args.get('from_faculty'):
        return redirect(url_for('admin.faculty_detail', id=faculty_id))
    return redirect(url_for('admin.groups'))


# ==================== YO'NALISHLAR ====================
@bp.route('/directions/create', methods=['GET', 'POST'])
@login_required
@admin_required
def create_direction():
    """Yangi yo'nalish yaratish (admin uchun)"""
    faculty_id = request.args.get('faculty_id', type=int)
    
    if request.method == 'POST':
        name = request.form.get('name')
        code = request.form.get('code', '').upper()
        description = request.form.get('description')
        faculty_id = request.form.get('faculty_id', type=int)
        course_year = request.form.get('course_year', type=int)
        semester = request.form.get('semester', type=int)
        education_type = request.form.get('education_type', 'kunduzgi')
        enrollment_year = request.form.get('enrollment_year', type=int)
        
        # Validatsiya
        if not name or not code:
            flash("Yo'nalish nomi va kodi majburiy", 'error')
            return render_template('admin/create_direction.html', 
                                 faculties=Faculty.query.all(),
                                 faculty_id=faculty_id)
        
        if not faculty_id:
            flash("Fakultet tanlash majburiy", 'error')
            return render_template('admin/create_direction.html', 
                                 faculties=Faculty.query.all(),
                                 faculty_id=faculty_id)
        
        if not course_year or course_year < 1 or course_year > 5:
            flash("Kurs 1-5 oralig'ida bo'lishi kerak", 'error')
            return render_template('admin/create_direction.html', 
                                 faculties=Faculty.query.all(),
                                 faculty_id=faculty_id)
        
        if not semester or semester < 1 or semester > 10:
            flash("Semestr 1-10 oralig'ida bo'lishi kerak", 'error')
            return render_template('admin/create_direction.html', 
                                 faculties=Faculty.query.all(),
                                 faculty_id=faculty_id)
        
        if not enrollment_year or enrollment_year < 1900 or enrollment_year > 2100:
            flash("Qabul yili to'g'ri kiriting (1900-2100)", 'error')
            return render_template('admin/create_direction.html', 
                                 faculties=Faculty.query.all(),
                                 faculty_id=faculty_id)
        
        # Ta'lim shakli validatsiyasi
        valid_education_types = ['kunduzgi', 'sirtqi', 'masofaviy', 'kechki']
        if education_type not in valid_education_types:
            flash("Noto'g'ri ta'lim shakli tanlandi", 'error')
            return render_template('admin/create_direction.html', 
                                 faculties=Faculty.query.all(),
                                 faculty_id=faculty_id)
        
        # Kod takrorlanmasligini tekshirish (fakultet, kurs, semestr va ta'lim shakli bo'yicha)
        existing = Direction.query.filter_by(
            code=code, 
            faculty_id=faculty_id,
            course_year=course_year,
            semester=semester,
            education_type=education_type
        ).first()
        
        if existing:
            flash("Bu kod, kurs, semestr va ta'lim shakli bilan yo'nalish allaqachon mavjud", 'error')
            return render_template('admin/create_direction.html', 
                                 faculties=Faculty.query.all(),
                                 faculty_id=faculty_id)
        
        direction = Direction(
            name=name,
            code=code,
            description=description,
            faculty_id=faculty_id,
            course_year=course_year,
            semester=semester,
            education_type=education_type,
            enrollment_year=enrollment_year
        )
        db.session.add(direction)
        db.session.commit()
        
        flash("Yo'nalish muvaffaqiyatli yaratildi", 'success')
        # Fakultet detail sahifasiga qaytish
        if faculty_id:
            return redirect(url_for('admin.faculty_detail', id=faculty_id))
        return redirect(url_for('admin.directions'))
    
    return render_template('admin/create_direction.html', 
                         faculties=Faculty.query.all(),
                         faculty_id=faculty_id)


@bp.route('/directions/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_direction(id):
    """Yo'nalishni tahrirlash (admin uchun)"""
    direction = Direction.query.get_or_404(id)
    
    if request.method == 'POST':
        direction.name = request.form.get('name')
        direction.code = request.form.get('code', '').upper()
        direction.description = request.form.get('description')
        direction.faculty_id = request.form.get('faculty_id', type=int)
        course_year = request.form.get('course_year', type=int)
        semester = request.form.get('semester', type=int)
        education_type = request.form.get('education_type', 'kunduzgi')
        enrollment_year = request.form.get('enrollment_year', type=int)
        
        # Validatsiya
        if not course_year or course_year < 1 or course_year > 5:
            flash("Kurs 1-5 oralig'ida bo'lishi kerak", 'error')
            return render_template('admin/edit_direction.html', 
                                 direction=direction,
                                 faculties=Faculty.query.all())
        
        if not semester or semester < 1 or semester > 10:
            flash("Semestr 1-10 oralig'ida bo'lishi kerak", 'error')
            return render_template('admin/edit_direction.html', 
                                 direction=direction,
                                 faculties=Faculty.query.all())
        
        if not enrollment_year or enrollment_year < 1900 or enrollment_year > 2100:
            flash("Qabul yili to'g'ri kiriting (1900-2100)", 'error')
            return render_template('admin/edit_direction.html', 
                                 direction=direction,
                                 faculties=Faculty.query.all())
        
        # Ta'lim shakli validatsiyasi
        valid_education_types = ['kunduzgi', 'sirtqi', 'masofaviy', 'kechki']
        if education_type not in valid_education_types:
            flash("Noto'g'ri ta'lim shakli tanlandi", 'error')
            return render_template('admin/edit_direction.html', 
                                 direction=direction,
                                 faculties=Faculty.query.all())
        
        # Kod takrorlanmasligini tekshirish
        existing = Direction.query.filter(
            Direction.code == direction.code,
            Direction.faculty_id == direction.faculty_id,
            Direction.course_year == course_year,
            Direction.semester == semester,
            Direction.education_type == education_type,
            Direction.id != id
        ).first()
        
        if existing:
            flash("Bu kod, kurs, semestr va ta'lim shakli bilan yo'nalish allaqachon mavjud", 'error')
            return render_template('admin/edit_direction.html', 
                                 direction=direction,
                                 faculties=Faculty.query.all())
        
        direction.course_year = course_year
        direction.semester = semester
        direction.education_type = education_type
        direction.enrollment_year = enrollment_year
        
        db.session.commit()
        flash("Yo'nalish yangilandi", 'success')
        # Fakultet detail sahifasiga qaytish
        if request.args.get('faculty_id'):
            return redirect(url_for('admin.faculty_detail', id=direction.faculty_id))
        return redirect(url_for('admin.directions'))
    
    return render_template('admin/edit_direction.html', 
                         direction=direction,
                         faculties=Faculty.query.all())


@bp.route('/directions/<int:id>/delete', methods=['POST'])
@login_required
@admin_required
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
            flash(f"Yo'nalishda {len(groups)} ta guruh va {total_students} ta talaba mavjud. O'chirish mumkin emas", 'error')
        else:
            flash(f"Yo'nalishda {len(groups)} ta guruh mavjud. Avval guruhlarni o'chiring yoki boshqa yo'nalishga o'tkazing", 'error')
    else:
        db.session.delete(direction)
        db.session.commit()
        flash("Yo'nalish o'chirildi", 'success')
    
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
def directions():
    """Admin uchun barcha yo'nalishlar - fakultetlar sahifasiga redirect"""
    return redirect(url_for('admin.faculties'))

@bp.route('/students/create', methods=['GET', 'POST'])
@login_required
@admin_required
def create_student():
    """Admin uchun yangi talaba yaratish"""
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        full_name = request.form.get('full_name', '').strip()
        passport_number = request.form.get('passport_number', '').strip()
        phone = request.form.get('phone', '').strip()
        student_id = request.form.get('student_id', '').strip()
        pinfl = request.form.get('pinfl', '').strip()
        birth_date = request.form.get('birth_date', '').strip()
        description = request.form.get('description', '').strip()
        
        # Talaba ID majburiy
        if not student_id:
            flash("Talaba ID majburiy maydon", 'error')
            return render_template('admin/create_student.html')
        
        if User.query.filter_by(student_id=student_id).first():
            flash("Bu talaba ID allaqachon mavjud", 'error')
            return render_template('admin/create_student.html')
        
        # Pasport seriyasi va raqami majburiy
        if not passport_number:
            flash("Pasport seriyasi va raqami majburiy", 'error')
            return render_template('admin/create_student.html')
        
        # Email ixtiyoriy, lekin agar kiritilgan bo'lsa, unikallikni tekshirish
        if email:
            if User.query.filter_by(email=email).first():
                flash("Bu email allaqachon mavjud", 'error')
                return render_template('admin/create_student.html')
        
        # Pasport raqamini katta harfga o'zgartirish
        passport_number = passport_number.upper()
        
        # Tug'ilgan sanani parse qilish (yyyy-mm-dd)
        parsed_birth_date = None
        if birth_date:
            try:
                parsed_birth_date = datetime.strptime(birth_date, '%Y-%m-%d').date()
            except ValueError:
                flash("Tug'ilgan sana noto'g'ri formatda (yyyy-mm-dd)", 'error')
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
            description=description.strip() if description and description.strip() else None
        )
        
        # Email maydonini alohida o'rnatish (agar bo'sh bo'lsa, o'rnatmaymiz)
        if email_value:
            student.email = email_value
        
        # Parolni pasport raqamiga o'rnatish
        if passport_number:
            student.set_password(passport_number)
        else:
            student.set_password('student123')
        
        db.session.add(student)
        
        # Commit qilish va agar email NOT NULL xatolik bo'lsa, email maydonini bo'sh qatorga o'zgartirish
        try:
            db.session.commit()
        except Exception as e:
            error_str = str(e).lower()
            if 'email' in error_str and ('not null' in error_str or 'constraint' in error_str):
                # Database'da email NOT NULL bo'lsa, bo'sh qator qo'yamiz
                db.session.rollback()
                student.email = ''  # Bo'sh qator (database NOT NULL constraint uchun)
                db.session.add(student)
                db.session.commit()
            else:
                raise
        
        flash(f"{student.full_name} muvaffaqiyatli yaratildi", 'success')
        return redirect(url_for('admin.students'))
    
    return render_template('admin/create_student.html')


@bp.route('/students/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_student(id):
    """Admin uchun talabani tahrirlash"""
    student = User.query.get_or_404(id)
    if student.role != 'student':
        flash("Bu foydalanuvchi talaba emas", 'error')
        return redirect(url_for('admin.students'))
    
    if request.method == 'POST':
        student_id = request.form.get('student_id', '').strip()
        full_name = request.form.get('full_name', '').strip()
        passport_number = request.form.get('passport_number', '').strip()
        phone = request.form.get('phone', '').strip()
        email = request.form.get('email', '').strip()
        pinfl = request.form.get('pinfl', '').strip()
        birth_date_str = request.form.get('birth_date', '').strip()
        description = request.form.get('description', '').strip()
        
        # Talaba ID majburiy
        if not student_id:
            flash("Talaba ID majburiy maydon", 'error')
            return render_template('admin/edit_student.html', student=student)
        
        # Talaba ID unikalligi (boshqa talabada bo'lmasligi kerak)
        existing_student = User.query.filter_by(student_id=student_id).first()
        if existing_student and existing_student.id != student.id:
            flash("Bu talaba ID allaqachon boshqa talabada mavjud", 'error')
            return render_template('admin/edit_student.html', student=student)
        
        # Pasport seriyasi va raqami majburiy
        if not passport_number:
            flash("Pasport seriyasi va raqami majburiy", 'error')
            return render_template('admin/edit_student.html', student=student)
        
        # Email ixtiyoriy, lekin agar kiritilgan bo'lsa, unikallikni tekshirish
        if email:
            existing_student_with_email = User.query.filter_by(email=email).first()
            if existing_student_with_email and existing_student_with_email.id != student.id:
                flash("Bu email allaqachon boshqa talabada mavjud", 'error')
                return render_template('admin/edit_student.html', student=student)
        
        # Pasport raqamini katta harfga o'zgartirish
        passport_number = passport_number.upper()
        
        # Tug'ilgan sanani parse qilish (yyyy-mm-dd)
        if birth_date_str:
            try:
                student.birth_date = datetime.strptime(birth_date_str, '%Y-%m-%d').date()
            except ValueError:
                flash("Tug'ilgan sana noto'g'ri formatda (yyyy-mm-dd)", 'error')
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
        
        db.session.commit()
        flash(f"{student.full_name} ma'lumotlari yangilandi", 'success')
        return redirect(url_for('admin.students'))
    
    return render_template('admin/edit_student.html', student=student)


@bp.route('/students')
@login_required
@admin_required
def students():
    """Admin uchun barcha talabalar"""
    from app.models import Direction
    
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '')
    faculty_id = request.args.get('faculty', type=int)
    course_year = request.args.get('course', type=int)
    semester = request.args.get('semester', type=int)
    education_type = request.args.get('education_type', '')
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
    
    # Filtrlash
    if group_id:
        query = query.filter(User.group_id == group_id)
    elif direction_id:
        # Yo'nalish bo'yicha filtrlash
        group_ids = [g.id for g in Group.query.filter_by(direction_id=direction_id).all()]
        if group_ids:
            query = query.filter(User.group_id.in_(group_ids))
        else:
            query = query.filter(User.id == -1)  # Hech narsa topilmaydi
    elif education_type:
        # Ta'lim shakli bo'yicha filtrlash
        group_ids = [g.id for g in Group.query.filter_by(education_type=education_type).all()]
        if group_ids:
            query = query.filter(User.group_id.in_(group_ids))
        else:
            query = query.filter(User.id == -1)
    elif semester:
        # Semestr bo'yicha filtrlash
        if faculty_id:
            # Fakultet bo'yicha yo'nalishlarni topish
            direction_ids = [d.id for d in Direction.query.filter_by(
                faculty_id=faculty_id, 
                semester=semester
            ).all()]
            if direction_ids:
                group_ids = [g.id for g in Group.query.filter(Group.direction_id.in_(direction_ids)).all()]
                if group_ids:
                    query = query.filter(User.group_id.in_(group_ids))
                else:
                    query = query.filter(User.id == -1)
            else:
                query = query.filter(User.id == -1)
        else:
            # Barcha fakultetlar bo'yicha
            direction_ids = [d.id for d in Direction.query.filter_by(semester=semester).all()]
            if direction_ids:
                group_ids = [g.id for g in Group.query.filter(Group.direction_id.in_(direction_ids)).all()]
                if group_ids:
                    query = query.filter(User.group_id.in_(group_ids))
                else:
                    query = query.filter(User.id == -1)
            else:
                query = query.filter(User.id == -1)
    elif course_year:
        # Kurs bo'yicha filtrlash
        if faculty_id:
            group_ids = [g.id for g in Group.query.filter_by(
                faculty_id=faculty_id,
                course_year=course_year
            ).all()]
            if group_ids:
                query = query.filter(User.group_id.in_(group_ids))
            else:
                query = query.filter(User.id == -1)
        else:
            group_ids = [g.id for g in Group.query.filter_by(course_year=course_year).all()]
            if group_ids:
                query = query.filter(User.group_id.in_(group_ids))
            else:
                query = query.filter(User.id == -1)
    elif faculty_id:
        # Fakultet bo'yicha filtrlash
        group_ids = [g.id for g in Group.query.filter_by(faculty_id=faculty_id).all()]
        if group_ids:
            query = query.filter(User.group_id.in_(group_ids))
        else:
            query = query.filter(User.id == -1)
    
    students = query.order_by(User.full_name).paginate(page=page, per_page=50, error_out=False)
    
    # Filtrlar uchun ma'lumotlar
    groups = Group.query.order_by(Group.name).all()
    faculties = Faculty.query.order_by(Faculty.name).all()
    directions = Direction.query.order_by(Direction.code, Direction.name).all()
    
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
        for course in range(1, 5):
            semesters_set = set()
            for direction in Direction.query.filter_by(faculty_id=faculty.id, course_year=course).all():
                semesters_set.add(direction.semester)
            if semesters_set:
                faculty_course_semesters[faculty.id][course] = sorted(list(semesters_set))
    
    # Fakultet + Kurs + Semestr -> Ta'lim shakllari
    faculty_course_semester_education_types = {}
    for faculty in faculties:
        faculty_course_semester_education_types[faculty.id] = {}
        for course in range(1, 5):
            faculty_course_semester_education_types[faculty.id][course] = {}
            for direction in Direction.query.filter_by(faculty_id=faculty.id, course_year=course).all():
                semester = direction.semester
                if semester not in faculty_course_semester_education_types[faculty.id][course]:
                    faculty_course_semester_education_types[faculty.id][course][semester] = set()
                faculty_course_semester_education_types[faculty.id][course][semester].add(direction.education_type)
            # Set'larni list'ga o'tkazish
            for semester in faculty_course_semester_education_types[faculty.id][course]:
                faculty_course_semester_education_types[faculty.id][course][semester] = sorted(list(faculty_course_semester_education_types[faculty.id][course][semester]))
    
    # Fakultet + Kurs + Semestr + Ta'lim shakli -> Yo'nalishlar
    faculty_course_semester_education_directions = {}
    for faculty in faculties:
        faculty_course_semester_education_directions[faculty.id] = {}
        for course in range(1, 5):
            faculty_course_semester_education_directions[faculty.id][course] = {}
            for direction in Direction.query.filter_by(faculty_id=faculty.id, course_year=course).all():
                semester = direction.semester
                education_type = direction.education_type
                if semester not in faculty_course_semester_education_directions[faculty.id][course]:
                    faculty_course_semester_education_directions[faculty.id][course][semester] = {}
                if education_type not in faculty_course_semester_education_directions[faculty.id][course][semester]:
                    faculty_course_semester_education_directions[faculty.id][course][semester][education_type] = []
                faculty_course_semester_education_directions[faculty.id][course][semester][education_type].append({
                    'id': direction.id,
                    'code': direction.code,
                    'name': direction.name
                })
            # Yo'nalishlarni tartiblash
            for semester in faculty_course_semester_education_directions[faculty.id][course]:
                for education_type in faculty_course_semester_education_directions[faculty.id][course][semester]:
                    faculty_course_semester_education_directions[faculty.id][course][semester][education_type].sort(key=lambda x: (x['code'], x['name']))
    
    # Yo'nalish -> Guruhlar
    direction_groups = {}
    for direction in directions:
        direction_groups[direction.id] = []
        for group in Group.query.filter_by(direction_id=direction.id).all():
            direction_groups[direction.id].append({
                'id': group.id,
                'name': group.name
            })
        direction_groups[direction.id].sort(key=lambda x: x['name'])
    
    # Teskari filtrlash uchun qo'shimcha ma'lumotlar
    # Kurs -> Fakultetlar (kurs tanlanganda fakultetlarni filtrlash)
    course_faculties = {}
    for course in range(1, 5):
        faculties_set = set()
        for group in Group.query.filter_by(course_year=course).all():
            if group.faculty_id:
                faculties_set.add(group.faculty_id)
        course_faculties[course] = sorted(list(faculties_set))
    
    # Semestr -> Kurslar (semestr tanlanganda kurslarni filtrlash)
    semester_courses = {}
    for direction in directions:
        semester = direction.semester
        course = direction.course_year
        if semester not in semester_courses:
            semester_courses[semester] = set()
        semester_courses[semester].add(course)
    for semester in semester_courses:
        semester_courses[semester] = sorted(list(semester_courses[semester]))
    
    # Fakultet + Semestr -> Kurslar
    faculty_semester_courses = {}
    for faculty in faculties:
        faculty_semester_courses[faculty.id] = {}
        for direction in Direction.query.filter_by(faculty_id=faculty.id).all():
            semester = direction.semester
            course = direction.course_year
            if semester not in faculty_semester_courses[faculty.id]:
                faculty_semester_courses[faculty.id][semester] = set()
            faculty_semester_courses[faculty.id][semester].add(course)
        for semester in faculty_semester_courses[faculty.id]:
            faculty_semester_courses[faculty.id][semester] = sorted(list(faculty_semester_courses[faculty.id][semester]))
    
    # Ta'lim shakli -> Semestrlar (ta'lim shakli tanlanganda semestrlarni filtrlash)
    education_type_semesters = {}
    for direction in directions:
        education_type = direction.education_type
        semester = direction.semester
        if education_type not in education_type_semesters:
            education_type_semesters[education_type] = set()
        education_type_semesters[education_type].add(semester)
    for et in education_type_semesters:
        education_type_semesters[et] = sorted(list(education_type_semesters[et]))
    
    # Fakultet + Kurs + Ta'lim shakli -> Semestrlar
    faculty_course_education_semesters = {}
    for faculty in faculties:
        faculty_course_education_semesters[faculty.id] = {}
        for course in range(1, 5):
            faculty_course_education_semesters[faculty.id][course] = {}
            for direction in Direction.query.filter_by(faculty_id=faculty.id, course_year=course).all():
                education_type = direction.education_type
                semester = direction.semester
                if education_type not in faculty_course_education_semesters[faculty.id][course]:
                    faculty_course_education_semesters[faculty.id][course][education_type] = set()
                faculty_course_education_semesters[faculty.id][course][education_type].add(semester)
            for et in faculty_course_education_semesters[faculty.id][course]:
                faculty_course_education_semesters[faculty.id][course][et] = sorted(list(faculty_course_education_semesters[faculty.id][course][et]))
    
    # Yo'nalish -> Ta'lim shakllari (yo'nalish tanlanganda ta'lim shakllarini filtrlash)
    direction_education_types = {}
    for direction in directions:
        direction_education_types[direction.id] = direction.education_type
    
    # Fakultet + Kurs + Semestr -> Ta'lim shakllari (ta'lim shakli tanlashda)
    # (Bu allaqachon faculty_course_semester_education_types da mavjud)
    
    # Fakultet + Kurs + Semestr + Ta'lim shakli -> Yo'nalishlar (yo'nalish tanlashda)
    # (Bu allaqachon faculty_course_semester_education_directions da mavjud)
    
    # Fakultet + Kurs -> Guruhlar (guruh tanlashda)
    faculty_course_groups = {}
    for faculty in faculties:
        faculty_course_groups[faculty.id] = {}
        for course in range(1, 5):
            faculty_course_groups[faculty.id][course] = []
            for group in Group.query.filter_by(faculty_id=faculty.id, course_year=course).all():
                faculty_course_groups[faculty.id][course].append({
                    'id': group.id,
                    'name': group.name
                })
            faculty_course_groups[faculty.id][course].sort(key=lambda x: x['name'])
    
    # Fakultet + Kurs + Semestr -> Guruhlar
    faculty_course_semester_groups = {}
    for faculty in faculties:
        faculty_course_semester_groups[faculty.id] = {}
        for course in range(1, 5):
            faculty_course_semester_groups[faculty.id][course] = {}
            for direction in Direction.query.filter_by(faculty_id=faculty.id, course_year=course).all():
                semester = direction.semester
                if semester not in faculty_course_semester_groups[faculty.id][course]:
                    faculty_course_semester_groups[faculty.id][course][semester] = []
                for group in Group.query.filter_by(direction_id=direction.id).all():
                    faculty_course_semester_groups[faculty.id][course][semester].append({
                        'id': group.id,
                        'name': group.name
                    })
            for semester in faculty_course_semester_groups[faculty.id][course]:
                faculty_course_semester_groups[faculty.id][course][semester].sort(key=lambda x: x['name'])
    
    # Fakultet + Kurs + Semestr + Ta'lim shakli -> Guruhlar
    faculty_course_semester_education_groups = {}
    for faculty in faculties:
        faculty_course_semester_education_groups[faculty.id] = {}
        for course in range(1, 5):
            faculty_course_semester_education_groups[faculty.id][course] = {}
            for direction in Direction.query.filter_by(faculty_id=faculty.id, course_year=course).all():
                semester = direction.semester
                education_type = direction.education_type
                if semester not in faculty_course_semester_education_groups[faculty.id][course]:
                    faculty_course_semester_education_groups[faculty.id][course][semester] = {}
                if education_type not in faculty_course_semester_education_groups[faculty.id][course][semester]:
                    faculty_course_semester_education_groups[faculty.id][course][semester][education_type] = []
                for group in Group.query.filter_by(direction_id=direction.id).all():
                    faculty_course_semester_education_groups[faculty.id][course][semester][education_type].append({
                        'id': group.id,
                        'name': group.name
                    })
            for semester in faculty_course_semester_education_groups[faculty.id][course]:
                for et in faculty_course_semester_education_groups[faculty.id][course][semester]:
                    faculty_course_semester_education_groups[faculty.id][course][semester][et].sort(key=lambda x: x['name'])
    
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
            'faculty_id': direction.faculty_id,
            'course_year': direction.course_year,
            'semester': direction.semester,
            'education_type': direction.education_type
        }
    
    # Kurslar ro'yxati (1-4)
    courses = list(range(1, 5))
    
    # Semestrlarni olish
    semesters = sorted(set([d.semester for d in Direction.query.all()]))
    
    # Ta'lim shakllari
    education_types = sorted(set([g.education_type for g in Group.query.filter(Group.education_type != None).all() if g.education_type]))
    
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
                         groups_json=groups_json)

@bp.route('/students/<int:id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_student(id):
    """Admin uchun talabani o'chirish"""
    student = User.query.get_or_404(id)
    if student.role != 'student':
        flash("Bu foydalanuvchi talaba emas", 'error')
        return redirect(url_for('admin.students'))
    
    student_name = student.full_name
    
    # Talabaning to'lovlarini o'chirish
    StudentPayment.query.filter_by(student_id=student.id).delete()
    
    # Talabani o'chirish
    db.session.delete(student)
    db.session.commit()
    flash(f"{student_name} o'chirildi", 'success')
    return redirect(url_for('admin.students'))

@bp.route('/students/<int:id>/reset-password', methods=['POST'])
@login_required
@admin_required
def reset_student_password(id):
    """Admin uchun talaba parolini boshlang'ich holatga qaytarish (pasport raqami)"""
    student = User.query.get_or_404(id)
    if student.role != 'student':
        flash("Bu foydalanuvchi talaba emas", 'error')
        return redirect(url_for('admin.students'))
    
    # Parolni pasport seriya raqamiga qaytarish
    if not student.passport_number:
        flash("Bu talabada pasport seriya raqami mavjud emas", 'error')
        return redirect(url_for('admin.students'))
    
    new_password = student.passport_number
    student.set_password(new_password)
    db.session.commit()
    flash(f"{student.full_name} paroli boshlang'ich holatga qaytarildi. Yangi parol: {new_password}", 'success')
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
        # Guruhga biriktirilgan fanlar (TeacherSubject orqali)
        assignments = TeacherSubject.query.filter_by(group_id=group_id).all()
        subjects_data = {}
        for a in assignments:
            if a.subject_id not in subjects_data:
                subjects_data[a.subject_id] = {
                    'id': a.subject.id,
                    'name': a.subject.name,
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
    start_weekday = calendar.monthrange(year, month)[0]
    
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
    
    start_code = int(f"{year}{month:02d}01")
    end_code = int(f"{year}{month:02d}{days_in_month:02d}")
    
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
        fid = g.faculty_id
        if fid not in faculty_courses: continue
        
        c = g.course_year
        if not c: continue
        
        faculty_courses[fid].add(c)
        
        if g.direction:
            d = g.direction
            s = d.semester
            
            if c not in faculty_course_semesters[fid]:
                faculty_course_semesters[fid][c] = set()
            faculty_course_semesters[fid][c].add(s)
            
            if s not in faculty_course_semester_education_directions[fid]:
                faculty_course_semester_education_directions[fid][s] = {}
            if c not in faculty_course_semester_education_directions[fid][s]:
                faculty_course_semester_education_directions[fid][s][c] = {}
            
            etype = d.education_type or 'kunduzgi'
            if etype not in faculty_course_semester_education_directions[fid][s][c]:
                faculty_course_semester_education_directions[fid][s][c][etype] = []
            
            if not any(item['id'] == d.id for item in faculty_course_semester_education_directions[fid][s][c][etype]):
                faculty_course_semester_education_directions[fid][s][c][etype].append({
                    'id': d.id,
                    'name': d.name,
                    'code': d.code,
                    'enrollment_year': d.enrollment_year,
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


    # Global lists for independent filters
    from sqlalchemy import distinct
    all_courses = [c[0] for c in db.session.query(distinct(Group.course_year)).filter(Group.course_year.isnot(None)).order_by(Group.course_year).all()]
    all_semesters = [s[0] for s in db.session.query(distinct(Direction.semester)).filter(Direction.semester.isnot(None)).order_by(Direction.semester).all()]
    all_directions = Direction.query.order_by(Direction.name).all()
    all_groups = Group.query.order_by(Group.name).all()

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
        # Join Direction if needed (already joined Group)
        query = query.join(Direction, Group.direction_id == Direction.id).filter(Direction.semester == semester)
        
    schedules = query.order_by(Schedule.day_of_week, Schedule.start_time).all()
    
    schedule_by_day = {i: [] for i in range(1, days_in_month + 1)}
    for s in schedules:
        try:
            code_str = str(s.day_of_week)
            day = int(code_str[-2:])
        except (TypeError, ValueError):
            continue
        if 1 <= day <= days_in_month:
            schedule_by_day[day].append(s)
    
    for day in schedule_by_day:
        schedule_by_day[day].sort(key=lambda x: x.start_time or '')
    
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
                         days_in_month=days_in_month,
                         start_weekday=start_weekday,
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
        fid = g.faculty_id
        if fid not in faculty_courses: continue
        
        c = g.course_year
        if not c: continue
        
        faculty_courses[fid].add(c)
        
        if g.direction:
            d = g.direction
            s = d.semester
            
            if c not in faculty_course_semesters[fid]:
                faculty_course_semesters[fid][c] = set()
            faculty_course_semesters[fid][c].add(s)
            
            if s not in faculty_course_semester_education_directions[fid]:
                faculty_course_semester_education_directions[fid][s] = {}
            if c not in faculty_course_semester_education_directions[fid][s]:
                faculty_course_semester_education_directions[fid][s][c] = {}
            
            etype = d.education_type or 'kunduzgi'
            if etype not in faculty_course_semester_education_directions[fid][s][c]:
                faculty_course_semester_education_directions[fid][s][c][etype] = []
            
            if not any(item['id'] == d.id for item in faculty_course_semester_education_directions[fid][s][c][etype]):
                faculty_course_semester_education_directions[fid][s][c][etype].append({
                    'id': d.id,
                    'name': d.name,
                    'code': d.code,
                    'enrollment_year': d.enrollment_year,
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
                flash("Sana noto'g'ri formatda", 'error')
                return redirect(url_for('admin.create_schedule'))
        
        if not date_code:
            flash("Sana tanlanishi shart", 'error')
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
            flash("Ushbu o'qituvchiga bu guruh va fan uchun dars turi biriktirilmagan", 'error')
            return redirect(url_for('admin.create_schedule'))
        
        # Dars turlarini yig'ish
        types_map = {
            'maruza': 'Ma\'ruza',
            'lecture': 'Ma\'ruza',
            'amaliyot': 'Amaliyot',
            'practice': 'Amaliyot',
            'lab': 'Laboratoriya',
            'seminar': 'Seminar'
        }
        found_types = sorted(list(set([types_map.get(a.lesson_type, a.lesson_type.capitalize()) for a in assignments if a.lesson_type])))
        lesson_type_display = "/".join(found_types) if found_types else 'Ma\'ruza'
        
        # Takrorlanishni tekshirish
        existing = Schedule.query.filter_by(
            group_id=group_id,
            day_of_week=date_code,
            start_time=start_time
        ).first()
        
        if existing:
            flash(f"Bu vaqtda ({start_time}) guruhda dars allaqachon mavjud: {existing.subject.name}", 'warning')
            return redirect(url_for('admin.schedule', year=parsed_date.year, month=parsed_date.month, group=group_id))

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
        
        flash("Dars jadvaliga qo'shildi", 'success')
            
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
        fid = g.faculty_id
        if fid not in faculty_courses: continue
        
        c = g.course_year
        if not c: continue
        
        faculty_courses[fid].add(c)
        
        if g.direction:
            d = g.direction
            s = d.semester
            
            if c not in faculty_course_semesters[fid]:
                faculty_course_semesters[fid][c] = set()
            faculty_course_semesters[fid][c].add(s)
            
            if s not in faculty_course_semester_education_directions[fid]:
                faculty_course_semester_education_directions[fid][s] = {}
            if c not in faculty_course_semester_education_directions[fid][s]:
                faculty_course_semester_education_directions[fid][s][c] = {}
            
            etype = d.education_type or 'kunduzgi'
            if etype not in faculty_course_semester_education_directions[fid][s][c]:
                faculty_course_semester_education_directions[fid][s][c][etype] = []
            
            if not any(item['id'] == d.id for item in faculty_course_semester_education_directions[fid][s][c][etype]):
                faculty_course_semester_education_directions[fid][s][c][etype].append({
                    'id': d.id,
                    'name': d.name,
                    'code': d.code,
                    'enrollment_year': d.enrollment_year,
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
    current_semester = current_direction.semester if current_direction else None
    
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
                flash("Sana noto'g'ri formatda. Iltimos, kalendardan tanlang.", 'error')
                return redirect(url_for('admin.edit_schedule', id=id))
        
        if not date_code:
            flash("Sana tanlanishi shart.", 'error')
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
            'lecture': 'Ma\'ruza',
            'amaliyot': 'Amaliyot',
            'practice': 'Amaliyot',
            'lab': 'Laboratoriya',
            'seminar': 'Seminar'
        }
        found_types = sorted(list(set([types_map.get(a.lesson_type, str(a.lesson_type).capitalize()) for a in assignments if a.lesson_type])))
        schedule.lesson_type = "/".join(found_types)[:20] if found_types else 'Ma\'ruza'

        
        db.session.commit()
        
        flash("Dars jadvali yangilandi", 'success')
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
def delete_schedule(id):
    """Admin uchun dars jadvalini o'chirish"""
    schedule = Schedule.query.get_or_404(id)
    
    db.session.delete(schedule)
    db.session.commit()
    flash("Jadval o'chirildi", 'success')
    
    return redirect(url_for('admin.schedule'))
