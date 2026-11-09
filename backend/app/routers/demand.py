"""Demanda sanitaria: proyección por proyecto, exportación y escenarios de demanda."""
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.schemas.demand import DemandInputs, DemandResult, ScenarioApplied, ScenarioApply
from app.services import demand
from app.services.network import get_project_or_404
from app.services.sig_io import safe_name

router = APIRouter(prefix="/projects/{project_id}/demand", tags=["demanda"])
SessionDep = Annotated[Session, Depends(get_session)]
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.get("/projection", response_model=DemandResult, summary="Proyección de demanda (tabla por año y escenarios)")
def get_projection(project_id: uuid.UUID, session: SessionDep) -> DemandResult:
    return demand.result(session, get_project_or_404(session, project_id))


@router.put("/projection", response_model=DemandResult, summary="Editar las entradas de la proyección")
def put_projection(project_id: uuid.UUID, body: DemandInputs, session: SessionDep) -> DemandResult:
    return demand.save_inputs(session, get_project_or_404(session, project_id), body)


@router.delete("/projection", response_model=DemandResult, summary="Volver a los valores por defecto")
def reset_projection(project_id: uuid.UUID, session: SessionDep) -> DemandResult:
    project = get_project_or_404(session, project_id)
    project.demand_projection = None
    session.commit()
    return demand.result(session, project)


@router.get("/projection.xlsx", response_class=Response, responses={200: {"content": {XLSX: {}}}},
            summary="Exportar la tabla de proyección a Excel")
def export_projection(project_id: uuid.UUID, session: SessionDep) -> Response:
    project = get_project_or_404(session, project_id)
    data = demand.export_xlsx(demand.result(session, project))
    return Response(content=data, media_type=XLSX,
                    headers={"Content-Disposition": f'attachment; filename="{safe_name(project.name)}-proyeccion.xlsx"'})


@router.post("/scenario", response_model=ScenarioApplied,
             summary="Aplicar un escenario de demanda (crea una versión con el multiplicador)")
def apply_scenario(project_id: uuid.UUID, body: ScenarioApply, session: SessionDep) -> ScenarioApplied:
    version, mult = demand.apply_scenario(session, get_project_or_404(session, project_id), body.scenario)
    return ScenarioApplied(version=version, multiplier=mult)
