# Translation dictionary for 3 languages: Uzbek, Russian, English
# Complete translations including base UI elements and all flash messages

TRANSLATIONS = {
    'uz': {
        # ============================================
        # SITE INFO
        # ============================================
        'site_name': 'TIQXMMI Milliy tadqiqot universitet LMS',
        'site_name_short': 'TIQXMMI LMS',
        'site_tagline': 'Masofaviy ta\'lim platformasi',
        'university_name': 'TIQXMMI Milliy tadqiqot universitet',
        
        # ============================================
        # COMMON UI ELEMENTS
        # ============================================
        'dashboard': 'Bosh sahifa',
        'logout': 'Chiqish',
        'login': 'Kirish',
        'register': "Ro'yxatdan o'tish",
        'settings': 'Sozlamalar',
        'search': 'Qidirish',
        'save': "Saqlash",
        'cancel': 'Bekor qilish',
        'delete': "O'chirish",
        'edit': "Tahrirlash",
        'create': 'Yaratish',
        'back': 'Orqaga',
        'next': 'Keyingi',
        'previous': 'Oldingi',
        'submit': 'Yuborish',
        'close': 'Yopish',
        'yes': 'Ha',
        'no': "Yo'q",
        'actions': 'Amallar',
        'status': 'Holat',
        'date': 'Sana',
        'name': 'Ism',
        'email': 'Email',
        'phone': 'Telefon',
        'password': 'Parol',
        'confirm_password': 'Parolni tasdiqlash',
        'role': 'Rol',
        'active': 'Faol',
        'inactive': 'Nofaol',
        
        # ============================================
        # ROLES
        # ============================================
        'admin': 'Administrator',
        'dean': 'Dekan',
        'teacher': "O'qituvchi",
        'student': 'Talaba',
        
        # ============================================
        # DASHBOARD ELEMENTS
        # ============================================
        'welcome': 'Xush kelibsiz',
        'good_morning': 'Xayrli tong',
        'good_afternoon': 'Xayrli kun',
        'good_evening': 'Xayrli kech',
        'today': 'Bugun',
        'total_users': 'Jami foydalanuvchilar',
        'total_students': 'Jami talabalar',
        'total_teachers': "Jami o'qituvchilar",
        'total_faculties': 'Jami fakultetlar',
        'total_groups': 'Jami guruhlar',
        'total_subjects': 'Jami fanlar',
        
        # ============================================
        # SUBJECTS
        # ============================================
        'subjects': 'Fanlar',
        'subject': 'Fan',
        'subject_name': 'Fan nomi',
        'subject_code': 'Fan kodi',
        'credits': 'Kredit',
        'semester': 'Semestr',
        'lessons': 'Darslar',
        'lesson': 'Dars',
        'assignments': 'Topshiriqlar',
        'assignment': 'Topshiriq',
        'grades': 'Baholar',
        'grade': 'Baho',
        
        # ============================================
        # USERS
        # ============================================
        'users': 'Foydalanuvchilar',
        'user': 'Foydalanuvchi',
        'full_name': 'To\'liq ism',
        'student_id': 'Talaba ID',
        'group': 'Guruh',
        'groups': 'Guruhlar',
        'faculty': 'Fakultet',
        'faculties': 'Fakultetlar',
        
        # ============================================
        # MESSAGES
        # ============================================
        'messages': 'Xabarlar',
        'announcements': 'E\'lonlar',
        'schedule': 'Dars jadvali',
        
        # ============================================
        # GRADE SCALE
        # ============================================
        'grade_scale': 'Baholash tizimi',
        'excellent': 'A\'lo',
        'good': 'Yaxshi',
        'satisfactory': 'Qoniqarli',
        'poor': 'Past',
        'failed': 'Yiqildi',
        
        # ============================================
        # FLASH MESSAGES - AUTH
        # ============================================
        'no_access_permission': "Sizda bu sahifaga kirish huquqi yo'q",
        'account_blocked': 'Sizning hisobingiz bloklangan',
        'invalid_login_credentials': "Login, email, talaba ID yoki parol noto'g'ri",
        'logout_success': "Tizimdan muvaffaqiyatli chiqdingiz",
        'registration_closed': "Ro'yxatdan o'tish funksiyasi yopilgan. Iltimos, administrator bilan bog'laning.",
        'login_required_input': "Iltimos, login, talaba ID yoki email kiriting",
        'user_not_found_by_credentials': "Bu login, talaba ID yoki email bilan foydalanuvchi topilmadi",
        'function_only_for_teachers_students': "Bu funksiya faqat o'qituvchi va talabalar uchun mavjud",
        'passport_number_required_input': "Iltimos, pasport seriya raqamini kiriting",
        'user_not_found': "Foydalanuvchi topilmadi",
        'incorrect_passport_number': "Pasport seriya raqami noto'g'ri",
        'passport_not_available': "Foydalanuvchida pasport seriya raqami mavjud emas",
        'token_not_found_or_used': "Token topilmadi yoki allaqachon ishlatilgan",
        'token_expired': "Token muddati tugagan. Iltimos, yangi so'rov yuboring",
        'passwords_do_not_match': "Parollar mos kelmaydi",
        'password_min_length': "Parol kamida 6 ta belgidan iborat bo'lishi kerak",
        'password_min_length_8': "Parol kamida 8 ta belgidan iborat bo'lishi kerak",
        'password_changed_success': "Parol muvaffaqiyatli o'zgartirildi! Endi tizimga kiring",
        'password_changed_success_short': "Parol muvaffaqiyatli o'zgartirildi",
        'password_reset_success': "Parol muvaffaqiyatli boshlang'ich holatga qaytarildi! Parol: {new_password}",
        'user_password_reset': "{user.full_name} paroli boshlang'ich holatga qaytarildi. Yangi parol: {new_password}",
        'student_password_reset': "{student.full_name} paroli boshlang'ich holatga qaytarildi. Yangi parol: {new_password}",
        'no_permission_for_role': "Sizda bu rolga kirish huquqi yo'q",
        
        # ============================================
        # FLASH MESSAGES - VALIDATION ERRORS
        # ============================================
        'login_required_field': "Login majburiy maydon",
        'login_required_for_staff': "Login majburiy maydon (xodimlar uchun)",
        'login_already_exists': "Bu login allaqachon mavjud",
        'login_already_exists_other_user': "Bu login allaqachon boshqa foydalanuvchida mavjud",
        'student_id_required': "Talaba ID majburiy maydon",
        'student_id_required_for_students': "Talaba ID majburiy maydon (talabalar uchun)",
        'student_id_already_exists': "Bu talaba ID allaqachon mavjud",
        'student_id_already_exists_other_student': "Bu talaba ID allaqachon boshqa talabada mavjud",
        'email_already_exists': "Bu email allaqachon mavjud",
        'email_already_exists_other_user': "Bu email allaqachon boshqa foydalanuvchida mavjud",
        'email_already_exists_other_student': "Bu email allaqachon boshqa talabada mavjud",
        'email_used_by_another_user': "Bu email allaqachon boshqa foydalanuvchi tomonidan ishlatilmoqda",
        'passport_required': "Pasport seriyasi va raqami majburiy",
        'passport_not_available_for_user': "Bu foydalanuvchida pasport seriya raqami mavjud emas",
        'passport_not_available_for_student': "Bu talabada pasport seriya raqami mavjud emas",
        'birthdate_invalid_format': "Tug'ilgan sana noto'g'ri formatda (yyyy-mm-dd)",
        'date_invalid_format': "Sana noto'g'ri formatda",
        'date_invalid_format_use_calendar': "Sana noto'g'ri formatda. Iltimos, kalendardan tanlang.",
        'date_required': "Sana tanlanishi shart",
        'date_required_select': "Sana tanlanishi shart.",
        'all_required_fields': "Barcha majburiy maydonlar to'ldirilishi kerak",
        'all_fields_required': "Barcha maydonlar to'ldirilishi kerak",
        'at_least_one_role_required': "Kamida bitta rol tanlanishi kerak",
        'code_already_exists': "Bu kod allaqachon mavjud",
        'invalid_request': "Noto'g'ri murojaat",
        'title_and_text_required': "Sarlavha va matn majburiy",
        'message_cannot_be_empty': "Xabar bo'sh bo'lishi mumkin emas",
        'new_passwords_do_not_match': "Yangi parollar mos kelmaydi",
        
        # ============================================
        # FLASH MESSAGES - PERMISSION ERRORS
        # ============================================
        'no_permission_for_operation': "Sizda bu amal uchun ruxsat yo'q",
        'no_permission_for_action': "Sizda bu amal uchun huquq yo'q",
        'no_permission_to_edit_group': "Sizda bu guruhni tahrirlash huquqi yo'q",
        'no_permission_to_delete_group': "Sizda bu guruhni o'chirish huquqi yo'q",
        'no_permission_to_view_group': "Sizda bu guruhni ko'rish huquqi yo'q",
        'no_permission_to_add_students_to_group': "Sizda bu guruhga talaba qo'shish huquqi yo'q",
        'no_permission_to_edit_student': "Sizda bu talabani tahrirlash huquqi yo'q",
        'no_permission_to_create_announcement': "Sizda e'lon yaratish huquqi yo'q",
        'no_permission_to_edit_announcement': "Sizda bu e'lonni tahrirlash huquqi yo'q",
        'no_permission_to_delete_announcement': "Sizda bu e'lonni o'chirish huquqi yo'q",
        'no_permission_to_delete_all_announcements': "Sizda barcha e'lonlarni o'chirish huquqi yo'q",
        'no_permission_to_chat': "Sizda ushbu foydalanuvchi bilan suhbatlashish uchun ruxsat yo'q",
        'no_permission_to_view_course': "Sizda bu kursni ko'rish huquqi yo'q",
        'no_permission_to_edit_course': "Sizda bu kursni tahrirlash huquqi yo'q",
        'no_permission_to_delete_course': "Sizda bu kursni o'chirish huquqi yo'q",
        'no_permission_to_view_lesson': "Sizda bu darsni ko'rish huquqi yo'q",
        'no_permission_to_edit_lesson': "Sizda bu darsni tahrirlash huquqi yo'q",
        'no_permission_to_delete_lesson': "Sizda bu darsni o'chirish huquqi yo'q",
        'no_permission_to_view_assignment': "Sizda bu topshiriqni ko'rish huquqi yo'q",
        'no_permission_to_edit_assignment': "Sizda bu topshiriqni tahrirlash huquqi yo'q",
        'no_permission_to_delete_assignment': "Sizda bu topshiriqni o'chirish huquqi yo'q",
        'no_permission_to_view_submission': "Sizda bu javobni ko'rish huquqi yo'q",
        'no_permission_to_edit_submission': "Sizda bu javobni tahrirlash huquqi yo'q",
        'no_permission_to_delete_submission': "Sizda bu javobni o'chirish huquqi yo'q",
        'no_permission_to_view_grade': "Sizda bu bahoni ko'rish huquqi yo'q",
        'no_permission_to_edit_grade': "Sizda bu bahoni tahrirlash huquqi yo'q",
        'no_permission_to_delete_grade': "Sizda bu bahoni o'chirish huquqi yo'q",
        
        # ============================================
        # FLASH MESSAGES - USER OPERATIONS
        # ============================================
        'user_created_with_role': "{role} muvaffaqiyatli yaratildi",
        'user_status_changed': "Foydalanuvchi {status}",
        'user_updated': "Foydalanuvchi muvaffaqiyatli yangilandi",
        'user_deleted': "Foydalanuvchi o'chirildi",
        'staff_created': "Xodim {full_name} muvaffaqiyatli yaratildi",
        'staff_updated': "Xodim {full_name} ma'lumotlari yangilandi",
        'profile_updated': "Ma'lumotlar muvaffaqiyatli yangilandi",
        'profile_role_changed': "Profil {role_name} roliga o'zgartirildi. Endi siz {role_name} sifatida ishlayapsiz.",
        'cannot_block_yourself': "O'zingizni bloklashingiz mumkin emas",
        'cannot_delete_yourself': "O'zingizni o'chirishingiz mumkin emas",
        'user_not_staff': "Bu talaba, xodim emas",
        'user_not_student': "Bu foydalanuvchi talaba emas",
        
        # ============================================
        # FLASH MESSAGES - FACULTY OPERATIONS
        # ============================================
        'faculty_created': "Fakultet muvaffaqiyatli yaratildi",
        'faculty_updated': "Fakultet muvaffaqiyatli yangilandi",
        'faculty_deleted': "Fakultet «{faculty_name}» va uning barcha yo'nalishlari, guruhlari o'chirildi",
        'faculty_not_found': "Fakultet topilmadi",
        'faculty_required': "Fakultet tanlash majburiy",
        'faculty_selected_not_found': "Tanlangan fakultet topilmadi",
        'faculty_incorrect_selection': "Fakultet noto'g'ri tanlangan",
        'faculty_not_assigned': "Sizga fakultet biriktirilmagan",
        'faculty_required_for_dean': "Dekan roli tanlangan bo'lsa, fakultet tanlash majburiy",
        'faculty_has_students': "Fakultetda {students_count} ta talaba mavjud. Fakultetni o'chirish uchun avval talabalarni boshqa fakultetga ko'chiring yoki o'chiring",
        'responsible_deans_changed': "Masul dekanlar muvaffaqiyatli o'zgartirildi",
        
        # ============================================
        # FLASH MESSAGES - DIRECTION OPERATIONS
        # ============================================
        'direction_created': "Yo'nalish muvaffaqiyatli yaratildi",
        'direction_updated': "Yo'nalish yangilandi",
        'direction_deleted': "Yo'nalish o'chirildi",
        'direction_required': "Yo'nalish tanlash majburiy",
        'direction_incorrect_selection': "Noto'g'ri yo'nalish tanlandi",
        'direction_name_and_code_required': "Yo'nalish nomi va kodi majburiy",
        'direction_name_and_code_required_fill': "Yo'nalish nomi va kodi to'ldirilishi shart",
        'direction_already_exists': "Bu kod, kurs, semestr va ta'lim shakli bilan yo'nalish allaqachon mavjud",
        'direction_code_already_exists': "Bu kod bilan yo'nalish allaqachon mavjud",
        'direction_has_groups_and_students': "Yo'nalishda {groups_count} ta guruh va {total_students} ta talaba mavjud. O'chirish mumkin emas",
        'direction_has_groups': "Yo'nalishda {groups_count} ta guruh mavjud. Avval guruhlarni o'chiring yoki boshqa yo'nalishga o'tkazing",
        'direction_no_groups': "Yo'nalishda guruhlar mavjud emas",
        'groups_assigned_to_direction': "Guruhlar yo'nalishga biriktirildi",
        'directions_and_groups_imported': "{d_count} ta yo'nalish va {g_count} ta guruh import qilindi",
        
        # ============================================
        # FLASH MESSAGES - GROUP OPERATIONS
        # ============================================
        'group_created': "Guruh muvaffaqiyatli yaratildi",
        'group_updated': "Guruh yangilandi",
        'group_deleted': "Guruh o'chirildi",
        'group_name_required': "Guruh nomi majburiy",
        'group_already_exists': "Bu yo'nalishda, kursda va semestrda bunday nomli guruh allaqachon mavjud",
        'group_course_and_semester_required': "Kurs va semestr majburiy",
        'group_all_fields_required': "Kurs, semestr va ta'lim shakli majburiy",
        'group_has_students': "Guruhda talabalar bor. O'chirish mumkin emas",
        'group_has_students_transfer_first': "Guruhda talabalar mavjud. Avval talabalarni boshqa guruhga o'tkazing",
        'no_groups_for_year_education_type': "{year}-yil {education_type} ta'lim shakli bo'yicha guruhlar mavjud emas",
        'no_active_groups_for_semester': "{semester}-semestrda faol guruhlar topilmadi",
        
        # ============================================
        # FLASH MESSAGES - STUDENT OPERATIONS
        # ============================================
        'student_created': "{full_name} muvaffaqiyatli yaratildi",
        'student_updated': "{full_name} ma'lumotlari yangilandi",
        'student_deleted': "{student_name} o'chirildi",
        'student_status_changed': "Talaba {full_name} {status}",
        'students_added_to_group': "{added_count} ta talaba guruhga qo'shildi",
        'student_removed_from_group': "{full_name} guruhdan chiqarildi",
        'students_removed_from_group': "{count} ta talaba guruhdan chiqarildi",
        'no_students_selected': "Hech qanday talaba tanlanmagan",
        'no_students_added': "Hech qanday talaba qo'shilmadi. Tanlangan talabalar allaqachon boshqa guruhga biriktirilgan bo'lishi mumkin",
        'no_students_removed': "Hech qanday talaba guruhdan chiqarilmadi",
        
        # ============================================
        # FLASH MESSAGES - SUBJECT OPERATIONS
        # ============================================
        'subject_name_required': "Fan nomi majburiy maydon",
        'subject_created': "Fan muvaffaqiyatli yaratildi",
        'subject_updated': "Fan yangilandi",
        'subject_deleted': "Fan o'chirildi",
        'subject_not_in_curriculum': "Fan endi hech qanday o'quv rejada ishlatilmayapti. O'chirishingiz mumkin.",
        'subject_removed_from_all_curriculums': "«{subject_name}» barcha o'quv rejalardan olib tashlandi ({deleted} ta yozuv). Endi fanni o'chirishingiz mumkin.",
        'subject_not_found': "Tanlangan fan topilmadi",
        
        # ============================================
        # FLASH MESSAGES - CURRICULUM OPERATIONS
        # ============================================
        'subjects_added_to_curriculum': "{added} ta fan o'quv rejaga qo'shildi",
        'curriculum_updated': "{semester}-semestr o'quv rejasi yangilandi",
        'subject_removed_from_curriculum': "Fan o'quv rejasidan o'chirildi",
        'curriculum_import_success': "Muvaffaqiyatli! {imported} ta yangi qo'shildi, {updated} ta yangilandi.",
        'curriculum_import_subjects_created': "{subjects_created} ta yangi fan yaratildi.",
        'curriculum_import_errors': "{errors_count} ta xatolik yuz berdi.",
        'subject_already_in_semester': "{subject_name} fani bu semestrda allaqachon mavjud",
        'subject_replaced': "Fan {new_subject_name} ga almashtirildi",
        'subject_and_semester_required': "Fan va semestr tanlash majburiy",
        'new_subject_not_selected': "Yangi fan tanlanmagan",
        'semester_not_selected': "Semestr tanlanmagan",
        'semester_teachers_saved': "{semester}-semestr o'qituvchilari muvaffaqiyatli saqlandi",
        
        # ============================================
        # FLASH MESSAGES - SCHEDULE OPERATIONS
        # ============================================
        'schedule_added': "Dars jadvaliga qo'shildi",
        'schedule_updated': "Dars jadvali yangilandi",
        'schedule_deleted': "Jadval o'chirildi",
        'schedules_imported': "{count} ta dars jadvali muvaffaqiyatli import qilindi",
        'teacher_not_assigned_to_lesson_type': "Ushbu o'qituvchiga bu guruh va fan uchun dars turi biriktirilmagan",
        'lesson_already_exists_at_time': "Bu vaqtda ({start_time}) guruhda dars allaqachon mavjud: {existing_subject}",
        
        # ============================================
        # FLASH MESSAGES - GRADING SYSTEM
        # ============================================
        'grade_letter_already_exists': "Bu baho harfi allaqachon mavjud",
        'min_score_greater_than_max': "Minimal ball maksimaldan katta bo'lishi mumkin emas",
        'grade_added': "Baho muvaffaqiyatli qo'shildi",
        'grade_updated': "Baho yangilandi",
        'grade_deleted': "Baho o'chirildi",
        'grade_required': "Baho majburiy",
        'grade_assigned': "Baho muvaffaqiyatli qo'yildi",
        'grading_system_reset': "Baholash tizimi standart holatga qaytarildi",
        
        # ============================================
        # FLASH MESSAGES - COURSE/LESSON/ASSIGNMENT
        # ============================================
        'course_name_required': "Kurs nomi majburiy",
        'course_created': "Kurs muvaffaqiyatli yaratildi",
        'course_updated': "Kurs yangilandi",
        'course_deleted': "Kurs o'chirildi",
        'lesson_name_required': "Dars nomi majburiy",
        'lesson_created': "Dars muvaffaqiyatli yaratildi",
        'lesson_created_for_groups': "Dars {created_count} ta guruh uchun muvaffaqiyatli qo'shildi",
        'lesson_updated': "Dars yangilandi",
        'lesson_deleted': "Dars o'chirildi",
        'lesson_cannot_delete_has_assignments': "Bu mavzuni o'chirib bo'lmaydi! Quyidagi topshiriqlar bu mavzuga bog'langan: {assignments_list}",
        'assignment_name_required': "Topshiriq nomi majburiy",
        'assignment_created': "Topshiriq muvaffaqiyatli yaratildi",
        'assignment_created_for_groups': "Topshiriq {created_count} ta guruh uchun muvaffaqiyatli yaratildi",
        'assignment_updated': "Topshiriq yangilandi",
        'assignment_deleted': "Topshiriq o'chirildi",
        'submission_text_required': "Javob matni majburiy",
        'submission_submitted': "Javob muvaffaqiyatli yuborildi",
        'submission_resubmitted': "Javobingiz qayta yuborildi ({resubmission_count}/3)",
        'submission_updated': "Javob yangilandi",
        'submission_deleted': "Javob o'chirildi",
        'teacher_not_assigned_to_lesson_type_direction': "Siz tanlagan dars turiga ushbu yo'nalishda biriktirilmagansiz. Faqat o'zingizga biriktirilgan dars turlari uchun dars yarata olasiz.",
        'teacher_not_assigned_to_new_lesson_type': "Siz ushbu yo'nalishda '{lesson_type}' dars turiga biriktirilmagansiz. Faqat o'zingizga biriktirilgan dars turlarini o'zgartira olasiz.",
        'teacher_not_assigned_to_assignment_lesson_type': "Siz tanlagan dars turiga ushbu yo'nalishda biriktirilmagansiz.",
        'teacher_not_assigned_for_grading': "Sizda ushbu yo'nalishda '{lesson_type}' dars turiga biriktirilganligi yo'q. Faqat o'zingizga biriktirilgan dars turlari uchun baho qo'yishingiz mumkin.",
        
        # ============================================
        # FLASH MESSAGES - ANNOUNCEMENTS
        # ============================================
        'announcement_created': "E'lon muvaffaqiyatli yaratildi",
        'announcement_updated': "E'lon muvaffaqiyatli yangilandi",
        'announcement_deleted': "E'lon o'chirildi",
        'all_announcements_deleted': "Barcha {count} ta e'lon o'chirildi",
        
        # ============================================
        # FLASH MESSAGES - MESSAGING
        # ============================================
        'message_sent': "Xabar yuborildi",
        
        # ============================================
        # FLASH MESSAGES - ACCOUNTING
        # ============================================
        'contract_not_found': "Kontrakt ma'lumotlari topilmadi",
        'payment_info_updated': "To'lov ma'lumotlari yangilandi",
        
        # ============================================
        # FLASH MESSAGES - IMPORT/EXPORT
        # ============================================
        'file_not_selected': "Fayl tanlanmagan",
        'only_excel_files_allowed': "Faqat Excel fayllar (.xlsx, .xls) qo'llab-quvvatlanadi",
        'only_xlsx_or_xls_allowed': "Faqat .xlsx yoki .xls formatidagi fayllar qabul qilinadi",
        'only_xlsx_files_allowed': "Faqat .xlsx formatidagi fayllarni yuklash mumkin",
        'no_changes_made': "Hech qanday o'zgarish kiritilmadi",
        'no_students_imported': "Hech qanday talaba import qilinmadi",
        'students_imported': "{imported_count} ta talaba muvaffaqiyatli import qilindi",
        'no_subjects_imported': "Hech qanday fan import qilinmadi",
        'subjects_imported': "{imported_count} ta fan muvaffaqiyatli import qilindi",
        'subjects_updated': "{updated_count} ta fan yangilandi",
        'no_users_imported': "Hech qanday foydalanuvchi import qilinmadi",
        'users_imported': "{imported_count} ta foydalanuvchi muvaffaqiyatli import qilindi",
        'no_records_imported': "Hech qanday yozuv import qilinmadi",
        'records_imported': "{imported_count} ta yozuv muvaffaqiyatli import qilindi",
        'openpyxl_not_installed': "Excel export funksiyasi ishlamayapti. Iltimos, 'pip install openpyxl' buyrug'ini bajaring.",
        
        # ============================================
        # FLASH MESSAGES - ERROR MESSAGES
        # ============================================
        'error_occurred': "Xatolik yuz berdi: {error}",
        'import_error': "Import xatosi: {error}",
        'import_error_with_details': "Import xatosi: {errors}",
        'import_error_joined': "Import qilishda xatolik: {errors}",
        'export_error': "Export xatosi: {error}",
        'export_grades_error': "Eksport qilishda xatolik yuz berdi: {error}",
        'excel_import_not_working': "Excel import funksiyasi ishlamayapti: {error}",
        'template_file_creation_error': "Namuna fayl yaratishda xatolik: {error}",
        'template_file_download_error': "Namuna fayl yuklab olishda xatolik: {error}",
        'announcement_delete_error': "E'lonni o'chirishda xatolik yuz berdi: {error}",
        'announcements_delete_error': "E'lonlarni o'chirishda xatolik yuz berdi: {error}",
        'invalid_file_format': "Ruxsat berilmagan fayl formati: {filename}. Ruxsatli formatlar: PDF, DOC, DOCX, XLS, XLSX, PPT, PPTX, TXT, ZIP, RAR",
        'file_size_limit': "Fayl hajmi {max_size} MB dan oshmasligi kerak",
    },
    'ru': {
        # ============================================
        # SITE INFO
        # ============================================
        'site_name': 'ТИКХММИ Национальный исследовательский университет LMS',
        'site_name_short': 'ТИКХММИ LMS',
        'site_tagline': 'Платформа дистанционного обучения',
        'university_name': 'ТИКХММИ Национальный исследовательский университет',
        
        # ============================================
        # COMMON UI ELEMENTS
        # ============================================
        'dashboard': 'Главная',
        'logout': 'Выход',
        'login': 'Вход',
        'register': 'Регистрация',
        'settings': 'Настройки',
        'search': 'Поиск',
        'save': 'Сохранить',
        'cancel': 'Отмена',
        'delete': 'Удалить',
        'edit': 'Редактировать',
        'create': 'Создать',
        'back': 'Назад',
        'next': 'Следующий',
        'previous': 'Предыдущий',
        'submit': 'Отправить',
        'close': 'Закрыть',
        'yes': 'Да',
        'no': 'Нет',
        'actions': 'Действия',
        'status': 'Статус',
        'date': 'Дата',
        'name': 'Имя',
        'email': 'Email',
        'phone': 'Телефон',
        'password': 'Пароль',
        'confirm_password': 'Подтвердить пароль',
        'role': 'Роль',
        'active': 'Активный',
        'inactive': 'Неактивный',
        
        # ============================================
        # ROLES
        # ============================================
        'admin': 'Администратор',
        'dean': 'Декан',
        'teacher': 'Преподаватель',
        'student': 'Студент',
        
        # ============================================
        # DASHBOARD ELEMENTS
        # ============================================
        'welcome': 'Добро пожаловать',
        'good_morning': 'Доброе утро',
        'good_afternoon': 'Добрый день',
        'good_evening': 'Добрый вечер',
        'today': 'Сегодня',
        'total_users': 'Всего пользователей',
        'total_students': 'Всего студентов',
        'total_teachers': 'Всего преподавателей',
        'total_faculties': 'Всего факультетов',
        'total_groups': 'Всего групп',
        'total_subjects': 'Всего предметов',
        
        # ============================================
        # SUBJECTS
        # ============================================
        'subjects': 'Предметы',
        'subject': 'Предмет',
        'subject_name': 'Название предмета',
        'subject_code': 'Код предмета',
        'credits': 'Кредиты',
        'semester': 'Семестр',
        'lessons': 'Уроки',
        'lesson': 'Урок',
        'assignments': 'Задания',
        'assignment': 'Задание',
        'grades': 'Оценки',
        'grade': 'Оценка',
        
        # ============================================
        # USERS
        # ============================================
        'users': 'Пользователи',
        'user': 'Пользователь',
        'full_name': 'Полное имя',
        'student_id': 'ID студента',
        'group': 'Группа',
        'groups': 'Группы',
        'faculty': 'Факультет',
        'faculties': 'Факультеты',
        
        # ============================================
        # MESSAGES
        # ============================================
        'messages': 'Сообщения',
        'announcements': 'Объявления',
        'schedule': 'Расписание',
        
        # ============================================
        # GRADE SCALE
        # ============================================
        'grade_scale': 'Система оценивания',
        'excellent': 'Отлично',
        'good': 'Хорошо',
        'satisfactory': 'Удовлетворительно',
        'poor': 'Плохо',
        'failed': 'Неудовлетворительно',
        
        # ============================================
        # FLASH MESSAGES - AUTH
        # ============================================
        'no_access_permission': "У вас нет прав доступа к этой странице",
        'account_blocked': 'Ваш аккаунт заблокирован',
        'invalid_login_credentials': "Неверный логин, email, ID студента или пароль",
        'logout_success': "Вы успешно вышли из системы",
        'registration_closed': "Регистрация закрыта. Пожалуйста, свяжитесь с администратором.",
        'login_required_input': "Пожалуйста, введите логин, ID студента или email",
        'user_not_found_by_credentials': "Пользователь с таким логином, ID студента или email не найден",
        'function_only_for_teachers_students': "Эта функция доступна только для преподавателей и студентов",
        'passport_number_required_input': "Пожалуйста, введите серию и номер паспорта",
        'user_not_found': "Пользователь не найден",
        'incorrect_passport_number': "Неверная серия и номер паспорта",
        'passport_not_available': "У пользователя нет серии и номера паспорта",
        'token_not_found_or_used': "Токен не найден или уже использован",
        'token_expired': "Срок действия токена истек. Пожалуйста, отправьте новый запрос",
        'passwords_do_not_match': "Пароли не совпадают",
        'password_min_length': "Пароль должен содержать минимум 6 символов",
        'password_min_length_8': "Пароль должен содержать минимум 8 символов",
        'password_changed_success': "Пароль успешно изменен! Теперь войдите в систему",
        'password_changed_success_short': "Пароль успешно изменен",
        'password_reset_success': "Пароль успешно сброшен! Пароль: {new_password}",
        'user_password_reset': "Пароль {user.full_name} сброшен. Новый пароль: {new_password}",
        'student_password_reset': "Пароль {student.full_name} сброшен. Новый пароль: {new_password}",
        'no_permission_for_role': "У вас нет доступа к этой роли",
        
        # ============================================
        # FLASH MESSAGES - VALIDATION ERRORS
        # ============================================
        'login_required_field': "Логин обязательное поле",
        'login_required_for_staff': "Логин обязательное поле (для сотрудников)",
        'login_already_exists': "Этот логин уже существует",
        'login_already_exists_other_user': "Этот логин уже существует у другого пользователя",
        'student_id_required': "ID студента обязательное поле",
        'student_id_required_for_students': "ID студента обязательное поле (для студентов)",
        'student_id_already_exists': "Этот ID студента уже существует",
        'student_id_already_exists_other_student': "Этот ID студента уже существует у другого студента",
        'email_already_exists': "Этот email уже существует",
        'email_already_exists_other_user': "Этот email уже существует у другого пользователя",
        'email_already_exists_other_student': "Этот email уже существует у другого студента",
        'email_used_by_another_user': "Этот email уже используется другим пользователем",
        'passport_required': "Серия и номер паспорта обязательны",
        'passport_not_available_for_user': "У этого пользователя нет серии и номера паспорта",
        'passport_not_available_for_student': "У этого студента нет серии и номера паспорта",
        'birthdate_invalid_format': "Неверный формат даты рождения (yyyy-mm-dd)",
        'date_invalid_format': "Неверный формат даты",
        'date_invalid_format_use_calendar': "Неверный формат даты. Пожалуйста, выберите из календаря.",
        'date_required': "Дата обязательна для выбора",
        'date_required_select': "Дата обязательна для выбора.",
        'all_required_fields': "Все обязательные поля должны быть заполнены",
        'all_fields_required': "Все поля должны быть заполнены",
        'at_least_one_role_required': "Необходимо выбрать хотя бы одну роль",
        'code_already_exists': "Этот код уже существует",
        'invalid_request': "Неверный запрос",
        'title_and_text_required': "Заголовок и текст обязательны",
        'message_cannot_be_empty': "Сообщение не может быть пустым",
        'new_passwords_do_not_match': "Новые пароли не совпадают",
        
        # ============================================
        # FLASH MESSAGES - PERMISSION ERRORS
        # ============================================
        'no_permission_for_operation': "У вас нет разрешения на эту операцию",
        'no_permission_for_action': "У вас нет прав на это действие",
        'no_permission_to_edit_group': "У вас нет прав на редактирование этой группы",
        'no_permission_to_delete_group': "У вас нет прав на удаление этой группы",
        'no_permission_to_view_group': "У вас нет прав на просмотр этой группы",
        'no_permission_to_add_students_to_group': "У вас нет прав на добавление студентов в эту группу",
        'no_permission_to_edit_student': "У вас нет прав на редактирование этого студента",
        'no_permission_to_create_announcement': "У вас нет прав на создание объявления",
        'no_permission_to_edit_announcement': "У вас нет прав на редактирование этого объявления",
        'no_permission_to_delete_announcement': "У вас нет прав на удаление этого объявления",
        'no_permission_to_delete_all_announcements': "У вас нет прав на удаление всех объявлений",
        'no_permission_to_chat': "У вас нет разрешения на чат с этим пользователем",
        'no_permission_to_view_course': "У вас нет прав на просмотр этого курса",
        'no_permission_to_edit_course': "У вас нет прав на редактирование этого курса",
        'no_permission_to_delete_course': "У вас нет прав на удаление этого курса",
        'no_permission_to_view_lesson': "У вас нет прав на просмотр этого урока",
        'no_permission_to_edit_lesson': "У вас нет прав на редактирование этого урока",
        'no_permission_to_delete_lesson': "У вас нет прав на удаление этого урока",
        'no_permission_to_view_assignment': "У вас нет прав на просмотр этого задания",
        'no_permission_to_edit_assignment': "У вас нет прав на редактирование этого задания",
        'no_permission_to_delete_assignment': "У вас нет прав на удаление этого задания",
        'no_permission_to_view_submission': "У вас нет прав на просмотр этого ответа",
        'no_permission_to_edit_submission': "У вас нет прав на редактирование этого ответа",
        'no_permission_to_delete_submission': "У вас нет прав на удаление этого ответа",
        'no_permission_to_view_grade': "У вас нет прав на просмотр этой оценки",
        'no_permission_to_edit_grade': "У вас нет прав на редактирование этой оценки",
        'no_permission_to_delete_grade': "У вас нет прав на удаление этой оценки",
        
        # ============================================
        # FLASH MESSAGES - USER OPERATIONS
        # ============================================
        'user_created_with_role': "{role} успешно создан",
        'user_status_changed': "Пользователь {status}",
        'user_updated': "Пользователь успешно обновлен",
        'user_deleted': "Пользователь удален",
        'staff_created': "Сотрудник {full_name} успешно создан",
        'staff_updated': "Данные сотрудника {full_name} обновлены",
        'profile_updated': "Данные успешно обновлены",
        'profile_role_changed': "Профиль изменен на роль {role_name}. Теперь вы работаете как {role_name}.",
        'cannot_block_yourself': "Вы не можете заблокировать себя",
        'cannot_delete_yourself': "Вы не можете удалить себя",
        'user_not_staff': "Это студент, а не сотрудник",
        'user_not_student': "Этот пользователь не студент",
        
        # ============================================
        # FLASH MESSAGES - FACULTY OPERATIONS
        # ============================================
        'faculty_created': "Факультет успешно создан",
        'faculty_updated': "Факультет успешно обновлен",
        'faculty_deleted': "Факультет «{faculty_name}» и все его направления, группы удалены",
        'faculty_not_found': "Факультет не найден",
        'faculty_required': "Выбор факультета обязателен",
        'faculty_selected_not_found': "Выбранный факультет не найден",
        'faculty_incorrect_selection': "Факультет выбран неверно",
        'faculty_not_assigned': "Вам не назначен факультет",
        'faculty_required_for_dean': "Если выбрана роль декана, выбор факультета обязателен",
        'faculty_has_students': "На факультете {students_count} студентов. Для удаления факультета сначала переведите или удалите студентов",
        'responsible_deans_changed': "Ответственные деканы успешно изменены",
        
        # ============================================
        # FLASH MESSAGES - DIRECTION OPERATIONS
        # ============================================
        'direction_created': "Направление успешно создано",
        'direction_updated': "Направление обновлено",
        'direction_deleted': "Направление удалено",
        'direction_required': "Выбор направления обязателен",
        'direction_incorrect_selection': "Выбрано неверное направление",
        'direction_name_and_code_required': "Название и код направления обязательны",
        'direction_name_and_code_required_fill': "Название и код направления должны быть заполнены",
        'direction_already_exists': "Направление с этим кодом, курсом, семестром и формой обучения уже существует",
        'direction_code_already_exists': "Направление с этим кодом уже существует",
        'direction_has_groups_and_students': "В направлении {groups_count} групп и {total_students} студентов. Удаление невозможно",
        'direction_has_groups': "В направлении {groups_count} групп. Сначала удалите или переведите группы в другое направление",
        'direction_no_groups': "В направлении нет групп",
        'groups_assigned_to_direction': "Группы назначены направлению",
        'directions_and_groups_imported': "{d_count} направлений и {g_count} групп импортировано",
        
        # ============================================
        # FLASH MESSAGES - GROUP OPERATIONS
        # ============================================
        'group_created': "Группа успешно создана",
        'group_updated': "Группа обновлена",
        'group_deleted': "Группа удалена",
        'group_name_required': "Название группы обязательно",
        'group_already_exists': "Группа с таким названием уже существует в этом направлении, курсе и семестре",
        'group_course_and_semester_required': "Курс и семестр обязательны",
        'group_all_fields_required': "Курс, семестр и форма обучения обязательны",
        'group_has_students': "В группе есть студенты. Удаление невозможно",
        'group_has_students_transfer_first': "В группе есть студенты. Сначала переведите студентов в другую группу",
        'no_groups_for_year_education_type': "Нет групп для {year} года по форме обучения {education_type}",
        'no_active_groups_for_semester': "Не найдено активных групп для семестра {semester}",
        
        # ============================================
        # FLASH MESSAGES - STUDENT OPERATIONS
        # ============================================
        'student_created': "{full_name} успешно создан",
        'student_updated': "Данные {full_name} обновлены",
        'student_deleted': "{student_name} удален",
        'student_status_changed': "Студент {full_name} {status}",
        'students_added_to_group': "{added_count} студентов добавлено в группу",
        'student_removed_from_group': "{full_name} удален из группы",
        'students_removed_from_group': "{count} студентов удалено из группы",
        'no_students_selected': "Не выбрано ни одного студента",
        'no_students_added': "Не добавлено ни одного студента. Выбранные студенты могут быть уже прикреплены к другой группе",
        'no_students_removed': "Не удален ни один студент из группы",
        
        # ============================================
        # FLASH MESSAGES - SUBJECT OPERATIONS
        # ============================================
        'subject_name_required': "Название предмета обязательное поле",
        'subject_created': "Предмет успешно создан",
        'subject_updated': "Предмет обновлен",
        'subject_deleted': "Предмет удален",
        'subject_not_in_curriculum': "Предмет больше не используется ни в одном учебном плане. Вы можете удалить его.",
        'subject_removed_from_all_curriculums': "«{subject_name}» удален из всех учебных планов ({deleted} записей). Теперь вы можете удалить предмет.",
        'subject_not_found': "Выбранный предмет не найден",
        
        # ============================================
        # FLASH MESSAGES - CURRICULUM OPERATIONS
        # ============================================
        'subjects_added_to_curriculum': "{added} предметов добавлено в учебный план",
        'curriculum_updated': "Учебный план {semester} семестра обновлен",
        'subject_removed_from_curriculum': "Предмет удален из учебного плана",
        'curriculum_import_success': "Успешно! {imported} новых добавлено, {updated} обновлено.",
        'curriculum_import_subjects_created': "{subjects_created} новых предметов создано.",
        'curriculum_import_errors': "{errors_count} ошибок произошло.",
        'subject_already_in_semester': "Предмет {subject_name} уже существует в этом семестре",
        'subject_replaced': "Предмет заменен на {new_subject_name}",
        'subject_and_semester_required': "Выбор предмета и семестра обязателен",
        'new_subject_not_selected': "Новый предмет не выбран",
        'semester_not_selected': "Семестр не выбран",
        'semester_teachers_saved': "Преподаватели семестра {semester} успешно сохранены",
        
        # ============================================
        # FLASH MESSAGES - SCHEDULE OPERATIONS
        # ============================================
        'schedule_added': "Добавлено в расписание занятий",
        'schedule_updated': "Расписание занятий обновлено",
        'schedule_deleted': "Расписание удалено",
        'schedules_imported': "{count} расписаний успешно импортировано",
        'teacher_not_assigned_to_lesson_type': "Этому преподавателю не назначен тип занятия для этой группы и предмета",
        'lesson_already_exists_at_time': "В это время ({start_time}) у группы уже есть занятие: {existing_subject}",
        
        # ============================================
        # FLASH MESSAGES - GRADING SYSTEM
        # ============================================
        'grade_letter_already_exists': "Эта буква оценки уже существует",
        'min_score_greater_than_max': "Минимальный балл не может быть больше максимального",
        'grade_added': "Оценка успешно добавлена",
        'grade_updated': "Оценка обновлена",
        'grade_deleted': "Оценка удалена",
        'grade_required': "Оценка обязательна",
        'grade_assigned': "Оценка успешно выставлена",
        'grading_system_reset': "Система оценивания возвращена к стандартному состоянию",
        
        # ============================================
        # FLASH MESSAGES - COURSE/LESSON/ASSIGNMENT
        # ============================================
        'course_name_required': "Название курса обязательно",
        'course_created': "Курс успешно создан",
        'course_updated': "Курс обновлен",
        'course_deleted': "Курс удален",
        'lesson_name_required': "Название урока обязательно",
        'lesson_created': "Урок успешно создан",
        'lesson_created_for_groups': "Урок успешно добавлен для {created_count} групп",
        'lesson_updated': "Урок обновлен",
        'lesson_deleted': "Урок удален",
        'lesson_cannot_delete_has_assignments': "Эту тему нельзя удалить! Следующие задания связаны с этой темой: {assignments_list}",
        'assignment_name_required': "Название задания обязательно",
        'assignment_created': "Задание успешно создано",
        'assignment_created_for_groups': "Задание успешно создано для {created_count} групп",
        'assignment_updated': "Задание обновлено",
        'assignment_deleted': "Задание удалено",
        'submission_text_required': "Текст ответа обязателен",
        'submission_submitted': "Ответ успешно отправлен",
        'submission_resubmitted': "Ваш ответ переотправлен ({resubmission_count}/3)",
        'submission_updated': "Ответ обновлен",
        'submission_deleted': "Ответ удален",
        'teacher_not_assigned_to_lesson_type_direction': "Вы не назначены на выбранный тип занятия в этом направлении. Вы можете создавать уроки только для назначенных вам типов занятий.",
        'teacher_not_assigned_to_new_lesson_type': "Вы не назначены на тип занятия '{lesson_type}' в этом направлении. Вы можете изменять только назначенные вам типы занятий.",
        'teacher_not_assigned_to_assignment_lesson_type': "Вы не назначены на выбранный тип занятия в этом направлении.",
        'teacher_not_assigned_for_grading': "Вы не назначены на тип занятия '{lesson_type}' в этом направлении. Вы можете выставлять оценки только для назначенных вам типов занятий.",
        
        # ============================================
        # FLASH MESSAGES - ANNOUNCEMENTS
        # ============================================
        'announcement_created': "Объявление успешно создано",
        'announcement_updated': "Объявление успешно обновлено",
        'announcement_deleted': "Объявление удалено",
        'all_announcements_deleted': "Все {count} объявлений удалены",
        
        # ============================================
        # FLASH MESSAGES - MESSAGING
        # ============================================
        'message_sent': "Сообщение отправлено",
        
        # ============================================
        # FLASH MESSAGES - ACCOUNTING
        # ============================================
        'contract_not_found': "Данные контракта не найдены",
        'payment_info_updated': "Платежная информация обновлена",
        
        # ============================================
        # FLASH MESSAGES - IMPORT/EXPORT
        # ============================================
        'file_not_selected': "Файл не выбран",
        'only_excel_files_allowed': "Поддерживаются только Excel файлы (.xlsx, .xls)",
        'only_xlsx_or_xls_allowed': "Принимаются только файлы формата .xlsx или .xls",
        'only_xlsx_files_allowed': "Можно загружать только файлы формата .xlsx",
        'no_changes_made': "Никаких изменений не внесено",
        'no_students_imported': "Не импортировано ни одного студента",
        'students_imported': "{imported_count} студентов успешно импортировано",
        'no_subjects_imported': "Не импортировано ни одного предмета",
        'subjects_imported': "{imported_count} предметов успешно импортировано",
        'subjects_updated': "{updated_count} предметов обновлено",
        'no_users_imported': "Не импортировано ни одного пользователя",
        'users_imported': "{imported_count} пользователей успешно импортировано",
        'no_records_imported': "Не импортировано ни одной записи",
        'records_imported': "{imported_count} записей успешно импортировано",
        'openpyxl_not_installed': "Функция экспорта Excel не работает. Пожалуйста, выполните команду 'pip install openpyxl'.",
        
        # ============================================
        # FLASH MESSAGES - ERROR MESSAGES
        # ============================================
        'error_occurred': "Произошла ошибка: {error}",
        'import_error': "Ошибка импорта: {error}",
        'import_error_with_details': "Ошибка импорта: {errors}",
        'import_error_joined': "Ошибка при импорте: {errors}",
        'export_error': "Ошибка экспорта: {error}",
        'export_grades_error': "Произошла ошибка при экспорте: {error}",
        'excel_import_not_working': "Функция импорта Excel не работает: {error}",
        'template_file_creation_error': "Ошибка при создании файла шаблона: {error}",
        'template_file_download_error': "Ошибка при скачивании файла шаблона: {error}",
        'announcement_delete_error': "Произошла ошибка при удалении объявления: {error}",
        'announcements_delete_error': "Произошла ошибка при удалении объявлений: {error}",
        'invalid_file_format': "Недопустимый формат файла: {filename}. Допустимые форматы: PDF, DOC, DOCX, XLS, XLSX, PPT, PPTX, TXT, ZIP, RAR",
        'file_size_limit': "Размер файла не должен превышать {max_size} МБ",
    },
    'en': {
        # ============================================
        # SITE INFO
        # ============================================
        'site_name': 'TIQXMMI National Research University LMS',
        'site_name_short': 'TIQXMMI LMS',
        'site_tagline': 'Distance Learning Platform',
        'university_name': 'TIQXMMI National Research University',
        
        # ============================================
        # COMMON UI ELEMENTS
        # ============================================
        'dashboard': 'Dashboard',
        'logout': 'Logout',
        'login': 'Login',
        'register': 'Register',
        'settings': 'Settings',
        'search': 'Search',
        'save': 'Save',
        'cancel': 'Cancel',
        'delete': 'Delete',
        'edit': 'Edit',
        'create': 'Create',
        'back': 'Back',
        'next': 'Next',
        'previous': 'Previous',
        'submit': 'Submit',
        'close': 'Close',
        'yes': 'Yes',
        'no': 'No',
        'actions': 'Actions',
        'status': 'Status',
        'date': 'Date',
        'name': 'Name',
        'email': 'Email',
        'phone': 'Phone',
        'password': 'Password',
        'confirm_password': 'Confirm Password',
        'role': 'Role',
        'active': 'Active',
        'inactive': 'Inactive',
        
        # ============================================
        # ROLES
        # ============================================
        'admin': 'Administrator',
        'dean': 'Dean',
        'teacher': 'Teacher',
        'student': 'Student',
        
        # ============================================
        # DASHBOARD ELEMENTS
        # ============================================
        'welcome': 'Welcome',
        'good_morning': 'Good Morning',
        'good_afternoon': 'Good Afternoon',
        'good_evening': 'Good Evening',
        'today': 'Today',
        'total_users': 'Total Users',
        'total_students': 'Total Students',
        'total_teachers': 'Total Teachers',
        'total_faculties': 'Total Faculties',
        'total_groups': 'Total Groups',
        'total_subjects': 'Total Subjects',
        
        # ============================================
        # SUBJECTS
        # ============================================
        'subjects': 'Subjects',
        'subject': 'Subject',
        'subject_name': 'Subject Name',
        'subject_code': 'Subject Code',
        'credits': 'Credits',
        'semester': 'Semester',
        'lessons': 'Lessons',
        'lesson': 'Lesson',
        'assignments': 'Assignments',
        'assignment': 'Assignment',
        'grades': 'Grades',
        'grade': 'Grade',
        
        # ============================================
        # USERS
        # ============================================
        'users': 'Users',
        'user': 'User',
        'full_name': 'Full Name',
        'student_id': 'Student ID',
        'group': 'Group',
        'groups': 'Groups',
        'faculty': 'Faculty',
        'faculties': 'Faculties',
        
        # ============================================
        # MESSAGES
        # ============================================
        'messages': 'Messages',
        'announcements': 'Announcements',
        'schedule': 'Schedule',
        
        # ============================================
        # GRADE SCALE
        # ============================================
        'grade_scale': 'Grade Scale',
        'excellent': 'Excellent',
        'good': 'Good',
        'satisfactory': 'Satisfactory',
        'poor': 'Poor',
        'failed': 'Failed',
        
        # ============================================
        # FLASH MESSAGES - AUTH
        # ============================================
        'no_access_permission': "You do not have permission to access this page",
        'account_blocked': 'Your account has been blocked',
        'invalid_login_credentials': "Invalid login, email, student ID or password",
        'logout_success': "You have successfully logged out",
        'registration_closed': "Registration is closed. Please contact the administrator.",
        'login_required_input': "Please enter login, student ID or email",
        'user_not_found_by_credentials': "User with this login, student ID or email not found",
        'function_only_for_teachers_students': "This function is only available for teachers and students",
        'passport_number_required_input': "Please enter passport series and number",
        'user_not_found': "User not found",
        'incorrect_passport_number': "Incorrect passport series and number",
        'passport_not_available': "User does not have passport series and number",
        'token_not_found_or_used': "Token not found or already used",
        'token_expired': "Token has expired. Please submit a new request",
        'passwords_do_not_match': "Passwords do not match",
        'password_min_length': "Password must contain at least 6 characters",
        'password_min_length_8': "Password must contain at least 8 characters",
        'password_changed_success': "Password successfully changed! Now log in to the system",
        'password_changed_success_short': "Password successfully changed",
        'password_reset_success': "Password successfully reset! Password: {new_password}",
        'user_password_reset': "{user.full_name}'s password has been reset. New password: {new_password}",
        'student_password_reset': "{student.full_name}'s password has been reset. New password: {new_password}",
        'no_permission_for_role': "You do not have access to this role",
        
        # ============================================
        # FLASH MESSAGES - VALIDATION ERRORS
        # ============================================
        'login_required_field': "Login is a required field",
        'login_required_for_staff': "Login is a required field (for staff)",
        'login_already_exists': "This login already exists",
        'login_already_exists_other_user': "This login already exists for another user",
        'student_id_required': "Student ID is a required field",
        'student_id_required_for_students': "Student ID is a required field (for students)",
        'student_id_already_exists': "This student ID already exists",
        'student_id_already_exists_other_student': "This student ID already exists for another student",
        'email_already_exists': "This email already exists",
        'email_already_exists_other_user': "This email already exists for another user",
        'email_already_exists_other_student': "This email already exists for another student",
        'email_used_by_another_user': "This email is already used by another user",
        'passport_required': "Passport series and number are required",
        'passport_not_available_for_user': "This user does not have passport series and number",
        'passport_not_available_for_student': "This student does not have passport series and number",
        'birthdate_invalid_format': "Invalid birthdate format (yyyy-mm-dd)",
        'date_invalid_format': "Invalid date format",
        'date_invalid_format_use_calendar': "Invalid date format. Please select from the calendar.",
        'date_required': "Date is required",
        'date_required_select': "Date is required.",
        'all_required_fields': "All required fields must be filled",
        'all_fields_required': "All fields must be filled",
        'at_least_one_role_required': "At least one role must be selected",
        'code_already_exists': "This code already exists",
        'invalid_request': "Invalid request",
        'title_and_text_required': "Title and text are required",
        'message_cannot_be_empty': "Message cannot be empty",
        'new_passwords_do_not_match': "New passwords do not match",
        
        # ============================================
        # FLASH MESSAGES - PERMISSION ERRORS
        # ============================================
        'no_permission_for_operation': "You do not have permission for this operation",
        'no_permission_for_action': "You do not have permission for this action",
        'no_permission_to_edit_group': "You do not have permission to edit this group",
        'no_permission_to_delete_group': "You do not have permission to delete this group",
        'no_permission_to_view_group': "You do not have permission to view this group",
        'no_permission_to_add_students_to_group': "You do not have permission to add students to this group",
        'no_permission_to_edit_student': "You do not have permission to edit this student",
        'no_permission_to_create_announcement': "You do not have permission to create an announcement",
        'no_permission_to_edit_announcement': "You do not have permission to edit this announcement",
        'no_permission_to_delete_announcement': "You do not have permission to delete this announcement",
        'no_permission_to_delete_all_announcements': "You do not have permission to delete all announcements",
        'no_permission_to_chat': "You do not have permission to chat with this user",
        'no_permission_to_view_course': "You do not have permission to view this course",
        'no_permission_to_edit_course': "You do not have permission to edit this course",
        'no_permission_to_delete_course': "You do not have permission to delete this course",
        'no_permission_to_view_lesson': "You do not have permission to view this lesson",
        'no_permission_to_edit_lesson': "You do not have permission to edit this lesson",
        'no_permission_to_delete_lesson': "You do not have permission to delete this lesson",
        'no_permission_to_view_assignment': "You do not have permission to view this assignment",
        'no_permission_to_edit_assignment': "You do not have permission to edit this assignment",
        'no_permission_to_delete_assignment': "You do not have permission to delete this assignment",
        'no_permission_to_view_submission': "You do not have permission to view this submission",
        'no_permission_to_edit_submission': "You do not have permission to edit this submission",
        'no_permission_to_delete_submission': "You do not have permission to delete this submission",
        'no_permission_to_view_grade': "You do not have permission to view this grade",
        'no_permission_to_edit_grade': "You do not have permission to edit this grade",
        'no_permission_to_delete_grade': "You do not have permission to delete this grade",
        
        # ============================================
        # FLASH MESSAGES - USER OPERATIONS
        # ============================================
        'user_created_with_role': "{role} successfully created",
        'user_status_changed': "User {status}",
        'user_updated': "User successfully updated",
        'user_deleted': "User deleted",
        'staff_created': "Staff member {full_name} successfully created",
        'staff_updated': "Staff member {full_name} information updated",
        'profile_updated': "Information successfully updated",
        'profile_role_changed': "Profile changed to {role_name} role. Now you are working as {role_name}.",
        'cannot_block_yourself': "You cannot block yourself",
        'cannot_delete_yourself': "You cannot delete yourself",
        'user_not_staff': "This is a student, not a staff member",
        'user_not_student': "This user is not a student",
        
        # ============================================
        # FLASH MESSAGES - FACULTY OPERATIONS
        # ============================================
        'faculty_created': "Faculty successfully created",
        'faculty_updated': "Faculty successfully updated",
        'faculty_deleted': "Faculty «{faculty_name}» and all its directions, groups deleted",
        'faculty_not_found': "Faculty not found",
        'faculty_required': "Faculty selection is required",
        'faculty_selected_not_found': "Selected faculty not found",
        'faculty_incorrect_selection': "Faculty incorrectly selected",
        'faculty_not_assigned': "Faculty not assigned to you",
        'faculty_required_for_dean': "If dean role is selected, faculty selection is required",
        'faculty_has_students': "Faculty has {students_count} students. To delete faculty, first transfer or delete students",
        'responsible_deans_changed': "Responsible deans successfully changed",
        
        # ============================================
        # FLASH MESSAGES - DIRECTION OPERATIONS
        # ============================================
        'direction_created': "Direction successfully created",
        'direction_updated': "Direction updated",
        'direction_deleted': "Direction deleted",
        'direction_required': "Direction selection is required",
        'direction_incorrect_selection': "Incorrect direction selected",
        'direction_name_and_code_required': "Direction name and code are required",
        'direction_name_and_code_required_fill': "Direction name and code must be filled",
        'direction_already_exists': "Direction with this code, course, semester and education type already exists",
        'direction_code_already_exists': "Direction with this code already exists",
        'direction_has_groups_and_students': "Direction has {groups_count} groups and {total_students} students. Cannot delete",
        'direction_has_groups': "Direction has {groups_count} groups. First delete or transfer groups to another direction",
        'direction_no_groups': "Direction has no groups",
        'groups_assigned_to_direction': "Groups assigned to direction",
        'directions_and_groups_imported': "{d_count} directions and {g_count} groups imported",
        
        # ============================================
        # FLASH MESSAGES - GROUP OPERATIONS
        # ============================================
        'group_created': "Group successfully created",
        'group_updated': "Group updated",
        'group_deleted': "Group deleted",
        'group_name_required': "Group name is required",
        'group_already_exists': "Group with this name already exists in this direction, course and semester",
        'group_course_and_semester_required': "Course and semester are required",
        'group_all_fields_required': "Course, semester and education type are required",
        'group_has_students': "Group has students. Cannot delete",
        'group_has_students_transfer_first': "Group has students. First transfer students to another group",
        'no_groups_for_year_education_type': "No groups for year {year} with education type {education_type}",
        'no_active_groups_for_semester': "No active groups found for semester {semester}",
        
        # ============================================
        # FLASH MESSAGES - STUDENT OPERATIONS
        # ============================================
        'student_created': "{full_name} successfully created",
        'student_updated': "{full_name} information updated",
        'student_deleted': "{student_name} deleted",
        'student_status_changed': "Student {full_name} {status}",
        'students_added_to_group': "{added_count} students added to group",
        'student_removed_from_group': "{full_name} removed from group",
        'students_removed_from_group': "{count} students removed from group",
        'no_students_selected': "No students selected",
        'no_students_added': "No students added. Selected students may already be assigned to another group",
        'no_students_removed': "No students removed from group",
        
        # ============================================
        # FLASH MESSAGES - SUBJECT OPERATIONS
        # ============================================
        'subject_name_required': "Subject name is a required field",
        'subject_created': "Subject successfully created",
        'subject_updated': "Subject updated",
        'subject_deleted': "Subject deleted",
        'subject_not_in_curriculum': "Subject is no longer used in any curriculum. You can delete it.",
        'subject_removed_from_all_curriculums': "«{subject_name}» removed from all curriculums ({deleted} entries). Now you can delete the subject.",
        'subject_not_found': "Selected subject not found",
        
        # ============================================
        # FLASH MESSAGES - CURRICULUM OPERATIONS
        # ============================================
        'subjects_added_to_curriculum': "{added} subjects added to curriculum",
        'curriculum_updated': "Curriculum for semester {semester} updated",
        'subject_removed_from_curriculum': "Subject removed from curriculum",
        'curriculum_import_success': "Success! {imported} new added, {updated} updated.",
        'curriculum_import_subjects_created': "{subjects_created} new subjects created.",
        'curriculum_import_errors': "{errors_count} errors occurred.",
        'subject_already_in_semester': "Subject {subject_name} already exists in this semester",
        'subject_replaced': "Subject replaced with {new_subject_name}",
        'subject_and_semester_required': "Subject and semester selection is required",
        'new_subject_not_selected': "New subject not selected",
        'semester_not_selected': "Semester not selected",
        'semester_teachers_saved': "Teachers for semester {semester} successfully saved",
        
        # ============================================
        # FLASH MESSAGES - SCHEDULE OPERATIONS
        # ============================================
        'schedule_added': "Added to class schedule",
        'schedule_updated': "Class schedule updated",
        'schedule_deleted': "Schedule deleted",
        'schedules_imported': "{count} schedules successfully imported",
        'teacher_not_assigned_to_lesson_type': "This teacher is not assigned a lesson type for this group and subject",
        'lesson_already_exists_at_time': "At this time ({start_time}) the group already has a lesson: {existing_subject}",
        
        # ============================================
        # FLASH MESSAGES - GRADING SYSTEM
        # ============================================
        'grade_letter_already_exists': "This grade letter already exists",
        'min_score_greater_than_max': "Minimum score cannot be greater than maximum",
        'grade_added': "Grade successfully added",
        'grade_updated': "Grade updated",
        'grade_deleted': "Grade deleted",
        'grade_required': "Grade is required",
        'grade_assigned': "Grade successfully assigned",
        'grading_system_reset': "Grading system reset to default state",
        
        # ============================================
        # FLASH MESSAGES - COURSE/LESSON/ASSIGNMENT
        # ============================================
        'course_name_required': "Course name is required",
        'course_created': "Course successfully created",
        'course_updated': "Course updated",
        'course_deleted': "Course deleted",
        'lesson_name_required': "Lesson name is required",
        'lesson_created': "Lesson successfully created",
        'lesson_created_for_groups': "Lesson successfully added for {created_count} groups",
        'lesson_updated': "Lesson updated",
        'lesson_deleted': "Lesson deleted",
        'lesson_cannot_delete_has_assignments': "Cannot delete this topic! The following assignments are linked to it: {assignments_list}",
        'assignment_name_required': "Assignment name is required",
        'assignment_created': "Assignment successfully created",
        'assignment_created_for_groups': "Assignment successfully created for {created_count} groups",
        'assignment_updated': "Assignment updated",
        'assignment_deleted': "Assignment deleted",
        'submission_text_required': "Submission text is required",
        'submission_submitted': "Submission successfully submitted",
        'submission_resubmitted': "Your submission resubmitted ({resubmission_count}/3)",
        'submission_updated': "Submission updated",
        'submission_deleted': "Submission deleted",
        'teacher_not_assigned_to_lesson_type_direction': "You are not assigned to the selected lesson type in this direction. You can only create lessons for lesson types assigned to you.",
        'teacher_not_assigned_to_new_lesson_type': "You are not assigned to lesson type '{lesson_type}' in this direction. You can only modify lesson types assigned to you.",
        'teacher_not_assigned_to_assignment_lesson_type': "You are not assigned to the selected lesson type in this direction.",
        'teacher_not_assigned_for_grading': "You are not assigned to lesson type '{lesson_type}' in this direction. You can only grade for lesson types assigned to you.",
        
        # ============================================
        # FLASH MESSAGES - ANNOUNCEMENTS
        # ============================================
        'announcement_created': "Announcement successfully created",
        'announcement_updated': "Announcement successfully updated",
        'announcement_deleted': "Announcement deleted",
        'all_announcements_deleted': "All {count} announcements deleted",
        
        # ============================================
        # FLASH MESSAGES - MESSAGING
        # ============================================
        'message_sent': "Message sent",
        
        # ============================================
        # FLASH MESSAGES - ACCOUNTING
        # ============================================
        'contract_not_found': "Contract information not found",
        'payment_info_updated': "Payment information updated",
        
        # ============================================
        # FLASH MESSAGES - IMPORT/EXPORT
        # ============================================
        'file_not_selected': "File not selected",
        'only_excel_files_allowed': "Only Excel files (.xlsx, .xls) are supported",
        'only_xlsx_or_xls_allowed': "Only .xlsx or .xls format files are accepted",
        'only_xlsx_files_allowed': "Only .xlsx format files can be uploaded",
        'no_changes_made': "No changes made",
        'no_students_imported': "No students imported",
        'students_imported': "{imported_count} students successfully imported",
        'no_subjects_imported': "No subjects imported",
        'subjects_imported': "{imported_count} subjects successfully imported",
        'subjects_updated': "{updated_count} subjects updated",
        'no_users_imported': "No users imported",
        'users_imported': "{imported_count} users successfully imported",
        'no_records_imported': "No records imported",
        'records_imported': "{imported_count} records successfully imported",
        'openpyxl_not_installed': "Excel export function is not working. Please run 'pip install openpyxl' command.",
        
        # ============================================
        # FLASH MESSAGES - ERROR MESSAGES
        # ============================================
        'error_occurred': "An error occurred: {error}",
        'import_error': "Import error: {error}",
        'import_error_with_details': "Import error: {errors}",
        'import_error_joined': "Error during import: {errors}",
        'export_error': "Export error: {error}",
        'export_grades_error': "An error occurred during export: {error}",
        'excel_import_not_working': "Excel import function is not working: {error}",
        'template_file_creation_error': "Error creating template file: {error}",
        'template_file_download_error': "Error downloading template file: {error}",
        'announcement_delete_error': "An error occurred while deleting announcement: {error}",
        'announcements_delete_error': "An error occurred while deleting announcements: {error}",
        'invalid_file_format': "Invalid file format: {filename}. Allowed formats: PDF, DOC, DOCX, XLS, XLSX, PPT, PPTX, TXT, ZIP, RAR",
        'file_size_limit': "File size must not exceed {max_size} MB",
    }
}


def get_translation(key, lang='uz', **kwargs):
    """
    Get translation for a key with optional variable substitution.
    
    Args:
        key: Translation key
        lang: Language code ('uz', 'ru', 'en')
        **kwargs: Variables to substitute in the translation (e.g., full_name="John", count=5)
    
    Returns:
        Translated string with variables substituted if provided
    
    Example:
        get_translation('students_added_to_group', 'uz', added_count=5)
        # Returns: "5 ta talaba guruhga qo'shildi"
    """
    translation = TRANSLATIONS.get(lang, {}).get(key, key)
    if kwargs:
        try:
            return translation.format(**kwargs)
        except (KeyError, ValueError):
            return translation
    return translation


def get_current_language():
    """Get current language from session or default"""
    from flask import session
    return session.get('language', 'uz')


def t(key, **kwargs):
    """
    Shorthand for get_translation using current session language.
    Use this in routes for flash messages.
    
    Example:
        from app.utils.translations import t
        flash(t('student_created', full_name=student.full_name), 'success')
    """
    return get_translation(key, get_current_language(), **kwargs)
