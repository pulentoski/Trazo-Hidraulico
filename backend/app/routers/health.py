from fastapi import APIRouter, Response
from sqlalchemy import text

from app.core.cache import get_redis
from app.core.db import get_engine

router = APIRouter(tags=["sistema"])


@router.get("/health", summary="Estado de la API, la base de datos y la caché")
def health(response: Response) -> dict[str, str]:
    status = {"api": "ok", "db": "ok", "cache": "ok"}
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001
        status["db"] = "error"
    try:
        get_redis().ping()
    except Exception:  # noqa: BLE001
        status["cache"] = "error"
    if "error" in status.values():
        response.status_code = 503
    return status
