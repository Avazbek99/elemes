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
        "Tug'ilgan sana (YYYY-MM-DD)",  # E
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

    # Namuna ma'lumotlar
    sample_data = [
        ["ST2024001", "Aliyev Vali", "AB1234567", "30202020200021", "2000-01-15", "+998901234567", "kunduzgi", "5230100", "Dasturiy injiniring", "1", "DI-21", "IT", "vali@example.com"],
        ["ST2024002", "Karimova Zuhra", "AC2345678", "30202020200022", "2001-03-20", "+998901234568", "kunduzgi", "5230100", "Dasturiy injiniring", "1", "DI-21", "IT", "zuhra@example.com"]
    ]

    for row_num, row_data in enumerate(sample_data, start=header_row + 1):
        for col_num, value in enumerate(row_data, 1):
            cell = ws.cell(row=row_num, column=col_num)
            cell.value = value
            cell.border = Border(
                left=Side(style='thin'),
                right=Side(style='thin'),
                top=Side(style='thin'),
                bottom=Side(style='thin')
            )

    # Ustun kengliklarini sozlash
    column_widths = [15, 25, 18, 18, 20, 16, 15, 25, 25, 12, 12, 15, 25]
    for col_num, width in enumerate(column_widths, 1):
        ws.column_dimensions[get_column_letter(col_num)].width = width

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output


def generate_staff_sample_file():
    """Xodimlarni import qilish uchun namuna Excel fayl (bitta sheet'da)"""
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
        from openpyxl.utils import get_column_letter
    except ImportError:
        raise ImportError("openpyxl kutubxonasi o'rnatilmagan. Iltimos, 'pip install openpyxl' buyrug'ini bajaring.")

    wb = Workbook()
    ws = wb.active
    ws.title = "Xodimlar"
    
    # Sarlavha
    title = "Xodimlar ro'yxati"
    ws.merge_cells('A1:L1')
    title_cell = ws['A1']
    title_cell.value = title
    title_cell.font = Font(size=16, bold=True, color="FFFFFF")
    title_cell.alignment = Alignment(horizontal='center', vertical='center')
    title_cell.fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
    
    # Sana
    from datetime import datetime
    ws['A2'] = f"Yaratilgan: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
    ws.merge_cells('A2:L2')
    ws['A2'].font = Font(size=10, italic=True)
    ws['A2'].alignment = Alignment(horizontal='center')
    
    # Jadval sarlavhalari
    headers = ['№', "To'liq ism", 'Email', 'Telefon', 'Pasport raqami', 'JSHSHIR', 'Tug\'ilgan sana', 'Kafedra', 'Lavozim', 'Fakultet', 'Rollar', 'Holat']
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
    
    # Namuna ma'lumotlar
    sample_data = [
        [1, "Tursunqulov Avazbek", "admin@university.uz", "+998901234567", "AB1234567", "30202020200021", "06.02.1999", "IT", "Administrator", "IT fakulteti", "Administrator", "Faol"],
        [2, "Karimov Sherzod", "dean.it@university.uz", "+998901234568", "AC2345678", "30202020200022", "15.05.1980", "IT", "Dekan", "IT fakulteti", "Dekan", "Faol"],
        [3, "Mamatov Valijon", "valijon@university.uz", "+998901234569", "AD3456789", "30202020200023", "20.08.1985", "Dasturiy injiniring", "Dotsent", "IT fakulteti", "O'qituvchi", "Faol"],
        [4, "Rahimova Aziza", "accounting@university.uz", "+998901234570", "AE4567890", "30202020200024", "10.12.1990", "Buxgalteriya", "Buxgalter", "", "Buxgalter", "Faol"],
        [5, "Aliyev Vali", "vali@university.uz", "+998901234571", "AF5678901", "30202020200025", "25.03.1988", "IT", "Dekan", "IT fakulteti", "Dekan, O'qituvchi", "Faol"]
    ]
    
    for row_num, row_data in enumerate(sample_data, start=header_row + 1):
        for col_num, value in enumerate(row_data, 1):
            cell = ws.cell(row=row_num, column=col_num)
            cell.value = value
            cell.border = Border(
                left=Side(style='thin'),
                right=Side(style='thin'),
                top=Side(style='thin'),
                bottom=Side(style='thin')
            )
    
    # Ustun kengliklarini sozlash
    column_widths = [5, 30, 25, 16, 18, 16, 14, 20, 15, 20, 30, 12]
    for col_num, width in enumerate(column_widths, 1):
        ws.column_dimensions[get_column_letter(col_num)].width = width
    
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output


def import_students_from_excel(file):
    """Excel fayldan talabalarni import qilish"""
    try:
        from openpyxl import load_workbook
        from app.models import User, Group, Faculty
        from app import db
        from datetime import datetime
    except ImportError:
        return {
            'success': False,
            'imported': 0,
            'errors': ["openpyxl kutubxonasi o'rnatilmagan"]
        }
    
    try:
        wb = load_workbook(file)
        ws = wb.active
        
        imported = 0
        errors = []
        
        # Sarlavha qatorini topish (3-qator)
        header_row = 3
        headers = []
        for col in range(1, ws.max_column + 1):
            cell_value = ws.cell(row=header_row, column=col).value
            if cell_value:
                headers.append(str(cell_value).strip())
        
        # Ma'lumotlarni o'qish
        for row_num in range(header_row + 1, ws.max_row + 1):
            try:
                row_data = {}
                for col_num, header in enumerate(headers, 1):
                    cell_value = ws.cell(row=row_num, column=col_num).value
                    row_data[header] = str(cell_value).strip() if cell_value else ''
                
                # Bo'sh qatorlarni o'tkazib yuborish
                if not row_data.get("To'liq ismi") and not row_data.get('Email'):
                    continue
                
                full_name = row_data.get("To'liq ismi", '').strip()
                email = row_data.get('Email', '').strip()
                passport_number = row_data.get('Pasport raqami', '').strip()
                
                if not full_name or not email or not passport_number:
                    errors.append(f"Qator {row_num}: Ism, email yoki pasport raqami kiritilmagan")
                    continue
                
                # Foydalanuvchini topish yoki yaratish
                user = User.query.filter_by(email=email).first()
                
                if user:
                    # Yangilash
                    user.full_name = full_name
                    user.phone = row_data.get('Telefon', '').strip() or None
                    user.student_id = row_data.get('Talaba ID', '').strip() or None
                    user.passport_number = passport_number
                    user.pinfl = row_data.get('JSHSHIR-kod', '').strip() or None
                    user.specialty = row_data.get('Mutaxassislik', '').strip() or None
                    user.specialty_code = row_data.get('Shifr (mutaxassislik kodi)', '').strip() or None
                    user.education_type = row_data.get("Ta'lim shakli", '').strip() or None
                    
                    # Tug'ilgan sana
                    birth_date_str = row_data.get("Tug'ilgan sana (YYYY-MM-DD)", '').strip()
                    if birth_date_str:
                        try:
                            user.birth_date = datetime.strptime(birth_date_str, '%Y-%m-%d').date()
                        except:
                            try:
                                user.birth_date = datetime.strptime(birth_date_str, '%d.%m.%Y').date()
                            except:
                                pass
                    
                    # Guruh
                    group_name = row_data.get('Guruh', '').strip()
                    if group_name:
                        group = Group.query.filter_by(name=group_name).first()
                        if group:
                            user.group_id = group.id
                    
                    user.set_password(passport_number)
                else:
                    # Yaratish
                    user = User(
                        email=email,
                        full_name=full_name,
                        role='student',
                        phone=row_data.get('Telefon', '').strip() or None,
                        student_id=row_data.get('Talaba ID', '').strip() or None,
                        passport_number=passport_number,
                        pinfl=row_data.get('JSHSHIR-kod', '').strip() or None,
                        specialty=row_data.get('Mutaxassislik', '').strip() or None,
                        specialty_code=row_data.get('Shifr (mutaxassislik kodi)', '').strip() or None,
                        education_type=row_data.get("Ta'lim shakli", '').strip() or None
                    )
                    
                    # Tug'ilgan sana
                    birth_date_str = row_data.get("Tug'ilgan sana (YYYY-MM-DD)", '').strip()
                    if birth_date_str:
                        try:
                            user.birth_date = datetime.strptime(birth_date_str, '%Y-%m-%d').date()
                        except:
                            try:
                                user.birth_date = datetime.strptime(birth_date_str, '%d.%m.%Y').date()
                            except:
                                pass
                    
                    # Guruh
                    group_name = row_data.get('Guruh', '').strip()
                    if group_name:
                        group = Group.query.filter_by(name=group_name).first()
                        if group:
                            user.group_id = group.id
                    
                    user.set_password(passport_number)
                    db.session.add(user)
                    imported += 1
                
            except Exception as e:
                errors.append(f"Qator {row_num}: Xatolik - {str(e)}")
        
        db.session.commit()
        
        return {
            'success': True,
            'imported': imported,
            'errors': errors
        }
        
    except Exception as e:
        return {
            'success': False,
            'imported': 0,
            'errors': [f"Fayl o'qishda xatolik: {str(e)}"]
        }


def import_directions_from_excel(file):
    """Excel fayldan yo'nalishlar va guruhlarni import qilish"""
    try:
        from openpyxl import load_workbook
        from app.models import Direction, Group, Faculty
        from app import db
    except ImportError:
        return {
            'success': False,
            'imported': 0,
            'errors': ["openpyxl kutubxonasi o'rnatilmagan"]
        }
    
    try:
        wb = load_workbook(file)
        ws = wb.active
        
        imported = 0
        errors = []
        
        # Sarlavha qatorini topish (1-qator)
        header_row = 1
        headers = []
        for col in range(1, ws.max_column + 1):
            cell_value = ws.cell(row=header_row, column=col).value
            if cell_value:
                headers.append(str(cell_value).strip())
        
        # Ma'lumotlarni o'qish
        for row_num in range(header_row + 1, ws.max_row + 1):
            try:
                row_data = {}
                for col_num, header in enumerate(headers, 1):
                    cell_value = ws.cell(row=row_num, column=col_num).value
                    row_data[header] = str(cell_value).strip() if cell_value else ''
                
                # Bo'sh qatorlarni o'tkazib yuborish
                if not row_data.get('Yo\'nalish nomi') and not row_data.get('Yo\'nalish kodi'):
                    continue
                
                direction_name = row_data.get('Yo\'nalish nomi', '').strip()
                direction_code = row_data.get('Yo\'nalish kodi', '').strip()
                faculty_name = row_data.get('Fakultet', '').strip()
                group_name = row_data.get('Guruh', '').strip()
                course_year = row_data.get('Kurs', '').strip()
                
                if not direction_name or not direction_code:
                    errors.append(f"Qator {row_num}: Yo'nalish nomi yoki kodi kiritilmagan")
                    continue
                
                # Fakultetni topish
                faculty = None
                if faculty_name:
                    faculty = Faculty.query.filter_by(name=faculty_name).first()
                    if not faculty:
                        errors.append(f"Qator {row_num}: Fakultet '{faculty_name}' topilmadi")
                        continue
                
                # Yo'nalishni topish yoki yaratish
                direction = Direction.query.filter_by(code=direction_code).first()
                if not direction:
                    if not faculty:
                        errors.append(f"Qator {row_num}: Fakultet kiritilmagan")
                        continue
                    direction = Direction(
                        name=direction_name,
                        code=direction_code,
                        description=row_data.get('Tavsif', '').strip() or None,
                        faculty_id=faculty.id
                    )
                    db.session.add(direction)
                    db.session.flush()
                    imported += 1
                
                # Guruhni topish yoki yaratish
                if group_name and faculty:
                    group = Group.query.filter_by(name=group_name).first()
                    if not group:
                        try:
                            course_year_int = int(course_year) if course_year else 1
                        except:
                            course_year_int = 1
                        
                        group = Group(
                            name=group_name,
                            faculty_id=faculty.id,
                            direction_id=direction.id,
                            course_year=course_year_int
                        )
                        db.session.add(group)
                
            except Exception as e:
                errors.append(f"Qator {row_num}: Xatolik - {str(e)}")
        
        db.session.commit()
        
        return {
            'success': True,
            'imported': imported,
            'errors': errors
        }
        
    except Exception as e:
        return {
            'success': False,
            'imported': 0,
            'errors': [f"Fayl o'qishda xatolik: {str(e)}"]
        }


def import_staff_from_excel(file):
    """Excel fayldan xodimlarni import qilish (bitta sheet'dan) - bir nechta rollarni qo'llab-quvvatlash"""
    try:
        from openpyxl import load_workbook
        from app.models import User, Faculty, UserRole
        from app import db
        from datetime import datetime
    except ImportError:
        return {
            'success': False,
            'imported': 0,
            'updated': 0,
            'errors': ["openpyxl kutubxonasi o'rnatilmagan"]
        }
    
    try:
        wb = load_workbook(file)
        ws = wb.active  # Bitta sheet'dan o'qish
        
        imported = 0
        updated = 0
        errors = []
        
        # Rol mapping (katta harfdan kichik harfga)
        role_mapping = {
            'Administrator': 'admin',
            'Dekan': 'dean',
            "O'qituvchi": 'teacher',
            'Buxgalter': 'accounting'
        }
        
        # Sarlavha qatorini topish (3-qator)
        header_row = 3
        headers = []
        for col in range(1, ws.max_column + 1):
            cell_value = ws.cell(row=header_row, column=col).value
            if cell_value:
                headers.append(str(cell_value).strip())
        
        # Ma'lumotlarni o'qish
        for row_num in range(header_row + 1, ws.max_row + 1):
            try:
                row_data = {}
                for col_num, header in enumerate(headers, 1):
                    cell_value = ws.cell(row=row_num, column=col_num).value
                    row_data[header] = str(cell_value).strip() if cell_value else ''
                
                # Bo'sh qatorlarni o'tkazib yuborish
                if not row_data.get("To'liq ism") and not row_data.get('Email'):
                    continue
                
                full_name = row_data.get("To'liq ism", '').strip()
                email = row_data.get('Email', '').strip()
                
                if not full_name or not email:
                    errors.append(f"Qator {row_num}: Ism yoki email kiritilmagan")
                    continue
                
                # Foydalanuvchini topish yoki yaratish
                user = User.query.filter_by(email=email).first()
                
                # Xodim uchun
                passport_number = row_data.get('Pasport raqami', '').strip()
                if not passport_number:
                    errors.append(f"Qator {row_num}: Pasport raqami kiritilmagan")
                    continue
                
                # Rollarni o'qish (Rollar ustunidan)
                roles_str = row_data.get('Rollar', '').strip()
                roles_list = []
                if roles_str:
                    # "Administrator, Dekan" formatidan rollarni ajratish
                    for role_display in roles_str.split(','):
                        role_display = role_display.strip()
                        role = role_mapping.get(role_display)
                        if role:
                            roles_list.append(role)
                
                if not roles_list:
                    errors.append(f"Qator {row_num}: Rollar kiritilmagan yoki noto'g'ri format")
                    continue
                
                # Asosiy rol (birinchi rol)
                primary_role = roles_list[0]
                
                if user:
                    # Yangilash
                    user.full_name = full_name
                    user.phone = row_data.get('Telefon', '').strip() or None
                    user.passport_number = passport_number
                    user.pinfl = row_data.get('JSHSHIR', '').strip() or None
                    user.department = row_data.get('Kafedra', '').strip() or None
                    user.position = row_data.get('Lavozim', '').strip() or None
                    
                    # Tug'ilgan sana
                    birth_date_str = row_data.get("Tug'ilgan sana", '').strip()
                    if birth_date_str:
                        try:
                            user.birth_date = datetime.strptime(birth_date_str, '%d.%m.%Y').date()
                        except:
                            pass
                    
                    # Fakultet (dekan uchun)
                    if 'dean' in roles_list:
                        faculty_name = row_data.get('Fakultet', '').strip()
                        if faculty_name:
                            faculty = Faculty.query.filter_by(name=faculty_name).first()
                            if faculty:
                                user.faculty_id = faculty.id
                    
                    user.set_password(passport_number)
                    
                    # Agar foydalanuvchi talaba bo'lsa, rolini o'zgartirish
                    if user.role == 'student':
                        user.role = primary_role
                    
                    # Bir nechta rollarni qo'llab-quvvatlash
                    # Eski rollarni o'chirish va yangilarini qo'shish
                    UserRole.query.filter_by(user_id=user.id).delete()
                    for role in roles_list:
                        user_role = UserRole(user_id=user.id, role=role)
                        db.session.add(user_role)
                    
                    updated += 1
                else:
                    # Yaratish
                    user = User(
                        email=email,
                        full_name=full_name,
                        role=primary_role,
                        phone=row_data.get('Telefon', '').strip() or None,
                        passport_number=passport_number,
                        pinfl=row_data.get('JSHSHIR', '').strip() or None,
                        department=row_data.get('Kafedra', '').strip() or None,
                        position=row_data.get('Lavozim', '').strip() or None
                    )
                    
                    # Tug'ilgan sana
                    birth_date_str = row_data.get("Tug'ilgan sana", '').strip()
                    if birth_date_str:
                        try:
                            user.birth_date = datetime.strptime(birth_date_str, '%d.%m.%Y').date()
                        except:
                            pass
                    
                    # Fakultet (dekan uchun)
                    if 'dean' in roles_list:
                        faculty_name = row_data.get('Fakultet', '').strip()
                        if faculty_name:
                            faculty = Faculty.query.filter_by(name=faculty_name).first()
                            if faculty:
                                user.faculty_id = faculty.id
                    
                    user.set_password(passport_number)
                    db.session.add(user)
                    db.session.flush()
                    
                    # Bir nechta rollarni qo'llab-quvvatlash
                    for role in roles_list:
                        user_role = UserRole(user_id=user.id, role=role)
                        db.session.add(user_role)
                    
                    imported += 1
                
            except Exception as e:
                errors.append(f"Qator {row_num}: Xatolik - {str(e)}")
        
        db.session.commit()
        
        return {
            'success': True,
            'imported': imported,
            'updated': updated,
            'errors': errors
        }
        
    except Exception as e:
        return {
            'success': False,
            'imported': 0,
            'updated': 0,
            'errors': [f"Fayl o'qishda xatolik: {str(e)}"]
        }


def import_all_users_from_excel(file):
    """Excel fayldan barcha foydalanuvchilarni import qilish (rol bo'yicha ajratish) - eski funksiya, import_staff_from_excel ishlatiladi"""
    return import_staff_from_excel(file)
