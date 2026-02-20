import os
from datetime import timedelta

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'eduspace-secret-key-2024'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///eduspace.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # File upload settings
    UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
    MAX_CONTENT_LENGTH = 220 * 1024 * 1024  # 220 MB (200 MB video + 20 MB bufer: lesson_files, form ma'lumotlari)
    ALLOWED_VIDEO_EXTENSIONS = {'mp4', 'webm', 'ogg', 'mov', 'avi'}
    ALLOWED_SUBMISSION_EXTENSIONS = {'pdf', 'doc', 'docx', 'xls', 'xlsx', 'jpg', 'jpeg', 'png', 'gif', 'bmp', 'txt', 'rtf'}
    MAX_SUBMISSION_SIZE = 2 * 1024 * 1024  # 2 MB max file size for submissions
    
    # CSRF Protection settings
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = 3600  # 1 soat (3600 soniya)
    
    # Superadmin – tizim ichida, hech kim o'chira olmaydi, barcha rollarni boshqaradi
    SUPERADMIN_LOGIN = os.environ.get('SUPERADMIN_LOGIN') or 'Avazbek.Tursunqulov.99'
    SUPERADMIN_PASSWORD = os.environ.get('SUPERADMIN_PASSWORD') or 'Avazbek.Tursunqulov.99'

    # Zoom integratsiyasi (Server-to-Server OAuth)
    ZOOM_ACCOUNT_ID = os.environ.get('ZOOM_ACCOUNT_ID', '')
    ZOOM_CLIENT_ID = os.environ.get('ZOOM_CLIENT_ID', '')
    ZOOM_CLIENT_SECRET = os.environ.get('ZOOM_CLIENT_SECRET', '')
    ZOOM_DURATION_MINUTES = int(os.environ.get('ZOOM_DURATION_MINUTES', '90'))
    ZOOM_TIMEZONE = os.environ.get('ZOOM_TIMEZONE', 'Asia/Tashkent')

    # Session timeout settings (30 daqiqa)
    PERMANENT_SESSION_LIFETIME = timedelta(minutes=30)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SECURE = os.environ.get('FLASK_ENV') == 'production'  # HTTPS da True
    SESSION_COOKIE_SAMESITE = 'Lax'
