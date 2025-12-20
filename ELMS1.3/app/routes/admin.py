from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, send_file, Response, session
from flask_login import login_required, current_user
from app.models import User, Faculty, Group, Subject, TeacherSubject, Assignment, Direction, GradeScale, Schedule, UserRole
from app import db
from functools import wraps
from datetime import datetime

from app.utils.excel_import import import_students_from_excel, import_directions_from_excel, generate_sample_file, import_staff_from_excel, generate_staff_sample_file
from app.utils.excel_export import create_all_users_excel
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
        'total_teachers': User.query.filter_by(role='teacher').count(),
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
        query = query.filter_by(role=role)
    
    if search:
        query = query.filter(
            (User.full_name.ilike(f'%{search}%')) |
            (User.email.ilike(f'%{search}%'))
        )
    
    users = query.order_by(User.created_at.desc()).paginate(page=page, per_page=20)
    
    stats = {
        'total': User.query.count(),
        'admins': User.query.filter_by(role='admin').count(),
        'deans': User.query.filter_by(role='dean').count(),
        'teachers': User.query.filter_by(role='teacher').count(),
        'students': User.query.filter_by(role='student').count(),
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
    
    if request.method == 'POST':
        email = request.form.get('email')
        # Email ixtiyoriy, lekin agar kiritilgan bo'lsa, unikallikni tekshirish
        if email:
            existing_user_with_email = User.query.filter_by(email=email).first()
            if existing_user_with_email and existing_user_with_email.id != user.id:
                flash("Bu email allaqachon boshqa foydalanuvchida mavjud", 'error')
                return render_template('admin/edit_user.html', user=user, faculties=faculties, groups=groups)
        user.email = email if email else None
        user.full_name = request.form.get('full_name')
        user.role = request.form.get('role')
        user.is_active = request.form.get('is_active') == 'on'
        user.phone = request.form.get('phone')
        
        # Rolga qarab qo'shimcha ma'lumotlar
        if user.role == 'student':
            user.student_id = request.form.get('student_id')
            user.group_id = request.form.get('group_id', type=int)
            user.enrollment_year = request.form.get('enrollment_year', type=int)
        elif user.role == 'teacher':
            user.department = request.form.get('department')
            user.position = request.form.get('position')
        elif user.role == 'dean':
            user.faculty_id = request.form.get('faculty_id', type=int)
            user.position = request.form.get('position')
        
        new_password = request.form.get('new_password')
        if new_password:
            user.set_password(new_password)
        
        db.session.commit()
        flash("Foydalanuvchi muvaffaqiyatli yangilandi", 'success')
        return redirect(url_for('admin.users'))
    
    return render_template('admin/edit_user.html', user=user, faculties=faculties, groups=groups)


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
    
    # Demo hisoblar uchun maxsus tekshirish
    demo_logins = ['admin', 'accounting', 'a_karimov', 'b_aliyev', 'd_toshmatov', 'n_rahimova', 'dean_it', 'dean_iq']
    is_demo_account = user.login in demo_logins or (user.email and '@university.uz' in user.email and user.email.split('@')[0] in ['admin', 'accounting', 'a.karimov', 'b.aliyev', 'd.toshmatov', 'n.rahimova', 'dean.it', 'dean.iq'])
    
    if is_demo_account:
        # Demo hisoblar uchun default parollar
        if user.role == 'admin' or user.login == 'admin':
            new_password = 'admin123'
        elif user.role == 'dean' or (user.login and 'dean' in user.login):
            new_password = 'dean123'
        elif user.role == 'teacher' or (user.login and user.login in ['a_karimov', 'b_aliyev', 'd_toshmatov', 'n_rahimova']):
            new_password = 'teacher123'
        elif user.role == 'accounting' or user.login == 'accounting':
            new_password = 'accounting123'
        else:
            new_password = 'student123'
    elif user.passport_number:
        # Oddiy foydalanuvchilar uchun pasport raqami
        new_password = user.passport_number
    else:
        # Pasport raqami yo'q bo'lsa, default parollar
        if user.role == 'admin':
            new_password = 'admin123'
        elif user.role == 'dean':
            new_password = 'dean123'
        elif user.role == 'teacher':
            new_password = 'teacher123'
        elif user.role == 'accounting':
            new_password = 'accounting123'
        elif user.role == 'student':
            new_password = 'student123'
        else:
            flash("Bu foydalanuvchida pasport raqami mavjud emas va default parol aniqlanmadi", 'error')
            referer = request.referrer or url_for('admin.users')
            if 'staff' in referer:
                return redirect(url_for('admin.staff'))
            elif 'students' in referer:
                return redirect(url_for('admin.students'))
            return redirect(url_for('admin.users'))
    
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
# ==================== XODIMLAR BAZASI ====================
@bp.route('/staff')
@login_required
@admin_required
def staff():
    """Xodimlar bazasi (talabalar bo'lmagan barcha foydalanuvchilar)"""
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '')
    
    # Talabalar bo'lmagan barcha foydalanuvchilar
    query = User.query.filter(User.role != 'student')
    
    if search:
        query = query.filter(
            (User.full_name.ilike(f'%{search}%')) |
            (User.email.ilike(f'%{search}%')) |
            (User.phone.ilike(f'%{search}%'))
        )
    
    users = query.order_by(User.created_at.desc()).paginate(page=page, per_page=20)
    
    return render_template('admin/staff.html', users=users, search=search)


@bp.route('/staff/create', methods=['GET', 'POST'])
@login_required
@admin_required
def create_staff():
    """Yangi xodim yaratish (bir nechta rol bilan)"""
    faculties = Faculty.query.all()
    
    if request.method == 'POST':
        email = request.form.get('email')
        login = request.form.get('login')  # Login (xodimlar uchun majburiy)
        full_name = request.form.get('full_name')
        phone = request.form.get('phone')
        passport_number = request.form.get('passport_number')
        pinfl = request.form.get('pinfl')
        birth_date_str = request.form.get('birth_date')
        department = request.form.get('department')
        position = request.form.get('position')
        faculty_id = request.form.get('faculty_id', type=int)
        
        # Bir nechta rol tanlash
        selected_roles = request.form.getlist('roles')  # ['admin', 'dean', 'teacher']
        
        if not selected_roles:
            flash("Kamida bitta rol tanlanishi kerak", 'error')
            return render_template('admin/create_staff.html', faculties=faculties)
        
        # Login majburiy (xodimlar uchun)
        if not login:
            flash("Login majburiy maydon", 'error')
            return render_template('admin/create_staff.html', faculties=faculties)
        
        # Login unikalligi
        if User.query.filter_by(login=login).first():
            flash("Bu login allaqachon mavjud", 'error')
            return render_template('admin/create_staff.html', faculties=faculties)
        
        # Email ixtiyoriy, lekin agar kiritilgan bo'lsa, unikallikni tekshirish
        if email and User.query.filter_by(email=email).first():
            flash("Bu email allaqachon mavjud", 'error')
            return render_template('admin/create_staff.html', faculties=faculties)
        
        # Pasport raqami parol sifatida ishlatiladi
        if not passport_number:
            flash("Pasport seriyasi va raqami majburiy", 'error')
            return render_template('admin/create_staff.html', faculties=faculties)
        
        # Pasport raqamini katta harfga o'zgartirish
        passport_number = passport_number.upper()
        
        password = passport_number  # Pasport raqami parol
        
        # Tug'ilgan sanani parse qilish (yyyy-mm-dd)
        birth_date = None
        if birth_date_str:
            try:
                birth_date = datetime.strptime(birth_date_str, '%Y-%m-%d').date()
            except ValueError:
                flash("Tug'ilgan sana noto'g'ri formatda (yyyy-mm-dd)", 'error')
                return render_template('admin/create_staff.html', faculties=faculties)
        
        # Asosiy rol (birinchisi yoki eng yuqori darajali)
        main_role = selected_roles[0]
        if 'admin' in selected_roles:
            main_role = 'admin'
        elif 'dean' in selected_roles:
            main_role = 'dean'
        elif 'teacher' in selected_roles:
            main_role = 'teacher'
        
        user = User(
            email=email if email else None,  # Email ixtiyoriy
            login=login,
            full_name=full_name,
            role=main_role,  # Asosiy rol (eski kodlar bilan mosligi uchun)
            phone=phone,
            passport_number=passport_number,
            pinfl=pinfl,
            birth_date=birth_date,
            department=department,
            position=position,
            faculty_id=faculty_id if main_role == 'dean' else None
        )
        
        user.set_password(password)
        db.session.add(user)
        db.session.flush()  # ID olish uchun
        
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
    
    faculties = Faculty.query.all()
    
    # Foydalanuvchining mavjud rollarini olish
    existing_roles = [ur.role for ur in user.roles_list.all()]
    
    if request.method == 'POST':
        login = request.form.get('login')
        # Login majburiy (xodimlar uchun)
        if not login:
            flash("Login majburiy maydon", 'error')
            return render_template('admin/edit_staff.html', user=user, faculties=faculties, existing_roles=existing_roles)
        
        # Login unikalligi (boshqa foydalanuvchida bo'lmasligi kerak)
        existing_user_with_login = User.query.filter_by(login=login).first()
        if existing_user_with_login and existing_user_with_login.id != user.id:
            flash("Bu login allaqachon boshqa foydalanuvchida mavjud", 'error')
            return render_template('admin/edit_staff.html', user=user, faculties=faculties, existing_roles=existing_roles)
        
        user.login = login
        email = request.form.get('email')
        # Email ixtiyoriy, lekin agar kiritilgan bo'lsa, unikallikni tekshirish
        if email:
            existing_user_with_email = User.query.filter_by(email=email).first()
            if existing_user_with_email and existing_user_with_email.id != user.id:
                flash("Bu email allaqachon boshqa foydalanuvchida mavjud", 'error')
                return render_template('admin/edit_staff.html', user=user, faculties=faculties, existing_roles=existing_roles)
        user.email = email if email else None
        user.full_name = request.form.get('full_name')
        user.phone = request.form.get('phone')
        passport_number = request.form.get('passport_number')
        # Pasport raqamini katta harfga o'zgartirish
        if passport_number:
            passport_number = passport_number.upper()
        user.passport_number = passport_number
        user.pinfl = request.form.get('pinfl')
        birth_date_str = request.form.get('birth_date')
        user.department = request.form.get('department')
        user.position = request.form.get('position')
        faculty_id = request.form.get('faculty_id', type=int)
        
        # Tug'ilgan sanani parse qilish (yyyy-mm-dd)
        if birth_date_str:
            try:
                user.birth_date = datetime.strptime(birth_date_str, '%Y-%m-%d').date()
            except ValueError:
                flash("Tug'ilgan sana noto'g'ri formatda (yyyy-mm-dd)", 'error')
                return render_template('admin/edit_staff.html', user=user, faculties=faculties, existing_roles=existing_roles)
        
        # Bir nechta rol tanlash
        selected_roles = request.form.getlist('roles')
        
        if not selected_roles:
            flash("Kamida bitta rol tanlanishi kerak", 'error')
            return render_template('admin/edit_staff.html', user=user, faculties=faculties, existing_roles=existing_roles)
        
        # Asosiy rol (eng yuqori darajali)
        main_role = selected_roles[0]
        if 'admin' in selected_roles:
            main_role = 'admin'
        elif 'dean' in selected_roles:
            main_role = 'dean'
        elif 'teacher' in selected_roles:
            main_role = 'teacher'
        
        user.role = main_role
        user.faculty_id = faculty_id if 'dean' in selected_roles else None
        
        # Rollarni yangilash
        # Eski rollarni o'chirish
        UserRole.query.filter_by(user_id=user.id).delete()
        
        # Yangi rollarni qo'shish
        for role in selected_roles:
            user_role = UserRole(user_id=user.id, role=role)
            db.session.add(user_role)
        
        db.session.commit()
        flash(f"Xodim {user.full_name} ma'lumotlari yangilandi", 'success')
        return redirect(url_for('admin.staff'))
    
    return render_template('admin/edit_staff.html', user=user, faculties=faculties, existing_roles=existing_roles)


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
        directions_count = Direction.query.filter_by(faculty_id=faculty.id).count()
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
    if request.method == 'POST':
        name = request.form.get('name')
        code = request.form.get('code').upper()
        description = request.form.get('description')
        
        if Faculty.query.filter_by(code=code).first():
            flash("Bu kod allaqachon mavjud", 'error')
            return render_template('admin/create_faculty.html')
        
        faculty = Faculty(name=name, code=code, description=description)
        db.session.add(faculty)
        db.session.commit()
        
        flash("Fakultet muvaffaqiyatli yaratildi", 'success')
        return redirect(url_for('admin.faculties'))
    
    return render_template('admin/create_faculty.html')


@bp.route('/faculties/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_faculty(id):
    faculty = Faculty.query.get_or_404(id)
    
    if request.method == 'POST':
        faculty.name = request.form.get('name')
        faculty.code = request.form.get('code').upper()
        faculty.description = request.form.get('description')
        
        db.session.commit()
        flash("Fakultet yangilandi", 'success')
        return redirect(url_for('admin.faculties'))
    
    return render_template('admin/edit_faculty.html', faculty=faculty)


@bp.route('/faculties/<int:id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_faculty(id):
    faculty = Faculty.query.get_or_404(id)
    
    if faculty.groups.count() > 0 or faculty.subjects.count() > 0:
        flash("Fakultetda guruhlar yoki fanlar mavjud. Avval ularni o'chiring", 'error')
    else:
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
    
    # Fakultetdagi barcha yo'nalishlarni olish
    all_directions = Direction.query.filter_by(faculty_id=faculty.id).order_by(Direction.name).all()
    
    # Fakultetdagi barcha guruhlarni kurs bo'yicha guruhlash
    all_groups = faculty.groups.order_by(Group.course_year, Group.name).all()
    
    # Filtrlash
    if course_filter:
        all_groups = [g for g in all_groups if g.course_year == course_filter]
    if direction_filter:
        all_groups = [g for g in all_groups if g.direction_id == direction_filter]
    if group_filter:
        all_groups = [g for g in all_groups if g.id == group_filter]
    
    # Kurslar bo'yicha guruhlash
    courses_dict = {}
    
    # Avval barcha yo'nalishlarni kurslar bo'yicha qo'shish
    for direction in all_directions:
        # Bu yo'nalishga tegishli guruhlarni topish
        direction_groups = [g for g in all_groups if g.direction_id == direction.id]
        
        if direction_groups:
            # Agar guruhlar bo'lsa, kurs bo'yicha guruhlash
            for group in direction_groups:
                course_year = group.course_year
                if course_year not in courses_dict:
                    courses_dict[course_year] = {}
                
                direction_id = direction.id
                if direction_id not in courses_dict[course_year]:
                    courses_dict[course_year][direction_id] = {
                        'direction': direction,
                        'groups': []
                    }
                
                courses_dict[course_year][direction_id]['groups'].append(group)
        else:
            # Agar guruhlar bo'lmasa ham, yo'nalishni ko'rsatish (1-kurs sifatida)
            if 1 not in courses_dict:
                courses_dict[1] = {}
            
            direction_id = direction.id
            if direction_id not in courses_dict[1]:
                courses_dict[1][direction_id] = {
                    'direction': direction,
                    'groups': []
                }
    
    # Biriktirilmagan guruhlarni qo'shish
    for group in all_groups:
        if not group.direction_id:
            course_year = group.course_year
            if course_year not in courses_dict:
                courses_dict[course_year] = {}
            
            direction_id = None
            if direction_id not in courses_dict[course_year]:
                courses_dict[course_year][direction_id] = {
                    'direction': None,
                    'groups': []
                }
            
            courses_dict[course_year][direction_id]['groups'].append(group)
    
    # Har bir kurs uchun statistika hisoblash
    for course_year, course_data in courses_dict.items():
        total_directions = len(course_data)
        total_groups = sum(len(d['groups']) for d in course_data.values())
        total_students = sum(
            User.query.filter(User.group_id.in_([g.id for g in d['groups']]), User.role == 'student').count()
            for d in course_data.values()
        )
        
        # Har bir yo'nalish uchun statistika
        for direction_id, direction_data in course_data.items():
            direction_data['students_count'] = User.query.filter(
                User.group_id.in_([g.id for g in direction_data['groups']]),
                User.role == 'student'
            ).count() if direction_data['groups'] else 0
            
            if direction_data['direction']:
                # Fanlar yo'nalishga to'g'ridan-to'g'ri biriktirilmagan, fakultetga biriktirilgan
                # Shuning uchun faqat fakultetdagi fanlarni hisoblaymiz
                direction_data['subjects_count'] = Subject.query.filter_by(
                    faculty_id=faculty.id
                ).count()
            else:
                direction_data['subjects_count'] = 0
        
        course_data['total_directions'] = total_directions
        course_data['total_groups'] = total_groups
        course_data['total_students'] = total_students
    
    # Kurslarni tartiblash
    sorted_courses = sorted(courses_dict.items())
    
    # Template uchun courses_dict'ni to'g'rilash
    # courses_dict strukturasini template'ga moslashtirish
    formatted_courses_dict = {}
    for course_year, course_data in dict(sorted_courses).items():
        # course_data o'zi dict bo'lib, uning ichida yo'nalishlar kalit sifatida saqlanadi
        # Lekin template'da course_data.directions ishlatilmoqda
        formatted_courses_dict[course_year] = {
            'directions': course_data,  # directions kalitini qo'shish
            'total_directions': course_data.get('total_directions', len([k for k in course_data.keys() if k is not None])),
            'total_groups': course_data.get('total_groups', 0),
            'total_students': course_data.get('total_students', 0)
        }
    
    # Filtrlar uchun ma'lumotlar
    courses_list = sorted(set([g.course_year for g in faculty.groups.all()]))
    directions_list = Direction.query.filter_by(faculty_id=faculty.id).order_by(Direction.name).all()
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
    faculty_id = request.args.get('faculty', type=int)
    
    query = Subject.query
    if faculty_id:
        query = query.filter_by(faculty_id=faculty_id)
    
    subjects = query.order_by(Subject.code).all()
    faculties = Faculty.query.all()
    
    return render_template('admin/subjects.html', subjects=subjects, faculties=faculties, current_faculty=faculty_id)


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
    faculties = Faculty.query.all()
    
    if request.method == 'POST':
        code = request.form.get('code').upper()
        
        if Subject.query.filter_by(code=code).first():
            flash("Bu fan kodi allaqachon mavjud", 'error')
            return render_template('admin/create_subject.html', faculties=faculties)
        
        subject = Subject(
            name=request.form.get('name'),
            code=code,
            description=request.form.get('description'),
            credits=request.form.get('credits', 3, type=int),
            faculty_id=request.form.get('faculty_id', type=int),
            semester=request.form.get('semester', 1, type=int)
        )
        db.session.add(subject)
        db.session.commit()
        
        flash("Fan muvaffaqiyatli yaratildi", 'success')
        return redirect(url_for('admin.subjects'))
    
    return render_template('admin/create_subject.html', faculties=faculties)


@bp.route('/subjects/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_subject(id):
    subject = Subject.query.get_or_404(id)
    faculties = Faculty.query.all()
    
    if request.method == 'POST':
        subject.name = request.form.get('name')
        subject.code = request.form.get('code').upper()
        subject.description = request.form.get('description')
        subject.credits = request.form.get('credits', 3, type=int)
        subject.faculty_id = request.form.get('faculty_id', type=int)
        subject.semester = request.form.get('semester', 1, type=int)
        
        db.session.commit()
        flash("Fan yangilandi", 'success')
        return redirect(url_for('admin.subjects'))
    
    return render_template('admin/edit_subject.html', subject=subject, faculties=faculties)


@bp.route('/subjects/<int:id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_subject(id):
    subject = Subject.query.get_or_404(id)
    db.session.delete(subject)
    db.session.commit()
    flash("Fan o'chirildi", 'success')
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
        'total_teachers': User.query.filter_by(role='teacher').count(),
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
            'subjects': faculty.subjects.count(),
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
        min_score = request.form.get('min_score', type=int)
        max_score = request.form.get('max_score', type=int)
        
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
        grade.min_score = request.form.get('min_score', type=int)
        grade.max_score = request.form.get('max_score', type=int)
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
    faculties = Faculty.query.all()
    
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
        
        faculty_id = request.form.get('faculty_id', type=int)
        
        try:
            from app.utils.excel_import import import_students_from_excel
            
            result = import_students_from_excel(file, faculty_id=faculty_id)
            
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
    
    return render_template('admin/import_students.html', faculties=faculties)


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
    
    group_id = request.args.get('group_id', type=int) or request.args.get('group', type=int)
    year = request.args.get('year', type=int)
    month = request.args.get('month', type=int)
    
    # Oy/yil bo'yicha filtr
    if year and month:
        days_in_month = calendar.monthrange(year, month)[1]
        start_code = int(f"{year}{month:02d}01")
        end_code = int(f"{year}{month:02d}{days_in_month:02d}")
        
        if group_id:
            group = Group.query.get_or_404(group_id)
            schedules = Schedule.query.filter(
                Schedule.group_id == group_id,
                Schedule.day_of_week.between(start_code, end_code)
            ).order_by(Schedule.day_of_week, Schedule.start_time).all()
            group_name = group.name
            faculty_name = None
        else:
            schedules = Schedule.query.filter(
                Schedule.day_of_week.between(start_code, end_code)
            ).order_by(Schedule.day_of_week, Schedule.start_time).all()
            group_name = None
            faculty_name = None
    else:
        if group_id:
            group = Group.query.get_or_404(group_id)
            schedules = Schedule.query.filter_by(group_id=group_id).order_by(Schedule.day_of_week, Schedule.start_time).all()
            group_name = group.name
            faculty_name = None
        else:
            schedules = Schedule.query.order_by(Schedule.day_of_week, Schedule.start_time).all()
            group_name = None
            faculty_name = None
    
    excel_file = create_schedule_excel(schedules, group_name, faculty_name)
    
    filename = f"dars_jadvali_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    if group_name:
        filename = f"dars_jadvali_{group_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    elif faculty_name:
        filename = f"dars_jadvali_{faculty_name.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    
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
        faculty_id = request.form.get('faculty_id', type=int)
        direction_id = request.form.get('direction_id', type=int)
        
        # Validatsiya
        if not name:
            flash("Guruh nomi majburiy", 'error')
            return render_template('admin/create_group.html', 
                                 faculties=Faculty.query.all(), 
                                 directions=Direction.query.filter_by(faculty_id=faculty_id).all() if faculty_id else Direction.query.all(),
                                 faculty_id=faculty_id,
                                 direction_id=direction_id)
        
        if not faculty_id:
            flash("Fakultet tanlash majburiy", 'error')
            return render_template('admin/create_group.html', 
                                 faculties=Faculty.query.all(), 
                                 directions=Direction.query.all(),
                                 faculty_id=faculty_id,
                                 direction_id=direction_id)
        
        if not direction_id:
            flash("Yo'nalish tanlash majburiy", 'error')
            return render_template('admin/create_group.html', 
                                 faculties=Faculty.query.all(), 
                                 directions=Direction.query.filter_by(faculty_id=faculty_id).all() if faculty_id else Direction.query.all(),
                                 faculty_id=faculty_id,
                                 direction_id=direction_id)
        
        # Yo'nalish tekshiruvi
        direction = Direction.query.get(direction_id)
        if not direction or direction.faculty_id != faculty_id:
            flash("Noto'g'ri yo'nalish tanlandi", 'error')
            return render_template('admin/create_group.html', 
                                 faculties=Faculty.query.all(), 
                                 directions=Direction.query.filter_by(faculty_id=faculty_id).all() if faculty_id else Direction.query.all(),
                                 faculty_id=faculty_id,
                                 direction_id=direction_id)
        
        if Group.query.filter_by(name=name, faculty_id=faculty_id).first():
            flash("Bu guruh nomi allaqachon mavjud", 'error')
            return render_template('admin/create_group.html', 
                                 faculties=Faculty.query.all(), 
                                 directions=Direction.query.filter_by(faculty_id=faculty_id).all() if faculty_id else Direction.query.all(),
                                 faculty_id=faculty_id,
                                 direction_id=direction_id)
        
        # Yo'nalishdan kurs, semestr va ta'lim shaklini olish
        group = Group(
            name=name.upper(),
            faculty_id=faculty_id,
            course_year=direction.course_year,
            education_type=direction.education_type,  # Yo'nalishdan olinadi
            direction_id=direction_id
        )
        db.session.add(group)
        db.session.commit()
        
        flash("Guruh muvaffaqiyatli yaratildi", 'success')
        # Fakultet detail sahifasiga qaytish
        if faculty_id:
            return redirect(url_for('admin.faculty_detail', id=faculty_id))
        return redirect(url_for('admin.groups'))
    
    # GET request - faqat shu fakultetdagi yo'nalishlarni ko'rsatish
    directions = []
    if faculty_id:
        directions = Direction.query.filter_by(faculty_id=faculty_id).order_by(Direction.course_year, Direction.semester, Direction.name).all()
    else:
        directions = Direction.query.order_by(Direction.faculty_id, Direction.course_year, Direction.semester, Direction.name).all()
    
    return render_template('admin/create_group.html', 
                         faculties=Faculty.query.all(), 
                         directions=directions,
                         faculty_id=faculty_id,
                         direction_id=direction_id)


@bp.route('/groups/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_group(id):
    group = Group.query.get_or_404(id)
    
    if request.method == 'POST':
        # Faqat guruh nomini o'zgartirish mumkin
        group.name = request.form.get('name').upper()
        
        # Agar guruhga yo'nalish biriktirilgan bo'lsa, kurs va ta'lim shaklini yo'nalishdan olish
        if group.direction_id:
            direction = Direction.query.get(group.direction_id)
            if direction:
                group.course_year = direction.course_year
                group.education_type = direction.education_type
        
        db.session.commit()
        flash("Guruh yangilandi", 'success')
        # Fakultet detail sahifasiga qaytish
        if request.args.get('from_faculty'):
            return redirect(url_for('admin.faculty_detail', id=group.faculty_id))
        return redirect(url_for('admin.groups'))
    
    return render_template('admin/edit_group.html', 
                         group=group, 
                         faculties=Faculty.query.all())


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
    if group.students.count() > 0:
        flash("Guruhda talabalar bor. O'chirish mumkin emas", 'error')
    else:
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
            education_type=education_type
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
@bp.route('/assignments')
@login_required
@admin_required
def assignments():
    faculty_id = request.args.get('faculty_id', type=int)
    search = request.args.get('search', '')
    
    query = TeacherSubject.query
    if faculty_id:
        query = query.join(Group).filter(Group.faculty_id == faculty_id)
        
    if search:
        query = query.join(User, TeacherSubject.teacher_id == User.id)\
                     .filter(User.full_name.ilike(f'%{search}%'))
        
    assignments_list = query.all()
    faculties = Faculty.query.all()
    teachers = User.query.filter_by(role='teacher').order_by(User.full_name).all()
    
    return render_template('admin/assignments.html', assignments=assignments_list, faculties=faculties, teachers=teachers, current_faculty=faculty_id, search=search)


@bp.route('/assignments/create', methods=['POST'])
@login_required
@admin_required
def create_assignment():
    try:
        teacher_id = request.form.get('teacher_id', type=int)
        group_id = request.form.get('group_id', type=int)
        subject_id = request.form.get('subject_id', type=int)
        lesson_type = request.form.get('lesson_type', 'maruza')
        
        # Check if already exists
        exists = TeacherSubject.query.filter_by(
            teacher_id=teacher_id,
            group_id=group_id,
            subject_id=subject_id,
            lesson_type=lesson_type
        ).first()
        
        if exists:
            flash("Bu o'qituvchi ushbu guruh va fanga allaqachon biriktirilgan", 'error')
        else:
            assignment = TeacherSubject(
                teacher_id=teacher_id,
                group_id=group_id,
                subject_id=subject_id,
                lesson_type=lesson_type,
                assigned_by=current_user.id,
                semester=1 # Default
            )
            db.session.add(assignment)
            db.session.commit()
            flash("O'qituvchi muvaffaqiyatli biriktirildi", 'success')
            
    except Exception as e:
        db.session.rollback()
        flash(f"Xatolik yuz berdi: {str(e)}", 'error')
        
    return redirect(request.referrer or url_for('admin.assignments'))


@bp.route('/assignments/<int:id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_assignment(id):
    assignment = TeacherSubject.query.get_or_404(id)
    db.session.delete(assignment)
    db.session.commit()
    flash("Biriktirish o'chirildi", 'success')
    return redirect(url_for('admin.assignments'))


# ==================== ADMIN UCHUN DEKAN FUNKSIYALARI ====================
# Admin uchun barcha fakultetlar bo'yicha ishlaydi

@bp.route('/directions')
@login_required
@admin_required
def directions():
    """Admin uchun barcha yo'nalishlar"""
    directions_list = Direction.query.order_by(Direction.name).all()
    faculties = Faculty.query.order_by(Faculty.name).all()
    unassigned_groups = Group.query.filter_by(direction_id=None).order_by(Group.name).all()
    
    direction_groups = {}
    for direction in directions_list:
        direction_groups[direction.id] = Group.query.filter_by(direction_id=direction.id).all()
    
    return render_template('dean/directions.html',
                         faculty=None,
                         directions=directions_list,
                         unassigned_groups=unassigned_groups,
                         direction_groups=direction_groups,
                         is_admin=True)

@bp.route('/students/create', methods=['GET', 'POST'])
@login_required
@admin_required
def create_student():
    """Admin uchun yangi talaba yaratish"""
    directions = Direction.query.all()
    groups = Group.query.all()
    faculties = Faculty.query.all()
    
    if request.method == 'POST':
        email = request.form.get('email')
        full_name = request.form.get('full_name')
        passport_number = request.form.get('passport_number')
        phone = request.form.get('phone')
        student_id = request.form.get('student_id')
        direction_id = request.form.get('direction_id', type=int)
        group_id = request.form.get('group_id', type=int)
        enrollment_year = request.form.get('enrollment_year', type=int)
        pinfl = request.form.get('pinfl')
        birth_date = request.form.get('birth_date')
        specialty = request.form.get('specialty')
        specialty_code = request.form.get('specialty_code')
        education_type = request.form.get('education_type')
        
        # Email ixtiyoriy, lekin agar kiritilgan bo'lsa, unikallikni tekshirish
        if email and User.query.filter_by(email=email).first():
            flash("Bu email allaqachon mavjud", 'error')
            return render_template('admin/create_student.html', 
                                 directions=directions, groups=groups, faculties=faculties)
        
        # Talaba ID majburiy (talabalar uchun)
        if not student_id:
            flash("Talaba ID majburiy maydon", 'error')
            return render_template('admin/create_student.html', 
                                 directions=directions, groups=groups, faculties=faculties)
        
        if User.query.filter_by(student_id=student_id).first():
            flash("Bu talaba ID allaqachon mavjud", 'error')
            return render_template('admin/create_student.html', 
                                 directions=directions, groups=groups, faculties=faculties)
        
        if not passport_number:
            flash("Pasport seriyasi va raqami majburiy", 'error')
            return render_template('admin/create_student.html', 
                                 directions=directions, groups=groups, faculties=faculties)
        
        # Pasport raqamini katta harfga o'zgartirish
        passport_number = passport_number.upper()
        
        # Tug'ilgan sanani parse qilish (yyyy-mm-dd)
        parsed_birth_date = None
        if birth_date:
            try:
                parsed_birth_date = datetime.strptime(birth_date, '%Y-%m-%d').date()
            except ValueError:
                flash("Tug'ilgan sana noto'g'ri formatda (yyyy-mm-dd)", 'error')
                return render_template('admin/create_student.html', 
                                     directions=directions, groups=groups, faculties=faculties)
        
        student = User(
            email=email if email else None,  # Email ixtiyoriy
            full_name=full_name,
            role='student',
            phone=phone,
            student_id=student_id,
            group_id=group_id,
            enrollment_year=enrollment_year,
            passport_number=passport_number,
            pinfl=pinfl,
            birth_date=parsed_birth_date,
            specialty=specialty,
            specialty_code=specialty_code,
            education_type=education_type
        )
        
        # Parolni pasport raqamiga o'rnatish
        student.set_password(passport_number)
        
        db.session.add(student)
        db.session.commit()
        
        flash(f"{student.full_name} muvaffaqiyatli yaratildi", 'success')
        return redirect(url_for('admin.students'))
    
    return render_template('admin/create_student.html', 
                         directions=directions, groups=groups, faculties=faculties)


@bp.route('/students/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_student(id):
    """Admin uchun talabani tahrirlash"""
    student = User.query.get_or_404(id)
    if student.role != 'student':
        flash("Bu foydalanuvchi talaba emas", 'error')
        return redirect(url_for('admin.students'))
    
    directions = Direction.query.all()
    groups = Group.query.all()
    faculties = Faculty.query.all()
    
    if request.method == 'POST':
        student_id = request.form.get('student_id')
        # Talaba ID majburiy (talabalar uchun)
        if not student_id:
            flash("Talaba ID majburiy maydon", 'error')
            return render_template('admin/edit_student.html', 
                                 student=student, directions=directions, groups=groups, faculties=faculties)
        
        # Talaba ID unikalligi (boshqa talabada bo'lmasligi kerak)
        existing_student = User.query.filter_by(student_id=student_id).first()
        if existing_student and existing_student.id != student.id:
            flash("Bu talaba ID allaqachon boshqa talabada mavjud", 'error')
            return render_template('admin/edit_student.html', 
                                 student=student, directions=directions, groups=groups, faculties=faculties)
        
        email = request.form.get('email')
        # Email ixtiyoriy, lekin agar kiritilgan bo'lsa, unikallikni tekshirish
        if email:
            existing_student_with_email = User.query.filter_by(email=email).first()
            if existing_student_with_email and existing_student_with_email.id != student.id:
                flash("Bu email allaqachon boshqa talabada mavjud", 'error')
                return render_template('admin/edit_student.html', 
                                     student=student, directions=directions, groups=groups, faculties=faculties)
        student.email = email if email else None
        student.full_name = request.form.get('full_name')
        student.phone = request.form.get('phone')
        student.student_id = student_id
        student.group_id = request.form.get('group_id', type=int)
        student.enrollment_year = request.form.get('enrollment_year', type=int)
        passport_number = request.form.get('passport_number')
        # Pasport raqamini katta harfga o'zgartirish
        if passport_number:
            passport_number = passport_number.upper()
        student.passport_number = passport_number
        student.pinfl = request.form.get('pinfl')
        birth_date_str = request.form.get('birth_date')
        # Tug'ilgan sanani parse qilish (yyyy-mm-dd)
        if birth_date_str:
            try:
                student.birth_date = datetime.strptime(birth_date_str, '%Y-%m-%d').date()
            except ValueError:
                flash("Tug'ilgan sana noto'g'ri formatda (yyyy-mm-dd)", 'error')
                return render_template('admin/edit_student.html', 
                                     student=student, directions=directions, groups=groups, faculties=faculties)
        else:
            student.birth_date = None
        student.specialty = request.form.get('specialty')
        student.specialty_code = request.form.get('specialty_code')
        student.education_type = request.form.get('education_type')
        
        db.session.commit()
        flash(f"{student.full_name} ma'lumotlari yangilandi", 'success')
        return redirect(url_for('admin.students'))
    
    return render_template('admin/edit_student.html', 
                         student=student, directions=directions, groups=groups, faculties=faculties)


@bp.route('/students')
@login_required
@admin_required
def students():
    """Admin uchun barcha talabalar"""
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '')
    group_id = request.args.get('group', type=int)
    faculty_id = request.args.get('faculty', type=int)
    
    query = User.query.filter(User.role == 'student')
    
    if search:
        query = query.filter(
            (User.full_name.ilike(f'%{search}%')) |
            (User.email.ilike(f'%{search}%')) |
            (User.student_id.ilike(f'%{search}%'))
        )
    
    if group_id:
        query = query.filter(User.group_id == group_id)
    elif faculty_id:
        group_ids = [g.id for g in Group.query.filter_by(faculty_id=faculty_id).all()]
        query = query.filter(User.group_id.in_(group_ids))
    
    students = query.order_by(User.full_name).paginate(page=page, per_page=20)
    groups = Group.query.order_by(Group.name).all()
    faculties = Faculty.query.order_by(Faculty.name).all()
    
    return render_template('admin/students.html', 
                         students=students,
                         groups=groups,
                         faculties=faculties,
                         current_group=group_id,
                         current_faculty=faculty_id,
                         search=search)

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
    
    if not student.passport_number:
        # Pasport raqami yo'q bo'lsa, default parol
        new_password = 'student123'
        student.set_password(new_password)
        db.session.commit()
        flash(f"{student.full_name} paroli boshlang'ich holatga qaytarildi. Yangi parol: {new_password}", 'success')
    else:
        new_password = student.passport_number
        student.set_password(new_password)
        db.session.commit()
        flash(f"{student.full_name} paroli boshlang'ich holatga qaytarildi. Yangi parol: {new_password}", 'success')
    return redirect(url_for('admin.students'))

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
    
    group_id = request.args.get('group', type=int)
    groups = Group.query.order_by(Group.name).all()
    
    if group_id:
        schedules = Schedule.query.filter(
            Schedule.group_id == group_id,
            Schedule.day_of_week.between(start_code, end_code)
        ).order_by(Schedule.day_of_week, Schedule.start_time).all()
    else:
        schedules = Schedule.query.filter(
            Schedule.day_of_week.between(start_code, end_code)
        ).order_by(Schedule.day_of_week, Schedule.start_time).all()
    
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
                         groups=groups,
                         current_group=group_id,
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
    groups = Group.query.order_by(Group.name).all()
    subjects = Subject.query.order_by(Subject.code).all()
    teachers = User.query.filter_by(role='teacher').order_by(User.full_name).all()
    
    # GET parametrlar orqali kelgan default sana va guruh
    default_date = request.args.get('date')
    default_group_id = request.args.get('group', type=int)
    
    if request.method == 'POST':
        # Sana (kalendardan) -> YYYYMMDD formatida int
        date_str = request.form.get('schedule_date')
        date_code = None
        if date_str:
            try:
                parsed_date = datetime.strptime(date_str, "%Y-%m-%d")
                date_code = int(parsed_date.strftime("%Y%m%d"))
            except ValueError:
                flash("Sana noto'g'ri formatda. Iltimos, kalendardan tanlang.", 'error')
                return redirect(url_for('admin.create_schedule'))
        
        if not date_code:
            flash("Sana tanlanishi shart.", 'error')
            return redirect(url_for('admin.create_schedule'))
        
        schedule = Schedule(
            subject_id=request.form.get('subject_id', type=int),
            group_id=request.form.get('group_id', type=int),
            teacher_id=request.form.get('teacher_id', type=int),
            day_of_week=date_code,
            start_time=request.form.get('start_time'),
            end_time=request.form.get('end_time') or None,
            link=request.form.get('link'),
            lesson_type=request.form.get('lesson_type')
        )
        db.session.add(schedule)
        db.session.commit()
        
        flash("Dars jadvalga qo'shildi", 'success')
        # Sana bo'yicha qayta ochish (shu oy/yil)
        return redirect(url_for(
            'admin.schedule',
            year=parsed_date.year,
            month=parsed_date.month,
            group=schedule.group_id
        ))
    
    return render_template('admin/create_schedule.html',
                         groups=groups,
                         subjects=subjects,
                         teachers=teachers,
                         default_date=default_date,
                         default_group_id=default_group_id)


@bp.route('/schedule/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_schedule(id):
    """Admin uchun dars jadvalini tahrirlash"""
    schedule = Schedule.query.get_or_404(id)
    
    groups = Group.query.order_by(Group.name).all()
    subjects = Subject.query.order_by(Subject.code).all()
    teachers = User.query.filter_by(role='teacher').order_by(User.full_name).all()
    
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
        schedule.end_time = request.form.get('end_time') or None
        schedule.link = request.form.get('link')
        schedule.lesson_type = request.form.get('lesson_type')
        
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
        groups=groups,
        subjects=subjects,
        teachers=teachers,
        schedule=schedule,
        schedule_date=schedule_date,
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
