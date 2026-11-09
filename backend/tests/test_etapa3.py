"""Etapa 3: operación de bombas, alertas de período extendido, proyección de demanda, formato .trazo e
importación .inp con [VERTICES], [LABELS] y [TAGS]."""
import io
import json
import zipfile

import pytest
from openpyxl import load_workbook

from app.hydraulic.inp_writer import write_inp
from app.schemas.network import NetworkModel
from app.validators.network_validator import validate_model
from tests.helpers import fc, node, pipe
from tests.test_sig_excel import create_demo

LAT = -29.9
X = [-71.2 + 0.001 * k for k in range(4)]


def pump_net(*, schedule=None, level_control=None, curve=((10.0, 60.0),), tank_max=4.0):
    return fc(
        node("R1", "reservoir", lon=X[0], lat=LAT, head=100.0),
        node("J1", lon=X[1], lat=LAT, elevation=100.0),
        node("E1", "tank", lon=X[2], lat=LAT, elevation=140.0, init_level=2.0, min_level=0.5, max_level=tank_max,
             tank_diameter=8.0, min_volume=0.0),
        node("J2", lon=X[3], lat=LAT, elevation=110.0, base_demand=3.0),
        {"type": "Feature", "id": "B1", "geometry": {"type": "LineString", "coordinates": [[X[0], LAT], [X[1], LAT]]},
         "properties": {"element": "link", "kind": "pump", "from_node": "R1", "to_node": "J1",
                        "curve_points": [list(p) for p in curve] if curve else None, "schedule": schedule,
                        "level_control": level_control}},
        pipe("P1", "J1", "E1", [[X[1], LAT], [X[2], LAT]], length_choice="manual", length_hydraulic_m=200.0),
        pipe("P2", "E1", "J2", [[X[2], LAT], [X[3], LAT]], length_choice="manual", length_hydraulic_m=200.0),
    )


def model_of(net, **opts) -> NetworkModel:
    return NetworkModel.model_validate({"network": net, "options": {"duration_h": 24, **opts}})


# ── Operación en el .inp ──

def test_curva_por_puntos_horario_nivel_y_reglas():
    sched = [0] * 6 + [1] * 12 + [0] * 6
    inp = write_inp(model_of(pump_net(schedule=sched)))
    assert " CB_B1\t10\t60" in inp and "B1\tR1\tJ1\tHEAD\tCB_B1" in inp
    assert " B1\tClosed" in inp.split("[STATUS]")[1].split("[")[0]
    assert " LINK B1 OPEN AT CLOCKTIME 6:00" in inp and " LINK B1 CLOSED AT CLOCKTIME 18:00" in inp
    lc = {"tank": "E1", "on_below": 1.5, "off_above": 3.5}
    inp = write_inp(model_of(pump_net(level_control=lc)))
    assert " LINK B1 OPEN IF NODE E1 BELOW 1.5" in inp and " LINK B1 CLOSED IF NODE E1 ABOVE 3.5" in inp
    inp = write_inp(model_of(pump_net(schedule=sched, level_control=lc)))
    rules = inp.split("[RULES]")[1].split("\n[")[0]
    assert "IF TANK E1 LEVEL BELOW 1.5" in rules and "THEN PUMP B1 STATUS IS CLOSED" in rules
    assert "IF SYSTEM CLOCKTIME >= 18:00" in rules


def test_validacion_de_curva_y_control():
    bad = validate_model(model_of(pump_net(curve=((5, 60), (10, 50)))))
    assert any(e.code == "E_PUMP_CURVE" for e in bad.errors)
    bad = validate_model(model_of(pump_net(curve=((5, 60), (10, 65), (15, 40)))))
    assert any(e.code == "E_PUMP_CURVE" for e in bad.errors)
    bad = validate_model(model_of(pump_net(level_control={"tank": "J2", "on_below": 1, "off_above": 2})))
    assert any(e.code == "E_OPERATION" for e in bad.errors)
    bad = validate_model(model_of(pump_net(level_control={"tank": "E1", "on_below": 3, "off_above": 2})))
    assert any(e.code == "E_OPERATION" for e in bad.errors)
    m = model_of(pump_net())
    m.aux["patterns"] = " MOD\t0.5\t1.5\t0.9"
    assert any(w.code == "W_PATTERN_MEAN" for w in validate_model(m).warnings)


def _simulate(client, name, net, **opts):
    pid = client.post("/api/projects", json={"name": name}).json()["id"]
    r = client.put(f"/api/projects/{pid}/network", json={"base_version": 1, "kind": "manual", "network": net,
                                                         "options": {"duration_h": 24, **opts}})
    assert r.status_code == 200, r.text
    sim = client.post(f"/api/projects/{pid}/simulate", json={"model_version": r.json()["version"]})
    assert sim.status_code == 200, sim.text
    return pid, sim.json()


def test_control_por_nivel_mantiene_el_estanque_entre_niveles(client):
    _, sim = _simulate(client, "Control por nivel", pump_net(curve=((0, 80), (15, 60), (25, 30)),
                                                             level_control={"tank": "E1", "on_below": 1.5,
                                                                            "off_above": 3.0}),
                       hydraulic_step_min=5)
    level = sim["nodes"]["E1"]["pressure"]
    assert max(level) <= 3.0 + 0.3 and min(level) >= 1.5 - 0.3
    q = sim["links"]["B1"]["flow"]
    assert any(v > 1 for v in q) and any(abs(v) < 1e-6 for v in q), "la bomba se enciende y se apaga"


def test_alertas_bomba_fuera_de_curva_y_estanque_vacio(client):
    _, sim = _simulate(client, "Bomba débil", pump_net(curve=((0, 30), (5, 25), (10, 10))))
    codes = {a["code"] for a in sim["alerts"]}
    assert "PUMP_OFF_CURVE" in codes and "TANK_EMPTY" in codes


# ── Proyección de demanda (planilla Proyecc10-30HospChamp) ──

PLANILLA = {  # año: (población, QMD, QMH, bombeo, regulación 15 %)
    2016: (2000.0, 6.7751, 10.1626, 13.5501, 87.8049),
    2017: (2100.0, 7.1138, 10.6707, 14.2276, 92.1951),
    2026: (3257.7893, 11.0359, 16.5538, 22.0717, 143.0249),
    2033: (4163.7794, 14.1049, 21.1574, 28.2099, 182.8001),
}


def test_proyeccion_reproduce_la_planilla(client):
    pid = client.post("/api/projects", json={"name": "Proyección"}).json()["id"]
    d = client.get(f"/api/projects/{pid}/demand/projection").json()
    assert d["verified"] is False and not d["customized"] and "no verificado" in d["note"]
    inputs = {**d["inputs"], "base_year": 2016, "model_year": 2016, "current_year": 2026, "base_mode": "arranques",
              "base_connections": 400, "persons_per_dwelling": 5, "growth": [{"from_year": 2017, "rate_pct": 5},
                                                                             {"from_year": 2029, "rate_pct": 3}],
              "horizon_years": 17, "dotation_lphd": 160, "losses_pct": 18, "coef_day": 1.5, "coef_hour": 1.5,
              "pump_hours": 12, "regulation_pct": 15}
    r = client.put(f"/api/projects/{pid}/demand/projection", json=inputs)
    assert r.status_code == 200, r.text
    rows = {x["year"]: x for x in r.json()["rows"]}
    assert len(rows) == 18
    for year, (pop, qmd, qmh, qb, reg) in PLANILLA.items():
        x = rows[year]
        assert x["population"] == pytest.approx(pop, abs=1e-3)
        assert x["qmd_lps"] == pytest.approx(qmd, abs=1e-3) and x["qmh_lps"] == pytest.approx(qmh, abs=1e-3)
        assert x["pump_lps"] == pytest.approx(qb, abs=1e-3) and x["regulation_m3"] == pytest.approx(reg, abs=1e-3)
    assert rows[2016]["clients"] == pytest.approx(400) and rows[2016]["consumption_m3"] == pytest.approx(117120)
    sc = {s["id"]: s for s in r.json()["scenarios"]}
    assert sc["base"]["multiplier"] == 1 and sc["horizonte"]["multiplier"] == pytest.approx(4163.7794 / 2000, abs=1e-4)
    assert sc["actual"]["multiplier"] == pytest.approx(3257.7893 / 2000, abs=1e-4)
    x = client.get(f"/api/projects/{pid}/demand/projection.xlsx")
    ws = load_workbook(io.BytesIO(x.content)).active
    assert any(row[0] == 2033 for row in ws.iter_rows(values_only=True))


def test_escenario_de_demanda_escala_nudos_y_clientes(client):
    pid = create_demo(client, "APR escenario de demanda")
    base = client.post(f"/api/projects/{pid}/simulate", json={"model_version": 1}).json()
    client.put(f"/api/projects/{pid}/demand/projection",
               json={**client.get(f"/api/projects/{pid}/demand/projection").json()["inputs"],
                     "growth": [{"from_year": 2000, "rate_pct": 2}], "horizon_years": 20})
    r = client.post(f"/api/projects/{pid}/demand/scenario", json={"scenario": "horizonte"})
    assert r.status_code == 200
    mult = r.json()["multiplier"]
    assert mult == pytest.approx(1.02 ** 20, rel=1e-6)
    assert f"DEMAND MULTIPLIER\t{mult:.12g}" in client.get(f"/api/projects/{pid}/export.inp").text
    sim = client.post(f"/api/projects/{pid}/simulate", json={"model_version": r.json()["version"]}).json()
    j = "J-3"  # tiene clientes
    assert sim["nodes"][j]["demand"][0] == pytest.approx(base["nodes"][j]["demand"][0] * mult, rel=1e-3)


# ── Formato .trazo ──

def _trazo_doc(content: bytes) -> tuple[dict, str]:
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        return json.loads(z.read("trazo.json")), z.read("modelo.inp").decode("latin-1")


def test_trazo_ida_y_vuelta_sin_perdida(client):
    pid = create_demo(client, "APR trazo")
    client.post(f"/api/projects/{pid}/queries", json={"name": "Ruta 3", "definition": {
        "element": "clientes", "where": {"logic": "and", "conditions": [{"field": "route", "op": "eq", "value": "3"}]}}})
    client.put(f"/api/projects/{pid}/design-params", json=[{"key": "dotacion", "value": 170}])
    proj = client.get(f"/api/projects/{pid}/demand/projection").json()["inputs"]
    client.put(f"/api/projects/{pid}/demand/projection", json={**proj, "horizon_years": 25})
    a = client.get(f"/api/projects/{pid}/export.trazo")
    assert a.status_code == 200 and a.headers["content-type"] == "application/zip"
    doc_a, inp_a = _trazo_doc(a.content)
    assert doc_a["format"] == "trazo" and doc_a["format_version"] == 1
    assert len(doc_a["sectors"]) == 4 and doc_a["saved_queries"][0]["name"] == "Ruta 3"
    r = client.post("/api/projects/import-trazo", files={"file": ("apr.trazo", a.content, "application/zip")})
    assert r.status_code == 201, r.text
    pid2 = r.json()["project"]["id"]
    b = client.get(f"/api/projects/{pid2}/export.trazo")
    doc_b, inp_b = _trazo_doc(b.content)
    for key in ("model", "saved_queries", "sectors"):
        assert doc_a[key] == doc_b[key], key
    for key in ("name", "description", "length_srid", "design_profile", "design_params", "demand_projection"):
        assert doc_a["project"][key] == doc_b["project"][key], key
    assert inp_a == inp_b
    net_b = client.get(f"/api/projects/{pid2}/network").json()["network"]["features"]
    c = next(f for f in net_b if f["id"] == "C-001")["properties"]
    assert c["attributes"] == {"Sector social": "A"} and c["meter_number"] == "MED-2401"


def test_trazo_invalido_se_rechaza(client):
    r = client.post("/api/projects/import-trazo", files={"file": ("x.trazo", b"no es zip", "application/zip")})
    assert r.status_code == 422


# ── Importación .inp con vértices, rótulos y etiquetas ──

def test_inp_latlon_con_vertices_rotulos_y_etiquetas(client, networks_dir):
    with open(networks_dir / "etiquetas-latlon.inp", "rb") as fh:
        r = client.post("/api/projects/import", files={"file": ("etiquetas-latlon.inp", fh, "text/plain")})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["georeference"] == "EPSG:4326"
    assert any("etiquetas [TAGS]" in n for n in body["notes"])
    pid = body["project"]["id"]
    doc = client.get(f"/api/projects/{pid}/network").json()
    feats = {f["id"]: f for f in doc["network"]["features"]}
    assert feats["J1"]["properties"]["attributes"]["__tag"] == "Sector_Norte"
    assert feats["P2"]["properties"]["attributes"]["__tag"] == "Matriz_2015"
    assert len(feats["P4"]["geometry"]["coordinates"]) == 4  # 2 vértices
    assert feats["P2"]["geometry"]["coordinates"][1][0] == pytest.approx(-71.140335, abs=1e-6)
    # El largo en planta calculado coincide con el del archivo (coordenadas geográficas bien leídas).
    assert feats["P2"]["properties"]["length_plan_m"] == pytest.approx(330.3, rel=0.01)
    assert "Sector Norte" in doc["aux"]["labels"]
    inp = client.get(f"/api/projects/{pid}/export.inp").text
    assert "[TAGS]" in inp and " NODE\tJ1\tSector_Norte" in inp and " LINK\tP2\tMatriz_2015" in inp
    labels = inp.split("[LABELS]")[1].split("[")[0]
    assert '"Sector Norte"' in labels and "J1" in labels
    assert len(inp.split("[VERTICES]")[1].split("[")[0].strip().splitlines()) == 4  # P2, P3 y dos de P4


# ── Demo «APR Demo» en 24 h ──

def test_demo_simula_24_h_con_bomba_horaria_y_variacion_de_nivel(client):
    pid = create_demo(client, "APR Demo 24 h")
    doc = client.get(f"/api/projects/{pid}/network").json()
    assert doc["options"]["duration_h"] == 24 and doc["options"]["extra"]["PATTERN"] == "MOD"
    b1 = next(f for f in doc["network"]["features"] if f["id"] == "B-1")["properties"]
    assert len(b1["curve_points"]) == 3 and sum(b1["schedule"]) == 14
    sim = client.post(f"/api/projects/{pid}/simulate", json={"model_version": 1}).json()
    assert sim["status"] in ("ok", "warning") and not [m for m in sim["messages"] if m["severity"] == "error"]
    assert len(sim["times"]) == 25
    level = sim["nodes"]["E-1"]["pressure"]
    assert max(level) - min(level) > 1.5, "el nivel del estanque varía en el día"
    q = sim["links"]["B-1"]["flow"]
    assert q[3] == pytest.approx(0, abs=1e-6) and q[10] > 8
    # La planilla exportada conserva la operación de la bomba (ida y vuelta sin cambios).
    exp = client.get(f"/api/projects/{pid}/sig/export.xlsx").content
    p = client.post(f"/api/projects/{pid}/sig/import/preview",
                    files={"file": ("e.xlsx", exp, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}).json()
    assert p["ok"] and p["modified"] == [] and p["new"] == []
