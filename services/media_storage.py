from __future__ import annotations

import mimetypes
import logging
import os
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

from flask import current_app, has_request_context, request
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

from services import get_admin_client


IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.gif'}
VIDEO_EXTENSIONS = {'.mp4', '.webm', '.mov', '.m4v', '.mkv'}
IMAGE_MIME_TYPES = {'image/jpeg', 'image/png', 'image/webp', 'image/gif'}
VIDEO_MIME_TYPES = {'video/mp4', 'video/quicktime', 'video/webm', 'video/x-matroska', 'video/x-m4v'}
logger = logging.getLogger(__name__)


def _uploads_root() -> Path:
    configured = current_app.config.get('UPLOAD_FOLDER')
    root = Path(configured) if configured else Path(current_app.instance_path) / 'uploads'
    root.mkdir(parents=True, exist_ok=True)
    return root


def _is_cloudinary_enabled() -> bool:
    return bool(
        current_app.config.get('CLOUDINARY_CLOUD_NAME')
        and current_app.config.get('CLOUDINARY_API_KEY')
        and current_app.config.get('CLOUDINARY_API_SECRET')
    )


def _configure_cloudinary() -> None:
    import cloudinary

    cloudinary.config(
        cloud_name=current_app.config['CLOUDINARY_CLOUD_NAME'],
        api_key=current_app.config['CLOUDINARY_API_KEY'],
        api_secret=current_app.config['CLOUDINARY_API_SECRET'],
        secure=True,
    )


def _is_loopback_url(url: str) -> bool:
    parsed = urlparse(url)
    hostname = parsed.hostname
    return hostname in {None, 'localhost', '127.0.0.1', '0.0.0.0'}


def _public_base_url() -> str:
    configured = (current_app.config.get('BACKEND_PUBLIC_URL') or '').strip().rstrip('/')
    if configured and not _is_loopback_url(configured):
        return configured
    if has_request_context() and request.host_url:
        return request.host_url.rstrip('/')
    return configured


def _local_media_url(relative_path: str) -> str:
    base = _public_base_url()
    media_path = f"/uploads/{relative_path}"
    return f"{base}{media_path}" if base else media_path


def _allowed_extensions(kind: str) -> set[str]:
    return IMAGE_EXTENSIONS if kind == 'image' else VIDEO_EXTENSIONS


def _allowed_mime_types(kind: str) -> set[str]:
    return IMAGE_MIME_TYPES if kind == 'image' else VIDEO_MIME_TYPES


def _validate_file(file: FileStorage, kind: str) -> str:
    filename = secure_filename(file.filename or '')
    if not filename:
        raise ValueError('A file is required')

    extension = Path(filename).suffix.lower()
    if extension not in _allowed_extensions(kind):
        raise ValueError(f'Unsupported {kind} file type')

    mime_type = (file.mimetype or mimetypes.guess_type(filename)[0] or '').split(';', 1)[0].strip().lower()
    if mime_type and mime_type != 'application/octet-stream' and mime_type not in _allowed_mime_types(kind):
        raise ValueError(f'Unsupported {kind} MIME type')

    return extension


def _supabase_media_url(bucket: str, path: str) -> str:
    base = (current_app.config.get('SUPABASE_URL') or '').strip().rstrip('/')
    return f'{base}/storage/v1/object/public/{bucket}/{path}'


def _upload_to_supabase_storage(file: FileStorage, kind: str, extension: str) -> dict[str, str] | None:
    client = get_admin_client()
    if client is None:
        return None

    bucket = (current_app.config.get('SUPABASE_MEDIA_BUCKET') or 'media').strip() or 'media'
    filename = f'{kind}-{uuid4().hex}{extension}'
    object_path = f'{kind}s/{filename}'

    file.stream.seek(0)
    client.storage.from_(bucket).upload(
        object_path,
        file.stream,
        {
            'content-type': file.mimetype or mimetypes.guess_type(file.filename or '')[0] or 'application/octet-stream',
            'cache-control': '3600',
            'x-upsert': 'true',
        },
    )

    return {
        'url': _supabase_media_url(bucket, object_path),
        'provider': 'supabase',
        'public_id': object_path,
    }


def save_media_file(file: FileStorage, kind: str) -> dict[str, str]:
    extension = _validate_file(file, kind)

    try:
        uploaded = _upload_to_supabase_storage(file, kind, extension)
        if uploaded:
            return uploaded
    except Exception as exc:
        logger.warning('Supabase Storage upload failed for %s; falling back to local storage: %s', kind, exc)
        file.stream.seek(0)

    if _is_cloudinary_enabled():
        try:
            import cloudinary.uploader
        except ImportError as exc:
            raise RuntimeError('Cloudinary support is not installed') from exc

        try:
            _configure_cloudinary()
            resource_type = 'image' if kind == 'image' else 'video'
            uploaded = cloudinary.uploader.upload(
                file,
                folder=f"hok/{kind}s",
                resource_type=resource_type,
                public_id=f"{kind}-{uuid4().hex}",
                overwrite=True,
            )
            return {
                'url': uploaded['secure_url'],
                'provider': 'cloudinary',
                'public_id': uploaded.get('public_id'),
            }
        except Exception as exc:
            logger.warning('Cloudinary upload failed for %s; falling back to local storage: %s', kind, exc)
            file.stream.seek(0)

    relative_dir = Path(kind + 's')
    filename = f"{kind}-{uuid4().hex}{extension}"
    target_dir = _uploads_root() / relative_dir
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / filename
    file.save(target_path)
    return {
        'url': _local_media_url(str(relative_dir / filename).replace(os.sep, '/')),
        'provider': 'local',
        'public_id': None,
    }