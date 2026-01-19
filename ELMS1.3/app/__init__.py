import os
from flask import Flask
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

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    
    # Create uploads folder
    os.makedirs(app.config.get('UPLOAD_FOLDER', 'uploads'), exist_ok=True)
    os.makedirs(os.path.join(app.config.get('UPLOAD_FOLDER', 'uploads'), 'videos'), exist_ok=True)
    os.makedirs(os.path.join(app.config.get('UPLOAD_FOLDER', 'uploads'), 'submissions'), exist_ok=True)
    os.makedirs(os.path.join(app.config.get('UPLOAD_FOLDER', 'uploads'), 'lesson_files'), exist_ok=True)
    
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)
    
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
    
    # Context processor for translations
    @app.context_processor
    def inject_global_data():
        from flask import session
        from flask_login import current_user
        from app.utils.translations import get_translation
        from app.models import Message
        
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
                
        return {
            't': lambda key: get_translation(key, lang),
            'current_lang': lang,
            'unread_msg_count': unread_msg_count,
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
        
        from app.models import create_demo_data, GradeScale
        if not os.environ.get('FLASK_SKIP_DEMO_DATA'):
            create_demo_data()
            GradeScale.init_default_grades()
    
    return app
