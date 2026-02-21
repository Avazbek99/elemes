"""
Hikvision yuz tanilash API – qurilmalardan log qabul qilish.
Faqat superadmin ko‘rishi mumkin bo‘lgan amallar alohida himoyalangan.
"""
from flask import Blueprint

face_api_bp = Blueprint('face_api', __name__, url_prefix='/face-api')

from app.face_api import routes  # noqa: E402, F401
