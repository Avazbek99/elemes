import os
import random
from pathlib import Path
from flask import Flask, redirect, url_for, request, send_from_directory, abort
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect, CSRFError
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
    
    @app.errorhandler(CSRFError)
    def handle_csrf_error(e):
        """CSRF token muddati tugaganda login sahifasiga yo'naltirish."""
        from flask import flash
        flash("Sessiya muddati tugadi. Iltimos, qaytadan kiring.", "warning")
        return redirect(url_for('auth.login'))
    
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
    # Qayta ishga tushirish kerak bo'lsa (yangilanishdan keyin)
    @app.before_request
    def check_restart_required():
        try:
            from app.services.updater import schedule_restart, RESTART_FLAG
            root = Path(app.root_path).resolve().parent
            flag_file = root / RESTART_FLAG
        except Exception:
            return None
        if not flag_file.exists():
            return None
        try:
            version = flag_file.read_text(encoding='utf-8').strip()
        except Exception:
            version = ''
        try:
            flag_file.unlink()
        except Exception:
            pass
        from flask import Response
        html = f'''<!DOCTYPE html><html><head><meta charset="utf-8"><meta http-equiv="refresh" content="5;url=/"><title>Yangilanish</title>
<style>body{{font-family:sans-serif;text-align:center;padding:80px;background:#f5f5f5;}}
.box{{background:#fff;padding:40px;border-radius:8px;max-width:500px;margin:0 auto;box-shadow:0 2px 10px rgba(0,0,0,0.1);}}
h1{{color:#0a0;}}</style></head><body>
<div class="box"><h1>Yangilanish mavjud</h1><p>Versiya: {version}</p><p>Qayta ishga tushirilmoqda (5 soniya)...</p></div></body></html>'''
        schedule_restart()
        return Response(html, status=200, mimetype='text/html; charset=utf-8')

    # Markaz o'zi bloklanganmi (faqat markaz UI; institutlar va /central-api ishlaydi)
    @app.before_request
    def check_center_blocked():
        try:
            is_central = app.config.get('IS_CENTRAL_SERVER') or not (app.config.get('CENTRAL_API_URL') or '').strip()
        except Exception:
            is_central = False
        if not is_central:
            return None
        try:
            from app.central_api import get_center_block_status
            st = get_center_block_status()
        except Exception:
            return None
        if not st.get('blocked'):
            return None
        path = (request.path or '').rstrip('/')
        allow_paths = ('/static', '/central-api', '/admin/update', '/auth/login', '/auth/logout', '/.well-known')
        if any(path.startswith(p) for p in allow_paths):
            return None
        reason = st.get('block_reason') or 'Markaz vaqtincha bloklangan.'
        from flask import Response
        html = f'''<!DOCTYPE html><html><head><meta charset="utf-8"><title>Tizim bloklangan</title>
<style>body{{font-family:sans-serif;text-align:center;padding:80px;background:#f5f5f5;}}
.box{{background:#fff;padding:40px;border-radius:8px;max-width:500px;margin:0 auto;box-shadow:0 2px 10px rgba(0,0,0,0.1);}}
h1{{color:#c00;}}p{{color:#666;}}</style></head><body>
<div class="box"><h1>Tizim bloklangan</h1><p>{reason}</p>
<p>Tizim Administratorlari bilan bog'laning.</p><p><a href="/admin/update">Tizim yangilanishi (blokni olish)</a></p></div></body></html>'''
        return Response(html, status=403, mimetype='text/html; charset=utf-8')

    # Markazdan bloklash va ruxsat tekshiruvi (central-api uchun o'tkazib yuborish)
    @app.before_request
    def check_central_block_and_permission():
        from app.services.central_client import is_central_enabled, get_status, check_blueprint_permission
        if not is_central_enabled():
            return None
        # Ham markaz ham institut bo'lgan server hech qachon bloklanmaydi
        try:
            is_central = app.config.get('IS_CENTRAL_SERVER') or not (app.config.get('CENTRAL_API_URL') or '').strip()
            if not is_central and (app.config.get('CENTRAL_API_URL') or '').strip():
                from urllib.parse import urlparse
                central_host = urlparse((app.config.get('CENTRAL_API_URL') or '').strip()).netloc.split(':')[0].lower()
                request_host = (request.host or '').split(':')[0].lower()
                if central_host and request_host and central_host == request_host:
                    is_central = True  # CENTRAL_API_URL o'zimizga qaraydi – markaz rejimi
        except Exception:
            is_central = False
        if is_central:
            return None
        path = (request.path or '').rstrip('/')
        skip_paths = ('/static', '/face-api/receive', '/face-api/receive.php', '/face-api/ping', '/.well-known', '/central-api')
        if any(path.startswith(p) for p in skip_paths):
            return None
        status = get_status(use_cache=True)
        if status.get('blocked'):
            reason = status.get('block_reason') or 'Tizim vaqtincha bloklangan.'
            from flask import Response
            html = f'''<!DOCTYPE html><html><head><meta charset="utf-8"><title>Tizim bloklangan</title>
<style>body{{font-family:sans-serif;text-align:center;padding:80px;background:#f5f5f5;}}
.box{{background:#fff;padding:40px;border-radius:8px;max-width:500px;margin:0 auto;box-shadow:0 2px 10px rgba(0,0,0,0.1);}}
h1{{color:#c00;}}p{{color:#666;}}</style></head><body>
<div class="box"><h1>Tizim bloklangan</h1><p>{reason}</p>
<p>Tizim Administratorlari bilan bog'laning.</p></div></body></html>'''
            return Response(html, status=403, mimetype='text/html; charset=utf-8')
        # Ruxsat tekshiruvi – blueprint bo'yicha
        bp = request.blueprint
        if bp and not check_blueprint_permission(bp):
            from flask import redirect, url_for
            try:
                return redirect(url_for('main.dashboard'))
            except Exception:
                from flask import abort
                abort(403)

    # Session timeout middleware (central-api / SSE uchun session kerak emas)
    @app.before_request
    def make_session_permanent():
        if (request.path or '').startswith('/central-api'):
            return None
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
    
    # Custom Jinja2 filter for Toshkent time
    @app.template_filter('to_tashkent_time')
    def to_tashkent_time_filter(value):
        """DB dagi UTC vaqtni Toshkent (UTC+5) da ko'rsatish. String (SQLite) yoki datetime qabul qiladi."""
        if value is None:
            return None
        from datetime import datetime, timedelta, timezone
        dt = value
        if isinstance(dt, str):
            s = dt.strip().replace('Z', '+00:00')
            try:
                if '+05:00' in s or '+00:00' in s:
                    dt = datetime.fromisoformat(s)
                    if dt.tzinfo:
                        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
                else:
                    dt = datetime.strptime(s[:19], '%Y-%m-%d %H:%M:%S') if ' ' in s[:19] else datetime.strptime(s[:19], '%Y-%m-%dT%H:%M:%S')
            except (ValueError, TypeError):
                return value
        elif getattr(dt, 'tzinfo', None) is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt + timedelta(hours=5)
    
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
        # Markaziy ruxsatlar – menu yashirish uchun
        central_has_permission = lambda p: True
        try:
            from app.services.central_client import is_central_enabled, has_permission as _hp
            if is_central_enabled():
                central_has_permission = _hp
        except Exception:
            pass

        return {
            't': lambda key, **kwargs: get_translation(key, lang, **kwargs),
            't_lang': lambda key, l, **kwargs: get_translation(key, l, **kwargs),
            'current_lang': lang,
            'central_has_permission': central_has_permission,
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
    from app.face_api import face_api_bp
    from app.attendance import attendance_bp
    from app.central_api import central_bp

    # Let's Encrypt ACME http-01 validation (win-acme)
    acme_dir = Path(app.root_path).resolve().parent / '.well-known' / 'acme-challenge'

    @app.route('/.well-known/acme-challenge/<path:filename>')
    def acme_challenge(filename):
        """win-acme/Let's Encrypt tekshiruv fayllarini xizmat qilish."""
        if not acme_dir.exists():
            abort(404)
        path = (acme_dir / filename).resolve()
        if not str(path).startswith(str(acme_dir.resolve())) or not path.exists():
            abort(404)
        return send_from_directory(acme_dir, filename, mimetype='text/plain')

    app.register_blueprint(main.bp)
    app.register_blueprint(auth.bp)
    app.register_blueprint(admin.bp)
    app.register_blueprint(dean.bp)
    app.register_blueprint(courses.bp)
    app.register_blueprint(api.bp)
    app.register_blueprint(accounting.bp)
    app.register_blueprint(face_api_bp)
    app.register_blueprint(attendance_bp)
    app.register_blueprint(central_bp)

    # Hikvision qurilmalari va markaziy API (institutlar ulanishi) – CSRF dan ozod
    csrf.exempt(face_api_bp)
    csrf.exempt(central_bp)
    
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

            # FaceLog jadvaliga yangi ustunlar
            if 'face_logs' in inspector.get_table_names():
                fl_cols = [col['name'] for col in inspector.get_columns('face_logs')]
                with db.engine.begin() as conn:
                    if 'device_employee_id' not in fl_cols:
                        conn.execute(text("ALTER TABLE face_logs ADD COLUMN device_employee_id VARCHAR(50)"))
                    if 'picture_path' not in fl_cols:
                        conn.execute(text("ALTER TABLE face_logs ADD COLUMN picture_path VARCHAR(255)"))
                    if 'direction' not in fl_cols:
                        conn.execute(text("ALTER TABLE face_logs ADD COLUMN direction VARCHAR(10) DEFAULT 'IN'"))

                # User jadvaliga employee_code
                if 'user' in inspector.get_table_names():
                    user_cols = [col['name'] for col in inspector.get_columns('user')]
                    with db.engine.begin() as conn:
                        if 'employee_code' not in user_cols:
                            conn.execute(text("ALTER TABLE user ADD COLUMN employee_code VARCHAR(50)"))
                # Message jadvaliga reply_to_id, is_pinned (chat javob/qilish)
                if 'message' in inspector.get_table_names():
                    msg_cols = [col['name'] for col in inspector.get_columns('message')]
                    with db.engine.begin() as conn:
                        if 'reply_to_id' not in msg_cols:
                            conn.execute(text("ALTER TABLE message ADD COLUMN reply_to_id INTEGER"))
                        if 'is_pinned' not in msg_cols:
                            conn.execute(text("ALTER TABLE message ADD COLUMN is_pinned BOOLEAN DEFAULT 0"))
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

        # Davomat – har kuni 00:05 da kunlik hisoblash (Toshkent vaqti uchun TZ=Asia/Tashkent qo'yiladi)
        try:
            from apscheduler.schedulers.background import BackgroundScheduler
            from app.services.attendance_service import compute_daily_attendance
            from datetime import date, timedelta

            def _run_daily_attendance():
                with app.app_context():
                    try:
                        yesterday = date.today() - timedelta(days=1)
                        compute_daily_attendance(yesterday)
                        app.logger.info("Daily attendance computed for %s", yesterday)
                    except Exception as e:
                        app.logger.exception("Daily attendance compute error: %s", e)

            scheduler = BackgroundScheduler()
            scheduler.add_job(_run_daily_attendance, 'cron', hour=0, minute=5, id='daily_attendance')
            scheduler.start()
            app.logger.info("APScheduler: daily attendance job at 00:05 registered")
        except Exception as e:
            app.logger.warning("APScheduler not started: %s", e)

    # Markazda yangi versiya faqat qo'lda: flask release
    import click

    @app.cli.command('release')
    def release_command():
        """Yangi versiya yaratish: zip, version.json yangilash, institutlarga yangilanish xabari."""
        with app.app_context():
            from app.services.release_builder import build_and_publish
            if build_and_publish(app):
                click.echo("Release yaratildi. Institutlar yangilanish xabarini oldi.")
            else:
                click.echo("Xato: release yaratilmadi (CENTRAL_PUBLIC_URL tekshiring).", err=True)

    @app.cli.command('db-stamp-head')
    def db_stamp_head_command():
        """Bazadagi migratsiya versiyasini joriy head ga moslashtirish (revision topilmasa xato bo'lsa)."""
        with app.app_context():
            from flask_migrate import stamp
            stamp(revision='head')
            click.echo("Baza versiyasi joriy head ga moslashtirildi.")

    @app.cli.command('db-fix-version')
    def db_fix_version_command():
        """Avval upgrade; agar 'revision topilmayapti' xatosi bo'lsa, stamp head bajarish."""
        with app.app_context():
            from flask_migrate import upgrade, stamp
            try:
                upgrade()
                click.echo("Migratsiyalar joriy.")
            except Exception as e:
                err_msg = str(e)
                if "Can't locate revision" in err_msg or "revision" in err_msg.lower():
                    click.echo("Bazadagi migratsiya versiyasi joriy fayllarda yo'q. Stamp head bajarilmoqda...")
                    stamp(revision='head')
                    click.echo("Baza versiyasi joriy head ga moslashtirildi.")
                else:
                    raise

    @app.cli.command('check-update')
    def check_update_command():
        """Institut: yangilanish mavjudligini qo'lda tekshirish (joriy va so'nggi versiya)."""
        with app.app_context():
            from app.services.sse_client import is_enabled
            if not is_enabled(app):
                click.echo("Markazga ulanish yo'q (CENTRAL_API_URL yoki mahalliy version.json).", err=True)
                return
            from app.services.updater import get_latest_version_info, get_current_version, is_central_newer
            current = get_current_version()
            v = get_latest_version_info()
            if not v:
                click.echo("So'nggi versiya olinmadi.")
                return
            latest = (v.get('version') or '').strip()
            click.echo("Joriy versiya:  %s" % current)
            click.echo("So'nggi versiya: %s" % latest)
            if is_central_newer(latest, current):
                click.echo("Yangilanish mavjud. O'rnatish: flask run-update")
            else:
                click.echo("Platforma joriy.")

    @app.cli.command('run-update')
    def run_update_command():
        """Institut: yangilanishni qo'lda o'rnatish (vaqt oynasiga qaramay)."""
        with app.app_context():
            from app.services.sse_client import is_enabled
            if not is_enabled(app):
                click.echo("Markazga ulanish yo'q.", err=True)
                return
            from app.services.updater import run_update, schedule_restart
            if run_update():
                click.echo("Yangilanish o'rnatildi. Qayta ishga tushirilmoqda...")
                schedule_restart()
            else:
                click.echo("Yangilanish o'tkazilmadi (so'nggi versiya allaqachon o'rnatilgan yoki xato).", err=True)

    return app
