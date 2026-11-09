"""Comandos de administración.

    python -m app.cli create-admin [--email X] [--password Y] [--name Z]   superadministrador de plataforma
    python -m app.cli seed-demo                                             organización «Demo APR» y sus usuarios
    python -m app.cli ensure-user --email X --password Y --org NOMBRE --role ROL
    python -m app.cli purge                                                 sesiones y enlaces vencidos

Sin --email o --password los pide por consola (la contraseña sin eco). También lee TRAZO_ADMIN_EMAIL y
TRAZO_ADMIN_PASSWORD (para instalaciones automatizadas).
"""
from __future__ import annotations

import argparse
import getpass
import os
import sys
import uuid
from pathlib import Path

from sqlalchemy import select

from app.core.db import get_sessionmaker
from app.models import Membership, Organization, Project, User
from app.services import auth

DEMO_ORG = "Demo APR"
DEMO_USERS = [  # correo, nombre, rol, contraseña (solo entorno local; ver docs/demo.md)
    ("admin@demo-apr.cl", "Administración Demo APR", "admin", "Apr-Gestion-2026"),
    ("proyectista@demo-apr.cl", "Proyectista Demo", "proyectista", "Apr-Diseno-2026"),
    ("revisor@demo-apr.cl", "Revisor Demo", "revisor", "Apr-Revision-2026"),
    ("lector@demo-apr.cl", "Lector Demo", "lector", "Apr-Consulta-2026"),
]


def _user(session, email: str, password: str, name: str = "", superadmin: bool = False) -> User:
    user = auth.user_by_email(session, email)
    if user is None:
        user = User(id=uuid.uuid4(), email=email.strip().lower(), name=name)
        session.add(user)
    auth.set_password(session, user, password)
    user.active = True
    if superadmin:
        user.is_superadmin = True
    if name:
        user.name = name
    session.flush()
    return user


def _org(session, name: str, plan: str = "basico") -> Organization:
    org = session.scalars(select(Organization).where(Organization.name == name)).first()
    if org is None:
        org = Organization(id=uuid.uuid4(), name=name, kind="apr", plan=plan)
        session.add(org)
        session.flush()
    return org


def _member(session, user: User, org: Organization, role: str) -> None:
    m = session.get(Membership, (user.id, org.id))
    if m is None:
        session.add(Membership(user_id=user.id, org_id=org.id, role=role, active=True))
    else:
        m.role, m.active = role, True


def create_admin(args) -> None:
    email = args.email or os.environ.get("TRAZO_ADMIN_EMAIL") or input("Correo del superadministrador: ").strip()
    pw = args.password or os.environ.get("TRAZO_ADMIN_PASSWORD")
    if not pw:
        pw = getpass.getpass("Contraseña: ")
        if getpass.getpass("Repita la contraseña: ") != pw:
            sys.exit("Las contraseñas no coinciden.")
    with get_sessionmaker()() as session:
        token = auth.current.set(auth.SYSTEM)
        try:
            user = _user(session, email, pw, args.name or "Superadministrador", superadmin=True)
            first = session.scalars(select(Organization).order_by(Organization.created_at)).first()
            if first is not None and session.get(Membership, (user.id, first.id)) is None:
                _member(session, user, first, "admin")  # acceso a los proyectos existentes (organización inicial)
            auth.audit(session, "cuenta.superadmin", user=user)
            session.commit()
        finally:
            auth.current.reset(token)
    print(f"Superadministrador listo: {email}. Si los administradores requieren segundo factor, configúrelo en /perfil "
          "al ingresar.")


def seed_demo(_args) -> None:
    with get_sessionmaker()() as session:
        token = auth.current.set(auth.SYSTEM)
        try:
            org = _org(session, DEMO_ORG, plan="profesional")
            for email, name, role, pw in DEMO_USERS:
                _member(session, _user(session, email, pw, name), org, role)
            project = session.scalars(select(Project).where(Project.name == "APR Demo")
                                      .order_by(Project.updated_at.desc())).first()
            if project is None:
                _create_demo_project(session, org)
            else:
                project.org_id = org.id
            session.commit()
        finally:
            auth.current.reset(token)
    print(f"Organización «{DEMO_ORG}» lista con un usuario por rol (credenciales en docs/demo.md).")


def _create_demo_project(session, org: Organization) -> None:
    from app.services import sig_io

    path = Path(os.environ.get("EXAMPLES_DIR", "/app/examples")) / "apr-demo.xlsx"
    if not path.exists():
        print("Aviso: no se encontró examples/apr-demo.xlsx; la organización queda sin proyecto.")
        return
    admin = auth.user_by_email(session, DEMO_USERS[0][0])
    principal = auth.Principal(user_id=admin.id, email=admin.email, org_id=org.id, roles={org.id: "admin"}, need="edit")
    tok = auth.current.set(principal)
    try:
        sig_io.create_from_excel(session, "apr-demo.xlsx", path.read_bytes(), name="APR Demo", zone=19, hemisphere="S")
    finally:
        auth.current.reset(tok)


def ensure_user(args) -> None:
    with get_sessionmaker()() as session:
        token = auth.current.set(auth.SYSTEM)
        try:
            org = _org(session, args.org)
            user = _user(session, args.email, args.password, args.email.split("@")[0])
            user.mfa_enabled, user.mfa_secret = False, None  # usuario de pruebas: el recorrido configura el TOTP
            user.failed_logins, user.locked_until = 0, None
            _member(session, user, org, args.role)
            session.commit()
        finally:
            auth.current.reset(token)
    print(f"Usuario {args.email} ({args.role}) en «{args.org}».")


def purge(_args) -> None:
    with get_sessionmaker()() as session:
        auth.purge_expired(session)
        session.commit()
    print("Sesiones y enlaces vencidos eliminados.")


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m app.cli")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("create-admin")
    a.add_argument("--email")
    a.add_argument("--password")
    a.add_argument("--name")
    a.set_defaults(func=create_admin)
    sub.add_parser("seed-demo").set_defaults(func=seed_demo)
    e = sub.add_parser("ensure-user")
    e.add_argument("--email", required=True)
    e.add_argument("--password", required=True)
    e.add_argument("--org", required=True)
    e.add_argument("--role", choices=auth.ROLES, required=True)
    e.set_defaults(func=ensure_user)
    sub.add_parser("purge").set_defaults(func=purge)
    args = ap.parse_args()
    try:
        args.func(args)
    except auth.AuthError as exc:
        sys.exit(f"Error: {exc.detail}")


if __name__ == "__main__":
    main()
