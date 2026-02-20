from app import db, login_manager
from flask import has_request_context, session
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date, timedelta


def _cap_first(s):
    """Matnni bosh harf bilan qaytaradi (asl yozuv)."""
    if not s:
        return s or ''
    return s[:1].upper() + s[1:]


def _education_type_label(edu_type_raw):
    """Ta'lim shaklini tanlangan tilda qaytarish (request context bo'lsa)."""
    if not edu_type_raw:
        return "____"
    if has_request_context():
        from app.utils.translations import get_translation
        key = str(edu_type_raw).strip().lower()
        if key in ('kunduzgi', 'sirtqi', 'kechki', 'masofaviy'):
            return get_translation('education_type_' + key, session.get('language', 'uz'))
        return get_translation('education_type_not_set', session.get('language', 'uz'))
    return edu_type_raw.capitalize() if isinstance(edu_type_raw, str) else str(edu_type_raw)

@login_manager.user_loader
def load_user(id):
    return User.query.get(int(id))


# ==================== FAKULTET ====================
class Faculty(db.Model):
    """Fakultet modeli – nomi barcha tillarda (name_uz, name_ru, name_en)."""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False, unique=True)  # Asosiy (name_uz) – qidiruv va tartiblash
    name_uz = db.Column(db.String(200))
    name_ru = db.Column(db.String(200))
    name_en = db.Column(db.String(200))
    code = db.Column(db.String(20), nullable=False, unique=True)  # IT, IQ, HQ
    description = db.Column(db.Text)  # Asosiy (description_uz) – fallback
    description_uz = db.Column(db.Text)
    description_ru = db.Column(db.Text)
    description_en = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    groups = db.relationship('Group', backref='faculty', lazy='dynamic', cascade='all, delete-orphan')

    def get_display_description(self, lang=None):
        """Berilgan til uchun tavsif (lang: uz, ru, en)."""
        try:
            if lang and str(lang).lower() in ('uz', 'ru', 'en'):
                val = getattr(self, 'description_' + str(lang).lower(), None)
                if val:
                    return val
            for key in ('description_uz', 'description_ru', 'description_en'):
                v = getattr(self, key, None)
                if v:
                    return v
            return self.description or ''
        except Exception:
            return self.description or ''

    def get_display_name(self, lang=None):
        """Berilgan til uchun nom (lang: uz, ru, en)."""
        try:
            if lang and str(lang).lower() in ('uz', 'ru', 'en'):
                val = getattr(self, 'name_' + str(lang).lower(), None)
                if val:
                    return val
            for key in ('name_uz', 'name_ru', 'name_en'):
                v = getattr(self, key, None)
                if v:
                    return v
            return self.name or ''
        except Exception:
            return self.name or ''


# ==================== KAFEDRA (DEPARTMENT) ====================
class Department(db.Model):
    """Kafedra modeli – fakultetga bog'lanmaydi. Nomi barcha tillarda (name_uz, name_ru, name_en)."""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)  # Asosiy (name_uz) – qidiruv va tartiblash uchun
    name_uz = db.Column(db.String(200))
    name_ru = db.Column(db.String(200))
    name_en = db.Column(db.String(200))
    description = db.Column(db.Text)  # Ixtiyoriy, formada ko‘rsatilmaydi
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    subjects = db.relationship('Subject', backref='department', lazy='dynamic', foreign_keys='Subject.department_id')
    teacher_memberships = db.relationship('TeacherDepartment', backref='department', lazy='dynamic', cascade='all, delete-orphan')
    
    def get_display_name(self, lang=None):
        """Berilgan til uchun nom (lang: uz, ru, en). Lang bo‘lmasa yoki xato bo‘lsa name qaytadi."""
        try:
            if lang and str(lang).lower() in ('uz', 'ru', 'en'):
                val = getattr(self, 'name_' + str(lang).lower(), None)
                if val:
                    return val
            for key in ('name_uz', 'name_ru', 'name_en'):
                v = getattr(self, key, None)
                if v:
                    return v
            return self.name or ''
        except Exception:
            return self.name or ''


# ==================== KAFEDRA MUDIRLARI (BIR NECHTA KAFEDRAGA BIR XODIM) ====================
class DepartmentHead(db.Model):
    """Kafedra – xodim (mudir) bog‘lanishi: bitta xodim bir nechta kafedraga mudir bo‘lishi mumkin."""
    __tablename__ = 'department_head'
    id = db.Column(db.Integer, primary_key=True)
    department_id = db.Column(db.Integer, db.ForeignKey('department.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint('department_id', 'user_id', name='uq_department_head_dept_user'),)

    department = db.relationship('Department', backref=db.backref('head_links', lazy='dynamic', cascade='all, delete-orphan'))
    user = db.relationship('User', backref=db.backref('department_head_links', lazy='dynamic'))


# ==================== XODIM – FAKULTET (BIR NECHTA FAKULTETGA DEKAN) ====================
class UserFaculty(db.Model):
    """Xodim – fakultet bog‘lanishi: bitta xodim (dekan) bir nechta fakultetga biriktirilishi mumkin."""
    __tablename__ = 'user_faculty'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    faculty_id = db.Column(db.Integer, db.ForeignKey('faculty.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint('user_id', 'faculty_id', name='uq_user_faculty_user_faculty'),)

    user = db.relationship('User', backref=db.backref('user_faculty_links', lazy='dynamic', cascade='all, delete-orphan'))
    faculty = db.relationship('Faculty', backref=db.backref('user_faculty_links', lazy='dynamic'))


# ==================== YO'NALISH (DIRECTION) ====================
class Direction(db.Model):
    """Akademik yo'nalish modeli – nomi va tavsifi barcha tillarda."""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)  # Asosiy (name_uz) – qidiruv va fallback
    name_uz = db.Column(db.String(200))
    name_ru = db.Column(db.String(200))
    name_en = db.Column(db.String(200))
    code = db.Column(db.String(20), nullable=False)  # DI (15 tagacha belgi)
    description = db.Column(db.Text)  # Asosiy (description_uz) – fallback
    description_uz = db.Column(db.Text)
    description_ru = db.Column(db.Text)
    description_en = db.Column(db.Text)
    faculty_id = db.Column(db.Integer, db.ForeignKey('faculty.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    faculty = db.relationship('Faculty', backref='directions')
    groups = db.relationship('Group', backref='direction', lazy='dynamic')
    curriculum_items = db.relationship('DirectionCurriculum', backref='direction', lazy='dynamic', cascade='all, delete-orphan')
    
    def get_display_name(self, lang=None):
        """Berilgan til uchun nom (lang: uz, ru, en)."""
        try:
            if lang:
                val = getattr(self, 'name_' + str(lang).lower(), None)
                if val:
                    return val
            for key in ('name_uz', 'name_ru', 'name_en'):
                v = getattr(self, key, None)
                if v:
                    return v
            return self.name or ''
        except Exception:
            return self.name or ''
    
    def get_display_description(self, lang=None):
        """Berilgan til uchun tavsif (lang: uz, ru, en)."""
        try:
            if lang:
                val = getattr(self, 'description_' + str(lang).lower(), None)
                if val:
                    return val
            for key in ('description_uz', 'description_ru', 'description_en'):
                v = getattr(self, key, None)
                if v:
                    return v
            return self.description or ''
        except Exception:
            return self.description or ''
    
    @property
    def formatted_direction(self):
        """Get formatted direction name from groups: [Year] - [Code] - [Name] ([Education Type])"""
        name_display = _cap_first(self.name) if self.name else (self.name or '')
        first_group = self.groups.first()
        if first_group and first_group.enrollment_year and first_group.education_type:
            year = first_group.enrollment_year
            edu_type = _education_type_label(first_group.education_type)
            return f"{year} - {self.code} - {name_display} ({edu_type})"
        return f"____ - {self.code} - {name_display}"


# ==================== GURUH ====================
class Group(db.Model):
    """Guruh modeli"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)  # DI-21, IQ-22
    faculty_id = db.Column(db.Integer, db.ForeignKey('faculty.id'), nullable=False)
    direction_id = db.Column(db.Integer, db.ForeignKey('direction.id'), nullable=True)  # Yo'nalishga biriktirish
    course_year = db.Column(db.Integer, nullable=False)  # 1, 2, 3, 4-kurs
    semester = db.Column(db.Integer, nullable=False, default=1)  # 1-10 semestr
    education_type = db.Column(db.String(20), default='kunduzgi')  # kunduzgi, sirtqi, kechki
    enrollment_year = db.Column(db.Integer)  # Qabul yili (masalan: 2024)
    description = db.Column(db.Text)  # Guruh haqida tavsif
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    students = db.relationship('User', backref='group', lazy='dynamic', foreign_keys='User.group_id')
    
    @property
    def formatted_direction(self):
        """Standardized direction display: [Year] - [Code] - [Name] ([Education Type])"""
        if self.direction:
            year = self.enrollment_year if self.enrollment_year else "____"
            edu_type = _education_type_label(self.education_type)
            name_display = _cap_first(self.direction.name) if self.direction.name else (self.direction.name or '')
            return f"{year} - {self.direction.code} - {name_display} ({edu_type})"
        return self.name  # Fallback to group name if no direction

    def get_students_count(self):
        return self.students.count()


# ==================== FAN (SUBJECT) ====================
class Subject(db.Model):
    """Fan modeli"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=True)  # Fallback: name_uz yoki birinchi to'ldirilgan til
    name_uz = db.Column(db.String(200), nullable=True)
    name_ru = db.Column(db.String(200), nullable=True)
    name_en = db.Column(db.String(200), nullable=True)
    code = db.Column(db.String(20), nullable=True)  # Fan kodi (ixtiyoriy)
    department_id = db.Column(db.Integer, db.ForeignKey('department.id'))  # Kafedraga biriktirish
    description = db.Column(db.Text, nullable=True)  # Fallback
    description_uz = db.Column(db.Text, nullable=True)
    description_ru = db.Column(db.Text, nullable=True)
    description_en = db.Column(db.Text, nullable=True)
    credits = db.Column(db.Integer, default=3)  # Kredit soni
    semester = db.Column(db.Integer, default=1)  # 1-8 semestr
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def get_display_name(self, lang=None):
        if lang == 'ru' and self.name_ru:
            return self.name_ru
        if lang == 'en' and self.name_en:
            return self.name_en
        return self.name_uz or self.name_ru or self.name_en or self.name or ''
    
    def get_display_description(self, lang=None):
        if lang == 'ru' and self.description_ru:
            return self.description_ru
        if lang == 'en' and self.description_en:
            return self.description_en
        return self.description_uz or self.description_ru or self.description_en or self.description or ''
    
    # Relationships
    lessons = db.relationship('Lesson', backref='subject', lazy='dynamic', cascade='all, delete-orphan')
    assignments = db.relationship('Assignment', backref='subject', lazy='dynamic', cascade='all, delete-orphan')
    teacher_assignments = db.relationship('TeacherSubject', backref='subject', lazy='dynamic', cascade='all, delete-orphan')
    schedules = db.relationship('Schedule', backref='subject', lazy='dynamic', cascade='all, delete-orphan')
    
    def get_teacher(self, group_id=None):
        """Ushbu fan uchun biriktirilgan o'qituvchini olish (birinchi topilgan)"""
        query = TeacherSubject.query.filter_by(subject_id=self.id)
        if group_id:
            query = query.filter_by(group_id=group_id)
        assignment = query.first()
        return assignment.teacher if assignment else None

    def get_teacher_for_type(self, group_id, lesson_type):
        """Ushbu fan uchun dars turi bo'yicha biriktirilgan o'qituvchini olish"""
        # lesson_type formatini to'g'irlash (Maruza -> maruza)
        normalized_type = (lesson_type or '').lower().strip()
        
        # 1. Exact match search
        assignment = TeacherSubject.query.filter_by(
            subject_id=self.id,
            group_id=group_id,
            lesson_type=normalized_type
        ).first()
        
        # 2. Normalized fallback if not found
        db_type = normalized_type # Initialize for potential use in fallback
        if not assignment:
            if 'maru' in normalized_type or 'lect' in normalized_type:
                db_type = 'maruza'
            elif 'sem' in normalized_type:
                db_type = 'seminar'
            else:
                db_type = 'amaliyot' if 'amal' in normalized_type or 'lab' in normalized_type or 'kurs' in normalized_type else normalized_type
            
            if db_type != normalized_type:
                assignment = TeacherSubject.query.filter_by(
                    subject_id=self.id,
                    group_id=group_id,
                    lesson_type=db_type
                ).first()

        # Har bir guruh uchun faqat o'sha guruhga biriktirilgan o'qituvchini qaytarish.
        # Boshqa guruhlardan fallback qilmaslik - aks holda forma boshqa guruhni avtomatik to'ldiradi.
        return assignment.teacher if assignment else None
    
    def check_curriculum_completion(self, direction_id=None, teacher_id=None, is_admin=False, group=None):
        """O'quv reja bo'yicha darslar to'liqligini tekshirish
        Args:
            direction_id: Yo'nalish ID
            teacher_id: O'qituvchi ID (agar berilgan bo'lsa, faqat shu o'qituvchiga biriktirilgan dars turlari tekshiriladi)
            is_admin: Admin uchun barcha dars turlarini ko'rsatish
            group: Guruh obyekti (enrollment_year, education_type, semester bo'yicha to'g'ri o'quv rejani olish uchun)
        Returns: {'has_issue': bool, 'warnings': list, 'stats': {'lessons_count': int, 'assignments_count': int}}
        """
        if not direction_id:
            return {'has_issue': False, 'warnings': [], 'stats': {'lessons_count': 0, 'assignments_count': 0}}
        
        # Ushbu yo'nalish uchun o'quv rejani olish (guruh kontekstiga mos)
        curr_q = DirectionCurriculum.query.filter_by(
            direction_id=direction_id,
            subject_id=self.id
        )
        if group:
            curr_q = DirectionCurriculum.filter_by_group_context(curr_q, group)
            if group.semester:
                curr_q = curr_q.filter_by(semester=group.semester)
        curriculum = curr_q.first()
        
        if not curriculum:
            return {'has_issue': False, 'warnings': [], 'stats': {'lessons_count': 0, 'assignments_count': 0}}
        
        # Ushbu yo'nalishdagi guruhlar
        direction_group_ids = [g.id for g in db.session.query(Group).filter_by(direction_id=direction_id).all()]
        
        # Ushbu yo'nalish uchun barcha darslar va topshiriqlar soni
        lessons_count = Lesson.query.filter_by(
            subject_id=self.id,
            direction_id=direction_id
        ).count()
        
        assignments_count = Assignment.query.filter_by(
            subject_id=self.id,
            direction_id=direction_id
        ).count()
        
        # Agar teacher_id berilgan bo'lsa va admin emas bo'lsa, faqat shu o'qituvchiga biriktirilgan dars turlarini olish
        teacher_lesson_types = None
        if teacher_id and not is_admin:
            # O'qituvchiga biriktirilgan dars turlari
            teacher_assignments = db.session.query(TeacherSubject).filter(
                TeacherSubject.teacher_id == teacher_id,
                TeacherSubject.subject_id == self.id,
                TeacherSubject.group_id.in_(direction_group_ids)
            ).all()
            
            # Dars turlarini normallashtirish
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
                # Agar teacher_id berilgan bo'lsa va admin emas bo'lsa, faqat o'qituvchiga biriktirilgan dars turlarini tekshirish
                if teacher_lesson_types is not None and not is_admin and lesson_type not in teacher_lesson_types:
                    continue  # Bu dars turi o'qituvchiga biriktirilmagan, o'tkazib yuborish
                
                required = data['required_topics']
                actual = data['actual_topics']
                
                if lesson_type == 'kurs_ishi':
                    if actual < 1:
                        has_issue = True
                        warnings.append({
                            'lesson_type': lesson_type, 'no_topics': True,
                            'name': data['name'], 'hours': data['hours'],
                            'required': required, 'actual': actual, 'missing': 1.0
                        })
                elif actual < required:
                    has_issue = True
                    missing = required - actual
                    warnings.append({
                        'lesson_type': lesson_type, 'no_topics': False,
                        'name': data['name'], 'hours': data['hours'],
                        'required': required, 'actual': actual, 'missing': missing
                    })
        
        return {
            'has_issue': has_issue, 
            'warnings': warnings,
            'stats': {
                'lessons_count': lessons_count,
                'assignments_count': assignments_count
            }
        }

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
    
    # Qaysi o'quv yiliga va ta'lim shakliga tegishli ekanligi (Independent Curriculum)
    enrollment_year = db.Column(db.Integer, nullable=True) # 2025, 2026 ...
    education_type = db.Column(db.String(20), nullable=True) # kunduzgi, masofaviy ...

    hours_maruza = db.Column(db.Integer, default=0)  # M - Maruza soatlari
    hours_amaliyot = db.Column(db.Integer, default=0)  # A - Amaliyot soatlari
    hours_laboratoriya = db.Column(db.Integer, default=0)  # L - Laboratoriya soatlari
    hours_seminar = db.Column(db.Integer, default=0)  # S - Seminar soatlari
    hours_kurs_ishi = db.Column(db.Integer, default=0)  # K - Kurs ishi soatlari
    hours_mustaqil = db.Column(db.Integer, default=0)  # MT - Mustaqil ta'lim soatlari
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    subject = db.relationship('Subject', backref='curriculum_items')
    
    # Unique constraint: bir yo'nalishda bir semestrda bir fan bir marta bo'lishi kerak (yil va ta'lim shakli bo'yicha)
    __table_args__ = (db.UniqueConstraint('direction_id', 'subject_id', 'semester', 'enrollment_year', 'education_type', name='uq_direction_subject_semester_year_type'),)

    @staticmethod
    def filter_by_group_context(query, group):
        """Guruh kontekstiga mos o'quv reja elementlarini filtrlash.
        Agar guruhda enrollment_year va education_type bo'lsa, faqat aniq mos keladiganlar.
        NULL-NULL (eski/umumiy) yozuvlar guruh konteksti bor bo'lganda ko'rsatilmaydi."""
        if group and group.enrollment_year is not None and group.education_type:
            return query.filter(
                DirectionCurriculum.enrollment_year == group.enrollment_year,
                DirectionCurriculum.education_type == group.education_type
            )
        from sqlalchemy import or_
        return query.filter(
            or_(DirectionCurriculum.enrollment_year.is_(None), DirectionCurriculum.enrollment_year == (group.enrollment_year if group else None)),
            or_(DirectionCurriculum.education_type.is_(None), DirectionCurriculum.education_type == (group.education_type if group else None))
        )

    @staticmethod
    def remove_teacher_assignments_for_zeroed_hours(curriculum_item):
        """O'quv rejada soatlari 0 bo'lgan dars turlariga biriktirilgan o'qituvchilarni bekor qilish.
        Bu dars turi soatlari o'chirilganda TeacherSubject yozuvlarini avtomatik o'chiradi."""
        if not curriculum_item:
            return 0
        from app.models import TeacherSubject, Group
        from sqlalchemy import or_, func
        # Mos guruhlarni topish (yo'nalish, qabul yili, ta'lim shakli)
        groups_q = Group.query.filter_by(direction_id=curriculum_item.direction_id)
        if curriculum_item.enrollment_year is not None and curriculum_item.education_type:
            groups_q = groups_q.filter(
                Group.enrollment_year == curriculum_item.enrollment_year,
                Group.education_type == curriculum_item.education_type
            )
        elif curriculum_item.enrollment_year is not None:
            groups_q = groups_q.filter(Group.enrollment_year == curriculum_item.enrollment_year)
        elif curriculum_item.education_type:
            groups_q = groups_q.filter(Group.education_type == curriculum_item.education_type)
        group_ids = [g.id for g in groups_q.all()]
        if not group_ids:
            return 0
        # Soatlari 0 bo'lgan dars turlari
        zeroed_types = []
        if (curriculum_item.hours_maruza or 0) == 0:
            zeroed_types.append('maruza')
        if (curriculum_item.hours_amaliyot or 0) == 0:
            zeroed_types.append('amaliyot')
        if (curriculum_item.hours_laboratoriya or 0) == 0:
            zeroed_types.append('laboratoriya')
        if (curriculum_item.hours_seminar or 0) == 0:
            zeroed_types.append('seminar')
        if (curriculum_item.hours_kurs_ishi or 0) == 0:
            zeroed_types.append('kurs_ishi')
        if not zeroed_types:
            return 0
        # TeacherSubject.lesson_type ni kanonik formatga o'xshatish uchun variantlar
        lt_variants = {
            'maruza': ['maruza', 'maru', 'lect', 'лекция'],
            'amaliyot': ['amaliyot', 'amal', 'prac', 'практика'],
            'laboratoriya': ['laboratoriya', 'lab', 'lob', 'лаборатория'],
            'seminar': ['seminar', 'sem', 'семинар'],
            'kurs_ishi': ['kurs_ishi', 'kurs', 'course', 'курс'],
        }
        deleted_count = 0
        for canon in zeroed_types:
            variants = lt_variants.get(canon, [canon])
            ts_query = TeacherSubject.query.filter(
                TeacherSubject.subject_id == curriculum_item.subject_id,
                TeacherSubject.group_id.in_(group_ids)
            )
            to_delete = []
            for ts in ts_query.all():
                raw = (ts.lesson_type or '').strip().lower()
                if not raw:
                    continue
                matched = any(v in raw for v in variants) or raw == canon
                if matched:
                    to_delete.append(ts)
            for ts in to_delete:
                db.session.delete(ts)
                deleted_count += 1
        return deleted_count


# ==================== O'QITUVCHI-KAFEDRA BOG'LANISHI ====================
class TeacherDepartment(db.Model):
    """O'qituvchini kafedraga biriktirish"""
    __tablename__ = 'teacher_department'
    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    department_id = db.Column(db.Integer, db.ForeignKey('department.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    teacher = db.relationship('User', backref='department_memberships')


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


# ==================== ROL UCHUN RUXSATLAR (superadmin boshqaradi) ====================
class RolePermission(db.Model):
    """Rol uchun ruxsatlar – superadmin check orqali biriktirishi/o'chirishi mumkin"""
    __tablename__ = 'role_permissions'
    role = db.Column(db.String(30), primary_key=True)   # admin, dean, teacher, accounting, student
    permission = db.Column(db.String(80), primary_key=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# ==================== SAYT SOZLAMALARI (superadmin boshqaradi) ====================
class SiteSetting(db.Model):
    """Sayt sozlamalari – platforma nomi, logo va h.k. (key-value)"""
    __tablename__ = 'site_settings'
    key = db.Column(db.String(80), primary_key=True)
    value = db.Column(db.Text, nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @staticmethod
    def get(key, default=''):
        """Kalit bo'yicha qiymat olish"""
        row = SiteSetting.query.filter_by(key=key).first()
        return (row.value or '').strip() if row else default

    @staticmethod
    def set(key, value):
        """Kalit qiymatini o'rnatish"""
        row = SiteSetting.query.filter_by(key=key).first()
        if row:
            row.value = value
        else:
            row = SiteSetting(key=key, value=value)
            db.session.add(row)
        db.session.commit()


# ==================== FLASH XABAR ====================
class FlashMessage(db.Model):
    """Flash xabar (banner) – bir nechta yaratilishi mumkin, sarlavxada tanlangan til bo'yicha ko'rsatiladi"""
    __tablename__ = 'flash_message'
    id = db.Column(db.Integer, primary_key=True)
    text_uz = db.Column(db.Text, default='')
    text_ru = db.Column(db.Text, default='')
    text_en = db.Column(db.Text, default='')
    url = db.Column(db.String(500), default='')
    text_color = db.Column(db.String(20), default='white')  # white, red
    enabled = db.Column(db.Boolean, default=True)
    date_from = db.Column(db.Date, nullable=True)
    date_to = db.Column(db.Date, nullable=True)
    sort_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def get_text(self, lang):
        """Tanlangan til bo'yicha matn olish"""
        if lang == 'uz':
            return (self.text_uz or '').strip()
        if lang == 'ru':
            return (self.text_ru or '').strip()
        if lang == 'en':
            return (self.text_en or '').strip()
        return (self.text_uz or '').strip()

    def is_in_date_range(self, d=None):
        """Berilgan sana muddat ichidami"""
        if d is None:
            d = date.today()
        if self.date_from and d < self.date_from:
            return False
        if self.date_to and d > self.date_to:
            return False
        return True


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
    semester = db.Column(db.Integer)  # Semestr (1-8)
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
    managed_department_id = db.Column(db.Integer, db.ForeignKey('department.id'))  # Kafedra mudiri qaysi kafedrani boshqaradi
    description = db.Column(db.Text)  # Xodim haqida tavsif

    # Superadminlar bo'limi – bir nechta superadmin bo'lishi mumkin (config dagi login ham doim superadmin)
    superadmin_flag = db.Column(db.Boolean, default=False)
    
    # Relationships
    submissions = db.relationship('Submission', backref='student', lazy='dynamic', foreign_keys='Submission.student_id')
    announcements = db.relationship('Announcement', backref='author', lazy='dynamic')
    managed_faculty = db.relationship('Faculty', foreign_keys=[faculty_id], uselist=False)
    managed_department = db.relationship('Department', foreign_keys=[managed_department_id], uselist=False)
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

    def get_sorted_roles(self):
        """Rollarni tartiblangan holda qaytarish: admin, dean, edu_dept, department_head, teacher, accounting, student"""
        role_order = ['admin', 'dean', 'edu_dept', 'department_head', 'teacher', 'accounting', 'student']
        user_roles = self.get_roles()
        result = []
        for r in role_order:
            if r in user_roles:
                result.append(r)
        for r in user_roles:
            if r not in role_order:
                result.append(r)
        return result
    
    def has_role(self, role_name):
        """Foydalanuvchida bunday rol bormi?"""
        return role_name in self.get_roles()

    def is_dean_of_faculty(self, faculty_id):
        """Xodim (dekan) shu fakultetga biriktirilganmi? (faculty_id yoki user_faculty orqali)"""
        if not faculty_id:
            return False
        if self.faculty_id == faculty_id:
            return True
        return self.user_faculty_links.filter_by(faculty_id=faculty_id).first() is not None

    @property
    def is_superadmin(self):
        """Superadmin – config dagi login yoki DB dagi superadmin_flag"""
        if not self.login:
            return False
        if getattr(self, 'superadmin_flag', False):
            return True
        try:
            from flask import current_app
            return current_app.config.get('SUPERADMIN_LOGIN', '').strip() == self.login.strip()
        except RuntimeError:
            return False

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
        """Asosiy rol nomini olish (superadmin uchun Superadmin)"""
        if getattr(self, 'is_superadmin', False):
            return 'Superadmin'
        roles = {
            'admin': 'Administrator',
            'teacher': "O'qituvchi",
            'student': 'Talaba',
            'dean': 'Dekan',
            'accounting': 'Buxgalteriya'
        }
        return roles.get(self.role, self.role)

    def get_all_roles_display(self):
        """Barcha rollarni ko'rinishda olish (superadmin birinchi)"""
        roles = {
            'admin': 'Administrator',
            'teacher': "O'qituvchi",
            'student': 'Talaba',
            'dean': 'Dekan',
            'accounting': 'Buxgalteriya',
            'superadmin': 'Superadmin',
        }
        if getattr(self, 'is_superadmin', False):
            result = [roles.get('superadmin', 'Superadmin')]
            user_roles = self.get_roles()
            role_order = ['admin', 'dean', 'teacher', 'accounting', 'student']
            for r in role_order:
                if r in user_roles:
                    result.append(roles.get(r, r))
            for r in user_roles:
                if r not in role_order and r != 'superadmin':
                    result.append(roles.get(r, r))
            return result
        user_roles = self.get_roles()
        role_order = ['admin', 'dean', 'teacher', 'accounting', 'student']
        sorted_roles = []
        for ordered_role in role_order:
            if ordered_role in user_roles:
                sorted_roles.append(roles.get(ordered_role, ordered_role))
        for role in user_roles:
            if role not in role_order:
                sorted_roles.append(roles.get(role, role))
        return sorted_roles
    
    def has_permission(self, permission, for_role=None):
        """Ruxsatni tekshirish. for_role berilsa, faqat shu rol uchun tekshiradi (tanlangan rol bo'yicha UI filtrlash)."""
        if self.is_superadmin:
            return True
        defaults = {
            'admin': ['view_admin_panel', 'view_users', 'create_user', 'edit_user', 'delete_user', 'toggle_user', 'reset_user_password',
                      'view_staff', 'create_staff', 'edit_staff', 'delete_staff', 'view_students', 'create_student', 'edit_student', 'delete_student',
                      'view_faculties', 'create_faculty', 'edit_faculty', 'delete_faculty', 'view_directions', 'create_direction', 'edit_direction', 'delete_direction',
                      'manage_groups', 'create_group', 'edit_group', 'delete_group', 'view_subjects', 'create_subject', 'edit_subject', 'delete_subject',
                      'view_curriculum', 'edit_curriculum', 'view_schedule', 'create_schedule', 'edit_schedule', 'delete_schedule',
                      'view_reports', 'view_grade_scale', 'manage_grade_scale', 'view_teachers', 'assign_teachers',
                      'export_subjects', 'import_subjects', 'import_schedule', 'import_students', 'import_staff',
                      'view_announcements', 'send_message', 'view_messages', 'view_departments', 'create_department', 'edit_department', 'delete_department'],
            'dean': ['view_dean_panel', 'view_subjects', 'view_students', 'view_teachers', 'view_reports',
                     'create_announcement', 'manage_groups', 'assign_teachers',
                     'dean_manage_students', 'dean_manage_directions', 'dean_manage_groups',
                     'dean_manage_curriculum', 'dean_manage_teachers', 'dean_manage_schedule',
                     'view_announcements', 'send_message', 'view_messages'],
            'edu_dept': ['view_directions', 'view_curriculum', 'edit_curriculum',
                         'view_subjects', 'create_subject'],
            'department_head': ['view_admin_panel', 'view_subjects',
                               'create_subject', 'view_teachers', 'assign_teachers'],
            'teacher': ['view_subjects', 'view_students', 'create_lesson', 'edit_lesson', 'delete_lesson',
                        'create_assignment', 'edit_assignment', 'delete_assignment',
                        'grade_students', 'view_submissions', 'create_announcement',
                        'view_announcements', 'send_message', 'view_messages'],
            'student': ['view_subjects', 'view_lessons', 'submit_assignment', 'view_grades', 'view_announcements', 'send_message', 'view_messages'],
            'accounting': ['view_accounting', 'view_students', 'view_reports', 'manage_payments', 'manage_contracts', 'view_contract_amounts', 'import_payments',
                          'view_announcements', 'send_message', 'view_messages'],
        }
        if for_role:
            if for_role not in self.get_roles():
                return False
            roles_to_check = [for_role]
        else:
            roles_to_check = self.get_roles()
        for role in roles_to_check:
            # Rol uchun DB da yozuv bo'lsa – faqat DB dagi ruxsatlar (superadmin sozlagan); bo'sh ro'yxat ham mumkin
            perms_list = RolePermission.query.filter_by(role=role).all()
            if perms_list:
                user_perms = [p.permission for p in perms_list if getattr(p, 'permission', '') and p.permission != '__configured__']
            else:
                user_perms = defaults.get(role, [])
            if permission in user_perms:
                return True
        return False
    
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
    max_score = db.Column(db.Float, default=100.0)
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
    score = db.Column(db.Float)
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


# ==================== TEST ====================
class Test(db.Model):
    """Test (savol-javob) modeli"""
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    subject_id = db.Column(db.Integer, db.ForeignKey('subject.id'), nullable=False)
    direction_id = db.Column(db.Integer, db.ForeignKey('direction.id'), nullable=True)
    group_id = db.Column(db.Integer, db.ForeignKey('group.id'), nullable=True)
    max_score = db.Column(db.Float, default=100.0)
    time_limit_minutes = db.Column(db.Integer, default=0)  # 0 = cheklovsiz
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    
    subject = db.relationship('Subject', backref='tests')
    direction = db.relationship('Direction', backref='tests')
    group = db.relationship('Group', backref='tests')
    questions = db.relationship('TestQuestion', backref='test', lazy='dynamic', order_by='TestQuestion.order', cascade='all, delete-orphan')
    submissions = db.relationship('TestSubmission', backref='test', lazy='dynamic', cascade='all, delete-orphan')


class TestQuestion(db.Model):
    """Test savoli"""
    id = db.Column(db.Integer, primary_key=True)
    test_id = db.Column(db.Integer, db.ForeignKey('test.id'), nullable=False)
    text = db.Column(db.Text, nullable=False)
    order = db.Column(db.Integer, default=0)
    points = db.Column(db.Float, default=1.0)
    
    options = db.relationship('TestOption', backref='question', lazy='dynamic', order_by='TestOption.order', cascade='all, delete-orphan')


class TestOption(db.Model):
    """Test javob variantlari"""
    id = db.Column(db.Integer, primary_key=True)
    question_id = db.Column(db.Integer, db.ForeignKey('test_question.id'), nullable=False)
    text = db.Column(db.String(500), nullable=False)
    is_correct = db.Column(db.Boolean, default=False)
    order = db.Column(db.Integer, default=0)


class TestSubmission(db.Model):
    """Talaba test topshirig'i"""
    id = db.Column(db.Integer, primary_key=True)
    test_id = db.Column(db.Integer, db.ForeignKey('test.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    score = db.Column(db.Float)
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)
    answers_json = db.Column(db.Text)  # {"question_id": "option_id", ...}
    
    student = db.relationship('User', backref='test_submissions')


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
    
    def get_teacher_lesson_types(self):
        """Bu o'qituvchiga biriktirilgan dars turlarini curriculum asosida olish"""
        # O'qituvchiga biriktirilgan turlarni olish
        assignments = TeacherSubject.query.filter_by(
            subject_id=self.subject_id,
            group_id=self.group_id,
            teacher_id=self.teacher_id
        ).all()
        
        if not assignments:
            return []
        
        # O'qituvchi qaysi kategoriyalarga biriktirilgan
        has_maruza = any(a.lesson_type and a.lesson_type.lower() in ('maruza', 'ma\'ruza', 'lecture') for a in assignments)
        has_amaliyot = any(a.lesson_type and a.lesson_type.lower() in ('amaliyot', 'practice') for a in assignments)
        has_seminar = any(a.lesson_type and a.lesson_type.lower() == 'seminar' for a in assignments)
        
        # Curriculum'ni olish (enrollment_year va education_type bilan)
        curriculum = None
        if self.group and self.group.direction:
            # Avval aniq moslikni qidirish
            curriculum = DirectionCurriculum.query.filter_by(
                direction_id=self.group.direction.id,
                subject_id=self.subject_id,
                semester=self.group.semester,
                enrollment_year=self.group.enrollment_year,
                education_type=self.group.education_type
            ).first()
            
            # Agar topilmasa, faqat direction, subject, semester bo'yicha qidirish
            if not curriculum:
                curriculum = DirectionCurriculum.query.filter_by(
                    direction_id=self.group.direction.id,
                    subject_id=self.subject_id,
                    semester=self.group.semester
                ).first()
        
        lesson_types = []
        
        # Maruza
        if has_maruza:
            if curriculum and curriculum.hours_maruza and curriculum.hours_maruza > 0:
                lesson_types.append('maruza')
            elif not curriculum:
                lesson_types.append('maruza')
        
        # Amaliyot kategoriyasi (amaliyot, laboratoriya, kurs ishi)
        if has_amaliyot:
            if curriculum:
                # Faqat soati bor turlarni ko'rsatish
                if curriculum.hours_amaliyot and curriculum.hours_amaliyot > 0:
                    lesson_types.append('amaliyot')
                if curriculum.hours_laboratoriya and curriculum.hours_laboratoriya > 0:
                    lesson_types.append('laboratoriya')
                if curriculum.hours_kurs_ishi and curriculum.hours_kurs_ishi > 0:
                    lesson_types.append('kurs ishi')
                # Agar hech biri yo'q - hech narsa qo'shmaymiz
            else:
                # Curriculum yo'q - umumiy amaliyot
                lesson_types.append('amaliyot')
        
        # Seminar
        if has_seminar:
            if curriculum and curriculum.hours_seminar and curriculum.hours_seminar > 0:
                lesson_types.append('seminar')
            elif not curriculum:
                lesson_types.append('seminar')
        
        return lesson_types


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
    period_start = db.Column(db.Date, nullable=True)  # Maxsus kontrakt boshlanish sanasi
    period_end = db.Column(db.Date, nullable=True)  # Maxsus kontrakt tugash sanasi
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
        return (float(self.paid_amount) / float(self.contract_amount)) * 100


class DirectionContractAmount(db.Model):
    """Yo'nalish va o'quv yili bo'yicha standart kontrakt summasi (fakultet/yo'nalish uchun bir xil)"""
    id = db.Column(db.Integer, primary_key=True)
    direction_id = db.Column(db.Integer, db.ForeignKey('direction.id'), nullable=False)
    enrollment_year = db.Column(db.Integer, nullable=False)  # O'quv yili (2024, 2025)
    education_type = db.Column(db.String(20), nullable=True)  # kunduzgi, sirtqi, kechki (bo'sh bo'lsa barcha uchun)
    period_start = db.Column(db.Date, nullable=True)   # Boshlanish sanasi (masalan: 02.09.2025)
    period_end = db.Column(db.Date, nullable=True)     # Tugash sanasi (masalan: 06.06.2026)
    contract_amount = db.Column(db.Numeric(15, 2), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    direction = db.relationship('Direction', backref=db.backref('contract_amounts', lazy='dynamic', cascade='all, delete-orphan'))

    @staticmethod
    def get_contract_for_student(student):
        """Talaba guruhining yo'nalishi, qabul yili va ta'lim shakliga mos kontrakt summalarini yig'adi.
        Talaba qabul yilidan boshlab keyingi barcha o'quv yillaridagi kontrakt summalari qo'shiladi."""
        if not student or not student.group or not student.group.direction_id:
            return 0
        g = student.group
        base_year = g.enrollment_year or 0
        grp_et = (g.education_type or '').strip() or None
        amounts = DirectionContractAmount.query.filter(
            DirectionContractAmount.direction_id == g.direction_id,
            DirectionContractAmount.enrollment_year >= base_year
        ).all()
        # education_type bo'yicha filtrlash: aniq mos yoki NULL = barcha uchun
        filtered = []
        for a in amounts:
            a_et = (a.education_type or '').strip() or None
            if a_et is None or a_et == grp_et:
                filtered.append(a)
        return sum(float(a.contract_amount) for a in filtered)


# ==================== BAHOLASH TIZIMI ====================
class GradeScale(db.Model):
    """Baholash tizimi (ballik tizim)"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)  # A, B, C, D, F
    letter = db.Column(db.String(5), nullable=False)  # A, B, C, D, F
    min_score = db.Column(db.Float, nullable=False)  # Minimal ball
    max_score = db.Column(db.Float, nullable=False)  # Maksimal ball
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
        # Foiz scale_max ga yetgan yoki oshganda, eng yuqori bahoni qaytarish (60% da "–" o‘rniga A chiqishi uchun)
        if grade is None:
            scale_max = GradeScale.get_scale_max()
            if percent >= scale_max:
                top = GradeScale.query.filter(GradeScale.max_score == scale_max).order_by(GradeScale.order).first()
                if top:
                    return top
        return grade
    
    @staticmethod
    def get_all_ordered():
        """Barcha baholarni tartibda olish"""
        return GradeScale.query.order_by(GradeScale.order).all()
    
    @staticmethod
    def get_scale_max():
        """Baholash tizimidagi eng yuqori foiz (masalan 60 yoki 100)"""
        grades = GradeScale.query.all()
        if not grades:
            return 100.0
        return max(g.max_score for g in grades)
    
    @staticmethod
    def init_default_grades():
        """Standart baholarni yaratish"""
        if GradeScale.query.first() is not None:
            return
        
        default_grades = [
            {'letter': 'A', 'name': "A'lo", 'min_score': 90.0, 'max_score': 100.0, 'description': "A'lo natija", 'gpa_value': 5.0, 'color': 'green', 'order': 1, 'is_passing': True},
            {'letter': 'B', 'name': 'Yaxshi', 'min_score': 70.0, 'max_score': 89.99, 'description': 'Yaxshi natija', 'gpa_value': 4.0, 'color': 'blue', 'order': 2, 'is_passing': True},
            {'letter': 'C', 'name': 'Qoniqarli', 'min_score': 60.0, 'max_score': 69.99, 'description': 'Qoniqarli natija', 'gpa_value': 3.0, 'color': 'yellow', 'order': 3, 'is_passing': True},
            {'letter': 'D', 'name': "O'tmadi", 'min_score': 0.0, 'max_score': 59.99, 'description': "Qoniqarsiz natija", 'gpa_value': 2.0, 'color': 'red', 'order': 4, 'is_passing': False},
        ]
        
        for g in default_grades:
            grade = GradeScale(**g)
            db.session.add(grade)
        db.session.commit()
