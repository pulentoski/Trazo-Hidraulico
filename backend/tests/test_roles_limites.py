"""Roles y permisos (Super Admin / Admin de organización), intentos de escalar privilegios, límites por plan
(usuarios, invitaciones por día, expiración) y Panel admin (resumen, ficha, soporte, suspender y eliminar con
confirmación escrita). Cada regla se valida en el backend, no solo en la interfaz."""
import json
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select

from tests.conftest import make_user, new_client


def uniq(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}@trazo.test"


def set_plan(org_id, plan: str, limits: dict | None = None) -> None:
    from app.core.db import get_sessionmaker
    from app.models import Organization

    with get_sessionmaker()() as s:
        o = s.get(Organization, org_id)
        o.plan, o.limits = plan, limits
        s.commit()


def token_of(link: str) -> str:
    return link.split("token=")[1]


@pytest.fixture()
def org(database):
    """Organización nueva (plan básico) con un administrador, un proyectista y un lector."""
    name = f"Org roles {uuid.uuid4().hex[:6]}"
    out = {"name": name}
    for role in ("admin", "proyectista", "lector"):
        email = uniq(role)
        uid, org_id = make_user(email, name, role)
        out[role], out[f"{role}_id"], out[f"{role}_email"] = new_client(email), uid, email
    out["id"] = org_id
    set_plan(org_id, "basico")
    sa = uniq("super")
    make_user(sa, f"Plataforma {uuid.uuid4().hex[:4]}", "admin", superadmin=True)
    out["super"], out["super_email"] = new_client(sa), sa
    yield out
    for k in ("admin", "proyectista", "lector", "super"):
        out[k].close()


# ── Administrador de la organización ──

def test_admin_edita_datos_pero_no_plan_ni_limites(org):
    a, oid = org["admin"], org["id"]
    r = a.patch(f"/api/orgs/{oid}", json={"name": org["name"] + " SpA", "info": {"rut": "76.123.456-7", "comuna": "Vicuña"}})
    assert r.status_code == 200 and r.json()["info"]["comuna"] == "Vicuña"
    org["name"] += " SpA"
    assert org["lector"].get(f"/api/orgs/{oid}").json()["info"]["rut"] == "76.123.456-7"  # los miembros leen los datos
    # Plan, límites o suspensión: el esquema del administrador no los acepta y la ruta de plataforma no existe para él.
    for body in ({"plan": "ilimitado"}, {"limits": {"max_users": 999}}, {"suspended": True}):
        assert a.patch(f"/api/orgs/{oid}", json=body).status_code == 422, body
        assert a.patch(f"/api/admin/orgs/{oid}", json=body).status_code == 404, body
    assert a.post("/api/admin/orgs", json={"name": "Otra org"}).status_code == 404
    assert a.request("DELETE", f"/api/admin/orgs/{oid}", json={"confirm": org["name"]}).status_code == 404
    assert a.put("/api/admin/plans", json={"plans": {"basico": {"max_users": 100}}}).status_code == 404
    # Otros roles no editan los datos
    assert org["proyectista"].patch(f"/api/orgs/{oid}", json={"name": "Hackeada"}).status_code == 403
    log = a.get(f"/api/orgs/{oid}/audit").json()
    assert any(x["action"] == "organizacion.datos" for x in log)


def test_admin_no_nombra_superadmin_ni_toca_al_superadmin(org):
    a, oid = org["admin"], org["id"]
    assert a.patch(f"/api/admin/users/{org['lector_id']}", json={"is_superadmin": True}).status_code == 404
    # Un superadministrador miembro de la organización no puede ser degradado por el administrador
    sa_email = uniq("super-miembro")
    sa_id, _ = make_user(sa_email, org["name"], "admin", superadmin=True)
    assert a.patch(f"/api/orgs/{oid}/members/{sa_id}", json={"role": "lector"}).status_code == 403
    assert a.patch(f"/api/orgs/{oid}/members/{sa_id}", json={"active": False}).status_code == 403
    assert a.post(f"/api/orgs/{oid}/members/{sa_id}/reset-link").status_code == 403


def test_roles_hasta_admin_y_auditoria(org):
    a, oid = org["admin"], org["id"]
    r = a.patch(f"/api/orgs/{oid}/members/{org['lector_id']}", json={"role": "admin"})
    assert r.status_code == 200 and r.json()["role"] == "admin"
    assert a.patch(f"/api/orgs/{oid}/members/{org['lector_id']}", json={"role": "revisor"}).status_code == 200
    assert a.patch(f"/api/orgs/{oid}/members/{org['lector_id']}", json={"role": "superadmin"}).status_code == 422
    log = a.get(f"/api/orgs/{oid}/audit", params={"action": "permiso.cambio"}).json()
    assert len(log) >= 2 and log[0]["detail"]["despues"]["rol"] == "revisor"


@pytest.mark.parametrize("who", ["proyectista", "lector"])
def test_sin_permiso_de_administrar_no_escala(org, who):
    c, oid = org[who], org["id"]
    # Intentos de darse más rol, invitar a un admin o cambiar a otros: rechazados en el backend.
    assert c.patch(f"/api/orgs/{oid}/members/{org[f'{who}_id']}", json={"role": "admin"}).status_code == 403
    assert c.patch(f"/api/orgs/{oid}/members/{org['admin_id']}", json={"active": False}).status_code == 403
    assert c.post(f"/api/orgs/{oid}/invitations", json={"email": uniq("x"), "role": "admin", "send_email": False}).status_code == 403
    assert c.post(f"/api/orgs/{oid}/invitations", json={"email": uniq("x"), "role": "lector", "send_email": False}).status_code == 403
    assert c.get(f"/api/admin/orgs/{oid}").status_code == 404
    assert c.post(f"/api/admin/orgs/{oid}/support").status_code == 404
    assert c.put(f"/api/orgs/{oid}/settings", json={}).status_code == 403


def test_nadie_asigna_rol_superior_al_propio(org):
    """Regla de jerarquía en la función común (un rol con permiso de administrar pero de rango menor)."""
    from app.services import auth

    oid = org["id"]
    p = auth.Principal(user_id=uuid.uuid4(), email="x", roles={oid: "proyectista"})
    with pytest.raises(auth.AuthError) as e:
        auth.check_assignable(p, oid, "admin")
    assert e.value.status == 403
    auth.check_assignable(p, oid, "proyectista")
    auth.check_assignable(p, oid, "lector")
    auth.check_assignable(auth.Principal(user_id=None, email="s", is_superadmin=True), oid, "admin")


def test_siempre_queda_un_admin_activo(org):
    a, s, oid = org["admin"], org["super"], org["id"]
    # El único administrador no puede quitarse el rol ni desactivarse
    assert a.patch(f"/api/orgs/{oid}/members/{org['admin_id']}", json={"role": "lector"}).status_code == 400
    assert a.patch(f"/api/orgs/{oid}/members/{org['admin_id']}", json={"active": False}).status_code == 400
    # Ni el superadministrador lo deja sin administradores
    assert s.patch(f"/api/orgs/{oid}/members/{org['admin_id']}", json={"role": "lector"}).status_code == 400
    assert s.patch(f"/api/admin/users/{org['admin_id']}", json={"active": False}).status_code == 400
    # Con un segundo administrador sí
    a.patch(f"/api/orgs/{oid}/members/{org['proyectista_id']}", json={"role": "admin"})
    assert s.patch(f"/api/orgs/{oid}/members/{org['admin_id']}", json={"role": "lector"}).status_code == 200


# ── Límites por plan ──

def test_tope_de_usuarios_por_plan(org):
    a, s, oid = org["admin"], org["super"], org["id"]
    assert s.patch(f"/api/admin/orgs/{oid}", json={"limits": {"max_users": 4}}).status_code == 200
    u = a.get(f"/api/orgs/{oid}/usage").json()
    assert u["users"] == 3 and u["limits"]["max_users"] == 4 and u["invite_days"] == 7
    r = a.post(f"/api/orgs/{oid}/invitations", json={"email": uniq("cuarto"), "role": "lector", "send_email": False})
    assert r.status_code == 201
    link = r.json()["link"]
    # Con la invitación pendiente se llega al tope: no se puede invitar a otra persona
    r = a.post(f"/api/orgs/{oid}/invitations", json={"email": uniq("quinto"), "role": "lector", "send_email": False})
    assert r.status_code == 403 and r.json()["detail"] == "Su plan permite 4 usuarios."
    assert new_client().post(f"/api/auth/invitation/{token_of(link)}", json={"name": "C", "password": "Cuarto-2026-x"}).status_code == 204
    assert a.get(f"/api/orgs/{oid}/usage").json()["users"] == 4
    # Desactivar y reactivar respeta el tope
    assert a.patch(f"/api/orgs/{oid}/members/{org['lector_id']}", json={"active": False}).status_code == 200
    extra = uniq("extra")
    eid, _ = make_user(extra, org["name"], "lector")  # ocupa el cupo liberado
    r = a.patch(f"/api/orgs/{oid}/members/{org['lector_id']}", json={"active": True})
    assert r.status_code == 403 and "Su plan permite 4 usuarios" in r.json()["detail"]


def test_tope_al_aceptar_invitacion(org):
    a, s, oid = org["admin"], org["super"], org["id"]
    link = a.post(f"/api/orgs/{oid}/invitations", json={"email": uniq("tarde"), "role": "lector", "send_email": False}).json()["link"]
    s.patch(f"/api/admin/orgs/{oid}", json={"limits": {"max_users": 3}})  # el plan baja después de invitar
    r = new_client().post(f"/api/auth/invitation/{token_of(link)}", json={"name": "T", "password": "Tarde-2026-xx"})
    assert r.status_code == 403 and "Su plan permite 3 usuarios" in r.json()["detail"]


def test_invitaciones_por_dia_y_expiracion(org):
    a, s, oid = org["admin"], org["super"], org["id"]
    s.patch(f"/api/admin/orgs/{oid}", json={"limits": {"max_invites_day": 2, "max_users": None}})
    for _ in range(2):
        assert a.post(f"/api/orgs/{oid}/invitations", json={"email": uniq("dia"), "role": "lector", "send_email": False}).status_code == 201
    r = a.post(f"/api/orgs/{oid}/invitations", json={"email": uniq("dia"), "role": "lector", "send_email": False})
    assert r.status_code == 429 and "2 invitaciones por día" in r.json()["detail"]
    inv = a.get(f"/api/orgs/{oid}/invitations").json()
    assert len(inv) == 2
    days = (__import__("datetime").datetime.fromisoformat(inv[0]["expires_at"]) -
            __import__("datetime").datetime.fromisoformat(inv[0]["created_at"]))
    assert timedelta(days=6, hours=23) < days <= timedelta(days=7, minutes=1)
    # Anular una invitación (queda en auditoría) y que no se pueda aceptar
    assert a.delete(f"/api/orgs/{oid}/invitations/{inv[0]['id']}").status_code == 204
    assert len(a.get(f"/api/orgs/{oid}/invitations").json()) == 1
    assert any(x["action"] == "permiso.invitacion_anulada" for x in a.get(f"/api/orgs/{oid}/audit").json())


def test_invitacion_vencida_no_sirve(org):
    from app.core.db import get_sessionmaker
    from app.models import OneTimeToken
    from app.services import auth

    a, oid = org["admin"], org["id"]
    link = a.post(f"/api/orgs/{oid}/invitations", json={"email": uniq("vence"), "role": "lector", "send_email": False}).json()["link"]
    from app.core import security

    with get_sessionmaker()() as ses:
        t = ses.get(OneTimeToken, security.token_hash(token_of(link)))
        t.expires_at = auth.now() - timedelta(minutes=1)
        ses.commit()
    assert new_client().get(f"/api/auth/invitation/{token_of(link)}").status_code == 400


def test_invitar_miembro_activo_es_conflicto(org):
    a, oid = org["admin"], org["id"]
    r = a.post(f"/api/orgs/{oid}/invitations", json={"email": org["lector_email"], "role": "lector", "send_email": False})
    assert r.status_code == 409


def test_planes_configurables_por_superadmin(org):
    s, a, oid = org["super"], org["admin"], org["id"]
    before = s.get("/api/admin/system").json()["plans"]
    assert before["basico"]["max_users"] == 5 and before["basico"]["max_invites_day"] == 10
    try:
        r = s.put("/api/admin/plans", json={"plans": {"basico": {"max_users": 2}}})
        assert r.status_code == 200 and r.json()["basico"]["max_users"] == 2
        assert a.get(f"/api/orgs/{oid}/usage").json()["limits"]["max_users"] == 2
        r = a.post(f"/api/orgs/{oid}/invitations", json={"email": uniq("x"), "role": "lector", "send_email": False})
        assert r.status_code == 403 and r.json()["detail"] == "Su plan permite 2 usuarios."
        assert s.put("/api/admin/plans", json={"plans": {"basico": {"inventado": 1}}}).status_code == 422
        assert s.put("/api/admin/plans", json={"plans": {"basico": {"max_users": -1}}}).status_code == 422
    finally:
        s.put("/api/admin/plans", json={"plans": {"basico": {"max_users": 5}}})


# ── Panel admin ──

def test_resumen_y_ficha(org):
    s, oid = org["super"], org["id"]
    s.patch(f"/api/admin/orgs/{oid}", json={"limits": {"max_users": 3}})  # 3 de 3: cerca del límite
    ov = s.get("/api/admin/overview").json()
    assert ov["orgs_active"] >= 1 and ov["users_total"] >= 3 and ov["recent_audit"]
    assert any(n["org"]["id"] == str(oid) and n["worst"]["key"] == "max_users" for n in ov["near_limit"])
    d = s.get(f"/api/admin/orgs/{oid}").json()
    assert d["org"]["name"] == org["name"] and len(d["members"]) == 3
    assert {x["key"] for x in d["limits_use"]} >= {"max_users", "max_projects", "max_ortho_mb"}
    assert all("last_login_at" in m and "role" in m for m in d["members"])


def test_modo_soporte_con_auditoria(org):
    s, oid = org["super"], org["id"]
    assert s.get(f"/api/orgs/{oid}/settings").status_code != 200  # no es miembro
    assert s.post(f"/api/admin/orgs/{oid}/support").status_code == 204
    me = s.get("/api/auth/me").json()
    assert me["support_org"]["id"] == str(oid) and me["current_org"] == str(oid)
    assert s.get(f"/api/orgs/{oid}/settings").status_code == 200
    p = s.post("/api/projects", json={"name": "Creado por soporte"})
    assert p.status_code == 201
    assert s.post("/api/auth/support/exit").status_code == 204
    assert s.get("/api/auth/me").json()["support_org"] is None
    assert s.get(f"/api/orgs/{oid}/settings").status_code != 200
    log = org["admin"].get(f"/api/orgs/{oid}/audit").json()
    acts = {x["action"] for x in log}
    assert {"soporte.entrada", "soporte.salida"} <= acts
    assert all(x["detail"].get("soporte") for x in log if x["action"].startswith("soporte."))


def test_suspender_y_eliminar_con_confirmacion_escrita(org):
    s, oid = org["super"], org["id"]
    assert s.patch(f"/api/admin/orgs/{oid}", json={"suspended": True, "confirm": "otro nombre"}).status_code == 400
    assert s.patch(f"/api/admin/orgs/{oid}", json={"suspended": True, "confirm": org["name"]}).status_code == 200
    assert org["admin"].get("/api/projects").json() == []
    assert s.patch(f"/api/admin/orgs/{oid}", json={"suspended": False}).status_code == 200
    assert s.request("DELETE", f"/api/admin/orgs/{oid}", json={"confirm": "mal"}).status_code == 400
    assert s.request("DELETE", f"/api/admin/orgs/{oid}", json={"confirm": org["name"]}).status_code == 204
    assert s.get(f"/api/admin/orgs/{oid}").status_code == 404
    from app.core.db import get_sessionmaker
    from app.models import AuditLog

    with get_sessionmaker()() as ses:
        a = ses.scalars(select(AuditLog).where(AuditLog.action == "organizacion.eliminada").order_by(AuditLog.id.desc())).first()
        assert a.detail["id"] == str(oid) and a.detail["nombre"] == org["name"]


def test_superadmin_nombra_superadmin_y_no_se_quita_a_si_mismo(org):
    s = org["super"]
    users = {u["email"]: u for u in s.get("/api/admin/users").json()}
    me = users[org["super_email"]]
    assert s.patch(f"/api/admin/users/{me['id']}", json={"is_superadmin": False}).status_code == 400
    lid = str(org["lector_id"])
    assert s.patch(f"/api/admin/users/{lid}", json={"is_superadmin": True}).json()["is_superadmin"] is True
    assert s.patch(f"/api/admin/users/{lid}", json={"is_superadmin": False}).json()["is_superadmin"] is False


def test_ruta_api_de_organizaciones_solo_superadmin(org):
    for k in ("admin", "proyectista", "lector"):
        for path in ("/api/admin/overview", f"/api/admin/orgs/{org['id']}"):
            assert org[k].get(path).status_code == 404, (k, path)


__all__ = ["json"]
