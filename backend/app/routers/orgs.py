"""Organizaciones: datos, miembros, invitaciones, roles, auditoría y uso (administrador de la organización);
Panel admin (superadministrador): resumen, organizaciones, planes y límites, usuarios y modo soporte; conteo de
cargas de mapa; revisiones de versiones.

Reglas de roles (validadas aquí, no solo en la interfaz): nadie asigna un rol superior al propio, la organización
conserva siempre un administrador activo, el administrador no toca plan, límites, suspensión ni superadministradores,
y todo cambio queda en la auditoría."""
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.models import (AuditLog, Membership, OneTimeToken, Organization, Orthophoto, Project, ProjectVersion, User,
                        UserSession, VersionReview)
from app.schemas.auth import (AdminOverview, AuditOut, InvitationOut, InviteIn, LimitUse, LinkOut, MapLoadOut, MemberOut,
                              MemberUpdate, NearLimit, OrgAdminOut, OrgCreate, OrgCreated, OrgDataUpdate, OrgDelete,
                              OrgDetail, OrgOut, OrgRef, OrgSettings, OrgUpdate, PlansUpdate, ReviewIn, ReviewOut,
                              ServiceStatus, SystemInfo, Usage, UserAdminOut, UserAdminUpdate)
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
                 users=auth.active_users(session, org.id), pending_invitations=auth.pending_invitations(session, org.id),
                 invitations_today=auth.invitations_today(session, org.id),
                 invite_days=auth.get_settings().invite_token_days, limits=auth.limits_for(org))


LIMIT_LABELS = {"max_users": ("users", "Usuarios"), "max_projects": ("projects", "Proyectos"),
                "max_simulations_month": ("simulations", "Simulaciones del mes"),
                "max_map_loads_month": ("map_loads", "Cargas de mapa del mes"), "max_ortho_mb": ("ortho_mb", "Ortofotos (MB)"),
                "max_invites_day": ("invitations_today", "Invitaciones de hoy")}


def limits_use(u: Usage) -> list[LimitUse]:
    out = []
    for key, (field, label) in LIMIT_LABELS.items():
        used, cap = float(getattr(u, field)), u.limits.get(key)
        out.append(LimitUse(key=key, label=label, used=used, limit=cap,
                            ratio=None if cap is None else (used / cap if cap else 1.0)))
    return out


def _member_rows(session: Session, org_id: uuid.UUID) -> list[MemberOut]:
    rows = session.execute(select(Membership, User).join(User, User.id == Membership.user_id)
                           .where(Membership.org_id == org_id).order_by(User.email)).all()
    return [MemberOut(user_id=u.id, email=u.email, name=u.name, role=m.role, active=m.active and u.active,
                      mfa_enabled=u.mfa_enabled, last_login_at=u.last_login_at) for m, u in rows]


# ── Administrador de la organización ──

@router.get("/orgs/{org_id}", response_model=OrgOut, summary="Datos de la organización (miembros)")
def org_data(org_id: uuid.UUID, session: SessionDep) -> OrgOut:
    auth.require_org_perm(org_id, "view")
    return OrgOut.model_validate(_org(session, org_id))


@router.patch("/orgs/{org_id}", response_model=OrgOut, summary="Nombre, tipo y datos de la organización (administrador)")
def update_org_data(org_id: uuid.UUID, body: OrgDataUpdate, session: SessionDep) -> OrgOut:
    auth.require_org_perm(org_id, "manage")
    org = _org(session, org_id)
    data = body.model_dump(exclude_unset=True)
    if data.get("name"):
        name = data["name"].strip()
        dup = session.scalar(select(Organization).where(func.lower(Organization.name) == name.lower(), Organization.id != org.id))
        if dup is not None:
            raise auth.AuthError(409, "Ya existe una organización con ese nombre.")
        org.name = name
    if data.get("kind"):
        org.kind = data["kind"]
    if "info" in data:
        org.info = {k: v for k, v in (data["info"] or {}).items() if v not in (None, "")} or None
    auth.audit(session, "organizacion.datos", org_id=org.id, detail={k: v for k, v in data.items() if k != "info"} |
               ({"datos": sorted((data.get("info") or {}).keys())} if "info" in data else {}))
    session.commit()
    return OrgOut.model_validate(org)


@router.get("/orgs/{org_id}/members", response_model=list[MemberOut], summary="Miembros de la organización")
def members(org_id: uuid.UUID, session: SessionDep) -> list[MemberOut]:
    auth.require_org_perm(org_id, "manage")
    return _member_rows(session, org_id)


@router.get("/orgs/{org_id}/invitations", response_model=list[InvitationOut], summary="Invitaciones vigentes")
def invitations(org_id: uuid.UUID, session: SessionDep) -> list[InvitationOut]:
    auth.require_org_perm(org_id, "manage")
    rows = session.scalars(select(OneTimeToken).where(
        OneTimeToken.org_id == org_id, OneTimeToken.purpose == "invite", OneTimeToken.used_at.is_(None),
        OneTimeToken.expires_at > auth.now()).order_by(OneTimeToken.created_at.desc()))
    return [InvitationOut(id=t.token_hash[:16], email=t.email or "", role=t.role, created_at=t.created_at,
                          expires_at=t.expires_at) for t in rows]


@router.delete("/orgs/{org_id}/invitations/{inv_id}", status_code=204, summary="Anular una invitación")
def revoke_invitation(org_id: uuid.UUID, inv_id: str, session: SessionDep) -> Response:
    auth.require_org_perm(org_id, "manage")
    t = session.scalars(select(OneTimeToken).where(
        OneTimeToken.org_id == org_id, OneTimeToken.purpose == "invite", OneTimeToken.used_at.is_(None),
        OneTimeToken.token_hash.startswith(inv_id[:16]))).first() if len(inv_id) >= 16 else None
    if t is None:
        raise auth.AuthError(404, "Invitación no encontrada.")
    t.used_at = auth.now()
    auth.audit(session, "permiso.invitacion_anulada", org_id=org_id, detail={"email": t.email, "rol": t.role})
    session.commit()
    return Response(status_code=204)


@router.post("/orgs/{org_id}/invitations", response_model=LinkOut, status_code=201,
             summary="Invitar por correo o con un enlace de un solo uso")
def invite(org_id: uuid.UUID, body: InviteIn, session: SessionDep) -> LinkOut:
    p = auth.require_org_perm(org_id, "manage")
    org = _org(session, org_id)
    auth.check_assignable(p, org_id, body.role)
    existing = auth.user_by_email(session, body.email)
    if existing is not None:
        m = session.get(Membership, (existing.id, org_id))
        if m is not None and m.active:
            raise auth.AuthError(409, "Esa persona ya es miembro activo de la organización.")
    auth.check_invite_limits(session, org)
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
    target = session.get(User, user_id)
    if target.is_superadmin and not p.is_superadmin:
        raise auth.AuthError(403, "No puede cambiar el rol de un superadministrador.", "forbidden")
    if user_id == p.user_id and (body.active is False or (body.role and body.role != "admin")):
        raise auth.AuthError(400, "No puede quitarse a sí mismo el rol de administrador.")
    if body.role is not None:
        auth.check_assignable(p, org_id, body.role)
    before = {"rol": m.role, "activo": m.active}
    if body.active and not m.active:
        auth.check_user_limit(session, _org(session, org_id))
    if body.role is not None:
        m.role = body.role
    if body.active is not None:
        m.active = body.active
    session.flush()
    if not auth.active_admins(session, org_id):
        session.rollback()
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


@router.get("/orgs/{org_id}/settings", response_model=OrgSettings, summary="Ajustes de la organización")
def org_settings(org_id: uuid.UUID, session: SessionDep) -> OrgSettings:
    auth.require_org_perm(org_id, "view")
    return settings_of(_org(session, org_id))


@router.put("/orgs/{org_id}/settings", response_model=OrgSettings,
            summary="Editar perfil de diseño por defecto, vida útil y precios (administrador)")
def put_org_settings(org_id: uuid.UUID, body: OrgSettings, session: SessionDep) -> OrgSettings:
    from app.repositories import catalog as catalog_repo

    auth.require_org_perm(org_id, "manage")
    org = _org(session, org_id)
    if body.default_profile_id is not None and catalog_repo.get_profile(session, body.default_profile_id) is None:
        raise auth.AuthError(422, "Perfil de diseño inexistente.")
    org.settings = body.model_dump(mode="json")
    auth.audit(session, "organizacion.ajustes", org_id=org_id,
               detail={"perfil": body.default_profile_id, "vida_util": bool(body.service_life), "precios": bool(body.prices)})
    session.commit()
    return settings_of(org)


def settings_of(org: Organization) -> OrgSettings:
    try:
        return OrgSettings.model_validate(org.settings or {})
    except ValueError:
        return OrgSettings()


# ── Superadministrador de plataforma ──

@router.get("/admin/system", response_model=SystemInfo, summary="Versión, motor, estado de servicios y último respaldo")
def admin_system(session: SessionDep) -> SystemInfo:
    import json
    import time

    from sqlalchemy import text

    from app.core.cache import get_redis
    from app.hydraulic.version import engine_info
    from app.models import PlatformSetting

    auth.require_superadmin()
    services = [ServiceStatus(name="API", status="ok")]
    try:
        session.execute(text("SELECT 1"))
        services.append(ServiceStatus(name="Base de datos", status="ok"))
    except Exception as exc:  # noqa: BLE001
        services.append(ServiceStatus(name="Base de datos", status="error", detail=str(exc)[:120]))
    try:
        r = get_redis()
        r.ping()
        services.append(ServiceStatus(name="Caché", status="ok"))
        beat = r.get("trazo:worker:heartbeat")
        if beat is None:
            services.append(ServiceStatus(name="Worker de ortofotos", status="sin datos", detail="sin latido registrado"))
        else:
            age = time.time() - float(beat)
            services.append(ServiceStatus(name="Worker de ortofotos", status="ok" if age < 120 else "error",
                                          detail=f"último latido hace {int(age)} s"))
    except Exception as exc:  # noqa: BLE001
        services.append(ServiceStatus(name="Caché", status="error", detail=str(exc)[:120]))
    row = session.get(PlatformSetting, "ultimo_respaldo")
    backup = None
    if row is not None:
        try:
            backup = json.loads(row.value)
        except ValueError:
            backup = {"detalle": row.value}
    from app.main import app as fastapi_app

    return SystemInfo(api_version=fastapi_app.version, engine=engine_info(), services=services, last_backup=backup,
                      plans=auth.plans(session))


@router.put("/admin/plans", response_model=dict[str, dict], summary="Editar los límites de cada plan")
def admin_plans(body: PlansUpdate, session: SessionDep) -> dict[str, dict]:
    import json

    from app.models import PlatformSetting

    p = auth.require_superadmin()
    for plan, lim in body.plans.items():
        bad = set(lim) - set(auth.LIMIT_KEYS)
        if bad:
            raise auth.AuthError(422, f"Límite desconocido en {plan}: {', '.join(sorted(bad))}.")
        if any(v is not None and v < 0 for v in lim.values()):
            raise auth.AuthError(422, "Los límites no pueden ser negativos (vacío = sin límite).")
    current = auth.plans(session)
    for plan, lim in body.plans.items():
        current[plan].update(lim)
    row = session.get(PlatformSetting, auth.PLANS_SETTING)
    if row is None:
        row = PlatformSetting(key=auth.PLANS_SETTING, value="{}", encrypted=False)
        session.add(row)
    row.value, row.updated_by = json.dumps(current), p.email
    auth.audit(session, "plataforma.planes", detail={k: dict(v) for k, v in body.plans.items()})
    session.commit()
    return auth.plans(session)


@router.get("/admin/overview", response_model=AdminOverview, summary="Resumen del Panel admin")
def admin_overview(session: SessionDep) -> AdminOverview:
    import shutil

    auth.require_superadmin()
    orgs = list(session.scalars(select(Organization)))
    near = []
    for org in orgs:
        if org.suspended:
            continue
        lu = [x for x in limits_use(usage_of(session, org)) if x.ratio is not None]
        worst = max(lu, key=lambda x: x.ratio, default=None)
        if worst is not None and worst.ratio >= 0.8:
            near.append(NearLimit(org=OrgOut.model_validate(org), worst=worst))
    near.sort(key=lambda x: -(x.worst.ratio or 0))
    disk = None
    try:
        disk = shutil.disk_usage(auth.get_settings().ortho_dir)
    except OSError:
        pass
    gb = 1024 ** 3
    ortho_n, ortho_b = session.execute(select(func.count(), func.coalesce(func.sum(Orthophoto.size_bytes), 0))
                                       .select_from(Orthophoto)).one()
    recent = session.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(12))
    return AdminOverview(
        orgs_active=sum(1 for o in orgs if not o.suspended), orgs_suspended=sum(1 for o in orgs if o.suspended),
        users_total=session.scalar(select(func.count()).select_from(User)) or 0,
        users_active=session.scalar(select(func.count()).select_from(User).where(User.active.is_(True))) or 0,
        projects_total=session.scalar(select(func.count()).select_from(Project)) or 0,
        ortho_count=int(ortho_n), ortho_mb=round(int(ortho_b) / 1024 / 1024, 2),
        disk_total_gb=round(disk.total / gb, 1) if disk else None, disk_used_gb=round(disk.used / gb, 1) if disk else None,
        disk_free_gb=round(disk.free / gb, 1) if disk else None, near_limit=near[:10],
        recent_audit=[AuditOut(id=a.id, created_at=a.created_at, user_email=a.user_email, action=a.action,
                               project_id=a.project_id, version=a.version, detail=a.detail, ip=a.ip) for a in recent])



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


@router.get("/admin/orgs/{org_id}", response_model=OrgDetail, summary="Ficha de una organización")
def admin_org_detail(org_id: uuid.UUID, session: SessionDep) -> OrgDetail:
    auth.require_superadmin()
    org = _org(session, org_id)
    u = usage_of(session, org)
    return OrgDetail(org=OrgOut.model_validate(org), usage=u, limits_use=limits_use(u), members=_member_rows(session, org_id))


@router.post("/admin/orgs/{org_id}/support", status_code=204, summary="Entrar a la organización como soporte")
def admin_support(org_id: uuid.UUID, session: SessionDep) -> Response:
    p = auth.require_superadmin()
    org = _org(session, org_id)
    s = session.get(UserSession, p.session_hash)
    s.support_org_id = org.id
    s.org_id = org.id
    auth.audit(session, "soporte.entrada", org_id=org.id, detail={"organizacion": org.name, "soporte": True})
    session.commit()
    return Response(status_code=204)


@router.delete("/admin/orgs/{org_id}", status_code=204, summary="Eliminar una organización con sus proyectos")
def admin_delete_org(org_id: uuid.UUID, body: OrgDelete, session: SessionDep) -> Response:
    import shutil

    from app.services.orthophotos import ortho_dir

    auth.require_superadmin()
    org = _org(session, org_id)
    if body.confirm.strip() != org.name:
        raise auth.AuthError(400, "Escriba el nombre exacto de la organización para confirmar.", "confirm")
    folders = [ortho_dir(o) for o in session.scalars(select(Orthophoto.id).join(Project, Project.id == Orthophoto.project_id)
                                                       .where(Project.org_id == org.id))]
    n_projects = session.scalar(select(func.count()).select_from(Project).where(Project.org_id == org.id)) or 0
    name = org.name
    session.delete(org)
    # La auditoría de la organización se borra con ella: el registro de la eliminación queda sin organización.
    auth.audit(session, "organizacion.eliminada", detail={"nombre": name, "id": str(org_id), "proyectos": n_projects})
    session.commit()
    for f in folders:
        shutil.rmtree(f, ignore_errors=True)
    return Response(status_code=204)


@router.patch("/admin/orgs/{org_id}", response_model=OrgOut, summary="Plan, límites, nombre o suspensión")
def admin_update_org(org_id: uuid.UUID, body: OrgUpdate, session: SessionDep) -> OrgOut:
    auth.require_superadmin()
    org = _org(session, org_id)
    data = body.model_dump(exclude_unset=True)
    confirm = data.pop("confirm", None)
    if data.get("suspended") and not org.suspended and (confirm or "").strip() != org.name:
        raise auth.AuthError(400, "Escriba el nombre exacto de la organización para suspenderla.", "confirm")
    if "limits" in data and data["limits"] is not None:
        bad = set(data["limits"]) - set(auth.LIMIT_KEYS)
        if bad:
            raise auth.AuthError(422, f"Límite desconocido: {', '.join(sorted(bad))}.")
    if data.get("name"):
        data["name"] = data["name"].strip()
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
    if body.is_superadmin is not None and body.is_superadmin != u.is_superadmin:
        if u.id == p.user_id:
            raise auth.AuthError(400, "No puede quitarse a sí mismo el rol de superadministrador.")
        u.is_superadmin = body.is_superadmin
        auth.audit(session, "cuenta.superadmin" if body.is_superadmin else "cuenta.superadmin_retirado",
                   detail={"usuario": u.email})
    if body.active is not None:
        if u.id == p.user_id and not body.active:
            raise auth.AuthError(400, "No puede suspender su propia cuenta.")
        u.active = body.active
        session.flush()
        if not body.active:
            orgs = session.scalars(select(Membership.org_id).where(Membership.user_id == u.id, Membership.role == "admin",
                                                                   Membership.active.is_(True)))
            if any(not auth.active_admins(session, o) for o in orgs):
                session.rollback()
                raise auth.AuthError(400, "Es el único administrador activo de una organización: nombre otro antes de "
                                          "suspender la cuenta.")
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
