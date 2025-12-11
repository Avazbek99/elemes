from app import db, login_manager
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

@login_manager.user_loader
def load_user(id):
    return User.query.get(int(id))


# ==================== FAKULTET ====================
class Faculty(db.Model):
    """Fakultet modeli"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False, unique=True)
    code = db.Column(db.String(20), nullable=False, unique=True)  # IT, IQ, HQ
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    groups = db.relationship('Group', backref='faculty', lazy='dynamic', cascade='all, delete-orphan')
    subjects = db.relationship('Subject', backref='faculty', lazy='dynamic', cascade='all, delete-orphan')


# ==================== GURUH ====================
class Group(db.Model):
    """Guruh modeli"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)  # DI-21, IQ-22
    faculty_id = db.Column(db.Integer, db.ForeignKey('faculty.id'), nullable=False)
    course_year = db.Column(db.Integer, nullable=False)  # 1, 2, 3, 4-kurs
    education_type = db.Column(db.String(20), default='kunduzgi')  # kunduzgi, sirtqi, kechki
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    students = db.relationship('User', backref='group', lazy='dynamic', foreign_keys='User.group_id')
    
    def get_students_count(self):
        return self.students.count()


# ==================== FAN (SUBJECT) ====================
class Subject(db.Model):
    """Fan modeli"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    code = db.Column(db.String(20), nullable=False)  # DA101, MB201
    description = db.Column(db.Text)
    credits = db.Column(db.Integer, default=3)  # Kredit soni
    faculty_id = db.Column(db.Integer, db.ForeignKey('faculty.id'), nullable=False)
    semester = db.Column(db.Integer, default=1)  # 1-8 semestr
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    lessons = db.relationship('Lesson', backref='subject', lazy='dynamic', cascade='all, delete-orphan')
    assignments = db.relationship('Assignment', backref='subject', lazy='dynamic', cascade='all, delete-orphan')
    teacher_assignments = db.relationship('TeacherSubject', backref='subject', lazy='dynamic', cascade='all, delete-orphan')
    schedules = db.relationship('Schedule', backref='subject', lazy='dynamic', cascade='all, delete-orphan')
    
    def get_teacher(self, group_id=None):
        """Ushbu fan uchun biriktirilgan o'qituvchini olish"""
        query = TeacherSubject.query.filter_by(subject_id=self.id)
        if group_id:
            query = query.filter_by(group_id=group_id)
        assignment = query.first()
        return assignment.teacher if assignment else None
    
    def has_lessons_without_content(self):
        """Fanda darslar bor lekin hech birida video yoki fayl yo'qmi?"""
        lessons_count = self.lessons.count()
        if lessons_count == 0:
            return False  # Darslar yo'q bo'lsa, qizil ko'rsatmaymiz
        
        # Darslar bor, lekin hech birida video yoki fayl yo'q
        lessons_with_content = self.lessons.filter(
            (Lesson.video_file != None) | 
            (Lesson.video_url != None) | 
            (Lesson.file_url != None)
        ).count()
        
        return lessons_with_content == 0  # Agar hech bir darsda content yo'q bo'lsa True


# ==================== O'QITUVCHI-FAN BOG'LANISHI ====================
class TeacherSubject(db.Model):
    """O'qituvchini fanga biriktirish"""
    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey('subject.id'), nullable=False)
    group_id = db.Column(db.Integer, db.ForeignKey('group.id'), nullable=False)
    lesson_type = db.Column(db.String(20), default='maruza')  # maruza yoki amaliyot
    academic_year = db.Column(db.String(20))  # 2024-2025
    semester = db.Column(db.Integer, default=1)  # 1 yoki 2
    assigned_at = db.Column(db.DateTime, default=datetime.utcnow)
    assigned_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    
    # Relationships
    teacher = db.relationship('User', foreign_keys=[teacher_id], backref='teaching_subjects')
    group = db.relationship('Group', backref='subject_assignments')
    assigner = db.relationship('User', foreign_keys=[assigned_by])


# ==================== FOYDALANUVCHI ====================
class User(UserMixin, db.Model):
    """Foydalanuvchi modeli"""
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    full_name = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='student')  # admin, teacher, student, dean, accounting
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    phone = db.Column(db.String(20))
    
    # Talaba uchun
    student_id = db.Column(db.String(20), unique=True)  # Talaba ID raqami
    group_id = db.Column(db.Integer, db.ForeignKey('group.id'))
    enrollment_year = db.Column(db.Integer)  # Qabul yili
    
    # O'qituvchi/Dekan uchun
    department = db.Column(db.String(100))
    position = db.Column(db.String(50))
    faculty_id = db.Column(db.Integer, db.ForeignKey('faculty.id'))  # Dekan qaysi fakultetga tegishli
    
    # Relationships
    submissions = db.relationship('Submission', backref='student', lazy='dynamic', foreign_keys='Submission.student_id')
    announcements = db.relationship('Announcement', backref='author', lazy='dynamic')
    managed_faculty = db.relationship('Faculty', foreign_keys=[faculty_id], uselist=False)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def get_role_display(self):
        roles = {
            'admin': 'Administrator',
            'teacher': "O'qituvchi",
            'student': 'Talaba',
            'dean': 'Dekan',
            'accounting': 'Buxgalteriya'
        }
        return roles.get(self.role, self.role)
    
    def has_permission(self, permission):
        permissions = {
            'admin': ['all'],
            'dean': ['view_subjects', 'view_students', 'view_teachers', 'view_reports', 
                    'create_announcement', 'manage_groups', 'assign_teachers'],
            'teacher': ['view_subjects', 'create_lesson', 'create_assignment', 
                       'grade_students', 'view_students', 'create_announcement'],
            'student': ['view_subjects', 'submit_assignment', 'view_grades']
        }
        user_perms = permissions.get(self.role, [])
        return 'all' in user_perms or permission in user_perms
    
    def get_subjects(self):
        """Foydalanuvchi uchun fanlarni olish"""
        if self.role == 'student' and self.group_id:
            # Talaba - guruhiga biriktirilgan fanlar
            return Subject.query.join(TeacherSubject).filter(
                TeacherSubject.group_id == self.group_id
            ).all()
        elif self.role == 'teacher':
            # O'qituvchi - unga biriktirilgan fanlar
            return Subject.query.join(TeacherSubject).filter(
                TeacherSubject.teacher_id == self.id
            ).all()
        return []


# ==================== DARS ====================
class Lesson(db.Model):
    """Dars modeli"""
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text)
    video_url = db.Column(db.String(500))  # External video URL (YouTube, etc.)
    video_file = db.Column(db.String(500))  # Uploaded video file path
    file_url = db.Column(db.String(500))  # Dars materiallari
    duration = db.Column(db.Integer)  # minutes
    order = db.Column(db.Integer, default=0)
    lesson_type = db.Column(db.String(20), default='maruza')  # maruza yoki amaliyot
    subject_id = db.Column(db.Integer, db.ForeignKey('subject.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    
    creator = db.relationship('User', backref='created_lessons')
    
    # Video ko'rish yozuvlari
    views = db.relationship('LessonView', backref='lesson', lazy='dynamic', cascade='all, delete-orphan')


# ==================== DARS KO'RISH YOZUVI ====================
class LessonView(db.Model):
    """Talaba darsni ko'rganligini qayd qilish"""
    id = db.Column(db.Integer, primary_key=True)
    lesson_id = db.Column(db.Integer, db.ForeignKey('lesson.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime)
    attention_checks_passed = db.Column(db.Integer, default=0)  # 3 ta tekshiruvdan o'tganlar
    is_completed = db.Column(db.Boolean, default=False)
    watch_duration = db.Column(db.Integer, default=0)  # seconds
    
    student = db.relationship('User', backref='lesson_views')


# ==================== TOPSHIRIQ ====================
class Assignment(db.Model):
    """Topshiriq modeli"""
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    subject_id = db.Column(db.Integer, db.ForeignKey('subject.id'), nullable=False)
    group_id = db.Column(db.Integer, db.ForeignKey('group.id'))  # Qaysi guruh uchun
    due_date = db.Column(db.DateTime)
    max_score = db.Column(db.Integer, default=100)
    file_required = db.Column(db.Boolean, default=False)  # Fayl yuklash majburiy yoki ixtiyoriy
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    
    # Relationships
    submissions = db.relationship('Submission', backref='assignment', lazy='dynamic', cascade='all, delete-orphan')
    creator = db.relationship('User', backref='created_assignments')
    group = db.relationship('Group', backref='assignments')
    
    def get_submission_count(self):
        return self.submissions.count()


# ==================== JAVOB ====================
class Submission(db.Model):
    """Talaba javobi"""
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    assignment_id = db.Column(db.Integer, db.ForeignKey('assignment.id'), nullable=False)
    content = db.Column(db.Text)
    file_url = db.Column(db.String(500))
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)
    score = db.Column(db.Integer)
    feedback = db.Column(db.Text)
    graded_at = db.Column(db.DateTime)
    graded_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    
    grader = db.relationship('User', foreign_keys=[graded_by], backref='graded_submissions')


# ==================== E'LON ====================
class Announcement(db.Model):
    """E'lon modeli"""
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    is_important = db.Column(db.Boolean, default=False)
    target_roles = db.Column(db.String(100))  # comma-separated: student,teacher,dean
    faculty_id = db.Column(db.Integer, db.ForeignKey('faculty.id'))  # Faqat shu fakultet uchun
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    target_faculty = db.relationship('Faculty', backref='announcements')


# ==================== DARS JADVALI ====================
class Schedule(db.Model):
    """Dars jadvali"""
    id = db.Column(db.Integer, primary_key=True)
    subject_id = db.Column(db.Integer, db.ForeignKey('subject.id'), nullable=False)
    group_id = db.Column(db.Integer, db.ForeignKey('group.id'), nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    day_of_week = db.Column(db.Integer)  # 0=Monday, 6=Sunday
    start_time = db.Column(db.String(5))  # HH:MM
    end_time = db.Column(db.String(5))
    link = db.Column(db.String(500))  # Meeting link (Zoom, Teams, etc.)
    lesson_type = db.Column(db.String(20))  # lecture, practice, lab
    
    group = db.relationship('Group', backref='schedules')
    teacher = db.relationship('User', backref='teaching_schedules')


# ==================== XABAR ====================
class Message(db.Model):
    """Xabar modeli"""
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    sender = db.relationship('User', foreign_keys=[sender_id], backref='sent_messages')
    receiver = db.relationship('User', foreign_keys=[receiver_id], backref='received_messages')


# ==================== PAROLNI TIKLASH TOKENI ====================
class PasswordResetToken(db.Model):
    """Parolni tiklash tokeni"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    token = db.Column(db.String(100), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)
    is_used = db.Column(db.Boolean, default=False)
    
    user = db.relationship('User', backref='password_reset_tokens')


# ==================== BUXGALTERIYA ====================
class StudentPayment(db.Model):
    """Talaba kontrakt va to'lov ma'lumotlari"""
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    contract_amount = db.Column(db.Numeric(15, 2), nullable=False)  # Kontrakt miqdori
    paid_amount = db.Column(db.Numeric(15, 2), default=0)  # To'lagan summasi
    academic_year = db.Column(db.String(20))  # O'quv yili (2024-2025)
    semester = db.Column(db.Integer, default=1)  # Semestr
    notes = db.Column(db.Text)  # Qo'shimcha eslatmalar
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    student = db.relationship('User', backref='payments')
    
    def get_remaining_amount(self):
        """Qolgan to'lov summasi"""
        return float(self.contract_amount) - float(self.paid_amount)
    
    def get_payment_percentage(self):
        """To'lov foizi"""
        if float(self.contract_amount) == 0:
            return 0
        return round((float(self.paid_amount) / float(self.contract_amount)) * 100, 2)


# ==================== BAHOLASH TIZIMI ====================
class GradeScale(db.Model):
    """Baholash tizimi (ballik tizim)"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)  # A, B, C, D, F
    letter = db.Column(db.String(5), nullable=False)  # A, B, C, D, F
    min_score = db.Column(db.Integer, nullable=False)  # Minimal ball
    max_score = db.Column(db.Integer, nullable=False)  # Maksimal ball
    description = db.Column(db.String(100))  # A'lo, Yaxshi, va h.k.
    gpa_value = db.Column(db.Float, default=0)  # GPA qiymati (4.0, 3.5, ...)
    color = db.Column(db.String(20), default='gray')  # green, blue, yellow, orange, red
    order = db.Column(db.Integer, default=0)
    is_passing = db.Column(db.Boolean, default=True)  # O'tish bahosimi
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    @staticmethod
    def get_grade(score, max_score=100):
        """Ball asosida bahoni aniqlash"""
        if max_score == 0:
            return None
        percent = (score / max_score) * 100
        grade = GradeScale.query.filter(
            GradeScale.min_score <= percent,
            GradeScale.max_score >= percent
        ).first()
        return grade
    
    @staticmethod
    def get_all_ordered():
        """Barcha baholarni tartibda olish"""
        return GradeScale.query.order_by(GradeScale.order).all()
    
    @staticmethod
    def init_default_grades():
        """Standart baholarni yaratish"""
        if GradeScale.query.first() is not None:
            return
        
        default_grades = [
            {'letter': 'A', 'name': "A'lo", 'min_score': 86, 'max_score': 100, 'description': "A'lo natija", 'gpa_value': 4.0, 'color': 'green', 'order': 1, 'is_passing': True},
            {'letter': 'B', 'name': 'Yaxshi', 'min_score': 71, 'max_score': 85, 'description': 'Yaxshi natija', 'gpa_value': 3.0, 'color': 'blue', 'order': 2, 'is_passing': True},
            {'letter': 'C', 'name': 'Qoniqarli', 'min_score': 56, 'max_score': 70, 'description': 'Qoniqarli natija', 'gpa_value': 2.0, 'color': 'yellow', 'order': 3, 'is_passing': True},
            {'letter': 'D', 'name': 'Past', 'min_score': 41, 'max_score': 55, 'description': 'Past natija', 'gpa_value': 1.0, 'color': 'orange', 'order': 4, 'is_passing': True},
            {'letter': 'F', 'name': 'Yiqildi', 'min_score': 0, 'max_score': 40, 'description': "O'tmadi", 'gpa_value': 0, 'color': 'red', 'order': 5, 'is_passing': False},
        ]
        
        for g in default_grades:
            grade = GradeScale(**g)
            db.session.add(grade)
        db.session.commit()


# ==================== DEMO MA'LUMOTLAR ====================
def create_demo_data():
    """Demo ma'lumotlarni yaratish"""
    # Accounting accountini har doim yaratish/yangilash
    accounting = User.query.filter_by(email='accounting@university.uz').first()
    if not accounting:
        accounting = User(
            email='accounting@university.uz',
            full_name='Buxgalteriya Bo\'limi',
            role='accounting',
            phone='+998 90 123 45 68'
        )
        accounting.set_password('accounting123')
        db.session.add(accounting)
        db.session.commit()
    
    # Agar database'da allaqachon ma'lumotlar bo'lsa, qolganini yaratmaymiz
    if User.query.filter_by(role='admin').first() is not None:
        return
    
    # ===== FAKULTETLAR =====
    faculties_data = [
        {'name': 'Axborot texnologiyalari fakulteti', 'code': 'IT', 'description': 'Dasturlash va kompyuter fanlari'},
        {'name': 'Iqtisodiyot fakulteti', 'code': 'IQ', 'description': 'Iqtisodiyot va menejment'},
        {'name': 'Huquqshunoslik fakulteti', 'code': 'HQ', 'description': 'Huquq va qonunchilik'},
    ]
    
    faculties = {}
    for f in faculties_data:
        faculty = Faculty(name=f['name'], code=f['code'], description=f['description'])
        db.session.add(faculty)
        faculties[f['code']] = faculty
    
    db.session.commit()
    
    # ===== ADMIN =====
    admin = User(
        email='admin@university.uz',
        full_name='Tizim Administratori',
        role='admin'
    )
    admin.set_password('admin123')
    db.session.add(admin)
    
    # ===== BUXGALTERIYA =====
    accounting = User(
        email='accounting@university.uz',
        full_name='Buxgalteriya Bo\'limi',
        role='accounting',
        phone='+998 90 123 45 68'
    )
    accounting.set_password('accounting123')
    db.session.add(accounting)
    
    # ===== DEKANLAR =====
    deans_data = [
        {'email': 'dean.it@university.uz', 'full_name': 'Sherzod Karimov', 'faculty': 'IT', 'position': 'Dekan'},
        {'email': 'dean.iq@university.uz', 'full_name': 'Aziza Rahimova', 'faculty': 'IQ', 'position': 'Dekan'},
    ]
    
    deans = {}
    for d in deans_data:
        dean = User(
            email=d['email'],
            full_name=d['full_name'],
            role='dean',
            position=d['position'],
            faculty_id=faculties[d['faculty']].id,
            phone='+998 90 123 45 67'
        )
        dean.set_password('dean123')
        deans[d['faculty']] = dean
        db.session.add(dean)
    
    db.session.commit()
    
    # ===== GURUHLAR =====
    groups_data = [
        {'name': 'DI-21', 'faculty': 'IT', 'course_year': 3, 'education_type': 'kunduzgi'},
        {'name': 'DI-22', 'faculty': 'IT', 'course_year': 2, 'education_type': 'kunduzgi'},
        {'name': 'DI-23', 'faculty': 'IT', 'course_year': 1, 'education_type': 'kunduzgi'},
        {'name': 'DS-22', 'faculty': 'IT', 'course_year': 2, 'education_type': 'sirtqi'},
        {'name': 'IQ-21', 'faculty': 'IQ', 'course_year': 3, 'education_type': 'kunduzgi'},
    ]
    
    groups = {}
    for g in groups_data:
        group = Group(
            name=g['name'],
            faculty_id=faculties[g['faculty']].id,
            course_year=g['course_year'],
            education_type=g['education_type']
        )
        db.session.add(group)
        groups[g['name']] = group
    
    db.session.commit()
    
    # ===== O'QITUVCHILAR =====
    teachers_data = [
        {'email': 'a.karimov@university.uz', 'full_name': 'Aziz Karimov', 'department': 'Dasturiy injiniring', 'position': 'Dotsent'},
        {'email': 'b.aliyev@university.uz', 'full_name': 'Bobur Aliyev', 'department': 'Dasturiy injiniring', 'position': "Katta o'qituvchi"},
        {'email': 'd.toshmatov@university.uz', 'full_name': 'Dilshod Toshmatov', 'department': 'Kompyuter fanlari', 'position': 'Professor'},
        {'email': 'n.rahimova@university.uz', 'full_name': 'Nilufar Rahimova', 'department': 'Iqtisodiyot', 'position': 'Dotsent'},
    ]
    
    teachers = []
    for t in teachers_data:
        teacher = User(
            email=t['email'],
            full_name=t['full_name'],
            role='teacher',
            department=t['department'],
            position=t['position'],
            phone='+998 91 234 56 78'
        )
        teacher.set_password('teacher123')
        teachers.append(teacher)
        db.session.add(teacher)
    
    db.session.commit()
    
    # ===== FANLAR =====
    subjects_data = [
        {'name': 'Dasturlash asoslari', 'code': 'DA101', 'faculty': 'IT', 'credits': 4, 'semester': 1},
        {'name': 'Web dasturlash', 'code': 'WD201', 'faculty': 'IT', 'credits': 3, 'semester': 3},
        {'name': "Ma'lumotlar bazasi", 'code': 'MB301', 'faculty': 'IT', 'credits': 4, 'semester': 3},
        {'name': 'Algoritmlar', 'code': 'AL201', 'faculty': 'IT', 'credits': 3, 'semester': 2},
        {'name': 'Kompyuter tarmoqlari', 'code': 'KT401', 'faculty': 'IT', 'credits': 3, 'semester': 4},
        {'name': 'Makroiqtisodiyot', 'code': 'MI101', 'faculty': 'IQ', 'credits': 3, 'semester': 1},
    ]
    
    subjects = {}
    for s in subjects_data:
        subject = Subject(
            name=s['name'],
            code=s['code'],
            faculty_id=faculties[s['faculty']].id,
            credits=s['credits'],
            semester=s['semester'],
            description=f"{s['name']} fani bo'yicha ma'ruzalar va amaliy mashg'ulotlar"
        )
        db.session.add(subject)
        subjects[s['code']] = subject
    
    db.session.commit()
    
    # ===== TALABALAR =====
    students_data = [
        {'email': 'student1@university.uz', 'full_name': 'Dilshod Rahimov', 'student_id': 'ST2021001', 'group': 'DI-21'},
        {'email': 'student2@university.uz', 'full_name': 'Malika Karimova', 'student_id': 'ST2021002', 'group': 'DI-21'},
        {'email': 'student3@university.uz', 'full_name': 'Jasur Toshmatov', 'student_id': 'ST2022001', 'group': 'DI-22'},
        {'email': 'student4@university.uz', 'full_name': 'Nodira Aliyeva', 'student_id': 'ST2022002', 'group': 'DI-22'},
        {'email': 'student5@university.uz', 'full_name': 'Sardor Mahmudov', 'student_id': 'ST2023001', 'group': 'DI-23'},
        {'email': 'student6@university.uz', 'full_name': 'Gulnora Rahimova', 'student_id': 'ST2021003', 'group': 'IQ-21'},
    ]
    
    students = []
    for s in students_data:
        student = User(
            email=s['email'],
            full_name=s['full_name'],
            role='student',
            student_id=s['student_id'],
            group_id=groups[s['group']].id,
            enrollment_year=int('20' + s['group'][-2:])
        )
        student.set_password('student123')
        students.append(student)
        db.session.add(student)
    
    db.session.commit()
    
    # ===== O'QITUVCHI-FAN BIRIKTIRISH =====
    assignments_data = [
        {'teacher': teachers[0], 'subject': 'DA101', 'group': 'DI-23'},
        {'teacher': teachers[0], 'subject': 'WD201', 'group': 'DI-21'},
        {'teacher': teachers[1], 'subject': 'AL201', 'group': 'DI-22'},
        {'teacher': teachers[2], 'subject': 'MB301', 'group': 'DI-21'},
        {'teacher': teachers[2], 'subject': 'KT401', 'group': 'DI-21'},
        {'teacher': teachers[3], 'subject': 'MI101', 'group': 'IQ-21'},
    ]
    
    for a in assignments_data:
        ta = TeacherSubject(
            teacher_id=a['teacher'].id,
            subject_id=subjects[a['subject']].id,
            group_id=groups[a['group']].id,
            academic_year='2024-2025',
            semester=1,
            assigned_by=deans['IT'].id if 'D' in a['group'] else deans['IQ'].id
        )
        db.session.add(ta)
    
    db.session.commit()
    
    # ===== DARSLAR =====
    for code, subject in subjects.items():
        for i in range(1, 6):
            lesson = Lesson(
                title=f"{i}-mavzu: {subject.name}",
                content=f"Bu {subject.name} fanining {i}-mavzusi. Ushbu mavzuda asosiy tushunchalar bilan tanishamiz.",
                duration=80,
                order=i,
                subject_id=subject.id,
                created_by=teachers[0].id
            )
            db.session.add(lesson)
    
    # ===== TOPSHIRIQLAR =====
    for code, subject in list(subjects.items())[:3]:
        for i in range(1, 3):
            assignment = Assignment(
                title=f"Amaliy topshiriq #{i}",
                description=f"{subject.name} bo'yicha {i}-amaliy topshiriq. Barcha vazifalarni bajarib, muddatida topshiring.",
                subject_id=subject.id,
                group_id=groups['DI-21'].id if code != 'MI101' else groups['IQ-21'].id,
                max_score=100,
                due_date=datetime(2024, 12, 15 + i),
                created_by=teachers[0].id
            )
            db.session.add(assignment)
    
    # ===== E'LONLAR =====
    announcements_data = [
        {'title': 'Yakuniy imtihonlar jadvali', 'content': "Hurmatli talabalar! 2024-2025 o'quv yili 1-semestr yakuniy imtihonlari 2024-yil 15-dekabrdan boshlanadi.", 'is_important': True, 'author': deans['IT']},
        {'title': "Kutubxona ish vaqti o'zgarishi", 'content': "Imtihon davrida kutubxona ish vaqti uzaytirildi. Yangi ish vaqti: dushanba-shanba 08:00-22:00.", 'is_important': False, 'author': deans['IT']},
    ]
    
    for a in announcements_data:
        announcement = Announcement(
            title=a['title'],
            content=a['content'],
            is_important=a['is_important'],
            author_id=a['author'].id,
            target_roles='student,teacher,dean'
        )
        db.session.add(announcement)
    
    # ===== DARS JADVALI =====
    schedule_data = [
        {'subject': 'DA101', 'group': 'DI-23', 'teacher': teachers[0], 'day': 0, 'start': '09:00', 'end': '10:30', 'room': '301-xona', 'type': 'lecture'},
        {'subject': 'DA101', 'group': 'DI-23', 'teacher': teachers[0], 'day': 2, 'start': '14:00', 'end': '16:00', 'room': 'Lab-1', 'type': 'lab'},
        {'subject': 'WD201', 'group': 'DI-21', 'teacher': teachers[0], 'day': 1, 'start': '09:00', 'end': '10:30', 'room': '205-xona', 'type': 'lecture'},
        {'subject': 'MB301', 'group': 'DI-21', 'teacher': teachers[2], 'day': 3, 'start': '11:00', 'end': '12:30', 'room': '302-xona', 'type': 'lecture'},
        {'subject': 'AL201', 'group': 'DI-22', 'teacher': teachers[1], 'day': 1, 'start': '14:00', 'end': '15:30', 'room': '201-xona', 'type': 'lecture'},
    ]
    
    for s in schedule_data:
        schedule = Schedule(
            subject_id=subjects[s['subject']].id,
            group_id=groups[s['group']].id,
            teacher_id=s['teacher'].id,
            day_of_week=s['day'],
            start_time=s['start'],
            end_time=s['end'],
            room=s['room'],
            lesson_type=s['type']
        )
        db.session.add(schedule)
    
    db.session.commit()
