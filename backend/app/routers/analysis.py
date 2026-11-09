"""Análisis sobre una versión: escenarios de llaves, factibilidad de clientes, importación de clientes y
parámetros de diseño del proyecto."""
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.schemas.analysis import (ClientImportResult, CompareRequest, CompareResult, FeasibilityRequest,
                                  FeasibilityResult, ScenarioRequest, ScenarioResult)
from app.schemas.design import DesignParamsOut, DesignParamUpdate
from app.schemas.simulation import SimulationBlocked
from app.services import clients_import, design, feasibility, report, scenarios
from app.services.errors import SimulationBlockedError
from app.services.network import get_project_or_404, get_version_or_404, load_model
from app.services.simulation import validation_for

router = APIRouter(prefix="/projects/{project_id}", tags=["análisis"])
SessionDep = Annotated[Session, Depends(get_session)]
MAX_CSV_BYTES = 5 * 1024 * 1024
BLOCKED = {422: {"model": SimulationBlocked, "description": "Errores bloqueantes en la red: no se ejecutó"}}


def _scenario(session: Session, project_id: uuid.UUID, version: int, scenario: str) -> ScenarioResult:
    project = get_project_or_404(session, project_id)
    v = get_version_or_404(session, project, version)
    model = load_model(session, v)
    rep = validation_for(session, project, model)
    if not rep.ok:
        raise SimulationBlockedError(v.number, rep)
    pmin = float(design.param(design.effective(session, project), "pressure_min").value)
    return scenarios.simulate_scenario(model, scenario, project_id=str(project.id), version=v.number, pressure_min=pmin)


@router.post("/scenarios/simulate", response_model=ScenarioResult, responses=BLOCKED,
             summary="Simular un escenario de llaves: suministro y presión por nudo y cliente")
def simulate_scenario(project_id: uuid.UUID, body: ScenarioRequest, session: SessionDep) -> ScenarioResult:
    return _scenario(session, project_id, body.model_version, body.scenario)


@router.post("/scenarios/compare", response_model=CompareResult, responses=BLOCKED,
             summary="Comparar dos escenarios de llaves (presión antes, después y diferencia)")
def compare_scenarios(project_id: uuid.UUID, body: CompareRequest, session: SessionDep) -> CompareResult:
    a = _scenario(session, project_id, body.model_version, body.a)
    b = _scenario(session, project_id, body.model_version, body.b)
    return scenarios.compare(a, b)


@router.post("/feasibility", response_model=FeasibilityResult, responses=BLOCKED,
             summary="Factibilidad de un nuevo cliente (no modifica el proyecto)")
def assess_feasibility(project_id: uuid.UUID, body: FeasibilityRequest, session: SessionDep) -> FeasibilityResult:
    project = get_project_or_404(session, project_id)
    return feasibility.assess(session, project, body)[0]


@router.post("/feasibility/report", response_class=Response, responses={200: {"content": {"text/html": {}}}, **BLOCKED},
             summary="Informe de factibilidad en HTML imprimible")
def feasibility_report(project_id: uuid.UUID, body: FeasibilityRequest, session: SessionDep) -> Response:
    project = get_project_or_404(session, project_id)
    result, _ = feasibility.assess(session, project, body)
    return Response(content=report.feasibility_html(result), media_type="text/html; charset=utf-8")


@router.post("/clients/import", response_model=ClientImportResult, status_code=201,
             summary="Importar clientes desde CSV (lat, lon, nombre, consumo) y asignarlos a nudos")
def import_clients(project_id: uuid.UUID, session: SessionDep,
                   file: Annotated[UploadFile, File(description="CSV con columnas lat, lon, nombre, consumo (L/s)")],
                   base_version: Annotated[int | None, Form()] = None) -> ClientImportResult:
    project = get_project_or_404(session, project_id)
    content = file.file.read(MAX_CSV_BYTES + 1)
    if len(content) > MAX_CSV_BYTES:
        raise HTTPException(status_code=413, detail="El CSV supera 5 MB")
    try:
        return clients_import.import_csv(session, project, content, base_version)
    except clients_import.CsvImportError as exc:
        raise HTTPException(status_code=422, detail={"message": "El CSV tiene errores; no se importó nada.",
                                                     "errors": exc.errors}) from exc


def _params_out(session: Session, project) -> DesignParamsOut:
    from app.repositories import catalog as catalog_repo

    profile = catalog_repo.get_profile(session, project.design_profile_id)
    return DesignParamsOut(project_id=str(project.id), profile_name=profile.name if profile else None,
                           customized=bool(project.design_params), params=design.effective(session, project))


@router.get("/design-params", response_model=DesignParamsOut, summary="Parámetros de diseño del proyecto")
def get_design_params(project_id: uuid.UUID, session: SessionDep) -> DesignParamsOut:
    return _params_out(session, get_project_or_404(session, project_id))


@router.put("/design-params", response_model=DesignParamsOut, summary="Editar parámetros de diseño del proyecto")
def put_design_params(project_id: uuid.UUID, body: list[DesignParamUpdate], session: SessionDep) -> DesignParamsOut:
    project = get_project_or_404(session, project_id)
    try:
        design.update(session, project, body)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _params_out(session, project)
