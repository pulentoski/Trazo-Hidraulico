"""Formato de proyecto .trazo (exportar e importar)."""
import os
import tempfile
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from starlette.background import BackgroundTask
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
                 version: Annotated[int | None, Query(description="Número de versión (última si se omite)")] = None,
                 ortofotos: Annotated[bool, Query(description="Incluir los archivos de las ortofotos")] = False
                 ) -> Response:
    project = get_project_or_404(session, project_id)
    if not ortofotos:
        data, filename = trazo.export(session, project, version)
        return Response(content=data, media_type="application/zip",
                        headers={"Content-Disposition": f'attachment; filename="{filename}"'})
    # Con imágenes el zip puede pesar cientos de MB: se arma en disco (volumen de ortofotos) y se envía por partes.
    tmpdir = os.path.join(get_settings().ortho_dir, ".tmp")
    os.makedirs(tmpdir, exist_ok=True)
    fd, path = tempfile.mkstemp(suffix=".trazo", dir=tmpdir)
    try:
        with os.fdopen(fd, "wb") as fh:
            _, filename = trazo.export(session, project, version, include_orthos=True, dest=fh)
    except Exception:
        os.remove(path)
        raise
    return FileResponse(path, media_type="application/zip", filename=filename,
                        background=BackgroundTask(os.remove, path))


@router.post("/projects/import-trazo", response_model=TrazoImportResult, status_code=status.HTTP_201_CREATED,
             summary="Importar un archivo .trazo como proyecto nuevo")
def import_trazo(session: SessionDep, file: Annotated[UploadFile, File(description="Archivo .trazo")],
                 name: Annotated[str | None, Form()] = None) -> TrazoImportResult:
    # Puede traer ortofotos: se copia a disco (volumen de ortofotos) con el límite ORTHO_MAX_MB.
    s = get_settings()
    limit = max(s.max_inp_mb, s.max_ortho_mb) * 1024 * 1024
    tmpdir = os.path.join(s.ortho_dir, ".tmp")
    os.makedirs(tmpdir, exist_ok=True)
    fd, path = tempfile.mkstemp(suffix=".trazo", dir=tmpdir)
    try:
        size = 0
        with os.fdopen(fd, "wb") as fh:
            while chunk := file.file.read(4 * 1024 * 1024):
                size += len(chunk)
                if size > limit:
                    raise HTTPException(status_code=413, detail=f"El archivo supera {limit // 1024 // 1024} MB")
                fh.write(chunk)
        try:
            project, version, notes = trazo.import_file(session, file.filename or "proyecto.trazo", path, name=name)
        except trazo.TrazoError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except InpImportError as exc:
            raise HTTPException(status_code=422, detail="El .inp del .trazo tiene errores") from exc
    finally:
        os.remove(path)
    return TrazoImportResult(project=project_out(session, project), version=version, notes=notes)
