"""Ingreso, sesión, segundo factor (TOTP), contraseña, recuperación, invitaciones y perfil."""
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import security
from app.core.config import get_settings
from app.core.db import get_session
from app.core.ratelimit import client_ip
from app.models import Membership, OneTimeToken, Organization, Orthophoto, Project, User, UserSession
from app.schemas.auth import (AuthStatus, CodeIn, InvitationAccept, InvitationInfo, LoginIn, LoginOut, Me, MfaDisable,
                              MfaSetup, OrgRef, OrgSwitch, PasswordChange, RecoverIn, RecoverOut, ResetIn, SessionOut, ProfileUpdate)
from app.services import auth

router = APIRouter(prefix="/auth", tags=["autenticación"])
SessionDep = Annotated[Session, Depends(get_session)]


def _set_cookie(resp: Response, token: str) -> None:
    s = get_settings()
    resp.set_cookie(s.cookie_name, token, max_age=int(s.session_hours * 3600), httponly=True, secure=s.cookie_secure,
                    samesite="strict", path="/")


def _clear_cookie(resp: Response) -> None:
    s = get_settings()
    resp.delete_cookie(s.cookie_name, path="/", httponly=True, secure=s.cookie_secure, samesite="strict")


def _token(request: Request) -> str | None:
    return request.cookies.get(get_settings().cookie_name)


@router.get("/status", response_model=AuthStatus, summary="Configuración pública del ingreso")
def status() -> AuthStatus:
    s = get_settings()
    return AuthStatus(email_enabled=auth.smtp_configured(), mfa_required_for_admins=s.mfa_required_for_admins,
                      password_min_length=s.password_min_length)


@router.post("/login", response_model=LoginOut, summary="Ingresar con correo y contraseña")
def login(body: LoginIn, request: Request, response: Response, session: SessionDep) -> LoginOut:
    token, pending = auth.login(session, body.email, body.password, client_ip(request), request.headers.get("user-agent"))
    _set_cookie(response, token)
    return LoginOut(mfa_required=pending)


@router.post("/mfa", status_code=204, summary="Completar el ingreso con el código TOTP")
def mfa(body: CodeIn, request: Request, session: SessionDep) -> Response:
    auth.verify_mfa(session, _token(request) or "", body.code, client_ip(request))
    return Response(status_code=204)


@router.post("/logout", status_code=204, summary="Cerrar la sesión actual")
def logout(request: Request, session: SessionDep) -> Response:
    auth.logout(session, _token(request))
    resp = Response(status_code=204)
    _clear_cookie(resp)
    return resp


@router.post("/logout-all", status_code=204, summary="Cerrar todas las sesiones del usuario")
def logout_all(request: Request, session: SessionDep) -> Response:
    auth.logout(session, _token(request), everywhere=True)
    resp = Response(status_code=204)
    _clear_cookie(resp)
    return resp


def _me_user(session: Session) -> User:
    p = auth.principal()
    user = session.get(User, p.user_id)
    if user is None:
        raise auth.AuthError(401, "Inicie sesión.", "login_required")
    return user


@router.get("/me", response_model=Me, summary="Usuario de la sesión")
def me(request: Request, session: SessionDep) -> Me:
    s = session.get(UserSession, security.token_hash(_token(request) or ""))
    user = session.get(User, s.user_id)
    roles = auth.memberships(session, user.id)
    names = dict(session.execute(select(Organization.id, Organization.name).where(Organization.id.in_(list(roles)))).all())
    current = s.org_id if s.org_id in roles else next(iter(roles), None)
    return Me(id=user.id, email=user.email, name=user.name, is_superadmin=user.is_superadmin, mfa_enabled=user.mfa_enabled,
              mfa_pending=s.mfa_pending, mfa_setup_required=auth.mfa_setup_required(user, roles), current_org=current,
              orgs=sorted([OrgRef(id=o, name=names.get(o, "?"), role=r) for o, r in roles.items()], key=lambda x: x.name))


@router.patch("/me", response_model=Me, summary="Editar el perfil (nombre visible)")
def update_me(body: ProfileUpdate, request: Request, session: SessionDep) -> Me:
    s = session.get(UserSession, security.token_hash(_token(request) or ""))
    if s is None or s.mfa_pending:
        raise auth.AuthError(401, "Complete el ingreso para editar su perfil.", "mfa_pending")
    user = _me_user(session)
    user.name = body.name.strip()
    auth.audit(session, "cuenta.perfil", detail={"nombre": user.name})
    session.commit()
    return me(request, session)


@router.post("/org", status_code=204, summary="Cambiar la organización activa")
def switch_org(body: OrgSwitch, session: SessionDep) -> Response:
    p = auth.principal()
    if body.org_id not in p.roles:
        raise auth.AuthError(404, "Organización no encontrada.")
    session.get(UserSession, p.session_hash).org_id = body.org_id
    session.commit()
    return Response(status_code=204)


@router.post("/password", status_code=204, summary="Cambiar la contraseña (cierra las demás sesiones)")
def change_password(body: PasswordChange, session: SessionDep) -> Response:
    p = auth.principal()
    auth.change_password(session, _me_user(session), body.current_password, body.new_password, p.session_hash)
    return Response(status_code=204)


@router.post("/mfa/setup", response_model=MfaSetup, summary="Generar un secreto TOTP (se activa al confirmar un código)")
def mfa_setup(session: SessionDep) -> MfaSetup:
    user = _me_user(session)
    if user.mfa_enabled:
        raise auth.AuthError(409, "El segundo factor ya está activo.")
    user.mfa_secret = security.new_totp_secret()
    session.commit()
    uri = security.totp_uri(user.mfa_secret, user.email)
    return MfaSetup(secret=user.mfa_secret, uri=uri, qr_svg=security.qr_svg(uri))


@router.post("/mfa/enable", status_code=204, summary="Activar el segundo factor con un código de la aplicación")
def mfa_enable(body: CodeIn, session: SessionDep) -> Response:
    user = _me_user(session)
    if not security.verify_totp(user.mfa_secret, body.code):
        raise auth.AuthError(400, "Código incorrecto: revise la hora del teléfono y reintente.", "bad_code")
    user.mfa_enabled = True
    auth.audit(session, "mfa.activado", user=user)
    session.commit()
    return Response(status_code=204)


@router.post("/mfa/disable", status_code=204, summary="Desactivar el segundo factor")
def mfa_disable(body: MfaDisable, session: SessionDep) -> Response:
    user = _me_user(session)
    if not security.verify_password(user.password_hash, body.password):
        raise auth.AuthError(400, "La contraseña no es correcta.")
    if get_settings().mfa_required_for_admins and (user.is_superadmin or "admin" in auth.memberships(session, user.id).values()):
        raise auth.AuthError(403, "Su rol exige el segundo factor: no se puede desactivar.", "forbidden")
    user.mfa_enabled, user.mfa_secret = False, None
    auth.audit(session, "mfa.desactivado", user=user)
    session.commit()
    return Response(status_code=204)


@router.get("/sessions", response_model=list[SessionOut], summary="Sesiones activas del usuario")
def sessions(session: SessionDep) -> list[SessionOut]:
    p = auth.principal()
    rows = session.scalars(select(UserSession).where(UserSession.user_id == p.user_id, UserSession.expires_at > auth.now())
                           .order_by(UserSession.last_seen_at.desc()))
    return [SessionOut(id=s.token_hash[:16], current=s.token_hash == p.session_hash, ip=s.ip, user_agent=s.user_agent,
                       created_at=s.created_at, last_seen_at=s.last_seen_at, expires_at=s.expires_at) for s in rows]


@router.delete("/sessions/{sid}", status_code=204, summary="Cerrar una sesión")
def close_session(sid: str, session: SessionDep) -> Response:
    p = auth.principal()
    s = session.scalars(select(UserSession).where(UserSession.user_id == p.user_id,
                                                  UserSession.token_hash.startswith(sid[:16]))).first() if len(sid) >= 16 else None
    if s is None:
        raise auth.AuthError(404, "Sesión no encontrada.")
    session.delete(s)
    session.commit()
    return Response(status_code=204)


@router.post("/recover", response_model=RecoverOut, summary="Pedir un enlace de recuperación por correo")
def recover(body: RecoverIn, request: Request, session: SessionDep) -> RecoverOut:
    return RecoverOut(email_enabled=auth.request_recovery(session, body.email, client_ip(request)))


@router.post("/reset", status_code=204, summary="Crear una contraseña nueva con un enlace de un solo uso")
def reset(body: ResetIn, session: SessionDep) -> Response:
    auth.reset_password(session, body.token, body.password)
    return Response(status_code=204)


@router.get("/invitation/{token}", response_model=InvitationInfo, summary="Datos de una invitación")
def invitation(token: str, session: SessionDep) -> InvitationInfo:
    t = auth.take_token(session, token, "invite", consume=False)
    org = session.get(Organization, t.org_id)
    return InvitationInfo(org_name=org.name if org else "?", email=t.email, role=t.role,
                          existing_user=auth.user_by_email(session, t.email) is not None)


@router.post("/invitation/{token}", status_code=204, summary="Aceptar una invitación (crea la cuenta o la vincula)")
def accept(token: str, body: InvitationAccept, request: Request, response: Response, session: SessionDep) -> Response:
    tok = auth.accept_invitation(session, token, body.name, body.password, client_ip(request),
                                 request.headers.get("user-agent"))
    resp = Response(status_code=204)
    _set_cookie(resp, tok)
    return resp


@router.get("/tile/{ortho_id}", status_code=204, include_in_schema=False)
def tile_check(ortho_id: str, session: SessionDep) -> Response:
    """Usado por Caddy (forward_auth) antes de servir teselas: la ortofoto debe ser de un proyecto visible."""
    import uuid as _uuid

    try:
        oid = _uuid.UUID(ortho_id)
    except ValueError:
        raise auth.AuthError(404, "No encontrado.") from None
    o = session.get(Orthophoto, oid)
    project = session.get(Project, o.project_id) if o else None
    p = auth.principal()
    if project is None or project.org_id not in p.roles:
        raise auth.AuthError(404, "No encontrado.")
    return Response(status_code=204)


__all__ = ["Membership", "OneTimeToken", "router"]
