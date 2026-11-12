"""Mapa base desde Configuración: la key de Google Maps se guarda cifrada, solo el superadministrador la gestiona y
todo usuario con sesión la recibe en tiempo de ejecución (sin recompilar el frontend)."""
import uuid

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import get_sessionmaker
from app.models import PlatformSetting
from tests.conftest import make_user, new_client

KEY = "AIzaSyD-prueba_1234567890abcdefXYZ"


@pytest.fixture(scope="module")
def admin(database):
    make_user("super-mapa@trazo.test", "Plataforma mapa", "admin", superadmin=True)
    with new_client("super-mapa@trazo.test") as c:
        yield c


def test_solo_superadmin_gestiona_y_todos_leen(client, admin):
    assert client.get("/api/admin/maps").status_code == 404  # usuario normal: no existe para él
    assert client.put("/api/admin/maps", json={"api_key": KEY}).status_code == 404
    st = admin.get("/api/admin/maps").json()
    assert st["encryption_ready"] and not st["configured"]
    assert client.get("/api/maps/config").json() == {"provider": "auto", "api_key": None, "map_id": None, "source": "none"}

    st = admin.put("/api/admin/maps", json={"api_key": KEY, "map_id": "mapa-oscuro-01"}).json()
    assert st["configured"] and st["key_hint"] == "AIza…fXYZ" and st["map_id"] == "mapa-oscuro-01"
    assert KEY not in str(st)
    cfg = client.get("/api/maps/config").json()
    assert cfg == {"provider": "auto", "api_key": KEY, "map_id": "mapa-oscuro-01", "source": "db"}
    # En la base queda cifrada.
    with get_sessionmaker()() as s:
        row = s.scalar(select(PlatformSetting).where(PlatformSetting.key == "google_maps_api_key"))
        assert row.encrypted and KEY not in row.value
    # Cambiar solo el Map ID conserva la key; formato inválido se rechaza.
    assert admin.put("/api/admin/maps", json={"map_id": ""}).json()["map_id"] is None
    assert client.get("/api/maps/config").json()["api_key"] == KEY
    assert admin.put("/api/admin/maps", json={"api_key": "no válida!"}).status_code == 422
    st = admin.delete("/api/admin/maps").json()
    assert not st["configured"] and st["key_hint"] is None
    assert client.get("/api/maps/config").json()["source"] == "none"


def test_sin_clave_de_cifrado_no_se_guarda(admin, monkeypatch):
    monkeypatch.setattr(get_settings(), "settings_secret_key", "")
    r = admin.put("/api/admin/maps", json={"api_key": KEY})
    assert r.status_code == 503 and "SETTINGS_SECRET_KEY" in r.json()["detail"]
    assert admin.get("/api/admin/maps").json()["encryption_ready"] is False


def test_requiere_sesion():
    with new_client() as anon:
        assert anon.get("/api/maps/config").status_code == 401


def test_listado_con_clientes_y_km(client):
    from tests.test_sig_excel import create_demo

    pid = create_demo(client, "APR listado")
    p = next(x for x in client.get("/api/projects").json() if x["id"] == pid)
    assert p["client_count"] == 30 and 2.0 < p["network_km"] < 2.6 and p["latest_version"] == 1
    # Miniatura del trazado: un polilínea por tramo, dentro de la grilla 0–1000; centro en Chile central.
    assert p["outline"] and all(len(line) >= 4 and len(line) % 2 == 0 for line in p["outline"])
    assert all(0 <= v <= 1000 for line in p["outline"] for v in line)
    lon, lat = p["center"]
    assert -76 < lon < -66 and -56 < lat < -17
    assert isinstance(p["overdue_tasks"], int) and p["overdue_tasks"] >= 0


def test_mantenciones_atrasadas_por_proyecto(client):
    from datetime import date

    from app.models import MaintenanceTask
    from app.repositories.projects import overdue_tasks
    from tests.test_sig_excel import create_demo

    pid = uuid.UUID(create_demo(client, "APR atrasos"))
    with get_sessionmaker()() as s:
        base = overdue_tasks(s, [pid], date(2026, 11, 12)).get(pid, 0)
        s.add_all([
            MaintenanceTask(project_id=pid, kind="otro", next_date=date(2026, 11, 1), frequency_days=30),  # atrasada
            MaintenanceTask(project_id=pid, kind="otro", next_date=date(2026, 11, 1), done_on=date(2026, 11, 2)),  # única cumplida
            MaintenanceTask(project_id=pid, kind="otro", next_date=date(2026, 11, 12), frequency_days=7),  # vence hoy: al día
        ])
        s.commit()
        assert overdue_tasks(s, [pid], date(2026, 11, 12))[pid] == base + 1


def test_proveedor_del_mapa_base(client, admin):
    assert client.get("/api/maps/config").json()["provider"] == "auto"
    st = admin.put("/api/admin/maps", json={"provider": "osm"}).json()
    assert st["provider"] == "osm" and not st["configured"]
    assert client.get("/api/maps/config").json()["provider"] == "osm"
    assert admin.put("/api/admin/maps", json={"provider": "bing"}).status_code == 422
    assert admin.put("/api/admin/maps", json={"provider": "auto"}).json()["provider"] == "auto"
