"""Registro de funcionamiento: mediciones, importación y comparación con el modelo."""
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.schemas.measurement import (MeasureCompareResult, MeasurementImportResult, MeasurementIn, MeasurementOut,
                                     MonitoringSettings)
from app.services import measurements as svc
from app.services.errors import SimulationBlockedError
from app.services.network import get_project_or_404, get_version_or_404, load_model
from app.services.simulation import simulate_version

router = APIRouter(prefix="/projects/{project_id}", tags=["registro de funcionamiento"])
SessionDep = Annotated[Session, Depends(get_session)]
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class IdList(BaseModel):
    ids: list[int]


@router.get("/measurements", response_model=list[MeasurementOut], summary="Mediciones registradas")
def list_measurements(project_id: uuid.UUID, session: SessionDep,
                      element_type: Annotated[str | None, Query()] = None,
                      element_id: Annotated[str | None, Query()] = None) -> list[MeasurementOut]:
    project = get_project_or_404(session, project_id)
    return [svc.out(m) for m in svc.list_for(session, project, element_type, element_id)]


@router.post("/measurements", response_model=list[MeasurementOut], status_code=201, summary="Agregar mediciones")
def add_measurements(project_id: uuid.UUID, body: list[MeasurementIn], session: SessionDep) -> list[MeasurementOut]:
    project = get_project_or_404(session, project_id)
    return [svc.out(m) for m in svc.add(session, project, body)]


@router.post("/measurements/delete", summary="Eliminar mediciones")
def delete_measurements(project_id: uuid.UUID, body: IdList, session: SessionDep) -> dict:
    return {"deleted": svc.remove(session, get_project_or_404(session, project_id), body.ids)}


@router.get("/measurements/template.xlsx", response_class=Response, responses={200: {"content": {XLSX: {}}}},
            summary="Plantilla de mediciones")
def template(project_id: uuid.UUID, session: SessionDep) -> Response:
    get_project_or_404(session, project_id)
    return Response(content=svc.template_xlsx(), media_type=XLSX,
                    headers={"Content-Disposition": 'attachment; filename="plantilla-mediciones.xlsx"'})


@router.post("/measurements/import", response_model=MeasurementImportResult, summary="Importar mediciones (todo o nada)",
             responses={422: {"model": MeasurementImportResult}})
def import_measurements(project_id: uuid.UUID, session: SessionDep, file: Annotated[UploadFile, File()]):
    project = get_project_or_404(session, project_id)
    content = file.file.read(10 * 1024 * 1024 + 1)
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="El archivo supera 10 MB")
    items, errors = svc.read_file(file.filename or "", content)
    if errors or not items:
        body = MeasurementImportResult(created=0, errors=errors or ["El archivo no tiene mediciones."])
        return Response(status_code=422, content=body.model_dump_json(), media_type="application/json")
    return MeasurementImportResult(created=len(svc.add(session, project, items)), errors=[])


@router.get("/monitoring", response_model=MonitoringSettings, summary="Tolerancias de comparación")
def get_settings(project_id: uuid.UUID, session: SessionDep) -> MonitoringSettings:
    return svc.settings(get_project_or_404(session, project_id))


@router.put("/monitoring", response_model=MonitoringSettings, summary="Editar tolerancias de comparación")
def put_settings(project_id: uuid.UUID, body: MonitoringSettings, session: SessionDep) -> MonitoringSettings:
    project = get_project_or_404(session, project_id)
    project.monitoring = body.model_dump()
    session.commit()
    return body


@router.get("/measurements/compare", response_model=MeasureCompareResult, summary="Comparación modelo contra medición")
def compare(project_id: uuid.UUID, session: SessionDep, version: Annotated[int | None, Query()] = None) -> MeasureCompareResult:
    project = get_project_or_404(session, project_id)
    v = get_version_or_404(session, project, version)
    model = load_model(session, v)
    try:
        sim = simulate_version(session, project, v.number)
    except SimulationBlockedError:
        sim = None
    cfg = svc.settings(project)
    return MeasureCompareResult(project_id=str(project.id), model_version=v.number, settings=cfg,
                         series=svc.compare(model, sim, svc.list_for(session, project), cfg))
