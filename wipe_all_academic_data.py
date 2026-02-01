#!/usr/bin/env python
"""Barcha dekan, talaba, o'qituvchi, fakultet, guruh, fan va bog'liq ma'lumotlarni o'chirish.

Ishga tushirish: python wipe_all_academic_data.py
Eslatma: Admin va GradeScale saqlanadi (tizimga kirish va baholash uchun).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from app.models import (
    User, UserRole, Faculty, Group, Direction, Subject, TeacherSubject,
    Submission, LessonView, Announcement, StudentPayment, DirectionCurriculum,
    Schedule, Lesson, Assignment, Message, PasswordResetToken
)


def wipe_all_academic_data():
    app = create_app()
    
    with app.app_context():
        print("Barcha akademik ma'lumotlar o'chirilmoqda...")
        
        # 1. Bog'liq yozuvlarni o'chirish (FK tartibida)
        n_sub = Submission.query.delete()
        n_lv = LessonView.query.delete()
        n_sp = StudentPayment.query.delete()
        n_msg = Message.query.delete()
        n_ann = Announcement.query.delete()
        n_pt = PasswordResetToken.query.delete()
        n_ts = TeacherSubject.query.delete()
        n_sched = Schedule.query.delete()
        n_less = Lesson.query.delete()
        n_assign = Assignment.query.delete()
        n_curr = DirectionCurriculum.query.delete()
        
        db.session.commit()
        print(f"  Submissions: {n_sub}, LessonView: {n_lv}, StudentPayment: {n_sp}")
        print(f"  Message: {n_msg}, Announcement: {n_ann}, PasswordResetToken: {n_pt}")
        print(f"  TeacherSubject: {n_ts}, Schedule: {n_sched}, Lesson: {n_less}")
        print(f"  Assignment: {n_assign}, DirectionCurriculum: {n_curr}")
        
        # 2. Barcha User'lardan group_id va faculty_id ni null qilish (Guruh/Fakultet o'chirishdan oldin)
        User.query.update({User.group_id: None, User.faculty_id: None}, synchronize_session=False)
        db.session.commit()
        
        # 3. Guruhlar
        n_gr = Group.query.delete()
        db.session.commit()
        print(f"  {n_gr} ta guruh o'chirildi.")
        
        # 4. Yo'nalishlar
        n_dir = Direction.query.delete()
        db.session.commit()
        print(f"  {n_dir} ta yo'nalish o'chirildi.")
        
        # 5. Fanlar
        n_subj = Subject.query.delete()
        db.session.commit()
        print(f"  {n_subj} ta fan o'chirildi.")
        
        # 6. Fakultetlar
        n_fac = Faculty.query.delete()
        db.session.commit()
        print(f"  {n_fac} ta fakultet o'chirildi.")
        
        # 7. Dekan, talaba, o'qituvchi, buxgalter (admin saqlanadi)
        user_ids_to_delete = []
        for u in User.query.all():
            roles = u.get_roles()
            if not roles:
                roles = [u.role] if u.role else []
            if 'admin' not in roles:
                user_ids_to_delete.append(u.id)
        
        if user_ids_to_delete:
            UserRole.query.filter(UserRole.user_id.in_(user_ids_to_delete)).delete(synchronize_session=False)
            User.query.filter(User.id.in_(user_ids_to_delete)).delete(synchronize_session=False)
            db.session.commit()
            print(f"  {len(user_ids_to_delete)} ta foydalanuvchi (talaba, o'qituvchi, dekan, buxgalter) o'chirildi.")
        
        print("Barcha akademik ma'lumotlar tozalandi.")


if __name__ == '__main__':
    wipe_all_academic_data()
