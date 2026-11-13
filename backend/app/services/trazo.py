"""Formato de proyecto .trazo: zip con el .inp completo (compatibilidad EPANET) y `trazo.json` con los datos
propios de Trazo Hidráulico (clientes, llaves, escenarios, atributos de gestión, cuarteles, consultas
guardadas, parámetros de diseño, proyección de demanda, origen de las cotas, vértices, eventos de pérdidas,
configuración del Resumen, mediciones (medidores, presiones y niveles) y ortofotos: referencia, georreferencia y puntos de control, y opcionalmente el
archivo de imagen en `ortofotos/<id>/`). La importación usa el JSON (sin pérdida); el .inp solo si el JSON falta.
"""
from __future__ import annotations

import io
import json
import os
import shutil
import tempfile
import uuid
import zipfile
from datetime import date, datetime, timezone
from typing import IO

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.services.auth import new_project_org

from app.core.config import get_settings
from app.models import LeakEvent, Measurement, Orthophoto, Project, SavedQuery
from app.repositories import catalog as catalog_repo
from app.schemas.network import HydraulicOptions, NetworkFeatureCollection, NetworkModel, ValveScenario
from app.services.errors import NotFound
from app.services.network import create_version, get_version_or_404, load_model, prepare_network
from app.services.projects import export_inp, import_inp
from app.sig.sectors import compute_sectors

FORMAT = "trazo"
FORMAT_VERSION = 1
JSON_NAME = "trazo.json"
INP_NAME = "modelo.inp"
MAX_UNCOMPRESSED = 200 * 1024 * 1024  # trazo.json y .inp (las ortofotos incluidas tienen su propio límite)
ORTHO_PREFIX = "ortofotos/"


class TrazoError(ValueError):
    pass


def _ortho_doc(o: Orthophoto, include_file: bool) -> dict:
    from app.services.orthophotos import WORLD_EXT, ortho_dir

    d = {"id": str(o.id), "name": o.name, "source": o.source,
         "captured_on": o.captured_on.isoformat() if o.captured_on else None, "georef": o.georef,
         "original_name": o.original_name, "original_ext": o.original_ext, "src_crs": o.src_crs, "world": o.world,
         "gcps": o.gcps, "bounds": o.bounds, "residual_m": o.residual_m, "width": o.width, "height": o.height,
         "size_bytes": o.size_bytes, "opacity": o.opacity, "visible": o.visible, "target_res_m": o.target_res_m,
         "status": o.status}
    original = os.path.join(ortho_dir(o.id), f"original.{o.original_ext}")
    if include_file and o.status != "uploading" and os.path.exists(original):
        d["file"] = f"{ORTHO_PREFIX}{o.id}/original.{o.original_ext}"
        world = os.path.join(ortho_dir(o.id), f"original.{WORLD_EXT.get(o.original_ext, 'wld')}")
        if os.path.exists(world):
            d["world_file"] = f"{ORTHO_PREFIX}{o.id}/{os.path.basename(world)}"
    else:
        d["note"] = "Referencia: el archivo de imagen no se incluye en este .trazo"
    return d


def export(session: Session, project: Project, number: int | None, *, include_orthos: bool = False,
           dest: IO[bytes] | None = None) -> tuple[bytes | None, str]:
    """Escribe el .trazo en `dest` (archivo) o lo devuelve en memoria. Con `include_orthos`, agrega las imágenes."""
    from app.services.orthophotos import ortho_dir

    version = get_version_or_404(session, project, number)
    model = load_model(session, version)
    inp_text, inp_name = export_inp(session, project, version.number)
    profile = catalog_repo.get_profile(session, project.design_profile_id)
    queries = session.scalars(select(SavedQuery).where(SavedQuery.project_id == project.id).order_by(SavedQuery.name))
    orthos = list(session.scalars(select(Orthophoto).where(Orthophoto.project_id == project.id)
                                  .order_by(Orthophoto.created_at)))
    leaks = session.scalars(select(LeakEvent).where(LeakEvent.project_id == project.id)
                            .order_by(LeakEvent.event_date, LeakEvent.id))
    ortho_docs = [_ortho_doc(o, include_orthos) for o in orthos]
    doc = {
        "format": FORMAT, "format_version": FORMAT_VERSION,
        "generator": "Trazo Hidráulico (OWA-EPANET 2.3.5)",
        "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "project": {"name": project.name, "description": project.description, "length_srid": project.length_srid,
                    "design_profile": profile.name if profile else None, "design_params": project.design_params,
                    "demand_projection": project.demand_projection, "monitoring": project.monitoring,
                    "summary_settings": project.summary_settings, "gestion_settings": project.gestion_settings},
        "version": {"number": version.number, "kind": version.kind, "label": version.label,
                    "content_sha256": version.content_sha256},
        "model": {"options": model.options.model_dump(mode="json"), "aux": model.aux,
                  "scenarios": [s.model_dump(mode="json") for s in model.scenarios],
                  "network": model.network.model_dump(mode="json")},
        "saved_queries": [{"name": q.name, "definition": q.definition} for q in queries],
        "sectors": compute_sectors(model).model_dump(mode="json")["sectors"],
        "leak_events": [{"link_id": e.link_id, "event_date": e.event_date.isoformat(), "kind": e.kind,
                         "flow_lps": e.flow_lps, "note": e.note} for e in leaks],
        "measurements": _measurements_doc(session, project),
        "orthophotos": ortho_docs,
        **_gestion_doc(session, project),
    }
    target = dest or io.BytesIO()
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as z:
        z.writestr(INP_NAME, inp_text.encode("latin-1", errors="replace"))
        z.writestr(JSON_NAME, json.dumps(doc, ensure_ascii=False, indent=1, sort_keys=False))
        for o, d in zip(orthos, ortho_docs):
            for key in ("file", "world_file"):
                if d.get(key):
                    src = os.path.join(ortho_dir(o.id), os.path.basename(d[key]))
                    # Las imágenes ya vienen comprimidas: se guardan sin volver a comprimir.
                    z.write(src, d[key], compress_type=zipfile.ZIP_STORED if key == "file" else zipfile.ZIP_DEFLATED)
    name = inp_name.rsplit(".", 1)[0] + ".trazo"
    return (None if dest else target.getvalue()), name


def _open_zip(src: bytes | str) -> zipfile.ZipFile:
    try:
        return zipfile.ZipFile(io.BytesIO(src) if isinstance(src, bytes) else src)
    except zipfile.BadZipFile as exc:
        raise TrazoError("El archivo no es un .trazo válido (zip).") from exc


def _read_zip(content: bytes | str) -> tuple[dict | None, bytes | None]:
    with _open_zip(content) as z:
        infos = z.infolist()
        total = sum(i.file_size for i in infos if not i.filename.startswith(ORTHO_PREFIX))
        if total > MAX_UNCOMPRESSED:
            raise TrazoError("El .trazo descomprimido es demasiado grande.")
        ortho_total = sum(i.file_size for i in infos if i.filename.startswith(ORTHO_PREFIX))
        if ortho_total > get_settings().max_ortho_mb * 1024 * 1024 * 4:
            raise TrazoError("Las ortofotos incluidas en el .trazo son demasiado grandes.")
        names = {i.filename for i in infos}
        doc = None
        if JSON_NAME in names:
            try:
                doc = json.loads(z.read(JSON_NAME).decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise TrazoError("trazo.json no es un JSON válido.") from exc
        inp_name = next((n for n in names if n.lower().endswith(".inp") and "/" not in n), None)
        inp = z.read(inp_name) if inp_name else None
    if doc is None and inp is None:
        raise TrazoError("El .trazo no contiene trazo.json ni un .inp.")
    return doc, inp


def import_file(session: Session, filename: str, content: bytes | str, *,
                name: str | None) -> tuple[Project, int, list[str]]:
    """Importa un .trazo (bytes o ruta de un archivo temporal) como proyecto nuevo."""
    doc, inp = _read_zip(content)
    notes: list[str] = []
    if doc is None:
        with tempfile.TemporaryDirectory():
            res = import_inp(session, filename.rsplit(".", 1)[0] + ".inp", inp, name=name, crs="auto")
        project = session.get(Project, res.project.id)
        return project, res.version, ["El .trazo no traía trazo.json: se importó solo el .inp.", *res.notes]
    if doc.get("format") != FORMAT:
        raise TrazoError("trazo.json no corresponde al formato .trazo.")
    if int(doc.get("format_version", 0)) > FORMAT_VERSION:
        raise TrazoError(f"Versión de formato {doc.get('format_version')} más nueva que la soportada ({FORMAT_VERSION}).")
    p, m = doc.get("project") or {}, doc.get("model") or {}
    try:
        model = NetworkModel(options=HydraulicOptions.model_validate(m.get("options") or {}), aux=m.get("aux") or {},
                             network=NetworkFeatureCollection.model_validate(m.get("network") or {}),
                             scenarios=[ValveScenario.model_validate(x) for x in m.get("scenarios") or []])
    except ValueError as exc:
        raise TrazoError(f"El modelo del .trazo no es válido: {exc}") from exc
    profiles = {pr.name: pr.id for pr in catalog_repo.list_profiles(session)}
    default = catalog_repo.default_profile(session)
    srid = int(p.get("length_srid") or get_settings().length_srid)
    project = Project(id=uuid.uuid4(), org_id=new_project_org(session), name=(name or p.get("name") or "Proyecto .trazo")[:200],
                      description=p.get("description") or "", length_srid=srid,
                      design_profile_id=profiles.get(p.get("design_profile")) or (default.id if default else None),
                      design_params=p.get("design_params"), demand_projection=p.get("demand_projection"),
                      monitoring=p.get("monitoring"), summary_settings=_settings(p.get("summary_settings")))
    session.add(project)
    session.flush()
    prepare_network(model.network, srid)
    v = doc.get("version") or {}
    version = create_version(session, project, model, kind="import",
                             label=(v.get("label") or f"Importado desde {os.path.basename(filename)}")[:200], parent=None)
    for q in doc.get("saved_queries") or []:
        if q.get("name") and isinstance(q.get("definition"), dict):
            session.add(SavedQuery(project_id=project.id, name=str(q["name"])[:120], definition=q["definition"]))
    links = {lk.id for lk in model.network.links()}
    skipped = 0
    for e in doc.get("leak_events") or []:
        try:
            if e.get("link_id") not in links or e.get("kind") not in ("fuga", "rotura", "reparacion"):
                raise ValueError
            session.add(LeakEvent(project_id=project.id, link_id=str(e["link_id"])[:31],
                                  event_date=date.fromisoformat(str(e["event_date"])[:10]), kind=e["kind"],
                                  flow_lps=float(e["flow_lps"]) if e.get("flow_lps") is not None else None,
                                  note=(str(e["note"])[:300] if e.get("note") else None)))
        except (ValueError, TypeError, KeyError):
            skipped += 1
    if skipped:
        notes.append(f"{skipped} eventos de pérdidas no válidos se omitieron.")
    notes += _import_measurements(session, project, doc.get("measurements") or [])
    project.gestion_settings = _gestion_settings(p.get("gestion_settings"))
    session.flush()
    notes += _import_gestion(session, project, doc)
    session.commit()
    notes += _import_orthos(session, project, content, doc.get("orthophotos") or [])
    return project, version.number, notes


def _measurements_doc(session: Session, project: Project) -> list[dict]:
    """Registro de funcionamiento: lecturas de medidor (m³ acumulados), presiones y niveles medidos."""
    rows = session.scalars(select(Measurement).where(Measurement.project_id == project.id)
                           .order_by(Measurement.element_type, Measurement.element_id, Measurement.kind,
                                     Measurement.measured_at, Measurement.id))
    return [{"element_type": m.element_type, "element_id": m.element_id, "kind": m.kind,
             "measured_at": m.measured_at.isoformat(), "value": m.value, "note": m.note} for m in rows]


def _import_measurements(session: Session, project: Project, items: list) -> list[str]:
    """Mediciones del .trazo (clave opcional: los .trazo anteriores no la traen). Las filas no válidas se omiten."""
    from app.schemas.measurement import MeasurementIn
    from app.services.measurements import MAX_ROWS

    good, bad = [], 0
    for raw in items[:MAX_ROWS] if isinstance(items, list) else []:
        try:
            m = MeasurementIn.model_validate(raw)
            if m.measured_at.tzinfo is None:
                m.measured_at = m.measured_at.replace(tzinfo=timezone.utc)
            good.append(Measurement(project_id=project.id, **m.model_dump()))
        except (ValueError, TypeError):
            bad += 1
    session.add_all(good)
    notes = []
    if bad:
        notes.append(f"{bad} mediciones no válidas se omitieron.")
    if isinstance(items, list) and len(items) > MAX_ROWS:
        notes.append(f"Se importaron las primeras {MAX_ROWS} mediciones de {len(items)}.")
    return notes


def _gestion_doc(session: Session, project: Project) -> dict:
    """Registros de la página «Gestión» (operación, mantenciones con su cumplimiento y factibilidades)."""
    from app.models import FeasibilityRecord, MaintenanceLog
    from app.services import gestion_records as rec

    records: dict[str, list[dict]] = {}
    task_index: dict[int, int] = {}
    for kind, spec in rec.SPECS.items():
        rows = sorted(rec.list_rows(session, project, kind), key=lambda r: r.id)
        records[kind] = [{f.key: rec._json(getattr(r, f.key)) for f in spec.fields} for r in rows]
        if kind == "mantenciones":
            for i, r in enumerate(rows):
                task_index[r.id] = i
    logs = [{"task": task_index[x.task_id], "done_on": x.done_on.isoformat(),
             "scheduled_for": x.scheduled_for.isoformat() if x.scheduled_for else None, "by": x.by, "note": x.note}
            for x in session.scalars(select(MaintenanceLog).where(MaintenanceLog.project_id == project.id)
                                     .order_by(MaintenanceLog.id)) if x.task_id in task_index]
    feas = [{"created_at": f.created_at.isoformat(), "created_by": f.created_by, "model_version": f.model_version,
             "link_id": f.link_id, "location": f.location, "consumption_lps": f.consumption_lps, "elevation": f.elevation,
             "feasible": f.feasible, "pressure_new": f.pressure_new, "bottleneck": f.bottleneck, "name": f.name}
            for f in session.scalars(select(FeasibilityRecord).where(FeasibilityRecord.project_id == project.id)
                                     .order_by(FeasibilityRecord.id))]
    return {"records": records, "maintenance_logs": logs, "feasibility_history": feas}


def _gestion_settings(raw) -> dict | None:
    if not raw:
        return None
    from app.schemas.gestion import GestionSettings

    try:
        return GestionSettings.model_validate(raw).model_dump(mode="json")
    except ValueError:
        return None


def _import_gestion(session: Session, project: Project, doc: dict) -> list[str]:
    from app.models import FeasibilityRecord, MaintenanceLog
    from app.services import gestion_records as rec

    notes: list[str] = []
    ctx = rec.context(session, project)
    tasks: dict[int, object] = {}
    for kind, spec in rec.SPECS.items():
        items = (doc.get("records") or {}).get(kind) or []
        good: list[tuple[int, dict, dict]] = []
        bad = 0
        for i, raw in enumerate(items):
            vals, err = rec.validate(spec, raw, ctx) if isinstance(raw, dict) else ({}, ["fila no válida"])
            if err:
                bad += 1
            else:
                good.append((i, vals, raw))
        if good:
            _, _, rows = rec.create(session, project, kind, [v for _, v, _ in good], None)
            if kind == "mantenciones":
                # Los cumplimientos vienen en «maintenance_logs»: se descarta el registrado al crear la tarea.
                for r, (i, _, _raw) in zip(rows, good):
                    tasks[i] = r
                session.flush()
                session.execute(delete(MaintenanceLog).where(MaintenanceLog.task_id.in_([r.id for r in rows])))
        if bad:
            notes.append(f"Registro «{spec.title}»: {bad} filas no válidas se omitieron.")
    session.flush()
    for x in doc.get("maintenance_logs") or []:
        try:
            t = tasks.get(int(x["task"]))
            if t is None:
                continue
            session.add(MaintenanceLog(task_id=t.id, project_id=project.id, done_on=date.fromisoformat(x["done_on"]),
                                       scheduled_for=date.fromisoformat(x["scheduled_for"]) if x.get("scheduled_for") else None,
                                       by=(x.get("by") or None), note=(x.get("note") or None)))
        except (ValueError, TypeError, KeyError):
            continue
    for f in doc.get("feasibility_history") or []:
        try:
            session.add(FeasibilityRecord(project_id=project.id, created_by=f.get("created_by"),
                                          created_at=datetime.fromisoformat(f["created_at"]),
                                          model_version=int(f["model_version"]), link_id=str(f["link_id"])[:31],
                                          location=list(f.get("location") or []), consumption_lps=float(f["consumption_lps"]),
                                          elevation=f.get("elevation"), feasible=bool(f["feasible"]),
                                          pressure_new=f.get("pressure_new"), bottleneck=f.get("bottleneck"),
                                          name=(str(f["name"])[:200] if f.get("name") else None)))
        except (ValueError, TypeError, KeyError):
            continue
    return notes


def _settings(raw) -> dict | None:
    """Configuración del Resumen: se valida (valores fuera de rango se descartan y quedan los sugeridos)."""
    if not raw:
        return None
    from app.schemas.summary import SummarySettings

    try:
        return SummarySettings.model_validate(raw).model_dump(mode="json")
    except ValueError:
        return None


def _import_orthos(session: Session, project: Project, content: bytes | str, items: list[dict]) -> list[str]:
    from app.services.auth import check_limit
    from app.services.orthophotos import IMAGE_EXT, OrthoError, check_disk, enqueue, ortho_dir

    notes: list[str] = []
    missing = 0
    with _open_zip(content) as z:
        names = {i.filename: i for i in z.infolist()}
        for d in items:
            path = d.get("file")
            ext = str(d.get("original_ext") or "").lower()
            if not path or path not in names or ext not in IMAGE_EXT or not path.startswith(ORTHO_PREFIX):
                missing += 1
                continue
            size = names[path].file_size
            try:
                check_disk(size)
                check_limit(session, project.org_id, "ortho", extra=size)
            except (OrthoError, Exception) as exc:  # noqa: BLE001 - cupo o disco: se informa y se sigue
                notes.append(f"Ortofoto «{d.get('name')}» no importada: {exc}")
                continue
            oid = uuid.uuid4()
            folder = ortho_dir(oid)
            os.makedirs(folder, exist_ok=True)
            with z.open(path) as src, open(os.path.join(folder, f"original.{ext}"), "wb") as dst:
                shutil.copyfileobj(src, dst, 4 * 1024 * 1024)
            wf = d.get("world_file")
            has_world = bool(wf and wf in names and wf.startswith(ORTHO_PREFIX))
            if has_world:
                with z.open(wf) as src, open(os.path.join(folder, os.path.basename(wf)), "wb") as dst:
                    shutil.copyfileobj(src, dst)
            georef = d.get("georef") if d.get("georef") in ("geotiff", "worldfile", "gcp") else "geotiff"
            ready_to_process = georef != "gcp" or has_world
            captured = d.get("captured_on")
            o = Orthophoto(id=oid, project_id=project.id, name=str(d.get("name") or "Ortofoto")[:200],
                           source=d.get("source"), captured_on=date.fromisoformat(captured) if captured else None,
                           georef=georef, status="pending" if ready_to_process else "uploaded",
                           original_name=str(d.get("original_name") or f"original.{ext}")[:255], original_ext=ext,
                           src_crs=d.get("src_crs"), world=d.get("world"), gcps=d.get("gcps"),
                           residual_m=d.get("residual_m"), width=d.get("width"), height=d.get("height"),
                           size_bytes=size, opacity=float(d.get("opacity", 1.0)), visible=bool(d.get("visible", True)),
                           target_res_m=d.get("target_res_m"))
            session.add(o)
            session.commit()
            if o.status == "pending":
                enqueue(o)
    if missing:
        notes.append(f"{missing} ortofotos referenciadas no traen su archivo en el .trazo: súbalas de nuevo "
                     "(exporte con «incluir ortofotos» para llevarlas).")
    return notes


def get_project(session: Session, pid: uuid.UUID) -> Project:
    p = session.get(Project, pid)
    if p is None:
        raise NotFound("Proyecto no encontrado")
    return p
