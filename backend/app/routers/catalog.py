from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.hydraulic.version import engine_info
from app.repositories import catalog as catalog_repo
from app.schemas.catalog import CatalogPipeOut, DesignProfileOut
from app.schemas.network import ROUGHNESS_MEANING
from app.schemas.simulation import EngineInfo

router = APIRouter(tags=["catálogo y motor"])
SessionDep = Annotated[Session, Depends(get_session)]


@router.get("/catalog/pipes", response_model=list[CatalogPipeOut], summary="Catálogo de tuberías PVC y HDPE")
def list_pipes(session: SessionDep) -> list[CatalogPipeOut]:
    return [CatalogPipeOut.model_validate(p) for p in catalog_repo.list_pipes(session)]


@router.get("/design-profiles", response_model=list[DesignProfileOut], summary="Perfiles de criterios de diseño")
def list_profiles(session: SessionDep) -> list[DesignProfileOut]:
    return [DesignProfileOut.model_validate(p) for p in catalog_repo.list_profiles(session)]


@router.get("/engine", response_model=EngineInfo, summary="Versión verificada del motor hidráulico")
def get_engine() -> EngineInfo:
    return EngineInfo(**engine_info())


@router.get("/roughness-meaning", response_model=dict[str, str], summary="Significado de la rugosidad por fórmula")
def roughness_meaning() -> dict[str, str]:
    return ROUGHNESS_MEANING
