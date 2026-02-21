"""
Database models for Hikvision Face Log Server.
"""
from datetime import datetime

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class FaceLog(db.Model):
    """
    Stores face recognition event logs from Hikvision devices.
    """

    __tablename__ = 'face_logs'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    person_name = db.Column(db.String(150), nullable=True, index=True)
    event_time = db.Column(db.DateTime, nullable=True, index=True)
    device_ip = db.Column(db.String(50), nullable=True, index=True)
    raw_data = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self):
        return {
            'id': self.id,
            'person_name': self.person_name,
            'event_time': self.event_time.isoformat() if self.event_time else None,
            'device_ip': self.device_ip,
            'raw_data': self.raw_data[:500] + '...' if self.raw_data and len(self.raw_data) > 500 else self.raw_data,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
