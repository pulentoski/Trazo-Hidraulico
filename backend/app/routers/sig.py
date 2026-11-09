"""SIG: planillas Excel/CSV, cuarteles de corta, consultas, búsqueda, grifos y exportaciones DXF/GeoPackage."""
import csv
import io
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_session
from app.models import SavedQuery
from app.schemas.sig import (FireResult, ImportApplyResult, ImportPreview, QueryDef, QueryElement, QueryRequest,
                             QueryResult, SavedQueryIn, SavedQueryOut, SearchHit, SectorsResult)
from app.services import sig_io
from app.services.errors import NotFound
from app.services.network import get_project_or_404, get_version_or_404, load_model
from app.sig import dxf, fire, gpkg, queries, sectors
from app.sig.excel import write_csv
from app.sig.spec import SHEET_BY_KEY
from app.sig.tables import model_rows

router = APIRouter(tags=["SIG"])
SessionDep = Annotated[Session, Depends(get_session)]
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
VersionQ = Annotated[int | None, Query(description="Número de versión (última si se omite)")]


def _attach(content: bytes, media: str, filename: str) -> Response:
    return Response(content=content, media_type=media, headers={"Content-Disposition": f'attachment; filename="{filename}"'})


def _read(file: UploadFile) -> bytes:
    max_mb = get_settings().max_xlsx_mb
    content = file.file.read(max_mb * 1024 * 1024 + 1)
    if len(content) > max_mb * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"El archivo supera {max_mb} MB")
    return content


def _bad(exc: Exception) -> HTTPException:
    return HTTPException(status_code=422, detail=str(exc))


# ── Planillas ──

@router.get("/sig/template.xlsx", response_class=Response, summary="Plantilla Excel vacía",
            responses={200: {"content": {XLSX: {}}}})
def template(session: SessionDep) -> Response:
    return _attach(sig_io.template(session), XLSX, "plantilla-trazo-hidraulico.xlsx")


@router.get("/projects/{project_id}/sig/export.xlsx", response_class=Response, responses={200: {"content": {XLSX: {}}}},
            summary="Exportar el proyecto completo a la planilla")
def export_xlsx(project_id: uuid.UUID, session: SessionDep, version: VersionQ = None) -> Response:
    data, name = sig_io.export_xlsx(session, get_project_or_404(session, project_id), version)
    return _attach(data, XLSX, name)


@router.get("/projects/{project_id}/sig/export.csv", response_class=Response,
            responses={200: {"content": {"text/csv": {}}}}, summary="Exportar una hoja como CSV")
def export_csv(project_id: uuid.UUID, session: SessionDep, sheet: Annotated[str, Query()],
               version: VersionQ = None) -> Response:
    project = get_project_or_404(session, project_id)
    rows = sig_io.rows_for(session, project, version, sheet)
    return _attach(write_csv(SHEET_BY_KEY[sheet], rows), "text/csv; charset=utf-8",
                   f"{sig_io.safe_name(project.name)}-{sheet}.csv")




def _import_kwargs(sheet, delete_missing, utm_zone, hemisphere) -> dict:
    return {"sheet": sheet, "delete_missing": delete_missing, "zone": utm_zone, "hemisphere": hemisphere}


@router.post("/projects/{project_id}/sig/import/preview", response_model=ImportPreview,
             summary="Vista previa de la importación (no modifica el proyecto)")
def import_preview(project_id: uuid.UUID, session: SessionDep,
                   file: Annotated[UploadFile, File(description="Planilla .xlsx o CSV de una hoja")],
                   sheet: Annotated[str | None, Form(description="Hoja del CSV (Nudos, Tramos, …)")] = None,
                   delete_missing: Annotated[bool, Form()] = False,
                   utm_zone: Annotated[int | None, Form(description="Huso UTM de Este/Norte")] = None,
                   hemisphere: Annotated[str, Form()] = "S") -> ImportPreview:
    project = get_project_or_404(session, project_id)
    try:
        return sig_io.preview(session, project, file.filename or "", _read(file),
                              **_import_kwargs(sheet, delete_missing, utm_zone, hemisphere))
    except sig_io.ImportFileError as exc:
        raise _bad(exc) from exc


@router.post("/projects/{project_id}/sig/import/apply", response_model=ImportApplyResult,
             summary="Aplicar la importación (todo o nada; crea una versión nueva)",
             responses={409: {"description": "La versión base no es la última"},
                        422: {"model": ImportApplyResult, "description": "Errores: no se aplicó nada"}})
def import_apply(project_id: uuid.UUID, session: SessionDep,
                 file: Annotated[UploadFile, File()],
                 sheet: Annotated[str | None, Form()] = None,
                 delete_missing: Annotated[bool, Form()] = False,
                 utm_zone: Annotated[int | None, Form()] = None,
                 hemisphere: Annotated[str, Form()] = "S",
                 base_version: Annotated[int | None, Form()] = None) -> ImportApplyResult | Response:
    project = get_project_or_404(session, project_id)
    try:
        res = sig_io.apply(session, project, file.filename or "", _read(file), base_version=base_version,
                           **_import_kwargs(sheet, delete_missing, utm_zone, hemisphere))
    except sig_io.ImportFileError as exc:
        raise _bad(exc) from exc
    if not res.preview.ok:
        return Response(status_code=422, content=res.model_dump_json(), media_type="application/json")
    return res


@router.post("/projects/import-excel", response_model=ImportApplyResult, status_code=status.HTTP_201_CREATED,
             summary="Crear un proyecto nuevo desde una planilla",
             responses={422: {"model": ImportApplyResult, "description": "Errores: no se creó el proyecto"}})
def create_from_excel(session: SessionDep, file: Annotated[UploadFile, File()],
                      name: Annotated[str | None, Form()] = None,
                      utm_zone: Annotated[int | None, Form()] = None,
                      hemisphere: Annotated[str, Form()] = "S") -> ImportApplyResult | Response:
    try:
        res = sig_io.create_from_excel(session, file.filename or "planilla.xlsx", _read(file), name=name,
                                       zone=utm_zone, hemisphere=hemisphere)
    except (sig_io.ImportFileError, ValueError) as exc:
        raise _bad(exc) from exc
    if not res.preview.ok:
        return Response(status_code=422, content=res.model_dump_json(), media_type="application/json")
    return res


# ── Cuarteles de corta ──

def _model(session: Session, project_id: uuid.UUID, version: int | None):
    project = get_project_or_404(session, project_id)
    v = get_version_or_404(session, project, version)
    return project, v, load_model(session, v)


@router.get("/projects/{project_id}/sectors", response_model=SectorsResult, summary="Cuarteles de corta")
def get_sectors(project_id: uuid.UUID, session: SessionDep, version: VersionQ = None) -> SectorsResult:
    project, v, model = _model(session, project_id, version)
    return sectors.compute_sectors(model, project_id=str(project.id), version=v.number)


@router.get("/projects/{project_id}/sectors/{sector_id}/export", response_class=Response,
            responses={200: {"content": {XLSX: {}, "text/csv": {}}}},
            summary="Lista exportable de un cuartel: válvulas a cerrar y clientes sin agua")
def export_sector(project_id: uuid.UUID, sector_id: str, session: SessionDep, version: VersionQ = None,
                  fmt: Annotated[str, Query(pattern="^(csv|xlsx)$")] = "xlsx") -> Response:
    project, v, model = _model(session, project_id, version)
    res = sectors.compute_sectors(model)
    s = next((x for x in res.sectors if x.id == sector_id), None)
    if s is None:
        raise NotFound(f"Cuartel {sector_id} no encontrado")
    clients = {c.id: c for c in model.network.clients()}
    lines: list[list] = [["Cuartel", s.id], ["Metros de red", s.length_m], ["Clientes afectados", s.affected_clients], [],
                         ["Válvulas a cerrar"]]
    shut = {x.id: x for x in model.network.shutoffs()}
    lines.append(["ID", "Nombre", "Tramo", "Tipo", "Estado actual"])
    for vid in s.valves:
        p = shut[vid].properties
        lines.append([vid, p.name or "", p.link, p.valve_type or "", "abierta" if p.state == "open" else "cerrada"])
    lines += [[], ["Clientes sin agua"], ["ID", "N° cliente", "Nombre", "Dirección", "Ruta", "N° medidor", "Nudo",
                                        "Afectación"]]
    for cid, kind in [(c, "en el cuartel") for c in s.clients] + [(c, "aguas abajo") for c in s.downstream_clients]:
        p = clients[cid].properties
        lines.append([cid, p.client_number or "", p.name or "", p.address or "", p.route or "", p.meter_number or "",
                      p.node, kind])
    base = f"{sig_io.safe_name(project.name)}-cuartel-{s.id}"
    if fmt == "csv":
        buf = io.StringIO()
        csv.writer(buf, delimiter=";").writerows(lines)
        return _attach(("﻿" + buf.getvalue()).encode(), "text/csv; charset=utf-8", base + ".csv")
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = s.id
    for row in lines:
        ws.append(row)
    out = io.BytesIO()
    wb.save(out)
    return _attach(out.getvalue(), XLSX, base + ".xlsx")


# ── Consultas ──

@router.get("/sig/query-fields", response_model=list[QueryElement], summary="Tipos de elemento y campos consultables")
def query_fields(session: SessionDep) -> list[QueryElement]:
    sig_io._catalog(session)
    return queries.elements()


@router.post("/projects/{project_id}/query", response_model=QueryResult, summary="Ejecutar una consulta")
def run_query(project_id: uuid.UUID, body: QueryRequest, session: SessionDep) -> QueryResult:
    project, v, model = _model(session, project_id, body.model_version)
    sig_io._catalog(session)
    try:
        return queries.run_query(model, body.element, body.where, srid=project.length_srid, version=v.number)
    except queries.QueryError as exc:
        raise _bad(exc) from exc


@router.post("/projects/{project_id}/query/export", response_class=Response,
             responses={200: {"content": {XLSX: {}, "text/csv": {}}}},
             summary="Exportar los resultados de una consulta (Excel con el formato de la plantilla, o CSV)")
def export_query(project_id: uuid.UUID, body: QueryRequest, session: SessionDep,
                 fmt: Annotated[str, Query(pattern="^(csv|xlsx)$")] = "xlsx") -> Response:
    project, v, model = _model(session, project_id, body.model_version)
    sig_io._catalog(session)
    try:
        res = queries.run_query(model, body.element, body.where, srid=project.length_srid, version=v.number)
    except queries.QueryError as exc:
        raise _bad(exc) from exc
    ids = {r["id"] for r in res.rows}
    rows = [r for r in model_rows(model, project.length_srid)[body.element] if r.id in ids]
    name = f"{sig_io.safe_name(project.name)}-consulta-{body.element}"
    if fmt == "csv":
        return _attach(write_csv(SHEET_BY_KEY[body.element], rows), "text/csv; charset=utf-8", name + ".csv")
    return _attach(sig_io.export_rows_xlsx(session, project, body.element, rows), XLSX, name + ".xlsx")


@router.get("/projects/{project_id}/search", response_model=list[SearchHit],
            summary="Búsqueda rápida por ID, nombre, dirección o N° de medidor")
def search(project_id: uuid.UUID, session: SessionDep, q: Annotated[str, Query(min_length=1, max_length=100)],
           version: VersionQ = None) -> list[SearchHit]:
    project, _v, model = _model(session, project_id, version)
    return queries.search(model, q, srid=project.length_srid)


@router.get("/projects/{project_id}/queries", response_model=list[SavedQueryOut], summary="Consultas guardadas")
def list_saved(project_id: uuid.UUID, session: SessionDep) -> list[SavedQueryOut]:
    get_project_or_404(session, project_id)
    items = session.scalars(select(SavedQuery).where(SavedQuery.project_id == project_id).order_by(SavedQuery.name))
    return [SavedQueryOut(id=x.id, name=x.name, definition=QueryDef.model_validate(x.definition),
                          created_at=x.created_at) for x in items]


@router.post("/projects/{project_id}/queries", response_model=SavedQueryOut, status_code=201,
             summary="Guardar una consulta (reemplaza la del mismo nombre)")
def save_query(project_id: uuid.UUID, body: SavedQueryIn, session: SessionDep) -> SavedQueryOut:
    get_project_or_404(session, project_id)
    if body.definition.element not in SHEET_BY_KEY:
        raise HTTPException(status_code=422, detail="Tipo de elemento desconocido")
    item = session.scalars(select(SavedQuery).where(SavedQuery.project_id == project_id,
                                                    SavedQuery.name == body.name)).first()
    if item is None:
        item = SavedQuery(project_id=project_id, name=body.name, definition=body.definition.model_dump(mode="json"))
        session.add(item)
    else:
        item.definition = body.definition.model_dump(mode="json")
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail="Ya existe una consulta con ese nombre") from exc
    session.refresh(item)
    return SavedQueryOut(id=item.id, name=item.name, definition=body.definition, created_at=item.created_at)


@router.delete("/projects/{project_id}/queries/{query_id}", status_code=204, summary="Eliminar una consulta guardada")
def delete_query(project_id: uuid.UUID, query_id: int, session: SessionDep) -> Response:
    item = session.get(SavedQuery, query_id)
    if item is None or item.project_id != project_id:
        raise NotFound("Consulta no encontrada")
    session.delete(item)
    session.commit()
    return Response(status_code=204)


# ── Grifos ──

@router.post("/projects/{project_id}/hydrants/fire", response_model=FireResult,
             summary="Escenario de incendio: presión residual y caudal disponible por grifo")
def fire_scenario(project_id: uuid.UUID, session: SessionDep, version: VersionQ = None,
                  hydrant: Annotated[str | None, Query(description="ID de un grifo (todos si se omite)")] = None
                  ) -> FireResult:
    from app.services.errors import SimulationBlockedError
    from app.services.simulation import validation_for

    project, v, model = _model(session, project_id, version)
    rep = validation_for(session, project, model)
    if not rep.ok:
        raise SimulationBlockedError(v.number, rep)
    return FireResult(project_id=str(project.id), model_version=v.number,
                      hydrants=fire.assess(model, {hydrant} if hydrant else None))


# ── Exportaciones GIS/CAD ──

@router.get("/projects/{project_id}/export.dxf", response_class=Response,
            responses={200: {"content": {"application/dxf": {}}}}, summary="DXF por capas (UTM)")
def export_dxf(project_id: uuid.UUID, session: SessionDep, version: VersionQ = None) -> Response:
    project, v, model = _model(session, project_id, version)
    return _attach(dxf.write_dxf(model, project.length_srid), "application/dxf",
                   f"{sig_io.safe_name(project.name)}-v{v.number}.dxf")


@router.get("/projects/{project_id}/export.gpkg", response_class=Response,
            responses={200: {"content": {"application/geopackage+sqlite3": {}}}}, summary="GeoPackage para QGIS")
def export_gpkg(project_id: uuid.UUID, session: SessionDep, version: VersionQ = None) -> Response:
    project, v, model = _model(session, project_id, version)
    return _attach(gpkg.write_gpkg(model, project.length_srid), "application/geopackage+sqlite3",
                   f"{sig_io.safe_name(project.name)}-v{v.number}.gpkg")
