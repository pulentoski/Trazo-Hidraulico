"""Panel general del proyecto («Resumen»): cálculos con resultados conocidos (clientes sobre cota, zonas por
presión, área operacional, agua no contabilizada, vencimientos) y el resumen completo de «APR Demo»."""
import io
import math
from datetime import datetime, timedelta

import pytest
from openpyxl import Workbook, load_workbook
from shapely.geometry import box

from app.services import summary_calc as calc
from tests.test_sig_excel import XLSX, create_demo

# ── Clientes sobre cota ──


def test_clientes_sobre_cota_deficit_conocido():
    clients = [calc.ClientHead("A", ground=100.0, head=120.0),  # 100 + 15 − 120 = −5: cumple
               calc.ClientHead("B", ground=110.0, head=120.0),  # déficit 5 m
               calc.ClientHead("C", ground=108.0, head=120.0),  # déficit 3 m
               calc.ClientHead("D", ground=105.0, head=120.0)]  # 0: justo en el límite, cumple
    assert calc.over_elevation(clients, pmin=15.0) == [("B", 5.0), ("C", 3.0)]
    assert calc.over_elevation(clients, pmin=10.0) == []


# ── Zonas por presión ──


def test_rangos_de_presion():
    assert [x[0] for x in calc.range_labels([15, 30, 50, 70])] == ["< 15", "15–30", "30–50", "50–70", "> 70"]
    assert [calc.range_of(p, [15, 30, 50, 70]) for p in (-2, 14.99, 15, 29.9, 30, 50, 70, 120)] == [0, 0, 1, 1, 2, 3, 4, 4]


def test_zonas_por_presion_voronoi_recortado():
    area = box(0, 0, 100, 100)  # 0,01 km²
    zones = calc.pressure_zones([("N1", 25, 50, 10.0), ("N2", 75, 50, 40.0)], area, [15, 30, 50, 70])
    by = {z.node: z for z in zones}
    assert by["N1"].cls == 0 and by["N2"].cls == 2
    assert by["N1"].cell.area == pytest.approx(5000) and by["N2"].cell.area == pytest.approx(5000)
    assert by["N1"].cell.bounds == pytest.approx((0, 0, 50, 100))
    km2, nodes, clients = calc.zone_totals(zones, [("c1", 10, 10), ("c2", 90, 90), ("c3", 60, 20), ("fuera", 500, 500)], 5)
    assert km2 == pytest.approx([0.005, 0, 0.005, 0, 0])
    assert nodes[0] == ["N1"] and nodes[2] == ["N2"]
    assert clients[0] == ["c1"] and sorted(clients[2]) == ["c2", "c3"]
    # Un solo nudo: su zona es toda el área; nudos repetidos en el mismo punto no rompen el diagrama.
    one = calc.pressure_zones([("N1", 50, 50, 20.0), ("N1b", 50, 50, 21.0)], area, [15, 30])
    assert len(one) == 1 and one[0].cell.area == pytest.approx(10000) and one[0].cls == 1


# ── Área operacional ──


def test_area_operacional_con_margen():
    n = 8 * 4  # polígono de 32 lados del buffer (quad_segs = 8)
    circle = 0.5 * n * 50 ** 2 * math.sin(2 * math.pi / n)
    a = calc.operational_area([], [(0, 0)], 50)
    assert a.area == pytest.approx(circle, rel=1e-9)
    b = calc.operational_area([[(0, 0), (1000, 0)]], [(500, 0)], 50)  # el punto queda dentro del buffer del tramo
    assert b.area == pytest.approx(1000 * 100 + circle, rel=1e-9)
    c = calc.operational_area([[(0, 0), (1000, 0)]], [(500, 500)], 50)  # cliente aislado: suma su círculo
    assert c.area == pytest.approx(1000 * 100 + 2 * circle, rel=1e-9)


# ── Agua no contabilizada ──


def test_agua_no_contabilizada():
    t0 = datetime(2026, 10, 1, 8)
    prod = calc.meter_production([(t0 + timedelta(days=d), 1000 + 30 * d) for d in (3, 0, 1, 2)])
    assert prod is not None and prod[0] == pytest.approx(30.0) and prod[1] == t0
    assert calc.nrw_pct(30.0, 22.5) == 25.0
    assert calc.nrw_pct(0.0, 5.0) is None
    assert calc.meter_production([(t0, 5.0)]) is None
    assert calc.meter_production([(t0, 5.0), (t0 + timedelta(days=1), 4.0)]) is None  # medidor reiniciado


# ── Vencimientos y plan de renovación ──


def test_vencimientos_y_plan():
    life = {"PVC": 50, "AC": 40, "HA": 50}
    pipes = [calc.PipeAge("A", "PVC", 110, 1000.0, 2000),  # vence 2050
             calc.PipeAge("B", "AC", 75, 500.0, 1990),  # vence 2030
             calc.PipeAge("C", "HA", 200, 250.0, 1970),  # venció 2020
             calc.PipeAge("D", "PVC", 63, 100.0, None),  # sin año
             calc.PipeAge("E", "FFD", 160, 300.0, 1986)]  # sin vida propia: 60 por defecto → 2046
    assert calc.expiry_year(pipes[4], life, 60) == 2046
    assert calc.expired(pipes, life, 60, 2026) == (0.25, ["C"])
    assert calc.due_within(pipes, life, 60, 2026, 5) == (0.5, ["B"])
    assert calc.due_within(pipes, life, 60, 2026, 10) == (0.5, ["B"])
    assert calc.due_within(pipes, life, 60, 2026, 20) == (0.8, ["B", "E"])
    assert calc.due_within(pipes, life, 60, 2026, 30) == (1.8, ["A", "B", "E"])
    prices = [("*", 75, 40000.0), ("*", 200, 80000.0), ("AC", 110, 55000.0)]
    assert calc.price_for("AC", 75, prices) == 55000.0  # fila propia del material
    assert calc.price_for("PVC", 63, prices) == 40000.0
    assert calc.price_for("HA", 250, prices) is None
    plan = calc.renewal_plan(pipes, life, 60, 2026, 20, prices)
    assert plan == [(2026, 0.25, 250 * 80000, ["C"]), (2030, 0.5, 500 * 55000, ["B"]), (2046, 0.3, 300 * 80000, ["E"])]


# ── Resumen completo de la demostración ──


@pytest.fixture(scope="module")
def demo(client):
    return create_demo(client, "APR Resumen")


def test_resumen_demo(client, demo):
    r = client.get(f"/api/projects/{demo}/summary")
    assert r.status_code == 200, r.text
    s = r.json()
    assert s["simulated"] and s["scenario"] == "modelo" and len(s["times"]) == 25
    assert s["period"] == s["peak_period"]  # por defecto, la hora punta
    c = s["clients"]
    assert (c["total"]["count"], c["active"]["count"], c["projected"]["count"], c["suspended"]["count"]) == (30, 27, 2, 1)
    assert {g["key"]: g["count"] for g in c["by_sector"]} == {"Bajo": 26, "Alto": 4}
    assert {g["key"]: g["count"] for g in c["by_route"]} == {"1": 9, "2": 11, "3": 10}
    n = s["network"]
    assert n["pipes"]["count"] == 15 and n["valves"]["count"] == 4 and n["hydrants"]["count"] == 1
    assert n["tanks"]["ids"] == ["E-1"] and n["wells"]["ids"] == ["PZ-1"]
    assert sum(g["km"] for g in n["by_material"]) == pytest.approx(n["km_total"], abs=1e-3)
    assert s["clients_per_pipe"][0]["clients"] == 3
    # Presiones y clientes sobre cota (C-025 está en la loma, cota 257 m)
    p = s["pressures"]
    assert p["min"]["value"] <= p["avg"] <= p["max"]["value"]
    assert "C-025" in p["clients_below"]["ids"] and p["critical_node"] is not None
    over = s["over_elevation"]
    assert [o["client"] for o in over] == ["C-025"]
    o = over[0]
    assert o["deficit"] == pytest.approx(o["ground"] + o["pmin"] - o["head"], abs=1e-3) and o["deficit"] > 0
    # Las zonas cubren toda el área operacional y reparten a los clientes no proyectados
    z = s["zones"]
    assert sum(r["area_km2"] for r in z["ranges"]) == pytest.approx(s["area"]["area_km2"], abs=1e-5)
    assert sum(r["clients"]["count"] for r in z["ranges"]) == 28
    assert s["area"]["geometry"]["type"] in ("Polygon", "MultiPolygon") and s["area"]["area_km2"] > 0.1
    # Consumo y mayores consumidores
    cs = s["consumption"]
    assert cs["m3_day"] == pytest.approx(cs["lps"] * 86.4, abs=1e-2) and cs["m3_month"] == pytest.approx(cs["m3_day"] * 30, abs=0.1)
    assert [x["years"] for x in cs["projection"]] == [10, 20] and cs["projection"][1]["m3_day"] > cs["m3_day"]
    assert s["top_consumers"][0]["client"] == "C-017" and len(s["top_consumers"]) == 10
    # Pérdidas: eventos de la planilla y agua no contabilizada
    lo = s["losses"]
    assert lo["total_events"] == 8 and lo["top_links"][0]["link"] == "P-06" and lo["top_links"][0]["events"] == 4
    bal = {b["sector"]: b for b in lo["balance"]}
    assert set(bal) == {"Total", "Alto"}
    assert bal["Total"]["nrw_pct"] == pytest.approx(
        (bal["Total"]["production_m3_day"] - bal["Total"]["consumption_m3_day"]) / bal["Total"]["production_m3_day"] * 100,
        abs=0.01)
    assert bal["Alto"]["clients"]["count"] == 4
    # Mantenimiento: P-08 (1972, PVC 50 años) vencido; P-13 (1979) vence en 5 años
    m = s["maintenance"]
    assert m["expired"]["ids"] == ["P-08"] and "P-13" in m["due"][0]["ids"]
    assert sorted(m["bad_condition"]["ids"]) == ["P-06", "P-08", "P-13"]
    assert m["plan"][0]["year"] == m["current_year"] and m["plan_cost"] == sum(x["cost"] for x in m["plan"])
    # Estanque y pozo
    tw = s["tank_well"]
    assert tw["tanks"][0]["autonomy_h"] > 0
    w = tw["wells"][0]
    assert w["pump"] == "B-1" and w["pump_hours_day"] == pytest.approx(14.0)
    alerts = {(a["type"], a["id"]) for a in s["alerts"]}
    assert ("client", "C-025") in alerts and ("link", "P-08") in alerts


def test_resumen_escenario_hora_y_errores(client, demo):
    s = client.get(f"/api/projects/{demo}/summary", params={"scenario": "normal", "period": 3}).json()
    assert s["scenario"] == "normal" and s["period"] == 3
    assert client.get(f"/api/projects/{demo}/summary", params={"scenario": "no-existe"}).status_code == 404
    assert client.get(f"/api/projects/{demo}/summary", params={"period": 99}).status_code == 404


def test_resumen_configuracion(client, demo):
    st = client.get(f"/api/projects/{demo}/summary/settings").json()
    assert st["pressure_ranges"] == [15, 30, 50, 70] and st["area_margin_m"] == 50 and not st["life_verified"]
    assert client.put(f"/api/projects/{demo}/summary/settings", json={**st, "pressure_ranges": [30, 15]}).status_code == 422
    base = client.get(f"/api/projects/{demo}/summary").json()["area"]["area_km2"]
    st2 = {**st, "area_margin_m": 100, "pressure_ranges": [20, 40], "service_life": {**st["service_life"], "PVC": 60}}
    assert client.put(f"/api/projects/{demo}/summary/settings", json=st2).status_code == 200
    s = client.get(f"/api/projects/{demo}/summary").json()
    assert s["area"]["area_km2"] > base and [r["label"] for r in s["zones"]["ranges"]] == ["< 20", "20–40", "> 40"]
    assert "P-08" not in s["maintenance"]["expired"]["ids"]  # 1972 + 60 = 2032
    assert client.delete(f"/api/projects/{demo}/summary/settings").json()["area_margin_m"] == 50


def test_registro_de_perdidas(client, demo):
    before = len(client.get(f"/api/projects/{demo}/leaks").json())
    r = client.post(f"/api/projects/{demo}/leaks", json=[{"link_id": "P-10", "event_date": "2026-11-01", "kind": "fuga",
                                                          "flow_lps": 0.02, "note": "manual"}])
    assert r.status_code == 201, r.text
    new_id = r.json()[0]["id"]
    assert client.post(f"/api/projects/{demo}/leaks", json=[{"link_id": "NO", "event_date": "2026-11-01",
                                                             "kind": "fuga"}]).status_code == 422
    # Importación todo o nada desde la plantilla
    tpl = client.get(f"/api/projects/{demo}/leaks/template.xlsx")
    assert tpl.status_code == 200 and load_workbook(io.BytesIO(tpl.content)).sheetnames == ["Pérdidas"]
    wb = Workbook()
    ws = wb.active
    ws.title = "Pérdidas"
    for row in (["Tramo", "Fecha", "Tipo", "Caudal estimado", "Observación"], ["P-09", "2026-10-05", "Rotura", 0.2, None],
                ["P-09", "05/10/2026", "reparación", None, "ok"], ["P-99", "2026-10-05", "fuga", None, None]):
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    bad = client.post(f"/api/projects/{demo}/leaks/import", files={"file": ("p.xlsx", buf.getvalue(), XLSX)})
    assert bad.status_code == 422 and "P-99" in bad.json()["errors"][0]
    ws.delete_rows(4)
    buf = io.BytesIO()
    wb.save(buf)
    ok = client.post(f"/api/projects/{demo}/leaks/import", files={"file": ("p.xlsx", buf.getvalue(), XLSX)})
    assert ok.status_code == 200 and ok.json()["created"] == 2
    csv = "Tramo;Fecha;Tipo\nP-10;2026-11-02;fuga\n".encode()
    assert client.post(f"/api/projects/{demo}/leaks/import", files={"file": ("p.csv", csv, "text/csv")}).json()["created"] == 1
    assert len(client.get(f"/api/projects/{demo}/leaks").json()) == before + 4
    assert client.post(f"/api/projects/{demo}/leaks/delete", json={"ids": [new_id]}).json()["deleted"] == 1


def test_exportaciones_del_resumen(client, demo):
    x = client.get(f"/api/projects/{demo}/summary.xlsx")
    assert x.status_code == 200
    wb = load_workbook(io.BytesIO(x.content))
    assert {"Resumen", "Clientes", "Zonas por presión", "Clientes sobre cota", "Agua no contabilizada",
            "Plan de renovación", "Alertas"} <= set(wb.sheetnames)
    h = client.get(f"/api/projects/{demo}/summary.html")
    assert h.status_code == 200 and "Clientes sobre cota" in h.text and "C-025" in h.text and "window.print()" in h.text
    a = client.get(f"/api/projects/{demo}/summary/area.geojson").json()
    assert a["features"][0]["properties"]["margen_m"] == 50
    zg = client.get(f"/api/projects/{demo}/summary/zones.geojson").json()
    assert len(zg["features"]) >= 10 and {"nudo", "presion_m", "rango"} <= set(zg["features"][0]["properties"])


def test_resumen_sin_datos_de_perdidas(client):
    r = client.post("/api/projects", json={"name": "Vacío resumen"})
    pid = r.json()["id"]
    s = client.get(f"/api/projects/{pid}/summary").json()
    assert s["losses"]["has_events"] is False and s["losses"]["has_production"] is False
    assert "Sin datos" in s["losses"]["help"]
    assert s["clients"]["total"]["count"] == 0 and s["area"]["geometry"] is None
