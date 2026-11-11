"""Configuración de la plataforma guardada en la base: key de Google Maps (cifrada) y Map ID.

El cifrado usa Fernet (AES-128-CBC + HMAC-SHA256) con una clave derivada de SETTINGS_SECRET_KEY (.env). Sin esa
variable no se puede guardar la key. El frontend obtiene la key en tiempo de ejecución (/api/maps/config); la
variable VITE_GOOGLE_MAPS_API_KEY del frontend queda solo como respaldo.
"""
from __future__ import annotations

import base64
import hashlib
import re

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import PlatformSetting

MAPS_KEY = "google_maps_api_key"
MAPS_ID = "google_maps_map_id"
KEY_RE = re.compile(r"^[A-Za-z0-9_\-]{20,200}$")
MAP_ID_RE = re.compile(r"^[A-Za-z0-9_\-]{1,100}$")


class SettingsError(ValueError):
    pass


class NotConfigured(SettingsError):
    """Falta SETTINGS_SECRET_KEY en el .env."""


def _fernet() -> Fernet:
    secret = get_settings().settings_secret_key.strip()
    if not secret:
        raise NotConfigured("Falta SETTINGS_SECRET_KEY en el .env del servidor: sin ella no se puede guardar la key "
                            "cifrada. Agréguela (ver .env.example) y reinicie la API.")
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest()))


def encryption_ready() -> bool:
    return bool(get_settings().settings_secret_key.strip())


def _get(session: Session, key: str) -> PlatformSetting | None:
    return session.get(PlatformSetting, key)


def _value(session: Session, key: str) -> str | None:
    row = _get(session, key)
    if row is None:
        return None
    if not row.encrypted:
        return row.value
    try:
        return _fernet().decrypt(row.value.encode()).decode()
    except (InvalidToken, NotConfigured):
        return None  # clave de cifrado cambiada o ausente: la key guardada ya no se puede leer


def _put(session: Session, key: str, value: str | None, *, encrypt: bool, who: str | None) -> None:
    row = _get(session, key)
    if value is None:
        if row is not None:
            session.delete(row)
        return
    stored = _fernet().encrypt(value.encode()).decode() if encrypt else value
    if row is None:
        session.add(PlatformSetting(key=key, value=stored, encrypted=encrypt, updated_by=who))
    else:
        row.value, row.encrypted, row.updated_by = stored, encrypt, who


def maps_config(session: Session) -> tuple[str | None, str | None]:
    return _value(session, MAPS_KEY), _value(session, MAPS_ID)


def hint(key: str | None) -> str | None:
    """Solo los primeros 4 y los últimos 4 caracteres (nunca la key completa)."""
    if not key:
        return None
    return f"{key[:4]}…{key[-4:]}"


def maps_status(session: Session) -> dict:
    key, map_id = maps_config(session)
    row = _get(session, MAPS_KEY) or _get(session, MAPS_ID)
    stored_unreadable = _get(session, MAPS_KEY) is not None and key is None
    return {"configured": bool(key), "key_hint": hint(key), "map_id": map_id,
            "updated_at": row.updated_at if row else None, "updated_by": row.updated_by if row else None,
            "encryption_ready": encryption_ready(), "unreadable": stored_unreadable}


def save_maps(session: Session, api_key: str | None, map_id: str | None, *, keep_key: bool, keep_map_id: bool,
              who: str | None) -> None:
    if not keep_key:
        if api_key is not None:
            api_key = api_key.strip()
            if not KEY_RE.match(api_key):
                raise SettingsError("La key no tiene el formato de una API key de Google (letras, números, «-» y «_»).")
        _put(session, MAPS_KEY, api_key, encrypt=True, who=who)
    if not keep_map_id:
        if map_id is not None:
            map_id = map_id.strip() or None
            if map_id is not None and not MAP_ID_RE.match(map_id):
                raise SettingsError("El Map ID solo admite letras, números, «-» y «_».")
        _put(session, MAPS_ID, map_id, encrypt=False, who=who)
