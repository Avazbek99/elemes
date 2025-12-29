from flask import Blueprint, render_template, redirect, url_for, flash, request, session
from flask_login import login_user, logout_user, login_required, current_user
from app.models import User, PasswordResetToken
from app import db
from datetime import datetime, timedelta
import secrets

bp = Blueprint('auth', __name__)

@bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    
    if request.method == 'POST':
        login_input = request.form.get('login')  # Login, email yoki talaba ID
        password = request.form.get('password')
        remember = request.form.get('remember', False)
        
        # Login, email yoki talaba ID orqali foydalanuvchini topish
        user = None
        if login_input:
            # Avval email orqali qidirish
            user = User.query.filter_by(email=login_input).first()
            # Agar topilmasa, login orqali qidirish
            if not user:
                user = User.query.filter_by(login=login_input).first()
            # Agar hali ham topilmasa, talaba ID orqali qidirish
            if not user:
                user = User.query.filter_by(student_id=login_input).first()
        
        if user and user.check_password(password):
            if not user.is_active:
                flash("Sizning hisobingiz bloklangan", 'error')
                return render_template('auth/login.html')
            
            user.last_login = datetime.utcnow()
            db.session.commit()
            
            # Session'dagi eski current_role ni tozalash va yangi foydalanuvchining asosiy rolini o'rnatish
            session.pop('current_role', None)
            session['current_role'] = user.role
            
            login_user(user, remember=remember)
            
            next_page = request.args.get('next')
            return redirect(next_page or url_for('main.dashboard'))
        else:
            flash("Login, email, talaba ID yoki parol noto'g'ri", 'error')
    
    return render_template('auth/login.html')

@bp.route('/logout')
@login_required
def logout():
    # Session'dagi current_role ni tozalash
    session.pop('current_role', None)
    logout_user()
    flash("Tizimdan muvaffaqiyatli chiqdingiz", 'success')
    return redirect(url_for('auth.login'))

@bp.route('/register', methods=['GET', 'POST'])
def register():
    # Ro'yxatdan o'tish funksiyasi yopilgan - foydalanuvchilar admin tomonidan qo'shiladi
    flash("Ro'yxatdan o'tish funksiyasi yopilgan. Iltimos, administrator bilan bog'laning.", 'error')
    return redirect(url_for('auth.login'))

@bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    """Parolni unutish sahifasi"""
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'check':
            # Login, talaba ID yoki email orqali foydalanuvchini qidirish
            login_input = request.form.get('login_input', '').strip()
            
            if not login_input:
                flash("Iltimos, login, talaba ID yoki email kiriting", 'error')
                return render_template('auth/forgot_password.html')
            
            # Foydalanuvchini qidirish
            user = None
            # Avval email orqali qidirish
            user = User.query.filter_by(email=login_input).first()
            # Agar topilmasa, login orqali qidirish
            if not user:
                user = User.query.filter_by(login=login_input).first()
            # Agar hali ham topilmasa, talaba ID orqali qidirish
            if not user:
                user = User.query.filter_by(student_id=login_input).first()
            
            if not user:
                flash("Bu login, talaba ID yoki email bilan foydalanuvchi topilmadi", 'error')
                return render_template('auth/forgot_password.html')
            
            # Faqat talaba va o'qituvchi uchun
            if user.role not in ['teacher', 'student']:
                flash("Bu funksiya faqat o'qituvchi va talabalar uchun mavjud", 'error')
                return render_template('auth/forgot_password.html')
            
            # Foydalanuvchi topildi, pasport inputini ko'rsatish
            return render_template('auth/forgot_password.html', user_found=True, user_id=user.id)
        
        elif action == 'reset':
            # Pasport orqali tekshirish va parolni reset qilish
            user_id = request.form.get('user_id')
            passport = request.form.get('passport', '').strip().upper()
            
            if not user_id or not passport:
                flash("Iltimos, pasport seriya raqamini kiriting", 'error')
                return render_template('auth/forgot_password.html', user_found=True, user_id=user_id)
            
            user = User.query.get(user_id)
            if not user:
                flash("Foydalanuvchi topilmadi", 'error')
                return render_template('auth/forgot_password.html')
            
            # Faqat talaba va o'qituvchi uchun
            if user.role not in ['teacher', 'student']:
                flash("Bu funksiya faqat o'qituvchi va talabalar uchun mavjud", 'error')
                return render_template('auth/forgot_password.html')
            
            # Pasportni tekshirish
            if not user.passport_number or user.passport_number.upper() != passport:
                flash("Pasport seriya raqami noto'g'ri", 'error')
                return render_template('auth/forgot_password.html', user_found=True, user_id=user_id)
            
            # Parolni boshlang'ich holatga qaytarish (pasport seriya raqamiga)
            if not user.passport_number:
                flash("Foydalanuvchida pasport seriya raqami mavjud emas", 'error')
                return render_template('auth/forgot_password.html', user_found=True, user_id=user_id)
            
            new_password = user.passport_number
            user.set_password(new_password)
            db.session.commit()
            
            flash(f"Parol muvaffaqiyatli boshlang'ich holatga qaytarildi! Parol: {new_password}", 'success')
            return redirect(url_for('auth.login'))
    
    return render_template('auth/forgot_password.html')

@bp.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    """Parolni tiklash sahifasi"""
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    
    reset_token = PasswordResetToken.query.filter_by(token=token, is_used=False).first()
    
    if not reset_token:
        flash("Token topilmadi yoki allaqachon ishlatilgan", 'error')
        return redirect(url_for('auth.forgot_password'))
    
    if datetime.utcnow() > reset_token.expires_at:
        flash("Token muddati tugagan. Iltimos, yangi so'rov yuboring", 'error')
        reset_token.is_used = True
        db.session.commit()
        return redirect(url_for('auth.forgot_password'))
    
    user = reset_token.user
    
    if request.method == 'POST':
        password = request.form.get('password')
        password2 = request.form.get('password2')
        
        if password != password2:
            flash("Parollar mos kelmaydi", 'error')
            return render_template('auth/reset_password.html', token=token, user=user)
        
        if len(password) < 6:
            flash("Parol kamida 6 ta belgidan iborat bo'lishi kerak", 'error')
            return render_template('auth/reset_password.html', token=token, user=user)
        
        # Parolni o'zgartirish
        user.set_password(password)
        reset_token.is_used = True
        db.session.commit()
        
        flash("Parol muvaffaqiyatli o'zgartirildi! Endi tizimga kiring", 'success')
        return redirect(url_for('auth.login'))
    
    return render_template('auth/reset_password.html', token=token, user=user)

