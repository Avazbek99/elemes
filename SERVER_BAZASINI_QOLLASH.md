# Serverdan olgan bazani joriy loyihada ishlatish

Serverdan `ELMS1.3.zip` (yoki baza fayli) ni yuklab oldingiz. Uni kompyuteringizdagi loyihada ishlatish uchun:

## 1. ZIP ni oching

- `d:\Ish\Platforma\clon\ELMS1.3.zip` faylini o‘ng tugma → "Extract All" / "Barchasini chiqarish" yoki ikkita marta bosing.
- Chiqarilgan papkada `instance` papkasini qiding; ichida **eduspace.db** bo‘ladi (serverdagi baza).

Agar ZIP da butun loyiha bo‘lsa, yo‘l odatda shunday bo‘ladi:
- `ELMS1.3\instance\eduspace.db`
yoki
- `instance\eduspace.db`

## 2. Joriy bazani zaxiraga oling (ixtiyoriy)

Agar hozirgi kompyuterdagi baza kerak bo‘lsa, avval nusxalab qo‘ying:

```
d:\Ish\Platforma\ELMS1.3\instance\eduspace.db
→ nusxasini masalan: eduspace.db.local-backup nomi bilan instance papkasida saqlang
```

## 3. Server bazasini joriy loyihaga qo‘ying

ZIP dan chiqarilgan **eduspace.db** faylini **qattiq nusxalang** (Copy–Paste yoki cmd):

- **Qayerdan:** ZIP dan ochilgan papkadagi `instance\eduspace.db`
- **Qayerga:** `d:\Ish\Platforma\ELMS1.3\instance\eduspace.db`

Ya’ni mavjud `d:\Ish\Platforma\ELMS1.3\instance\eduspace.db` faylini serverdagi baza bilan **almashtiring** (avval 2-qadamda nusxa olgan bo‘lsangiz, xavfsiz).

**Cmd orqali (ZIP dan chiqarilgan papka masalan `d:\Ish\Platforma\clon\ELMS1.3_extracted` bo‘lsa):**

```cmd
copy /Y "d:\Ish\Platforma\clon\ELMS1.3_extracted\ELMS1.3\instance\eduspace.db" "d:\Ish\Platforma\ELMS1.3\instance\eduspace.db"
```

Yo‘l ZIP ichidagi strukturaga qarab o‘zgarishi mumkin; asosi — **serverdagi eduspace.db** ni **ELMS1.3\instance\eduspace.db** ustiga qo‘yish.

## 4. Loyihani ishga tushiring

Bazani almashtirgach, loyihani odatdagidek ishga tushiring:

```cmd
cd /d d:\Ish\Platforma\ELMS1.3
python run.py
```

Endi brauzerda serverdagi ma’lumotlar (foydalanuvchilar, fanlar, talabalar va h.k.) ko‘rinadi.

---

**Eslatma:** Agar ZIP da faqat **eduspace.db** bo‘lsa (instance papkasiz), uni to‘g‘ridan-to‘g‘ri `d:\Ish\Platforma\ELMS1.3\instance\eduspace.db` ga nusxalang.
