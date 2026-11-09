"""Punto de entrada FastAPI de Trazo Hidráulico."""
from fastapi import FastAPI

from app.routers import health

app = FastAPI(
    title="Trazo Hidráulico API",
    version="0.1.0",
    description="Diseño y simulación de redes de agua potable. Motor único: OWA-EPANET 2.3.5.",
    openapi_url="/api/openapi.json",
    docs_url="/api/docs",
    redoc_url=None,
)

app.include_router(health.router, prefix="/api")
