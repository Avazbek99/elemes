"""
Hikvision Face Log Server - Production application entry point.
Receives face recognition logs from Hikvision devices and stores in MySQL.

CURL TESTING EXAMPLES:
  # POST JSON (Hikvision-style)
  curl -X POST http://localhost/face-api/receive -H "Content-Type: application/json" -d "{\"personName\":\"John Doe\",\"eventTime\":\"2025-02-21T10:30:00\"}"

  # POST raw JSON
  curl -X POST http://localhost/face-api/receive -d "{\"personName\":\"Jane Smith\"}"

  # GET latest logs
  curl http://localhost/face-api/logs

  # Health check
  curl http://localhost/health
"""
import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Ensure project root is on path when running: python app.py
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from flask import Flask

from config import Config, LOGS_DIR
from models import db, FaceLog
from face_api import face_api_bp


def create_app(config_class=Config):
    """Create and configure the Flask application."""
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Store logs directory in config for routes
    app.config['LOGS_DIR'] = LOGS_DIR
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    # Initialize extensions
    db.init_app(app)

    # Create tables
    with app.app_context():
        db.create_all()

    # Register blueprints
    app.register_blueprint(face_api_bp)

    # Health check
    @app.route('/health')
    def health():
        return {'status': 'ok', 'service': 'face-log-server'}, 200

    return app


def setup_logging(app):
    """Configure rotating file logging."""
    if not app.debug:
        log_level = getattr(logging, app.config.get('LOG_LEVEL', 'INFO').upper(), logging.INFO)
        app.logger.setLevel(log_level)

        log_file = LOGS_DIR / 'app.log'
        handler = RotatingFileHandler(
            log_file,
            maxBytes=app.config.get('LOG_MAX_BYTES', 10 * 1024 * 1024),
            backupCount=app.config.get('LOG_BACKUP_COUNT', 5),
            encoding='utf-8',
        )
        handler.setLevel(log_level)
        formatter = logging.Formatter(
            '[%(asctime)s] %(levelname)s in %(module)s: %(message)s'
        )
        handler.setFormatter(formatter)
        app.logger.addHandler(handler)
        app.logger.info('Face Log Server started')


def main():
    """Run the application with Waitress (Windows production server)."""
    app = create_app()
    setup_logging(app)

    host = app.config.get('HOST', '0.0.0.0')
    port = app.config.get('PORT', 80)
    threads = app.config.get('THREADS', 4)

    app.logger.info('Starting Waitress on %s:%d', host, port)

    try:
        from waitress import serve
        serve(app, host=host, port=port, threads=threads)
    except ImportError:
        app.logger.warning('Waitress not installed. Run: pip install waitress')
        app.logger.info('Falling back to Flask dev server (NOT for production)')
        app.run(host=host, port=port, debug=False, threaded=True)


if __name__ == '__main__':
    main()
