"""Página «Gestión» de un proyecto: pestañas de indicadores, registros de operación, metas e informe mensual."""
import uuid
from datetime import date, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.schemas.gestion import (CapacityResult, CompleteTask, Filters, GestionSettings, RecordImportPreview, MaintenanceLogOut,
                                 RecordKind, RecordList, RecordSpec, Tab, TabResult)
from app.schemas.simulation import SimulationBlocked
from app.services import auth
from app.services import gestion as svc
from app.services import gestion_capacity, gestion_report
from app.services import gestion_records as rec
from app.services.errors import NotFound
from app.services.network import get_project_or_404
from app.services.sig_io import safe_name

router = APIRouter(prefix="/projects/{project_id}/gestion", tags=["gestión"])
SessionDep = Annotated[Session, Depends(get_session)]
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
CSV = "text/csv; charset=utf-8"
StartQ = Annotated[date | None, Query(alias="desde", description="Inicio del período (vacío = 12 meses hasta el último dato)")]
EndQ = Annotated[date | None, Query(alias="hasta", description="Fin del período")]
SectorQ = Annotated[str | None, Query(alias="sector", max_length=60)]
RouteQ = Annotated[str | None, Query(alias="ruta", max_length=40)]
BLOCKED = {409: {"model": SimulationBlocked, "description": "La red tiene errores bloqueantes"}}


class IdList(BaseModel):
    ids: list[int]


def _period(session: Session, project, start: date | None, end: date | None) -> tuple[date, date]:
    if start and end:
        return start, end
    f = svc.filters(session, project)
    last = end or f.data_end or date.today()
    first = start or (date(last.year - 1, last.month, 1) + timedelta(days=32)).replace(day=1)
    return first, last


def _who() -> str | None:
    p = auth.current.get()
    return p.email if p and not p.system else None


def _audit(session: Session, project, action: str, detail: dict) -> None:
    auth.audit(session, f"gestion.{action}", org_id=project.org_id, project_id=project.id, detail=detail)


# ── Filtros, metas y pestañas ──

@router.get("/filters", response_model=Filters, summary="Sectores, rutas y rango de fechas con datos")
def get_filters(project_id: uuid.UUID, session: SessionDep) -> Filters:
    return svc.filters(session, get_project_or_404(session, project_id))


@router.get("/settings", response_model=GestionSettings, summary="Metas e indicadores del proyecto")
def get_settings(project_id: uuid.UUID, session: SessionDep) -> GestionSettings:
    return svc.settings_of(get_project_or_404(session, project_id))


@router.put("/settings", response_model=GestionSettings, summary="Editar metas e indicadores")
def put_settings(project_id: uuid.UUID, body: GestionSettings, session: SessionDep) -> GestionSettings:
    project = get_project_or_404(session, project_id)
    _audit(session, project, "metas", {"metas": len(body.targets)})
    return svc.save_settings(session, project, body)


@router.delete("/settings", response_model=GestionSettings, summary="Volver a las metas sugeridas")
def reset_settings(project_id: uuid.UUID, session: SessionDep) -> GestionSettings:
    project = get_project_or_404(session, project_id)
    project.gestion_settings = None
    session.commit()
    return svc.settings_of(project)


@router.get("/capacity", response_model=CapacityResult, responses=BLOCKED,
            summary="Capacidad remanente: clientes nuevos que caben manteniendo la presión mínima")
def capacity(project_id: uuid.UUID, session: SessionDep) -> CapacityResult:
    project = get_project_or_404(session, project_id)
    try:
        return gestion_capacity.for_project(session, project, svc.settings_of(project))
    except gestion_capacity.CapacityError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/tabs/{tab}", response_model=TabResult, summary="Indicadores, gráficos y tablas de una pestaña")
def get_tab(project_id: uuid.UUID, tab: Tab, session: SessionDep, start: StartQ = None, end: EndQ = None,
            sector: SectorQ = None, route: RouteQ = None) -> TabResult:
    project = get_project_or_404(session, project_id)
    a, b = _period(session, project, start, end)
    cap = None
    if tab == "planificacion":
        try:
            cap = gestion_capacity.for_project(session, project, svc.settings_of(project))
        except Exception:  # noqa: BLE001 — sin simulación: la pestaña muestra el resto
            cap = None
    return svc.build(session, project, tab, a, b, sector, route, capacity=cap)


@router.get("/tabs/{tab}/tables/{key}.{fmt}", response_class=Response,
            responses={200: {"content": {XLSX: {}, "text/csv": {}}}}, summary="Exportar una tabla de detalle (Excel o CSV)")
def export_table(project_id: uuid.UUID, tab: Tab, key: str, fmt: str, session: SessionDep, start: StartQ = None,
                 end: EndQ = None, sector: SectorQ = None, route: RouteQ = None) -> Response:
    if fmt not in ("xlsx", "csv"):
        raise HTTPException(status_code=404, detail="Formato desconocido (xlsx o csv)")
    project = get_project_or_404(session, project_id)
    a, b = _period(session, project, start, end)
    cap = None
    if tab == "planificacion" and key == "capacidad":
        cap = gestion_capacity.for_project(session, project, svc.settings_of(project))
    res = svc.build(session, project, tab, a, b, sector, route, capacity=cap)
    t = svc.table_of(res, key)
    if t is None:
        raise HTTPException(status_code=404, detail=f"Tabla «{key}» no encontrada en la pestaña")
    name = f"{safe_name(project.name)}-{tab}-{key}"
    if fmt == "csv":
        return Response(content=svc.table_csv(t), media_type=CSV,
                        headers={"Content-Disposition": f'attachment; filename="{name}.csv"'})
    return Response(content=svc.table_xlsx(t, project.name, res), media_type=XLSX,
                    headers={"Content-Disposition": f'attachment; filename="{name}.xlsx"'})


@router.get("/report.html", response_class=Response, responses={200: {"content": {"text/html": {}}}},
            summary="Informe mensual imprimible (HTML)")
def report_html(project_id: uuid.UUID, session: SessionDep, start: StartQ = None, end: EndQ = None,
                sector: SectorQ = None, route: RouteQ = None) -> Response:
    project = get_project_or_404(session, project_id)
    a, b = _period(session, project, start, end)
    tabs = gestion_report.build_all(session, project, a, b, sector, route)
    version = svc.filters(session, project).model_version
    return Response(content=gestion_report.to_html(project, tabs, version), media_type="text/html; charset=utf-8")


@router.get("/report.xlsx", response_class=Response, responses={200: {"content": {XLSX: {}}}},
            summary="Informe mensual (Excel)")
def report_xlsx(project_id: uuid.UUID, session: SessionDep, start: StartQ = None, end: EndQ = None,
                sector: SectorQ = None, route: RouteQ = None) -> Response:
    project = get_project_or_404(session, project_id)
    a, b = _period(session, project, start, end)
    tabs = gestion_report.build_all(session, project, a, b, sector, route)
    version = svc.filters(session, project).model_version
    return Response(content=gestion_report.to_xlsx(project, tabs, version), media_type=XLSX,
                    headers={"Content-Disposition": f'attachment; filename="{safe_name(project.name)}-informe-{b.strftime("%Y-%m")}.xlsx"'})


# ── Registros ──

@router.get("/records", response_model=list[RecordSpec], summary="Especificación de los registros (campos y ayudas)")
def record_specs(project_id: uuid.UUID, session: SessionDep) -> list[RecordSpec]:
    get_project_or_404(session, project_id)
    return [rec.spec_out(s) for s in rec.SPECS.values()]


@router.get("/records/{kind}", response_model=RecordList, summary="Filas de un registro")
def list_records(project_id: uuid.UUID, kind: RecordKind, session: SessionDep, start: StartQ = None,
                 end: EndQ = None) -> RecordList:
    project = get_project_or_404(session, project_id)
    spec = rec.SPECS[kind]
    return RecordList(kind=kind, rows=[rec.row_out(spec, r) for r in rec.list_rows(session, project, kind, start, end)])


def _validated(session: Session, project, kind: str, body: list[dict[str, Any]]) -> list[dict[str, Any]]:
    spec = rec.SPECS[kind]
    ctx = rec.context(session, project)
    items, errors = [], []
    for n, raw in enumerate(body, start=1):
        vals, err = rec.validate(spec, raw, ctx)
        if err:
            errors.append({"row": n, "errors": err})
        items.append(vals)
    if errors:
        raise HTTPException(status_code=422, detail={"message": "Hay filas con errores", "rows": errors})
    return items


@router.post("/records/{kind}", response_model=RecordList, status_code=201, summary="Agregar filas a un registro")
def add_records(project_id: uuid.UUID, kind: RecordKind, body: list[dict[str, Any]], session: SessionDep) -> RecordList:
    project = get_project_or_404(session, project_id)
    if not body:
        raise HTTPException(status_code=422, detail="Sin filas")
    items = _validated(session, project, kind, body)
    _, _, rows = rec.create(session, project, kind, items, _who())
    _audit(session, project, f"registro.{kind}", {"filas": len(rows), "accion": "agregar"})
    session.commit()
    spec = rec.SPECS[kind]
    return RecordList(kind=kind, rows=[rec.row_out(spec, r) for r in rows])


@router.put("/records/{kind}/{rid}", response_model=RecordList, summary="Editar una fila")
def edit_record(project_id: uuid.UUID, kind: RecordKind, rid: int, body: dict[str, Any], session: SessionDep) -> RecordList:
    project = get_project_or_404(session, project_id)
    items = _validated(session, project, kind, [body])
    r = rec.update(session, project, kind, rid, items[0])
    if r is None:
        raise NotFound("Fila no encontrada")
    _audit(session, project, f"registro.{kind}", {"id": rid, "accion": "editar"})
    session.commit()
    return RecordList(kind=kind, rows=[rec.row_out(rec.SPECS[kind], r)])


@router.post("/records/{kind}/delete", summary="Eliminar filas")
def delete_records(project_id: uuid.UUID, kind: RecordKind, body: IdList, session: SessionDep) -> dict:
    project = get_project_or_404(session, project_id)
    n = rec.remove(session, project, kind, body.ids)
    _audit(session, project, f"registro.{kind}", {"filas": n, "accion": "eliminar"})
    session.commit()
    return {"deleted": n}


@router.get("/records/{kind}/template.xlsx", response_class=Response, responses={200: {"content": {XLSX: {}}}},
            summary="Plantilla Excel del registro")
def record_template(project_id: uuid.UUID, kind: RecordKind, session: SessionDep) -> Response:
    get_project_or_404(session, project_id)
    return Response(content=rec.template(kind), media_type=XLSX,
                    headers={"Content-Disposition": f'attachment; filename="plantilla-{kind}.xlsx"'})


@router.get("/records/{kind}/export.{fmt}", response_class=Response,
            responses={200: {"content": {XLSX: {}, "text/csv": {}}}}, summary="Exportar el registro (Excel o CSV)")
def record_export(project_id: uuid.UUID, kind: RecordKind, fmt: str, session: SessionDep, start: StartQ = None,
                  end: EndQ = None) -> Response:
    if fmt not in ("xlsx", "csv"):
        raise HTTPException(status_code=404, detail="Formato desconocido (xlsx o csv)")
    project = get_project_or_404(session, project_id)
    spec = rec.SPECS[kind]
    rows = [rec.row_out(spec, r) for r in rec.list_rows(session, project, kind, start, end)]
    name = f"{safe_name(project.name)}-{kind}"
    if fmt == "csv":
        return Response(content=rec.export_csv(kind, rows), media_type=CSV,
                        headers={"Content-Disposition": f'attachment; filename="{name}.csv"'})
    return Response(content=rec.export_xlsx(kind, rows), media_type=XLSX,
                    headers={"Content-Disposition": f'attachment; filename="{name}.xlsx"'})


@router.post("/records/{kind}/import", response_model=RecordImportPreview, summary="Importar desde Excel o CSV: vista previa o aplicación",
             responses={422: {"model": RecordImportPreview}})
def import_records(project_id: uuid.UUID, kind: RecordKind, session: SessionDep, file: Annotated[UploadFile, File()],
                   apply: Annotated[bool, Query(description="false = solo vista previa con errores por fila")] = False,
                   only_valid: Annotated[bool, Query(description="Al aplicar, importar solo las filas válidas")] = False):
    project = get_project_or_404(session, project_id)
    content = file.file.read(10 * 1024 * 1024 + 1)
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="El archivo supera 10 MB")
    spec = rec.SPECS[kind]
    try:
        parsed = rec.parse(spec, rec.read_table(file.filename or "", content, spec.sheet), rec.context(session, project))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    pv = rec.preview(spec, parsed)
    if not apply:
        return pv
    if pv.invalid and not only_valid:
        return Response(status_code=422, content=pv.model_dump_json(), media_type="application/json")
    good = [vals for _, vals, err in parsed if not err]
    if not good:
        return Response(status_code=422, content=pv.model_dump_json(), media_type="application/json")
    pv.created, pv.updated, _ = rec.create(session, project, kind, good, _who())
    pv.applied = True
    _audit(session, project, f"registro.{kind}", {"filas": len(good), "accion": "importar", "archivo": (file.filename or "")[:80]})
    session.commit()
    return pv


@router.post("/records/mantenciones/{rid}/complete", response_model=RecordList, summary="Cumplir una mantención")
def complete_task(project_id: uuid.UUID, rid: int, body: CompleteTask, session: SessionDep) -> RecordList:
    project = get_project_or_404(session, project_id)
    r = rec.complete(session, project, rid, body.done_on, body.by or _who(), body.note)
    if r is None:
        raise NotFound("Mantención no encontrada")
    _audit(session, project, "registro.mantenciones", {"id": rid, "accion": "cumplir", "fecha": body.done_on.isoformat()})
    session.commit()
    return RecordList(kind="mantenciones", rows=[rec.row_out(rec.SPECS["mantenciones"], r)])


@router.get("/records/mantenciones/logs", response_model=list[MaintenanceLogOut], summary="Registro de cumplimiento")
def maintenance_logs(project_id: uuid.UUID, session: SessionDep,
                     task_id: Annotated[int | None, Query()] = None) -> list[MaintenanceLogOut]:
    project = get_project_or_404(session, project_id)
    return [MaintenanceLogOut(id=x.id, task_id=x.task_id, done_on=x.done_on, scheduled_for=x.scheduled_for, by=x.by,
                              note=x.note, created_at=x.created_at) for x in rec.logs(session, project, task_id)]
