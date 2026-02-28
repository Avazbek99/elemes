# Smart Dashboard — qayta reja

## 1. Maqsad va qamrov

**Smart Dashboard** — xodimlar davomatini real vaqtda ko‘rsatadigan monitoring ekrani (TV/taqsimot rejimi va admin rejimi).

- **TV rejim** (`/smart-dashboard?tv=1`): login siz, ekranda doimiy ko‘rinish.
- **Admin rejim** (`/smart-dashboard`): superadmin kirganda, iframe orqali yoki to‘liq sahifa.

**Asosiy vazifalar:**
- Vaqtida kelganlar / kech qolganlar (ertalab 09:00 gacha/keyin).
- Vaqtida ketganlar / vaqtidan oldin ketganlar (kechki 17:00 dan keyin/oldin).
- (Ixtiyoriy) Markazda “Hozir kirayotganlar” (live stream) — yangi kirishlar onlayn.
- Sana, vaqt, ish vaqti sozlamalari, tizim holati (Jonli/Uzildi).

---

## 2. Hozirgi holat

### 2.1 Tuzilma
- **Bitta HTML**: `app/templates/attendance/smart_dashboard.html`.
- **TV rejim**: `{% if tv_mode %}` — to‘liq sahifa, Tailwind CDN, 2 ustunli layout.
- **Admin rejim**: `{% else %}` — base.html + iframe ichida TV URL.

### 2.2 Layout (TV)
- **Header**: logo, “Davomat monitoringi”, bugungi sana, Kirish 09:00 / Chiqish 17:00–18:00, status (Jonli/Uzildi), soat.
- **Asosiy qism**: 2 ta panel (chap/o‘ng), 50/50.
  - **Chap**: ertalab — “Vaqtida kelganlar”, kechqurun — “Vaqtida ketganlar”.
  - **O‘ng**: ertalab — “Kech qolganlar”, kechqurun — “Vaqtidan oldin ketganlar”.
- Kartochkalar: grid (2–4 ustun), har biri — rasm, ism, identifikator, “Kirdi: HH:mm:ss”, status (Keldi/Kechikdi/Yo‘q/Kirish rad etildi).

### 2.3 Ma’lumot
- **API**: `GET /face-api/dashboard-cards?tv=1&limit=2000`.
- **Javob**: `kirish_on_time`, `kirish_late`, `chiqish_on_time`, `chiqish_late`, `date`.
- **Yangilanish**: 2 soniyada bir `fetch` (polling), WebSocket yo‘q.

### 2.4 Kamchiliklari
- Faqat 2 ustun; “Hozir kirayotganlar” (live stream) yo‘q.
- Dizayn KPI namunasiga to‘liq moslashtirilmagan.
- Real vaqtda yangi kirishni darhol ko‘rsatish cheklangan (faqat polling).
- Analytics (kunlik umumiy, grafiklar) yo‘q yoki past darajada.

---

## 3. Taklif etiladigan tuzilma

### 3.1 Umumiy layout (3 ustun)

| Chap panel           | Markaz panel              | O‘ng panel                |
|----------------------|---------------------------|---------------------------|
| **Ertalab**: Vaqtida kelganlar | **Hozir kirayotganlar (Live)** | **Ertalab**: Kech qolganlar |
| **Kechqurun**: Vaqtida ketganlar | Yangi kirishlar ro‘yxati      | **Kechqurun**: Vaqtidan oldin ketganlar |

- **Chap va o‘ng**: mavjud API dan `kirish_on_time`, `kirish_late`, `chiqish_on_time`, `chiqish_late` — vaqt rejimiga qarab sarlavhalar o‘zgaradi.
- **Markaz**: “Hozir kirayotganlar” — so‘nggi N ta kirish (yoki WebSocket orqali real vaqtda), yangi qo‘shilganlar qisqa vaqt yorqinlashadi (pulse).

### 3.2 Sarlavhalar va vaqt rejimi
- **Vaqt rejimi**: Toshkent soati bo‘yicha:
  - **Ertalab**: 00:00 – 11:59 → “Vaqtida kelganlar” / “Kech qolganlar”.
  - **Kechqurun**: 12:00 – 23:59 → “Vaqtida ketganlar” / “Vaqtidan oldin ketganlar”.
- Sarlavhalar va subtitle’lar hozirgi mantiqda qoladi, faqat markaz panel qo‘shiladi.

### 3.3 Kartochka dizayni (KPI uslubida)
- Oq fon, yumaloq burchaklar, yengil soya.
- Rasm: chapda, aylana yoki to‘rtburchak (KPI namunasiga mos).
- Matn: ism (qalin), identifikator (kichik), bo‘lim/kafedra (ixtiyoriy), vaqt, status badge (yashil/to‘q sariq/qizil).
- “Kirish rad etildi”: alohida rang/ramka yoki overlay.
- Yorug‘lik effekti: yangi qo‘shilgan kartochka 2–3 soniya yashil/oq glow.

### 3.4 Header
- Logo (chap), sarlavha “Davomat monitoringi”.
- Sana (bugun), ish vaqti: Kirish 09:00 | Chiqish 17:00–18:00.
- Status: Jonli (yashil nuqta) / Uzildi (qizil).
- Soat (HH:mm:ss), soniyada yangilanadi.

---

## 4. Real vaqt va yangilanish

### 4.1 Polling (hozirgi)
- `dashboard-cards` har 2 soniyada chaqirilsin.
- Chap/o‘ng panellar shu API dan yangilansin.
- Markaz panel: yoki shu javobdan “so‘nggi kirishlar” ajratilsin, yoki alohida endpoint (masalan `GET /face-api/dashboard-cards?live_only=1&limit=50`).

### 4.2 WebSocket (ixtiyoriy, keyingi bosqich)
- Face log qayd etilganda server `attendance:refresh` yoki `attendance:entry` yuborsa, brauzer darhol `fetchCards()` qiladi yoki yangi kartochkani markazga qo‘shadi.
- Socket.IO namespace: `/attendance` (agar loyihada bor bo‘lsa).

### 4.3 Markaz panel ma’lumoti
- **Variant A**: `dashboard-cards` dan barcha bugungi kirishlarni vaqt bo‘yicha kamayish tartibida olib, eng so‘nggi 30–50 tasini “Hozir kirayotganlar” sifatida ko‘rsatish.
- **Variant B**: Alohida API `GET /face-api/live-entries?limit=50` — faqat IN (kirish) event’lar, `event_time` bo‘yicha so‘nggi N ta.

---

## 5. Dizayn va stil (KPI ga yaqinlashtirish)

- **Fon**: och kulrang (#f5f6f8 yoki #f9fafb).
- **Panellar**: oq kartalar, border-radius 12px, yengil soya.
- **Chap panel**: yashil chegarа (border-left 4px #22c55e).
- **O‘ng panel**: to‘q sariq/to‘q qizil chegarа (#f97316).
- **Markaz panel**: ko‘k yoki boshqa neytral chegarа (live e’tibor uchun).
- **Kartochkalar**: padding 8–10px, gap 6–8px, scrollbar ingichka, bo‘sh joyda “Xabar yo‘q” matni (dashed border).
- **Typography**: sarlavhalar 1.1–1.25rem, matn 0.8–0.9rem, vaqt monospace.

---

## 6. Texnik o‘zgarishlar

### 6.1 Backend (minimal)
- `dashboard_cards` javobiga ixtiyoriy `live_entries` (so‘nggi 50 ta kirish) qo‘shish — markaz panel uchun.
- Yoki `GET /face-api/live-entries?limit=50` — faqat bugungi IN event’lar, tartiblangan.

### 6.2 Frontend (TV rejim)
- Layout: 3 ustun (grid yoki flex). Chap 1fr, markaz 1fr, o‘ng 1fr (yoki markaz biroz kengroq).
- Markazda alohida konteyner: “Hozir kirayotganlar (Live)” + ro‘yxat (scroll), yangi elementga `.card-glow` va 3 s keyin o‘chirish.
- Barcha kartochkalar uchun bitta `renderCard(card, options)` — options: { side: 'left'|'center'|'right', isNew: boolean }.
- Sana/soat/status — mavjudidek, faqat kodni modulli qilish (funksiyalar).

### 6.3 Admin rejim
- Hozirgi kabi iframe yoki to‘g‘ridan-to‘g‘ri bir xil template (tv_mode=false da 3 ustunli ko‘rinishni ham ko‘rsatish mumkin).

---

## 7. Amalga oshirish bosqichlari

| Bosqich | Vazifa | Bajarilishi |
|--------|--------|-------------|
| **1** | Reja hujjati (ushbu fayl) va layout rejasi tasdiqlash | ✅ |
| **2** | TV layout: 3 ustun (chap + markaz + o‘ng), sarlavhalar va bo‘sh joylar | ✅ |
| **3** | API: `live_entries` yoki `live-entries` endpoint — markaz panel uchun | Keyingi |
| **4** | Kartochka komponenti birlashtirish (chap/o‘ng/markaz), KPI ranglar va border | Keyingi |
| **5** | Markaz panel: “Hozir kirayotganlar” ro‘yxati, yangi kirishda glow | Keyingi |
| **6** | Polling 2 s, yangi kartochkalarni “new” deb belgilash, animatsiya | Keyingi |
| **7** | (Ixtiyoriy) WebSocket `attendance:refresh` — darhol `fetchCards()` | Keyingi |
| **8** | Analytics blok (pastda): jami keldi/ketdi/kechikdi/erta — ixtiyoriy | Keyingi |

---

## 8. Fayllar va manbalar

- **Template**: `app/templates/attendance/smart_dashboard.html`
- **API**: `app/face_api/routes.py` — `dashboard_cards()`, `_dashboard_card_from_log()`, `_parse_raw_extra()`
- **Route**: `app/routes/main.py` — `smart_dashboard()`
- **KPI hisobot (dizayn eslatma)**: `app/templates/attendance/kpi_report.html`

Reja tasdiqlangandan keyin bosqichma-bosqich layout (3 ustun), keyin API, keyin kartochka va markaz panel, oxirida analytics qo‘shish mumkin.
