"""Planillas: plantilla, exportación (Excel/CSV) e importación en dos pasos (vista previa → aplicar)."""
from __future__ import annotations

import io
import re
import uuid

from sqlalchemy.orm import Session

from app.services.auth import new_project_org

from app.core.config import get_settings
from app.models import Project
from app.repositories import catalog as catalog_repo
from app.repositories import projects as projects_repo
from app.schemas.network import HydraulicOptions, NetworkModel
from app.schemas.sig import ImportApplyResult, ImportPreview
from app.services.errors import Conflict, NotFound
from app.services.network import create_version, get_version_or_404, load_model, prepare_network
from app.services.projects import _check_srid
from app.sig import excel
from app.sig.importer import CatalogItem, ImportOptions, Outcome, run_import
from app.sig.spec import SHEET_BY_KEY, SHEET_BY_NAME, norm, with_materials
from app.sig.tables import Row, model_rows, model_sheet_rows


class ImportFileError(ValueError):
    pass


def zone_label(srid: int) -> str:
    if 32701 <= srid <= 32760:
        return f"UTM {srid - 32700}S (EPSG:{srid})"
    if 32601 <= srid <= 32660:
        return f"UTM {srid - 32600}N (EPSG:{srid})"
    return f"EPSG:{srid}"


def utm_srid(zone: int | None, hemisphere: str, default: int) -> int:
    if zone is None:
        return default
    if not 1 <= zone <= 60:
        raise ImportFileError("El huso UTM debe estar entre 1 y 60.")
    return (32700 if hemisphere.upper().startswith("S") else 32600) + zone


def _catalog(session: Session) -> list[CatalogItem]:
    items = [CatalogItem(id=p.id, material=p.material, dn=p.dn, pipe_class=p.pipe_class,
                         inner_diameter_mm=p.inner_diameter_mm, hw_c=p.hw_c, dw_roughness_mm=p.dw_roughness_mm,
                         manning_n=p.manning_n) for p in catalog_repo.list_pipes(session)]
    with_materials(sorted({c.material for c in items}))
    return items


def safe_name(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", name).strip("_") or "proyecto"


def template(session: Session) -> bytes:
    _catalog(session)
    return excel.write_workbook(None, zone_label=zone_label(get_settings().length_srid), model_rows=None)


def export_xlsx(session: Session, project: Project, number: int | None) -> tuple[bytes, str]:
    _catalog(session)
    version = get_version_or_404(session, project, number)
    model = load_model(session, version)
    data = excel.write_workbook(model_rows(model, project.length_srid), zone_label=zone_label(project.length_srid),
                                model_rows=model_sheet_rows(model))
    return data, f"{safe_name(project.name)}-v{version.number}.xlsx"


def export_rows_xlsx(session: Session, project: Project, sheet_key: str, rows: list[Row]) -> bytes:
    _catalog(session)
    return excel.write_workbook({sheet_key: rows}, zone_label=zone_label(project.length_srid), only=[sheet_key])


def read_upload(filename: str, content: bytes, sheet: str | None):
    """Archivo subido → (hojas crudas, hoja Modelo, avisos). CSV requiere indicar la hoja."""
    name = (filename or "").lower()
    if name.endswith(".csv") or name.endswith(".txt"):
        sh = SHEET_BY_NAME.get(norm(sheet or ""))
        if sh is None:
            raise ImportFileError("Para importar un CSV indique la hoja (Nudos, Tramos, Clientes, …).")
        raw = excel.read_csv(sh, content)
        return {sh.key: raw}, None, []
    if not content.startswith(b"PK"):
        raise ImportFileError("El archivo debe ser una planilla .xlsx o un .csv.")
    try:
        sheets, model_sheet, notes = excel.read_workbook(content)
    except excel.WorkbookError as exc:
        raise ImportFileError(str(exc)) from exc
    if not sheets and model_sheet is None:
        raise ImportFileError("La planilla no tiene hojas reconocidas (Nudos, Tramos, Estanques, …).")
    return sheets, model_sheet, notes


def _run(session: Session, project: Project, filename: str, content: bytes, *, sheet: str | None,
         delete_missing: bool, zone: int | None, hemisphere: str) -> tuple[Outcome, object]:
    sheets, model_sheet, notes = read_upload(filename, content, sheet)
    srid = utm_srid(zone, hemisphere, project.length_srid)
    latest = projects_repo.get_version(session, project.id, None)
    base = load_model(session, latest) if latest else NetworkModel()
    out = run_import(base, sheets, model_sheet, srid=project.length_srid,
                     opts=ImportOptions(coord_srid=srid, delete_missing=delete_missing), catalog=_catalog(session),
                     notes=notes, base_version=latest.number if latest else None)
    return out, latest


def preview(session: Session, project: Project, filename: str, content: bytes, **kw) -> ImportPreview:
    return _run(session, project, filename, content, **kw)[0].preview


def apply(session: Session, project: Project, filename: str, content: bytes, *, base_version: int | None,
          label: str | None = None, **kw) -> ImportApplyResult:
    out, latest = _run(session, project, filename, content, **kw)
    if base_version is not None and latest is not None and base_version != latest.number:
        raise Conflict(f"La versión base {base_version} no es la última ({latest.number}). Repita la vista previa.")
    p = out.preview
    if not p.ok or out.model is None:
        return ImportApplyResult(version=None, created=False, project_id=str(project.id), preview=p)
    if not p.has_changes and not any(i.sheet == "Modelo" for i in p.modified):
        return ImportApplyResult(version=latest.number if latest else None, created=False,
                                 project_id=str(project.id), preview=p)
    model = out.model
    prepare_network(model.network, project.length_srid)
    text = label or (f"Importación {filename}: {len(p.new)} nuevos, {len(p.modified)} modificados, "
                     f"{len(p.deleted)} eliminados")
    version = create_version(session, project, model, kind="import", label=text[:200], parent=latest)
    session.commit()
    return ImportApplyResult(version=version.number, created=True, project_id=str(project.id), preview=p)


def create_from_excel(session: Session, filename: str, content: bytes, *, name: str | None, zone: int | None,
                      hemisphere: str) -> ImportApplyResult:
    """Proyecto nuevo desde una planilla (todo o nada: si hay errores no se crea el proyecto)."""
    srid_default = get_settings().length_srid
    srid = utm_srid(zone, hemisphere, srid_default)
    _check_srid(srid)
    default = catalog_repo.default_profile(session)
    stem = re.sub(r"\.(xlsx|csv)$", "", filename or "planilla", flags=re.I)
    project = Project(id=uuid.uuid4(), org_id=new_project_org(session), name=(name or stem)[:200], description="Creado desde planilla Excel",
                      length_srid=srid, design_profile_id=default.id if default else None)
    session.add(project)
    session.flush()
    sheets, model_sheet, notes = read_upload(filename, content, None)
    out = run_import(NetworkModel(options=HydraulicOptions()), sheets, model_sheet, srid=srid,
                     opts=ImportOptions(coord_srid=srid), catalog=_catalog(session), notes=notes)
    if not out.preview.ok or out.model is None:
        session.rollback()
        return ImportApplyResult(version=None, created=False, project_id="", preview=out.preview)
    prepare_network(out.model.network, srid)
    v = create_version(session, project, out.model, kind="import", label=f"Creado desde {filename}"[:200], parent=None)
    session.commit()
    if content.startswith(b"PK"):
        out.preview.notes.extend(_import_records(session, project, content, {lk.id for lk in out.model.network.links()}))
    return ImportApplyResult(version=v.number, created=True, project_id=str(project.id), preview=out.preview)


def _import_records(session: Session, project: Project, content: bytes, links: set[str]) -> list[str]:
    """Hojas «Mediciones» y «Pérdidas» de la planilla: registros del proyecto nuevo (si están y son válidas)."""
    from openpyxl import load_workbook

    from app.services import measurements, summary

    wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    tables = {norm(ws.title): [list(r) for r in ws.iter_rows(values_only=True)] for ws in wb.worksheets
              if norm(ws.title) in (norm("Mediciones"), norm("Pérdidas"))}
    wb.close()
    notes: list[str] = []
    meas = tables.get(norm("Mediciones"))
    if meas:
        if len(meas) > 1 and meas[1] and isinstance(meas[1][0], str) and meas[1][0].startswith("nudo, tramo"):
            meas = [meas[0], *meas[2:]]
        items, errors = measurements.parse_table(meas)
        if errors:
            notes.append(f"Hoja «Mediciones» no importada: {errors[0]}")
        elif items:
            measurements.add(session, project, items)
            notes.append(f"Hoja «Mediciones»: {len(items)} mediciones registradas.")
    leaks = tables.get(norm("Pérdidas"))
    if leaks:
        items, errors = summary.parse_leak_table(leaks, links)
        if errors:
            notes.append(f"Hoja «Pérdidas» no importada: {errors[0]}")
        elif items:
            summary.add_leaks(session, project, items)
            notes.append(f"Hoja «Pérdidas»: {len(items)} eventos registrados.")
    return notes


def rows_for(session: Session, project: Project, number: int | None, sheet_key: str) -> list[Row]:
    if sheet_key not in SHEET_BY_KEY:
        raise NotFound(f"Hoja «{sheet_key}» desconocida")
    version = get_version_or_404(session, project, number)
    return model_rows(load_model(session, version), project.length_srid)[sheet_key]
