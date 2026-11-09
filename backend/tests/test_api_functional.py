"""Pruebas funcionales de la API: crear proyecto, editar red, cambiar diámetro, simular, versionar, exportar."""
import json
from pathlib import Path

import pytest

from tests.helpers import fc, node, pipe


def pvc(client, dn, cls="C10"):
    items = client.get("/api/catalog/pipes").json()
    return next(i for i in items if i["material"] == "PVC" and i["dn"] == dn and i["pipe_class"] == cls)


def network(client, dn_p2=110):
    c1, c2 = pvc(client, 160), pvc(client, dn_p2)

    def from_catalog(item):
        return dict(material="PVC", dn=item["dn"], pipe_class=item["pipe_class"], catalog_pipe_id=item["id"],
                    inner_diameter_mm=item["inner_diameter_mm"], roughness=item["hw_c"])

    return fc(
        node("R1", "reservoir", lon=-70.6600, lat=-33.4500, elevation=95.0, head=100.0),
        node("J1", lon=-70.6550, lat=-33.4500, elevation=60.0, base_demand=6.0),
        node("J2", lon=-70.6500, lat=-33.4520, elevation=58.0, base_demand=4.0),
        node("J3", lon=-70.6450, lat=-33.4530, elevation=55.0, base_demand=3.0),
        pipe("P1", "R1", "J1", [[-70.66, -33.45], [-70.6575, -33.4502], [-70.655, -33.45]], **from_catalog(c1)),
        pipe("P2", "J1", "J2", [[-70.655, -33.45], [-70.65, -33.452]], **from_catalog(c2)),
        pipe("P3", "J2", "J3", [[-70.65, -33.452], [-70.645, -33.453]], **from_catalog(c2)),
    )


@pytest.fixture(scope="module")
def project(client):
    r = client.post("/api/projects", json={"name": "Funcional", "description": "Prueba"})
    assert r.status_code == 201, r.text
    return r.json()


def test_create_project_has_initial_version(client, project):
    assert project["latest_version"] == 1 and project["version_count"] == 1
    assert project["design_profile_id"] is not None
    doc = client.get(f"/api/projects/{project['id']}/network").json()
    assert doc["version"] == 1 and doc["network"]["features"] == []
    assert doc["options"]["headloss"] == "H-W"


def test_projects_listing_and_patch(client, project):
    assert any(p["id"] == project["id"] for p in client.get("/api/projects").json())
    r = client.patch(f"/api/projects/{project['id']}", json={"description": "Editado"})
    assert r.status_code == 200 and r.json()["description"] == "Editado"


def test_edit_network_and_simulate(client, project):
    pid = project["id"]
    r = client.put(f"/api/projects/{pid}/network", json={"base_version": 1, "kind": "manual", "network": network(client)})
    assert r.status_code == 200, r.text
    saved = r.json()
    assert saved["version"] == 2 and saved["created"]
    lens = saved["lengths"]["P1"]
    assert 400 < lens["length_plan_m"] < 500
    assert lens["length_slope_m"] > lens["length_plan_m"]  # desnivel de 35 m
    assert lens["length_hydraulic_m"] == lens["length_slope_m"]

    doc = client.get(f"/api/projects/{pid}/network", params={"version": 2}).json()
    p1 = next(f for f in doc["network"]["features"] if f["id"] == "P1")
    assert len(p1["geometry"]["coordinates"]) == 3  # vértice intermedio conservado

    r = client.post(f"/api/projects/{pid}/simulate", json={"model_version": 2})
    assert r.status_code == 200, r.text
    sim = r.json()
    assert sim["model_version"] == 2 and sim["status"] in ("ok", "warning")
    assert sim["engine"]["wheel_version"] == "2.3.5"
    assert sim["nodes"]["J3"]["pressure"][0] > 0
    q1 = sim["links"]["P1"]["flow"][0]
    assert q1 == pytest.approx(13.0, abs=1e-3)  # continuidad: suma de demandas
    assert sim["nodes"]["R1"]["demand"][0] == pytest.approx(-13.0, abs=1e-3)
    assert not sim["cached"]

    again = client.post(f"/api/projects/{pid}/simulate", json={"model_version": 2}).json()
    assert again["cached"] and again["run_id"] == sim["run_id"]
    assert again["nodes"]["J3"]["pressure"] == sim["nodes"]["J3"]["pressure"]


def test_change_diameter_creates_version_and_changes_results(client, project):
    pid = project["id"]
    before = client.post(f"/api/projects/{pid}/simulate", json={"model_version": 2}).json()
    r = client.put(f"/api/projects/{pid}/network", json={"base_version": 2, "kind": "manual",
                                                          "network": network(client, dn_p2=75)})
    assert r.status_code == 200
    v3 = r.json()["version"]
    assert v3 == 3
    after = client.post(f"/api/projects/{pid}/simulate", json={"model_version": v3}).json()
    assert after["links"]["P2"]["headloss"][0] > before["links"]["P2"]["headloss"][0] * 3
    assert after["nodes"]["J3"]["pressure"][0] < before["nodes"]["J3"]["pressure"][0]
    # Cuello de botella detectado con el criterio del perfil (10 m/km, no verificado)
    assert any(a["code"] == "BOTTLENECK" and a["element_id"] == "P2" for a in after["alerts"])
    assert after["profile_verified"] is False


def test_versions_are_immutable_and_listed(client, project):
    pid = project["id"]
    versions = client.get(f"/api/projects/{pid}/versions").json()
    assert [v["number"] for v in versions] == [3, 2, 1]
    assert versions[1]["has_results"] and versions[1]["node_count"] == 4 and versions[1]["link_count"] == 3
    v2 = client.get(f"/api/projects/{pid}/network", params={"version": 2}).json()
    p2 = next(f for f in v2["network"]["features"] if f["id"] == "P2")
    assert p2["properties"]["dn"] == 110  # la versión 2 no cambió


def test_autosave_with_identical_content_does_not_create_version(client, project):
    pid = project["id"]
    doc = client.get(f"/api/projects/{pid}/network").json()
    r = client.put(f"/api/projects/{pid}/network", json={"base_version": doc["version"], "kind": "auto",
                                                          "network": doc["network"]})
    assert r.status_code == 200 and r.json()["created"] is False and r.json()["version"] == doc["version"]


def test_stale_base_version_conflicts(client, project):
    r = client.put(f"/api/projects/{project['id']}/network", json={"base_version": 1, "network": network(client)})
    assert r.status_code == 409


def test_options_change_formula_and_pda(client, project):
    pid = project["id"]
    doc = client.get(f"/api/projects/{pid}/network").json()
    opts = {"headloss": "H-W", "demand_model": "PDA", "minimum_pressure": 0, "required_pressure": 15,
            "pressure_exponent": 0.5}
    r = client.put(f"/api/projects/{pid}/network", json={"base_version": doc["version"], "kind": "manual",
                                                          "options": opts, "network": doc["network"]})
    v = r.json()["version"]
    sim = client.post(f"/api/projects/{pid}/simulate", json={"model_version": v}).json()
    assert sim["options"]["demand_model"] == "PDA"
    assert "DEMAND MODEL\tPDA" in client.get(f"/api/projects/{pid}/export.inp").text


def test_export_inp(client, project):
    r = client.get(f"/api/projects/{project['id']}/export.inp", params={"version": 2})
    assert r.status_code == 200
    text = r.text
    for section in ("[JUNCTIONS]", "[RESERVOIRS]", "[PIPES]", "[COORDINATES]", "[VERTICES]", "[OPTIONS]"):
        assert section in text
    assert "versión 2" in text


def test_engine_and_catalog_endpoints(client):
    eng = client.get("/api/engine").json()
    assert eng["epanet_sha"] == "444725fbf16ab28b0470ef0ed281dc4849d49583"
    profiles = client.get("/api/design-profiles").json()
    assert profiles and profiles[0]["status"] == "no verificado" and profiles[0]["verified"] is False
    pipes = client.get("/api/catalog/pipes").json()
    assert {p["material"] for p in pipes} == {"PVC", "HDPE"}


def test_unknown_project_404(client):
    assert client.get("/api/projects/00000000-0000-0000-0000-000000000000").status_code == 404


def test_delete_project(client):
    pid = client.post("/api/projects", json={"name": "Borrar"}).json()["id"]
    assert client.delete(f"/api/projects/{pid}").status_code == 204
    assert client.get(f"/api/projects/{pid}").status_code == 404


def test_openapi_schema_is_committed_and_up_to_date():
    from app.main import app

    committed = Path("/app/openapi.committed.json")
    if not committed.exists():
        pytest.skip("openapi.json del frontend no montado")
    current = json.loads(json.dumps(app.openapi(), sort_keys=True))
    assert json.loads(committed.read_text()) == current, \
        "frontend/src/api/openapi.json está desactualizado: ejecute `make gen-types`"
