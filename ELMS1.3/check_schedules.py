from app import create_app, db
from app.models import Schedule, Subject
from datetime import datetime

app = create_app()
with app.app_context():
    schedules = Schedule.query.all()
    print("Schedules in DB:")
    for s in schedules:
        subject = Subject.query.get(s.subject_id)
        print(f"ID: {s.id}, DateCode/Weekday: {s.day_of_week}, Subject: {subject.name if subject else 'Unknown'}, Time: {s.start_time}")
