import os
import random
from flask import Flask, redirect, url_for, request
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from config import Config

from flask_migrate import Migrate

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
login_manager.login_view = 'auth.login'
login_manager.login_message = "Iltimos, tizimga kiring"
csrf = CSRFProtect()

@login_manager.unauthorized_handler
def unauthorized_callback():
    """Session tugaganda /logout ga yo'naltirilganda next= parametri qo'shilmasin."""
    if request.path and '/logout' in request.path:
        return redirect(url_for('auth.login'))
    return redirect(url_for('auth.login', next=request.url))

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    # Bazani doim instance/eduspace.db ga yo'naltirish (bitta fayl bo'lishi uchun)
    if not os.environ.get('DATABASE_URL'):
        uri = app.config.get('SQLALCHEMY_DATABASE_URI') or ''
        if uri == 'sqlite:///eduspace.db' or (uri.startswith('sqlite:///') and 'eduspace.db' in uri and '/' not in uri.replace('sqlite:///', '')):
            db_path = os.path.join(app.instance_path, 'eduspace.db').replace('\\', '/')
            app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + db_path
    # Create uploads folder
    os.makedirs(app.config.get('UPLOAD_FOLDER', 'uploads'), exist_ok=True)
    os.makedirs(os.path.join(app.config.get('UPLOAD_FOLDER', 'uploads'), 'videos'), exist_ok=True)
    os.makedirs(os.path.join(app.config.get('UPLOAD_FOLDER', 'uploads'), 'submissions'), exist_ok=True)
    os.makedirs(os.path.join(app.config.get('UPLOAD_FOLDER', 'uploads'), 'lesson_files'), exist_ok=True)
    os.makedirs(os.path.join(app.config.get('UPLOAD_FOLDER', 'uploads'), 'site'), exist_ok=True)
    
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)
    # superadmin_flag ustuni yo'q bo'lsa qo'shish (eski bazalar uchun)
    with app.app_context():
        try:
            from sqlalchemy import text, inspect
            conn = db.engine.connect()
            try:
                inspector = inspect(db.engine)
                if 'user' in inspector.get_table_names():
                    cols = [c['name'] for c in inspector.get_columns('user')]
                    if 'superadmin_flag' not in cols:
                        conn.execute(text("ALTER TABLE user ADD COLUMN superadmin_flag INTEGER"))
                        conn.commit()
                    if 'managed_department_id' not in cols:
                        conn.execute(text("ALTER TABLE user ADD COLUMN managed_department_id INTEGER"))
                        conn.commit()
                if 'subject' in inspector.get_table_names():
                    cols = [c['name'] for c in inspector.get_columns('subject')]
                    if 'department_id' not in cols:
                        conn.execute(text("ALTER TABLE subject ADD COLUMN department_id INTEGER"))
                        conn.commit()
            finally:
                conn.close()
        except Exception as e:
            app.logger.warning("superadmin_flag migration: %s", e)
        try:
            from app.models import FlashMessage, SiteSetting
            from datetime import date
            from sqlalchemy import inspect
            inspector = inspect(db.engine)
            if 'flash_message' in inspector.get_table_names() and FlashMessage.query.count() == 0:
                tuz = (SiteSetting.get('ticker_text_uz') or '').strip()
                tru = (SiteSetting.get('ticker_text_ru') or '').strip()
                ten = (SiteSetting.get('ticker_text_en') or '').strip()
                tmain = (SiteSetting.get('ticker_text') or '').strip()
                if tuz or tru or ten or tmain:
                    fm = FlashMessage()
                    fm.text_uz = tuz or tmain
                    fm.text_ru = tru or tmain
                    fm.text_en = ten or tmain
                    fm.url = (SiteSetting.get('ticker_url') or '').strip()
                    fm.text_color = (SiteSetting.get('ticker_text_color') or 'white').strip().lower()
                    fm.enabled = (SiteSetting.get('ticker_enabled') or '').strip().lower() in ('1', 'true', 'yes', 'on')
                    df = (SiteSetting.get('ticker_date_from') or '').strip()
                    dt = (SiteSetting.get('ticker_date_to') or '').strip()
                    try:
                        fm.date_from = date.fromisoformat(df) if df else None
                    except (ValueError, TypeError):
                        fm.date_from = None
                    try:
                        fm.date_to = date.fromisoformat(dt) if dt else None
                    except (ValueError, TypeError):
                        fm.date_to = None
                    db.session.add(fm)
                    db.session.commit()
        except Exception as e:
            app.logger.warning("flash_message data migration: %s", e)
    # Session timeout middleware
    @app.before_request
    def make_session_permanent():
        from flask import session
        session.permanent = True
        app.permanent_session_lifetime = app.config['PERMANENT_SESSION_LIFETIME']
    
    # Custom Jinja2 filter for formatting numbers
    @app.template_filter('format_float')
    def format_float_filter(value, decimals=2):
        """Format float to string with specified decimals"""
        try:
            if value is None:
                return f"0.{'0' * decimals}"
            return f"{float(value):.{decimals}f}"
        except (ValueError, TypeError):
            return f"0.{'0' * decimals}"
    
    # Custom Jinja2 filter for Tashkent time
    @app.template_filter('to_tashkent_time')
    def to_tashkent_time_filter(value):
        """Convert UTC to Tashkent time (UTC+5)"""
        if value is None:
            return None
        from datetime import timedelta
        return value + timedelta(hours=5)
    
    # Escape string for use inside JavaScript single-quoted string (e.g. confirm('...'))
    @app.template_filter('escapejs')
    def escapejs_filter(value):
        """Escape backslash and single quote so UZ/RU text in confirm() does not break JS."""
        if value is None:
            return ''
        return str(value).replace('\\', '\\\\').replace("'", "\\'")
    
    # O'quv yilini "2025-2026" formatida ko'rsatish
    @app.template_filter('academic_year_display')
    def academic_year_display_filter(value):
        if value is None:
            return '—'
        try:
            y = int(value)
            return f'{y}-{y + 1}'
        except (ValueError, TypeError):
            return str(value)

    # Ta'lim shaklini tanlangan tilda ko'rsatish (Kunduzgi → Дневная / Full-time)
    @app.template_filter('education_type_label')
    def education_type_label_filter(value):
        from flask import session
        from app.utils.translations import get_translation
        if not value:
            return get_translation('education_type_not_set', session.get('language', 'uz'))
        key = str(value).strip().lower()
        if key in ('kunduzgi', 'sirtqi', 'kechki', 'masofaviy'):
            return get_translation('education_type_' + key, session.get('language', 'uz'))
        return get_translation('education_type_not_set', session.get('language', 'uz'))
    
    # Dars turini tanlangan tilda ko'rsatish (Maruza → Лекция / Lecture)
    @app.template_filter('lesson_type_label')
    def lesson_type_label_filter(value):
        from flask import session
        from app.utils.translations import get_translation
        if not value:
            return value
        # Dars turi kalitlarini aniqlash
        lesson_type_map = {
            # O'zbekcha variantlar
            'maruza': 'lesson_type_maruza',
            'ma\'ruza': 'lesson_type_maruza',
            'amaliyot': 'lesson_type_amaliyot',
            'laboratoriya': 'lesson_type_laboratoriya',
            'lobaratoriya': 'lesson_type_laboratoriya',  # Xato yozilgan variant
            'seminar': 'lesson_type_seminar',
            'kurs ishi': 'lesson_type_kurs_ishi',
            'kurs_ishi': 'lesson_type_kurs_ishi',
            'mustaqil ta\'lim': 'lesson_type_mustaqil_talim',
            'mustaqil talim': 'lesson_type_mustaqil_talim',
            # Inglizcha variantlar
            'lecture': 'lesson_type_maruza',
            'practice': 'lesson_type_amaliyot',
            'practical': 'lesson_type_amaliyot',
            'lab': 'lesson_type_laboratoriya',
            'laboratory': 'lesson_type_laboratoriya',
            # Ruscha variantlar (lowercase)
            'лекция': 'lesson_type_maruza',
            'практика': 'lesson_type_amaliyot',
            'лабораторная': 'lesson_type_laboratoriya',
            'семинар': 'lesson_type_seminar',
        }
        lang = session.get('language', 'uz')
        
        def translate_part(part):
            k = part.strip().lower()
            return get_translation(lesson_type_map[k], lang) if k in lesson_type_map else part.strip()
        
        sval = str(value).strip()
        # Vergul yoki slash bilan ajratilgan bo'lsa, har birini alohida tarjima qilish
        if ',' in sval:
            parts = [translate_part(p) for p in sval.split(',')]
            return ', '.join(parts)
        if '/' in sval:
            parts = [translate_part(p) for p in sval.split('/')]
            return '/'.join(parts)
        
        key = sval.lower()
        if key in lesson_type_map:
            return get_translation(lesson_type_map[key], lang)
        return value  # Agar topilmasa, asl qiymatni qaytarish
    
    # Context processor for translations
    @app.context_processor
    def inject_global_data():
        from flask import session
        from flask_login import current_user
        from app.utils.translations import get_translation
        from app.models import Message, SiteSetting, FlashMessage
        from datetime import date
        
        lang = session.get('language', 'uz')
        
        unread_msg_count = 0
        if current_user.is_authenticated:
            try:
                unread_msg_count = Message.query.filter_by(
                    receiver_id=current_user.id, 
                    is_read=False
                ).count()
            except:
                pass
        site_institution_name = (SiteSetting.get('institution_name_' + lang) or '').strip()
        site_name_short = (SiteSetting.get('site_name_short_' + lang) or '').strip()
        site_tagline = (SiteSetting.get('tagline_' + lang) or '').strip()
        site_logo_path = (SiteSetting.get('logo_path_' + lang) or '').strip()
        site_logo_filename = (site_logo_path.replace('\\', '/').split('/')[-1] or '') if site_logo_path else ''
        ticker_text = ''
        ticker_url = ''
        ticker_text_color = 'white'
        ticker_visible = False
        ticker_items = []  # Barcha faol va muddatiga mos flash xabarlar
        try:
            fm_list = FlashMessage.query.filter_by(enabled=True).order_by(FlashMessage.sort_order.asc(), FlashMessage.id.asc()).all()
            for fm in fm_list:
                if fm.is_in_date_range():
                    txt = fm.get_text(lang)
                    if txt:
                        ticker_items.append({
                            'text': txt,
                            'url': (fm.url or '').strip(),
                            'text_color': (fm.text_color or 'white').strip().lower()
                        })
                        ticker_visible = True
            if ticker_items:
                random.shuffle(ticker_items)
            if ticker_items and not ticker_text:
                ticker_text = ticker_items[0]['text']
                ticker_url = ticker_items[0]['url']
                ticker_text_color = ticker_items[0]['text_color']
        except Exception:
            pass
        if not ticker_visible and not ticker_text:
            ticker_enabled = (SiteSetting.get('ticker_enabled') or '').strip().lower() in ('1', 'true', 'yes', 'on')
            ticker_text = (SiteSetting.get('ticker_text_' + lang) or SiteSetting.get('ticker_text') or '').strip()
            ticker_url = (SiteSetting.get('ticker_url') or '').strip()
            ticker_text_color = (SiteSetting.get('ticker_text_color') or 'white').strip().lower()
            ticker_date_from = (SiteSetting.get('ticker_date_from') or '').strip()
            ticker_date_to = (SiteSetting.get('ticker_date_to') or '').strip()
            ticker_in_range = True
            if ticker_date_from or ticker_date_to:
                try:
                    today = date.today()
                    if ticker_date_from:
                        ticker_in_range = today >= date.fromisoformat(ticker_date_from)
                    if ticker_date_to:
                        ticker_in_range = ticker_in_range and today <= date.fromisoformat(ticker_date_to)
                except (ValueError, TypeError):
                    ticker_in_range = True
                    ticker_visible = ticker_enabled and bool(ticker_text) and ticker_in_range
        ticker_enabled = ticker_visible if 'ticker_enabled' not in dir() or not any([
            k for k in ('ticker_enabled',) if k in dir()
        ]) else (ticker_enabled if 'ticker_enabled' in dir() else ticker_visible)
        return {
            't': lambda key, **kwargs: get_translation(key, lang, **kwargs),
            't_lang': lambda key, l, **kwargs: get_translation(key, l, **kwargs),
            'current_lang': lang,
            'unread_msg_count': unread_msg_count,
            'site_institution_name': site_institution_name,
            'site_name_short': site_name_short,
            'site_tagline': site_tagline,
            'site_logo_path': site_logo_path,
            'site_logo_filename': site_logo_filename,
            'ticker_enabled': ticker_enabled,
            'ticker_text': ticker_text,
            'ticker_url': ticker_url,
            'ticker_text_color': ticker_text_color,
            'ticker_visible': ticker_visible,
            'ticker_items': ticker_items,
            'languages': {
                'uz': {'code': 'uz', 'name': 'O\'zbek', 'flag': '🇺🇿'},
                'ru': {'code': 'ru', 'name': 'Русский', 'flag': '🇷🇺'},
                'en': {'code': 'en', 'name': 'English', 'flag': '🇺🇸'}
            }
        }
    
    from app.routes import main, auth, admin, dean, courses, api, accounting
    app.register_blueprint(main.bp)
    app.register_blueprint(auth.bp)
    app.register_blueprint(admin.bp)
    app.register_blueprint(dean.bp)
    app.register_blueprint(courses.bp)
    app.register_blueprint(api.bp)
    app.register_blueprint(accounting.bp)
    
    with app.app_context():
        db.create_all()
        
        # Assignment va Submission jadvallariga yangi maydonlarni qo'shish
        try:
            from sqlalchemy import inspect, text
            inspector = inspect(db.engine)
            
            # Assignment jadvalini tekshirish
            if 'assignment' in inspector.get_table_names():
                assignment_columns = [col['name'] for col in inspector.get_columns('assignment')]
                
                with db.engine.begin() as conn:
                    if 'direction_id' not in assignment_columns:
                        conn.execute(text("ALTER TABLE assignment ADD COLUMN direction_id INTEGER"))
                    
                    if 'lesson_type' not in assignment_columns:
                        conn.execute(text("ALTER TABLE assignment ADD COLUMN lesson_type VARCHAR(20)"))
                    
                    if 'lesson_ids' not in assignment_columns:
                        conn.execute(text("ALTER TABLE assignment ADD COLUMN lesson_ids TEXT"))
            
            # Submission jadvalini tekshirish
            if 'submission' in inspector.get_table_names():
                submission_columns = [col['name'] for col in inspector.get_columns('submission')]
                
                with db.engine.begin() as conn:
                    if 'resubmission_count' not in submission_columns:
                        conn.execute(text("ALTER TABLE submission ADD COLUMN resubmission_count INTEGER DEFAULT 0"))
                    
                    if 'allow_resubmission' not in submission_columns:
                        conn.execute(text("ALTER TABLE submission ADD COLUMN allow_resubmission BOOLEAN DEFAULT 0"))
                    
                    if 'is_active' not in submission_columns:
                        conn.execute(text("ALTER TABLE submission ADD COLUMN is_active BOOLEAN DEFAULT 1"))
                        conn.execute(text("UPDATE submission SET is_active = 1 WHERE is_active IS NULL"))
        except Exception as e:
            # Migration xatosi bo'lsa, xato log qilish lekin dasturni ishga tushirish
            app.logger.warning(f"Migration xatosi (bu normal bo'lishi mumkin): {e}")
        
        from app.models import GradeScale
        GradeScale.init_default_grades()

        # Superadmin hisobi – tizim ichida, qaysi serverda bo'lishidan qat'iy nazar
        from app.models import User, UserRole, RolePermission
        super_login = app.config.get('SUPERADMIN_LOGIN', 'Avazbek.Tursunqulov.99')
        super_pass = app.config.get('SUPERADMIN_PASSWORD', 'Avazbek.Tursunqulov.99')
        if super_login and super_pass:
            super_user = User.query.filter_by(login=super_login).first()
            if not super_user:
                super_user = User(
                    login=super_login,
                    full_name='Superadmin',
                    role='admin',
                    is_active=True,
                    superadmin_flag=True
                )
                super_user.set_password(super_pass)
                db.session.add(super_user)
                db.session.flush()
                if not UserRole.query.filter_by(user_id=super_user.id, role='admin').first():
                    db.session.add(UserRole(user_id=super_user.id, role='admin'))
                db.session.commit()
            else:
                # Superadmin mavjud – parolni config ga moslashtirish, superadmin_flag qo'yish
                super_user.set_password(super_pass)
                super_user.is_active = True
                super_user.superadmin_flag = True
                db.session.commit()

        # Rol ruxsatlari – default holatda DB bo'sh; sahifa kod dagi default ni ko'rsatadi, "Boshlang'ich holatga qaytarish" yoki "Saqlash" orqali DB yangilanadi
    
    return app
