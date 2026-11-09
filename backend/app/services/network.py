"""Versiones del modelo: carga, guardado (siempre crea una versión nueva inmutable) y huella de contenido."""
import hashlib
import json
import uuid

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Project, ProjectVersion
from app.repositories import network as network_repo
from app.repositories import projects as projects_repo
from app.schemas.network import HydraulicOptions, NetworkFeatureCollection, NetworkModel, ValveScenario
from app.schemas.project import LinkLengths, NetworkDocument, NetworkSave, NetworkSaveResult
from app.services.errors import Conflict, InvalidNetwork, NotFound
from app.services.geometry import place_shutoffs, recompute_lengths
from app.validators.network_validator import validate_model


def sha256_of(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def content_hash(model: NetworkModel) -> str:
    payload = model.model_dump(mode="json", exclude={"title"})
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def get_project_or_404(session: Session, project_id: uuid.UUID) -> Project:
    project = projects_repo.get_project(session, project_id)
    if project is None:
        raise NotFound("Proyecto no encontrado")
    return project


def get_version_or_404(session: Session, project: Project, number: int | None) -> ProjectVersion:
    version = projects_repo.get_version(session, project.id, number)
    if version is None:
        raise NotFound("Versión no encontrada" if number is not None else "El proyecto no tiene versiones")
    return version


def load_model(session: Session, version: ProjectVersion) -> NetworkModel:
    return NetworkModel(options=HydraulicOptions(**version.options), aux=dict(version.aux or {}),
                        network=network_repo.load_network(session, version.id),
                        scenarios=[ValveScenario(**x) for x in (version.scenarios or [])])


def get_document(session: Session, project: Project, number: int | None) -> NetworkDocument:
    version = get_version_or_404(session, project, number)
    model = load_model(session, version)
    return NetworkDocument(project_id=project.id, version=version.number, kind=version.kind, label=version.label,
                           created_at=version.created_at, length_srid=project.length_srid, options=model.options,
                           aux=model.aux, network=model.network, scenarios=model.scenarios)


def create_version(session: Session, project: Project, model: NetworkModel, *, kind: str, label: str | None,
                   parent: ProjectVersion | None) -> ProjectVersion:
    number = (parent.number + 1) if parent else 1
    version = ProjectVersion(project_id=project.id, number=number, kind=kind, label=label,
                             parent_number=parent.number if parent else None,
                             options=model.options.model_dump(mode="json"), aux=model.aux,
                             scenarios=[x.model_dump(mode="json") for x in model.scenarios],
                             content_sha256=content_hash(model))
    session.add(version)
    session.flush()
    network_repo.insert_network(session, version, model.network)
    project.updated_at = func.now()
    return version


def prepare_network(fc: NetworkFeatureCollection, srid: int) -> None:
    structural = validate_model(NetworkModel(network=fc), structural_only=True)
    if not structural.ok:
        raise InvalidNetwork(structural, "La red tiene errores de estructura (IDs duplicados, tramos sin nudos "
                                         "válidos, clientes o llaves sin elemento asociado) y no se puede guardar.")
    for f in fc.features:
        if not f.properties.uid:
            f.properties.uid = str(uuid.uuid4())
    recompute_lengths(fc, srid)
    place_shutoffs(fc, srid)


def save_network(session: Session, project: Project, body: NetworkSave) -> NetworkSaveResult:
    latest = projects_repo.get_version(session, project.id, None)
    if body.base_version is not None and latest is not None and body.base_version != latest.number:
        raise Conflict(f"La versión base {body.base_version} no es la última ({latest.number}). Recargue el proyecto.")

    options = body.options or (HydraulicOptions(**latest.options) if latest else HydraulicOptions())
    aux = body.aux if body.aux is not None else (dict(latest.aux) if latest else {})
    scenarios = body.scenarios if body.scenarios is not None else (
        [ValveScenario(**x) for x in (latest.scenarios or [])] if latest else [])
    fc = body.network
    prepare_network(fc, project.length_srid)
    model = NetworkModel(options=options, aux=aux, network=fc, scenarios=scenarios)
    digest = content_hash(model)
    lengths = {lk.id: LinkLengths(length_plan_m=lk.properties.length_plan_m,
                                  length_slope_m=lk.properties.length_slope_m,
                                  length_hydraulic_m=lk.properties.length_hydraulic_m) for lk in fc.links()}

    if body.kind == "auto" and latest is not None and latest.content_sha256 == digest:
        return NetworkSaveResult(version=latest.number, created=False, content_sha256=digest, lengths=lengths)

    version = create_version(session, project, model, kind=body.kind, label=body.label, parent=latest)
    session.commit()
    return NetworkSaveResult(version=version.number, created=True, content_sha256=digest, lengths=lengths)
