"""
Markaziy serverni tekshirish – institut bloklangan yoki yo'q, ruxsatlar.
"""
import json
import logging
import threading
import time
from pathlib import Path

logger = logging.getLogger(__name__)

# Kesh – markazga har soatda yoki o'zgarishda yangilanadi
_status_cache = {}
_cache_lock = threading.Lock()
_cache_updated_at = 0
CACHE_TTL = 60  # soniya – bloklanish tekshiruvi har minutda


def get_central_url():
    """config dan markaziy URL olish."""
    try:
        from flask import current_app
        return (current_app.config.get('CENTRAL_API_URL') or '').strip()
    except Exception:
        import os
        return (os.environ.get('CENTRAL_API_URL') or '').strip()


def get_institution_id():
    """config dan institut ID olish."""
    try:
        from flask import current_app
        return str(current_app.config.get('INSTITUTION_ID') or '')
    except Exception:
        import os
        return str(os.environ.get('INSTITUTION_ID') or '')


def is_central_enabled():
    """Markaziy boshqaruv yoqilgan yoki yo'q."""
    url = get_central_url()
    return bool(url and url.startswith(('http://', 'https://')))


def fetch_status():
    """Markazdan institut holatini olish (HTTP so'rov)."""
    import requests
    url = get_central_url().rstrip('/')
    inst_id = get_institution_id()
    if not url or not inst_id:
        return {'blocked': False, 'permissions': [], 'block_reason': None}

    try:
        r = requests.get(
            f'{url}/api/institution/{inst_id}/status',
            timeout=10,
            headers={'Accept': 'application/json'}
        )
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        logger.warning("Markazdan status olishda xato: %s", e)

    return {'blocked': False, 'permissions': [], 'block_reason': None}


def get_status(use_cache=True):
    """
    Institut holati – bloklangan yoki yo'q, ruxsatlar.
    Kesh orqali – markazga har CACHE_TTL soniyada so'rov.
    """
    if not is_central_enabled():
        return {'blocked': False, 'permissions': [], 'block_reason': None}

    global _status_cache, _cache_updated_at
    now = time.time()

    with _cache_lock:
        if use_cache and _status_cache and (now - _cache_updated_at) < CACHE_TTL:
            return _status_cache.copy()

        status = fetch_status()
        _status_cache = status.copy()
        _status_cache.setdefault('permissions', [])
        _status_cache.setdefault('block_reason', None)
        _cache_updated_at = now
        return _status_cache.copy()


def invalidate_cache():
    """Keshni tozalash – markazda o'zgarish bo'lganda chaqiriladi."""
    global _status_cache, _cache_updated_at
    with _cache_lock:
        _status_cache = {}
        _cache_updated_at = 0


def is_blocked():
    """Institut bloklanganmi."""
    return bool(get_status().get('blocked', False))


def has_permission(permission):
    """Berilgan ruxsat bormi."""
    perms = get_status().get('permissions', [])
    if not perms:
        return True
    return permission in perms or 'admin' in perms


# Blueprint nomidan ruxsat nomiga moslash
BLUEPRINT_PERMISSION_MAP = {
    'main': 'main',
    'auth': 'main',
    'admin': 'admin',
    'dean': 'admin',
    'courses': 'courses',
    'accounting': 'accounting',
    'face_api': 'face_log',
    'attendance': 'attendance',
    'api': 'main',
}


def check_blueprint_permission(blueprint_name):
    """Blueprint nomi bo'yicha ruxsat tekshirish."""
    if blueprint_name in (None, 'main', 'auth'):
        return True
    perm = BLUEPRINT_PERMISSION_MAP.get(blueprint_name, 'main')
    return has_permission(perm)
