"""QA de validación (pruebas 7–9): errores bloqueantes antes del motor y cota faltante."""
import pytest

from app.services import simulation as sim_svc
from tests.helpers import fc, node, pipe
from tests.qa.common import LAT0, LON0, base_network, new_project, save, simulate


@pytest.fixture
def engine_must_not_run(monkeypatch):
    calls = []

    def fail(model):
        calls.append(model)
        raise AssertionError("el motor no debía ejecutarse")

    monkeypatch.setattr(sim_svc, "run_model", fail)
    return calls


def _codes(report, kind="errors"):
    return {i["code"] for i in report[kind]}


def _has_results(client, pid, version):
    return next(v for v in client.get(f"/api/projects/{pid}/versions").json() if v["number"] == version)["has_results"]


# 7 ─ Sin fuente
def test_07_sin_fuente_bloquea_y_no_ejecuta_el_motor(client, engine_must_not_run):
    pid = new_project(client, "QA 7 sin fuente")
    net = fc(node("J1", lon=LON0, lat=LAT0, elevation=20.0, base_demand=2.0),
             node("J2", lon=LON0 + 0.003, lat=LAT0, elevation=18.0, base_demand=1.0),
             pipe("P1", "J1", "J2", [[LON0, LAT0], [LON0 + 0.003, LAT0]], length_choice="manual",
                  length_hydraulic_m=300.0))
    v = save(client, pid, net)["version"]
    code, body = simulate(client, pid, v)
    assert code == 422 and body["status"] == "blocked" and body["model_version"] == v
    assert "E_NO_SOURCE" in _codes(body["validation"])
    assert engine_must_not_run == []
    assert not _has_results(client, pid, v)


# 8 ─ Nudo desconectado
def test_08_nudo_sin_tramos_se_detecta(client, engine_must_not_run):
    pid = new_project(client, "QA 8 nudo aislado")
    net = base_network(client)
    net["features"].append(node("J2", lon=LON0 + 0.006, lat=LAT0, elevation=20.0, base_demand=1.0))
    v = save(client, pid, net)["version"]
    report = client.post(f"/api/projects/{pid}/validate", json={"model_version": v}).json()
    assert not report["ok"]
    assert any(i["code"] == "E_ISOLATED_NODE" and i["element_id"] == "J2" for i in report["errors"])
    code, _ = simulate(client, pid, v)
    assert code == 422 and engine_must_not_run == []


def test_08_isla_sin_camino_a_la_fuente_se_detecta(client, engine_must_not_run):
    pid = new_project(client, "QA 8 isla")
    net = base_network(client)
    a, b = [LON0 + 0.006, LAT0], [LON0 + 0.009, LAT0]
    net["features"] += [node("J2", lon=a[0], lat=a[1], elevation=20.0, base_demand=1.0),
                        node("J3", lon=b[0], lat=b[1], elevation=19.0, base_demand=1.0),
                        pipe("P2", "J2", "J3", [a, b], length_choice="manual", length_hydraulic_m=300.0)]
    v = save(client, pid, net)["version"]
    report = client.post(f"/api/projects/{pid}/validate", json={"model_version": v}).json()
    islands = {i["element_id"] for i in report["errors"] if i["code"] == "E_DISCONNECTED_NODE"}
    assert islands == {"J2", "J3"}
    code, _ = simulate(client, pid, v)
    assert code == 422 and engine_must_not_run == []


# 9 ─ Cota faltante
def test_09_elemento_nuevo_sin_cota_es_error_bloqueante(client, engine_must_not_run):
    pid = new_project(client, "QA 9 sin cota")
    net = base_network(client, j1_elevation=None)
    j1 = next(f for f in net["features"] if f["id"] == "J1")
    assert j1["properties"]["elevation"] is None
    v = save(client, pid, net)["version"]
    doc = client.get(f"/api/projects/{pid}/network", params={"version": v}).json()
    stored = next(f for f in doc["network"]["features"] if f["id"] == "J1")
    assert stored["properties"]["elevation"] is None  # no se completa con un valor supuesto
    report = client.post(f"/api/projects/{pid}/validate", json={"model_version": v}).json()
    assert any(i["code"] == "E_MISSING_PARAM" and i["element_id"] == "J1" and "cota" in i["message"]
               for i in report["errors"])
    code, _ = simulate(client, pid, v)
    assert code == 422 and engine_must_not_run == []

    # Al ingresar la cota se puede simular.
    v2 = save(client, pid, base_network(client))["version"]
    code, sim = simulate(client, pid, v2)
    assert code == 200 and sim["status"] == "ok"


def test_09_estanque_nuevo_sin_cota_es_error_bloqueante(client):
    pid = new_project(client, "QA 9 estanque sin cota")
    net = base_network(client)
    next(f for f in net["features"] if f["id"] == "E1")["properties"]["elevation"] = None
    v = save(client, pid, net)["version"]
    report = client.post(f"/api/projects/{pid}/validate", json={"model_version": v}).json()
    assert any(i["code"] == "E_MISSING_PARAM" and i["element_id"] == "E1" for i in report["errors"])


INP_SIN_COTA = """[TITLE]
 QA cota faltante
[JUNCTIONS]
 J1
 J2\t18\t1
[TANKS]
 E1\t50\t3\t0.5\t4\t5\t0\t*
[PIPES]
 P1\tE1\tJ1\t300\t83\t150\t0\tOpen
 P2\tJ1\tJ2\t200\t83\t150\t0\tOpen
[OPTIONS]
 UNITS\tLPS
[END]
"""


def test_09_importacion_sin_cota_advierte_explicitamente(client):
    r = client.post("/api/projects/import", files={"file": ("sin_cota.inp", INP_SIN_COTA.encode(), "text/plain")})
    assert r.status_code == 201, r.text
    body = r.json()
    assert any("sin cota" in n and "J1" in n for n in body["notes"])
    pid, v = body["project"]["id"], body["version"]
    doc = client.get(f"/api/projects/{pid}/network").json()
    props = {f["id"]: f["properties"] for f in doc["network"]["features"]}
    assert props["J1"]["elevation_source"] == "supuesta" and props["J2"]["elevation_source"] == "inp"
    report = client.post(f"/api/projects/{pid}/validate", json={"model_version": v}).json()
    assumed = [w for w in report["warnings"] if w["code"] == "W_ELEVATION_ASSUMED"]
    assert [w["element_id"] for w in assumed] == ["J1"]
    assert "supuesta" in assumed[0]["message"] and "0 m" in assumed[0]["message"]
    assert report["ok"]  # advertencia, no error: el archivo importado sigue siendo simulable
