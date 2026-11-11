"""Protección mínima para publicar: límite de solicitudes en /api y tamaño máximo del .inp."""
import uuid

import pytest

from app.core.config import get_settings


@pytest.fixture
def settings(monkeypatch):
    s = get_settings()
    return lambda **kw: [monkeypatch.setattr(s, k, v) for k, v in kw.items()]


def _fresh_user(tag: str):
    from tests.conftest import make_user, new_client

    email = f"limite-{tag}-{uuid.uuid4().hex[:8]}@trazo.test"
    make_user(email, "Organización límites", "proyectista")
    return new_client(email)


def test_rate_limit_por_usuario_no_cierra_la_sesion(settings):
    settings(rate_limit_user_per_minute=3, rate_limit_per_minute=1000)
    a, b = _fresh_user("a"), _fresh_user("b")
    # El cupo es del usuario, aunque cambie la IP (varias pestañas, oficina tras una misma IP, red móvil).
    codes = [a.get("/api/catalog/pipes", headers={"X-Forwarded-For": f"203.0.113.{k}"}).status_code for k in range(4)]
    assert codes == [200, 200, 200, 429]
    r = a.get("/api/auth/me")
    assert r.status_code == 429 and int(r.headers["Retry-After"]) > 0 and r.json()["code"] == "rate_limited"
    assert "Demasiadas solicitudes" in r.json()["detail"]
    # Otro usuario desde la misma IP no se ve afectado
    assert b.get("/api/catalog/pipes", headers={"X-Forwarded-For": "203.0.113.0"}).status_code == 200
    # El 429 no cierra la sesión: pasada la ventana (aquí, sin límite) la misma cookie sigue válida
    settings(rate_limit_user_per_minute=0)
    me = a.get("/api/auth/me")
    assert me.status_code == 200 and me.json()["email"].startswith("limite-a-")
    a.close()
    b.close()


def test_rate_limit_publico_por_ip(settings):
    from tests.conftest import new_client

    settings(rate_limit_per_minute=3, rate_limit_user_per_minute=1000)
    ip = {"X-Forwarded-For": f"198.51.100.{uuid.uuid4().int % 250}"}
    with new_client() as anon:
        codes = [anon.get("/api/auth/status", headers=ip).status_code for _ in range(4)]
        assert codes == [200, 200, 200, 429]
        other = {"X-Forwarded-For": f"10.1.{uuid.uuid4().int % 250}.1"}
        assert anon.get("/api/auth/status", headers=other).status_code == 200
        # El chequeo de salud no se limita (lo usa el healthcheck del contenedor).
        assert anon.get("/api/health", headers=ip).status_code == 200


def test_teselas_de_ortofotos_no_cuentan(settings):
    settings(rate_limit_user_per_minute=2, rate_limit_per_minute=1000)
    c = _fresh_user("teselas")
    codes = {c.get(f"/api/auth/tile/{uuid.uuid4()}").status_code for _ in range(10)}
    assert 429 not in codes
    assert [c.get("/api/catalog/pipes").status_code for _ in range(3)] == [200, 200, 429]
    c.close()


def test_rate_limit_desactivado_con_cero(client, settings):
    settings(rate_limit_per_minute=0, rate_limit_user_per_minute=0)
    ip = {"X-Forwarded-For": "198.51.100.7"}
    assert all(client.get("/api/catalog/pipes", headers=ip).status_code == 200 for _ in range(5))


def test_inp_demasiado_grande_se_rechaza(client, settings):
    settings(max_inp_mb=1)
    big = b"[TITLE]\n" + b";" * (1024 * 1024 + 10)
    r = client.post("/api/projects/import", files={"file": ("grande.inp", big, "text/plain")})
    assert r.status_code == 413 and "1 MB" in r.json()["detail"]
