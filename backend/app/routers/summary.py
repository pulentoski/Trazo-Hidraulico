"""Panel general del proyecto («Resumen»), su configuración, exportaciones y el registro de pérdidas."""
import json
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.schemas.summary import LeakEventIn, LeakEventOut, LeakImportResult, SummaryResult, SummarySettings
from app.services import summary as svc
from app.services import summary_export
from app.services.network import get_project_or_404, get_version_or_404, load_model
from app.services.sig_io import safe_name

router = APIRouter(prefix="/projects/{project_id}", tags=["resumen"])
SessionDep = Annotated[Session, Depends(get_session)]
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
VersionQ = Annotated[int | None, Query(description="Versión (vacío = la última)")]
ScenarioQ = Annotated[str, Query(description="«modelo» (última simulación), «normal» o un escenario de llaves")]
PeriodQ = Annotated[int | None, Query(ge=0, description="Periodo de reporte (vacío = hora punta)")]


class IdList(BaseModel):
    ids: list[int]


@router.get("/summary", response_model=SummaryResult, summary="Panel general del proyecto")
def get_summary(project_id: uuid.UUID, session: SessionDep, version: VersionQ = None,
                scenario: ScenarioQ = svc.MODEL_SCENARIO, period: PeriodQ = None) -> SummaryResult:
    return svc.build(session, get_project_or_404(session, project_id), version, scenario, period)


@router.get("/summary.xlsx", response_class=Response, responses={200: {"content": {XLSX: {}}}},
            summary="Exportar el resumen a Excel")
def summary_xlsx(project_id: uuid.UUID, session: SessionDep, version: VersionQ = None,
                 scenario: ScenarioQ = svc.MODEL_SCENARIO, period: PeriodQ = None) -> Response:
    project = get_project_or_404(session, project_id)
    data = summary_export.to_xlsx(svc.build(session, project, version, scenario, period), project.name)
    return Response(content=data, media_type=XLSX,
                    headers={"Content-Disposition": f'attachment; filename="{safe_name(project.name)}-resumen.xlsx"'})


@router.get("/summary.html", response_class=Response, responses={200: {"content": {"text/html": {}}}},
            summary="Resumen imprimible (HTML; imprimir a PDF desde el navegador)")
def summary_html(project_id: uuid.UUID, session: SessionDep, version: VersionQ = None,
                 scenario: ScenarioQ = svc.MODEL_SCENARIO, period: PeriodQ = None) -> Response:
    project = get_project_or_404(session, project_id)
    page = summary_export.to_html(svc.build(session, project, version, scenario, period), project.name)
    return Response(content=page, media_type="text/html; charset=utf-8")


@router.get("/summary/area.geojson", response_class=Response, responses={200: {"content": {"application/geo+json": {}}}},
            summary="Área operacional (GeoJSON, WGS84)")
def area_geojson(project_id: uuid.UUID, session: SessionDep, version: VersionQ = None) -> Response:
    project = get_project_or_404(session, project_id)
    res = svc.build(session, project, version)
    return Response(content=json.dumps(svc.area_geojson(res, project.name), ensure_ascii=False),
                    media_type="application/geo+json",
                    headers={"Content-Disposition": f'attachment; filename="{safe_name(project.name)}-area-operacional.geojson"'})


@router.get("/summary/zones.geojson", response_class=Response, responses={200: {"content": {"application/geo+json": {}}}},
            summary="Zonas por presión (GeoJSON, WGS84)")
def zones_geojson(project_id: uuid.UUID, session: SessionDep, version: VersionQ = None,
                  scenario: ScenarioQ = svc.MODEL_SCENARIO, period: PeriodQ = None) -> Response:
    project = get_project_or_404(session, project_id)
    res = svc.build(session, project, version, scenario, period)
    return Response(content=json.dumps(svc.zones_geojson(res), ensure_ascii=False), media_type="application/geo+json",
                    headers={"Content-Disposition": f'attachment; filename="{safe_name(project.name)}-zonas-presion.geojson"'})


@router.get("/summary/settings", response_model=SummarySettings, summary="Configuración del resumen")
def get_settings(project_id: uuid.UUID, session: SessionDep) -> SummarySettings:
    return svc.settings_of(get_project_or_404(session, project_id))


@router.put("/summary/settings", response_model=SummarySettings, summary="Editar la configuración del resumen")
def put_settings(project_id: uuid.UUID, body: SummarySettings, session: SessionDep) -> SummarySettings:
    return svc.save_settings(session, get_project_or_404(session, project_id), body)


@router.delete("/summary/settings", response_model=SummarySettings, summary="Volver a los valores sugeridos")
def reset_settings(project_id: uuid.UUID, session: SessionDep) -> SummarySettings:
    project = get_project_or_404(session, project_id)
    project.summary_settings = None
    session.commit()
    return svc.settings_of(project)


@router.get("/leaks", response_model=list[LeakEventOut], summary="Eventos de pérdidas (fugas, roturas, reparaciones)")
def list_leaks(project_id: uuid.UUID, session: SessionDep) -> list[LeakEventOut]:
    return [svc.leak_out(e) for e in svc.list_leaks(session, get_project_or_404(session, project_id))]


def _links(session: Session, project) -> set[str]:
    return {lk.id for lk in load_model(session, get_version_or_404(session, project, None)).network.links()}


@router.post("/leaks", response_model=list[LeakEventOut], status_code=201, summary="Registrar eventos de pérdidas")
def add_leaks(project_id: uuid.UUID, body: list[LeakEventIn], session: SessionDep) -> list[LeakEventOut]:
    project = get_project_or_404(session, project_id)
    known = _links(session, project)
    missing = sorted({b.link_id for b in body} - known)
    if missing:
        raise HTTPException(status_code=422, detail=f"Tramos inexistentes en el modelo: {', '.join(missing)}")
    return [svc.leak_out(e) for e in svc.add_leaks(session, project, body)]


@router.post("/leaks/delete", summary="Eliminar eventos de pérdidas")
def delete_leaks(project_id: uuid.UUID, body: IdList, session: SessionDep) -> dict:
    return {"deleted": svc.delete_leaks(session, get_project_or_404(session, project_id), body.ids)}


@router.get("/leaks/template.xlsx", response_class=Response, responses={200: {"content": {XLSX: {}}}},
            summary="Plantilla de eventos de pérdidas")
def leaks_template(project_id: uuid.UUID, session: SessionDep) -> Response:
    get_project_or_404(session, project_id)
    return Response(content=svc.leaks_template(), media_type=XLSX,
                    headers={"Content-Disposition": 'attachment; filename="plantilla-perdidas.xlsx"'})


@router.post("/leaks/import", response_model=LeakImportResult, summary="Importar eventos desde Excel o CSV (todo o nada)",
             responses={422: {"model": LeakImportResult}})
def import_leaks(project_id: uuid.UUID, session: SessionDep, file: Annotated[UploadFile, File()]):
    project = get_project_or_404(session, project_id)
    content = file.file.read(5 * 1024 * 1024 + 1)
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="El archivo supera 5 MB")
    items, errors = svc.read_leak_file(file.filename or "", content, _links(session, project))
    if errors or not items:
        body = LeakImportResult(created=0, errors=errors or ["El archivo no tiene eventos."])
        return Response(status_code=422, content=body.model_dump_json(), media_type="application/json")
    return LeakImportResult(created=len(svc.add_leaks(session, project, items)), errors=[])
