"""To'lov hisob-kitob yordamchi funksiyalari."""
from datetime import datetime, date
from app.models import DirectionContractAmount, StudentPayment
from app.utils.date_utils import get_tashkent_time


def _build_contract_by_year(student, payments_for_student):
    """Talaba uchun kontrakt jadvali: har bir o'quv yili uchun summa (maxsus + yo'nalish)."""
    custom_dict = {}
    for p in payments_for_student:
        if p.contract_amount and float(p.contract_amount) > 0 and p.academic_year:
            ay = (p.academic_year or '').strip()
            if not ay:
                continue
            ps, pe = getattr(p, 'period_start', None), getattr(p, 'period_end', None)
            entry = {
                'amount': float(p.contract_amount),
                'payment_id': p.id,
                'period_start': ps,
                'period_end': pe
            }
            if ay not in custom_dict:
                custom_dict[ay] = entry
            elif (ps and pe) and (not custom_dict[ay].get('period_start') or not custom_dict[ay].get('period_end')):
                custom_dict[ay] = entry
    latest_custom_year = max(custom_dict.keys()) if custom_dict else None

    contract_by_year = []
    if student.group and student.group.direction_id:
        g = student.group
        grp_et = (g.education_type or '').strip() or None
        base_year = g.enrollment_year or 0
        dca_list = DirectionContractAmount.query.filter(
            DirectionContractAmount.direction_id == g.direction_id,
            DirectionContractAmount.enrollment_year >= base_year
        ).all()
        for a in dca_list:
            a_et = (a.education_type or '').strip() or None
            if a_et is None or a_et == grp_et:
                ay_key = f"{a.enrollment_year}-{a.enrollment_year + 1}"
                if latest_custom_year and ay_key <= latest_custom_year:
                    continue
                period_display = '—'
                if a.period_start and a.period_end:
                    period_display = f"{a.period_start.strftime('%d.%m.%Y')} – {a.period_end.strftime('%d.%m.%Y')}"
                contract_by_year.append({
                    'academic_year': ay_key,
                    'amount': float(a.contract_amount),
                    'is_custom': False,
                    'period_display': period_display,
                    'paid_amount': 0
                })
    for ay in sorted(custom_dict.keys()):
        info = custom_dict[ay]
        pid = info.get('payment_id')
        ps, pe = info.get('period_start'), info.get('period_end')
        if pid and (not ps or not pe):
            pm = StudentPayment.query.get(pid)
            if pm:
                ps = ps or pm.period_start
                pe = pe or pm.period_end
        if not ps or not pe:
            try:
                parts = ay.replace(' ', '').split('-')
                if len(parts) >= 2:
                    y1 = int(parts[0])
                    y2 = int(parts[1]) if len(parts[1]) == 4 else y1 + 1
                    ps = ps or date(y1, 9, 1)
                    pe = pe or date(y2, 6, 30)
            except (ValueError, IndexError):
                pass
        contract_by_year.append({
            'academic_year': ay,
            'amount': info['amount'],
            'is_custom': True,
            'period_start': ps,
            'period_end': pe,
            'paid_amount': 0,
            'payment_id': info['payment_id']
        })
    contract_by_year.sort(key=lambda x: x['academic_year'])
    return contract_by_year


def _allocate_payments_to_rows(contract_by_year, payments_sorted):
    """To'lovlarni ketma-ket qatorlarga taqsimlash."""
    remaining_per_row = [float(row['amount']) for row in contract_by_year]
    row_idx = 0
    for p in payments_sorted:
        amt = float(p.paid_amount or 0)
        if amt <= 0:
            continue
        while amt > 0 and row_idx < len(contract_by_year):
            need = remaining_per_row[row_idx]
            if need <= 0:
                row_idx += 1
                continue
            take = min(amt, need)
            contract_by_year[row_idx]['paid_amount'] = contract_by_year[row_idx].get('paid_amount', 0) + take
            remaining_per_row[row_idx] = need - take
            amt -= take
            if remaining_per_row[row_idx] <= 0:
                row_idx += 1


def get_current_year_payment_info(student):
    """Talaba uchun joriy o'quv yili to'lov ma'lumotlari (maxsus kontrakt, ortiqcha to'lov bilan)."""
    payments = StudentPayment.query.filter_by(student_id=student.id).all() if student else []
    contract_by_year = _build_contract_by_year(student, payments)
    if not contract_by_year:
        # Joriy o'quv yilini aniqlab bo'lmaydi (kontrakt jadvali yo'q)
        return None

    payments_sorted = sorted(payments, key=lambda p: (p.created_at or p.updated_at or datetime.min))
    _allocate_payments_to_rows(contract_by_year, payments_sorted)

    now_tz = get_tashkent_time()
    if now_tz.month >= 9:
        current_ay = f"{now_tz.year}-{now_tz.year + 1}"
    else:
        current_ay = f"{now_tz.year - 1}-{now_tz.year}"

    current_year_row = next((r for r in contract_by_year if r.get('academic_year') == current_ay), None)
    if not current_year_row:
        return None
    contract = float(current_year_row['amount'])
    paid = float(current_year_row.get('paid_amount', 0))
    remaining = max(0, contract - paid)
    overpayment = max(0, paid - contract)
    paid_display = min(paid, contract)
    percentage = min(100, (paid_display / contract * 100)) if contract > 0 else 0
    return {
        'contract': contract,
        'paid': paid,
        'paid_display': paid_display,
        'remaining': remaining,
        'percentage': percentage,
        'overpayment': overpayment,
        'current_academic_year': current_ay
    }


def get_effective_contract_for_student(student, payments_for_student):
    """Talaba uchun umumiy kontrakt: maxsus (StudentPayment) + yo'nalish (DirectionContractAmount).
    Maxsus kontrakt bo'lgan o'quv yillari uchun yo'nalish summasini o'rniga maxsus qo'llanadi."""
    custom_dict = {}
    for p in payments_for_student:
        if p.contract_amount and float(p.contract_amount) > 0 and p.academic_year:
            ay = (p.academic_year or '').strip()
            if not ay:
                continue
            if ay not in custom_dict:
                custom_dict[ay] = float(p.contract_amount)
    latest_custom_year = max(custom_dict.keys()) if custom_dict else None

    total = 0
    if student and student.group and student.group.direction_id:
        g = student.group
        grp_et = (g.education_type or '').strip() or None
        base_year = g.enrollment_year or 0
        for a in DirectionContractAmount.query.filter(
            DirectionContractAmount.direction_id == g.direction_id,
            DirectionContractAmount.enrollment_year >= base_year
        ).all():
            a_et = (a.education_type or '').strip() or None
            if a_et is None or a_et == grp_et:
                ay_key = f"{a.enrollment_year}-{a.enrollment_year + 1}"
                if latest_custom_year and ay_key <= latest_custom_year:
                    continue
                total += float(a.contract_amount)
    total += sum(custom_dict.values())
    return total
