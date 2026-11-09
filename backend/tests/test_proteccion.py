"""Protección mínima para publicar: límite de solicitudes en /api y tamaño máximo del .inp."""
import uuid

import pytest

from app.core.config import get_settings


@pytest.fixture
def settings(monkeypatch):
    s = get_settings()
    return lambda **kw: [monkeypatch.setattr(s, k, v) for k, v in kw.items()]


def test_rate_limit_por_ip(client, settings):
    settings(rate_limit_per_minute=3)
    ip = {"X-Forwarded-For": f"203.0.113.{uuid.uuid4().int % 250}, 10.0.0.{uuid.uuid4().int % 250}"}
    codes = [client.get("/api/catalog/pipes", headers=ip).status_code for _ in range(4)]
    assert codes == [200, 200, 200, 429]
    r = client.get("/api/design-profiles", headers=ip)
    assert r.status_code == 429 and int(r.headers["Retry-After"]) > 0
    assert "Demasiadas solicitudes" in r.json()["detail"]
    # Otra IP (último valor de X-Forwarded-For, el que agrega Caddy) tiene su propio cupo.
    other = {"X-Forwarded-For": f"10.1.{uuid.uuid4().int % 250}.1"}
    assert client.get("/api/catalog/pipes", headers=other).status_code == 200
    # El chequeo de salud no se limita (lo usa el healthcheck del contenedor).
    assert client.get("/api/health", headers=ip).status_code == 200


def test_rate_limit_desactivado_con_cero(client, settings):
    settings(rate_limit_per_minute=0)
    ip = {"X-Forwarded-For": "198.51.100.7"}
    assert all(client.get("/api/catalog/pipes", headers=ip).status_code == 200 for _ in range(5))


def test_inp_demasiado_grande_se_rechaza(client, settings):
    settings(max_inp_mb=1)
    big = b"[TITLE]\n" + b";" * (1024 * 1024 + 10)
    r = client.post("/api/projects/import", files={"file": ("grande.inp", big, "text/plain")})
    assert r.status_code == 413 and "1 MB" in r.json()["detail"]
