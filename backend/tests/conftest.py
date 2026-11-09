"""Fixtures de prueba: base de datos aislada (trazo_test), caché aislada y cliente HTTP."""
import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from app.core.config import get_settings

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


@pytest.fixture(scope="session")
def client(database):
    from fastapi.testclient import TestClient

    from app.core.cache import get_redis
    from app.main import app

    if get_settings().redis_db == 0:
        pytest.exit("Las pruebas usan una base Redis distinta de la 0", returncode=2)
    get_redis().flushdb()
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def report_dir() -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    return REPORT_DIR


@pytest.fixture(scope="session")
def networks_dir() -> Path:
    return NETWORKS_DIR
