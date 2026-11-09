"""Pozo y bombeo: cálculo, ficha imprimible y curva de bomba desde el punto de diseño."""
import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.schemas.well import CurveApplied, PumpCalc
from app.services import well_pump
from app.services.errors import NotFound
from app.services.network import create_version, get_project_or_404, get_version_or_404, load_model

router = APIRouter(prefix="/projects/{project_id}/wells/{well_id}", tags=["pozo y bombeo"])
SessionDep = Annotated[Session, Depends(get_session)]
Conv = Annotated[Literal["trazo", "planilla"], Query(description="trazo (γ 9.810, π) o planilla (γ 10.000, π 3,14)")]


def _load(session, project_id, well_id, version):
    project = get_project_or_404(session, project_id)
    v = get_version_or_404(session, project, version)
    model = load_model(session, v)
    well = next((w for w in model.network.wells() if w.id == well_id), None)
    if well is None:
        raise NotFound(f"Pozo {well_id} no encontrado")
    return project, v, model, well


def _calc(model, well, conventions):
    conv = well_pump.Conventions.planilla() if conventions == "planilla" else well_pump.Conventions()
    try:
        return well_pump.calculate(well, model, conv, "H-W" if conventions == "planilla" else None)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/pump", response_model=PumpCalc, summary="Altura manométrica, potencia, corriente y velocidades")
def pump_calc(project_id: uuid.UUID, well_id: str, session: SessionDep, conventions: Conv = "trazo",
              version: Annotated[int | None, Query()] = None) -> PumpCalc:
    _, _, model, well = _load(session, project_id, well_id, version)
    return _calc(model, well, conventions)


@router.get("/report.html", response_class=Response, responses={200: {"content": {"text/html": {}}}},
            summary="Ficha del pozo (HTML imprimible)")
def report(project_id: uuid.UUID, well_id: str, session: SessionDep, conventions: Conv = "trazo",
           version: Annotated[int | None, Query()] = None) -> Response:
    project, _, model, well = _load(session, project_id, well_id, version)
    return Response(content=well_pump.report_html(project.name, well, _calc(model, well, conventions)),
                    media_type="text/html; charset=utf-8")


@router.post("/apply-curve", response_model=CurveApplied,
             summary="Aplicar la curva de 3 puntos a la bomba del pozo y la cota del nivel dinámico al reservorio")
def apply_curve(project_id: uuid.UUID, well_id: str, session: SessionDep) -> CurveApplied:
    project, latest, model, well = _load(session, project_id, well_id, None)
    calc = _calc(model, well, "trazo")
    res_id = well.properties.node
    pump = next((lk for lk in model.network.links() if lk.properties.kind == "pump"
                 and res_id is not None and lk.properties.from_node == res_id), None)
    if pump is None:
        raise HTTPException(status_code=422, detail="El pozo no tiene un reservorio asociado con una bomba que salga de él.")
    pump.properties.curve_points = calc.curve_points
    pump.properties.pump_power = None
    pump.properties.pump_curve = None
    head = None
    for n in model.network.nodes():
        if n.id == res_id:
            n.properties.head = head = round(calc.dynamic_level_elevation, 4)
    v = create_version(session, project, model, kind="manual", label=f"Curva de bomba desde el pozo {well.id}",
                       parent=latest)
    session.commit()
    return CurveApplied(version=v.number, pump=pump.id, curve_points=calc.curve_points, reservoir=res_id,
                        reservoir_head=head)
