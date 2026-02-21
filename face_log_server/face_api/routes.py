"""
Face API routes for receiving and retrieving Hikvision face logs.
"""
import json
import logging
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

from flask import request, jsonify, current_app

from face_api import face_api_bp  # noqa: E402
from models import db, FaceLog  # noqa: E402

logger = logging.getLogger(__name__)

# Hikvision JSON/XML field name variations for person name
PERSON_NAME_KEYS = (
    'personName', 'person_name', 'PersonName', 'personName',
    'name', 'Name', 'userName', 'user_name', 'employeeName',
    'employee_name', 'EmployeeName', 'faceName', 'face_name',
)
EVENT_TIME_KEYS = (
    'eventTime', 'event_time', 'EventTime', 'time', 'Time',
    'timestamp', 'Timestamp', 'eventTime', 'captureTime',
)


def get_client_ip():
    """Detect client IP, handling proxies (X-Forwarded-For, X-Real-IP)."""
    if request.headers.get('X-Forwarded-For'):
        return request.headers.get('X-Forwarded-For').split(',')[0].strip()
    if request.headers.get('X-Real-IP'):
        return request.headers.get('X-Real-IP').strip()
    return request.remote_addr or 'unknown'


def safe_extract(data, keys, default=None):
    """Recursively extract value from dict by multiple possible keys."""
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
    """Parse event time from various formats."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    s = str(value).strip()
    if not s:
        return None
    # ISO format
    for fmt in (
        '%Y-%m-%dT%H:%M:%S',
        '%Y-%m-%dT%H:%M:%S.%f',
        '%Y-%m-%dT%H:%M:%SZ',
        '%Y-%m-%d %H:%M:%S',
        '%Y-%m-%d %H:%M:%S.%f',
        '%Y/%m/%d %H:%M:%S',
        '%d.%m.%Y %H:%M:%S',
    ):
        try:
            return datetime.strptime(s[:26].rstrip('Z'), fmt.replace('Z', ''))
        except ValueError:
            continue
    return None


def extract_person_name(data):
    """Extract person name from dict (handles nested structures)."""
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
    """Extract event time from dict."""
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


def log_incoming_raw(raw_str, client_ip):
    """Append raw request to logs/incoming.log."""
    try:
        logs_dir = current_app.config.get('LOGS_DIR')
        if logs_dir is None:
            logs_dir = Path(current_app.root_path) / 'logs'
        log_path = Path(logs_dir) / 'incoming.log'
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, 'a', encoding='utf-8', errors='replace') as f:
            f.write(f"--- {datetime.utcnow().isoformat()} | {client_ip} ---\n")
            f.write(raw_str[:65536])  # Limit 64KB per request
            if len(raw_str) > 65536:
                f.write("\n... [truncated]\n")
            f.write("\n\n")
    except Exception as e:
        logger.warning("Failed to write incoming.log: %s", e)


def _receive_json(data_str, client_ip):
    """Parse JSON and create FaceLog entry."""
    try:
        data = json.loads(data_str)
    except json.JSONDecodeError:
        return None, None, data_str
    person_name = extract_person_name(data)
    event_time = extract_event_time(data)
    return person_name, event_time, data_str


def _receive_xml(data_str, client_ip):
    """Parse XML and try to extract person name and event time."""
    person_name = None
    event_time = None
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
    return person_name, event_time, data_str


def _receive_raw(data_str, client_ip):
    """Try to parse as JSON first, else treat as raw."""
    stripped = data_str.strip()
    if stripped.startswith('{') or stripped.startswith('['):
        return _receive_json(data_str, client_ip)
    if stripped.startswith('<?xml') or stripped.startswith('<'):
        return _receive_xml(data_str, client_ip)
    return None, None, data_str


@face_api_bp.route('/receive', methods=['POST'])
def receive():
    """
    Receive face recognition logs from Hikvision devices.
    Accepts JSON, XML, or raw POST body.
    """
    client_ip = get_client_ip()
    raw_str = ''

    try:
        content_type = (request.content_type or '').lower()
        if 'json' in content_type or request.is_json:
            raw_str = request.get_data(as_text=True) or ''
        else:
            raw_str = request.get_data(as_text=True) or request.data.decode('utf-8', errors='replace')

        if not raw_str:
            raw_str = str(request.form) if request.form else '(empty body)'

        # Log full raw request
        log_incoming_raw(raw_str, client_ip)
        logger.info("Received face log from %s, length=%d", client_ip, len(raw_str))

        person_name = None
        event_time = None
        content_type = (request.content_type or '').lower()

        if 'json' in content_type or request.is_json:
            person_name, event_time, _ = _receive_json(raw_str, client_ip)
        elif 'xml' in content_type or raw_str.strip().startswith('<?xml') or raw_str.strip().startswith('<'):
            person_name, event_time, _ = _receive_xml(raw_str, client_ip)
        else:
            person_name, event_time, _ = _receive_raw(raw_str, client_ip)

        # Store in database
        entry = FaceLog(
            person_name=person_name,
            event_time=event_time,
            device_ip=client_ip,
            raw_data=raw_str,
        )
        db.session.add(entry)
        db.session.commit()
        logger.debug("Stored face log id=%d", entry.id)

        return jsonify({'status': 'success'}), 200

    except json.JSONDecodeError as e:
        logger.warning("Invalid JSON from %s: %s", client_ip, e)
        # Still store raw
        try:
            entry = FaceLog(
                person_name=None,
                event_time=None,
                device_ip=client_ip,
                raw_data=raw_str or '(invalid json)',
            )
            db.session.add(entry)
            db.session.commit()
        except Exception:
            db.session.rollback()
        return jsonify({'status': 'success'}), 200

    except Exception as e:
        logger.exception("Error processing face log from %s: %s", client_ip, e)
        db.session.rollback()
        try:
            log_incoming_raw(raw_str or str(e), client_ip)
        except Exception:
            pass
        return jsonify({'status': 'error', 'message': 'Internal server error'}), 500


@face_api_bp.route('/logs', methods=['GET'])
def logs():
    """Return latest 100 face logs in JSON, ordered newest first."""
    try:
        limit = min(int(request.args.get('limit', 100)), 500)
        rows = FaceLog.query.order_by(FaceLog.created_at.desc()).limit(limit).all()
        return jsonify({
            'status': 'success',
            'count': len(rows),
            'logs': [r.to_dict() for r in rows],
        }), 200
    except Exception as e:
        logger.exception("Error fetching logs: %s", e)
        return jsonify({'status': 'error', 'message': 'Internal server error'}), 500
