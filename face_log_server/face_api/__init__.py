"""
Face API blueprint for Hikvision Face Recognition log reception.
"""
from flask import Blueprint

face_api_bp = Blueprint('face_api', __name__, url_prefix='/face-api')

from . import routes  # noqa: E402, F401
