from __future__ import annotations

import logging
from datetime import datetime
from functools import lru_cache

from flask import current_app
from supabase import create_client


logger = logging.getLogger(__name__)


def _supabase_credentials() -> tuple[str, str]:
    url = (current_app.config.get('SUPABASE_URL') or '').strip()
    key = (
        current_app.config.get('SUPABASE_SERVICE_ROLE_KEY')
        or current_app.config.get('SUPABASE_KEY')
        or ''
    ).strip()
    return url, key


@lru_cache(maxsize=4)
def _client_for(url: str, key: str):
    return create_client(url, key)


def get_admin_client():
    url, key = _supabase_credentials()
    if not url or not key:
        return None
    return _client_for(url, key)


def update_user_login_metadata(user_id: int, last_login_at: datetime, last_login_ip: str) -> bool:
    client = get_admin_client()
    if client is None:
        return False

    payload = {
        'last_login_at': last_login_at.isoformat(timespec='seconds'),
        'last_login_ip': last_login_ip,
    }

    try:
        client.table('users').update(payload).eq('id', user_id).execute()
        return True
    except Exception as exc:
        logger.warning('Supabase login metadata update failed for user_id=%s: %s', user_id, exc)
        return False