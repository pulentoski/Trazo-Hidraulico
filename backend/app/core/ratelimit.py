"""Límite de solicitudes a /api (ventana fija de 60 s en Redis).

- Con sesión válida: por **usuario** (RATE_LIMIT_USER_PER_MINUTE, 1200 por defecto): varias pestañas o una oficina
  detrás de la misma IP no se bloquean entre sí.
- Sin sesión (ingreso, recuperación, invitaciones, estado): por **IP** y más estricto (RATE_LIMIT_PER_MINUTE); el
  ingreso tiene además su propio límite de intentos (LOGIN_RATE_PER_MINUTE).
- No cuentan: /api/health, las partes de una subida de ortofoto ni la verificación de teselas de ortofotos
  (/api/auth/tile/…, una por tesela que pide el mapa). Las teselas de OpenStreetMap, Esri y Google no pasan por la API.

La IP se toma del último valor de X-Forwarded-For, que agrega Caddy (único punto de entrada; descarta el encabezado
enviado por clientes no confiables). Si Redis no responde, la solicitud pasa: el límite es una defensa, no un
requisito de funcionamiento. La respuesta 429 trae Retry-After (segundos hasta la ventana siguiente).
"""
import logging
import re
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.cache import get_redis
from app.core.config import get_settings

log = logging.getLogger(__name__)
WINDOW_S = 60
SESSION_CACHE_S = 60
EXEMPT = {"/api/health"}
# Partes de una subida de ortofoto (muchas solicitudes seguidas por diseño) y verificación de teselas de ortofotos.
EXEMPT_RE = re.compile(r"^/api/(projects/[^/]+/orthophotos/[^/]+/upload|auth/tile/[^/]+)$")


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[-1].strip()
    return request.client.host if request.client else "desconocido"


def session_user(request: Request, redis) -> str | None:
    """Usuario de la cookie de sesión (si es válida), con caché corta en Redis para no consultar la base cada vez."""
    from app.core import security

    token = request.cookies.get(get_settings().cookie_name)
    if not token:
        return None
    th = security.token_hash(token)
    key = f"trazo:rlsess:{th}"
    cached = redis.get(key)
    if cached is not None:
        v = cached.decode() if isinstance(cached, bytes) else str(cached)
        return v or None
    from datetime import datetime, timezone

    from app.core.db import get_sessionmaker
    from app.models import UserSession

    with get_sessionmaker()() as session:
        s = session.get(UserSession, th)
        user = str(s.user_id) if s is not None and s.expires_at > datetime.now(timezone.utc) else ""
    redis.set(key, user, ex=SESSION_CACHE_S)
    return user or None


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        st = get_settings()
        path = request.url.path
        if not path.startswith("/api/") or path in EXEMPT or EXEMPT_RE.match(path):
            return await call_next(request)
        now = int(time.time())
        window = now // WINDOW_S
        try:
            redis = get_redis()
            user = session_user(request, redis)
            limit = st.rate_limit_user_per_minute if user else st.rate_limit_per_minute
            if limit <= 0:
                return await call_next(request)
            key = f"trazo:rl:{'u:' + user if user else 'ip:' + client_ip(request)}:{window}"
            pipe = redis.pipeline()
            pipe.incr(key)
            pipe.expire(key, WINDOW_S + 5)
            count = int(pipe.execute()[0])
        except Exception:  # noqa: BLE001
            log.warning("Límite de solicitudes no disponible (Redis)", exc_info=True)
            return await call_next(request)
        if count > limit:
            retry = max(1, (window + 1) * WINDOW_S - now)
            return JSONResponse(status_code=429, headers={"Retry-After": str(retry)},
                                content={"detail": f"Demasiadas solicitudes: máximo {limit} por minuto. Reintente en {retry} s.",
                                         "code": "rate_limited"})
        return await call_next(request)
