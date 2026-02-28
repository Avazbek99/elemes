"""
Markazda avtomatik release: hozirgi kodni zip qilish, version.json yangilash, institutlarga xabar.
"""
import json
import logging
import zipfile
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# Zipga kirmaydigan papka/fayllar (ma'lumot saqlanadi)
EXCLUDE = {'instance', 'uploads', 'logs', '.well-known', '.env', '__pycache__', '.git'}
EXCLUDE_SUFFIXES = ('.db', '.pyc', '.log')


def _project_root():
    return Path(__file__).resolve().parent.parent.parent


def _releases_dir(app):
    return Path(app.instance_path) / 'central' / 'releases'


def _should_include(name: str, path: Path) -> bool:
    if name.startswith('.'):
        return False
    if name in EXCLUDE:
        return False
    if path.is_file() and any(name.endswith(s) for s in EXCLUDE_SUFFIXES):
        return False
    return True


def build_zip(app) -> tuple[str, str]:
    """
    Loyiha ildizini zip qiladi, instance/central/releases/ ga saqlaydi.
    Qaytaradi: (version, zip_filename)
    """
    root = _project_root()
    rel_dir = _releases_dir(app)
    rel_dir.mkdir(parents=True, exist_ok=True)

    version = datetime.utcnow().strftime('%Y%m%d%H%M%S')
    zip_name = f'ELMS-{version}.zip'
    zip_path = rel_dir / zip_name

    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for item in root.iterdir():
            name = item.name
            if not _should_include(name, item):
                continue
            if item.is_file():
                zf.write(item, name)
            else:
                for f in item.rglob('*'):
                    if f.is_file() and _should_include(f.name, f):
                        arcname = f.relative_to(root)
                        try:
                            zf.write(f, str(arcname))
                        except Exception as e:
                            logger.warning("Zipga qo'shilmadi %s: %s", f, e)

    logger.info("Release yaratildi: %s", zip_name)
    return version, zip_name


def update_version_json(app, version: str, zip_filename: str):
    """version.json ni yangilaydi – download_url markazning public URL i bilan."""
    base_url = (app.config.get('CENTRAL_PUBLIC_URL') or '').strip().rstrip('/')
    if not base_url:
        raise ValueError("CENTRAL_PUBLIC_URL sozlanishi kerak (markazda avtomatik nashr uchun)")
    download_url = f"{base_url}/central-api/releases/{zip_filename}"

    rel_dir = _releases_dir(app)
    v_file = rel_dir / 'version.json'
    data = {
        'version': version,
        'released_at': datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
        'download_url': download_url,
        'checksum': ''
    }
    v_file.parent.mkdir(parents=True, exist_ok=True)
    v_file.write_text(json.dumps(data, indent=2), encoding='utf-8')
    logger.info("version.json yangilandi: %s", download_url)


def trigger_update_broadcast(app):
    """Markazda trigger-update ni chaqiradi – barcha SSE ulangan institutlar xabar oladi."""
    import requests
    url = 'http://127.0.0.1/central-api/api/trigger-update'
    try:
        r = requests.post(url, timeout=10)
        if r.status_code == 200:
            logger.info("Institutlarga yangilanish xabari yuborildi")
        else:
            logger.warning("trigger-update javob: %s %s", r.status_code, r.text)
    except Exception as e:
        logger.warning("trigger-update chaqirishda xato: %s", e)


def build_and_publish(app):
    """
    Zip yaratadi, version.json yangilaydi, institutlarga trigger-update yuboradi.
    Faqat markaz serverida, app context ichida chaqiriladi.
    """
    try:
        version, zip_name = build_zip(app)
        update_version_json(app, version, zip_name)
        trigger_update_broadcast(app)
        return True
    except Exception as e:
        logger.exception("Build va publish xato: %s", e)
        return False
