"""Ortofotos georreferenciadas por proyecto (capas bajo la red)."""
import os
import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.schemas.sig import GcpFit, GcpRequest, OrthophotoOut, OrthophotoUpdate
from app.services import orthophotos as svc
from app.services.network import get_project_or_404

router = APIRouter(prefix="/projects/{project_id}/orthophotos", tags=["ortofotos"])
SessionDep = Annotated[Session, Depends(get_session)]


@router.get("", response_model=list[OrthophotoOut], summary="Ortofotos del proyecto (más reciente primero)")
def list_orthophotos(project_id: uuid.UUID, session: SessionDep) -> list[OrthophotoOut]:
    project = get_project_or_404(session, project_id)
    return [svc.out(o) for o in svc.list_for(session, project)]


@router.post("", response_model=OrthophotoOut, status_code=status.HTTP_201_CREATED,
             summary="Subir una ortofoto (GeoTIFF, o JPG/PNG con archivo world o para ajustar con puntos de control)")
def upload_orthophoto(project_id: uuid.UUID, session: SessionDep,
                      file: Annotated[UploadFile, File(description="GeoTIFF, JPG o PNG")],
                      world: Annotated[UploadFile | None, File(description="Archivo world (.jgw/.pgw/.wld)")] = None,
                      name: Annotated[str | None, Form()] = None,
                      source: Annotated[str | None, Form()] = None,
                      captured_on: Annotated[date | None, Form()] = None,
                      src_crs: Annotated[str | None, Form(description="EPSG del archivo world (UTM del proyecto)")] = None
                      ) -> OrthophotoOut:
    project = get_project_or_404(session, project_id)
    try:
        o = svc.upload(session, project, file, world, name=name, source=source, captured_on=captured_on,
                       src_crs=src_crs)
    except svc.OrthoError as exc:
        code = 413 if "límite" in str(exc) else 422
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    return svc.out(o)


@router.patch("/{ortho_id}", response_model=OrthophotoOut, summary="Editar nombre, fecha, fuente, opacidad o visibilidad")
def update_orthophoto(project_id: uuid.UUID, ortho_id: uuid.UUID, body: OrthophotoUpdate,
                      session: SessionDep) -> OrthophotoOut:
    project = get_project_or_404(session, project_id)
    return svc.out(svc.update(session, svc.get(session, project, ortho_id), body))


@router.delete("/{ortho_id}", status_code=204, summary="Eliminar una ortofoto y sus archivos")
def delete_orthophoto(project_id: uuid.UUID, ortho_id: uuid.UUID, session: SessionDep) -> Response:
    project = get_project_or_404(session, project_id)
    svc.delete(session, svc.get(session, project, ortho_id))
    return Response(status_code=204)


@router.get("/{ortho_id}/original", response_class=FileResponse, summary="Imagen original (para puntos de control)")
def original(project_id: uuid.UUID, ortho_id: uuid.UUID, session: SessionDep) -> FileResponse:
    project = get_project_or_404(session, project_id)
    o = svc.get(session, project, ortho_id)
    if o.original_ext not in ("jpg", "jpeg", "png"):
        raise HTTPException(status_code=404, detail="Solo se sirven imágenes JPG o PNG")
    path = os.path.join(svc.ortho_dir(o.id), f"original.{o.original_ext}")
    media = "image/png" if o.original_ext == "png" else "image/jpeg"
    return FileResponse(path, media_type=media)


@router.post("/{ortho_id}/gcps", response_model=GcpFit,
             summary="Ajustar con puntos de control (mínimo 2): error residual y, si apply, procesar")
def gcps(project_id: uuid.UUID, ortho_id: uuid.UUID, body: GcpRequest, session: SessionDep) -> GcpFit:
    project = get_project_or_404(session, project_id)
    o = svc.get(session, project, ortho_id)
    try:
        if body.apply:
            return svc.apply_gcps(session, project, o, body.gcps)
        return svc.fit_gcps(body.gcps, project.length_srid)
    except svc.OrthoError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
