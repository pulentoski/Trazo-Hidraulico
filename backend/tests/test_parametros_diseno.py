"""Parámetros de diseño editables por proyecto, con valores por defecto «no verificado»."""
import pytest

from tests.analysis_net import create, network


def test_valores_por_defecto_no_verificados(client):
    pid = client.post("/api/projects", json={"name": "Parámetros"}).json()["id"]
    r = client.get(f"/api/projects/{pid}/design-params").json()
    params = {p["key"]: p for p in r["params"]}
    assert not r["customized"]
    assert params["pressure_min"]["value"] == 15 and params["pressure_min"]["bound"] == "min"
    assert params["dotacion"]["value"] == 150 and params["perdidas"]["value"] == 20
    assert len(params["curva_modulacion"]["value"]) == 24
    assert all(p["verified"] is False for p in r["params"])


def test_editar_presion_minima_cambia_alertas_y_factibilidad(client):
    pid, v = create(client, "Parámetros editados", network(client))
    sim = client.post(f"/api/projects/{pid}/simulate", json={"model_version": v}).json()
    assert not [a for a in sim["alerts"] if a["code"] == "PRESSURE_LOW"]
    r = client.put(f"/api/projects/{pid}/design-params", json=[{"key": "pressure_min", "value": 25.0}])
    assert r.status_code == 200
    p = next(x for x in r.json()["params"] if x["key"] == "pressure_min")
    assert p["value"] == 25 and p["source"] == "Ingresado en el proyecto" and p["verified"] is False
    assert r.json()["customized"]
    sim = client.post(f"/api/projects/{pid}/simulate", json={"model_version": v}).json()
    assert {a["element_id"] for a in sim["alerts"] if a["code"] == "PRESSURE_LOW"} == {"J1", "J2", "J3"}
    body = {"model_version": v, "link": "P2", "point": [-70.6462, -33.45], "consumption_lps": 0.5, "elevation": 30}
    res = client.post(f"/api/projects/{pid}/feasibility", json=body).json()
    assert not res["feasible"] and next(c for c in res["criteria"] if c["key"] == "pressure_min")["value"] == 25


def test_parametro_desconocido_o_tipo_invalido(client):
    pid = client.post("/api/projects", json={"name": "Parámetros inválidos"}).json()["id"]
    assert client.put(f"/api/projects/{pid}/design-params", json=[{"key": "nada", "value": 1}]).status_code == 422
    r = client.put(f"/api/projects/{pid}/design-params", json=[{"key": "curva_modulacion", "value": [1, 2]}])
    assert r.status_code == 422 and "24" in r.json()["detail"]
    ok = client.put(f"/api/projects/{pid}/design-params", json=[{"key": "dotacion", "value": 160, "verified": True,
                                                                  "source": "Estudio de demanda 2026"}]).json()
    d = next(x for x in ok["params"] if x["key"] == "dotacion")
    assert d["value"] == pytest.approx(160) and d["verified"] and d["source"] == "Estudio de demanda 2026"
