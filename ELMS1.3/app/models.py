from app import db, login_manager
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date, timedelta

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


# ==================== YO'NALISH (DIRECTION) ====================
class Direction(db.Model):
    """Akademik yo'nalish modeli"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)  # Dasturiy injiniring
    code = db.Column(db.String(20), nullable=False)  # DI (15 tagacha belgi)
    description = db.Column(db.Text)
    faculty_id = db.Column(db.Integer, db.ForeignKey('faculty.id'), nullable=False)
    course_year = db.Column(db.Integer, nullable=False)  # 1, 2, 3, 4, 5-kurs
    semester = db.Column(db.Integer, nullable=False)  # 1-10 semestr
    education_type = db.Column(db.String(20), nullable=False, default='kunduzgi')  # kunduzgi, sirtqi, masofaviy, kechki
    enrollment_year = db.Column(db.Integer)  # Qabul yili (masalan: 2024)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    faculty = db.relationship('Faculty', backref='directions')
    groups = db.relationship('Group', backref='direction', lazy='dynamic')
    curriculum_items = db.relationship('DirectionCurriculum', backref='direction', lazy='dynamic', cascade='all, delete-orphan')


# ==================== GURUH ====================
class Group(db.Model):
    """Guruh modeli"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)  # DI-21, IQ-22
    faculty_id = db.Column(db.Integer, db.ForeignKey('faculty.id'), nullable=False)
    direction_id = db.Column(db.Integer, db.ForeignKey('direction.id'), nullable=True)  # Yo'nalishga biriktirish
    course_year = db.Column(db.Integer, nullable=False)  # 1, 2, 3, 4-kurs
    education_type = db.Column(db.String(20), default='kunduzgi')  # kunduzgi, sirtqi, kechki
    description = db.Column(db.Text)  # Guruh haqida tavsif
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
    code = db.Column(db.String(20), nullable=True)  # Fan kodi (ixtiyoriy)
    description = db.Column(db.Text)
    credits = db.Column(db.Integer, default=3)  # Kredit soni
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
    
    def check_curriculum_completion(self, direction_id=None, teacher_id=None):
        """O'quv reja bo'yicha darslar to'liqligini tekshirish
        Args:
            direction_id: Yo'nalish ID
            teacher_id: O'qituvchi ID (agar berilgan bo'lsa, faqat shu o'qituvchiga biriktirilgan dars turlari tekshiriladi)
        Returns: {'has_issue': bool, 'warnings': list}
        """
        if not direction_id:
            return {'has_issue': False, 'warnings': []}
        
        # Ushbu yo'nalish uchun o'quv rejani olish
        curriculum = DirectionCurriculum.query.filter_by(
            direction_id=direction_id,
            subject_id=self.id
        ).first()
        
        if not curriculum:
            return {'has_issue': False, 'warnings': []}
        
        # Agar teacher_id berilgan bo'lsa, faqat shu o'qituvchiga biriktirilgan dars turlarini olish
        teacher_lesson_types = None
        if teacher_id:
            # Ushbu yo'nalishdagi guruhlar
            direction_group_ids = [g.id for g in db.session.query(Group).filter_by(direction_id=direction_id).all()]
            
            # O'qituvchiga biriktirilgan dars turlari
            teacher_assignments = db.session.query(TeacherSubject).filter(
                TeacherSubject.teacher_id == teacher_id,
                TeacherSubject.subject_id == self.id,
                TeacherSubject.group_id.in_(direction_group_ids)
            ).all()
            
            # Dars turlarini normallashtirish (lab -> laboratoriya, course_work -> kurs_ishi)
        teacher_lesson_types = set()
        for ta in teacher_assignments:
            if ta.lesson_type:
                l_type = ta.lesson_type.lower().strip()
                matched = False
                
                # Laboratoriya (lab, lob, laboratoriya, lobaratoriya)
                if 'lab' in l_type or 'lob' in l_type:
                    teacher_lesson_types.add('laboratoriya')
                    matched = True
                
                # Kurs ishi (kurs, course)
                if 'kurs' in l_type or 'course' in l_type:
                    teacher_lesson_types.add('kurs_ishi')
                    matched = True
                
                # Amaliyot (amaliyot, amal, practice) - bu Lobaratoriya va Kurs ishini ham o'z ichiga oladi
                if 'amal' in l_type or 'prac' in l_type:
                    teacher_lesson_types.add('amaliyot')
                    teacher_lesson_types.add('laboratoriya')
                    teacher_lesson_types.add('kurs_ishi')
                    matched = True
                
                # Maruza (maruza, lecture, ma'ruza)
                if 'maru' in l_type or 'lect' in l_type:
                    teacher_lesson_types.add('maruza')
                    matched = True
                
                # Seminar
                if 'sem' in l_type:
                    teacher_lesson_types.add('seminar')
                    matched = True
                
                if not matched:
                    teacher_lesson_types.add(l_type)
        
        warnings = []
        has_issue = False
        
        # Har bir dars turi uchun tekshirish (har bir mavzu = 2 soat = 1 para)
        lesson_types_check = {
            'maruza': {
                'name': 'Maruza',
                'hours': curriculum.hours_maruza or 0,
                'required_topics': (curriculum.hours_maruza or 0) / 2.0,
                'actual_topics': 0
            },
            'amaliyot': {
                'name': 'Amaliyot',
                'hours': curriculum.hours_amaliyot or 0,
                'required_topics': (curriculum.hours_amaliyot or 0) / 2.0,
                'actual_topics': 0
            },
            'laboratoriya': {
                'name': 'Laboratoriya',
                'hours': curriculum.hours_laboratoriya or 0,
                'required_topics': (curriculum.hours_laboratoriya or 0) / 2.0,
                'actual_topics': 0
            },
            'seminar': {
                'name': 'Seminar',
                'hours': curriculum.hours_seminar or 0,
                'required_topics': (curriculum.hours_seminar or 0) / 2.0,
                'actual_topics': 0
            },
            'kurs_ishi': {
                'name': 'Kurs ishi',
                'hours': curriculum.hours_kurs_ishi or 0,
                'required_topics': (curriculum.hours_kurs_ishi or 0) / 2.0,
                'actual_topics': 0
            }
        }
        
        # Ushbu yo'nalish uchun mavjud darslarni sanash
        lessons = Lesson.query.filter_by(
            subject_id=self.id,
            direction_id=direction_id
        ).all()
        
        for lesson in lessons:
            if lesson.lesson_type in lesson_types_check:
                lesson_types_check[lesson.lesson_type]['actual_topics'] += 1
        
        # Har bir dars turi uchun tekshirish
        for lesson_type, data in lesson_types_check.items():
            if data['hours'] > 0:  # Faqat soat belgilangan dars turlarini tekshirish
                # Agar teacher_id berilgan bo'lsa, faqat o'qituvchiga biriktirilgan dars turlarini tekshirish
                if teacher_lesson_types is not None and lesson_type not in teacher_lesson_types:
                    continue  # Bu dars turi o'qituvchiga biriktirilmagan, o'tkazib yuborish
                
                required = data['required_topics']
                actual = data['actual_topics']
                
                if lesson_type == 'kurs_ishi':
                    # Kurs ishi uchun kamida 1 ta mavzu bo'lishi kerak
                    if actual < 1:
                        has_issue = True
                        warnings.append(
                            f"{data['name']}: Kamida 1 ta mavzu yaratilishi kerak, lekin hali yaratilmagan"
                        )
                elif actual < required:
                    has_issue = True
                    missing = required - actual
                    warnings.append(
                        f"{data['name']}: {data['hours']} soat uchun {required:.1f} para mavzu kerak, "
                        f"lekin {actual} para kiritilgan (kam: {missing:.1f} para)"
                    )
        
        return {'has_issue': has_issue, 'warnings': warnings}

    def has_lessons_without_content(self):
        """Tarkibi bo'lmagan darslar borligini tekshirish"""
        for lesson in self.lessons:
            # Agar kontent, video va fayl bo'lmasa - dars bo'sh
            if not lesson.content and not lesson.video_url and not lesson.video_file and not lesson.file_url:
                return True
        return False


# ==================== O'QUV REJA (YO'NALISH-FAN BOG'LANISHI) ====================
class DirectionCurriculum(db.Model):
    """Yo'nalish o'quv rejasi - yo'nalish, semestr va fanlar o'rtasidagi bog'lanish"""
    id = db.Column(db.Integer, primary_key=True)
    direction_id = db.Column(db.Integer, db.ForeignKey('direction.id'), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey('subject.id'), nullable=False)
    semester = db.Column(db.Integer, nullable=False)  # 1-10 semestr
    hours_maruza = db.Column(db.Integer, default=0)  # M - Maruza soatlari
    hours_amaliyot = db.Column(db.Integer, default=0)  # A - Amaliyot soatlari
    hours_laboratoriya = db.Column(db.Integer, default=0)  # L - Laboratoriya soatlari
    hours_seminar = db.Column(db.Integer, default=0)  # S - Seminar soatlari
    hours_kurs_ishi = db.Column(db.Integer, default=0)  # K - Kurs ishi soatlari
    hours_mustaqil = db.Column(db.Integer, default=0)  # MT - Mustaqil ta'lim soatlari
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    subject = db.relationship('Subject', backref='curriculum_items')
    
    # Unique constraint: bir yo'nalishda bir semestrda bir fan bir marta bo'lishi kerak
    __table_args__ = (db.UniqueConstraint('direction_id', 'subject_id', 'semester', name='uq_direction_subject_semester'),)


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


# ==================== FOYDALANUVCHI ROLI ====================
class UserRole(db.Model):
    """Foydalanuvchi rollari (bir nechta rol qo'llab-quvvatlash uchun)"""
    __tablename__ = 'user_roles'
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), primary_key=True)
    role = db.Column(db.String(20), primary_key=True)  # admin, teacher, student, dean, accounting
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# ==================== FOYDALANUVCHI ====================
class User(UserMixin, db.Model):
    """Foydalanuvchi modeli"""
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=True, default=None)  # Email ixtiyoriy
    login = db.Column(db.String(50), unique=True)  # Login (xodimlar uchun majburiy)
    password_hash = db.Column(db.String(256), nullable=False)
    full_name = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='student')  # admin, teacher, student, dean, accounting
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    phone = db.Column(db.String(20))
    
    # Talaba uchun
    student_id = db.Column(db.String(20), unique=True)  # Talaba ID raqami (talabalar uchun majburiy)
    group_id = db.Column(db.Integer, db.ForeignKey('group.id'))
    enrollment_year = db.Column(db.Integer)  # Qabul yili
    semester = db.Column(db.Integer, default=1)  # Semestr (1-8)
    # Qo'shimcha talaba ma'lumotlari
    passport_number = db.Column(db.String(20))   # Pasport raqami
    pinfl = db.Column(db.String(14))            # JSHSHIR (PINFL)
    birth_date = db.Column(db.Date)             # Tug'ilgan sana
    specialty = db.Column(db.String(200))       # Yo'nalish nomi (agar to'g'ridan-to'g'ri berilsa)
    specialty_code = db.Column(db.String(50))   # Yo'nalish kodi (shifr)
    education_type = db.Column(db.String(50))   # Ta'lim shakli (kunduzgi, sirtqi, kechki)
    
    # O'qituvchi/Dekan uchun
    department = db.Column(db.String(100))
    position = db.Column(db.String(50))
    faculty_id = db.Column(db.Integer, db.ForeignKey('faculty.id'))  # Dekan qaysi fakultetga tegishli
    description = db.Column(db.Text)  # Xodim haqida tavsif
    
    # Relationships
    submissions = db.relationship('Submission', backref='student', lazy='dynamic', foreign_keys='Submission.student_id')
    announcements = db.relationship('Announcement', backref='author', lazy='dynamic')
    managed_faculty = db.relationship('Faculty', foreign_keys=[faculty_id], uselist=False)
    # Bir nechta rollar
    roles_list = db.relationship('UserRole', backref='user', lazy='dynamic', cascade='all, delete-orphan', foreign_keys='UserRole.user_id')
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def get_roles(self):
        """Foydalanuvchining barcha rollarini olish"""
        if self.roles_list.count() > 0:
            return [r.role for r in self.roles_list]
        # Agar roles_list bo'sh bo'lsa, eski role maydonini qaytaramiz
        return [self.role] if self.role else []
    
    def has_role(self, role_name):
        """Foydalanuvchida bunday rol bormi?"""
        return role_name in self.get_roles()
    
    def add_role(self, role_name):
        """Foydalanuvchiga rol qo'shish"""
        if not self.has_role(role_name):
            user_role = UserRole(user_id=self.id, role=role_name)
            db.session.add(user_role)
            db.session.commit()
    
    def remove_role(self, role_name):
        """Foydalanuvchidan rol olib tashlash"""
        UserRole.query.filter_by(user_id=self.id, role=role_name).delete()
        db.session.commit()
    
    def set_roles(self, role_list):
        """Foydalanuvchiga bir nechta rol biriktirish (eski rollarni o'chirib, yangilarini qo'shish)"""
        # Eski rollarni o'chirish
        UserRole.query.filter_by(user_id=self.id).delete()
        # Yangi rollarni qo'shish
        for role in role_list:
            user_role = UserRole(user_id=self.id, role=role)
            db.session.add(user_role)
        db.session.commit()
    
    def get_role_display(self):
        """Asosiy rol nomini olish (eski kodlar bilan mosligi uchun)"""
        roles = {
            'admin': 'Administrator',
            'teacher': "O'qituvchi",
            'student': 'Talaba',
            'dean': 'Dekan',
            'accounting': 'Buxgalteriya'
        }
        return roles.get(self.role, self.role)
    
    def get_all_roles_display(self):
        """Barcha rollarni ko'rinishda olish (tartiblangan)"""
        roles = {
            'admin': 'Administrator',
            'teacher': "O'qituvchi",
            'student': 'Talaba',
            'dean': 'Dekan',
            'accounting': 'Buxgalteriya'
        }
        user_roles = self.get_roles()
        # Rollarni belgilangan tartibda saralash: admin, dean, teacher, accounting, student
        role_order = ['admin', 'dean', 'teacher', 'accounting', 'student']
        sorted_roles = []
        for ordered_role in role_order:
            if ordered_role in user_roles:
                sorted_roles.append(roles.get(ordered_role, ordered_role))
        # Agar tartibda bo'lmagan rollar bo'lsa, ularni oxiriga qo'shish
        for role in user_roles:
            if role not in role_order:
                sorted_roles.append(roles.get(role, role))
        return sorted_roles
    
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
    group_id = db.Column(db.Integer, db.ForeignKey('group.id'), nullable=True)  # Qaysi guruh uchun
    direction_id = db.Column(db.Integer, db.ForeignKey('direction.id'), nullable=True)  # Qaysi yo'nalish uchun
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    
    creator = db.relationship('User', backref='created_lessons')
    group = db.relationship('Group', backref='lessons')
    direction = db.relationship('Direction', backref='lessons')
    
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
    direction_id = db.Column(db.Integer, db.ForeignKey('direction.id'), nullable=True)  # Qaysi yo'nalish uchun
    lesson_type = db.Column(db.String(20), nullable=True)  # Qaysi dars turi uchun (maruza, amaliyot, etc.)
    lesson_ids = db.Column(db.Text)  # Qaysi mavzularga tegishli (JSON array: [1, 2, 3])
    due_date = db.Column(db.DateTime)
    max_score = db.Column(db.Integer, default=100)
    file_required = db.Column(db.Boolean, default=False)  # Fayl yuklash majburiy yoki ixtiyoriy
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    
    # Relationships
    submissions = db.relationship('Submission', backref='assignment', lazy='dynamic', cascade='all, delete-orphan')
    creator = db.relationship('User', backref='created_assignments')
    group = db.relationship('Group', backref='assignments')
    direction = db.relationship('Direction', backref='assignments')
    # subject relationship - Subject modelida allaqachon backref mavjud
    
    def get_submission_count(self):
        return self.submissions.count()
    
    def get_lesson_ids_list(self):
        """Lesson IDs ni list sifatida qaytarish"""
        if self.lesson_ids:
            try:
                import json
                return json.loads(self.lesson_ids)
            except:
                return []
        return []


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
    resubmission_count = db.Column(db.Integer, default=0)  # Qayta topshirishlar soni
    allow_resubmission = db.Column(db.Boolean, default=False)  # O'qituvchi qo'shimcha imkon berishi mumkin
    is_active = db.Column(db.Boolean, default=True)  # Faol topshiriq (oxirgi yuborilgan)
    
    grader = db.relationship('User', foreign_keys=[graded_by], backref='graded_submissions')
    
    def can_resubmit(self, max_resubmissions=3):
        """Qayta topshirish mumkinligini tekshirish"""
        if self.allow_resubmission:
            return True  # O'qituvchi maxsus ruxsat bergan
        return self.resubmission_count < max_resubmissions


# ==================== E'LON ====================
class Announcement(db.Model):
    """E'lon modeli"""
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    author_role = db.Column(db.String(50))  # E'lon yaratilganda foydalanuvchining tanlangan roli
    is_important = db.Column(db.Boolean, default=False)
    target_roles = db.Column(db.String(100))  # comma-separated: student,teacher,dean
    faculty_id = db.Column(db.Integer, db.ForeignKey('faculty.id'))  # Faqat shu fakultet uchun
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    target_faculty = db.relationship('Faculty', backref='announcements')


# ==================== DARS JADVALI ====================
class Schedule(db.Model):
    """Dars jadvali (onlayn konsultatsiyalar)"""
    id = db.Column(db.Integer, primary_key=True)
    subject_id = db.Column(db.Integer, db.ForeignKey('subject.id'), nullable=False)
    group_id = db.Column(db.Integer, db.ForeignKey('group.id'), nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    # Sana: YYYYMMDD formatida butun son ko'rinishida saqlanadi, masalan 20251210
    # Eski ma'lumotlarda bu maydon hafta kuni sifatida ishlatilgan bo'lishi mumkin.
    day_of_week = db.Column(db.Integer)
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
    accounting = User.query.filter_by(login='accounting').first()
    if not accounting:
        # Email orqali ham qidirish (eski versiyalar uchun)
        accounting = User.query.filter_by(email='accounting@university.uz').first()
        if accounting:
            # Login qo'shish
            accounting.login = 'accounting'
            db.session.commit()
        else:
            accounting = User(
                email='accounting@university.uz',
                login='accounting',
                full_name='Buxgalteriya Bo\'limi',
                role='accounting',
                phone='+998 90 123 45 68'
            )
            accounting.set_password('accounting123')
            db.session.add(accounting)
            db.session.commit()
    
    # Mavjud demo hisoblar uchun login qo'shish (migratsiya) - avval buni qilamiz
    # Admin
    admin_existing = User.query.filter_by(role='admin').first()
    if admin_existing and not admin_existing.login:
        admin_existing.login = 'admin'
        db.session.commit()
    
    # Accounting
    accounting_old = User.query.filter_by(email='accounting@university.uz').first()
    if accounting_old and not accounting_old.login:
        accounting_old.login = 'accounting'
        db.session.commit()
    
    # Deans - mavjud demo hisoblar uchun
    deans_old = User.query.filter_by(role='dean').all()
    for dean in deans_old:
        if not dean.login and dean.email:
            login = dean.email.split('@')[0].replace('.', '_')
            # Login unikalligini tekshirish
            existing = User.query.filter_by(login=login).first()
            if not existing:
                dean.login = login
                db.session.commit()
    
    # Teachers - mavjud demo hisoblar uchun
    teachers_old = User.query.filter_by(role='teacher').all()
    for teacher in teachers_old:
        if not teacher.login and teacher.email:
            login = teacher.email.split('@')[0].replace('.', '_')
            # Login unikalligini tekshirish
            existing = User.query.filter_by(login=login).first()
            if not existing:
                teacher.login = login
                db.session.commit()
    
    # Eslatma: Har bir demo hisobni alohida tekshirib, agar yo'q bo'lsa yaratamiz
    # Shuning uchun bu yerda return qilmaymiz
    
    # ===== FAKULTETLAR =====
    faculties_data = [
        {'name': 'Axborot texnologiyalari fakulteti', 'code': 'IT', 'description': 'Dasturlash va kompyuter fanlari'},
        {'name': 'Iqtisodiyot fakulteti', 'code': 'IQ', 'description': 'Iqtisodiyot va menejment'},
        {'name': 'Huquqshunoslik fakulteti', 'code': 'HQ', 'description': 'Huquq va qonunchilik'},
    ]
    
    faculties = {}
    for f in faculties_data:
        faculty = Faculty.query.filter_by(code=f['code']).first()
        if not faculty:
            faculty = Faculty(name=f['name'], code=f['code'], description=f['description'])
            db.session.add(faculty)
        faculties[f['code']] = faculty
    
    db.session.commit()
    
    # ===== ADMIN =====
    admin = User.query.filter_by(login='admin').first()
    if not admin:
        # Demo admin uchun tahminiy ma'lumotlar
        admin = User(
            email='admin@university.uz',
            login='admin',
            full_name='Tizim Administratori',
            role='admin',
            passport_number='AA1234567',
            pinfl='12345678901234',
            birth_date=date(1985, 5, 15)
        )
        admin.set_password(admin.passport_number)
        db.session.add(admin)
    else:
        # Mavjud admin uchun ma'lumotlarni to'ldirish
        if not admin.passport_number:
            admin.passport_number = 'AA1234567'
        if not admin.pinfl:
            admin.pinfl = '12345678901234'
        if not admin.birth_date:
            admin.birth_date = date(1985, 5, 15)
        # Parolni pasport raqamiga yangilash
        admin.set_password(admin.passport_number)
        db.session.commit()
    
    # ===== BUXGALTERIYA =====
    accounting = User.query.filter_by(login='accounting').first()
    if not accounting:
        # Demo accounting uchun tahminiy ma'lumotlar
        accounting = User(
            email='accounting@university.uz',
            login='accounting',
            full_name='Buxgalteriya Bo\'limi',
            role='accounting',
            phone='+998 90 123 45 68',
            passport_number='AB1234568',
            pinfl='23456789012345',
            birth_date=date(1988, 8, 20)
        )
        accounting.set_password(accounting.passport_number)
        db.session.add(accounting)
    else:
        # Mavjud accounting uchun ma'lumotlarni to'ldirish
        if not accounting.passport_number:
            accounting.passport_number = 'AB1234568'
        if not accounting.pinfl:
            accounting.pinfl = '23456789012345'
        if not accounting.birth_date:
            accounting.birth_date = date(1988, 8, 20)
        db.session.commit()
    
    # ===== DEKANLAR =====
    deans_data = [
        {'email': 'dean.it@university.uz', 'full_name': 'Sherzod Karimov', 'faculty': 'IT', 'position': 'Dekan', 'passport': 'AC1234569', 'pinfl': '34567890123456', 'birth_date': date(1975, 3, 10)},
        {'email': 'dean.iq@university.uz', 'full_name': 'Aziza Rahimova', 'faculty': 'IQ', 'position': 'Dekan', 'passport': 'AD1234570', 'pinfl': '45678901234567', 'birth_date': date(1978, 7, 25)},
    ]
    
    deans = {}
    for d in deans_data:
        # Login yaratish: dean.it -> dean_it
        login = d['email'].split('@')[0].replace('.', '_')
        dean = User.query.filter_by(login=login).first()
        if not dean:
            # Demo hisoblar uchun tahminiy ma'lumotlar
            dean = User(
                email=d['email'],
                login=login,
                full_name=d['full_name'],
                role='dean',
                position=d['position'],
                faculty_id=faculties[d['faculty']].id,
                phone='+998 90 123 45 67',
                passport_number=d['passport'],
                pinfl=d['pinfl'],
                birth_date=d['birth_date']
            )
            dean.set_password(d['passport'])
            db.session.add(dean)
        else:
            # Mavjud dean uchun ma'lumotlarni to'ldirish
            if not dean.passport_number:
                dean.passport_number = d['passport']
            if not dean.pinfl:
                dean.pinfl = d['pinfl']
            if not dean.birth_date:
                dean.birth_date = d['birth_date']
            # Parolni pasport raqamiga yangilash
            dean.set_password(dean.passport_number)
            db.session.commit()
        deans[d['faculty']] = dean
    
    db.session.commit()
    
    # ===== DEMO MASOFAVIY YO'NALISHLAR =====
    # Har bir fakultet uchun masofaviy yo'nalish yaratish
    demo_directions = {}
    for faculty_code, faculty in faculties.items():
        demo_direction_code = f'DEMO-MASOFAVIY-{faculty_code}'
        demo_direction = Direction.query.filter_by(code=demo_direction_code, education_type='masofaviy').first()
        if not demo_direction:
            demo_direction = Direction(
                name=f'Demo Masofaviy Ta\'lim ({faculty.name})',
                code=demo_direction_code,
                description=f'Demo ma\'lumotlar uchun {faculty.name} masofaviy ta\'lim yo\'nalishi',
                faculty_id=faculty.id,
                course_year=1,
                semester=1,
                education_type='masofaviy',
                enrollment_year=2024
            )
            db.session.add(demo_direction)
            db.session.commit()
        demo_directions[faculty_code] = demo_direction
    
    # ===== YO'NALISHLAR (kunduzgi ta'lim uchun) =====
    # Har bir fakultet uchun kunduzgi va sirtqi yo'nalishlar yaratish
    directions = {}
    for faculty_code, faculty in faculties.items():
        # Kunduzgi yo'nalish
        direction_code = f'{faculty_code}-KUNDUZGI'
        direction = Direction.query.filter_by(code=direction_code, education_type='kunduzgi').first()
        if not direction:
            direction = Direction(
                name=f'Kunduzgi Ta\'lim Yo\'nalishi ({faculty.name})',
                code=direction_code,
                description=f'{faculty.name} kunduzgi ta\'lim yo\'nalishi',
                faculty_id=faculty.id,
                course_year=1,
                semester=1,
                education_type='kunduzgi',
                enrollment_year=2024
            )
            db.session.add(direction)
            db.session.commit()
        directions[f'{faculty_code}-KUNDUZGI'] = direction
        
        # Sirtqi yo'nalish (faqat IT uchun)
        if faculty_code == 'IT':
            direction_code_sirtqi = f'{faculty_code}-SIRTQI'
            direction_sirtqi = Direction.query.filter_by(code=direction_code_sirtqi, education_type='sirtqi').first()
            if not direction_sirtqi:
                direction_sirtqi = Direction(
                    name=f'Sirtqi Ta\'lim Yo\'nalishi ({faculty.name})',
                    code=direction_code_sirtqi,
                    description=f'{faculty.name} sirtqi ta\'lim yo\'nalishi',
                    faculty_id=faculty.id,
                    course_year=1,
                    semester=1,
                    education_type='sirtqi',
                    enrollment_year=2024
                )
                db.session.add(direction_sirtqi)
                db.session.commit()
            directions[f'{faculty_code}-SIRTQI'] = direction_sirtqi
    
    # ===== GURUHLAR =====
    # Kurs va semestr munosabati: 1-kurs=1-2 semestr, 2-kurs=3-4 semestr, 3-kurs=5-6 semestr
    groups_data = [
        {'name': 'DI-21', 'faculty': 'IT', 'course_year': 3, 'education_type': 'kunduzgi', 'direction': 'IT-KUNDUZGI'},  # 5-6 semestr
        {'name': 'DI-22', 'faculty': 'IT', 'course_year': 2, 'education_type': 'kunduzgi', 'direction': 'IT-KUNDUZGI'},  # 3-4 semestr
        {'name': 'DI-23', 'faculty': 'IT', 'course_year': 1, 'education_type': 'kunduzgi', 'direction': 'IT-KUNDUZGI'},  # 1-2 semestr
        {'name': 'DS-22', 'faculty': 'IT', 'course_year': 2, 'education_type': 'sirtqi', 'direction': 'IT-SIRTQI'},     # 3-4 semestr
        {'name': 'IQ-21', 'faculty': 'IQ', 'course_year': 3, 'education_type': 'kunduzgi', 'direction': 'IQ-KUNDUZGI'}, # 5-6 semestr
    ]
    
    groups = {}
    for g in groups_data:
        group = Group.query.filter_by(name=g['name']).first()
        direction = directions.get(g['direction'])
        
        if not group:
            group = Group(
                name=g['name'],
                faculty_id=faculties[g['faculty']].id,
                course_year=g['course_year'],
                education_type=g['education_type'],
                direction_id=direction.id if direction else None
            )
            db.session.add(group)
        else:
            # Mavjud guruhni to'g'ri yo'nalishga bog'lash
            if direction and group.direction_id != direction.id:
                group.direction_id = direction.id
            # Fakultet va kurs ma'lumotlarini yangilash
            if group.faculty_id != faculties[g['faculty']].id:
                group.faculty_id = faculties[g['faculty']].id
            if group.course_year != g['course_year']:
                group.course_year = g['course_year']
            if group.education_type != g['education_type']:
                group.education_type = g['education_type']
        groups[g['name']] = group
    
    db.session.commit()
    
    # ===== O'QITUVCHILAR =====
    teachers_data = [
        {'email': 'a.karimov@university.uz', 'full_name': 'Aziz Karimov', 'department': 'Dasturiy injiniring', 'position': 'Dotsent', 'passport': 'AE1234571', 'pinfl': '56789012345678', 'birth_date': date(1980, 1, 12)},
        {'email': 'b.aliyev@university.uz', 'full_name': 'Bobur Aliyev', 'department': 'Dasturiy injiniring', 'position': "Katta o'qituvchi", 'passport': 'AF1234572', 'pinfl': '67890123456789', 'birth_date': date(1982, 4, 18)},
        {'email': 'd.toshmatov@university.uz', 'full_name': 'Dilshod Toshmatov', 'department': 'Kompyuter fanlari', 'position': 'Professor', 'passport': 'AG1234573', 'pinfl': '78901234567890', 'birth_date': date(1970, 9, 5)},
        {'email': 'n.rahimova@university.uz', 'full_name': 'Nilufar Rahimova', 'department': 'Iqtisodiyot', 'position': 'Dotsent', 'passport': 'AH1234574', 'pinfl': '89012345678901', 'birth_date': date(1983, 11, 22)},
    ]
    
    teachers = []
    for t in teachers_data:
        # Login yaratish: a.karimov -> a_karimov
        login = t['email'].split('@')[0].replace('.', '_')
        teacher = User.query.filter_by(login=login).first()
        if not teacher:
            # Demo hisoblar uchun tahminiy ma'lumotlar
            teacher = User(
                email=t['email'],
                login=login,
                full_name=t['full_name'],
                role='teacher',
                department=t['department'],
                position=t['position'],
                phone='+998 91 234 56 78',
                passport_number=t['passport'],
                pinfl=t['pinfl'],
                birth_date=t['birth_date']
            )
            teacher.set_password(teacher.passport_number)
            db.session.add(teacher)
        else:
            # Mavjud teacher uchun ma'lumotlarni to'ldirish
            if not teacher.passport_number:
                teacher.passport_number = t['passport']
            if not teacher.pinfl:
                teacher.pinfl = t['pinfl']
            if not teacher.birth_date:
                teacher.birth_date = t['birth_date']
            db.session.commit()
        teachers.append(teacher)
    
    db.session.commit()
    
    # ===== FANLAR =====
    # Kurs va semestr munosabati: 1-kurs=1-2 semestr, 2-kurs=3-4 semestr, 3-kurs=5-6 semestr
    subjects_data = [
        # 1-kurs (1-2 semestr) - DI-23 uchun
        {'name': 'Dasturlash asoslari', 'faculty': 'IT', 'credits': 4, 'semester': 1},  # 1-kurs, 1-semestr
        {'name': 'Algoritmlar', 'faculty': 'IT', 'credits': 3, 'semester': 2},          # 1-kurs, 2-semestr
        
        # 2-kurs (3-4 semestr) - DI-22 va DS-22 uchun
        {'name': 'Web dasturlash', 'faculty': 'IT', 'credits': 3, 'semester': 3},       # 2-kurs, 3-semestr
        {'name': "Ma'lumotlar bazasi", 'faculty': 'IT', 'credits': 4, 'semester': 3},  # 2-kurs, 3-semestr
        {'name': 'Kompyuter tarmoqlari', 'faculty': 'IT', 'credits': 3, 'semester': 4}, # 2-kurs, 4-semestr
        
        # 3-kurs (5-6 semestr) - DI-21 va IQ-21 uchun
        {'name': 'Makroiqtisodiyot', 'faculty': 'IQ', 'credits': 3, 'semester': 5},     # 3-kurs, 5-semestr (IQ-21 uchun)
    ]
    
    subjects = {}
    for s in subjects_data:
        subject = Subject.query.filter_by(name=s['name']).first()
        if not subject:
            subject = Subject(
                name=s['name'],
                credits=s['credits'],
                semester=s['semester'],
                description=f"{s['name']} fani bo'yicha ma'ruzalar va amaliy mashg'ulotlar"
            )
            db.session.add(subject)
        else:
            # Mavjud fanni yangilash
            if subject.semester != s['semester']:
                subject.semester = s['semester']
            if subject.credits != s['credits']:
                subject.credits = s['credits']
        subjects[s['name']] = subject
    
    db.session.commit()
    
    # ===== TALABALAR =====
    # Kurs va semestr munosabati: 1-kurs=1-2 semestr, 2-kurs=3-4 semestr, 3-kurs=5-6 semestr
    # Har bir kursning birinchi semestri: 1-kurs=1-semestr, 2-kurs=3-semestr, 3-kurs=5-semestr
    students_data = [
        {'email': 'student1@university.uz', 'full_name': 'Dilshod Rahimov', 'student_id': 'ST2021001', 'group': 'DI-21', 'semester': 5, 'passport': 'AI1234575', 'pinfl': '90123456789012', 'birth_date': date(2003, 2, 14)},  # 3-kurs
        {'email': 'student2@university.uz', 'full_name': 'Malika Karimova', 'student_id': 'ST2021002', 'group': 'DI-21', 'semester': 5, 'passport': 'AJ1234576', 'pinfl': '01234567890123', 'birth_date': date(2003, 6, 8)},  # 3-kurs
        {'email': 'student3@university.uz', 'full_name': 'Jasur Toshmatov', 'student_id': 'ST2022001', 'group': 'DI-22', 'semester': 3, 'passport': 'AK1234577', 'pinfl': '12345678901230', 'birth_date': date(2004, 3, 20)},  # 2-kurs
        {'email': 'student4@university.uz', 'full_name': 'Nodira Aliyeva', 'student_id': 'ST2022002', 'group': 'DI-22', 'semester': 3, 'passport': 'AL1234578', 'pinfl': '23456789012301', 'birth_date': date(2004, 8, 15)},  # 2-kurs
        {'email': 'student5@university.uz', 'full_name': 'Sardor Mahmudov', 'student_id': 'ST2023001', 'group': 'DI-23', 'semester': 1, 'passport': 'AM1234579', 'pinfl': '34567890123012', 'birth_date': date(2005, 1, 10)},  # 1-kurs
        {'email': 'student6@university.uz', 'full_name': 'Gulnora Rahimova', 'student_id': 'ST2021003', 'group': 'IQ-21', 'semester': 5, 'passport': 'AN1234580', 'pinfl': '45678901230123', 'birth_date': date(2003, 10, 5)}, # 3-kurs
    ]
    
    students = []
    for s in students_data:
        # Talabalar uchun student_id orqali qidirish
        student = User.query.filter_by(student_id=s['student_id']).first()
        group = groups[s['group']]
        course_year = group.course_year if group else 1
        
        # Kurs bo'yicha birinchi semestr: 1-kurs=1, 2-kurs=3, 3-kurs=5, 4-kurs=7
        default_semester = (course_year - 1) * 2 + 1
        semester = s.get('semester', default_semester)
        
        if not student:
            student = User(
                email=s['email'] if s.get('email') else None,
                full_name=s['full_name'],
                role='student',
                student_id=s['student_id'],
                group_id=group.id if group else None,
                enrollment_year=int('20' + s['group'][-2:]),
                semester=semester,
                passport_number=s['passport'],
                pinfl=s['pinfl'],
                birth_date=s['birth_date']
            )
            student.set_password(s['passport'])
            db.session.add(student)
        else:
            # Mavjud talabani yangilash
            if student.group_id != group.id:
                student.group_id = group.id
            if student.semester != semester:
                student.semester = semester
            if student.enrollment_year != int('20' + s['group'][-2:]):
                student.enrollment_year = int('20' + s['group'][-2:])
            # Ma'lumotlarni to'ldirish
            if not student.passport_number:
                student.passport_number = s['passport']
            if not student.pinfl:
                student.pinfl = s['pinfl']
            if not student.birth_date:
                student.birth_date = s['birth_date']
            # Parolni pasport raqamiga yangilash
            if student.passport_number:
                student.set_password(student.passport_number)
            db.session.commit()
        students.append(student)
    
    db.session.commit()
    
    # ===== O'QUV REJA (DIRECTION CURRICULUM) =====
    # Har bir yo'nalish va fanga o'quv reja yaratish
    # Kurs va semestr munosabati: 1-kurs=1-2 semestr, 2-kurs=3-4 semestr, 3-kurs=5-6 semestr
    
    # IT fakulteti - Kunduzgi yo'nalish
    it_kunduzgi_direction = directions.get('IT-KUNDUZGI')
    if it_kunduzgi_direction:
        it_kunduzgi_curriculum = [
            # 1-kurs (1-2 semestr)
            {'subject': 'Dasturlash asoslari', 'semester': 1, 'hours_maruza': 30, 'hours_amaliyot': 30, 'hours_laboratoriya': 0, 'hours_kurs_ishi': 0},
            {'subject': 'Algoritmlar', 'semester': 2, 'hours_maruza': 20, 'hours_amaliyot': 30, 'hours_laboratoriya': 0, 'hours_kurs_ishi': 0},
            # 2-kurs (3-4 semestr)
            {'subject': 'Web dasturlash', 'semester': 3, 'hours_maruza': 20, 'hours_amaliyot': 30, 'hours_laboratoriya': 0, 'hours_kurs_ishi': 0},
            {'subject': "Ma'lumotlar bazasi", 'semester': 3, 'hours_maruza': 30, 'hours_amaliyot': 30, 'hours_laboratoriya': 0, 'hours_kurs_ishi': 0},
            {'subject': 'Kompyuter tarmoqlari', 'semester': 4, 'hours_maruza': 20, 'hours_amaliyot': 20, 'hours_laboratoriya': 10, 'hours_kurs_ishi': 0},
        ]
        
        for s in it_kunduzgi_curriculum:
            if s['subject'] in subjects:
                existing = DirectionCurriculum.query.filter_by(
                    direction_id=it_kunduzgi_direction.id,
                    subject_id=subjects[s['subject']].id,
                    semester=s['semester']
                ).first()
                
                if not existing:
                    curriculum = DirectionCurriculum(
                        direction_id=it_kunduzgi_direction.id,
                        subject_id=subjects[s['subject']].id,
                        semester=s['semester'],
                        hours_maruza=s['hours_maruza'],
                        hours_amaliyot=s['hours_amaliyot'],
                        hours_laboratoriya=s['hours_laboratoriya'],
                        hours_kurs_ishi=s['hours_kurs_ishi']
                    )
                    db.session.add(curriculum)
    
    # IT fakulteti - Sirtqi yo'nalish
    it_sirtqi_direction = directions.get('IT-SIRTQI')
    if it_sirtqi_direction:
        it_sirtqi_curriculum = [
            # 2-kurs (3-4 semestr)
            {'subject': 'Web dasturlash', 'semester': 3, 'hours_maruza': 20, 'hours_amaliyot': 30, 'hours_laboratoriya': 0, 'hours_kurs_ishi': 0},
            {'subject': "Ma'lumotlar bazasi", 'semester': 3, 'hours_maruza': 30, 'hours_amaliyot': 30, 'hours_laboratoriya': 0, 'hours_kurs_ishi': 0},
            {'subject': 'Kompyuter tarmoqlari', 'semester': 4, 'hours_maruza': 20, 'hours_amaliyot': 20, 'hours_laboratoriya': 10, 'hours_kurs_ishi': 0},
        ]
        
        for s in it_sirtqi_curriculum:
            if s['subject'] in subjects:
                existing = DirectionCurriculum.query.filter_by(
                    direction_id=it_sirtqi_direction.id,
                    subject_id=subjects[s['subject']].id,
                    semester=s['semester']
                ).first()
                
                if not existing:
                    curriculum = DirectionCurriculum(
                        direction_id=it_sirtqi_direction.id,
                        subject_id=subjects[s['subject']].id,
                        semester=s['semester'],
                        hours_maruza=s['hours_maruza'],
                        hours_amaliyot=s['hours_amaliyot'],
                        hours_laboratoriya=s['hours_laboratoriya'],
                        hours_kurs_ishi=s['hours_kurs_ishi']
                    )
                    db.session.add(curriculum)
    
    # IQ fakulteti - Kunduzgi yo'nalish
    iq_kunduzgi_direction = directions.get('IQ-KUNDUZGI')
    if iq_kunduzgi_direction:
        iq_kunduzgi_curriculum = [
            # 3-kurs (5-6 semestr)
            {'subject': 'Makroiqtisodiyot', 'semester': 5, 'hours_maruza': 30, 'hours_amaliyot': 20, 'hours_laboratoriya': 0, 'hours_kurs_ishi': 0},
        ]
        
        for s in iq_kunduzgi_curriculum:
            if s['subject'] in subjects:
                existing = DirectionCurriculum.query.filter_by(
                    direction_id=iq_kunduzgi_direction.id,
                    subject_id=subjects[s['subject']].id,
                    semester=s['semester']
                ).first()
                
                if not existing:
                    curriculum = DirectionCurriculum(
                        direction_id=iq_kunduzgi_direction.id,
                        subject_id=subjects[s['subject']].id,
                        semester=s['semester'],
                        hours_maruza=s['hours_maruza'],
                        hours_amaliyot=s['hours_amaliyot'],
                        hours_laboratoriya=s['hours_laboratoriya'],
                        hours_kurs_ishi=s['hours_kurs_ishi']
                    )
                    db.session.add(curriculum)
    
    db.session.commit()
    
    # ===== O'QITUVCHI-FAN BIRIKTIRISH =====
    # Kurs va semestr munosabati: 1-kurs=1-2 semestr, 2-kurs=3-4 semestr, 3-kurs=5-6 semestr
    # DI-21: 3-kurs (5-6 semestr), DI-22: 2-kurs (3-4 semestr), DI-23: 1-kurs (1-2 semestr)
    # DS-22: 2-kurs (3-4 semestr), IQ-21: 3-kurs (5-6 semestr)
    assignments_data = [
        # DI-23: 1-kurs (1-2 semestr)
        {'teacher': teachers[0], 'subject': 'Dasturlash asoslari', 'group': 'DI-23', 'lesson_type': 'maruza', 'semester': 1},
        {'teacher': teachers[0], 'subject': 'Dasturlash asoslari', 'group': 'DI-23', 'lesson_type': 'amaliyot', 'semester': 1},
        {'teacher': teachers[1], 'subject': 'Algoritmlar', 'group': 'DI-23', 'lesson_type': 'maruza', 'semester': 2},
        {'teacher': teachers[1], 'subject': 'Algoritmlar', 'group': 'DI-23', 'lesson_type': 'amaliyot', 'semester': 2},
        
        # DI-22: 2-kurs (3-4 semestr)
        {'teacher': teachers[0], 'subject': 'Web dasturlash', 'group': 'DI-22', 'lesson_type': 'maruza', 'semester': 3},
        {'teacher': teachers[0], 'subject': 'Web dasturlash', 'group': 'DI-22', 'lesson_type': 'amaliyot', 'semester': 3},
        {'teacher': teachers[2], 'subject': "Ma'lumotlar bazasi", 'group': 'DI-22', 'lesson_type': 'maruza', 'semester': 3},
        {'teacher': teachers[2], 'subject': "Ma'lumotlar bazasi", 'group': 'DI-22', 'lesson_type': 'amaliyot', 'semester': 3},
        {'teacher': teachers[2], 'subject': 'Kompyuter tarmoqlari', 'group': 'DI-22', 'lesson_type': 'maruza', 'semester': 4},
        {'teacher': teachers[2], 'subject': 'Kompyuter tarmoqlari', 'group': 'DI-22', 'lesson_type': 'amaliyot', 'semester': 4},
        {'teacher': teachers[2], 'subject': 'Kompyuter tarmoqlari', 'group': 'DI-22', 'lesson_type': 'laboratoriya', 'semester': 4},
        
        # DS-22: 2-kurs (3-4 semestr) - sirtqi
        {'teacher': teachers[0], 'subject': 'Web dasturlash', 'group': 'DS-22', 'lesson_type': 'maruza', 'semester': 3},
        {'teacher': teachers[0], 'subject': 'Web dasturlash', 'group': 'DS-22', 'lesson_type': 'amaliyot', 'semester': 3},
        
        # IQ-21: 3-kurs (5-6 semestr)
        {'teacher': teachers[3], 'subject': 'Makroiqtisodiyot', 'group': 'IQ-21', 'lesson_type': 'maruza', 'semester': 5},
        {'teacher': teachers[3], 'subject': 'Makroiqtisodiyot', 'group': 'IQ-21', 'lesson_type': 'amaliyot', 'semester': 5},
    ]
    
    for a in assignments_data:
        # Agar bunday biriktirish allaqachon mavjud bo'lsa, o'tkazib yuborish
        existing = TeacherSubject.query.filter_by(
            teacher_id=a['teacher'].id,
            subject_id=subjects[a['subject']].id,
            group_id=groups[a['group']].id,
            lesson_type=a['lesson_type']
        ).first()
        
        if not existing:
            # Guruhning yo'nalishini olish
            group = groups[a['group']]
            direction_id = group.direction_id if group else None
            
            ta = TeacherSubject(
                teacher_id=a['teacher'].id,
                subject_id=subjects[a['subject']].id,
                group_id=groups[a['group']].id,
                lesson_type=a['lesson_type'],
                academic_year='2024-2025',
                semester=a['semester'],
                assigned_by=deans['IT'].id if 'D' in a['group'] or a['group'].startswith('DS') else deans['IQ'].id
            )
            db.session.add(ta)
    
    db.session.commit()
    
    # ===== DARSLAR (MAVZULAR) =====
    # Har bir fan uchun mavzular yaratish, yo'nalish va dars turiga mos
    lessons_data = [
        # DI-23 (1-kurs, 1-semestr): Dasturlash asoslari
        {'subject': 'Dasturlash asoslari', 'group': 'DI-23', 'direction': 'IT-KUNDUZGI', 'lesson_type': 'maruza', 'order': 1, 'title': '1-mavzu: Dasturlashning asoslari'},
        {'subject': 'Dasturlash asoslari', 'group': 'DI-23', 'direction': 'IT-KUNDUZGI', 'lesson_type': 'maruza', 'order': 2, 'title': '2-mavzu: O\'zgaruvchilar va ma\'lumotlar turlari'},
        {'subject': 'Dasturlash asoslari', 'group': 'DI-23', 'direction': 'IT-KUNDUZGI', 'lesson_type': 'amaliyot', 'order': 1, 'title': 'Amaliy mashg\'ulot 1: Dasturlash muhitini o\'rganish'},
        
        # DI-23 (1-kurs, 2-semestr): Algoritmlar
        {'subject': 'Algoritmlar', 'group': 'DI-23', 'direction': 'IT-KUNDUZGI', 'lesson_type': 'maruza', 'order': 1, 'title': '1-mavzu: Algoritm tushunchasi'},
        {'subject': 'Algoritmlar', 'group': 'DI-23', 'direction': 'IT-KUNDUZGI', 'lesson_type': 'amaliyot', 'order': 1, 'title': 'Amaliy mashg\'ulot 1: Algoritm yaratish'},
        
        # DI-22 (2-kurs, 3-semestr): Web dasturlash va Ma'lumotlar bazasi
        {'subject': 'Web dasturlash', 'group': 'DI-22', 'direction': 'IT-KUNDUZGI', 'lesson_type': 'maruza', 'order': 1, 'title': '1-mavzu: HTML va CSS asoslari'},
        {'subject': 'Web dasturlash', 'group': 'DI-22', 'direction': 'IT-KUNDUZGI', 'lesson_type': 'maruza', 'order': 2, 'title': '2-mavzu: JavaScript asoslari'},
        {'subject': 'Web dasturlash', 'group': 'DI-22', 'direction': 'IT-KUNDUZGI', 'lesson_type': 'amaliyot', 'order': 1, 'title': 'Amaliy mashg\'ulot 1: Web sahifa yaratish'},
        
        {'subject': "Ma'lumotlar bazasi", 'group': 'DI-22', 'direction': 'IT-KUNDUZGI', 'lesson_type': 'maruza', 'order': 1, 'title': '1-mavzu: Ma\'lumotlar bazasi tushunchasi'},
        {'subject': "Ma'lumotlar bazasi", 'group': 'DI-22', 'direction': 'IT-KUNDUZGI', 'lesson_type': 'amaliyot', 'order': 1, 'title': 'Amaliy mashg\'ulot 1: SQL so\'rovlar'},
        
        # DI-22 (2-kurs, 4-semestr): Kompyuter tarmoqlari
        {'subject': 'Kompyuter tarmoqlari', 'group': 'DI-22', 'direction': 'IT-KUNDUZGI', 'lesson_type': 'maruza', 'order': 1, 'title': '1-mavzu: Tarmoq arxitekturasi'},
        {'subject': 'Kompyuter tarmoqlari', 'group': 'DI-22', 'direction': 'IT-KUNDUZGI', 'lesson_type': 'laboratoriya', 'order': 1, 'title': 'Laboratoriya 1: Tarmoq sozlash'},
        
        # IQ-21 (3-kurs, 5-semestr): Makroiqtisodiyot
        {'subject': 'Makroiqtisodiyot', 'group': 'IQ-21', 'direction': 'IQ-KUNDUZGI', 'lesson_type': 'maruza', 'order': 1, 'title': '1-mavzu: Makroiqtisodiyotning asoslari'},
        {'subject': 'Makroiqtisodiyot', 'group': 'IQ-21', 'direction': 'IQ-KUNDUZGI', 'lesson_type': 'amaliyot', 'order': 1, 'title': 'Amaliy mashg\'ulot 1: Iqtisodiy ko\'rsatkichlar'},
    ]
    
    for lesson_data in lessons_data:
        if lesson_data['subject'] in subjects:
            subject = subjects[lesson_data['subject']]
            group = groups.get(lesson_data['group'])
            direction = directions.get(lesson_data['direction'])
            
            if group and direction:
                # Mavjud darsni tekshirish
                existing = Lesson.query.filter_by(
                    subject_id=subject.id,
                    group_id=group.id,
                    direction_id=direction.id,
                    lesson_type=lesson_data['lesson_type'],
                    order=lesson_data['order']
                ).first()
                
                if not existing:
                    lesson = Lesson(
                        title=lesson_data['title'],
                        content=f"Bu {subject.name} fanining {lesson_data['title']} mavzusi.",
                        duration=80,
                        order=lesson_data['order'],
                        lesson_type=lesson_data['lesson_type'],
                        subject_id=subject.id,
                        group_id=group.id,
                        direction_id=direction.id,
                        created_by=teachers[0].id
                    )
                    db.session.add(lesson)
    
    # ===== TOPSHIRIQLAR =====
    # Demo topshiriqlar o'chirildi
    
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
        {'subject': 'Dasturlash asoslari', 'group': 'DI-23', 'teacher': teachers[0], 'day': 0, 'start': '09:00', 'end': '10:30', 'link': '', 'type': 'lecture'},
        {'subject': 'Dasturlash asoslari', 'group': 'DI-23', 'teacher': teachers[0], 'day': 2, 'start': '14:00', 'end': '16:00', 'link': '', 'type': 'lab'},
        {'subject': 'Web dasturlash', 'group': 'DI-21', 'teacher': teachers[0], 'day': 1, 'start': '09:00', 'end': '10:30', 'link': '', 'type': 'lecture'},
        {'subject': "Ma'lumotlar bazasi", 'group': 'DI-21', 'teacher': teachers[2], 'day': 3, 'start': '11:00', 'end': '12:30', 'link': '', 'type': 'lecture'},
        {'subject': 'Algoritmlar', 'group': 'DI-22', 'teacher': teachers[1], 'day': 1, 'start': '14:00', 'end': '15:30', 'link': '', 'type': 'lecture'},
    ]
    
    for s in schedule_data:
        # Mavjud schedule'ni tekshirish (subject, group, day, start_time bo'yicha)
        existing = Schedule.query.filter_by(
            subject_id=subjects[s['subject']].id,
            group_id=groups[s['group']].id,
            day_of_week=s['day'],
            start_time=s['start']
        ).first()
        
        if not existing:
            schedule = Schedule(
                subject_id=subjects[s['subject']].id,
                group_id=groups[s['group']].id,
                teacher_id=s['teacher'].id,
                day_of_week=s['day'],
                start_time=s['start'],
                end_time=s['end'],
                link=s['link'],
                lesson_type=s['type']
            )
            db.session.add(schedule)
    
    db.session.commit()
