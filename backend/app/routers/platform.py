"""Configuración de la plataforma: mapa base (key de Google Maps y Map ID) gestionado por el superadministrador."""
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.services import auth
from app.services import platform_settings as svc

router = APIRouter(tags=["plataforma"])
SessionDep = Annotated[Session, Depends(get_session)]


class MapsConfig(BaseModel):
    api_key: str | None = Field(None, description="Key de Google Maps (para cargar el mapa en el navegador)")
    map_id: str | None = None
    source: Literal["db", "none"] = Field(description="db = guardada desde Configuración; none = usar el respaldo "
                                                       "del frontend (VITE_GOOGLE_MAPS_API_KEY) si lo hay")


class MapsStatus(BaseModel):
    configured: bool
    key_hint: str | None = Field(None, description="Primeros y últimos 4 caracteres de la key")
    map_id: str | None
    updated_at: datetime | None
    updated_by: str | None
    encryption_ready: bool = Field(description="SETTINGS_SECRET_KEY definida en el servidor")
    unreadable: bool = Field(description="Hay una key guardada que no se puede descifrar (cambió la clave)")


class MapsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    api_key: str | None = Field(None, max_length=200, description="Nueva key (omitir para conservar la actual)")
    map_id: str | None = Field(None, max_length=100, description="Map ID (vacío lo borra; omitir lo conserva)")


@router.get("/maps/config", response_model=MapsConfig, summary="Key y Map ID del mapa base (usuarios con sesión)")
def maps_config(session: SessionDep) -> MapsConfig:
    auth.principal()
    key, map_id = svc.maps_config(session)
    return MapsConfig(api_key=key, map_id=map_id if key else None, source="db" if key else "none")


@router.get("/admin/maps", response_model=MapsStatus, summary="Estado del mapa base (superadministrador)")
def maps_status(session: SessionDep) -> MapsStatus:
    auth.require_superadmin()
    return MapsStatus(**svc.maps_status(session))


@router.put("/admin/maps", response_model=MapsStatus, summary="Guardar la key (cifrada) y el Map ID")
def maps_save(body: MapsUpdate, session: SessionDep) -> MapsStatus:
    p = auth.require_superadmin()
    sent = body.model_fields_set
    try:
        svc.save_maps(session, body.api_key or None, body.map_id, keep_key="api_key" not in sent or not body.api_key,
                      keep_map_id="map_id" not in sent, who=p.email)
    except svc.NotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except svc.SettingsError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    auth.audit(session, "plataforma.mapa_base", detail={"key": "actualizada" if "api_key" in sent and body.api_key else "sin cambio",
                                                        "map_id": body.map_id if "map_id" in sent else "sin cambio"})
    session.commit()
    return MapsStatus(**svc.maps_status(session))


@router.delete("/admin/maps", response_model=MapsStatus, summary="Borrar la key y el Map ID guardados")
def maps_delete(session: SessionDep) -> MapsStatus:
    p = auth.require_superadmin()
    svc.save_maps(session, None, None, keep_key=False, keep_map_id=False, who=p.email)
    auth.audit(session, "plataforma.mapa_base", detail={"key": "borrada"})
    session.commit()
    return MapsStatus(**svc.maps_status(session))
