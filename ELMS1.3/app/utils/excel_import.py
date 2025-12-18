from flask import flash
import io
import re


def generate_sample_file():
    """Talabalarni import qilish uchun namuna Excel fayl (A–M ustunlari bilan)"""
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
        from openpyxl.utils import get_column_letter
    except ImportError:
        raise ImportError("openpyxl kutubxonasi o'rnatilmagan. Iltimos, 'pip install openpyxl' buyrug'ini bajaring.")

    wb = Workbook()
    ws = wb.active
    ws.title = "Talabalar import"

    # Sarlavha
    ws.merge_cells('A1:M1')
    title_cell = ws['A1']
    title_cell.value = "Talabalar import uchun namuna fayl"
    title_cell.font = Font(size=14, bold=True, color="FFFFFF")
    title_cell.alignment = Alignment(horizontal='center', vertical='center')
    title_cell.fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")

    # Jadval sarlavhalari (A–M)
    headers = [
        "Talaba ID",              # A
        "To'liq ismi",            # B
        "Pasport raqami",         # C
        "JSHSHIR-kod",            # D
        "Tug‘ilgan sana (YYYY-MM-DD)",  # E
        "Telefon",                # F
        "Ta'lim shakli",          # G
        "Shifr (mutaxassislik kodi)",  # H
        "Mutaxassislik",          # I
        "Talaba kursi",           # J
        "Guruh",                  # K
        "Fakultet",               # L (ixtiyoriy, dekanda odatda kerak emas)
        "Email"                   # M
    ]

    header_row = 3
    for col_num, header in enumerate(headers, 1):
        cell = ws.cell(row=header_row, column=col_num)
        cell.value = header
        cell.font = Font(bold=True, color="FFFFFF")
        cell.alignment = Alignment(horizontal='center', vertical='center')
        cell.fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
        cell.border = Border(
            left=Side(style='thin'),
            right=Side(style='thin'),
            top=Side(style='thin'),
            bottom=Side(style='thin')
        )

    # 1–2 ta namunaviy qator
    sample_rows = [
        ["STU0001", "Aliyev Anvar Anvar o'g'li", "AB1234567", "12345678901234", "2003-05-12",
         "+998 90 123 45 67", "kunduzgi", "5330200", "Dasturiy injiniring", 1, "DI-21", "Informatika fakulteti",
         "anvar.aliyev@example.com"],
        ["STU0002", "Karimova Dilnoza Sobir qizi", "AA7654321", "43210987654321", "2004-09-01",
         "+998 90 765 43 21", "sirtqi", "5330200", "Dasturiy injiniring", 2, "DI-22", "Informatika fakulteti",
         "dilnoza.karimova@example.com"],
    ]

    for row_idx, row_values in enumerate(sample_rows, start=header_row + 1):
        for col_num, value in enumerate(row_values, 1):
            cell = ws.cell(row=row_idx, column=col_num)
            cell.value = value
            cell.alignment = Alignment(horizontal='left', vertical='center')

    # Ustun kengliklari
    column_widths = [15, 30, 16, 16, 18, 16, 14, 18, 24, 12, 14, 22, 28]
    from openpyxl.utils import get_column_letter
    for col_num, width in enumerate(column_widths, 1):
        ws.column_dimensions[get_column_letter(col_num)].width = width

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output


def import_students_from_excel(file, faculty_id=None):
    """Excel fayldan talabalar ro'yxatini import qilish"""
    try:
        from openpyxl import load_workbook
    except ImportError:
        raise ImportError("openpyxl kutubxonasi o'rnatilmagan. Iltimos, 'pip install openpyxl' buyrug'ini bajaring.")
    
    from app.models import User, Group
    from app import db
    
    try:
        # Excel faylni o'qish
        wb = load_workbook(filename=io.BytesIO(file.read()))
        ws = wb.active
        
        imported_count = 0
        errors = []
        
        # Sarlavha qatorini topish (3-qator yoki 1-qator)
        header_row = None
        for row_idx in range(1, min(5, ws.max_row + 1)):
            row_values = [str(cell.value).strip() if cell.value else '' for cell in ws[row_idx]]
            # Sarlavhalarni tekshirish
            if any('ism' in val.lower() or 'name' in val.lower() for val in row_values):
                header_row = row_idx
                break
        
        if header_row is None:
            header_row = 1  # Agar topilmasa, 1-qatordan boshlash
        
        # Ustunlar indekslarini topish
        headers = [str(cell.value).strip().lower() if cell.value else '' for cell in ws[header_row]]
        
        # Ustunlar indekslarini aniqlash (A–M formatini ham qo'llab-quvvatlaydi)
        col_indices = {}
        for idx, header in enumerate(headers, 1):
            header_lower = header.lower()
            if ('id' in header_lower and 'talaba' in header_lower) or header_lower.startswith('talaba id'):
                col_indices['student_id'] = idx
            elif 'ism' in header_lower or 'name' in header_lower or 'to\'liq' in header_lower:
                col_indices['full_name'] = idx
            elif 'email' in header_lower:
                col_indices['email'] = idx
            elif 'telefon' in header_lower or 'phone' in header_lower:
                col_indices['phone'] = idx
            elif 'guruh' in header_lower or 'group' in header_lower:
                col_indices['group'] = idx
            elif 'qabul' in header_lower or 'enrollment' in header_lower or 'yil' in header_lower:
                col_indices['enrollment_year'] = idx
            elif 'pasport' in header_lower:
                col_indices['passport'] = idx
            elif 'jshshir' in header_lower or 'pinfl' in header_lower:
                col_indices['pinfl'] = idx
            elif 'tug' in header_lower and 'sana' in header_lower:
                col_indices['birth_date'] = idx
            elif 'ta\'lim' in header_lower or 'education' in header_lower:
                col_indices['education_type'] = idx
            elif 'shifr' in header_lower or 'mutaxassislik kodi' in header_lower or 'specialty code' in header_lower:
                col_indices['specialty_code'] = idx
            elif 'mutaxassislik' in header_lower or 'specialty' in header_lower:
                col_indices['specialty'] = idx
            elif 'kurs' in header_lower or 'course' in header_lower:
                col_indices['course_year'] = idx
            elif 'fakultet' in header_lower or 'faculty' in header_lower:
                col_indices['faculty_name'] = idx
        
        # Ma'lumotlarni o'qish
        for row_idx in range(header_row + 1, ws.max_row + 1):
            row = ws[row_idx]
            
            # Bo'sh qatorni o'tkazib yuborish
            if not any(cell.value for cell in row):
                continue
            
            try:
                # Ma'lumotlarni olish
                full_name = str(row[col_indices.get('full_name', 1) - 1].value or '').strip()
                email = str(row[col_indices.get('email', 1) - 1].value or '').strip()
                
                # Minimal tekshiruvlar
                if not full_name or not email:
                    continue
                
                if '@' not in email:
                    errors.append(f"Qator {row_idx}: Noto'g'ri email format - {email}")
                    continue
                
                # Email takrorlanmasligini tekshirish
                if User.query.filter_by(email=email).first():
                    errors.append(f"Qator {row_idx}: Email allaqachon mavjud - {email}")
                    continue
                
                # Talaba ID
                student_id = None
                if 'student_id' in col_indices:
                    student_id_val = row[col_indices['student_id'] - 1].value
                    if student_id_val:
                        student_id = str(student_id_val).strip()
                        # Talaba ID takrorlanmasligini tekshirish
                        if student_id and User.query.filter_by(student_id=student_id).first():
                            errors.append(f"Qator {row_idx}: Talaba ID allaqachon mavjud - {student_id}")
                            continue
                
                # Telefon
                phone = None
                if 'phone' in col_indices:
                    phone_val = row[col_indices['phone'] - 1].value
                    if phone_val:
                        phone = str(phone_val).strip()
                
                # Guruh
                group_id = None
                if 'group' in col_indices:
                    group_name = str(row[col_indices['group'] - 1].value or '').strip()
                    if group_name:
                        # Guruh nomini topish
                        group = Group.query.filter_by(name=group_name.upper()).first()
                        if group:
                            # Fakultet tekshiruvi
                            if faculty_id and group.faculty_id != faculty_id:
                                errors.append(f"Qator {row_idx}: Guruh boshqa fakultetga tegishli - {group_name}")
                                continue
                            group_id = group.id
                        else:
                            errors.append(f"Qator {row_idx}: Guruh topilmadi - {group_name}")
                            continue
                
                # Qabul yili / kurs
                enrollment_year = None
                if 'enrollment_year' in col_indices:
                    year_val = row[col_indices['enrollment_year'] - 1].value
                    if year_val:
                        try:
                            enrollment_year = int(year_val)
                        except (ValueError, TypeError):
                            pass
                
                # Qo'shimcha talaba ma'lumotlari (agar ustunlar bo'lsa)
                extra_kwargs = {}
                if 'passport' in col_indices:
                    p_val = row[col_indices['passport'] - 1].value
                    if p_val:
                        extra_kwargs['passport_number'] = str(p_val).strip()
                if 'pinfl' in col_indices:
                    pin_val = row[col_indices['pinfl'] - 1].value
                    if pin_val:
                        extra_kwargs['pinfl'] = str(pin_val).strip()
                if 'birth_date' in col_indices:
                    b_val = row[col_indices['birth_date'] - 1].value
                    if b_val:
                        # Excel date obyekt bo'lishi yoki matn bo'lishi mumkin
                        from datetime import datetime
                        try:
                            if hasattr(b_val, 'strftime'):
                                extra_kwargs['birth_date'] = b_val
                            else:
                                extra_kwargs['birth_date'] = datetime.strptime(str(b_val), '%Y-%m-%d')
                        except Exception:
                            pass
                if 'education_type' in col_indices:
                    e_val = row[col_indices['education_type'] - 1].value
                    if e_val:
                        extra_kwargs['education_type'] = str(e_val).strip()
                if 'specialty_code' in col_indices:
                    sc_val = row[col_indices['specialty_code'] - 1].value
                    if sc_val:
                        extra_kwargs['specialty_code'] = str(sc_val).strip()
                if 'specialty' in col_indices:
                    s_val = row[col_indices['specialty'] - 1].value
                    if s_val:
                        extra_kwargs['specialty'] = str(s_val).strip()
                
                # Talaba yaratish
                student = User(
                    email=email,
                    full_name=full_name,
                    role='student',
                    student_id=student_id,
                    group_id=group_id,
                    enrollment_year=enrollment_year,
                    phone=phone,
                    **extra_kwargs
                )
                
                # Standart parol (foydalanuvchi keyinchalik o'zgartirishi mumkin)
                student.set_password('student123')
                
                db.session.add(student)
                imported_count += 1
                
            except Exception as e:
                errors.append(f"Qator {row_idx}: Xatolik - {str(e)}")
                continue
        
        # Ma'lumotlarni saqlash
        db.session.commit()
        
        return {
            'success': True,
            'imported': imported_count,
            'errors': errors
        }
        
    except Exception as e:
        return {
            'success': False,
            'imported': 0,
            'errors': [f"Fayl o'qishda xatolik: {str(e)}"]
        }


def import_directions_from_excel(file, faculty_id):
    """Excel fayldan yo'nalishlar va ularga tegishli guruhlarni import qilish"""
    try:
        from openpyxl import load_workbook
    except ImportError:
        raise ImportError("openpyxl kutubxonasi o'rnatilmagan. Iltimos, 'pip install openpyxl' buyrug'ini bajaring.")

    from app.models import Direction, Group, Faculty
    from app import db

    try:
        # Excel faylni o'qish
        wb = load_workbook(filename=io.BytesIO(file.read()))
        ws = wb.active

        imported_directions = 0
        imported_groups = 0
        errors = []

        faculty = Faculty.query.get(faculty_id)
        if not faculty:
            return {
                'success': False,
                'imported_directions': 0,
                'imported_groups': 0,
                'errors': ["Fakultet topilmadi"]
            }

        # Sarlavha qatorini 1-qatordan olamiz
        header_row = 1
        headers = [str(cell.value).strip().lower() if cell.value else '' for cell in ws[header_row]]

        # Ustun indekslarini aniqlash
        col_indices = {}
        for idx, header in enumerate(headers, 1):
            h = header.lower()
            if 'yo' in h and 'nalish' in h or 'direction' in h:
                col_indices['direction_name'] = idx
            elif 'kod' in h or 'code' in h:
                col_indices['direction_code'] = idx
            elif 'guruh' in h or 'group' in h:
                col_indices['group_name'] = idx
            elif 'kurs' in h or 'course' in h:
                col_indices['course_year'] = idx
            elif 'ta\'lim' in h or 'education' in h:
                col_indices['education_type'] = idx

        if 'direction_name' not in col_indices and 'direction_code' not in col_indices:
            return {
                'success': False,
                'imported_directions': 0,
                'imported_groups': 0,
                'errors': ["Excel faylda yo'nalish nomi yoki kodi ustuni topilmadi"]
            }

        # Ma'lumotlarni o'qish
        for row_idx in range(header_row + 1, ws.max_row + 1):
            row = ws[row_idx]

            # Bo'sh qatorni o'tkazib yuborish
            if not any(cell.value for cell in row):
                continue

            try:
                name = ''
                code = ''

                if 'direction_name' in col_indices:
                    name = str(row[col_indices['direction_name'] - 1].value or '').strip()
                if 'direction_code' in col_indices:
                    code = str(row[col_indices['direction_code'] - 1].value or '').strip()

                if not name and not code:
                    continue

                if not code:
                    # Agar kod bo'lmasa, nomdan qisqa kod yasaymiz
                    code = ''.join([word[0] for word in name.split()[:2]]).upper()

                # Yo'nalishni topish yoki yaratish
                direction = Direction.query.filter_by(faculty_id=faculty.id, code=code).first()
                if not direction:
                    direction = Direction(name=name or code, code=code, faculty_id=faculty.id)
                    db.session.add(direction)
                    db.session.flush()  # id olish uchun
                    imported_directions += 1
                else:
                    # Nom bo'sh bo'lmasa, yangilash
                    if name and direction.name != name:
                        direction.name = name

                # Guruh
                if 'group_name' in col_indices:
                    group_name = str(row[col_indices['group_name'] - 1].value or '').strip()
                    if group_name:
                        group_name_upper = group_name.upper()
                        group = Group.query.filter_by(name=group_name_upper, faculty_id=faculty.id).first()
                        if not group:
                            # Kurs va ta'lim shakli
                            course_year = 1
                            education_type = 'kunduzgi'
                            if 'course_year' in col_indices:
                                year_val = row[col_indices['course_year'] - 1].value
                                try:
                                    course_year = int(year_val) if year_val else 1
                                except (TypeError, ValueError):
                                    course_year = 1
                            if 'education_type' in col_indices:
                                edu_val = str(row[col_indices['education_type'] - 1].value or '').strip().lower()
                                if edu_val in ['kunduzgi', 'sirtqi', 'kechki']:
                                    education_type = edu_val

                            group = Group(
                                name=group_name_upper,
                                faculty_id=faculty.id,
                                course_year=course_year,
                                education_type=education_type,
                                direction_id=direction.id
                            )
                            db.session.add(group)
                            imported_groups += 1
                        else:
                            # Mavjud guruhni yo'nalishga biriktirish (agar hali biriktirilmagan bo'lsa)
                            if group.direction_id is None:
                                group.direction_id = direction.id

            except Exception as e:
                errors.append(f"Qator {row_idx}: Xatolik - {str(e)}")
                continue

        db.session.commit()

        return {
            'success': True,
            'imported_directions': imported_directions,
            'imported_groups': imported_groups,
            'errors': errors
        }

    except Exception as e:
        return {
            'success': False,
            'imported_directions': 0,
            'imported_groups': 0,
            'errors': [f"Fayl o'qishda xatolik: {str(e)}"]
        }


def import_payments_from_excel(file):
    """Excel fayldan to'lov ma'lumotlarini import qilish"""
    try:
        from openpyxl import load_workbook
    except ImportError:
        raise ImportError("openpyxl kutubxonasi o'rnatilmagan. Iltimos, 'pip install openpyxl' buyrug'ini bajaring.")
    
    from app.models import User, StudentPayment
    from app import db
    
    def parse_amount(value):
        """Summani raqamga aylantirish (bo'shliqlarni olib tashlash)"""
        if value is None:
            return 0
        if isinstance(value, (int, float)):
            return float(value)
        # Matndan raqamni ajratish
        value_str = str(value).replace(' ', '').replace(',', '')
        try:
            return float(value_str)
        except (ValueError, TypeError):
            return 0
    
    try:
        # Excel faylni o'qish
        wb = load_workbook(filename=io.BytesIO(file.read()))
        ws = wb.active
        
        imported_count = 0
        updated_count = 0
        errors = []
        
        # Sarlavha qatorini topish
        header_row = None
        for row_idx in range(1, min(5, ws.max_row + 1)):
            row_values = [str(cell.value).strip().lower() if cell.value else '' for cell in ws[row_idx]]
            # Sarlavhalarni tekshirish
            if any('talaba' in val and 'id' in val for val in row_values) or \
               any('ism' in val or 'name' in val for val in row_values):
                header_row = row_idx
                break
        
        if header_row is None:
            header_row = 1  # Agar topilmasa, 1-qatordan boshlash
        
        # Ustunlar indekslarini topish
        headers = [str(cell.value).strip().lower() if cell.value else '' for cell in ws[header_row]]
        
        # Ustunlar indekslarini aniqlash
        col_indices = {}
        for idx, header in enumerate(headers, 1):
            header_lower = header.lower()
            if 'talaba' in header_lower and 'id' in header_lower:
                col_indices['student_id'] = idx
            elif 'ism' in header_lower or 'name' in header_lower or 'to\'liq' in header_lower:
                col_indices['full_name'] = idx
            elif 'kontrakt' in header_lower or 'contract' in header_lower or 'miqdori' in header_lower:
                col_indices['contract_amount'] = idx
            elif 'to\'lagan' in header_lower or 'paid' in header_lower or 'tolagan' in header_lower:
                col_indices['paid_amount'] = idx
        
        # Ma'lumotlarni o'qish
        for row_idx in range(header_row + 1, ws.max_row + 1):
            row = ws[row_idx]
            
            # Bo'sh qatorni o'tkazib yuborish
            if not any(cell.value for cell in row):
                continue
            
            try:
                # Talaba ID yoki ism orqali talabani topish
                student = None
                
                # Talaba ID orqali
                if 'student_id' in col_indices:
                    student_id_val = row[col_indices['student_id'] - 1].value
                    if student_id_val:
                        student_id_str = str(student_id_val).strip()
                        student = User.query.filter_by(student_id=student_id_str, role='student').first()
                
                # Ism orqali (agar ID topilmasa)
                if not student and 'full_name' in col_indices:
                    full_name = str(row[col_indices['full_name'] - 1].value or '').strip()
                    if full_name:
                        student = User.query.filter_by(full_name=full_name, role='student').first()
                
                if not student:
                    name_val = row[col_indices.get('full_name', 1) - 1].value if 'full_name' in col_indices else 'Noma\'lum'
                    errors.append(f"Qator {row_idx}: Talaba topilmadi - {name_val}")
                    continue
                
                # Kontrakt miqdori
                contract_amount = 0
                if 'contract_amount' in col_indices:
                    contract_val = row[col_indices['contract_amount'] - 1].value
                    contract_amount = parse_amount(contract_val)
                
                if contract_amount <= 0:
                    errors.append(f"Qator {row_idx}: Kontrakt miqdori noto'g'ri - {student.full_name}")
                    continue
                
                # To'lagan summa
                paid_amount = 0
                if 'paid_amount' in col_indices:
                    paid_val = row[col_indices['paid_amount'] - 1].value
                    paid_amount = parse_amount(paid_val)
                
                # Mavjud yozuvni topish yoki yangi yaratish
                payment = StudentPayment.query.filter_by(student_id=student.id).first()
                
                if payment:
                    # Yangilash
                    payment.contract_amount = contract_amount
                    payment.paid_amount = paid_amount
                    payment.updated_at = datetime.utcnow()
                    updated_count += 1
                else:
                    # Yangi yaratish
                    payment = StudentPayment(
                        student_id=student.id,
                        contract_amount=contract_amount,
                        paid_amount=paid_amount,
                        academic_year='2024-2025'  # Default
                    )
                    db.session.add(payment)
                    imported_count += 1
                
            except Exception as e:
                errors.append(f"Qator {row_idx}: Xatolik - {str(e)}")
                continue
        
        # Ma'lumotlarni saqlash
        db.session.commit()
        
        return {
            'success': True,
            'imported': imported_count,
            'updated': updated_count,
            'errors': errors
        }
        
    except Exception as e:
        return {
            'success': False,
            'imported': 0,
            'updated': 0,
            'errors': [f"Fayl o'qishda xatolik: {str(e)}"]
        }

