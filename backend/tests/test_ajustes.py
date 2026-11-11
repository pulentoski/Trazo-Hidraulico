"""Ajustes: cada rol accede solo a sus secciones (Mi cuenta para todos; Organización para administradores;
Plataforma para el superadministrador), perfil editable y ajustes de la organización (perfil de diseño por
defecto, vida útil y precios) aplicados a los proyectos nuevos."""
import pytest

from tests.conftest import make_user, new_client

ORG = "Organización ajustes"
ROLES = ["admin", "proyectista", "revisor", "lector"]


@pytest.fixture(scope="module")
def users(database):
    out = {}
    for role in ROLES:
        _, org_id = make_user(f"{role}-ajustes@trazo.test", ORG, role)
        out[role] = new_client(f"{role}-ajustes@trazo.test")
    make_user("super-ajustes@trazo.test", ORG, "lector", superadmin=True)
    out["super"] = new_client("super-ajustes@trazo.test")
    yield org_id, out
    for c in out.values():
        c.close()


@pytest.mark.parametrize("role", ROLES)
def test_mi_cuenta_para_todos(users, role):
    _, c = users
    me = c[role].get("/api/auth/me").json()
    assert me["email"] == f"{role}-ajustes@trazo.test"
    r = c[role].patch("/api/auth/me", json={"name": f"Usuario {role}"})
    assert r.status_code == 200 and r.json()["name"] == f"Usuario {role}"
    assert c[role].patch("/api/auth/me", json={"name": ""}).status_code == 422
    assert c[role].patch("/api/auth/me", json={"name": "x", "email": "otro@x.cl"}).status_code == 422
    assert c[role].get("/api/auth/sessions").status_code == 200


@pytest.mark.parametrize("role", ROLES)
def test_organizacion_solo_administrador(users, role):
    org_id, c = users
    expected = 200 if role == "admin" else 403
    for path in ("members", "audit", "usage"):
        assert c[role].get(f"/api/orgs/{org_id}/{path}").status_code == expected, path
    # Los ajustes se leen (los usan los proyectos) pero solo el administrador los cambia.
    assert c[role].get(f"/api/orgs/{org_id}/settings").status_code == 200
    assert c[role].put(f"/api/orgs/{org_id}/settings", json={}).status_code == expected


@pytest.mark.parametrize("role", ROLES)
def test_plataforma_solo_superadministrador(users, role):
    _, c = users
    for path in ("/api/admin/system", "/api/admin/orgs", "/api/admin/users", "/api/admin/maps"):
        assert c[role].get(path).status_code == 404, path  # no existe para quien no es superadministrador
    s = c["super"].get("/api/admin/system")
    assert s.status_code == 200
    body = s.json()
    assert body["engine"]["epanet_tag"] and {x["name"] for x in body["services"]} >= {"API", "Base de datos", "Caché"}
    assert set(body["plans"]) == {"basico", "profesional", "ilimitado"}
    assert body["last_backup"] is None or "fecha" in body["last_backup"]


def test_ajustes_de_organizacion_se_aplican(users):
    org_id, c = users
    admin = c["admin"]
    profiles = admin.get("/api/design-profiles").json()
    target = profiles[-1]["id"]
    st = {"default_profile_id": target, "service_life": {"PVC": 45, "HDPE": 55}, "default_life": 40, "life_verified": True,
          "prices": [{"material": "*", "dn_max": 100000, "price_m": 77000}], "prices_verified": True}
    r = admin.put(f"/api/orgs/{org_id}/settings", json=st)
    assert r.status_code == 200 and r.json()["default_profile_id"] == target
    assert admin.put(f"/api/orgs/{org_id}/settings", json={"default_profile_id": 999999}).status_code == 422
    assert c["lector"].get(f"/api/orgs/{org_id}/settings").json()["service_life"]["PVC"] == 45
    # Proyecto nuevo sin perfil: toma el de la organización; el resumen usa su vida útil y precios
    p = c["proyectista"].post("/api/projects", json={"name": "Proyecto con ajustes de la organización"}).json()
    assert p["design_profile_id"] == target
    ss = c["proyectista"].get(f"/api/projects/{p['id']}/summary/settings").json()
    assert ss["service_life"]["PVC"] == 45 and ss["default_life"] == 40 and ss["prices"][0]["price_m"] == 77000
    assert ss["life_verified"] and ss["prices_verified"]
    # Un proyecto con valores propios los conserva
    ss["prices"][0]["price_m"] = 1000
    c["proyectista"].put(f"/api/projects/{p['id']}/summary/settings", json=ss)
    assert c["proyectista"].get(f"/api/projects/{p['id']}/summary/settings").json()["prices"][0]["price_m"] == 1000
    assert c["lector"].post("/api/projects", json={"name": "No"}).status_code == 403
    admin.put(f"/api/orgs/{org_id}/settings", json={})
