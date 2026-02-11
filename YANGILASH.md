# Tizimni serverda bazaga tegmasdan yangilash

Bazani (ma'lumotlarni) saqlab, faqat kodni yangilash uchun quyidagi tartibni bajaring.

## 1. Bazani zaxiraga oling

Yangilashdan **oldingin** baza faylini nusxalang:

```bash
# Loyiha ildizida (ELMS1.3)
cp instance/eduspace.db instance/eduspace.db.backup-$(date +%Y%m%d-%H%M%S)
```

Yoki `instance` papkasini butunlay:

```bash
cp -r instance instance.backup-$(date +%Y%m%d)
```

## 2. Yangi kodni oling

**Git ishlatilsa:**

```bash
git fetch origin
git pull origin main
```

Yoki yangi kodni boshqa usul bilan serverga nusxalang (FTP, rsync va h.k.).  
**Muhim:** `instance/eduspace.db` faylini **ustidan yozmaslik** kerak — agar pull/copy qilganda bu fayl yangi bo‘sh baza bilan almashtirilsa, 1-qadamda olingan zaxirani qayta qo‘ying.

## 3. Virtual muhit va kerakli paketlar

```bash
# Kerak bo‘lsa
python -m venv venv
source venv/bin/activate   # Linux/Mac
# yoki Windows: venv\Scripts\activate

pip install -r requirements.txt
```

## 4. Migratsiyalarni ishga tushiring (schema o‘zgarsa)

Yangi jadval yoki ustunlar qo‘shilgan bo‘lsa:

```bash
flask db upgrade
```

Bu `migrations/versions/` dagi yangi migratsiyalarni bazaga qo‘llaydi; mavjud ma'lumotlar odatda saqlanadi.

## 5. Ilovani qayta ishga tushiring

```bash
# Gunicorn/uWSGI ishlatilsa
sudo systemctl restart eduspace
# yoki
pkill -f "gunicorn.*run:app"
# keyin yana ishga tushiring

# Oddiy test uchun
python run.py
```

## Qisqa tartib (eslab qolish uchun)

1. `instance/eduspace.db` ni zaxiraga oling.  
2. Yangi kodni oling (baza faylini ustidan yozmaslik).  
3. `pip install -r requirements.txt`  
4. `flask db upgrade`  
5. Ilovani restart qiling.  

Shu tartibda serverda tizimni yangilasangiz, baza shikastlanmasdan qoladi.

---

## Serverda baza Git bilan almashtirilmasin

Agar serverda `git pull` qilganda `instance/eduspace.db` yangi (bo‘sh) fayl bilan ustidan yozilayotgan bo‘lsa, serverdagi loyiha papkasida mahalliy ravishda bazani ignore qiling:

```bash
# Serverda, loyiha ildizida
echo "instance/eduspace.db" >> .gitignore
```

Keyin `git pull` baza fayliga tegmaydi; baza faqat serverda qoladi va yangilanishlar unga ta’sir qilmaydi.
