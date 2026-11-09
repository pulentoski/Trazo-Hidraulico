"""Proyectos: creación, edición, importación y exportación de .inp."""
import os
import re
import tempfile
import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from app.services.auth import new_project_org

from app.core.config import get_settings
from app.hydraulic.inp_reader import InpImportError, read_inp
from app.hydraulic.inp_writer import write_inp
from app.models import Project
from app.repositories import catalog as catalog_repo
from app.repositories import projects as projects_repo
from app.schemas.network import HydraulicOptions, NetworkModel
from app.schemas.project import ImportResult, ProjectCreate, ProjectOut, ProjectUpdate
from app.services.errors import NotFound
from app.services.geometry import recompute_lengths, to_metric
from app.services.network import create_version, get_version_or_404, load_model


def project_out(session: Session, project: Project) -> ProjectOut:
    latest, count = projects_repo.version_stats(session, project.id)
    out = ProjectOut.model_validate(project)
    out.latest_version, out.version_count = latest, count
    return out


def _check_srid(srid: int) -> None:
    try:
        to_metric(srid)
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"SRID {srid} no reconocido") from exc


def create_project(session: Session, body: ProjectCreate) -> Project:
    srid = body.length_srid or get_settings().length_srid
    _check_srid(srid)
    profile_id = body.design_profile_id
    if profile_id is None:
        default = catalog_repo.default_profile(session)
        profile_id = default.id if default else None
    project = Project(id=uuid.uuid4(), org_id=new_project_org(session), name=body.name, description=body.description,
                      length_srid=srid, design_profile_id=profile_id)
    session.add(project)
    session.flush()
    model = NetworkModel(options=body.options or HydraulicOptions())
    create_version(session, project, model, kind="manual", label="Proyecto creado", parent=None)
    session.commit()
    return project


def update_project(session: Session, project: Project, body: ProjectUpdate) -> Project:
    data = body.model_dump(exclude_unset=True)
    if "length_srid" in data and data["length_srid"] is not None:
        _check_srid(data["length_srid"])
    if "design_profile_id" in data and data["design_profile_id"] is not None:
        if catalog_repo.get_profile(session, data["design_profile_id"]) is None:
            raise NotFound("Perfil de diseño no encontrado")
    for key, value in data.items():
        if value is not None or key == "design_profile_id":
            setattr(project, key, value)
    session.commit()
    session.refresh(project)
    return project


def import_inp(session: Session, filename: str, content: bytes, *, name: str | None, crs: str) -> ImportResult:
    s = get_settings()
    srid = s.length_srid
    with tempfile.TemporaryDirectory(prefix="trazo-upload-") as tmp:
        path = os.path.join(tmp, "upload.inp")
        with open(path, "wb") as fh:
            fh.write(content)
        result = read_inp(path, crs=crs, length_srid=srid,
                          origin=(s.default_map_center_lng, s.default_map_center_lat))
    model = result.model
    recompute_lengths(model.network, srid)
    default = catalog_repo.default_profile(session)
    stem = Path(filename or "red.inp").stem
    project = Project(id=uuid.uuid4(), org_id=new_project_org(session), name=name or stem, description=model.title or "",
                      length_srid=srid, design_profile_id=default.id if default else None)
    session.add(project)
    session.flush()
    version = create_version(session, project, model, kind="import", label=f"Importado desde {filename}", parent=None)
    session.commit()
    return ImportResult(project=project_out(session, project), version=version.number,
                        georeference=result.georeference, notes=result.warnings,
                        node_count=len(model.network.nodes()), link_count=len(model.network.links()))


def export_inp(session: Session, project: Project, number: int | None) -> tuple[str, str]:
    version = get_version_or_404(session, project, number)
    model = load_model(session, version)
    tr = to_metric(project.length_srid)

    def projector(lon: float, lat: float) -> tuple[float, float]:
        x, y = tr.transform(lon, lat)
        return float(x), float(y)

    title = f"{project.name} — versión {version.number}\nExportado por Trazo Hidráulico (OWA-EPANET 2.3.5)\n" \
            f"Coordenadas en EPSG:{project.length_srid}"
    text = write_inp(model, projector=projector, title=title)
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", project.name).strip("_") or "red"
    return text, f"{safe}-v{version.number}.inp"


__all__ = ["InpImportError", "create_project", "export_inp", "import_inp", "project_out", "update_project"]
