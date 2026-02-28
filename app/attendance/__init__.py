"""Davomat va KPI blueprint – Hikvision face log asosida."""
from flask import Blueprint

attendance_bp = Blueprint('attendance', __name__, url_prefix='/admin')

from app.attendance import routes  # noqa: E402, F401
