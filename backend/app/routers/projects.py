import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_session
from app.repositories import projects as projects_repo
from app.schemas.project import ImportResult, ProjectCreate, ProjectOut, ProjectUpdate, VersionOut
from app.services import auth
from app.services import projects as svc
from app.services.network import get_project_or_404, get_version_or_404

router = APIRouter(prefix="/projects", tags=["proyectos"])
SessionDep = Annotated[Session, Depends(get_session)]


@router.get("", response_model=list[ProjectOut], summary="Listar proyectos")
def list_projects(session: SessionDep,
                  org: Annotated[uuid.UUID | None, Query(description="Organización (todas las suyas si se omite)")] = None
                  ) -> list[ProjectOut]:
    p = auth.principal()
    orgs = [o for o in p.roles if org is None or o == org]
    out = []
    rows = projects_repo.list_projects(session, orgs)
    stats = projects_repo.latest_stats(session, [p.id for p, _, _ in rows])
    for project, latest, count in rows:
        item = ProjectOut.model_validate(project)
        item.latest_version, item.version_count = latest, count
        item.client_count, item.network_km = stats.get(project.id, (0, 0.0))
        out.append(item)
    return out


@router.post("", response_model=ProjectOut, status_code=status.HTTP_201_CREATED, summary="Crear proyecto")
def create_project(body: ProjectCreate, session: SessionDep) -> ProjectOut:
    try:
        project = svc.create_project(session, body)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return svc.project_out(session, project)


@router.post("/import", response_model=ImportResult, status_code=status.HTTP_201_CREATED,
             summary="Importar un archivo .inp como proyecto nuevo")
def import_project(
    session: SessionDep,
    file: Annotated[UploadFile, File(description="Archivo .inp de EPANET")],
    name: Annotated[str | None, Form()] = None,
    crs: Annotated[str, Form(description="auto, local o EPSG:xxxx de las coordenadas del archivo")] = "auto",
) -> ImportResult:
    max_mb = get_settings().max_inp_mb
    content = file.file.read(max_mb * 1024 * 1024 + 1)
    if len(content) > max_mb * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"El archivo supera {max_mb} MB")
    try:
        return svc.import_inp(session, file.filename or "red.inp", content, name=name, crs=crs)
    except svc.InpImportError as exc:
        raise HTTPException(status_code=422, detail={"message": "El archivo .inp tiene errores",
                                                     "engine_messages": [m.model_dump() for m in exc.messages]}) from exc


@router.get("/{project_id}", response_model=ProjectOut, summary="Obtener proyecto")
def get_project(project_id: uuid.UUID, session: SessionDep) -> ProjectOut:
    return svc.project_out(session, get_project_or_404(session, project_id))


@router.patch("/{project_id}", response_model=ProjectOut, summary="Editar datos del proyecto")
def update_project(project_id: uuid.UUID, body: ProjectUpdate, session: SessionDep) -> ProjectOut:
    project = get_project_or_404(session, project_id)
    try:
        project = svc.update_project(session, project, body)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return svc.project_out(session, project)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Eliminar proyecto y sus versiones")
def delete_project(project_id: uuid.UUID, session: SessionDep) -> Response:
    project = get_project_or_404(session, project_id)
    session.delete(project)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{project_id}/versions", response_model=list[VersionOut], summary="Listar versiones (más reciente primero)")
def list_versions(project_id: uuid.UUID, session: SessionDep) -> list[VersionOut]:
    get_project_or_404(session, project_id)
    return [VersionOut(number=v.number, kind=v.kind, label=v.label, parent_number=v.parent_number,
                       created_at=v.created_at, content_sha256=v.content_sha256, node_count=n, link_count=lk,
                       has_results=r)
            for v, n, lk, r in projects_repo.list_versions(session, project_id)]


@router.get("/{project_id}/versions/{number}", response_model=VersionOut, summary="Obtener una versión")
def get_version(project_id: uuid.UUID, number: int, session: SessionDep) -> VersionOut:
    project = get_project_or_404(session, project_id)
    get_version_or_404(session, project, number)
    for v, n, lk, r in projects_repo.list_versions(session, project_id):
        if v.number == number:
            return VersionOut(number=v.number, kind=v.kind, label=v.label, parent_number=v.parent_number,
                              created_at=v.created_at, content_sha256=v.content_sha256, node_count=n,
                              link_count=lk, has_results=r)
    raise HTTPException(status_code=404, detail="Versión no encontrada")


@router.get("/{project_id}/export.inp", response_class=Response, summary="Exportar una versión como .inp",
            responses={200: {"content": {"text/plain": {}}}})
def export_inp(project_id: uuid.UUID, session: SessionDep,
               version: Annotated[int | None, Query(description="Número de versión (última si se omite)")] = None
               ) -> Response:
    project = get_project_or_404(session, project_id)
    text, filename = svc.export_inp(session, project, version)
    return Response(content=text.encode("latin-1", errors="replace"), media_type="text/plain; charset=latin-1",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})
