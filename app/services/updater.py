"""
Avtomatik yangilash – markazdan zip yuklab, o'rnatish, qayta ishga tushirish.
"""
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

logger = logging.getLogger(__name__)

RESTART_FLAG = 'RESTART_REQUIRED'

# Yangilanmaydigan papka va fayllar (ma'lumot saqlanadi)
PROTECTED = {'instance', 'uploads', 'logs', '.well-known', '.env', 'eduspace.db', '*.db'}


def get_project_root():
    """Loyiha ildiz papkasi."""
    return Path(__file__).resolve().parent.parent.parent


def get_central_url():
    try:
        from flask import current_app
        return (current_app.config.get('CENTRAL_API_URL') or '').strip().rstrip('/')
    except Exception:
        return (os.environ.get('CENTRAL_API_URL') or '').strip().rstrip('/')


def _get_local_version_json():
    """Markazda: instance/central/releases/version.json dan so'nggi versiya (Flask instance_path yoki loyiha ildizi)."""
    v_file = None
    try:
        from flask import current_app
        v_file = Path(current_app.instance_path) / 'central' / 'releases' / 'version.json'
    except Exception:
        pass
    if not v_file or not v_file.is_file():
        root = get_project_root()
        v_file = root / 'instance' / 'central' / 'releases' / 'version.json'
    if not v_file.is_file():
        return None
    try:
        data = json.loads(v_file.read_text(encoding='utf-8'))
        if data and data.get('version'):
            return data
    except Exception as e:
        logger.debug("Mahalliy version.json o'qishda xato: %s", e)
    return None


def get_latest_version_info():
    """
    So'nggi versiya ma'lumotini olish.
    Markazda: avval mahalliy instance/central/releases/version.json.
    Institutda: markaz API (URL to'g'ri /central-api bilan).
    Qaytaradi: {'version': ..., 'download_url': ...} yoki xato bo'lsa {'error': 'xabar'}.
    """
    v = _get_local_version_json()
    if v:
        return v
    data, err = fetch_version()
    if data and data.get('version'):
        return data
    if isinstance(err, dict):
        return {'error_key': err.get('key', 'update_version_failed'), 'error_url': err.get('url'), 'error_code': err.get('code')}
    return {'error_key': 'update_version_failed', 'error_url': None}


def fetch_version():
    """
    Markazdan versiya ma'lumotini olish (API).
    Qaytaradi: (data_dict yoki None, error_dict yoki None). error_dict = {'key': '...', 'url': '...', 'code': ...}
    """
    import requests
    base = get_central_url()
    if not base:
        return None, {'key': 'update_center_not_configured', 'url': None}
    if '/central-api' in base:
        url = f'{base.rstrip("/")}/api/version'
    else:
        url = f'{base.rstrip("/")}/central-api/api/version'
    try:
        headers = {'Cache-Control': 'no-cache', 'Pragma': 'no-cache'}
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code == 200:
            return r.json(), None
        return None, {'key': 'update_center_bad_response', 'url': url, 'code': r.status_code}
    except requests.exceptions.Timeout:
        return None, {'key': 'update_center_timeout', 'url': url}
    except requests.exceptions.ConnectionError:
        return None, {'key': 'update_center_connection_error', 'url': url}
    except Exception as e:
        logger.warning("Versiya olishda xato: %s", e)
        return None, {'key': 'update_version_failed', 'url': None}


def get_current_version():
    """Joriy versiya (VERSION faylidan)."""
    vf = get_project_root() / 'VERSION'
    if vf.exists():
        return vf.read_text(encoding='utf-8').strip()
    return '0.0.0'


def is_central_newer(central_version: str, current_version: str) -> bool:
    """Markaz versiyasi joriy versiyadan yangiroqmi? YYYYMMDDHHMMSS (14 raqam) qator solishtirish."""
    cv = (central_version or '').strip()
    cur = (current_version or '').strip()
    if not cv:
        return False
    if not cur or cur == '0.0.0':
        return True
    if len(cv) == 14 and cv.isdigit() and len(cur) == 14 and cur.isdigit():
        return cv > cur
    return cv != cur


def _build_download_url(version: str) -> str:
    """download_url bo'sh bo'lsa, CENTRAL_API_URL va version dan qurish (/central-api/releases/)."""
    base = get_central_url()
    if not base:
        return ''
    base = base.rstrip('/')
    if '/central-api' in base:
        return f'{base}/releases/ELMS-{version}.zip'
    return f'{base}/central-api/releases/ELMS-{version}.zip'


def run_update(force=False):
    """
    Yangilanishni bajarish: zip yuklash, chiqarish, o'rnatish.
    Markaz versiyasi joriy versiyadan yangi bo'lsagina yangilaydi (force=True bo'lsa har doim).
    """
    root = get_project_root()
    v = get_latest_version_info()
    if not v or v.get('error_key') or v.get('error') or not v.get('version'):
        logger.warning("Yangilanish ma'lumoti olinmadi: %s", v.get('error_key') or v.get('error') if isinstance(v, dict) else 'version.json yoki markaz API')
        return False

    version = v.get('version', '').strip()
    current = get_current_version()
    if not force and not is_central_newer(version, current):
        logger.info("Markaz versiyasi yangi emas (markaz=%s, joriy=%s), yangilash o'tkazilmaydi", version, current)
        return False

    url = (v.get('download_url') or '').strip()
    # Proxy/CDN download_url ni bo'sh qaytarsa, version dan URL qurish
    # Haqiqiy release version: YYYYMMDDHHMMSS (14 raqam)
    if not url and version and len(version) == 14 and version.isdigit():
        url = _build_download_url(version)
        logger.info("download_url bo'sh – qurilgan: %s", url)
    if not url:
        logger.warning(
            "Yangilanish URL topilmadi. Markazdan bo'sh download_url qaytdi "
            "(proxy/CDN muammosi bo'lishi mumkin). CENTRAL_API_URL=%s",
            get_central_url()
        )
        return False

    try:
        import requests
        logger.info("Yangilanish yuklanmoqda: %s", version)
        r = requests.get(url, timeout=300, stream=True)
        r.raise_for_status()

        with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as tmp:
            for chunk in r.iter_content(chunk_size=65536):
                tmp.write(chunk)
            zip_path = tmp.name

        try:
            import zipfile
            with tempfile.TemporaryDirectory() as tmpdir:
                td = Path(tmpdir)
                with zipfile.ZipFile(zip_path, 'r') as zf:
                    zf.extractall(td)

                # Birinchi papka – odatda loyiha nomi
                extracted = list(td.iterdir())
                src_dir = extracted[0] if len(extracted) == 1 and extracted[0].is_dir() else td

                # Faqat kod va template'larni almashtirish
                for item in src_dir.iterdir():
                    name = item.name
                    if name.startswith('.') or name in PROTECTED:
                        continue
                    if name in ('instance', 'uploads', 'logs', '.well-known', '.env'):
                        continue
                    if name.endswith('.db'):
                        continue
                    dest = root / name
                    if item.is_dir():
                        if dest.exists():
                            shutil.rmtree(dest, ignore_errors=True)
                        shutil.copytree(item, dest, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
                    else:
                        shutil.copy2(item, dest)

                # VERSION faylini yozish
                (root / 'VERSION').write_text(version, encoding='utf-8')

            logger.info("Kod yangilandi: %s", version)
        finally:
            try:
                os.unlink(zip_path)
            except Exception:
                pass

        # pip install -r requirements.txt
        req_file = root / 'requirements.txt'
        if req_file.exists():
            try:
                subprocess.run(
                    [sys.executable, '-m', 'pip', 'install', '-r', str(req_file), '-q'],
                    cwd=str(root),
                    timeout=120,
                    check=False,
                )
            except Exception as e:
                logger.warning("pip install xato: %s", e)

        # Qayta ishga tushirish belgisi
        (root / RESTART_FLAG).write_text(version, encoding='utf-8')
        logger.info("Yangilanish tugadi. Qayta ishga tushirish kerak.")
        return True

    except Exception as e:
        logger.exception("Yangilanishda xato: %s", e)
        return False


def check_restart_flag():
    """RESTART_REQUIRED bor-yo'qligini tekshirish."""
    return (get_project_root() / RESTART_FLAG).exists()


def schedule_restart():
    """5 soniyadan keyin qayta ishga tushirish (os._exit)."""
    def _exit():
        time.sleep(5)
        os._exit(0)

    threading.Thread(target=_exit, daemon=True).start()
