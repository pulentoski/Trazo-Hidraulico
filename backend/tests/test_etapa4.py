"""Etapa 4: pozo y bombeo (BombaPozo1), registro de mediciones y diagnóstico automático."""
from datetime import datetime, timedelta, timezone

import pytest

from app.schemas.network import NetworkModel
from app.services.measurements import meter_flows
from app.services.well_pump import Conventions, calculate
from tests.analysis_net import network
from tests.helpers import fc, node, pipe
from tests.test_sig_excel import create_demo

DESIGN = {"pump_depth_m": 42, "design_flow_lps": 8, "arrival_elevation_m": 205, "minor_loss_pct": 5,
          "pump_efficiency": 0.9, "motor_efficiency": 0.9, "power_factor": 0.85, "voltage_v": 380,
          "column": {"material": "Acero", "dn": 100, "inner_diameter_mm": 100, "length_m": 42, "roughness": 140},
          "impulsion": {"material": "Acero", "dn": 100, "inner_diameter_mm": 100, "length_m": 120, "roughness": 140}}
LAT, X = -29.9, [-71.2 + 0.001 * k for k in range(4)]


def well_net():
    return fc(
        node("R-P", "reservoir", lon=X[0], lat=LAT, head=80.0),
        node("J1", lon=X[1], lat=LAT, elevation=100.0),
        node("E1", "tank", lon=X[2], lat=LAT, elevation=200.0, init_level=2, min_level=0.5, max_level=5, tank_diameter=6),
        {"type": "Feature", "id": "B1", "geometry": {"type": "LineString", "coordinates": [[X[0], LAT], [X[1], LAT]]},
         "properties": {"element": "link", "kind": "pump", "from_node": "R-P", "to_node": "J1", "pump_power": 15}},
        pipe("P1", "J1", "E1", [[X[1], LAT], [X[2], LAT]], length_choice="manual", length_hydraulic_m=120.0),
        {"type": "Feature", "id": "PZ", "geometry": {"type": "Point", "coordinates": [X[0], LAT]},
         "properties": {"element": "well", "node": "R-P", "ground_elevation": 100, "static_level_m": 7,
                        "dynamic_level_m": 25, "depth_m": 80, "authorized_flow_lps": 10, "pump_design": DESIGN}},
    )


def test_pozo_reproduce_bombapozo1_con_supuestos_de_la_planilla():
    m = NetworkModel.model_validate({"network": well_net()})
    well = m.network.wells()[0]
    c = calculate(well, m, Conventions.planilla(), "H-W")
    assert c.geometric_head_m == pytest.approx(130.0)
    assert c.segments[0].headloss_m == pytest.approx(0.47099, abs=1e-4)  # J16
    assert c.segments[1].headloss_m == pytest.approx(1.34569, abs=1e-4)  # L16
    assert c.segments[0].velocity_ms == pytest.approx(1.01911, abs=1e-4)  # J18 (π = 3,14)
    assert c.manometric_head_m == pytest.approx(138.4075, abs=1e-3)  # F26
    assert c.shaft_power_kw == pytest.approx(12.3029, abs=1e-3)  # J22
    assert c.shaft_power_hp == pytest.approx(12.3029 / 0.7457, abs=1e-3)
    assert c.current_a == pytest.approx(24.435, abs=0.01)  # N23 (trifásica)
    # Con γ = 9.810 N/m³, π exacto y H-W de EPANET la potencia es ~1,9 % menor.
    d = calculate(well, m)
    assert d.shaft_power_kw == pytest.approx(c.shaft_power_kw * 0.981, rel=0.01)
    assert any("10.000" in n for n in d.notes) and any("monofásica" in n for n in d.notes)
    assert d.curve_points[0][1] == pytest.approx(1.33 * d.manometric_head_m, abs=0.01)


def test_pozo_api_ficha_y_curva(client):
    pid = client.post("/api/projects", json={"name": "Pozo"}).json()["id"]
    r = client.put(f"/api/projects/{pid}/network", json={"base_version": 1, "kind": "manual", "network": well_net()})
    assert r.status_code == 200, r.text
    calc = client.get(f"/api/projects/{pid}/wells/PZ/pump", params={"conventions": "planilla"}).json()
    assert calc["manometric_head_m"] == pytest.approx(138.4075, abs=1e-3)
    html = client.get(f"/api/projects/{pid}/wells/PZ/report.html").text
    assert "Ficha del pozo PZ" in html and "Altura manométrica" in html and "trifásica" in html
    ap = client.post(f"/api/projects/{pid}/wells/PZ/apply-curve")
    assert ap.status_code == 200, ap.text
    assert ap.json()["pump"] == "B1" and ap.json()["reservoir_head"] == pytest.approx(75.0)
    doc = client.get(f"/api/projects/{pid}/network").json()
    b1 = next(f for f in doc["network"]["features"] if f["id"] == "B1")["properties"]
    assert len(b1["curve_points"]) == 3 and b1["pump_power"] is None
    sim = client.post(f"/api/projects/{pid}/simulate", json={"model_version": ap.json()["version"]})
    assert sim.status_code == 200
    assert 6 < sim.json()["links"]["B1"]["flow"][0] < 14  # cerca del punto de diseño (8 L/s)


# ── Mediciones ──

MINUTOS = [0, 6, 9, 10, 11, 12, 13, 14, 15, 15.5]
LECTURAS = [1373232.8, 1373238.8, 1373240.8, 1373241.8, 1373242.82, 1373243.83, 1373244.85, 1373245.86, 1373246.88,
            1373247.21]


def test_lecturas_de_bombapozo1_dan_15_49_lps():
    t0 = datetime(2026, 11, 9, 8, 0, tzinfo=timezone.utc)
    flows, avg = meter_flows([(t0 + timedelta(minutes=m), v) for m, v in zip(MINUTOS, LECTURAS)])
    assert avg == pytest.approx(15.4946, abs=1e-3)  # E76
    assert len(flows) == 9 and flows[0][1] == pytest.approx(6 * 1000 / 360)


def test_registro_importacion_y_comparacion(client):
    pid = create_demo(client, "APR mediciones")
    # La demostración trae lecturas de producción de octubre (hoja «Mediciones»): se parte de un registro vacío.
    ids = [m["id"] for m in client.get(f"/api/projects/{pid}/measurements").json()]
    assert len(ids) == 3322  # producción diaria de 12 meses (pozo y macromedidor), presión y nivel horarios
    client.post(f"/api/projects/{pid}/measurements/delete", json={"ids": ids})
    t0 = datetime(2026, 11, 9, 8, 0, tzinfo=timezone.utc)
    body = [{"element_type": "well", "element_id": "PZ-1", "kind": "meter", "value": v,
             "measured_at": (t0 + timedelta(minutes=m)).isoformat()} for m, v in zip(MINUTOS, LECTURAS)]
    r = client.post(f"/api/projects/{pid}/measurements", json=body)
    assert r.status_code == 201 and len(r.json()) == 10
    sim = client.post(f"/api/projects/{pid}/simulate", json={"model_version": 1}).json()
    p_model = sim["nodes"]["J-5"]["pressure"][8]
    csv = ("Elemento;ID;Medición;Fecha y hora;Valor;Nota\n"
           f"nudo;J-5;presión;2026-11-09 08:10;{p_model + 0.5:.2f};cerca\n".replace(".", ",", 0) +
           f"nudo;J-5;presión;2026-11-09 08:40;{p_model - 6:.2f};lejos\n"
           "estanque;E-1;nivel;2026-11-09 08:00;2,9;\n")
    imp = client.post(f"/api/projects/{pid}/measurements/import", files={"file": ("m.csv", csv.encode(), "text/csv")})
    assert imp.status_code == 200 and imp.json()["created"] == 3, imp.text
    bad = client.post(f"/api/projects/{pid}/measurements/import",
                      files={"file": ("m.csv", b"Elemento;ID;Medicion;Fecha y hora;Valor\nplaneta;X;presion;ayer;1\n", "text/csv")})
    assert bad.status_code == 422 and "Fila 2" in bad.json()["errors"][0]
    assert client.get(f"/api/projects/{pid}/measurements/template.xlsx").content[:2] == b"PK"
    client.put(f"/api/projects/{pid}/monitoring", json={"flow_pct": 10, "pressure_m": 2, "level_m": 0.3})
    cmp = client.get(f"/api/projects/{pid}/measurements/compare").json()
    s = {(x["element_id"], x["kind"]): x for x in cmp["series"]}
    meter = s[("PZ-1", "meter")]
    assert meter["average_measured"] == pytest.approx(15.4946, abs=1e-3) and meter["quantity"] == "caudal"
    assert all(p["model"] is not None for p in meter["points"])
    press = s[("J-5", "pressure")]
    assert [p["ok"] for p in press["points"]] == [True, False] and press["alert"] is True
    assert "difieren" in press["message"]
    level = s[("E-1", "level")]
    assert level["points"][0]["model"] == pytest.approx(sim["nodes"]["E-1"]["pressure"][8], abs=1e-3)


# ── Diagnóstico ──

def test_diagnostico_presion_baja_con_sugerencia_verificada(client):
    from tests.analysis_net import create

    pid, v = create(client, "Diagnóstico presión", network(client, elev=(36.0, 36.0, 36.0), dn1=63))
    d = client.get(f"/api/projects/{pid}/diagnosis").json()
    assert d["status"] == "no cumple"
    pres = next(i for i in d["items"] if i["section"] == "presion")
    assert pres["severity"] == "problem" and {"type": "link", "id": "P1"} in pres["refs"]
    assert "P1" in pres["text"] and pres["data"]["presion_m"] < 15
    sug = d["suggestions"][0]
    assert sug["kind"] == "upgrade_dn" and sug["verified"] is True and "P1" in sug["text"]
    # Aplicar la sugerencia efectivamente resuelve el problema.
    doc = client.get(f"/api/projects/{pid}/network").json()
    cat = client.get("/api/catalog/pipes").json()
    for ch in sug["action"]["links"]:
        f = next(x for x in doc["network"]["features"] if x["id"] == ch["link"])
        item = next(c for c in cat if c["material"] == f["properties"]["material"] and c["pipe_class"] == f["properties"]["pipe_class"]
                    and c["dn"] == ch["dn_to"])
        f["properties"].update(dn=item["dn"], inner_diameter_mm=item["inner_diameter_mm"], catalog_pipe_id=item["id"],
                               roughness=item["hw_c"])
    r = client.put(f"/api/projects/{pid}/network", json={"base_version": v, "kind": "manual", "network": doc["network"]})
    d2 = client.get(f"/api/projects/{pid}/diagnosis").json()
    assert d2["status"] != "no cumple", d2["items"]


def test_diagnostico_e_informe_de_la_demo(client):
    pid = create_demo(client, "APR diagnóstico")
    d = client.get(f"/api/projects/{pid}/diagnosis").json()
    assert d["summary"]["text"] and "hora punta" in d["summary"]["text"]
    tank = next(i for i in d["items"] if i["section"] == "estanque")
    assert "E-1" in tank["text"] and tank["refs"] == [{"type": "node", "id": "E-1"}]
    assert any(i["section"] == "bomba" and "B-1" in i["text"] for i in d["items"])
    assert all(s["verified"] for s in d["suggestions"])
    html = client.get(f"/api/projects/{pid}/report.html").text
    assert "Informe técnico" in html and "Diagnóstico" in html and "<svg" in html and "Criterios de diseño" in html
