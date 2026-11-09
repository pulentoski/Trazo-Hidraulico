"""Diagnóstico automático e informe técnico."""
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.schemas.diagnosis import DiagnosisResult
from app.schemas.simulation import SimulationBlocked
from app.services import diagnosis, tech_report
from app.services.network import get_project_or_404

router = APIRouter(prefix="/projects/{project_id}", tags=["diagnóstico"])
SessionDep = Annotated[Session, Depends(get_session)]
BLOCKED = {422: {"model": SimulationBlocked, "description": "Errores bloqueantes: no se simuló"}}


@router.get("/diagnosis", response_model=DiagnosisResult, responses=BLOCKED,
            summary="Diagnóstico de la simulación en español simple, con sugerencias verificadas")
def get_diagnosis(project_id: uuid.UUID, session: SessionDep,
                  version: Annotated[int | None, Query()] = None) -> DiagnosisResult:
    return diagnosis.diagnose(session, get_project_or_404(session, project_id), version)


@router.get("/report.html", response_class=Response, responses={200: {"content": {"text/html": {}}}, **BLOCKED},
            summary="Informe técnico (HTML imprimible): proyecto, criterios, resultados, gráficos y diagnóstico")
def report(project_id: uuid.UUID, session: SessionDep, version: Annotated[int | None, Query()] = None) -> Response:
    html = tech_report.build(session, get_project_or_404(session, project_id), version)
    return Response(content=html, media_type="text/html; charset=utf-8")
