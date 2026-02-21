"""
Hikvision face API – qurilmalardan log qabul qilish va superadmin uchun ko‘rsatish.
"""
import json
import logging
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

from flask import request, jsonify, current_app, send_file, abort

from app import db
from app.models import FaceLog

logger = logging.getLogger(__name__)

PERSON_NAME_KEYS = (
    'personName', 'person_name', 'PersonName', 'name', 'Name',
    'userName', 'user_name', 'employeeName', 'faceName', 'face_name',
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
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    s = str(value).strip()
    if not s:
        return None
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


def extract_device_employee_id(data):
    """Qurilmadagi xodim ID (employeeNoString) ni ajratib oladi."""
    keys = ('employeeNoString', 'employeeNo', 'employee_no')
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


def log_incoming_raw(raw_str, client_ip):
    try:
        logs_dir = Path(current_app.instance_path) / '..' / 'logs'
        logs_dir = logs_dir.resolve()
        logs_dir.mkdir(parents=True, exist_ok=True)
        log_path = logs_dir / 'face_incoming.log'
        with open(log_path, 'a', encoding='utf-8', errors='replace') as f:
            f.write(f"--- {datetime.utcnow().isoformat()} | {client_ip} ---\n")
            f.write(raw_str[:65536])
            if len(raw_str) > 65536:
                f.write("\n... [truncated]\n")
            f.write("\n\n")
    except Exception as e:
        logger.warning("face incoming.log yozishda xato: %s", e)


def _write_last_request(client_ip):
    """So'nggi qabul qilingan so'rov haqida (admin sahifada diagnostika uchun)."""
    try:
        inst = Path(current_app.instance_path)
        inst.mkdir(parents=True, exist_ok=True)
        path = inst / 'face_last_request.txt'
        with open(path, 'w', encoding='utf-8') as f:
            f.write(f"{datetime.utcnow().isoformat()}\n{client_ip}\n")
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


def _receive_json(data_str):
    try:
        data = json.loads(data_str)
    except json.JSONDecodeError:
        return None, None, None
    return extract_person_name(data), extract_event_time(data), extract_device_employee_id(data)


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
        raw_str = request.get_data(as_text=True) or request.data.decode('utf-8', errors='replace')
        if not raw_str:
            raw_str = str(request.form) if request.form else '(empty body)'

        log_incoming_raw(raw_str, client_ip)
        _write_last_request(client_ip)
        logger.info("Hikvision log qabul qilindi: %s, uzunlik=%d", client_ip, len(raw_str))

        person_name, event_time, device_employee_id = None, None, None
        parse_str = raw_str

        if 'multipart' in content_type:
            event_log_form = request.form.get('event_log') if request.form else None
            parse_str = (event_log_form if isinstance(event_log_form, str) else None) or _extract_event_log_from_multipart(raw_str) or raw_str

        if parse_str and (parse_str.strip().startswith('{') or parse_str.strip().startswith('[')):
            person_name, event_time, device_employee_id = _receive_json(parse_str)
        elif 'json' in content_type or request.is_json:
            person_name, event_time, device_employee_id = _receive_json(raw_str)
        elif 'xml' in content_type or raw_str.strip().startswith('<?xml') or raw_str.strip().startswith('<'):
            person_name, event_time, device_employee_id = _receive_xml(raw_str)
        else:
            person_name, event_time, device_employee_id = _receive_raw(parse_str or raw_str)

        picture_path = None
        pic_file = (request.files.get('Picture') or request.files.get('picture')) if 'multipart' in content_type else None
        if pic_file and pic_file.filename:
            try:
                pics_dir = Path(current_app.instance_path) / 'face_log_pictures'
                pics_dir.mkdir(parents=True, exist_ok=True)
                ext = Path(pic_file.filename).suffix or '.jpg'
                import uuid
                fname = f"{uuid.uuid4().hex}{ext}"
                save_path = pics_dir / fname
                pic_file.save(str(save_path))
                picture_path = fname
            except Exception as e:
                logger.warning("Face rasmini saqlashda xato: %s", e)

        entry = FaceLog(
            device_employee_id=device_employee_id,
            person_name=person_name,
            event_time=event_time,
            device_ip=client_ip,
            raw_data=raw_str,
            picture_path=picture_path,
        )
        db.session.add(entry)
        db.session.commit()
        return jsonify({'status': 'success'}), 200

    except json.JSONDecodeError:
        _write_last_request(client_ip)
        try:
            db.session.add(FaceLog(
                device_employee_id=None, person_name=None, event_time=None, device_ip=client_ip,
                raw_data=raw_str or '(invalid json)', picture_path=None,
            ))
            db.session.commit()
        except Exception:
            db.session.rollback()
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
    """Face log rasmini ko'rsatish – faqat superadmin."""
    from flask_login import current_user
    if not current_user.is_authenticated or not getattr(current_user, 'is_superadmin', False):
        abort(403)
    log = FaceLog.query.get_or_404(log_id)
    if not log or not log.picture_path:
        abort(404)
    path = Path(current_app.instance_path) / 'face_log_pictures' / log.picture_path
    if not path.exists():
        abort(404)
    return send_file(str(path), mimetype='image/jpeg')


@face_api_bp.route('/log-raw/<int:log_id>', methods=['GET'])
def log_raw(log_id):
    """Log raw ma'lumotini olish – faqat superadmin."""
    from flask_login import current_user
    if not current_user.is_authenticated or not getattr(current_user, 'is_superadmin', False):
        return jsonify({'status': 'error', 'message': 'Access denied'}), 403
    log = FaceLog.query.get_or_404(log_id)
    return (log.raw_data or ''), 200, {'Content-Type': 'text/plain; charset=utf-8'}


@face_api_bp.route('/logs', methods=['GET'])
def logs():
    """
    Hikvision loglarni JSON qaytarish — faqat superadmin uchun.
    """
    from flask_login import current_user

    if not current_user.is_authenticated or not getattr(current_user, 'is_superadmin', False):
        return jsonify({'status': 'error', 'message': 'Access denied'}), 403

    try:
        limit = min(int(request.args.get('limit', 100)), 500)
        rows = FaceLog.query.order_by(FaceLog.created_at.desc()).limit(limit).all()
        return jsonify({
            'status': 'success',
            'count': len(rows),
            'logs': [r.to_dict() for r in rows],
        }), 200
    except Exception as e:
        logger.exception("Loglarni olishda xato: %s", e)
        return jsonify({'status': 'error', 'message': 'Internal server error'}), 500
