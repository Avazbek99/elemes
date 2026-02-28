# EduSpace - Masofaviy Ta'lim Platformasi (Python/Flask)

Zamonaviy masofaviy ta'lim platformasi Python Flask yordamida yaratilgan.

## 🎯 Xususiyatlar

### Foydalanuvchi rollari:
- **Administrator** - Tizimni to'liq boshqarish, foydalanuvchilar va ruxsatlarni sozlash
- **O'qituvchi** - Kurslar yaratish, topshiriqlar berish, baholar qo'yish
- **Talaba** - Kurslarda qatnashish, topshiriqlar bajarish, baholarni ko'rish
- **Dekanat** - Hisobotlar, statistika va fakultet boshqaruvi

### Asosiy funksiyalar:
- 📚 Kurslar boshqaruvi
- 📝 Topshiriqlar va vazifalar
- 📊 Baholar va statistika
- 📅 Dars jadvali
- 💬 Xabarlar tizimi
- 📢 E'lonlar
- 👥 Foydalanuvchilar boshqaruvi (Admin)
- 🔐 Ruxsatlar tizimi (Admin)
- 📈 Hisobotlar (Admin, Dekanat)

## 🚀 O'rnatish va ishga tushirish

```bash
# 1. Virtual muhit yaratish
python -m venv venv

# 2. Virtual muhitni faollashtirish
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

# 3. Kutubxonalarni o'rnatish
pip install -r requirements.txt

# 4. Dasturni ishga tushirish
python run.py
```

Brauzerda oching: **http://localhost:5000**

## 🛠️ Texnologiyalar

- **Python 3.10+** - Asosiy dasturlash tili
- **Flask 3.0** - Web framework
- **Flask-SQLAlchemy** - ORM (ma'lumotlar bazasi)
- **Flask-Login** - Autentifikatsiya
- **SQLite** - Ma'lumotlar bazasi
- **Tailwind CSS** - Styling (CDN)
- **Jinja2** - HTML shablonlar

## 📁 Loyiha strukturasi

```
├── app/
│   ├── __init__.py          # Flask ilovasi
│   ├── models.py            # Ma'lumotlar bazasi modellari
│   ├── routes/
│   │   ├── auth.py          # Autentifikatsiya
│   │   ├── main.py          # Asosiy sahifalar
│   │   ├── courses.py       # Kurslar
│   │   ├── admin.py         # Admin panel
│   │   └── api.py           # API endpointlar
│   └── templates/           # HTML shablonlar
│       ├── base.html
│       ├── dashboard.html
│       ├── auth/
│       ├── courses/
│       └── admin/
├── config.py                # Sozlamalar
├── requirements.txt         # Python kutubxonalar
├── run.py                   # Ishga tushirish fayli
└── README.md
```

## 📝 Litsenziya

MIT License
