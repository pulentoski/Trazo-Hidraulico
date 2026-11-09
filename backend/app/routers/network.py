import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.repositories import projects as projects_repo
from app.repositories import results as results_repo
from app.schemas.network import HydraulicOptions, NetworkModel
from app.schemas.project import NetworkDocument, NetworkSave, NetworkSaveResult
from app.schemas.simulation import SimulateRequest, SimulationBlocked, SimulationResult
from app.schemas.validation import ValidateRequest, ValidationReport
from app.services import network as network_svc
from app.services import simulation as sim_svc
from app.services.errors import NotFound
from app.services.geometry import recompute_lengths

router = APIRouter(prefix="/projects/{project_id}", tags=["red y simulación"])
SessionDep = Annotated[Session, Depends(get_session)]


@router.get("/network", response_model=NetworkDocument, summary="Red de una versión como GeoJSON")
def get_network(project_id: uuid.UUID, session: SessionDep,
                version: Annotated[int | None, Query(description="Número de versión (última si se omite)")] = None
                ) -> NetworkDocument:
    project = network_svc.get_project_or_404(session, project_id)
    return network_svc.get_document(session, project, version)


@router.put("/network", response_model=NetworkSaveResult, summary="Guardar la red (crea una versión nueva inmutable)",
            responses={409: {"description": "La versión base no es la última"},
                       422: {"description": "Red con errores de estructura"}})
def put_network(project_id: uuid.UUID, body: NetworkSave, session: SessionDep) -> NetworkSaveResult:
    project = network_svc.get_project_or_404(session, project_id)
    return network_svc.save_network(session, project, body)


@router.post("/validate", response_model=ValidationReport, summary="Validar una versión o una red en edición")
def validate(project_id: uuid.UUID, body: ValidateRequest, session: SessionDep) -> ValidationReport:
    project = network_svc.get_project_or_404(session, project_id)
    if body.network is not None:
        latest = projects_repo.get_version(session, project.id, None)
        options = body.options or (HydraulicOptions(**latest.options) if latest else HydraulicOptions())
        aux = body.aux if body.aux is not None else (dict(latest.aux) if latest else {})
        model = NetworkModel(options=options, aux=aux, network=body.network)
        structural = sim_svc.validate_model(model, structural_only=True)
        if structural.ok:
            recompute_lengths(model.network, project.length_srid)
    else:
        version = network_svc.get_version_or_404(session, project, body.model_version)
        model = network_svc.load_model(session, version)
    return sim_svc.validation_for(session, project, model)


@router.post("/simulate", response_model=SimulationResult, summary="Simular una versión del modelo (síncrono)",
             responses={422: {"model": SimulationBlocked, "description": "Errores bloqueantes: no se ejecutó"}})
def simulate(project_id: uuid.UUID, body: SimulateRequest, session: SessionDep) -> SimulationResult:
    project = network_svc.get_project_or_404(session, project_id)
    return sim_svc.simulate_version(session, project, body.model_version)


@router.get("/runs/{run_id}", response_model=SimulationResult, summary="Resultados de una corrida guardada")
def get_run(project_id: uuid.UUID, run_id: uuid.UUID, session: SessionDep) -> SimulationResult:
    project = network_svc.get_project_or_404(session, project_id)
    run = results_repo.get_run(session, run_id)
    if run is None:
        raise NotFound("Corrida no encontrada")
    version = next((v for v in project.versions if v.id == run.version_id), None)
    if version is None:
        raise NotFound("Corrida no encontrada")
    return sim_svc.result_from_db(session, project, version, run)
