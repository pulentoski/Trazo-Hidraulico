"""Límite básico de solicitudes a /api por IP de cliente (ventana fija de 60 s en Redis).

Protección mínima mientras no existan usuarios. La IP se toma del último valor de X-Forwarded-For, que
agrega Caddy (único punto de entrada; descarta el encabezado enviado por clientes no confiables).
Si Redis no responde, la solicitud pasa: el límite es una defensa, no un requisito de funcionamiento.
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
EXEMPT = {"/api/health"}
# Partes de una subida de ortofoto: muchas solicitudes seguidas por diseño (cada una pasa por la autenticación).
EXEMPT_RE = re.compile(r"^/api/projects/[^/]+/orthophotos/[^/]+/upload$")


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[-1].strip()
    return request.client.host if request.client else "desconocido"


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        limit = get_settings().rate_limit_per_minute
        path = request.url.path
        if limit <= 0 or not path.startswith("/api/") or path in EXEMPT or EXEMPT_RE.match(path):
            return await call_next(request)
        now = int(time.time())
        window = now // WINDOW_S
        key = f"trazo:rl:{client_ip(request)}:{window}"
        try:
            pipe = get_redis().pipeline()
            pipe.incr(key)
            pipe.expire(key, WINDOW_S + 5)
            count = int(pipe.execute()[0])
        except Exception:  # noqa: BLE001
            log.warning("Límite de solicitudes no disponible (Redis)", exc_info=True)
            return await call_next(request)
        if count > limit:
            retry = (window + 1) * WINDOW_S - now
            return JSONResponse(status_code=429, headers={"Retry-After": str(retry)},
                                content={"detail": f"Demasiadas solicitudes: máximo {limit} por minuto. "
                                                   f"Reintente en {retry} s."})
        return await call_next(request)
