"""
SSE client – markazga ulanish va real-time yangilanish xabarlarini qabul qilish.
Institutlarda versiya tekshiruvi va yangilanish faqat 00:00–06:00 da (server mahalliy vaqti).
"""
import json
import logging
import threading
import time
from datetime import datetime

logger = logging.getLogger(__name__)

_running = False
_thread = None
_version_thread = None
_VERSION_CHECK_INTERVAL = 600

# Institutlarda yangilanish faqat shu vaqt oralig'ida (mahalliy vaqt, 00:00–06:00)
UPDATE_WINDOW_START_HOUR = 0   # 00:00
UPDATE_WINDOW_END_HOUR = 6    # 06:00 (6 dan oldin, ya'ni 0–5 soat)


def get_central_url():
    try:
        from flask import current_app
        return (current_app.config.get('CENTRAL_API_URL') or '').strip().rstrip('/')
    except Exception:
        import os
        return (os.environ.get('CENTRAL_API_URL') or '').strip().rstrip('/')


def get_institution_id():
    try:
        from flask import current_app
        return str(current_app.config.get('INSTITUTION_ID') or '')
    except Exception:
        import os
        return str(os.environ.get('INSTITUTION_ID') or '')


def _has_local_version_json():
    """Markazda: instance/central/releases/version.json mavjudmi."""
    try:
        from app.services.updater import get_project_root
        return (get_project_root() / 'instance' / 'central' / 'releases' / 'version.json').is_file()
    except Exception:
        return False


def is_enabled(app=None):
    """Yoqilgan: CENTRAL_API_URL bor yoki markazda instance/central/releases/version.json mavjud."""
    has_local = _has_local_version_json()
    if app:
        url = (app.config.get('CENTRAL_API_URL') or '').strip()
        if url and url.startswith(('http://', 'https://')):
            return True
        if has_local:
            return True
        return False
    try:
        url = get_central_url()
        if url and url.startswith(('http://', 'https://')):
            return True
        if has_local:
            return True
    except Exception:
        pass
    return False


def _is_institute(app):
    """Institut rejimi: markazga ulanadi, lekin mahalliy version.json yo'q (yangilanish vaqt oynasiga bog'lanadi)."""
    if not is_enabled(app):
        return False
    return not _has_local_version_json()


def _is_update_window():
    """Mahalliy vaqt 00:00–06:00 oralig'idami (institutlarda yangilanish shu vaqtda)."""
    hour = datetime.now().hour
    return UPDATE_WINDOW_START_HOUR <= hour < UPDATE_WINDOW_END_HOUR


def _run_single_version_check(app):
    """Ishga tushganda bir marta: joriy (VERSION) va so'nggi (version.json yoki API) farq qilsa yangilash."""
    try:
        with app.app_context():
            if not is_enabled(app):
                return
            if _is_institute(app) and not _is_update_window():
                logger.debug("Institut: yangilanish vaqt oynasida emas (00:00–06:00), tekshiruv o'tkazilmaydi")
                return
            from app.services.updater import get_latest_version_info, get_current_version, is_central_newer, run_update, schedule_restart
            v = get_latest_version_info()
            if not v or v.get('error_key') or v.get('error') or not v.get('version'):
                return
            latest_ver = (v.get('version') or '').strip()
            current_ver = get_current_version()
            if is_central_newer(latest_ver, current_ver):
                logger.info("So'nggi versiya yangi (so'nggi=%s, joriy=%s), yangilash boshlandi", latest_ver, current_ver)
                try:
                    if run_update():
                        schedule_restart()
                except Exception as e:
                    logger.exception("Yangilashda xato: %s", e)
    except Exception as e:
        logger.warning("Versiya tekshiruvida xato: %s", e)


def _version_check_loop(app):
    """Har 10 daqiqada so'nggi versiyani tekshiradi; yangi bo'lsa yangilash. Institutda faqat 00:00–06:00."""
    global _running
    while _running:
        time.sleep(_VERSION_CHECK_INTERVAL)
        if not _running:
            break
        try:
            with app.app_context():
                if not is_enabled(app):
                    continue
                if _is_institute(app) and not _is_update_window():
                    continue
                from app.services.updater import get_latest_version_info, get_current_version, is_central_newer, run_update, schedule_restart
                v = get_latest_version_info()
                if not v or v.get('error_key') or v.get('error') or not v.get('version'):
                    continue
                central_ver = (v.get('version') or '').strip()
                current_ver = get_current_version()
                if is_central_newer(central_ver, current_ver):
                    logger.info("Davriy tekshiruv: so'nggi yangi (so'nggi=%s, joriy=%s), yangilash boshlandi", central_ver, current_ver)
                    try:
                        if run_update():
                            schedule_restart()
                    except Exception as e:
                        logger.exception("Davriy yangilashda xato: %s", e)
        except Exception as e:
            if _running:
                logger.warning("Versiya tekshiruvida xato: %s", e)


def _sse_loop(app):
    """SSE ulanish va xabarlarni qabul qilish."""
    global _running
    import requests
    with app.app_context():
        url = get_central_url().rstrip('/')
        inst_id = get_institution_id()
    stream_url = f'{url}/api/stream?institution_id={inst_id}'

    while _running:
        try:
            with app.app_context():
                if not url or not inst_id:
                    time.sleep(30)
                    continue
                r = requests.get(stream_url, stream=True, timeout=60)
                r.raise_for_status()
                for line in r.iter_lines(decode_unicode=True):
                    if not _running:
                        break
                    if line and line.startswith('data:'):
                        data_str = line[5:].strip()
                        if not data_str:
                            continue
                        try:
                            msg = json.loads(data_str)
                            evt = msg.get('type', '')
                            if evt == 'update':
                                logger.info("Yangilanish xabari qabul qilindi")
                                from app.services.central_client import invalidate_cache
                                invalidate_cache()
                                if _is_institute(app) and not _is_update_window():
                                    logger.info("Institut: yangilanish 00:00–06:00 da amalga oshiriladi (kunduzi o'tkazilmaydi)")
                                    continue
                                from app.services.updater import run_update, schedule_restart
                                try:
                                    if run_update():
                                        schedule_restart()
                                except Exception as e:
                                    logger.exception("Yangilanishda xato: %s", e)
                            elif evt == 'institution_updated':
                                from app.services.central_client import invalidate_cache
                                invalidate_cache()
                        except json.JSONDecodeError:
                            pass
        except Exception as e:
            if _running:
                logger.warning("SSE ulanishda xato (qayta urinadi): %s", e)
        if _running:
            time.sleep(5)


def start_sse_client(app):
    """SSE clientni boshlash: ishga tushganda darhol + har 10 daqiqada versiya tekshiruvi."""
    global _running, _thread, _version_thread
    if not is_enabled(app):
        return
    if _thread and _thread.is_alive():
        return

    _running = True
    _thread = threading.Thread(target=lambda: _sse_loop(app), daemon=True)
    _thread.start()
    _version_thread = threading.Thread(target=lambda: _version_check_loop(app), daemon=True)
    _version_thread.start()
    # Ishga tushganda darhol so'nggi versiyani tekshirish (markaz: version.json, institut: API)
    threading.Thread(target=lambda: _run_single_version_check(app), daemon=True).start()
    logger.info("SSE client yoqildi (ishga tushganda + har 10 min versiya tekshiruvi)")


def stop_sse_client():
    """SSE clientni to'xtatish."""
    global _running
    _running = False
