"""
Markaziy API blueprint – vazirlik serverida institutlarni boshqarish.
Main app ichida /central-api/ prefiksi bilan qo'shiladi.
"""
import json
import logging
import threading
from pathlib import Path
from flask import Blueprint, jsonify, request, Response, stream_with_context, current_app, send_from_directory, send_from_directory

logger = logging.getLogger(__name__)

central_bp = Blueprint('central_api', __name__, url_prefix='/central-api')

# SSE subscribers: list of dicts {'q': queue, 'institution_id': str}
sse_subscribers = []
sse_lock = threading.Lock()


def get_connected_institution_ids():
    """Markazga hozir ulangan institut ID lari (SSE orqali)."""
    with sse_lock:
        return {s.get('institution_id') for s in sse_subscribers if s.get('institution_id')}


def get_institutions_with_status():
    """Ro'yxat: institutions.json dagi institutlar + ulangan holati."""
    data = _load_institutions()
    connected = get_connected_institution_ids()
    result = []
    for i in data.get('institutions', []):
        row = dict(i)
        row['connected'] = str(i.get('id', '')) in connected
        result.append(row)
    return result


def _get_central_dirs():
    """Markaziy ma'lumotlar papkalari – instance/central/ ichida."""
    inst = Path(current_app.instance_path)
    base = inst / 'central'
    return base / 'data', base / 'releases'


def _load_institutions():
    data_dir, _ = _get_central_dirs()
    inst_file = data_dir / 'institutions.json'
    if not inst_file.exists():
        data_dir.mkdir(parents=True, exist_ok=True)
        default = {
            "institutions": [],
            "default_permissions": ["main", "courses", "attendance", "face_log", "accounting", "admin"],
            "center_blocked": False,
            "center_block_reason": ""
        }
        inst_file.write_text(json.dumps(default, ensure_ascii=False, indent=2), encoding='utf-8')
        return default
    with open(inst_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    if 'center_blocked' not in data:
        data['center_blocked'] = False
        data['center_block_reason'] = ''
        _save_institutions(data)
    return data


def _save_institutions(data):
    data_dir, _ = _get_central_dirs()
    data_dir.mkdir(parents=True, exist_ok=True)
    with open(data_dir / 'institutions.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_center_block_status():
    """Markaz o'zi bloklanganmi (faqat markaz UI taqiqlanadi, institutlar ishlaydi)."""
    data = _load_institutions()
    return {
        "blocked": bool(data.get("center_blocked", False)),
        "block_reason": (data.get("center_block_reason") or "").strip()
    }


def set_center_block(blocked, block_reason=""):
    """Markaz blokini o'rnatish (True/False)."""
    data = _load_institutions()
    data["center_blocked"] = bool(blocked)
    data["center_block_reason"] = str(block_reason or "").strip()
    _save_institutions(data)


def _load_version():
    _, rel_dir = _get_central_dirs()
    v_file = rel_dir / 'version.json'
    if not v_file.exists():
        rel_dir.mkdir(parents=True, exist_ok=True)
        default = {"version": "1.0.0", "released_at": "2026-02-22T00:00:00Z", "download_url": "", "checksum": ""}
        v_file.write_text(json.dumps(default, indent=2), encoding='utf-8')
        return default
    with open(v_file, 'r', encoding='utf-8') as f:
        return json.load(f)


def _broadcast_event(event_type, data=None):
    payload = json.dumps({"type": event_type, "data": data or {}})
    with sse_lock:
        dead = []
        for s in sse_subscribers:
            q = s.get('q')
            if q is None:
                dead.append(s)
                continue
            try:
                q.put(payload)
            except Exception:
                dead.append(s)
        for d in dead:
            if d in sse_subscribers:
                sse_subscribers.remove(d)


@central_bp.route('/releases/<path:filename>')
def serve_release(filename):
    """Zip fayllarni instance/central/releases/ dan xizmat qilish (yangilanish uchun)."""
    if not filename.endswith('.zip') or '..' in filename:
        return jsonify({'error': 'Forbidden'}), 403
    _, rel_dir = _get_central_dirs()
    path = (rel_dir / filename).resolve()
    if not path.is_file() or not str(path).startswith(str(rel_dir.resolve())):
        return jsonify({'error': 'Not found'}), 404
    return send_from_directory(rel_dir, filename, as_attachment=True, download_name=filename)


@central_bp.route('/api/version', methods=['GET', 'POST'])
def api_version():
    if request.method == 'POST':
        try:
            payload = request.get_json()
            v = _load_version()
            v['version'] = payload.get('version', v['version'])
            v['released_at'] = payload.get('released_at', v['released_at'])
            v['download_url'] = payload.get('download_url', v['download_url'])
            v['checksum'] = payload.get('checksum', v.get('checksum', ''))
            _, rel_dir = _get_central_dirs()
            rel_dir.mkdir(parents=True, exist_ok=True)
            (rel_dir / 'version.json').write_text(json.dumps(v, indent=2), encoding='utf-8')
            _broadcast_event('update', v)
            logger.info("Yangi versiya: %s", v['version'])
            return jsonify({'status': 'success', 'version': v}), 200
        except Exception as e:
            logger.exception("Versiya yangilashda xato: %s", e)
            return jsonify({'status': 'error', 'message': str(e)}), 500
    v = _load_version()
    return jsonify(v)


@central_bp.route('/api/institution/<institution_id>/status', methods=['GET'])
def api_institution_status(institution_id):
    data = _load_institutions()
    inst = next((i for i in data.get('institutions', []) if str(i.get('id')) == str(institution_id)), None)
    if not inst:
        return jsonify({
            "blocked": False,
            "block_reason": None,
            "permissions": data.get('default_permissions', ['main', 'courses', 'attendance', 'face_log', 'accounting', 'admin'])
        }), 200
    return jsonify({
        "blocked": bool(inst.get('blocked', False)),
        "block_reason": inst.get('block_reason', ''),
        "permissions": inst.get('permissions', data.get('default_permissions', []))
    }), 200


@central_bp.route('/api/stream', methods=['GET'])
def api_stream():
    institution_id = (request.args.get('institution_id') or '').strip()
    logger.info("SSE ulanish: institution_id=%s", institution_id)
    import queue
    q = queue.Queue()
    sub = {'q': q, 'institution_id': institution_id}
    with sse_lock:
        sse_subscribers.append(sub)

    def generate():
        try:
            yield f"data: {json.dumps({'type': 'connected', 'message': 'Ulanish ochildi'})}\n\n"
            while True:
                try:
                    msg = sub['q'].get(timeout=30)
                    yield f"data: {msg}\n\n"
                except Exception:
                    yield f"data: {json.dumps({'type': 'ping'})}\n\n"
        except GeneratorExit:
            with sse_lock:
                for i, s in enumerate(sse_subscribers):
                    if s.get('q') is q:
                        sse_subscribers.pop(i)
                        break
            logger.info("SSE ulanish yopildi: institution_id=%s", institution_id)

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'}
    )


@central_bp.route('/api/institutions', methods=['GET'])
def api_institutions_list():
    data = _load_institutions()
    return jsonify(data.get('institutions', []))


def update_institutions_list(updated_list):
    """
    Institutlar ro'yxatini yangilash (markazda, dasturiy chaqirish).
    updated_list: [{'id': str, 'name': str, 'blocked': bool, 'block_reason': str, 'permissions': list}, ...]
    """
    data = _load_institutions()
    institutions = data.get('institutions', [])
    for u in updated_list:
        inst_id = str(u.get('id', ''))
        if not inst_id:
            continue
        existing = next((i for i in institutions if str(i.get('id')) == inst_id), None)
        if existing:
            existing.update({
                'name': u.get('name', existing.get('name')),
                'description': u.get('description', existing.get('description', '')),
                'blocked': u.get('blocked', existing.get('blocked')),
                'block_reason': u.get('block_reason', existing.get('block_reason', '')),
                'permissions': u.get('permissions', existing.get('permissions', []))
            })
        else:
            institutions.append({
                'id': inst_id,
                'name': u.get('name', 'Institut'),
                'description': u.get('description', ''),
                'blocked': u.get('blocked', False),
                'block_reason': u.get('block_reason', ''),
                'permissions': u.get('permissions', data.get('default_permissions', []))
            })
    data['institutions'] = institutions
    _save_institutions(data)
    _broadcast_event('institution_updated', {'institutions': institutions})
    return institutions


def delete_institution(inst_id):
    """Institutni ro'yxatdan o'chirish (markazda)."""
    data = _load_institutions()
    institutions = [i for i in data.get('institutions', []) if str(i.get('id')) != str(inst_id)]
    data['institutions'] = institutions
    _save_institutions(data)
    _broadcast_event('institution_updated', {'institutions': institutions})
    return institutions


@central_bp.route('/api/institutions', methods=['POST'])
def api_institutions_update():
    try:
        payload = request.get_json()
        updated = payload.get('institutions', payload) if isinstance(payload.get('institutions'), list) else [payload]
        institutions = update_institutions_list(updated)
        return jsonify({'status': 'success', 'institutions': institutions}), 200
    except Exception as e:
        logger.exception("Institutlarni yangilashda xato: %s", e)
        return jsonify({'status': 'error', 'message': str(e)}), 500


def trigger_update_now():
    """Markazda: barcha SSE ulangan institutlarga yangilanish xabarini yuborish (dasturiy chaqirish)."""
    v = _load_version()
    _broadcast_event('update', v)
    return v


@central_bp.route('/api/center-block', methods=['GET', 'POST'])
def api_center_block():
    """Markaz blok holati (faqat markaz UI taqiqlanadi; institutlar /central-api orqali ishlashda qoladi)."""
    if request.method == 'POST':
        try:
            payload = request.get_json() or {}
            blocked = payload.get('blocked', False)
            reason = (payload.get('block_reason') or '').strip()
            set_center_block(blocked, reason)
            return jsonify({'status': 'ok', 'center_blocked': blocked}), 200
        except Exception as e:
            logger.exception("Markaz blokini o'rnatishda xato: %s", e)
            return jsonify({'status': 'error', 'message': str(e)}), 500
    return jsonify(get_center_block_status()), 200


@central_bp.route('/api/trigger-update', methods=['POST'])
def api_trigger_update():
    trigger_update_now()
    return jsonify({'status': 'ok', 'message': 'Yangilanish xabari yuborildi'}), 200


@central_bp.route('/')
def index():
    v = _load_version()
    return jsonify({
        'service': 'Elemes Markaziy Boshqaruv',
        'version': v.get('version', '1.0.0'),
        'base_url': '/central-api',
        'endpoints': {
            'version': '/central-api/api/version',
            'stream': '/central-api/api/stream?institution_id=xxx',
            'status': '/central-api/api/institution/<id>/status',
            'institutions': '/central-api/api/institutions'
        }
    })
