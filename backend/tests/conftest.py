"""Fixtures de prueba: base de datos aislada (trazo_test), caché aislada y cliente HTTP."""
import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from app.core.config import get_settings

def pytest_sessionstart(session):
    """Aborta antes de cualquier prueba si el entorno no apunta a la base y la caché de prueba.

    Ninguna prueba puede tocar la base de desarrollo (trazo) ni la base Redis 0 de la pila normal.
    """
    s = get_settings()
    problems = []
    if not s.postgres_db.endswith("_test"):
        problems.append(f"POSTGRES_DB={s.postgres_db!r} (debe terminar en _test)")
    if s.redis_db == 0:
        problems.append("REDIS_DB=0 (las pruebas usan otra base Redis)")
    if problems:
        pytest.exit("Entorno de pruebas inseguro: " + "; ".join(problems) + ". Ejecute `make test`.", returncode=2)


NETWORKS_DIR = Path(os.environ.get("NETWORKS_DIR", "/app/examples/networks"))
REPORT_DIR = Path(os.environ.get("REPORT_DIR", "/tmp/reports"))


@pytest.fixture(scope="session")
def database():
    """Recrea la base de pruebas desde cero y aplica las migraciones."""
    s = get_settings()
    if not s.postgres_db.endswith("_test"):
        pytest.exit("Las pruebas solo se ejecutan contra una base *_test", returncode=2)
    admin_url = s.database_url.rsplit("/", 1)[0] + "/postgres"
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{s.postgres_db}" WITH (FORCE)'))
        conn.execute(text(f'CREATE DATABASE "{s.postgres_db}"'))
    admin.dispose()

    from alembic import command
    from alembic.config import Config

    command.upgrade(Config("alembic.ini"), "head")
    yield s.database_url


TEST_PASSWORD = "Prueba-segura-2026"


def make_user(email: str, org: str, role: str, *, password: str = TEST_PASSWORD, superadmin: bool = False):
    """Crea (o actualiza) un usuario con membresía en la organización indicada. Devuelve (user_id, org_id)."""
    import uuid as _uuid

    from sqlalchemy import select

    from app.core.db import get_sessionmaker
    from app.models import Membership, Organization, User
    from app.services import auth

    with get_sessionmaker()() as session:
        tok = auth.current.set(auth.SYSTEM)
        try:
            o = session.scalars(select(Organization).where(Organization.name == org)).first()
            if o is None:
                o = Organization(id=_uuid.uuid4(), name=org, kind="apr", plan="ilimitado")
                session.add(o)
                session.flush()
            u = auth.user_by_email(session, email)
            if u is None:
                u = User(id=_uuid.uuid4(), email=email, name=email.split("@")[0])
                session.add(u)
            auth.set_password(session, u, password)
            u.is_superadmin = superadmin
            u.active, u.locked_until, u.failed_logins = True, None, 0
            session.flush()
            m = session.get(Membership, (u.id, o.id))
            if m is None:
                session.add(Membership(user_id=u.id, org_id=o.id, role=role, active=True))
            else:
                m.role, m.active = role, True
            session.commit()
            return u.id, o.id
        finally:
            auth.current.reset(tok)


def new_client(email: str | None = None, password: str = TEST_PASSWORD):
    """Cliente HTTP (https, para que viaje la cookie Secure); con correo, ya autenticado."""
    from fastapi.testclient import TestClient

    from app.main import app

    c = TestClient(app, base_url="https://testserver")
    if email:
        r = c.post("/api/auth/login", json={"email": email, "password": password})
        assert r.status_code == 200, r.text
    return c


@pytest.fixture(scope="session")
def client(database):
    from app.core.cache import get_redis

    if get_settings().redis_db == 0:
        pytest.exit("Las pruebas usan una base Redis distinta de la 0", returncode=2)
    get_redis().flushdb()
    make_user("pruebas@trazo.test", "Organización de pruebas", "admin")
    with new_client("pruebas@trazo.test") as c:
        yield c


@pytest.fixture(scope="session")
def report_dir() -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    return REPORT_DIR


@pytest.fixture(scope="session")
def networks_dir() -> Path:
    return NETWORKS_DIR
