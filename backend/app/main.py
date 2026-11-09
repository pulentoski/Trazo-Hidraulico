"""Punto de entrada FastAPI de Trazo Hidráulico."""
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.ratelimit import RateLimitMiddleware
from app.routers import catalog, health, network, projects
from app.schemas.simulation import SimulationBlocked
from app.services.errors import Conflict, InvalidNetwork, NotFound, SimulationBlockedError

app = FastAPI(
    title="Trazo Hidráulico API",
    version="0.1.0",
    description="Diseño y simulación de redes de agua potable. Motor único: OWA-EPANET 2.3.5 (backend).",
    openapi_url="/api/openapi.json",
    docs_url="/api/docs",
    redoc_url=None,
)

app.add_middleware(RateLimitMiddleware)

for r in (health.router, catalog.router, projects.router, network.router):
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
