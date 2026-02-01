#!/usr/bin/env python
"""Demo ma'lumotlarni bazadan o'chirish skripti.

Namuna Excel fayllaridan import qilingan demo talabalar, xodimlar, fanlar va h.k.larni o'chiradi.
Ishga tushirish: python clean_demo_data.py
"""
import os
import sys

# Loyiha ildizini path ga qo'shish
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from app.models import (
    User, UserRole, Faculty, Group, Direction, Subject, TeacherSubject,
    Submission, LessonView, Announcement, StudentPayment, DirectionCurriculum,
    Schedule, Lesson, Assignment, Message, PasswordResetToken
)


# Namuna fayllardan olingan demo ma'lumotlar ro'yxati
DEMO_STUDENT_IDS = {'ST2024001', 'ST2024002'}
DEMO_STUDENT_EMAILS = {'vali@example.com', 'zuhra@example.com'}
DEMO_STAFF_LOGINS = {'sherzod', 'valijon', 'aziza', 'vali'}
DEMO_ADMIN_LOGIN = 'admin'
DEMO_ADMIN_NAME = 'TURSUNQULOV AVAZBEK'
DEMO_SUBJECT_NAMES = {
    "Dasturlash asoslari",
    "Ma'lumotlar bazasi",
    "Web dasturlash",
    "Amaliy matematika",
    "Iqtisodiy ta'limotlar tarixi",
    "Iqtisodiyot nazariyasi",
    "O'zbek (rus) tili",
    "Xorijiy til",
    "Iqtisodiyotda axborot kommunikasiya texnol",
}


def get_demo_users(app):
    """Demo foydalanuvchilarni topish"""
    with app.app_context():
        demo_user_ids = []
        
        # Demo talabalar (student_id yoki email bo'yicha)
        students = User.query.filter(User.role == 'student').all()
        for u in students:
            if (u.student_id and u.student_id in DEMO_STUDENT_IDS) or \
               (u.email and u.email.lower() in DEMO_STUDENT_EMAILS):
                demo_user_ids.append(u.id)
        
        # Demo xodimlar (login bo'yicha - admin dan tashqari)
        staff_logins = User.query.filter(User.role != 'student').filter(
            User.login.in_(DEMO_STAFF_LOGINS)
        ).all()
        for u in staff_logins:
            demo_user_ids.append(u.id)
        
        # Demo admin - faqat boshqa admin bo'lsa o'chiramiz
        admin_user = User.query.filter_by(login=DEMO_ADMIN_LOGIN).first()
        if admin_user and admin_user.full_name == DEMO_ADMIN_NAME:
            admin_count = User.query.join(UserRole).filter(
                UserRole.role == 'admin'
            ).count()
            # UserRole dan ham tekshiramiz
            from sqlalchemy import func
            users_with_admin = db.session.query(User.id).join(UserRole, User.id == UserRole.user_id).filter(
                UserRole.role == 'admin'
            ).distinct().count()
            if users_with_admin > 1:
                demo_user_ids.append(admin_user.id)
            else:
                print(f"  (Admin '{DEMO_ADMIN_LOGIN}' o'chirilmadi - boshqa admin yo'q)")
        
        return list(set(demo_user_ids))


def clean_demo_data():
    app = create_app()
    
    with app.app_context():
        print("Demo ma'lumotlarni o'chirish boshlandi...")
        
        # 1. Demo foydalanuvchilarni topish
        demo_ids = get_demo_users(app)
        demo_users = User.query.filter(User.id.in_(demo_ids)).all() if demo_ids else []
        
        if not demo_users:
            print("Demo foydalanuvchilar topilmadi.")
        else:
            print(f"Topilgan demo foydalanuvchilar: {[u.login or u.student_id or u.full_name for u in demo_users]}")
            
            # 2. Bog'liq yozuvlarni o'chirish (foreign key tartibida)
            for user in demo_users:
                uid = user.id
                # Submissions
                Submission.query.filter_by(student_id=uid).delete()
                # LessonView
                LessonView.query.filter_by(student_id=uid).delete()
                # StudentPayment
                StudentPayment.query.filter_by(student_id=uid).delete()
                # TeacherSubject
                TeacherSubject.query.filter_by(teacher_id=uid).delete()
                # Announcements (muallif)
                Announcement.query.filter_by(author_id=uid).delete()
                # Messages (yuboruvchi yoki qabul qiluvchi)
                Message.query.filter(
                    (Message.sender_id == uid) | (Message.receiver_id == uid)
                ).delete()
                # Graded submissions (graded_by)
                Submission.query.filter_by(graded_by=uid).update({Submission.graded_by: None})
                # PasswordResetToken
                PasswordResetToken.query.filter_by(user_id=uid).delete()
                # Lessons/Assignments created_by - NULL qilamiz (o'chirmaslik)
                Lesson.query.filter_by(created_by=uid).update({Lesson.created_by: None})
                Assignment.query.filter_by(created_by=uid).update({Assignment.created_by: None})
            
            db.session.commit()
            
            # 3. Foydalanuvchilarni o'chirish (UserRole cascade)
            for user in demo_users:
                db.session.delete(user)
            db.session.commit()
            print(f"  {len(demo_users)} ta demo foydalanuvchi o'chirildi.")
        
        # 4. Demo fanlarni o'chirish
        demo_subjects = Subject.query.filter(Subject.name.in_(DEMO_SUBJECT_NAMES)).all()
        if demo_subjects:
            for subj in demo_subjects:
                # DirectionCurriculum
                DirectionCurriculum.query.filter_by(subject_id=subj.id).delete()
                # Schedule
                Schedule.query.filter_by(subject_id=subj.id).delete()
                # TeacherSubject
                TeacherSubject.query.filter_by(subject_id=subj.id).delete()
                db.session.delete(subj)
            db.session.commit()
            print(f"  {len(demo_subjects)} ta demo fan o'chirildi: {[s.name for s in demo_subjects]}")
        else:
            print("Demo fanlar topilmadi.")
        
        # 5. Bo'sh guruhlar (talabasiz) - faqat demo dan qolganlari
        empty_groups = [g for g in Group.query.all() if g.students.count() == 0]
        deleted_groups = 0
        for g in empty_groups:
            Lesson.query.filter_by(group_id=g.id).delete()
            Assignment.query.filter_by(group_id=g.id).delete()
            Schedule.query.filter_by(group_id=g.id).delete()
            TeacherSubject.query.filter_by(group_id=g.id).delete()
            db.session.delete(g)
            deleted_groups += 1
        if deleted_groups:
            db.session.commit()
            print(f"  {deleted_groups} ta bo'sh guruh o'chirildi.")
        
        print("Demo ma'lumotlar tozalandi.")


if __name__ == '__main__':
    clean_demo_data()
