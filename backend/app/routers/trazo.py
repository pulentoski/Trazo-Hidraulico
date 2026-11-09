"""Formato de proyecto .trazo (exportar e importar)."""
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_session
from app.hydraulic.inp_reader import InpImportError
from app.schemas.project import ProjectOut
from app.services import trazo
from app.services.network import get_project_or_404
from app.services.projects import project_out

router = APIRouter(tags=["formato .trazo"])
SessionDep = Annotated[Session, Depends(get_session)]


class TrazoImportResult(BaseModel):
    project: ProjectOut
    version: int
    notes: list[str]


@router.get("/projects/{project_id}/export.trazo", response_class=Response,
            responses={200: {"content": {"application/zip": {}}}},
            summary="Exportar el proyecto como .trazo (zip: .inp + datos propios en JSON)")
def export_trazo(project_id: uuid.UUID, session: SessionDep,
                 version: Annotated[int | None, Query(description="Número de versión (última si se omite)")] = None
                 ) -> Response:
    data, filename = trazo.export(session, get_project_or_404(session, project_id), version)
    return Response(content=data, media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.post("/projects/import-trazo", response_model=TrazoImportResult, status_code=status.HTTP_201_CREATED,
             summary="Importar un archivo .trazo como proyecto nuevo")
def import_trazo(session: SessionDep, file: Annotated[UploadFile, File(description="Archivo .trazo")],
                 name: Annotated[str | None, Form()] = None) -> TrazoImportResult:
    limit = get_settings().max_inp_mb * 1024 * 1024
    content = file.file.read(limit + 1)
    if len(content) > limit:
        raise HTTPException(status_code=413, detail=f"El archivo supera {get_settings().max_inp_mb} MB")
    try:
        project, version, notes = trazo.import_file(session, file.filename or "proyecto.trazo", content, name=name)
    except trazo.TrazoError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except InpImportError as exc:
        raise HTTPException(status_code=422, detail="El .inp del .trazo tiene errores") from exc
    return TrazoImportResult(project=project_out(session, project), version=version, notes=notes)
