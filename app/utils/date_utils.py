from datetime import datetime, timedelta, date

def _parse_date(s: str):
    """Parse date from string, tries Y-m-d and d.m.Y formats. Returns date or None."""
    if not s or not isinstance(s, str):
        return None
    s = s.strip()
    for fmt in ('%Y-%m-%d', '%d.%m.%Y', '%d/%m/%Y'):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def get_tashkent_time():
    """Toshkent vaqtini qaytaradi (UTC+5)"""
    return datetime.utcnow() + timedelta(hours=5)
