"""
Zoom Server-to-Server OAuth integratsiyasi.
Dars jadvali qo'shilganda avtomatik Zoom meeting yaratish uchun.
2024-yildan JWT eskirgan, Server-to-Server OAuth ishlatiladi.
"""
import base64
import logging
from datetime import datetime
from typing import Optional

import requests

logger = logging.getLogger(__name__)

ZOOM_TOKEN_URL = "https://zoom.us/oauth/token"
ZOOM_API_BASE = "https://api.zoom.us/v2"
ZOOM_SCOPES = "meeting:write:admin"  # Meeting yaratish uchun


def get_access_token(account_id: str, client_id: str, client_secret: str) -> Optional[str]:
    """
    Zoom Server-to-Server OAuth orqali access token olish.
    Token 1 soat amal qiladi.
    """
    try:
        credentials = f"{client_id}:{client_secret}"
        encoded = base64.b64encode(credentials.encode()).decode()
        response = requests.post(
            ZOOM_TOKEN_URL,
            params={"grant_type": "account_credentials", "account_id": account_id},
            headers={
                "Authorization": f"Basic {encoded}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
        return data.get("access_token")
    except Exception as e:
        logger.exception("Zoom access token olishda xato: %s", e)
        return None


def create_meeting(
    access_token: str,
    topic: str,
    start_time: str,
    duration_minutes: int = 90,
    timezone: str = "Asia/Tashkent",
    password: Optional[str] = None,
) -> Optional[dict]:
    """
    Zoom meeting yaratish.
    
    Args:
        access_token: Zoom OAuth access token
        topic: Dars mavzusi
        start_time: ISO 8601 formatida (masalan: "2026-02-11T09:00:00")
        duration_minutes: Davomiylik (daqiqalar)
        timezone: Vaqt zonası (default: Asia/Tashkent)
        password: Meeting paroli (ixtiyoriy)
    
    Returns:
        meeting_data: join_url, start_url, meeting_id va boshqalar
        None: xato bo'lsa
    """
    try:
        url = f"{ZOOM_API_BASE}/users/me/meetings"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        body = {
            "topic": topic[:200] if topic else "Dars",
            "type": 2,  # Scheduled meeting
            "start_time": start_time,
            "duration": min(duration_minutes, 300),  # Max 300 daqiqa
            "timezone": timezone,
        }
        if password:
            body["password"] = str(password)[:10]
        response = requests.post(url, headers=headers, json=body, timeout=15)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.exception("Zoom meeting yaratishda xato: %s", e)
        return None


def create_schedule_meeting(
    subject_name: str,
    group_name: str,
    lesson_type: str,
    date_code: int,
    start_time: str,
    config: dict,
) -> Optional[str]:
    """
    Dars jadvali uchun Zoom meeting yaratish va join_url qaytarish.
    
    Args:
        subject_name: Fan nomi
        group_name: Guruh nomi
        lesson_type: Dars turi (maruza, amaliyot, ...)
        date_code: YYYYMMDD formatida sana
        start_time: HH:MM formatida vaqt
        config: {
            'ZOOM_ACCOUNT_ID': str,
            'ZOOM_CLIENT_ID': str,
            'ZOOM_CLIENT_SECRET': str,
            'ZOOM_DURATION_MINUTES': int (optional, default 90),
            'ZOOM_TIMEZONE': str (optional, default Asia/Tashkent),
        }
    
    Returns:
        join_url: Talaba va o'qituvchi uchun Zoom havola
        None: Zoom sozlanmagan yoki xato bo'lsa
    """
    account_id = config.get("ZOOM_ACCOUNT_ID") or config.get("zoom_account_id")
    client_id = config.get("ZOOM_CLIENT_ID") or config.get("zoom_client_id")
    client_secret = config.get("ZOOM_CLIENT_SECRET") or config.get("zoom_client_secret")

    if not all([account_id, client_id, client_secret]):
        logger.debug("Zoom sozlamalari to'liq emas, meeting yaratilmaydi")
        return None

    token = get_access_token(account_id, client_id, client_secret)
    if not token:
        return None

    # date_code (YYYYMMDD) va start_time (HH:MM) dan ISO 8601 yasash
    try:
        date_str = str(date_code)
        year, month, day = date_str[:4], date_str[4:6], date_str[6:8]
        start_iso = f"{year}-{month}-{day}T{start_time}:00"
    except (ValueError, IndexError):
        start_iso = datetime.now().strftime("%Y-%m-%dT%H:%M:00")

    topic = f"{subject_name} - {group_name}"
    if lesson_type:
        topic = f"{topic} ({lesson_type})"

    duration = config.get("ZOOM_DURATION_MINUTES") or config.get("zoom_duration_minutes") or 90
    timezone = config.get("ZOOM_TIMEZONE") or config.get("zoom_timezone") or "Asia/Tashkent"

    meeting = create_meeting(
        access_token=token,
        topic=topic,
        start_time=start_iso,
        duration_minutes=duration,
        timezone=timezone,
    )

    if meeting and meeting.get("join_url"):
        return meeting["join_url"]
    return None
