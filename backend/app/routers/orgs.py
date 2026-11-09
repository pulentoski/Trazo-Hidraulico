"""Organizaciones: miembros, invitaciones, roles, auditoría y uso (administrador de la organización);
gestión de la plataforma (superadministrador); conteo de cargas de mapa; revisiones de versiones."""
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.models import AuditLog, Membership, Organization, Project, ProjectVersion, User, VersionReview
from app.schemas.auth import (AuditOut, InviteIn, LinkOut, MapLoadOut, MemberOut, MemberUpdate, OrgAdminOut, OrgCreate,
                              OrgCreated, OrgOut, OrgRef, OrgUpdate, ReviewIn, ReviewOut, Usage, UserAdminOut,
                              UserAdminUpdate)
from app.services import auth
from app.services.network import get_project_or_404, get_version_or_404

router = APIRouter(tags=["organizaciones"])
SessionDep = Annotated[Session, Depends(get_session)]


def _org(session: Session, org_id: uuid.UUID) -> Organization:
    org = session.get(Organization, org_id)
    if org is None:
        raise auth.AuthError(404, "Organización no encontrada.")
    return org


def usage_of(session: Session, org: Organization) -> Usage:
    return Usage(month=auth.month(), simulations=auth.usage_count(session, org.id, "simulation"),
                 map_loads=auth.usage_count(session, org.id, "map_load"),
                 ortho_mb=round(auth.ortho_bytes(session, org.id) / 1024 / 1024, 2),
                 projects=session.scalar(select(func.count()).select_from(Project).where(Project.org_id == org.id)) or 0,
                 limits=auth.limits_for(org))


# ── Administrador de la organización ──

@router.get("/orgs/{org_id}/members", response_model=list[MemberOut], summary="Miembros de la organización")
def members(org_id: uuid.UUID, session: SessionDep) -> list[MemberOut]:
    auth.require_org_perm(org_id, "manage")
    rows = session.execute(select(Membership, User).join(User, User.id == Membership.user_id)
                           .where(Membership.org_id == org_id).order_by(User.email)).all()
    return [MemberOut(user_id=u.id, email=u.email, name=u.name, role=m.role, active=m.active and u.active,
                      mfa_enabled=u.mfa_enabled, last_login_at=u.last_login_at) for m, u in rows]


@router.post("/orgs/{org_id}/invitations", response_model=LinkOut, status_code=201,
             summary="Invitar por correo o con un enlace de un solo uso")
def invite(org_id: uuid.UUID, body: InviteIn, session: SessionDep) -> LinkOut:
    p = auth.require_org_perm(org_id, "manage")
    org = _org(session, org_id)
    url = auth.invitation_link(session, org_id, body.email, body.role, p.user_id)
    auth.audit(session, "permiso.invitacion", org_id=org_id, detail={"email": body.email, "rol": body.role})
    session.commit()
    emailed = body.send_email and auth.send_mail(
        body.email, f"Invitación a {org.name} en Trazo Hidráulico",
        f"Lo invitaron a la organización «{org.name}» con el rol {body.role}. Acepte en este enlace (válido "
        f"{auth.get_settings().invite_token_days} días):\n\n{url}")
    return LinkOut(link=url, emailed=emailed)


@router.patch("/orgs/{org_id}/members/{user_id}", response_model=MemberOut, summary="Cambiar rol o desactivar")
def update_member(org_id: uuid.UUID, user_id: uuid.UUID, body: MemberUpdate, session: SessionDep) -> MemberOut:
    p = auth.require_org_perm(org_id, "manage")
    m = session.get(Membership, (user_id, org_id))
    if m is None:
        raise auth.AuthError(404, "Miembro no encontrado.")
    if user_id == p.user_id and (body.active is False or (body.role and body.role != "admin")):
        raise auth.AuthError(400, "No puede quitarse a sí mismo el rol de administrador.")
    before = {"rol": m.role, "activo": m.active}
    if body.role is not None:
        m.role = body.role
    if body.active is not None:
        m.active = body.active
    admins = session.scalar(select(func.count()).select_from(Membership).where(
        Membership.org_id == org_id, Membership.role == "admin", Membership.active.is_(True)))
    if not admins:
        raise auth.AuthError(400, "La organización debe conservar al menos un administrador activo.")
    auth.audit(session, "permiso.cambio", org_id=org_id, detail={"usuario": str(user_id), "antes": before,
                                                                 "despues": {"rol": m.role, "activo": m.active}})
    session.commit()
    u = session.get(User, user_id)
    return MemberOut(user_id=u.id, email=u.email, name=u.name, role=m.role, active=m.active and u.active,
                     mfa_enabled=u.mfa_enabled, last_login_at=u.last_login_at)


@router.post("/orgs/{org_id}/members/{user_id}/reset-link", response_model=LinkOut,
             summary="Enlace de un solo uso para crear una contraseña nueva (sin correo saliente)")
def reset_link(org_id: uuid.UUID, user_id: uuid.UUID, session: SessionDep) -> LinkOut:
    p = auth.require_org_perm(org_id, "manage")
    if session.get(Membership, (user_id, org_id)) is None:
        raise auth.AuthError(404, "Miembro no encontrado.")
    user = session.get(User, user_id)
    if user.is_superadmin and not p.is_superadmin:
        raise auth.AuthError(403, "No puede restablecer la contraseña de un superadministrador.", "forbidden")
    url = auth.reset_link_for(session, user, created_by=p.user_id)
    auth.audit(session, "permiso.enlace_recuperacion", org_id=org_id, detail={"usuario": user.email})
    session.commit()
    return LinkOut(link=url)


@router.get("/orgs/{org_id}/audit", response_model=list[AuditOut], summary="Registro de auditoría")
def audit_log(org_id: uuid.UUID, session: SessionDep, limit: Annotated[int, Query(ge=1, le=1000)] = 200,
              action: Annotated[str | None, Query(max_length=60)] = None) -> list[AuditOut]:
    auth.require_org_perm(org_id, "manage")
    member_ids = select(Membership.user_id).where(Membership.org_id == org_id)
    q = select(AuditLog).where((AuditLog.org_id == org_id) | ((AuditLog.org_id.is_(None)) & AuditLog.user_id.in_(member_ids)
                                                             & AuditLog.action.startswith("login")))
    if action:
        q = q.where(AuditLog.action.startswith(action))
    rows = session.scalars(q.order_by(AuditLog.id.desc()).limit(limit))
    return [AuditOut(id=a.id, created_at=a.created_at, user_email=a.user_email, action=a.action, project_id=a.project_id,
                     version=a.version, detail=a.detail, ip=a.ip) for a in rows]


@router.get("/orgs/{org_id}/usage", response_model=Usage, summary="Uso del mes y límites del plan")
def org_usage(org_id: uuid.UUID, session: SessionDep) -> Usage:
    auth.require_org_perm(org_id, "manage")
    return usage_of(session, _org(session, org_id))


@router.post("/usage/map-load", response_model=MapLoadOut, summary="Contar una carga del mapa de Google")
def map_load(session: SessionDep) -> MapLoadOut:
    p = auth.principal()
    if p.org_id is None:
        return MapLoadOut(allowed=False, count=0, limit=0)
    org = _org(session, p.org_id)
    cap = auth.limits_for(org).get("max_map_loads_month")
    n = auth.usage_count(session, org.id, "map_load")
    if cap is not None and n >= cap:
        return MapLoadOut(allowed=False, count=n, limit=cap)
    auth.add_usage(session, org.id, "map_load")
    session.commit()
    return MapLoadOut(allowed=True, count=n + 1, limit=cap)


# ── Revisiones de versiones (revisor) ──

@router.get("/projects/{project_id}/versions/{number}/reviews", response_model=list[ReviewOut],
            summary="Comentarios y aprobaciones de una versión")
def reviews(project_id: uuid.UUID, number: int, session: SessionDep) -> list[ReviewOut]:
    project = get_project_or_404(session, project_id)
    v = get_version_or_404(session, project, number)
    rows = session.scalars(select(VersionReview).where(VersionReview.version_id == v.id).order_by(VersionReview.id))
    return [ReviewOut(id=r.id, version=number, user_email=r.user_email, status=r.status, comment=r.comment,
                      created_at=r.created_at) for r in rows]


@router.post("/projects/{project_id}/versions/{number}/reviews", response_model=ReviewOut, status_code=201,
             summary="Comentar, aprobar u observar una versión (revisor o administrador)")
def add_review(project_id: uuid.UUID, number: int, body: ReviewIn, session: SessionDep) -> ReviewOut:
    project = get_project_or_404(session, project_id)
    v = get_version_or_404(session, project, number)
    p = auth.principal()
    r = VersionReview(version_id=v.id, user_id=p.user_id, user_email=p.email, status=body.status, comment=body.comment)
    session.add(r)
    auth.audit(session, f"revision.{body.status}", org_id=project.org_id, project_id=project.id, version=number,
               detail={"comentario": body.comment[:200]})
    session.commit()
    return ReviewOut(id=r.id, version=number, user_email=r.user_email, status=r.status, comment=r.comment,
                     created_at=r.created_at)


# ── Superadministrador de plataforma ──

@router.get("/admin/orgs", response_model=list[OrgAdminOut], summary="Organizaciones con su uso")
def admin_orgs(session: SessionDep) -> list[OrgAdminOut]:
    auth.require_superadmin()
    out = []
    for org in session.scalars(select(Organization).order_by(Organization.name)):
        n = session.scalar(select(func.count()).select_from(Membership).where(Membership.org_id == org.id)) or 0
        out.append(OrgAdminOut(**OrgOut.model_validate(org).model_dump(), members=n, usage=usage_of(session, org)))
    return out


@router.post("/admin/orgs", response_model=OrgCreated, status_code=201, summary="Crear una organización")
def admin_create_org(body: OrgCreate, session: SessionDep) -> OrgCreated:
    p = auth.require_superadmin()
    if session.scalar(select(Organization).where(func.lower(Organization.name) == body.name.strip().lower())):
        raise auth.AuthError(409, "Ya existe una organización con ese nombre.")
    org = Organization(id=uuid.uuid4(), name=body.name.strip(), kind=body.kind, plan=body.plan)
    session.add(org)
    session.flush()
    url = auth.invitation_link(session, org.id, body.admin_email, "admin", p.user_id) if body.admin_email else None
    auth.audit(session, "organizacion.creada", org_id=org.id, detail={"nombre": org.name, "plan": org.plan})
    session.commit()
    return OrgCreated(org=OrgOut.model_validate(org), admin_invitation=url)


@router.patch("/admin/orgs/{org_id}", response_model=OrgOut, summary="Plan, límites, nombre o suspensión")
def admin_update_org(org_id: uuid.UUID, body: OrgUpdate, session: SessionDep) -> OrgOut:
    auth.require_superadmin()
    org = _org(session, org_id)
    data = body.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(org, k, v)
    auth.audit(session, "organizacion.cambio", org_id=org.id, detail={k: v for k, v in data.items()})
    session.commit()
    return OrgOut.model_validate(org)


@router.get("/admin/users", response_model=list[UserAdminOut], summary="Usuarios de la plataforma")
def admin_users(session: SessionDep) -> list[UserAdminOut]:
    auth.require_superadmin()
    orgs = dict(session.execute(select(Organization.id, Organization.name)).all())
    out = []
    for u in session.scalars(select(User).order_by(User.email)):
        ms = session.scalars(select(Membership).where(Membership.user_id == u.id))
        out.append(UserAdminOut(id=u.id, email=u.email, name=u.name, active=u.active, is_superadmin=u.is_superadmin,
                                mfa_enabled=u.mfa_enabled, locked=bool(u.locked_until and u.locked_until > auth.now()),
                                last_login_at=u.last_login_at,
                                orgs=[OrgRef(id=m.org_id, name=orgs.get(m.org_id, "?"), role=m.role) for m in ms]))
    return out


@router.patch("/admin/users/{user_id}", response_model=UserAdminOut, summary="Suspender o reactivar una cuenta")
def admin_update_user(user_id: uuid.UUID, body: UserAdminUpdate, session: SessionDep) -> UserAdminOut:
    p = auth.require_superadmin()
    u = session.get(User, user_id)
    if u is None:
        raise auth.AuthError(404, "Usuario no encontrado.")
    if body.active is not None:
        if u.id == p.user_id and not body.active:
            raise auth.AuthError(400, "No puede suspender su propia cuenta.")
        u.active = body.active
        if not body.active:
            auth.revoke_user_sessions(session, u.id)
        auth.audit(session, "cuenta.suspendida" if not body.active else "cuenta.reactivada", detail={"usuario": u.email})
    session.commit()
    return next(x for x in admin_users(session) if x.id == u.id)


@router.post("/admin/users/{user_id}/reset-link", response_model=LinkOut, summary="Enlace de recuperación (plataforma)")
def admin_reset_link(user_id: uuid.UUID, session: SessionDep) -> LinkOut:
    p = auth.require_superadmin()
    u = session.get(User, user_id)
    if u is None:
        raise auth.AuthError(404, "Usuario no encontrado.")
    url = auth.reset_link_for(session, u, created_by=p.user_id)
    auth.audit(session, "permiso.enlace_recuperacion", detail={"usuario": u.email})
    session.commit()
    return LinkOut(link=url)


__all__ = ["ProjectVersion", "Response", "router"]
