"""Ortofotos georreferenciadas por proyecto (capas bajo la red)."""
import os
import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, Response, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.core.config import get_settings
from app.schemas.sig import GcpFit, GcpRequest, OrthophotoOut, OrthophotoUpdate, UploadInit, UploadState
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
        raise _ortho_error(exc) from exc
    return svc.out(o)


def _ortho_error(exc: svc.OrthoError) -> HTTPException:
    if isinstance(exc, svc.DiskFull):
        return HTTPException(status_code=507, detail=str(exc))
    return HTTPException(status_code=413 if "límite" in str(exc) else 422, detail=str(exc))


@router.post("/uploads", response_model=UploadState, status_code=status.HTTP_201_CREATED,
             summary="Iniciar una subida por partes (reanudable): verifica tamaño, cupo y espacio en disco")
def start_upload(project_id: uuid.UUID, body: UploadInit, session: SessionDep) -> UploadState:
    project = get_project_or_404(session, project_id)
    try:
        return svc.init_upload(session, project, body)
    except svc.OrthoError as exc:
        raise _ortho_error(exc) from exc


@router.get("/{ortho_id}/upload", response_model=UploadState, summary="Estado de una subida (para retomarla)")
def upload_status(project_id: uuid.UUID, ortho_id: uuid.UUID, session: SessionDep) -> UploadState:
    project = get_project_or_404(session, project_id)
    return svc.upload_state(svc.get(session, project, ortho_id))


@router.put("/{ortho_id}/upload", response_model=UploadState, summary="Agregar una parte (cuerpo binario) en `offset`",
            responses={409: {"description": "La parte no empieza en el byte esperado: retomar desde `offset`"}},
            openapi_extra={"requestBody": {"content": {"application/octet-stream": {"schema": {"type": "string",
                                                                                                "format": "binary"}}}}})
async def upload_part(project_id: uuid.UUID, ortho_id: uuid.UUID, request: Request, session: SessionDep,
                      offset: Annotated[int, Query(ge=0, description="Byte inicial de la parte")]):
    limit = 2 * get_settings().ortho_part_mb * 1024 * 1024
    declared = int(request.headers.get("content-length") or 0)
    if declared > limit:
        raise HTTPException(status_code=413, detail="La parte supera el tamaño máximo por parte.")
    buf = bytearray()
    async for piece in request.stream():
        buf += piece
        if len(buf) > limit:
            raise HTTPException(status_code=413, detail="La parte supera el tamaño máximo por parte.")

    def work():
        project = get_project_or_404(session, project_id)
        return svc.append_chunk(session, project, svc.get(session, project, ortho_id), offset, bytes(buf))
    try:
        return await run_in_threadpool(work)
    except svc.OffsetMismatch as exc:
        return JSONResponse(status_code=409, content={"detail": str(exc), "offset": exc.offset})
    except svc.OrthoError as exc:
        raise _ortho_error(exc) from exc


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
        if body.save:
            return svc.save_gcps(session, project, o, body.gcps)
        return svc.fit_gcps(body.gcps, project.length_srid, (o.width, o.height) if o.width and o.height else None)
    except svc.OrthoError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
