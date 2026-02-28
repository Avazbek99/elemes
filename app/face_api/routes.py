"""
Hikvision face API – qurilmalardan log qabul qilish va superadmin uchun ko‘rsatish.
Qotishni oldini olish: loglar navbatga qo‘yiladi, har 3 soniyada bitta DB ga yoziladi.
"""
import json
import logging
import queue
import threading
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path

# Qurilma odatda mahalliy vaqt (Toshkent UTC+5) yuboradi; DB da UTC saqlaymiz, sahifada +5 qo‘shib ko‘rsatamiz
TASHKENT_UTC_OFFSET_HOURS = 5


def _device_time_to_utc(dt):
    """Qurilma yuborgan vaqt (naive, Toshkent mahalliy) ni UTC ga o‘giradi. Sahifada to‘g‘ri vaqt chiqishi uchun."""
    if dt is None:
        return None
    if getattr(dt, 'tzinfo', None) is not None:
        return dt
    return dt - timedelta(hours=TASHKENT_UTC_OFFSET_HOURS)


def _raw_time_has_timezone(raw_str):
    """Matnda vaqt timezone bilan yuborilganmi (+05:00, Z) – bunday bo'lsa parse_event_time allaqachon UTC qaytaradi."""
    if not raw_str or not isinstance(raw_str, str):
        return False
    s = raw_str.strip()
    return ('T' in s or 't' in s) and ('+' in s or 'Z' in s)

from flask import request, jsonify, current_app, send_file, abort
from sqlalchemy import or_, and_

from app import db
from app.models import FaceLog, User

logger = logging.getLogger(__name__)

# Har 3 soniyada 1 ta xodim logini qabul qilish (qotishni oldini olish)
FACE_LOG_QUEUE = queue.Queue()
FACE_LOG_INTERVAL_SEC = 3
_face_log_worker_started = False
_face_log_worker_lock = threading.Lock()


def _start_face_log_worker(app):
    """Navbatdan har 3 soniyada bitta logni DB ga yozadigan worker ni ishga tushirish."""
    global _face_log_worker_started
    with _face_log_worker_lock:
        if _face_log_worker_started:
            return
        _face_log_worker_started = True

    def _worker():
        while True:
            time.sleep(FACE_LOG_INTERVAL_SEC)
            try:
                entry_dict = FACE_LOG_QUEUE.get_nowait()
            except queue.Empty:
                continue
            try:
                with app.app_context():
                    log = FaceLog(
                        device_employee_id=entry_dict.get('device_employee_id'),
                        person_name=entry_dict.get('person_name'),
                        event_time=entry_dict.get('event_time'),
                        direction=entry_dict.get('direction') or 'IN',
                        device_ip=entry_dict.get('device_ip') or '',
                        raw_data=entry_dict.get('raw_data'),
                        picture_path=entry_dict.get('picture_path'),
                    )
                    db.session.add(log)
                    db.session.commit()
                    logger.debug("Face log navbatdan yozildi: id=%s", log.id)
            except Exception as e:
                logger.exception("Face log navbatdan yozishda xato: %s", e)
            try:
                FACE_LOG_QUEUE.task_done()
            except Exception:
                pass

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    logger.info("Face log worker ishga tushdi (har %d soniyada 1 ta log)", FACE_LOG_INTERVAL_SEC)


def _enqueue_face_log(entry_dict):
    """Logni navbatga qo‘shish; so‘rov tez qaytadi, DB yozuvi keyinroq worker tomonidan."""
    try:
        FACE_LOG_QUEUE.put_nowait(entry_dict)
        if FACE_LOG_QUEUE.qsize() > 500:
            logger.warning("Face log navbati o‘smoqda: %d ta", FACE_LOG_QUEUE.qsize())
    except queue.Full:
        logger.error("Face log navbati to‘ldi, log qo‘shilmadi")

PERSON_NAME_KEYS = (
    'personName', 'person_name', 'PersonName', 'name', 'Name',
    'userName', 'user_name', 'UserName',  # Dahua
    'employeeName', 'faceName', 'face_name',
    'deviceName', 'device_name',  # fallback: qurilma nomi (e.g. "B kirish")
)
EVENT_TIME_KEYS = (
    'eventTime', 'event_time', 'EventTime', 'time', 'Time',
    'dateTime', 'date_time', 'DateTime',  # Hikvision top-level
    'timestamp', 'Timestamp', 'captureTime',
)


def get_client_ip():
    if request.headers.get('X-Forwarded-For'):
        return request.headers.get('X-Forwarded-For').split(',')[0].strip()
    if request.headers.get('X-Real-IP'):
        return request.headers.get('X-Real-IP').strip()
    return request.remote_addr or 'unknown'


def safe_extract(data, keys, default=None):
    if not isinstance(data, dict):
        return default
    for key in keys:
        if key in data and data[key] is not None:
            val = data[key]
            if isinstance(val, (str, int, float)):
                return str(val).strip() if val else default
            if isinstance(val, dict):
                return safe_extract(val, keys, default)
    return default


def parse_event_time(value):
    """Qurilma vaqtini parse qiladi. Qurilma Toshkent vaqtini yuboradi — o'zgartirmasdan (naive Toshkent) saqlaymiz."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    s = str(value).strip()
    if not s:
        return None
    try:
        from datetime import timezone
        iso = s.replace('Z', '+00:00')
        # Hikvision: dateTime "2026-02-25T09:04:14+05:00" — qurilma Toshkent vaqtini yuboradi, shu vaqtni saqlaymiz
        if '+05:00' in iso:
            part = iso.split('+05:00')[0].strip()
            if 'T' in part:
                return datetime.strptime(part[:19], '%Y-%m-%dT%H:%M:%S')
            return datetime.strptime(part[:19], '%Y-%m-%d %H:%M:%S')
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is not None:
            return dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    except (ValueError, TypeError):
        pass
    for part in (s[:19], s[:26].rstrip('Z'), s[:26]):
        for fmt in (
            '%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M:%S.%f',
            '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M:%S.%f',
            '%Y/%m/%d %H:%M:%S', '%d.%m.%Y %H:%M:%S',
        ):
            try:
                return datetime.strptime(part, fmt)
            except ValueError:
                continue
    return None


def extract_person_name(data):
    if isinstance(data, dict):
        name = safe_extract(data, PERSON_NAME_KEYS)
        if name:
            return name[:150]
        for v in data.values():
            n = extract_person_name(v)
            if n:
                return n[:150]
    elif isinstance(data, list):
        for item in data:
            n = extract_person_name(item)
            if n:
                return n[:150]
    return None


def extract_event_time(data):
    if isinstance(data, dict):
        val = safe_extract(data, EVENT_TIME_KEYS)
        if val:
            return parse_event_time(val)
        for v in data.values():
            t = extract_event_time(v)
            if t:
                return t
    elif isinstance(data, list):
        for item in data:
            t = extract_event_time(item)
            if t:
                return t
    return None


def extract_direction(data):
    """IN/OUT ni raw JSON dan ajratib olish."""
    keys = ('direction', 'Direction', 'eventType', 'event_type', 'inOut', 'in_out')
    if isinstance(data, dict):
        for k in keys:
            if k in data and data[k] is not None:
                v = str(data[k]).strip().upper()
                if v in ('IN', 'OUT', '1', '2'):
                    return 'IN' if v in ('IN', '1') else 'OUT'
                if 'in' in v.lower():
                    return 'IN'
                if 'out' in v.lower():
                    return 'OUT'
        for v in data.values():
            d = extract_direction(v) if isinstance(v, (dict, list)) else None
            if d:
                return d
    elif isinstance(data, list):
        for item in data:
            d = extract_direction(item) if isinstance(item, (dict, list)) else None
            if d:
                return d
    return 'IN'


def extract_device_employee_id(data):
    """Qurilmaga xodim kiritilganda berilgan xodim ID (employeeNoString, cardNo va h.k.) ni ajratib oladi."""
    keys = ('employeeNoString', 'employeeNo', 'employee_no', 'cardNo', 'card_no', 'userNo', 'user_no', 'userID', 'UserID', 'user_id')
    if isinstance(data, dict):
        for k in keys:
            if k in data and data[k] is not None:
                return str(data[k]).strip()[:50]
        for v in data.values():
            r = extract_device_employee_id(v)
            if r:
                return r
    elif isinstance(data, list):
        for item in data:
            r = extract_device_employee_id(item)
            if r:
                return r
    return None


def _do_log_incoming(raw_str, client_ip):
    """Faqat bitta qator yozish (I/O kam), fayl 5MB dan oshsa aylantirish."""
    try:
        logs_dir = Path(current_app.instance_path) / '..' / 'logs'
        logs_dir = logs_dir.resolve()
        logs_dir.mkdir(parents=True, exist_ok=True)
        log_path = logs_dir / 'face_incoming.log'
        full_log = current_app.config.get('LOG_FACE_INCOMING_FULL', False)
        max_size = 5 * 1024 * 1024
        if log_path.exists() and log_path.stat().st_size > max_size:
            backup1 = logs_dir / 'face_incoming.log.1'
            if backup1.exists():
                backup1.unlink()
            log_path.rename(backup1)
        with open(log_path, 'a', encoding='utf-8', errors='replace') as f:
            if full_log:
                f.write(f"--- {datetime.utcnow().isoformat()} | {client_ip} ---\n")
                f.write((raw_str or '')[:65536])
                if len(raw_str or '') > 65536:
                    f.write("\n... [truncated]\n")
                f.write("\n\n")
            else:
                f.write(f"{datetime.utcnow().isoformat()} | {client_ip} | {len(raw_str or '')} bytes\n")
    except Exception as e:
        logger.warning("face incoming.log yozishda xato: %s", e)


def log_incoming_raw(raw_str, client_ip):
    """Log yozishni background threadda bajarish – so'rov tez qaytadi, platforma qotmaydi."""
    try:
        app = current_app._get_current_object()
        s, ip = (raw_str or '')[:70000], str(client_ip or '')
        def _run():
            with app.app_context():
                _do_log_incoming(s, ip)
        threading.Thread(target=_run, daemon=True).start()
    except Exception as e:
        logger.warning("log_incoming_raw thread: %s", e)


def _write_last_request(client_ip):
    """So'nggi so'rov haqida (admin diagnostika). Background'da – so'rov bloklanmaydi."""
    try:
        app = current_app._get_current_object()
        ip = str(client_ip or '')
        def _run():
            with app.app_context():
                try:
                    inst = Path(current_app.instance_path)
                    inst.mkdir(parents=True, exist_ok=True)
                    path = inst / 'face_last_request.txt'
                    with open(path, 'w', encoding='utf-8') as f:
                        f.write(f"{datetime.utcnow().isoformat()}\n{ip}\n")
                except Exception:
                    pass
        threading.Thread(target=_run, daemon=True).start()
    except Exception:
        pass


def _extract_event_log_from_multipart(raw_str):
    """Hikvision multipart/form-data dan event_log qismidagi JSON ni ajratib oladi."""
    try:
        idx = raw_str.find('name="event_log"')
        if idx == -1:
            idx = raw_str.find("name='event_log'")
        if idx == -1:
            return None
        rest = raw_str[idx:]
        start = rest.find('{')
        if start == -1:
            return None
        depth = 0
        for i, c in enumerate(rest[start:], start):
            if c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0:
                    return rest[start:i + 1]
        return None
    except Exception:
        return None


def _get_boundary_from_content_type(content_type):
    """Content-Type dan boundary qiymatini ajratib oladi."""
    if not content_type:
        return None
    for part in content_type.split(';'):
        part = part.strip()
        if part.lower().startswith('boundary='):
            boundary = part[9:].strip().strip('"\'')
            return boundary
    return None


def _extract_dahua_multipart(raw_bytes, content_type):
    """
    Dahua multipart: birinchi qism text/plain (JSON), ikkinchi qism image/jpeg.
    Qaytaradi: (json_str, image_bytes) yoki (None, None).
    """
    boundary = _get_boundary_from_content_type(content_type)
    if not boundary or not raw_bytes:
        return None, None
    try:
        sep = b'\r\n--' + boundary.encode('ascii')
        parts = raw_bytes.split(sep)
        json_str, image_bytes = None, None
        for i, block in enumerate(parts):
            if i == 0 and (not block or block.strip() == b''):
                continue
            if block.strip() == b'--' or block.strip().endswith(b'--'):
                break
            head_sep = b'\r\n\r\n'
            if head_sep not in block:
                continue
            headers_b, body_b = block.split(head_sep, 1)
            headers = headers_b.decode('ascii', errors='ignore').lower()
            if ('content-type: text/plain' in headers or 'content-type:text/plain' in headers) and json_str is None:
                try:
                    raw_json = body_b.decode('utf-8', errors='replace').strip()
                    if raw_json.startswith('{'):
                        json_str = raw_json
                except Exception:
                    pass
            elif ('content-type: image/jpeg' in headers or 'content-type:image/jpeg' in headers) and image_bytes is None:
                body = body_b.rstrip(b'\r\n')
                if body.endswith(b'--'):
                    body = body[:-2].rstrip(b'\r\n')
                if len(body) > 100:
                    image_bytes = body
        return (json_str if json_str else None), (image_bytes if image_bytes else None)
    except Exception as e:
        logger.debug("Dahua multipart parse xato: %s", e)
        return None, None


def _receive_json(data_str):
    try:
        data = json.loads(data_str)
    except json.JSONDecodeError:
        return None, None, None, 'IN'
    return extract_person_name(data), extract_event_time(data), extract_device_employee_id(data), (extract_direction(data) or 'IN')


def _receive_xml(data_str):
    person_name, event_time, device_employee_id = None, None, None
    try:
        root = ET.fromstring(data_str)
        for elem in root.iter():
            tag = (elem.tag or '').lower()
            if 'personname' in tag or 'person_name' in tag or 'name' in tag:
                if elem.text and elem.text.strip():
                    person_name = elem.text.strip()[:150]
                    break
        for elem in root.iter():
            tag = (elem.tag or '').lower()
            if 'eventtime' in tag or 'time' in tag or 'timestamp' in tag:
                if elem.text and elem.text.strip():
                    event_time = parse_event_time(elem.text.strip())
                    break
    except ET.ParseError:
        pass
    return person_name, event_time, device_employee_id


def _receive_raw(data_str):
    stripped = data_str.strip()
    if stripped.startswith('{') or stripped.startswith('['):
        return _receive_json(data_str)
    if stripped.startswith('<?xml') or stripped.startswith('<'):
        return _receive_xml(data_str)
    return None, None, None


from app.face_api import face_api_bp


@face_api_bp.route('/ping', methods=['GET'])
@face_api_bp.route('/ping.php', methods=['GET'])
def ping():
    """Ulanish tekshiruvi – qurilma serverni ko'ra olishini tekshirish uchun."""
    return jsonify({'status': 'ok', 'service': 'face-api', 'message': 'Server is reachable'}), 200


@face_api_bp.route('/receive', methods=['POST'])
@face_api_bp.route('/receive.php', methods=['POST'])  # Hikvision ba'zi qurilmalar .php qo'shadi
def receive():
    """
    Hikvision qurilmalaridan yuz tanilash loglarini qabul qilish.
    Auth va CSRF talab qilinmaydi (qurilma POST qiladi).
    """
    client_ip = get_client_ip()
    raw_str = ''

    try:
        content_type = (request.content_type or '').lower()
        raw_bytes = None
        if 'multipart' in content_type:
            raw_bytes = request.get_data(as_text=False)
        if raw_bytes is not None:
            raw_str = raw_bytes.decode('utf-8', errors='replace')
        else:
            raw_str = request.get_data(as_text=True) or request.data.decode('utf-8', errors='replace')
        if not raw_str:
            raw_str = str(request.form) if request.form else '(empty body)'

        person_name, event_time, device_employee_id, direction = None, None, None, 'IN'
        picture_path = None
        parse_str = raw_str

        # Dahua multipart: birinchi qism JSON (UserName, UserID), ikkinchi qism rasm
        if raw_bytes and 'multipart' in content_type:
            dahua_json, dahua_image = _extract_dahua_multipart(raw_bytes, content_type)
            if dahua_json:
                log_incoming_raw(dahua_json + (f"\n[Dahua image: {len(dahua_image)} bytes]" if dahua_image else ""), client_ip)
                _write_last_request(client_ip)
                logger.info("Dahua log qabul qilindi: %s, uzunlik=%d", client_ip, len(dahua_json))
                res = _receive_json(dahua_json)
                person_name, event_time, device_employee_id = res[0], res[1], res[2]
                if len(res) > 3:
                    direction = res[3] or 'IN'
                if event_time is None:
                    event_time = datetime.utcnow()
                elif not _raw_time_has_timezone(dahua_json):
                    event_time = _device_time_to_utc(event_time)
                entry_dict = {
                    'device_employee_id': device_employee_id,
                    'person_name': person_name,
                    'event_time': event_time,
                    'direction': direction or 'IN',
                    'device_ip': client_ip,
                    'raw_data': dahua_json,
                    'picture_path': None,
                }
                _enqueue_face_log(entry_dict)
                try:
                    _start_face_log_worker(current_app._get_current_object())
                except Exception:
                    pass
                return jsonify({'status': 'success'}), 200

        log_incoming_raw(raw_str, client_ip)
        _write_last_request(client_ip)
        logger.info("Hikvision log qabul qilindi: %s, uzunlik=%d", client_ip, len(raw_str))

        if 'multipart' in content_type and raw_str:
            event_log_form = request.form.get('event_log') if request.form else None
            parse_str = (event_log_form if isinstance(event_log_form, str) else None) or _extract_event_log_from_multipart(raw_str) or raw_str

        if parse_str and (parse_str.strip().startswith('{') or parse_str.strip().startswith('[')):
            res = _receive_json(parse_str)
            person_name, event_time, device_employee_id = res[0], res[1], res[2]
            if len(res) > 3:
                direction = res[3] or 'IN'
            if event_time is None:
                event_time = datetime.utcnow()
            elif not _raw_time_has_timezone(parse_str):
                event_time = _device_time_to_utc(event_time)
        elif 'json' in content_type or request.is_json:
            res = _receive_json(raw_str)
            person_name, event_time, device_employee_id = res[0], res[1], res[2]
            if len(res) > 3:
                direction = res[3] or 'IN'
            if event_time is None:
                event_time = datetime.utcnow()
            elif not _raw_time_has_timezone(raw_str):
                event_time = _device_time_to_utc(event_time)
        elif 'xml' in content_type or raw_str.strip().startswith('<?xml') or raw_str.strip().startswith('<'):
            person_name, event_time, device_employee_id = _receive_xml(raw_str)
            if event_time is None:
                event_time = datetime.utcnow()
            elif not _raw_time_has_timezone(raw_str):
                event_time = _device_time_to_utc(event_time)
        else:
            person_name, event_time, device_employee_id = _receive_raw(parse_str or raw_str)
            if event_time is None:
                event_time = datetime.utcnow()
            elif not _raw_time_has_timezone(parse_str or raw_str):
                event_time = _device_time_to_utc(event_time)

        entry_dict = {
            'device_employee_id': device_employee_id,
            'person_name': person_name,
            'event_time': event_time,
            'direction': direction if direction else 'IN',
            'device_ip': client_ip,
            'raw_data': raw_str,
            'picture_path': None,
        }
        _enqueue_face_log(entry_dict)
        try:
            _start_face_log_worker(current_app._get_current_object())
        except Exception:
            pass
        return jsonify({'status': 'success'}), 200

    except json.JSONDecodeError:
        _write_last_request(client_ip)
        _enqueue_face_log({
            'device_employee_id': None, 'person_name': None, 'event_time': None,
            'direction': 'IN', 'device_ip': client_ip,
            'raw_data': raw_str or '(invalid json)', 'picture_path': None,
        })
        try:
            _start_face_log_worker(current_app._get_current_object())
        except Exception:
            pass
        return jsonify({'status': 'success'}), 200

    except Exception as e:
        _write_last_request(client_ip)
        logger.exception("Hikvision log qayta ishlashda xato: %s", e)
        db.session.rollback()
        try:
            log_incoming_raw(raw_str or str(e), client_ip)
        except Exception:
            pass
        return jsonify({'status': 'error', 'message': 'Internal server error'}), 500


@face_api_bp.route('/picture/<int:log_id>', methods=['GET'])
def serve_picture(log_id):
    """Face log rasmini ko'rsatish. Superadmin yoki TV rejimi (?tv=1) da ruxsat."""
    from flask_login import current_user
    tv_public = request.args.get('tv', '').strip() == '1'
    if not tv_public and (not current_user.is_authenticated or not getattr(current_user, 'is_superadmin', False)):
        abort(403)
    log = FaceLog.query.get_or_404(log_id)
    if not log or not log.picture_path:
        abort(404)
    path = Path(current_app.instance_path) / 'face_log_pictures' / log.picture_path
    if not path.exists():
        abort(404)
    return send_file(str(path), mimetype='image/jpeg')


def backfill_device_employee_ids(limit=5000):
    """Mavjud loglardan raw_data dan Xodim ID ni ajratib, device_employee_id ni to'ldirish."""
    updated = 0
    logs = FaceLog.query.filter(FaceLog.device_employee_id.is_(None), FaceLog.raw_data.isnot(None)).limit(limit).all()
    for log in logs:
        try:
            raw = log.raw_data or ''
            if 'name="event_log"' in raw or "name='event_log'" in raw:
                parse_str = _extract_event_log_from_multipart(raw)
            else:
                parse_str = raw.strip()
                if parse_str.startswith('{'):
                    pass
                else:
                    parse_str = None
            if parse_str and parse_str.startswith('{'):
                _, _, dev_id = _receive_json(parse_str)
                if dev_id:
                    log.device_employee_id = dev_id[:50]
                    updated += 1
        except Exception as e:
            logger.warning("Backfill log %s: %s", log.id, e)
    if updated:
        db.session.commit()
    return updated


@face_api_bp.route('/backfill-device-ids', methods=['POST'])
def face_logs_backfill():
    """Eski loglardan Xodim ID ni qayta to'ldirish – faqat superadmin."""
    from flask_login import current_user
    if not current_user.is_authenticated or not getattr(current_user, 'is_superadmin', False):
        return jsonify({'status': 'error', 'message': 'Access denied'}), 403
    try:
        n = backfill_device_employee_ids()
        return jsonify({'status': 'success', 'updated': n, 'message': f'{n} ta yozuv yangilandi'}), 200
    except Exception as e:
        logger.exception("Backfill xato: %s", e)
        return jsonify({'status': 'error', 'message': str(e)}), 500


@face_api_bp.route('/clear-logs', methods=['POST'])
def face_logs_clear():
    """Barcha yuz tanish loglarini o'chirish – faqat superadmin."""
    from flask_login import current_user
    if not current_user.is_authenticated or not getattr(current_user, 'is_superadmin', False):
        return jsonify({'status': 'error', 'message': 'Access denied'}), 403
    try:
        deleted = FaceLog.query.delete()
        db.session.commit()
        return jsonify({'status': 'success', 'deleted': deleted, 'message': f'{deleted} ta yozuv o\'chirildi'}), 200
    except Exception as e:
        logger.exception("Loglarni tozalashda xato: %s", e)
        db.session.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500


@face_api_bp.route('/log-raw/<int:log_id>', methods=['GET'])
def log_raw(log_id):
    """Log raw ma'lumotini olish – faqat superadmin."""
    from flask_login import current_user
    if not current_user.is_authenticated or not getattr(current_user, 'is_superadmin', False):
        return jsonify({'status': 'error', 'message': 'Access denied'}), 403
    log = FaceLog.query.get_or_404(log_id)
    return (log.raw_data or ''), 200, {'Content-Type': 'text/plain; charset=utf-8'}


def _staff_full_names_for_logs(logs):
    """F.ID (device_employee_id) bo'yicha xodimlar bazasidan to'liq ism map. Agar F.ID bo'yicha xodim topilmasa log ismi ishlatiladi."""
    ids = list({(getattr(l, 'device_employee_id', None) or '').strip() for l in logs if (getattr(l, 'device_employee_id', None) or '').strip()})
    if not ids:
        return {}
    users = User.query.filter(User.employee_code.in_(ids)).all()
    return {u.employee_code: (u.full_name or '').strip() for u in users if (u.employee_code or '').strip()}


@face_api_bp.route('/logs', methods=['GET'])
def logs():
    """
    Hikvision loglarni JSON qaytarish — faqat superadmin. date_from, date_to orqali filtrlash (default bugun).
    Ism: F.ID ga biriktirilgan xodim bazasidagi ism, yo'q bo'lsa log dagi person_name.
    """
    from flask_login import current_user
    from datetime import time as dt_time

    if not current_user.is_authenticated or not getattr(current_user, 'is_superadmin', False):
        return jsonify({'status': 'error', 'message': 'Access denied'}), 403

    try:
        limit = min(int(request.args.get('limit', 100)), 500)
        today_tashkent = (datetime.utcnow() + timedelta(hours=5)).date()
        date_from_s = request.args.get('date_from', '')
        date_to_s = request.args.get('date_to', '')
        try:
            date_from = datetime.strptime(date_from_s, '%Y-%m-%d').date() if date_from_s else today_tashkent
            date_to = datetime.strptime(date_to_s, '%Y-%m-%d').date() if date_to_s else today_tashkent
        except ValueError:
            date_from = today_tashkent
            date_to = today_tashkent
        if date_from > date_to:
            date_to = date_from
        start_dt = datetime.combine(date_from, dt_time(0, 0, 0))
        end_dt = datetime.combine(date_to + timedelta(days=1), dt_time(0, 0, 0))
        sort_by = request.args.get('sort', 'event_time')
        sort_order = request.args.get('order', 'desc')
        if sort_by not in ('id', 'device_employee_id', 'person_name', 'event_time', 'device_ip', 'created_at'):
            sort_by = 'event_time'
        if sort_order not in ('asc', 'desc'):
            sort_order = 'desc'
        search_q = (request.args.get('q') or request.args.get('search') or '').strip()
        order_col = getattr(FaceLog, sort_by)
        order_fn = order_col.desc() if sort_order == 'desc' else order_col.asc()
        q = FaceLog.query.filter(
            FaceLog.event_time >= start_dt,
            FaceLog.event_time < end_dt,
        )
        if search_q:
            q = q.outerjoin(User, User.employee_code == FaceLog.device_employee_id).filter(
                or_(
                    FaceLog.person_name.ilike('%' + search_q + '%'),
                    FaceLog.device_employee_id.ilike('%' + search_q + '%'),
                    User.full_name.ilike('%' + search_q + '%'),
                )
            )
        q = q.order_by(order_fn)
        rows = q.limit(limit * 4).all()
        rows = [r for r in rows if _is_valid_person_name((r.person_name or '').strip())]
        rows = _dedupe_face_logs(rows)[:limit]
        staff_names = _staff_full_names_for_logs(rows)
        log_dicts = []
        for r in rows:
            d = r.to_dict()
            fid = (r.device_employee_id or '').strip()
            d['staff_full_name'] = staff_names.get(fid) or None
            log_dicts.append(d)
        return jsonify({
            'status': 'success',
            'count': len(rows),
            'logs': log_dicts,
        }), 200
    except Exception as e:
        logger.exception("Loglarni olishda xato: %s", e)
        return jsonify({'status': 'error', 'message': 'Internal server error'}), 500


def _is_valid_person_name(name):
    """Haqqiqiy shaxs ismi borligini tekshiradi. Ismsiz (ID 12345, A kirish va h.k.) False."""
    if not name or not isinstance(name, str):
        return False
    s = name.strip()
    if not s or s == '—' or s == '-' or len(s) < 3:
        return False
    s_upper = s.upper()
    if s_upper.startswith('ID'):
        rest = s_upper[2:].strip()
        if rest.isdigit():
            return False
    s_lower = s.lower()
    if s_lower.endswith(' kirish') or s_lower.endswith(' chiqish'):
        if len(s_lower) < 12:
            return False
    if len(s.split()) == 1 and len(s) <= 2:
        return False
    return True


def _dedupe_face_logs(logs):
    """Bir xil (xodim, shaxs, voqea vaqti daqiqasi) loglardan faqat birinchisini qoldiradi."""
    seen = set()
    out = []
    for log in logs:
        emp = (getattr(log, 'device_employee_id', None) or '').strip()
        name = (getattr(log, 'person_name', None) or '').strip()
        et = getattr(log, 'event_time', None)
        if et:
            et_key = et.replace(second=0, microsecond=0)
        else:
            et_key = None
        key = (emp, name, et_key)
        if key in seen:
            continue
        seen.add(key)
        out.append(log)
    return out


def _parse_raw_extra(raw_data):
    """raw_data (JSON) dan dashboard uchun qo'shimcha maydonlarni ajratib oladi."""
    out = {'role': None, 'department': None, 'attendanceStatus': 'present', 'kpiScore': None, 'similarity': None}
    if not raw_data or not isinstance(raw_data, str):
        return out
    try:
        if 'event_log' in raw_data and '{' in raw_data:
            json_str = _extract_event_log_from_multipart(raw_data) or raw_data
        else:
            json_str = raw_data.strip()
        if not json_str.startswith('{'):
            return out
        data = json.loads(json_str)
        if not isinstance(data, dict):
            return out
        out['role'] = (data.get('role') or data.get('userType') or '').strip() or None
        out['department'] = (data.get('department') or data.get('group') or data.get('departmentName') or '').strip() or None
        out['attendanceStatus'] = (data.get('attendanceStatus') or data.get('status') or 'present')
        if isinstance(out['attendanceStatus'], str):
            out['attendanceStatus'] = out['attendanceStatus'].strip().lower().replace(' ', '_')
        out['kpiScore'] = data.get('kpiScore') or data.get('kpi')
        out['similarity'] = data.get('similarity') or data.get('faceMatch')
        return out
    except Exception:
        return out


def _dashboard_card_from_log(log, tz, extra, time_str, event_time, photo_url):
    """FaceLog dan bitta kartochka obyektini yasaydi."""
    person_name = (log.person_name or '').strip()
    kpi = extra.get('kpiScore')
    if kpi is not None:
        try:
            kpi = min(100, max(0, int(kpi)))
        except (TypeError, ValueError):
            kpi = None
    sim = extra.get('similarity')
    if sim is not None:
        try:
            sim = min(100, max(0, int(sim)))
        except (TypeError, ValueError):
            sim = None
    return {
        'personName': person_name,
        'employeeNo': (log.device_employee_id or str(log.id)).strip()[:20] if (log.device_employee_id or log.id) else '—',
        'role': extra.get('role') or 'Employee',
        'department': extra.get('department') or '—',
        'photoUrl': photo_url,
        'lastEntryTime': time_str,
        'attendanceStatus': extra.get('attendanceStatus') or 'present',
        'kpiScore': kpi if kpi is not None else 0,
        'similarity': sim if sim is not None else 0,
        'lastUpdated': int((event_time or log.created_at or datetime.utcnow()).timestamp() * 1000),
    }


@face_api_bp.route('/dashboard-cards', methods=['GET'])
def dashboard_cards():
    """
    Smart Attendance Dashboard – faqat bugungi kun. Kirishlar 09:00 bo'yicha vaqtida/kech,
    chiqishlar 17:00 dan keyin. Barcha bugungi kirish va chiqishlar qaytariladi.
    """
    from flask_login import current_user
    from datetime import timedelta, date, time as dt_time

    try:
        tv_mode = request.args.get('tv', '').strip() == '1'
        if not tv_mode and (not current_user.is_authenticated or not getattr(current_user, 'is_superadmin', False)):
            return jsonify({'status': 'error', 'message': 'Access denied'}), 403

        tz = timedelta(hours=5)
        now_utc = datetime.utcnow()
        today_tashkent = (now_utc + tz).date()
        today_str = today_tashkent.isoformat()
        today_start_utc = datetime.combine(today_tashkent, dt_time(0, 0, 0)) - tz
        today_end_utc = today_start_utc + timedelta(days=1)
        today_start_tashkent = datetime.combine(today_tashkent, dt_time(0, 0, 0))
        today_end_tashkent = today_start_tashkent + timedelta(days=1)
        today_start_wide = today_start_tashkent - timedelta(hours=12)
        today_end_wide = today_end_tashkent + timedelta(hours=2)

        today_filter = or_(
            and_(FaceLog.event_time.isnot(None), FaceLog.event_time >= today_start_wide, FaceLog.event_time < today_end_wide),
            and_(FaceLog.event_time.is_(None), FaceLog.created_at >= today_start_utc, FaceLog.created_at < today_end_utc),
        )
        limit_val = min(int(request.args.get('limit', 300)), 500)
        rows = FaceLog.query.filter(today_filter).order_by(
            FaceLog.created_at.desc()
        ).limit(limit_val).all()
        rows_before = len(rows)
        # Toshkent sanasiga qat’iy moslashtirish (boshqa kunlar qolmasin)
        def _log_date_tashkent(log):
            disp = log.display_event_time()
            if disp:
                return disp.date()
            return (log.created_at + tz).date() if log.created_at else None
        rows = [r for r in rows if _log_date_tashkent(r) == today_tashkent]
        rows = sorted(rows, key=lambda r: (r.display_event_time() or r.created_at or now_utc), reverse=False)

        LATE_THRESHOLD = '09:00:00'
        EXIT_ON_TIME_THRESHOLD = '17:00:00'

        first_kirish_by_key = {}
        last_chiqish_by_key = {}

        for log in rows:
            person_name = (log.person_name or '').strip()
            if not person_name or person_name in ('—', '-'):
                person_name = (log.device_employee_id or '').strip() or ('ID %s' % log.id)
            if not person_name:
                continue
            if not _is_valid_person_name(person_name):
                continue
            if (log.person_name or '').strip() in ('', '—', '-'):
                continue
            event_time = log.display_event_time() or (log.created_at + tz if log.created_at else None)
            if not event_time:
                continue
            key = (log.device_employee_id or '').strip() or person_name or ''
            if not key:
                continue
            time_tashkent = event_time
            time_str = time_tashkent.strftime('%H:%M:%S')
            time_compare = time_str
            if len(time_compare) == 5:
                time_compare = time_compare + ':00'
            extra = _parse_raw_extra(log.raw_data or '')
            photo_url = None
            if log.picture_path:
                photo_url = f"/face-api/picture/{log.id}" + ("?tv=1" if tv_mode else "")
            card = _dashboard_card_from_log(log, tz, extra, time_str, event_time, photo_url)
            if not (log.person_name or '').strip() or (log.person_name or '').strip() in ('—', '-'):
                card['personName'] = person_name

            direction = (log.direction or 'IN').strip().upper()
            if 'CHIQISH' in (log.person_name or '').upper():
                direction = 'OUT'
            if direction == 'OUT':
                if key not in last_chiqish_by_key or event_time > (last_chiqish_by_key[key][0] or event_time):
                    last_chiqish_by_key[key] = (event_time, card)
            else:
                if key not in first_kirish_by_key:
                    first_kirish_by_key[key] = (event_time, card)

        kirish_on_time = []
        kirish_late = []
        for key, (_et, card) in first_kirish_by_key.items():
            card['firstEntryTime'] = card.get('lastEntryTime') or '—'
            card['lastExitTime'] = (last_chiqish_by_key[key][1].get('lastEntryTime') if key in last_chiqish_by_key else None) or '—'
            t = (card.get('lastEntryTime') or '').strip()
            if len(t) == 5:
                t = t + ':00'
            if t and t < LATE_THRESHOLD:
                kirish_on_time.append(card)
            else:
                kirish_late.append(card)

        chiqish_on_time = []
        chiqish_late = []
        for key, (_et, card) in last_chiqish_by_key.items():
            card['lastExitTime'] = card.get('lastEntryTime') or '—'
            card['firstEntryTime'] = (first_kirish_by_key[key][1].get('lastEntryTime') if key in first_kirish_by_key else None) or '—'
            t = (card.get('lastEntryTime') or '').strip()
            if len(t) == 5:
                t = t + ':00'
            if t and t >= EXIT_ON_TIME_THRESHOLD:
                chiqish_on_time.append(card)
            else:
                chiqish_late.append(card)

        # So'ngi o'tganlar birinchi: vaqt bo'yicha kamayish tartibida
        def _entry_time_for_sort(card):
            t = (card.get('lastEntryTime') or card.get('firstEntryTime') or '').strip()
            if len(t) == 5:
                t = t + ':00'
            return t or '00:00:00'
        kirish_on_time.sort(key=_entry_time_for_sort, reverse=True)
        kirish_late.sort(key=_entry_time_for_sort, reverse=True)
        chiqish_on_time.sort(key=_entry_time_for_sort, reverse=True)
        chiqish_late.sort(key=_entry_time_for_sort, reverse=True)

        # Markaz panel: so'nggi 50 ta kirish (IN) – har bir log alohida kartochka
        live_limit = min(int(request.args.get('live_limit', 50)), 100)
        in_logs = []
        for log in rows:
            direction = (log.direction or 'IN').strip().upper()
            if 'CHIQISH' in (log.person_name or '').upper():
                direction = 'OUT'
            if direction != 'IN':
                continue
            person_name = (log.person_name or '').strip()
            if not person_name or not _is_valid_person_name(person_name) or person_name in ('—', '-'):
                continue
            event_time = log.display_event_time() or (log.created_at + tz if log.created_at else None)
            if not event_time:
                continue
            in_logs.append((event_time, log))
        in_logs.sort(key=lambda x: x[0], reverse=True)
        live_entries = []
        for event_time, log in in_logs[:live_limit]:
            extra = _parse_raw_extra(log.raw_data or '')
            time_str = event_time.strftime('%H:%M:%S')
            photo_url = None
            if log.picture_path:
                photo_url = f"/face-api/picture/{log.id}" + ("?tv=1" if tv_mode else "")
            card = _dashboard_card_from_log(log, tz, extra, time_str, event_time, photo_url)
            card['firstEntryTime'] = time_str
            pn = (log.person_name or '').strip() or (log.device_employee_id or '').strip() or ('ID %s' % log.id)
            if pn:
                card['personName'] = pn
            live_entries.append(card)

        # Umumiy statistika (KPI dashboard): vaqtida keldi / kechikdi / kelmagan
        ontime_count = len(kirish_on_time)
        late_count = len(kirish_late)
        total_came = ontime_count + late_count
        total_all = max(total_came, 1)
        ontime_percent = round((ontime_count / total_all) * 100) if total_all else 0
        late_percent = round((late_count / total_all) * 100) if total_all else 0
        absent_count = 0
        absent_percent = 0
        stats = {
            'total_came': total_came,
            'total_all': total_came,
            'ontime_count': ontime_count,
            'late_count': late_count,
            'absent_count': absent_count,
            'ontime_percent': ontime_percent,
            'late_percent': late_percent,
            'absent_percent': absent_percent,
        }

        # Markaziy bo'linmalar: department bo'yicha guruhlash (kirish kartochkalaridan)
        dept_map = {}
        for c in kirish_on_time + kirish_late:
            dept_name = (c.get('department') or '—').strip() or 'Bo\'linmasi yo\'q'
            if dept_name not in dept_map:
                dept_map[dept_name] = {'count': 0, 'kpi_sum': 0}
            dept_map[dept_name]['count'] += 1
            dept_map[dept_name]['kpi_sum'] += (c.get('kpiScore') or 0)
        departments = []
        for name, v in dept_map.items():
            avg_kpi = round(v['kpi_sum'] / v['count']) if v['count'] else 0
            departments.append({'name': name, 'employee_count': v['count'], 'avg_kpi': avg_kpi})
        departments.sort(key=lambda d: d['employee_count'], reverse=True)

        # Faol xodimlar: bugun kelganlar (vaqtida + kechikkan), KPI va status bilan
        active_employees = []
        seen_key = set()
        for c in kirish_on_time + kirish_late:
            key = (c.get('employeeNo') or '') + (c.get('personName') or '')
            if key in seen_key:
                continue
            seen_key.add(key)
            active_employees.append({
                'personName': c.get('personName') or '—',
                'employeeNo': c.get('employeeNo') or '—',
                'department': c.get('department') or '—',
                'photoUrl': c.get('photoUrl'),
                'kpiScore': c.get('kpiScore') or 0,
                'attendanceStatus': c.get('attendanceStatus') or 'present',
                'firstEntryTime': c.get('firstEntryTime') or c.get('lastEntryTime') or '—',
            })
        active_employees.sort(key=lambda x: (x.get('firstEntryTime') or ''), reverse=True)

        out = {
            'status': 'success',
            'kirish_on_time': kirish_on_time,
            'kirish_late': kirish_late,
            'chiqish_on_time': chiqish_on_time,
            'chiqish_late': chiqish_late,
            'live_entries': live_entries,
            'date': today_tashkent.isoformat(),
            'stats': stats,
            'departments': departments,
            'active_employees': active_employees,
        }
        if request.args.get('debug', '').strip() == '1':
            out['_debug'] = {
                'today_tashkent': today_tashkent.isoformat(),
                'now_utc': now_utc.isoformat() + 'Z',
                'rows_fetched': rows_before,
                'rows_today': len(rows),
                'kirish_count': len(first_kirish_by_key),
                'chiqish_count': len(last_chiqish_by_key),
            }
        return jsonify(out), 200
    except Exception as e:
        logger.exception("Dashboard cards xato: %s", e)
        return jsonify({'status': 'error', 'message': 'Internal server error'}), 500
