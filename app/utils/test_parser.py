"""
Test savollarini matn formatidan parse qilish.
Format: savol\n=====\nvariant1\n=====\n#variant2 (to'g'ri)\n=====\n+++++\nkeyingi savol...
"""


def _clean_option_text(raw):
    """Javob matnidan ajratgich qoldiqlarini (=, ===, #) olib tashlash."""
    s = raw.strip()
    # Boshidagi =, ===, ===== kabi belgilarni olib tashlash
    while s and (s[0] in '= ' or s.startswith('=====') or s.startswith('===') or s.startswith('=')):
        if s.startswith('====='):
            s = s[5:].lstrip()
        elif s.startswith('==='):
            s = s[3:].lstrip()
        elif s.startswith('='):
            s = s[1:].lstrip()
        else:
            s = s.lstrip()
    # To'g'ri javob belgisi #
    correct = s.startswith('#')
    if correct:
        s = s[1:].strip()
    return s, correct


def parse_test_content(text):
    """
    Matn formatidagi testni parse qiladi.
    Qaytaradi: [{'question': str, 'options': [{'text': str, 'correct': bool}], ...}]
    """
    if not text or not text.strip():
        return []
    blocks = text.strip().split('+++++')
    questions = []
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        parts = [p.strip() for p in block.split('=====') if p.strip()]
        if len(parts) < 2:
            continue
        question_text = parts[0]
        options = []
        for opt in parts[1:]:
            opt, correct = _clean_option_text(opt)
            if opt:
                options.append({'text': opt, 'correct': correct})
        if options:
            questions.append({'question': question_text, 'options': options})
    return questions
