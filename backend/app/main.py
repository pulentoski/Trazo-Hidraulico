"""Punto de entrada FastAPI de Trazo Hidráulico."""
import logging
import re

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import get_settings
from app.core.ratelimit import RateLimitMiddleware
from app.routers import (analysis, auth as auth_router, catalog, demand, diagnosis, health, measurements, network,
                         orgs, orthophotos, projects, sig, trazo, wells)
from app.routers import summary as summary_router
from app.services import auth
from app.schemas.simulation import SimulationBlocked
from app.services.errors import Conflict, InvalidNetwork, NotFound, SimulationBlockedError

app = FastAPI(
    title="Trazo Hidráulico API",
    version="0.1.0",
    description="Diseño y simulación de redes de agua potable. Motor único: OWA-EPANET 2.3.5 (backend).",
    openapi_url="/api/openapi.json",
    docs_url="/api/docs",
    redoc_url=None,
    dependencies=[Depends(auth.authenticate)],
)

if not get_settings().cookie_secure:
    logging.getLogger("uvicorn.error").warning(
        "ADVERTENCIA: COOKIE_SECURE=false — la cookie de sesión viaja sin cifrar (modo HTTP por IP, solo pruebas). "
        "Publique con HTTPS y COOKIE_SECURE=true antes de usar datos reales.")

# Auditoría de importaciones y exportaciones (rutas con éxito): quién, qué y cuándo.
AUDIT_PATHS = [
    (re.compile(r"^/api/projects/([0-9a-f-]{36})/(export\.(inp|dxf|gpkg|trazo)|sig/export\.(xlsx|csv)|report\.html|"
                r"sectors/[^/]+/export|demand/projection\.xlsx|wells/[^/]+/report\.html|query/export)$"), "exportacion"),
    (re.compile(r"^/api/projects/([0-9a-f-]{36})/(sig/import/apply|clients/import|measurements/import|orthophotos)$"),
     "importacion"),
    (re.compile(r"^/api/projects/(import|import-excel|import-trazo)$"), "importacion"),
]


class AuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        path = request.url.path
        p = getattr(request.state, "principal", None)
        if p is None or response.status_code >= 400:
            return response
        for rx, action in AUDIT_PATHS:
            m = rx.match(path)
            if not m or (action == "importacion" and request.method != "POST"):
                continue
            from app.core.db import get_sessionmaker
            from app.models import Project

            with get_sessionmaker()() as session:
                pid = None
                org = p.org_id
                if m.group(1) and len(m.group(1)) == 36:
                    import uuid as _uuid

                    pid = _uuid.UUID(m.group(1))
                    proj = session.get(Project, pid)
                    org = proj.org_id if proj else org
                token = auth.current.set(p)
                try:
                    auth.audit(session, action, org_id=org, project_id=pid,
                               detail={"ruta": path.split("/api/projects/")[-1][:120], "metodo": request.method})
                    session.commit()
                finally:
                    auth.current.reset(token)
            break
        return response


app.add_middleware(AuditMiddleware)
app.add_middleware(RateLimitMiddleware)


@app.exception_handler(auth.AuthError)
def _auth_error(_: Request, exc: auth.AuthError) -> JSONResponse:
    return JSONResponse(status_code=exc.status, content={"detail": exc.detail, "code": exc.code})

for r in (health.router, auth_router.router, orgs.router, catalog.router, sig.router, trazo.router, projects.router,
          network.router, analysis.router, orthophotos.router, demand.router, wells.router, measurements.router,
          diagnosis.router, summary_router.router):
    app.include_router(r, prefix="/api")


@app.exception_handler(NotFound)
def _not_found(_: Request, exc: NotFound) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(Conflict)
def _conflict(_: Request, exc: Conflict) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.exception_handler(InvalidNetwork)
def _invalid(_: Request, exc: InvalidNetwork) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": exc.detail, "validation": exc.report.model_dump()})


@app.exception_handler(SimulationBlockedError)
def _blocked(_: Request, exc: SimulationBlockedError) -> JSONResponse:
    body = SimulationBlocked(model_version=exc.model_version, detail=str(exc), validation=exc.report)
    return JSONResponse(status_code=422, content=body.model_dump(mode="json"))
