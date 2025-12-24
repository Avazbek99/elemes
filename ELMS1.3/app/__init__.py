import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from config import Config

db = SQLAlchemy()
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
    
    # Context processor for translations
    @app.context_processor
    def inject_translations():
        from flask import session
        from app.utils.translations import get_translation, TRANSLATIONS
        lang = session.get('language', 'uz')
        return {
            't': lambda key: get_translation(key, lang),
            'current_lang': lang,
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
        from app.models import create_demo_data, GradeScale
        if not os.environ.get('FLASK_SKIP_DEMO_DATA'):
            create_demo_data()
            GradeScale.init_default_grades()
    
    return app
