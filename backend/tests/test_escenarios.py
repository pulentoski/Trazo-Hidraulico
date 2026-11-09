"""Escenarios de llaves: una llave cerrada aísla un sector y sus clientes quedan sin suministro."""
import pytest

from tests.analysis_net import create, network, shutoff_feature


@pytest.fixture(scope="module")
def project(client):
    net = network(client, extra=(shutoff_feature("LL1", "P2", 0.3, name="Llave calle norte"),
                                 shutoff_feature("LL2", "P1", 0.9)))
    scenarios = [{"id": "corte-norte", "name": "Corte sector norte", "closed": ["LL1"]}]
    return create(client, "Escenarios", net, scenarios=scenarios)


def _sim(client, pid, v, scenario):
    r = client.post(f"/api/projects/{pid}/scenarios/simulate", json={"model_version": v, "scenario": scenario})
    assert r.status_code == 200, r.text
    return r.json()


def test_llave_ubicada_sobre_su_tuberia_y_escenario_guardado(client, project):
    pid, v = project
    doc = client.get(f"/api/projects/{pid}/network", params={"version": v}).json()
    ll1 = next(f for f in doc["network"]["features"] if f["id"] == "LL1")
    p2 = next(f for f in doc["network"]["features"] if f["id"] == "P2")
    (x0, y0), (x1, y1) = p2["geometry"]["coordinates"]
    assert ll1["geometry"]["coordinates"][0] == pytest.approx(x0 + 0.3 * (x1 - x0), abs=1e-6)
    assert ll1["geometry"]["coordinates"][1] == pytest.approx(y0, abs=1e-6)
    assert doc["scenarios"][0]["name"] == "Corte sector norte"


def test_operacion_normal_abastece_a_todos(client, project):
    pid, v = project
    r = _sim(client, pid, v, "normal")
    assert r["unsupplied_nodes"] == [] and r["summary"]["afectados"] == 0
    assert all(c["supplied"] and c["pressure"] > 15 for c in r["clients"])


def test_corte_sector_norte_deja_sin_suministro_a_los_clientes_aguas_abajo(client, project):
    pid, v = project
    r = _sim(client, pid, v, "corte-norte")
    assert r["scenario_name"] == "Corte sector norte" and r["closed_links"] == ["P2"]
    assert r["unsupplied_nodes"] == ["J2", "J3"] and r["unsupplied_links"] == ["P3"]
    by_id = {c["id"]: c for c in r["clients"]}
    assert not by_id["C2"]["supplied"] and not by_id["C3"]["supplied"]
    assert by_id["C2"]["pressure"] is None and by_id["C2"]["affected"]
    assert by_id["C1"]["supplied"] and by_id["C1"]["pressure"] > 15 and not by_id["C1"]["affected"]
    assert r["summary"]["clientes_sin_suministro"] == 2
    assert r["summary"]["consumo_sin_suministro_lps"] == pytest.approx(1.5)
    # Sin presiones absurdas: el motor resolvió solo el sector abastecido.
    assert not [m for m in r["messages"] if m["code"] in ("NEGATIVE_PRESSURE", "DISCONNECTED_NODE")]


def test_todas_cerradas_deja_toda_la_red_sin_suministro(client, project):
    pid, v = project
    r = _sim(client, pid, v, "todas_cerradas")
    assert r["unsupplied_nodes"] == ["J1", "J2", "J3"] and r["summary"]["clientes_sin_suministro"] == 3


def test_comparacion_normal_contra_corte(client, project):
    pid, v = project
    r = client.post(f"/api/projects/{pid}/scenarios/compare", json={"model_version": v, "a": "normal", "b": "corte-norte"})
    assert r.status_code == 200
    rows = {(x["kind"], x["id"]): x for x in r.json()["rows"]}
    j1 = rows[("nudo", "J1")]
    assert j1["diff"] > 0  # menos caudal por P1 → menos pérdida → más presión en J1
    assert j1["b"] == pytest.approx(j1["a"] + j1["diff"], abs=1e-3)
    c2 = rows[("cliente", "C2")]
    assert c2["supplied_a"] and not c2["supplied_b"] and c2["b"] is None and c2["diff"] is None


def test_llave_cerrada_en_el_modelo_cierra_la_tuberia_en_el_inp(client):
    net = network(client, extra=(shutoff_feature("LL1", "P2", 0.5, state="closed"),))
    pid, v = create(client, "Llave cerrada", net)
    r = _sim(client, pid, v, "actual")
    assert r["closed_links"] == ["P2"] and r["unsupplied_nodes"] == ["J2", "J3"]
    assert _sim(client, pid, v, "normal")["unsupplied_nodes"] == []


def test_escenario_inexistente_404(client, project):
    pid, v = project
    r = client.post(f"/api/projects/{pid}/scenarios/simulate", json={"model_version": v, "scenario": "no-existe"})
    assert r.status_code == 404
