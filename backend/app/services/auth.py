"""Autenticación, sesiones, roles por organización, auditoría y uso.

- Sesión: cookie httpOnly + Secure + SameSite=Strict con un token opaco; en la base solo se guarda su SHA-256.
- Cada solicitud a /api (salvo las públicas) pasa por `authenticate`, que deja el `Principal` en un contextvar.
  `check_project` (llamado por get_project_or_404) filtra por organización: un proyecto de otra organización
  responde 404 (no se distingue de uno inexistente) y un rol sin el permiso necesario responde 403.
- Permisos por rol: lector = ver y exportar; revisor = ver y revisar versiones; proyectista = ver y editar;
  administrador = todo + miembros, auditoría y uso de su organización.
"""
from __future__ import annotations

import contextvars
import logging
import re
import smtplib
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage

from fastapi import Request
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.core import security
from app.core.cache import get_redis
from app.core.config import get_settings
from app.core.db import get_sessionmaker
from app.core.ratelimit import client_ip
from app.models import (AuditLog, Membership, OneTimeToken, Organization, Orthophoto, Project, UsageCounter, User,
                        UserSession)

log = logging.getLogger(__name__)
ROLES = ("admin", "proyectista", "revisor", "lector")
ROLE_LABEL = {"admin": "administrador", "proyectista": "proyectista", "revisor": "revisor", "lector": "lector"}
ROLE_PERMS = {"lector": {"view"}, "revisor": {"view", "review"}, "proyectista": {"view", "edit"},
              "admin": {"view", "edit", "review", "manage"}}
PUBLIC = re.compile(r"^/api/(health|auth/(login|recover|reset|invitation/[^/]+|status))$")
PENDING_OK = re.compile(r"^/api/auth/(mfa|logout|me)$")
AUTH_ONLY = re.compile(r"^/api/auth/")
READONLY_POST = re.compile(r"/(simulate|validate|scenarios/simulate|scenarios/compare|feasibility|feasibility/report|"
                           r"query|query/export|hydrants/fire)$")
REVIEW_POST = re.compile(r"/versions/\d+/reviews$")
PLANS = {
    "basico": {"max_projects": 10, "max_simulations_month": 5000, "max_map_loads_month": 2000, "max_ortho_mb": 2048},
    "profesional": {"max_projects": 50, "max_simulations_month": 50000, "max_map_loads_month": 20000,
                    "max_ortho_mb": 20480},
    "ilimitado": {"max_projects": None, "max_simulations_month": None, "max_map_loads_month": None,
                  "max_ortho_mb": None},
}


class AuthError(Exception):
    def __init__(self, status: int, detail: str, code: str | None = None):
        super().__init__(detail)
        self.status, self.detail, self.code = status, detail, code


@dataclass
class Principal:
    user_id: uuid.UUID | None
    email: str
    is_superadmin: bool = False
    session_hash: str | None = None
    org_id: uuid.UUID | None = None
    roles: dict[uuid.UUID, str] = field(default_factory=dict)
    ip: str | None = None
    need: str = "view"
    system: bool = False

    def role_in(self, org_id) -> str | None:
        return self.roles.get(org_id)

    def can(self, org_id, perm: str) -> bool:
        role = self.roles.get(org_id)
        return role is not None and perm in ROLE_PERMS[role]


SYSTEM = Principal(user_id=None, email="sistema", system=True)
current: contextvars.ContextVar[Principal | None] = contextvars.ContextVar("trazo_principal", default=None)


def now() -> datetime:
    return datetime.now(timezone.utc)


def need_for(method: str, path: str) -> str:
    if method in ("GET", "HEAD", "OPTIONS"):
        return "view"
    if REVIEW_POST.search(path):
        return "review"
    if method == "POST" and READONLY_POST.search(path):
        return "view"
    return "edit"


def memberships(session: Session, user_id) -> dict[uuid.UUID, str]:
    rows = session.execute(select(Membership.org_id, Membership.role).join(Organization, Organization.id == Membership.org_id)
                           .where(Membership.user_id == user_id, Membership.active.is_(True),
                                  Organization.suspended.is_(False))).all()
    return {o: r for o, r in rows}


def mfa_setup_required(user: User, roles: dict) -> bool:
    if not get_settings().mfa_required_for_admins or user.mfa_enabled:
        return False
    return user.is_superadmin or "admin" in roles.values()


async def authenticate(request: Request) -> None:
    """Dependencia global: resuelve la sesión y deja el Principal en el contextvar y en request.state."""
    path = request.url.path
    current.set(None)
    if not path.startswith("/api/") or PUBLIC.match(path):
        return
    token = request.cookies.get(get_settings().cookie_name)
    if not token:
        raise AuthError(401, "Inicie sesión para continuar.", "login_required")
    with get_sessionmaker()() as session:
        s = session.get(UserSession, security.token_hash(token))
        if s is None or s.expires_at <= now():
            raise AuthError(401, "La sesión expiró: inicie sesión nuevamente.", "login_required")
        user = session.get(User, s.user_id)
        if user is None or not user.active:
            session.delete(s)
            session.commit()
            raise AuthError(401, "La cuenta está desactivada.", "login_required")
        if s.mfa_pending and not PENDING_OK.match(path):
            raise AuthError(401, "Falta el código del segundo factor.", "mfa_pending")
        roles = memberships(session, user.id)
        if mfa_setup_required(user, roles) and not AUTH_ONLY.match(path):
            raise AuthError(403, "Su rol exige el segundo factor (TOTP): configúrelo en su perfil.", "mfa_setup_required")
        if (now() - s.last_seen_at).total_seconds() > 60:
            s.last_seen_at = now()
            session.commit()
        org = s.org_id if s.org_id in roles else next(iter(roles), None)
        p = Principal(user_id=user.id, email=user.email, is_superadmin=user.is_superadmin, session_hash=s.token_hash,
                      org_id=org, roles=roles, ip=client_ip(request), need=need_for(request.method, path))
    current.set(p)
    request.state.principal = p


def principal() -> Principal:
    p = current.get()
    if p is None:
        raise AuthError(401, "Inicie sesión para continuar.", "login_required")
    return p


def check_project(project: Project) -> None:
    """Filtro por organización y rol (lo llama get_project_or_404)."""
    from app.services.errors import NotFound

    p = current.get()
    if p is None:
        raise NotFound("Proyecto no encontrado")
    if p.system:
        return
    role = p.roles.get(project.org_id)
    if role is None:
        raise NotFound("Proyecto no encontrado")
    if p.need not in ROLE_PERMS[role]:
        what = {"edit": "modificar el proyecto", "review": "revisar versiones"}.get(p.need, "esta acción")
        raise AuthError(403, f"Su rol ({ROLE_LABEL[role]}) no permite {what}.", "forbidden")


def require_org_perm(org_id: uuid.UUID, perm: str) -> Principal:
    p = principal()
    if p.system or p.can(org_id, perm) or (perm == "manage" and p.is_superadmin):
        return p
    if org_id not in p.roles and not p.is_superadmin:
        raise AuthError(404, "Organización no encontrada.")
    raise AuthError(403, "Su rol no permite esta acción en la organización.", "forbidden")


def require_superadmin() -> Principal:
    p = principal()
    if not p.is_superadmin:
        raise AuthError(404, "No encontrado.")
    return p


def new_project_org(session: Session) -> uuid.UUID:
    """Organización de un proyecto nuevo (la activa de la sesión), con permiso de edición y bajo el límite."""
    org_id = current_org_for_create()
    check_limit(session, org_id, "projects")
    return org_id


def current_org_for_create() -> uuid.UUID:
    p = principal()
    if p.org_id is None:
        raise AuthError(403, "No pertenece a ninguna organización activa.", "forbidden")
    if not p.can(p.org_id, "edit"):
        raise AuthError(403, "Su rol no permite crear proyectos en esta organización.", "forbidden")
    return p.org_id


# ── Sesiones e ingreso ──

def _login_rate(ip: str) -> None:
    limit = get_settings().login_rate_per_minute
    if limit <= 0:
        return
    key = f"trazo:login:{ip}:{int(time.time()) // 60}"
    try:
        pipe = get_redis().pipeline()
        pipe.incr(key)
        pipe.expire(key, 70)
        n = int(pipe.execute()[0])
    except Exception:  # noqa: BLE001
        return
    if n > limit:
        raise AuthError(429, "Demasiados intentos de ingreso desde esta dirección: espere un minuto.", "rate_limited")


def user_by_email(session: Session, email: str) -> User | None:
    return session.scalars(select(User).where(func.lower(User.email) == email.strip().lower())).first()


def create_session(session: Session, user: User, *, ip: str | None, ua: str | None, mfa_pending: bool) -> str:
    token = security.new_token()
    roles = memberships(session, user.id)
    session.add(UserSession(token_hash=security.token_hash(token), user_id=user.id, org_id=next(iter(roles), None),
                            mfa_pending=mfa_pending, ip=ip, user_agent=(ua or "")[:300],
                            expires_at=now() + timedelta(hours=get_settings().session_hours)))
    return token


def login(session: Session, email: str, password: str, ip: str, ua: str | None) -> tuple[str, bool]:
    _login_rate(ip)
    s = get_settings()
    user = user_by_email(session, email)
    if user is not None and user.locked_until and user.locked_until > now():
        mins = max(1, int((user.locked_until - now()).total_seconds() // 60) + 1)
        audit(session, "login.bloqueado", user=user, ip=ip)
        session.commit()
        raise AuthError(423, f"Cuenta bloqueada temporalmente por intentos fallidos: reintente en {mins} min.", "locked")
    ok = security.verify_password(user.password_hash if user else None, password)
    if not ok:
        if user is not None:
            user.failed_logins += 1
            if user.failed_logins >= s.login_max_attempts:
                user.locked_until = now() + timedelta(minutes=s.login_lockout_minutes)
                user.failed_logins = 0
            audit(session, "login.fallido", user=user, ip=ip)
            session.commit()
        raise AuthError(401, "Correo o contraseña incorrectos.", "bad_credentials")
    if not user.active:
        raise AuthError(401, "La cuenta está desactivada.", "inactive")
    user.failed_logins = 0
    user.locked_until = None
    if security.needs_rehash(user.password_hash):
        user.password_hash = security.hash_password(password)
    pending = user.mfa_enabled
    token = create_session(session, user, ip=ip, ua=ua, mfa_pending=pending)
    if not pending:
        user.last_login_at = now()
    audit(session, "login.mfa_pendiente" if pending else "login.ok", user=user, ip=ip)
    session.commit()
    return token, pending


def verify_mfa(session: Session, token: str, code: str, ip: str) -> None:
    s = session.get(UserSession, security.token_hash(token))
    user = session.get(User, s.user_id) if s else None
    if s is None or user is None:
        raise AuthError(401, "Inicie sesión nuevamente.", "login_required")
    if not security.verify_totp(user.mfa_secret, code):
        user.failed_logins += 1
        if user.failed_logins >= get_settings().login_max_attempts:
            user.locked_until = now() + timedelta(minutes=get_settings().login_lockout_minutes)
            user.failed_logins = 0
            session.delete(s)
        audit(session, "login.mfa_fallido", user=user, ip=ip)
        session.commit()
        raise AuthError(401, "Código incorrecto.", "bad_code")
    s.mfa_pending = False
    user.failed_logins = 0
    user.last_login_at = now()
    audit(session, "login.ok", user=user, ip=ip, detail={"mfa": True})
    session.commit()


def logout(session: Session, token: str | None, *, everywhere: bool = False) -> None:
    if not token:
        return
    s = session.get(UserSession, security.token_hash(token))
    if s is None:
        return
    if everywhere:
        session.execute(delete(UserSession).where(UserSession.user_id == s.user_id))
    else:
        session.delete(s)
    audit(session, "logout.todas" if everywhere else "logout", user=session.get(User, s.user_id))
    session.commit()


def change_password(session: Session, user: User, current_pw: str, new_pw: str, keep_session: str | None) -> None:
    if not security.verify_password(user.password_hash, current_pw):
        raise AuthError(400, "La contraseña actual no es correcta.")
    set_password(session, user, new_pw)
    q = delete(UserSession).where(UserSession.user_id == user.id)
    if keep_session:
        q = q.where(UserSession.token_hash != keep_session)
    session.execute(q)
    audit(session, "password.cambio", user=user)
    session.commit()


def set_password(session: Session, user: User, pw: str) -> None:
    problems = security.password_problems(pw, user.email)
    if problems:
        raise AuthError(422, "Contraseña no válida: " + " ".join(problems), "weak_password")
    user.password_hash = security.hash_password(pw)
    user.password_changed_at = now()
    user.failed_logins = 0
    user.locked_until = None


# ── Tokens de un solo uso: recuperación e invitación ──

def make_token(session: Session, purpose: str, *, user: User | None = None, org_id=None, email=None, role=None,
               created_by=None, hours: float) -> str:
    token = security.new_token()
    session.add(OneTimeToken(token_hash=security.token_hash(token), purpose=purpose, user_id=user.id if user else None,
                             org_id=org_id, email=email, role=role, created_by=created_by,
                             expires_at=now() + timedelta(hours=hours)))
    return token


def take_token(session: Session, token: str, purpose: str, *, consume: bool = True) -> OneTimeToken:
    t = session.get(OneTimeToken, security.token_hash(token))
    if t is None or t.purpose != purpose or t.used_at is not None or t.expires_at <= now():
        raise AuthError(400, "El enlace no es válido, ya se usó o expiró.", "bad_token")
    if consume:
        t.used_at = now()
    return t


def link(path: str, token: str) -> str:
    return f"{get_settings().public_url.rstrip('/')}{path}?token={token}"


def smtp_configured() -> bool:
    s = get_settings()
    return bool(s.smtp_host and s.smtp_from)


def send_mail(to: str, subject: str, body: str) -> bool:
    s = get_settings()
    if not smtp_configured():
        return False
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = s.smtp_from, to, subject
    msg.set_content(body)
    try:
        with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=15) as smtp:
            if s.smtp_tls:
                smtp.starttls()
            if s.smtp_user:
                smtp.login(s.smtp_user, s.smtp_password)
            smtp.send_message(msg)
        return True
    except (OSError, smtplib.SMTPException):
        log.warning("No se pudo enviar el correo a %s", to, exc_info=True)
        return False


def reset_link_for(session: Session, user: User, created_by=None) -> str:
    token = make_token(session, "reset", user=user, created_by=created_by, hours=get_settings().reset_token_hours)
    return link("/recuperar", token)


def request_recovery(session: Session, email: str, ip: str) -> bool:
    _login_rate(ip)
    user = user_by_email(session, email)
    if user is None or not user.active or not smtp_configured():
        return smtp_configured()
    url = reset_link_for(session, user)
    audit(session, "password.recuperacion_solicitada", user=user, ip=ip)
    session.commit()
    send_mail(user.email, "Trazo Hidráulico: recuperar contraseña",
              f"Para crear una contraseña nueva abra este enlace (válido {get_settings().reset_token_hours} h, un solo "
              f"uso):\n\n{url}\n\nSi usted no lo pidió, ignore este correo.")
    return True


def reset_password(session: Session, token: str, pw: str) -> None:
    t = take_token(session, token, "reset")
    user = session.get(User, t.user_id)
    if user is None or not user.active:
        raise AuthError(400, "El enlace no es válido.", "bad_token")
    set_password(session, user, pw)
    session.execute(delete(UserSession).where(UserSession.user_id == user.id))
    audit(session, "password.restablecida", user=user)
    session.commit()


def invitation_link(session: Session, org_id, email: str, role: str, created_by) -> str:
    token = make_token(session, "invite", org_id=org_id, email=email.strip().lower(), role=role, created_by=created_by,
                       hours=24 * get_settings().invite_token_days)
    return link("/invitacion", token)


def accept_invitation(session: Session, token: str, name: str, password: str, ip: str, ua: str | None) -> str:
    t = take_token(session, token, "invite")
    org = session.get(Organization, t.org_id)
    if org is None or org.suspended:
        raise AuthError(400, "La organización no está disponible.", "bad_token")
    user = user_by_email(session, t.email)
    if user is None:
        user = User(id=uuid.uuid4(), email=t.email, name=name.strip()[:200])
        set_password(session, user, password)
        session.add(user)
        session.flush()
    elif not security.verify_password(user.password_hash, password):
        raise AuthError(401, "Ya existe una cuenta con ese correo: ingrese su contraseña actual para aceptar.",
                        "bad_credentials")
    m = session.get(Membership, (user.id, org.id))
    if m is None:
        session.add(Membership(user_id=user.id, org_id=org.id, role=t.role, active=True))
    else:
        m.role, m.active = t.role, True
    session.flush()
    tok = create_session(session, user, ip=ip, ua=ua, mfa_pending=user.mfa_enabled)
    s = session.get(UserSession, security.token_hash(tok))
    s.org_id = org.id
    audit(session, "invitacion.aceptada", user=user, org_id=org.id, ip=ip, detail={"rol": t.role})
    session.commit()
    return tok


# ── Auditoría y uso ──

def audit(session: Session, action: str, *, user: User | None = None, org_id=None, project_id=None, version=None,
          detail: dict | None = None, ip: str | None = None) -> None:
    p = current.get()
    uid = user.id if user else (p.user_id if p else None)
    email = user.email if user else (p.email if p and not p.system else None)
    session.add(AuditLog(org_id=org_id, user_id=uid, user_email=email, action=action, project_id=project_id,
                         version=version, detail=detail, ip=ip or (p.ip if p else None)))


def month() -> str:
    return now().strftime("%Y-%m")


def limits_for(org: Organization) -> dict:
    base = dict(PLANS.get(org.plan, PLANS["basico"]))
    base.update(org.limits or {})
    return base


def usage_count(session: Session, org_id, kind: str) -> int:
    c = session.get(UsageCounter, (org_id, month(), kind))
    return int(c.count) if c else 0


def add_usage(session: Session, org_id, kind: str, n: int = 1) -> None:
    from sqlalchemy.dialects.postgresql import insert

    session.execute(insert(UsageCounter).values(org_id=org_id, month=month(), kind=kind, count=n)
                    .on_conflict_do_update(index_elements=["org_id", "month", "kind"],
                                           set_={"count": UsageCounter.count + n}))


def ortho_bytes(session: Session, org_id) -> int:
    return int(session.scalar(select(func.coalesce(func.sum(Orthophoto.size_bytes), 0)).join(
        Project, Project.id == Orthophoto.project_id).where(Project.org_id == org_id)) or 0)


def check_limit(session: Session, org_id, kind: str, extra: float = 0) -> None:
    org = session.get(Organization, org_id)
    if org is None:
        return
    lim = limits_for(org)
    if kind == "projects":
        n, cap, what = session.scalar(select(func.count()).select_from(Project).where(Project.org_id == org_id)), \
            lim.get("max_projects"), "proyectos"
    elif kind == "simulation":
        n, cap, what = usage_count(session, org_id, "simulation"), lim.get("max_simulations_month"), "simulaciones del mes"
    elif kind == "ortho":
        n, cap, what = (ortho_bytes(session, org_id) + extra) / 1024 / 1024, lim.get("max_ortho_mb"), \
            "MB de ortofotos"
    else:
        return
    if cap is not None and n >= cap if kind != "ortho" else cap is not None and n > cap:
        raise AuthError(403, f"Se alcanzó el límite del plan de la organización: {cap} {what}.", "limit")


def revoke_user_sessions(session: Session, user_id) -> None:
    session.execute(delete(UserSession).where(UserSession.user_id == user_id))


def purge_expired(session: Session) -> None:
    session.execute(delete(UserSession).where(UserSession.expires_at <= now()))
    session.execute(update(OneTimeToken).where(OneTimeToken.expires_at <= now(), OneTimeToken.used_at.is_(None))
                    .values(used_at=now()))
