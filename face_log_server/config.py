"""
Configuration for Hikvision Face Log Server.
Uses environment variables for production deployment.
Loads .env file if present (python-dotenv).
"""
import os
from pathlib import Path

# Load .env file
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / '.env')
except ImportError:
    pass

# Base paths
BASE_DIR = Path(__file__).resolve().parent
LOGS_DIR = BASE_DIR / 'logs'

# Ensure logs directory exists
LOGS_DIR.mkdir(parents=True, exist_ok=True)


class Config:
    """Base configuration."""

    SECRET_KEY = os.environ.get('SECRET_KEY') or 'face-log-server-secret-change-in-production'

    # MySQL via PyMySQL: mysql+pymysql://user:password@host:port/database
    # Example .env:
    # MYSQL_HOST=localhost
    # MYSQL_PORT=3306
    # MYSQL_USER=face_log_user
    # MYSQL_PASSWORD=your_secure_password
    # MYSQL_DATABASE=face_logs_db
    MYSQL_HOST = os.environ.get('MYSQL_HOST', 'localhost')
    MYSQL_PORT = os.environ.get('MYSQL_PORT', '3306')
    MYSQL_USER = os.environ.get('MYSQL_USER', 'face_log_user')
    MYSQL_PASSWORD = os.environ.get('MYSQL_PASSWORD', '')
    MYSQL_DATABASE = os.environ.get('MYSQL_DATABASE', 'face_logs_db')

    SQLALCHEMY_DATABASE_URI = (
        os.environ.get('DATABASE_URL')
        or f"mysql+pymysql://{os.environ.get('MYSQL_USER', 'face_log_user')}:{os.environ.get('MYSQL_PASSWORD', '')}@{os.environ.get('MYSQL_HOST', 'localhost')}:{os.environ.get('MYSQL_PORT', '3306')}/{os.environ.get('MYSQL_DATABASE', 'face_logs_db')}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_recycle': 300,
    }

    # Application
    DEBUG = os.environ.get('FLASK_DEBUG', 'false').lower() in ('true', '1', 'yes')
    ENV = os.environ.get('FLASK_ENV', 'production')

    # Logging
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')
    LOG_MAX_BYTES = int(os.environ.get('LOG_MAX_BYTES', 10 * 1024 * 1024))  # 10 MB
    LOG_BACKUP_COUNT = int(os.environ.get('LOG_BACKUP_COUNT', 5))

    # Server
    HOST = os.environ.get('HOST', '0.0.0.0')
    PORT = int(os.environ.get('PORT', 80))
    THREADS = int(os.environ.get('WAITRESS_THREADS', 4))
