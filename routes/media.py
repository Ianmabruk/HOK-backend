from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request

from services.media_storage import MediaUploadError, save_media_file


media_bp = Blueprint('media', __name__)
logger = logging.getLogger(__name__)


def _media_kind() -> str:
    raw_kind = str(request.form.get('kind') or request.form.get('type') or 'image').strip().lower()
    if raw_kind in {'image', 'video'}:
        return raw_kind
    return 'image'


def _media_folder(kind: str) -> str:
    folder = str(request.form.get('folder') or request.form.get('category') or '').strip()
    if folder:
        return folder
    return f'{kind}s'


@media_bp.post('/media/upload')
def upload_media():
    file = request.files.get('file')
    if file is None or not file.filename:
        return jsonify({'message': 'Missing file'}), 400

    kind = _media_kind()
    folder = _media_folder(kind)

    try:
        uploaded = save_media_file(file, kind, folder=folder)
        return jsonify({
            'url': uploaded['url'],
            'public_url': uploaded['url'],
            'path': uploaded.get('public_id'),
            'public_id': uploaded.get('public_id'),
            'bucket': uploaded.get('bucket'),
            'media_type': kind,
            'content_type': uploaded.get('content_type'),
        }), 201
    except MediaUploadError as exc:
        logger.warning('media.upload.failed folder=%s kind=%s error=%s', folder, kind, exc)
        return jsonify({'message': exc.user_message, 'error': str(exc)}), exc.status_code
    except Exception as exc:  # pragma: no cover
        logger.exception('Unexpected media upload failure folder=%s kind=%s', folder, kind)
        return jsonify({'message': 'Upload failed', 'error': str(exc)}), 500
