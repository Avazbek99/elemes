import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'eduspace-secret-key-2024'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///eduspace.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # File upload settings
    UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
    MAX_CONTENT_LENGTH = 200 * 1024 * 1024  # 200 MB max file size
    ALLOWED_VIDEO_EXTENSIONS = {'mp4', 'webm', 'ogg', 'mov', 'avi'}
    ALLOWED_SUBMISSION_EXTENSIONS = {'pdf', 'doc', 'docx', 'xls', 'xlsx', 'jpg', 'jpeg', 'png', 'gif', 'bmp', 'txt', 'rtf'}
    MAX_SUBMISSION_SIZE = 2 * 1024 * 1024  # 2 MB max file size for submissions
    
    # CSRF Protection settings
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = 3600  # 1 soat (3600 soniya)
