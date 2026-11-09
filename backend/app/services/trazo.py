"""Formato de proyecto .trazo: zip con el .inp completo (compatibilidad EPANET) y `trazo.json` con los datos
propios de Trazo Hidráulico (clientes, llaves, escenarios, atributos de gestión, cuarteles, consultas
guardadas, parámetros de diseño, proyección de demanda, origen de las cotas, vértices y referencias a
ortofotos). La importación usa el JSON (sin pérdida); el .inp solo si el JSON falta.
"""
from __future__ import annotations

import io
import json
import os
import tempfile
import uuid
import zipfile
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.services.auth import new_project_org

from app.core.config import get_settings
from app.models import Orthophoto, Project, SavedQuery
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
MAX_UNCOMPRESSED = 200 * 1024 * 1024


class TrazoError(ValueError):
    pass


def export(session: Session, project: Project, number: int | None) -> tuple[bytes, str]:
    version = get_version_or_404(session, project, number)
    model = load_model(session, version)
    inp_text, inp_name = export_inp(session, project, version.number)
    profile = catalog_repo.get_profile(session, project.design_profile_id)
    queries = session.scalars(select(SavedQuery).where(SavedQuery.project_id == project.id).order_by(SavedQuery.name))
    orthos = session.scalars(select(Orthophoto).where(Orthophoto.project_id == project.id))
    doc = {
        "format": FORMAT, "format_version": FORMAT_VERSION,
        "generator": "Trazo Hidráulico (OWA-EPANET 2.3.5)",
        "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "project": {"name": project.name, "description": project.description, "length_srid": project.length_srid,
                    "design_profile": profile.name if profile else None, "design_params": project.design_params,
                    "demand_projection": project.demand_projection},
        "version": {"number": version.number, "kind": version.kind, "label": version.label,
                    "content_sha256": version.content_sha256},
        "model": {"options": model.options.model_dump(mode="json"), "aux": model.aux,
                  "scenarios": [s.model_dump(mode="json") for s in model.scenarios],
                  "network": model.network.model_dump(mode="json")},
        "saved_queries": [{"name": q.name, "definition": q.definition} for q in queries],
        "sectors": compute_sectors(model).model_dump(mode="json")["sectors"],
        "orthophotos": [{"id": str(o.id), "name": o.name, "source": o.source,
                         "captured_on": o.captured_on.isoformat() if o.captured_on else None, "georef": o.georef,
                         "original_name": o.original_name, "src_crs": o.src_crs, "bounds": o.bounds,
                         "residual_m": o.residual_m, "opacity": o.opacity, "visible": o.visible,
                         "note": "Referencia: el archivo de imagen no se incluye en el .trazo"} for o in orthos],
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(INP_NAME, inp_text.encode("latin-1", errors="replace"))
        z.writestr(JSON_NAME, json.dumps(doc, ensure_ascii=False, indent=1, sort_keys=False))
    return buf.getvalue(), inp_name.rsplit(".", 1)[0] + ".trazo"


def _read_zip(content: bytes) -> tuple[dict | None, bytes | None]:
    try:
        z = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile as exc:
        raise TrazoError("El archivo no es un .trazo válido (zip).") from exc
    with z:
        total = sum(i.file_size for i in z.infolist())
        if total > MAX_UNCOMPRESSED:
            raise TrazoError("El .trazo descomprimido es demasiado grande.")
        names = {i.filename for i in z.infolist()}
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


def import_file(session: Session, filename: str, content: bytes, *, name: str | None) -> tuple[Project, int, list[str]]:
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
                      design_params=p.get("design_params"), demand_projection=p.get("demand_projection"))
    session.add(project)
    session.flush()
    prepare_network(model.network, srid)
    v = doc.get("version") or {}
    version = create_version(session, project, model, kind="import",
                             label=(v.get("label") or f"Importado desde {os.path.basename(filename)}")[:200], parent=None)
    for q in doc.get("saved_queries") or []:
        if q.get("name") and isinstance(q.get("definition"), dict):
            session.add(SavedQuery(project_id=project.id, name=str(q["name"])[:120], definition=q["definition"]))
    session.commit()
    if doc.get("orthophotos"):
        notes.append(f"{len(doc['orthophotos'])} ortofotos referenciadas no se incluyen en el archivo: súbalas de nuevo.")
    return project, version.number, notes


def get_project(session: Session, pid: uuid.UUID) -> Project:
    p = session.get(Project, pid)
    if p is None:
        raise NotFound("Proyecto no encontrado")
    return p
