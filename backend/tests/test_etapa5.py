"""Etapa 5: autenticación, sesiones, MFA, recuperación, organizaciones y roles, aislamiento, auditoría y uso."""
import struct
import uuid
import zlib

import pytest

from app.core import security
from app.core.config import get_settings
from tests.conftest import TEST_PASSWORD, make_user, new_client

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@pytest.fixture
def settings(monkeypatch):
    s = get_settings()
    return lambda **kw: [monkeypatch.setattr(s, k, v) for k, v in kw.items()]


def png(w=8, h=8) -> bytes:
    raw = b"".join(b"\x00" + b"\x80\x90\xa0" * w for _ in range(h))
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def uniq(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}@trazo.test"


# ── Contraseñas y sesión ──

def test_argon2id_y_politica_de_contrasena():
    h = security.hash_password("Clave-larga-123")
    assert h.startswith("$argon2id$") and security.verify_password(h, "Clave-larga-123")
    assert not security.verify_password(h, "otra")
    assert security.password_problems("corta1")
    assert security.password_problems("solamenteletras")
    assert security.password_problems("1234567890")
    assert not security.password_problems("Agua-Potable-2026")


def test_sin_sesion_responde_401_y_salud_es_publica():
    c = new_client()
    assert c.get("/api/projects").status_code == 401
    assert c.get("/api/catalog/pipes").status_code == 401
    assert c.get("/api/health").status_code == 200
    assert c.get("/api/auth/status").status_code == 200


def test_cookie_segura_logout_y_bloqueo(settings):
    email = uniq("bloqueo")
    make_user(email, "Org bloqueo", "proyectista")
    c = new_client()
    r = c.post("/api/auth/login", json={"email": email, "password": TEST_PASSWORD})
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "secure" in cookie and "samesite=strict" in cookie and "max-age=43200" in cookie
    assert c.get("/api/projects").status_code == 200
    c.post("/api/auth/logout")
    assert c.get("/api/projects").status_code == 401
    # Bloqueo temporal tras 5 intentos fallidos (también rechaza la contraseña correcta mientras dura).
    bad = [new_client().post("/api/auth/login", json={"email": email, "password": "Mala-123456"}).status_code
           for _ in range(5)]
    assert bad == [401] * 5
    r = new_client().post("/api/auth/login", json={"email": email, "password": TEST_PASSWORD})
    assert r.status_code == 423 and "bloqueada" in r.json()["detail"]
    # Mismo mensaje para un correo inexistente (no revela cuentas).
    r = new_client().post("/api/auth/login", json={"email": uniq("nadie"), "password": "Mala-123456"})
    assert r.status_code == 401 and r.json()["detail"] == "Correo o contraseña incorrectos."


def test_limite_de_ingresos_por_ip(settings):
    settings(login_rate_per_minute=3)
    ip = {"X-Forwarded-For": f"192.0.2.{uuid.uuid4().int % 250}"}
    codes = [new_client().post("/api/auth/login", json={"email": "x@y.cl", "password": "Mala-123456"}, headers=ip).status_code
             for _ in range(4)]
    assert codes == [401, 401, 401, 429]


def test_cerrar_todas_las_sesiones_y_cambio_de_contrasena():
    email = uniq("sesiones")
    make_user(email, "Org sesiones", "lector")
    a, b = new_client(email), new_client(email)
    lst = a.get("/api/auth/sessions").json()
    assert len(lst) >= 2 and sum(s["current"] for s in lst) == 1
    r = a.post("/api/auth/password", json={"current_password": TEST_PASSWORD, "new_password": "Nueva-Clave-2026"})
    assert r.status_code == 204
    assert b.get("/api/projects").status_code == 401  # las demás sesiones se cierran
    assert a.get("/api/projects").status_code == 200
    a.post("/api/auth/logout-all")
    assert a.get("/api/projects").status_code == 401
    assert new_client(email, "Nueva-Clave-2026").get("/api/auth/me").json()["email"] == email


# ── Segundo factor ──

def test_mfa_totp_y_obligatorio_para_administradores(settings):
    email = uniq("mfa")
    make_user(email, "Org MFA", "admin")
    settings(mfa_required_for_admins=True)
    c = new_client(email)
    r = c.get("/api/projects")
    assert r.status_code == 403 and r.json()["code"] == "mfa_setup_required"
    assert c.get("/api/auth/me").json()["mfa_setup_required"] is True
    setup = c.post("/api/auth/mfa/setup").json()
    assert setup["uri"].startswith("otpauth://totp/") and "<svg" in setup["qr_svg"]
    assert c.post("/api/auth/mfa/enable", json={"code": "000000"}).status_code == 400
    assert c.post("/api/auth/mfa/enable", json={"code": security.totp(setup["secret"])}).status_code == 204
    assert c.get("/api/projects").status_code == 200
    assert c.post("/api/auth/mfa/disable", json={"password": TEST_PASSWORD}).status_code == 403  # obligatorio
    d = new_client()
    assert d.post("/api/auth/login", json={"email": email, "password": TEST_PASSWORD}).json() == {"mfa_required": True}
    assert d.get("/api/projects").status_code == 401  # falta el código
    assert d.post("/api/auth/mfa", json={"code": "123456" if security.totp(setup["secret"]) != "123456" else "654321"}).status_code == 401
    assert d.post("/api/auth/mfa", json={"code": security.totp(setup["secret"])}).status_code == 204
    assert d.get("/api/projects").status_code == 200


# ── Recuperación ──

def test_recuperacion_por_enlace_del_administrador_y_por_correo(monkeypatch):
    admin, user = uniq("admin-rec"), uniq("olvido")
    _, org = make_user(admin, "Org recuperación", "admin")
    uid, _ = make_user(user, "Org recuperación", "proyectista")
    a = new_client(admin)
    assert new_client().post("/api/auth/recover", json={"email": user}).json() == {"email_enabled": False}
    link = a.post(f"/api/orgs/{org}/members/{uid}/reset-link").json()["link"]
    token = link.split("token=")[1]
    c = new_client()
    assert c.post("/api/auth/reset", json={"token": token, "password": "corta"}).status_code == 422
    assert c.post("/api/auth/reset", json={"token": token, "password": "Recuperada-2026"}).status_code == 204
    assert c.post("/api/auth/reset", json={"token": token, "password": "Otra-Clave-2026"}).status_code == 400  # un uso
    assert new_client(user, "Recuperada-2026").get("/api/auth/me").status_code == 200
    # Con SMTP configurado se envía el enlace por correo.
    from app.services import auth

    sent = []
    monkeypatch.setattr(auth, "smtp_configured", lambda: True)
    monkeypatch.setattr(auth, "send_mail", lambda to, subject, body: sent.append((to, body)) or True)
    assert new_client().post("/api/auth/recover", json={"email": user}).json() == {"email_enabled": True}
    assert sent and sent[0][0] == user and "/recuperar?token=" in sent[0][1]


# ── Organizaciones, roles y aislamiento ──

@pytest.fixture(scope="module")
def two_orgs(client):
    a_email, b_email = uniq("org-a"), uniq("org-b")
    make_user(a_email, "Organización A", "admin")
    _, org_b = make_user(b_email, "Organización B", "admin")
    a, b = new_client(a_email), new_client(b_email)
    r = a.post("/api/projects/import-excel", files={"file": ("apr.xlsx", open("/app/examples/apr-demo.xlsx", "rb").read(), XLSX)},
               data={"name": "Proyecto de A"})
    assert r.status_code == 201, r.text
    pid = r.json()["project_id"]
    o = a.post(f"/api/projects/{pid}/orthophotos", files={"file": ("plano.png", png(), "image/png")})
    assert o.status_code == 201, o.text
    a.post(f"/api/projects/{pid}/queries", json={"name": "Q", "definition": {"element": "nudos", "where": {"conditions": []}}})
    return {"a": a, "b": b, "pid": pid, "oid": o.json()["id"], "org_b": org_b, "a_email": a_email}


def test_aislamiento_entre_organizaciones(two_orgs):
    a, b, pid, oid = two_orgs["a"], two_orgs["b"], two_orgs["pid"], two_orgs["oid"]
    assert pid not in {p["id"] for p in b.get("/api/projects").json()}
    assert pid in {p["id"] for p in a.get("/api/projects").json()}
    gets = ["", "/network", "/versions", "/export.inp", "/export.dxf", "/export.gpkg", "/export.trazo",
            "/sig/export.xlsx", "/sig/export.csv?sheet=nudos", "/report.html", "/sectors", "/orthophotos",
            f"/orthophotos/{oid}/original", "/queries", "/search?q=J", "/measurements", "/demand/projection",
            "/design-params", "/wells/PZ-1/pump", "/diagnosis", "/measurements/compare", "/versions/1/reviews"]
    for g in gets:
        ra, rb = a.get(f"/api/projects/{pid}{g}"), b.get(f"/api/projects/{pid}{g}")
        assert rb.status_code == 404, (g, rb.status_code)
        assert ra.status_code != 404 or g in ("/wells/PZ-1/pump",), (g, ra.status_code)
    writes = [("put", "/network", {"base_version": 1, "kind": "manual", "network": {"type": "FeatureCollection", "features": []}}),
              ("post", "/simulate", {"model_version": 1}), ("patch", "", {"name": "robado"}),
              ("post", "/query", {"element": "nudos"}), ("post", "/measurements", []),
              ("delete", f"/orthophotos/{oid}", None), ("delete", "", None)]
    for method, path, body in writes:
        r = getattr(b, method)(f"/api/projects/{pid}{path}", **({"json": body} if body is not None else {}))
        assert r.status_code == 404, (method, path, r.status_code)
    # Adivinar IDs: un UUID inexistente responde igual que uno ajeno.
    fake = uuid.uuid4()
    assert b.get(f"/api/projects/{fake}").json() == b.get(f"/api/projects/{pid}").json()
    # Teselas de la ortofoto: Caddy consulta /api/auth/tile antes de servirlas.
    assert a.get(f"/api/auth/tile/{oid}").status_code == 204
    assert b.get(f"/api/auth/tile/{oid}").status_code == 404
    # Datos de la organización ajena
    org_a = next(o["id"] for o in a.get("/api/auth/me").json()["orgs"] if o["name"] == "Organización A")
    for path in ("/members", "/audit", "/usage"):
        assert b.get(f"/api/orgs/{org_a}{path}").status_code == 404
    assert b.post(f"/api/orgs/{org_a}/invitations", json={"email": "x@y.cl", "role": "admin"}).status_code == 404
    assert a.get(f"/api/projects/{pid}").json()["name"] == "Proyecto de A"


def test_roles_lector_revisor_proyectista_y_administrador(two_orgs):
    a, pid = two_orgs["a"], two_orgs["pid"]
    clients = {}
    for role in ("lector", "revisor", "proyectista"):
        email = uniq(role)
        make_user(email, "Organización A", role)
        clients[role] = new_client(email)
    net = a.get(f"/api/projects/{pid}/network").json()
    save = {"base_version": net["version"], "kind": "manual", "label": "edición", "network": net["network"]}
    for role, c in clients.items():
        assert c.get(f"/api/projects/{pid}/network").status_code == 200
        assert c.get(f"/api/projects/{pid}/export.trazo").status_code == 200  # todos ven y exportan
        assert c.post(f"/api/projects/{pid}/simulate", json={"model_version": net["version"]}).status_code == 200
    r = clients["lector"].put(f"/api/projects/{pid}/network", json=save)
    assert r.status_code == 403 and "lector" in r.json()["detail"]
    assert clients["revisor"].put(f"/api/projects/{pid}/network", json=save).status_code == 403
    assert clients["lector"].post(f"/api/projects/{pid}/versions/1/reviews", json={"status": "aprobada"}).status_code == 403
    r = clients["revisor"].post(f"/api/projects/{pid}/versions/1/reviews", json={"status": "aprobada", "comment": "OK"})
    assert r.status_code == 201
    assert clients["proyectista"].post(f"/api/projects/{pid}/versions/1/reviews",
                                       json={"status": "comentario"}).status_code == 403
    assert clients["proyectista"].put(f"/api/projects/{pid}/network", json=save).status_code == 200
    assert clients["lector"].post("/api/projects", json={"name": "No"}).status_code == 403
    org_a = next(o["id"] for o in a.get("/api/auth/me").json()["orgs"] if o["name"] == "Organización A")
    assert clients["proyectista"].get(f"/api/orgs/{org_a}/members").status_code == 403
    reviews = a.get(f"/api/projects/{pid}/versions/1/reviews").json()
    assert reviews[0]["status"] == "aprobada" and reviews[0]["comment"] == "OK"


def test_invitacion_cambio_de_rol_y_desactivacion(two_orgs):
    a = two_orgs["a"]
    org_a = next(o["id"] for o in a.get("/api/auth/me").json()["orgs"] if o["name"] == "Organización A")
    email = uniq("invitado")
    r = a.post(f"/api/orgs/{org_a}/invitations", json={"email": email, "role": "lector", "send_email": False})
    assert r.status_code == 201 and not r.json()["emailed"]
    token = r.json()["link"].split("token=")[1]
    c = new_client()
    info = c.get(f"/api/auth/invitation/{token}").json()
    assert info == {"org_name": "Organización A", "email": email, "role": "lector", "existing_user": False}
    assert c.post(f"/api/auth/invitation/{token}", json={"name": "Invitado", "password": "Invitado-2026"}).status_code == 204
    assert two_orgs["pid"] in {p["id"] for p in c.get("/api/projects").json()}
    assert new_client().post(f"/api/auth/invitation/{token}", json={"password": "Invitado-2026"}).status_code == 400
    uid = c.get("/api/auth/me").json()["id"]
    assert a.patch(f"/api/orgs/{org_a}/members/{uid}", json={"role": "proyectista"}).json()["role"] == "proyectista"
    assert a.patch(f"/api/orgs/{org_a}/members/{uid}", json={"active": False}).json()["active"] is False
    assert c.get(f"/api/projects/{two_orgs['pid']}").status_code == 404


def test_auditoria(two_orgs):
    a, pid = two_orgs["a"], two_orgs["pid"]
    org_a = next(o["id"] for o in a.get("/api/auth/me").json()["orgs"] if o["name"] == "Organización A")
    a.get(f"/api/projects/{pid}/export.dxf")
    log = a.get(f"/api/orgs/{org_a}/audit").json()
    actions = {x["action"] for x in log}
    assert {"red.version", "exportacion", "importacion", "permiso.invitacion", "login.ok", "revision.aprobada",
            "permiso.cambio"} <= actions, actions
    v = next(x for x in log if x["action"] == "red.version")
    assert v["project_id"] and v["version"] and v["user_email"]
    exp = next(x for x in log if x["action"] == "exportacion" and "export.dxf" in x["detail"]["ruta"])
    assert exp["user_email"] == two_orgs["a_email"]


def test_superadministrador_uso_limites_y_suspension(two_orgs):
    sa = uniq("super")
    make_user(sa, "Plataforma", "admin", superadmin=True)
    s = new_client(sa)
    assert two_orgs["a"].get("/api/admin/orgs").status_code == 404  # solo superadministrador
    two_orgs["b"].post("/api/usage/map-load")
    # Una simulación nueva (modelo único, no reutilizada de la caché) se cuenta en el uso de la organización.
    a, pid = two_orgs["a"], two_orgs["pid"]
    net = a.get(f"/api/projects/{pid}/network").json()
    for f in net["network"]["features"]:
        if f["id"] == "J-1":
            f["properties"]["elevation"] += uuid.uuid4().int % 1000 / 10000
    v = a.put(f"/api/projects/{pid}/network", json={"base_version": net["version"], "kind": "manual",
                                                    "network": net["network"]}).json()["version"]
    assert a.post(f"/api/projects/{pid}/simulate", json={"model_version": v}).json()["cached"] is False
    orgs = {o["name"]: o for o in s.get("/api/admin/orgs").json()}
    a_org = orgs["Organización A"]
    assert a_org["usage"]["projects"] >= 1 and a_org["usage"]["simulations"] >= 1
    assert orgs["Organización B"]["usage"]["map_loads"] >= 1
    r = s.post("/api/admin/orgs", json={"name": f"APR Nueva {uuid.uuid4().hex[:6]}", "plan": "basico",
                                        "admin_email": uniq("nuevo-admin")})
    assert r.status_code == 201 and "/invitacion?token=" in r.json()["admin_invitation"]
    # Límite de proyectos por plan
    org_b = two_orgs["org_b"]
    assert s.patch(f"/api/admin/orgs/{org_b}", json={"limits": {"max_projects": 0}}).status_code == 200
    r = two_orgs["b"].post("/api/projects", json={"name": "excede"})
    assert r.status_code == 403 and "límite" in r.json()["detail"]
    # Límite de cargas de mapa
    s.patch(f"/api/admin/orgs/{org_b}", json={"limits": {"max_map_loads_month": 0}})
    assert two_orgs["b"].post("/api/usage/map-load").json()["allowed"] is False
    # Suspender una cuenta cierra sus sesiones
    email = uniq("suspendida")
    uid, _ = make_user(email, "Organización B", "lector")
    c = new_client(email)
    assert s.patch(f"/api/admin/users/{uid}", json={"active": False}).status_code == 200
    assert c.get("/api/projects").status_code == 401
    assert new_client().post("/api/auth/login", json={"email": email, "password": TEST_PASSWORD}).status_code == 401
    # Suspender la organización deja sin acceso a sus proyectos
    s.patch(f"/api/admin/orgs/{org_b}", json={"suspended": True})
    assert two_orgs["b"].get("/api/projects").json() == []
    s.patch(f"/api/admin/orgs/{org_b}", json={"suspended": False, "limits": {}})
