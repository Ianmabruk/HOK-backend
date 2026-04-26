from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

from flask import current_app
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename


IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.gif'}
VIDEO_EXTENSIONS = {'.mp4', '.webm', '.mov', '.m4v'}


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


def _local_media_url(relative_path: str) -> str:
    base = current_app.config.get('BACKEND_PUBLIC_URL', '').rstrip('/')
    media_path = f"/uploads/{relative_path}"
    return f"{base}{media_path}" if base else media_path


def _allowed_extensions(kind: str) -> set[str]:
    return IMAGE_EXTENSIONS if kind == 'image' else VIDEO_EXTENSIONS


def _validate_file(file: FileStorage, kind: str) -> str:
    filename = secure_filename(file.filename or '')
    if not filename:
        raise ValueError('A file is required')

    extension = Path(filename).suffix.lower()
    if extension not in _allowed_extensions(kind):
        raise ValueError(f'Unsupported {kind} file type')

    return extension


def save_media_file(file: FileStorage, kind: str) -> dict[str, str]:
    extension = _validate_file(file, kind)

    if _is_cloudinary_enabled():
        try:
            import cloudinary.uploader
        except ImportError as exc:
            raise RuntimeError('Cloudinary support is not installed') from exc

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
        }

    relative_dir = Path(kind + 's')
    filename = f"{kind}-{uuid4().hex}{extension}"
    target_dir = _uploads_root() / relative_dir
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / filename
    file.save(target_path)
    return {
        'url': _local_media_url(str(relative_dir / filename).replace(os.sep, '/')),
        'provider': 'local',
    }