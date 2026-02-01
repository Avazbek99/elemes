# Loyiha tuzilmasi (umumlashtirilgan)

## Hozirgi tuzilma – bitta ildiz

Loyiha **bitta** ildizda: `d:\Ish\Platforma\ELMS1.3\`. Ichki `ELMS1.3` papkasi va takroriy `app` nusxalari o‘chirildi.

| Papka / fayl | Vazifasi |
|--------------|----------|
| **app/** | Ilova kodi: routes, models, templates, utils |
| **app/templates/auth/login.html** | Yagona login sahifasi |
| **migrations/** | Alembic migratsiyalari |
| **uploads/** | Yuklangan fayllar (Excel, video va h.k.) |
| **instance/** | Ma’lumotlar bazasi (eduspace.db) – Flask tomonidan yaratiladi |
| **config.py** | Sozlamalar |
| **run.py** | Ishga tushirish: `python run.py` |

## Ishga tushirish

```bash
cd d:\Ish\Platforma\ELMS1.3
python run.py
```

Brauzerda: http://127.0.0.1:5000

## Qilingan umumlashtirish

1. **ELMS1.3\app** ichidagi kod ildizdagi **app** ustiga nusxalandi (semestr filtri va boshqa o‘zgarishlar saqlandi).
2. **run.py**, **config.py**, **migrations** ildizga yozildi.
3. Ildizdagi ortiqcha **templates/** (faqat 2 ta fayl) o‘chirildi – barcha template’lar **app/templates/** da.
4. Ichki **ELMS1.3** papkasi o‘chirildi – endi bitta loyiha ildizi bor.

## Eslatma

- **instance/** va **uploads/** ildizda qoldi – ma’lumotlar saqlanadi.
- Barcha template o‘zgarishlari: **app/templates/** (masalan, **app/templates/auth/login.html**).
