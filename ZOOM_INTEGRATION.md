# Zoom integratsiyasi – ELMS platformasi

## Zoom savollariga javoblar

### 1. Platforma tavsifi

**Savol:** Qaysi texnologiyadan foydalanayotganingiz (backend tili)?

**Javob:** 
- **Backend:** Python (Flask 3.0)
- **Ma'lumotlar bazasi:** SQLite / PostgreSQL (SQLAlchemy)
- **Frontend:** Jinja2 templates, vanilla JavaScript

### 2. Foydalanuvchi kirish tizimi

Har bir foydalanuvchi (admin, o'qituvchi, talaba, dekan, buxgalteriya) o'z **login** va **parol** bilan tizimga kiradi. Flask-Login orqali autentifikatsiya amalga oshiriladi.

### 3. Dars jadvali va Zoom meeting

**Talab:** Dars jadvali qo'shilganda, shu vaqtda Zoom'da dars (uchrashuv) avtomatik tashkil etilishi kerak.

**Implementatsiya:**
- Admin yoki Dekan dars jadvaliga qo'shganda (create_schedule), agar "Onlayn havola" bo'sh qoldirilsa, backend avtomatik Zoom meeting yaratadi
- Zoom API orqali olingan `join_url` dars yozuvidagi `link` maydoniga saqlanadi
- Talabalar va o'qituvchilar jadvaldagi link orqali Zoom'ga qo'shiladi

### 4. Autentifikatsiya usuli

**Server-to-Server OAuth** ishlatiladi (2024-yildan JWT eskirgan).

- Zoom Marketplace'da **Server-to-Server OAuth** ilovasi yaratiladi
- Kerakli ma'lumotlar: `Account ID`, `Client ID`, `Client Secret`
- Token 1 soat amal qiladi, har API chaqiruvida kerak bo'lsa yangilanadi

---

## Sozlash bo'yicha qo'llanma

### 1. Zoom Marketplace'da ilova yaratish

1. [Zoom Marketplace](https://marketplace.zoom.us/) ga kiring
2. **Develop** → **Build App** → **Server-to-Server OAuth** tanlang
3. Ilovani yarating va quyidagilarni oling:
   - **Account ID**
   - **Client ID**
   - **Client Secret**
4. **Scopes** bo'limida `meeting:write:admin` (yoki `meeting:write`) ruxsatini qo'shing
5. Ilovani **Activate** qiling

### 2. Platformada muhit o'zgaruvchilari

`.env` yoki server muhitida quyidagilarni o'rnating:

```env
ZOOM_ACCOUNT_ID=xxxxxxxxxxxxxxxx
ZOOM_CLIENT_ID=xxxxxxxxxxxxxxxxxxxxxxxx
ZOOM_CLIENT_SECRET=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# Ixtiyoriy (default qiymatlar)
ZOOM_DURATION_MINUTES=90
ZOOM_TIMEZONE=Asia/Tashkent
```

### 3. Lokal sinov

PowerShell'da:

```powershell
$env:ZOOM_ACCOUNT_ID="sizning_account_id"
$env:ZOOM_CLIENT_ID="sizning_client_id"
$env:ZOOM_CLIENT_SECRET="sizning_client_secret"
python run.py
```

Dars jadvaliga qo'shganda, "Onlayn havola" bo'sh qoldiring – Zoom link avtomatik yaratiladi.

---

## API va kod

### Zoom API

- **Token:** `POST https://zoom.us/oauth/token`  
  `grant_type=account_credentials`, `account_id=...`
- **Meeting yaratish:** `POST https://api.zoom.us/v2/users/me/meetings`
- **Javob:** `join_url`, `start_url`, `meeting_id` va hokazo

### Loyihadagi fayllar

| Fayl | Vazifa |
|------|--------|
| `app/services/zoom_service.py` | Token olish, meeting yaratish |
| `config.py` | ZOOM_* sozlamalari |
| `app/routes/admin.py` | Admin create_schedule da Zoom chaqiruv |
| `app/routes/dean.py` | Dekan create_schedule da Zoom chaqiruv |

---

## Muhim eslatmalar

1. **userId:** Hozir `users/me` ishlatiladi – meetinglar sizning Zoom hisobingizda yaratiladi. O'qituvchilar nomidan alohida meeting yaratish uchun ularning Zoom hisoblariga OAuth flow orqali ulanish kerak (kelajakda qo'shish mumkin).
2. **Import:** Excel orqali import qilinganda Zoom avtomatik yaratilmaydi – faqat qo'lda qo'shilganda ishlaydi.
3. **Xavfsizlik:** `ZOOM_CLIENT_SECRET` ni hech qachon git'ga yubormang. `.env` va `.gitignore` dan foydalaning.

---

## Foydali manbalar

- [Zoom Meeting API – Meeting yaratish](https://developers.zoom.us/docs/api/rest/reference/zoom-api/methods/#operation/meetingCreate)
- [Server-to-Server OAuth integratsiyasi](https://developers.zoom.us/docs/internal-apps/create/)
- [Zoom Server-to-Server OAuth Token (GitHub)](https://github.com/zoom/server-to-server-oauth-token)
