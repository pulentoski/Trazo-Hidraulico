"""QA de ida y vuelta .inp (prueba 10) y de versiones con sus corridas (prueba 11)."""
import uuid

import numpy as np
import pytest
from sqlalchemy import text

from app.core.db import get_sessionmaker
from tests.qa.common import QA, base_network, new_project, save, simulate

VARS_NODE = ("pressure", "head", "demand")
VARS_LINK = ("flow", "velocity", "headloss")


def _props(doc):
    return {f["id"]: f["properties"] for f in doc["network"]["features"]}


# 10 ─ Exportar → importar → simular
def test_10_ida_y_vuelta_inp_conserva_datos_y_resultados(client):
    pid = new_project(client, "QA 10 origen")
    saved = save(client, pid, base_network(client, demand=10.0))
    v = saved["version"]
    code, original = simulate(client, pid, v)
    assert code == 200

    exported = client.get(f"/api/projects/{pid}/export.inp", params={"version": v})
    assert exported.status_code == 200
    r = client.post("/api/projects/import", data={"crs": "auto"},
                    files={"file": ("qa10.inp", exported.content, "text/plain")})
    assert r.status_code == 201, r.text
    pid2, v2 = r.json()["project"]["id"], r.json()["version"]
    code, again = simulate(client, pid2, v2)
    assert code == 200

    a = _props(client.get(f"/api/projects/{pid}/network", params={"version": v}).json())
    b = _props(client.get(f"/api/projects/{pid2}/network", params={"version": v2}).json())
    assert set(a) == set(b) == {"E1", "J1", "P1"}
    assert b["P1"]["length_hydraulic_m"] == pytest.approx(a["P1"]["length_hydraulic_m"], abs=1e-6)
    assert b["P1"]["inner_diameter_mm"] == pytest.approx(a["P1"]["inner_diameter_mm"], abs=1e-6)
    assert b["P1"]["roughness"] == pytest.approx(a["P1"]["roughness"], abs=1e-9)
    for nid in ("E1", "J1"):
        assert b[nid]["elevation"] == pytest.approx(a[nid]["elevation"], abs=1e-6)
        assert b[nid]["elevation_source"] == "inp"
    for key in ("init_level", "min_level", "max_level", "tank_diameter", "min_volume"):
        assert b["E1"][key] == pytest.approx(a["E1"][key], abs=1e-6), key
    assert b["J1"]["base_demand"] == pytest.approx(a["J1"]["base_demand"], abs=1e-9)

    for var in VARS_NODE:
        ids = sorted(original["nodes"])
        row = QA.compare("10 · ida y vuelta .inp", var, np.array([[original["nodes"][i][var][0] for i in ids]]),
                         np.array([[again["nodes"][i][var][0] for i in ids]]))
        assert row.ok, row
    for var in VARS_LINK:
        ids = sorted(original["links"])
        scale = np.array([a[i]["length_hydraulic_m"] / 1000 for i in ids]) if var == "headloss" else 1.0
        row = QA.compare("10 · ida y vuelta .inp", var,
                         np.array([[original["links"][i][var][0] for i in ids]]) * scale,
                         np.array([[again["links"][i][var][0] for i in ids]]) * scale)
        assert row.ok, row
    assert {x["code"] for x in again["alerts"]} == {x["code"] for x in original["alerts"]}


# 11 ─ Versiones y corridas
def test_11_versiones_y_corridas_ligadas_a_la_version_correcta(client):
    pid = new_project(client, "QA 11 versiones")
    v_a = save(client, pid, base_network(client, demand=10.0, dn=90), label="DN 90")["version"]
    v_b = save(client, pid, base_network(client, demand=10.0, dn=160), label="DN 160")["version"]
    assert v_b == v_a + 1
    _, sim_a = simulate(client, pid, v_a)
    _, sim_b = simulate(client, pid, v_b)
    assert sim_a["model_version"] == v_a and sim_b["model_version"] == v_b
    assert sim_a["run_id"] != sim_b["run_id"]
    assert any(x["code"] == "BOTTLENECK" for x in sim_a["alerts"])
    assert not any(x["code"] == "BOTTLENECK" for x in sim_b["alerts"])

    # Recuperar la primera: su contenido no cambió y se restaura como versión nueva.
    doc_a = client.get(f"/api/projects/{pid}/network", params={"version": v_a}).json()
    assert _props(doc_a)["P1"]["dn"] == 90
    r = client.put(f"/api/projects/{pid}/network", json={"base_version": v_b, "kind": "manual",
                                                          "label": f"Restaurada desde v{v_a}",
                                                          "network": doc_a["network"]})
    assert r.status_code == 200 and r.json()["created"]
    v_c = r.json()["version"]
    _, sim_c = simulate(client, pid, v_c)
    assert sim_c["model_version"] == v_c and sim_c["run_id"] not in (sim_a["run_id"], sim_b["run_id"])
    assert sim_c["inp_sha256"] == sim_a["inp_sha256"]
    assert sim_c["nodes"]["J1"]["pressure"] == sim_a["nodes"]["J1"]["pressure"]

    # Las corridas guardadas quedan ligadas a su versión (base de datos y API).
    with get_sessionmaker()() as s:
        rows = s.execute(text("SELECT r.id, v.number FROM simulation_run r JOIN project_version v "
                              "ON v.id = r.version_id WHERE v.project_id = :p"), {"p": uuid.UUID(pid)}).all()
    linked = {str(rid): num for rid, num in rows}
    assert linked == {sim_a["run_id"]: v_a, sim_b["run_id"]: v_b, sim_c["run_id"]: v_c}
    for sim, v in ((sim_a, v_a), (sim_b, v_b), (sim_c, v_c)):
        got = client.get(f"/api/projects/{pid}/runs/{sim['run_id']}").json()
        assert got["model_version"] == v and got["nodes"]["J1"] == sim["nodes"]["J1"]
    # Re-simular una versión reutiliza su propia corrida.
    _, again_a = simulate(client, pid, v_a)
    assert again_a["cached"] and again_a["run_id"] == sim_a["run_id"]
    versions = {x["number"]: x for x in client.get(f"/api/projects/{pid}/versions").json()}
    assert versions[v_a]["has_results"] and versions[v_b]["has_results"] and versions[v_c]["has_results"]
    assert versions[1]["has_results"] is False
