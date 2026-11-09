"""Primitivas de seguridad: Argon2id, política de contraseñas, TOTP (RFC 6238) y tokens opacos."""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import get_settings

# Parámetros Argon2id (RFC 9106, segunda recomendación: 64 MiB, 3 pasadas, 4 hilos).
_ph = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4, hash_len=32, salt_len=16)
COMMON = {"1234567890", "contraseña1", "password12", "qwertyuiop", "trazohidraulico", "aguapotable1", "1q2w3e4r5t",
          "contrasena123", "administrador", "123456789a"}


def hash_password(pw: str) -> str:
    return _ph.hash(pw)


def verify_password(hashed: str | None, pw: str) -> bool:
    if not hashed:
        _ph.hash(pw)  # tiempo similar aunque no haya hash (no revela si existe el usuario)
        return False
    try:
        return _ph.verify(hashed, pw)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(hashed: str) -> bool:
    try:
        return _ph.check_needs_rehash(hashed)
    except InvalidHashError:
        return True


def password_problems(pw: str, email: str = "") -> list[str]:
    """Política mínima: largo, letras y números, no común ni igual al correo."""
    n = get_settings().password_min_length
    out = []
    if len(pw) < n:
        out.append(f"Debe tener al menos {n} caracteres.")
    if len(pw) > 256:
        out.append("Máximo 256 caracteres.")
    if not any(c.isalpha() for c in pw) or not any(c.isdigit() for c in pw):
        out.append("Debe combinar letras y números.")
    low = pw.lower()
    if low in COMMON or len(set(low)) < 4:
        out.append("Es demasiado común o repetitiva.")
    if email and email.split("@")[0].lower() in low and len(email.split("@")[0]) >= 4:
        out.append("No debe contener su correo.")
    return out


def new_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# ── TOTP (RFC 6238, SHA-1, 6 dígitos, 30 s) ──

def new_totp_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def totp(secret: str, at: float | None = None, step: int = 30, digits: int = 6) -> str:
    key = base64.b32decode(secret + "=" * (-len(secret) % 8), casefold=True)
    counter = int((at if at is not None else time.time()) // step)
    mac = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    off = mac[-1] & 0x0F
    code = (struct.unpack(">I", mac[off:off + 4])[0] & 0x7FFFFFFF) % 10 ** digits
    return str(code).zfill(digits)


def verify_totp(secret: str | None, code: str, window: int = 1) -> bool:
    if not secret or not code:
        return False
    code = code.strip().replace(" ", "")
    now = time.time()
    return any(hmac.compare_digest(totp(secret, now + k * 30), code) for k in range(-window, window + 1))


def totp_uri(secret: str, email: str, issuer: str = "Trazo Hidráulico") -> str:
    return (f"otpauth://totp/{quote(issuer)}:{quote(email)}?secret={secret}&issuer={quote(issuer)}"
            "&algorithm=SHA1&digits=6&period=30")


def qr_svg(data: str) -> str:
    import io

    import segno

    buf = io.BytesIO()
    segno.make(data, error="m").save(buf, kind="svg", scale=5, border=2, dark="#1b2733", light="#ffffff")
    return buf.getvalue().decode()
