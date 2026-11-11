"""Página «Gestión»: cálculos con resultados conocidos (agua no contabilizada, dotación real, horas-cliente sin
servicio, estado de mantenciones, capacidad remanente) y la API completa sobre «APR Demo» (pestañas, filtros,
registros con importación y vista previa, exportaciones, informe mensual y .trazo)."""
import io
from datetime import date, datetime, timezone

import pytest
from openpyxl import Workbook, load_workbook

from app.schemas.network import HydraulicOptions, NetworkFeatureCollection, NetworkModel
from app.services import gestion_calc as calc
from app.services.gestion_capacity import compute
from tests.helpers import fc, node, pipe
from tests.test_sig_excel import XLSX, create_demo

UTC = timezone.utc
PERIOD = {"desde": "2025-11-01", "hasta": "2026-10-31"}


# ── Cálculos ──

def test_agua_no_contabilizada_mensual():
    # Medidor acumulado: 300 m³ en noviembre (30 días) y 310 en diciembre; lectura partida a medianoche de fin de mes.
    readings = [(datetime(2025, 11, 1, tzinfo=UTC), 1000.0), (datetime(2025, 12, 1, tzinfo=UTC), 1300.0),
                (datetime(2026, 1, 1, tzinfo=UTC), 1610.0)]
    prod = calc.meter_volumes_by_month(readings)
    assert prod == pytest.approx({"2025-11": 300.0, "2025-12": 310.0})
    rows = calc.nrw_monthly(prod, {"2025-11": 240.0, "2025-12": 232.5})
    assert [(r.month, r.nrw_m3, r.nrw_pct) for r in rows] == [("2025-11", 60.0, 20.0), ("2025-12", 77.5, 25.0)]
    # Un intervalo que cruza el fin de mes se reparte por tiempo: 10 días en nov. y 5 en dic. → 2/3 y 1/3.
    split = calc.meter_volumes_by_month([(datetime(2025, 11, 21, tzinfo=UTC), 0.0), (datetime(2025, 12, 6, tzinfo=UTC), 150.0)])
    assert split == pytest.approx({"2025-11": 100.0, "2025-12": 50.0})
    # Cambio de medidor (lectura menor): no suma volumen negativo
    assert calc.meter_volumes_by_month([(datetime(2026, 1, 1, tzinfo=UTC), 500.0), (datetime(2026, 1, 2, tzinfo=UTC), 10.0)]) == {}
    assert calc.nrw(0.0, 5.0) == (-5.0, None)


def test_dotacion_real():
    # 20 viviendas × 3,5 hab × 30 días; 315 m³ → 315 000 L / 2 100 hab·día = 150 L/hab/día
    assert calc.dotacion(315.0, 20, 3.5, 30) == 150.0
    assert calc.dotacion(10.0, 0, 3.5, 30) is None
    assert calc.consumption_bin(9.99) == "0–10 m³" and calc.consumption_bin(50) == "≥ 50 m³"


def test_horas_cliente_sin_servicio():
    spans = [
        calc.OutageSpan(datetime(2026, 3, 10, 8, tzinfo=UTC), datetime(2026, 3, 10, 12, tzinfo=UTC), 30),  # 4 h × 30
        # Cruza fin de mes: 2 h en marzo y 3 h en abril, 10 clientes
        calc.OutageSpan(datetime(2026, 3, 31, 22, tzinfo=UTC), datetime(2026, 4, 1, 3, tzinfo=UTC), 10),
        calc.OutageSpan(datetime(2026, 4, 5, tzinfo=UTC), datetime(2026, 4, 5, tzinfo=UTC), 99),  # duración cero
    ]
    out = calc.client_hours_by_month(spans, ["2026-03", "2026-04"], datetime(2026, 5, 1, tzinfo=UTC))
    assert out == {"2026-03": 140.0, "2026-04": 30.0}
    # Corte sin término: se cuenta hasta «ahora»
    open_ = calc.client_hours_by_month([calc.OutageSpan(datetime(2026, 4, 30, 20, tzinfo=UTC), None, 5)], ["2026-04"],
                                       datetime(2026, 4, 30, 23, tzinfo=UTC))
    assert open_ == {"2026-04": 15.0}


def test_estado_de_mantenciones():
    today = date(2026, 11, 11)
    assert calc.maintenance_status(date(2026, 11, 10), None, 30, today) == "atrasada"
    assert calc.maintenance_status(date(2026, 11, 11), None, 30, today) == "pendiente"  # vence hoy: al día
    assert calc.maintenance_status(date(2026, 12, 1), None, None, today) == "pendiente"
    assert calc.maintenance_status(date(2026, 10, 1), date(2026, 10, 2), None, today) == "hecha"  # única cumplida
    assert calc.maintenance_status(date(2026, 10, 1), date(2026, 10, 2), 30, today) == "atrasada"  # periódica: no queda «hecha»
    # Cumplir: atrasada → desde la fecha de cumplimiento; adelantada → desde la fecha programada
    assert calc.advance(date(2026, 10, 1), 30, date(2026, 10, 20)) == date(2026, 11, 19)
    assert calc.advance(date(2026, 10, 1), 30, date(2026, 9, 25)) == date(2026, 10, 31)


def test_movimientos_de_clientes_y_semaforo():
    history = {"A": ["2026-01", "2026-02", "2026-03"], "B": ["2026-01"], "C": ["2026-02", "2026-03"]}
    by_month = {"2026-01": {"A", "B"}, "2026-02": {"A", "C"}, "2026-03": {"A", "C"}}
    mov = calc.client_movements(["2026-01", "2026-02", "2026-03"], by_month, history)
    assert mov == {"2026-01": (2, 0, 0), "2026-02": (2, 1, 1), "2026-03": (2, 0, 0)}
    assert calc.status_of(10, 20, 35, False) == "bueno" and calc.status_of(25, 20, 35, False) == "regular"
    assert calc.status_of(40, 20, 35, False) == "malo" and calc.status_of(96, 95, 80, True) == "bueno"
    assert calc.variation_pct(110, 100) == 10.0 and calc.variation_pct(5, 0) is None
    assert calc.previous_period(date(2026, 1, 1), date(2026, 3, 31)) == (date(2025, 10, 3), date(2025, 12, 31))


def test_capacidad_remanente_resultado_conocido():
    """Reservorio (carga 50 m) → 1 000 m de tubería D 100 mm C 130 → J1 (cota 0, 1 L/s). Clientes de 0,5 L/s.

    Hazen-Williams: con 25 clientes (13,5 L/s) la presión es 16,85 m; con 26 (14 L/s), 14,54 m < 15 m → caben 25.
    """
    net = fc(node("R", "reservoir", lon=-70.65, lat=-33.45, head=50.0, elevation=50.0),
             node("J1", lon=-70.64, lat=-33.45, elevation=0.0, base_demand=1.0),
             pipe("P1", "R", "J1", [[-70.65, -33.45], [-70.64, -33.45]], length_choice="manual", length_hydraulic_m=1000.0,
                  inner_diameter_mm=100.0, roughness=130.0, material="PVC", dn=110))
    model = NetworkModel(options=HydraulicOptions(duration_h=0, headloss="H-W"), network=NetworkFeatureCollection.model_validate(net))
    res = compute(model, q_lps=0.5, m3_month=1296.0, pmin=15.0, cap=200, version=1)
    assert res.capacity == 25 and not res.limited_by_cap
    assert res.bottleneck_node == "J1" and res.bottleneck_link == "P1"
    assert res.bottleneck_pressure < 15.0 and res.by_node == {"J1": 25}
    assert res.steps[-1].clients == 25 and res.steps[-1].min_pressure == pytest.approx(16.85, abs=0.1)
    capped = compute(model, q_lps=0.5, m3_month=1296.0, pmin=15.0, cap=10, version=1)
    assert capped.capacity == 10 and capped.limited_by_cap


# ── API sobre APR Demo ──

@pytest.fixture(scope="module")
def demo(client):
    return create_demo(client, "APR gestión")


def _tab(client, pid, tab, **q):
    r = client.get(f"/api/projects/{pid}/gestion/tabs/{tab}", params={**PERIOD, **q})
    assert r.status_code == 200, r.text
    body = r.json()
    return body, {i["key"]: i for i in body["indicators"]}, {t["key"]: t for t in body["tables"]}


def test_filtros_y_metas(client, demo):
    f = client.get(f"/api/projects/{demo}/gestion/filters").json()
    assert {"Alto", "Bajo"} <= set(f["sectors"]) and {"1", "2", "3"} <= set(f["routes"])
    assert f["data_start"] == "2025-11-01" and f["data_end"] == "2026-10-31" and f["model_version"] == 1
    st = client.get(f"/api/projects/{demo}/gestion/settings").json()
    assert st["targets"]["nrw"]["verified"] is False and st["chlorine_min"] == 0.2
    st["targets"]["nrw"].update(good=15, bad=30, verified=True)
    assert client.put(f"/api/projects/{demo}/gestion/settings", json=st).json()["targets"]["nrw"]["good"] == 15
    # Período por defecto: 12 meses hasta el último dato
    r = client.get(f"/api/projects/{demo}/gestion/tabs/equipo").json()
    assert r["period"]["start"] == "2025-11-01" and r["period"]["end"] == "2026-10-31" and len(r["period"]["months"]) == 12


def test_pestanas_operacion_clientes_perdidas(client, demo):
    body, ind, tab = _tab(client, demo, "operacion")
    assert 5 < ind["pressure_min"]["value"] < 25 and ind["pressure_min"]["chart"]["x"][0] == "00:00"
    assert {r["zona"] for r in tab["presion"]["rows"]} >= {"Alto", "Bajo"}
    assert 12 < ind["pump_hours"]["value"] < 16 and ind["kwh_m3"]["value"] > 0
    assert ind["well_use"]["value"] > 0 and ind["well_use"]["chart"]["reference"] == 6.0
    assert ind["tank_level_min"]["value"] is not None and ind["pressure_min"]["map"]["ids"] == ["J-11", "J-5"]
    _, ind_alto, _ = _tab(client, demo, "operacion", sector="Alto")
    assert ind_alto["pressure_min"]["value"] == ind["pressure_min"]["value"]  # el mínimo está en la zona alta (J-11)

    _, ind, tab = _tab(client, demo, "clientes")
    oct_ = next(r for r in tab["movimientos"]["rows"] if r["mes"] == "2026-10")
    assert oct_["activos"] == 27  # 30 − 2 proyectados − 1 suspendido
    assert sum(r["nuevos"] for r in tab["movimientos"]["rows"]) == 1  # C-028 (febrero)
    assert next(r for r in tab["movimientos"]["rows"] if r["mes"] == "2026-05")["bajas"] == 1  # C-029
    assert ind["active_clients"]["value"] == 27 and ind["consumption"]["value"] > 5000
    assert 80 < ind["dotacion"]["value"] < 250 and tab["mayores"]["rows"][0]["cliente"] == "C-017"
    _, ind_r, tab_r = _tab(client, demo, "clientes", ruta="1")
    assert ind_r["consumption"]["value"] < ind["consumption"]["value"] and {r["ruta"] for r in tab_r["consumo_cliente"]["rows"]} == {"1"}

    _, ind, tab = _tab(client, demo, "perdidas")
    assert 0 < ind["nrw"]["value"] < 50 and ind["nrw"]["target_verified"] is True
    assert {r["sector"] for r in tab["anc"]["rows"]} == {"Total", "Alto"} and len([r for r in tab["anc"]["rows"] if r["sector"] == "Total"]) == 12
    assert tab["fugas_tramo"]["rows"][0]["tramo"] == "P-06" and ind["leaks"]["map"]["weights"]["P-06"] == 2.0
    assert "P-08" in [r["tramo"] for r in tab["criticos"]["rows"]]


def test_pestanas_activos_cumplimiento_planificacion_equipo(client, demo):
    body, ind, tab = _tab(client, demo, "activos")
    assert ind["pipes_bad"]["value"] > 0 and tab["renovacion"]["rows"]
    assert any(r["status"] == "atrasada" for r in tab["mantenciones"]["rows"])
    assert tab["cumplimiento_mant"]["rows"] and body["extra"]["calendar"]

    _, ind, tab = _tab(client, demo, "cumplimiento")
    assert 0 < ind["extraction"]["value"] < 200 and ind["client_hours"]["value"] > 0
    assert 50 < ind["chlorine_ok"]["value"] < 100 and tab["cloro_fuera"]["rows"]
    assert ind["response_h"]["value"] > 0 and tab["cortes"]["rows"][0]["clients_affected"] >= 0
    assert all(r["clients_affected"] > 0 for r in tab["cortes"]["rows"])  # calculados con los cuarteles

    _, ind, tab = _tab(client, demo, "planificacion")
    assert [r["n"] for r in tab["proyeccion"]["rows"]][:3] == [0, 5, 10]
    assert ind["capacity"]["value"] is not None and tab["capacidad"]["rows"]
    assert tab["inversiones"]["rows"]

    _, ind, tab = _tab(client, demo, "equipo")
    assert "pruebas@trazo.test" in [r["email"] for r in tab["usuarios"]["rows"]]
    assert tab["tareas"]["rows"] and ind["tasks_overdue"]["value"] >= 1


def test_exportar_tabla_e_informe_mensual(client, demo):
    r = client.get(f"/api/projects/{demo}/gestion/tabs/perdidas/tables/anc.xlsx", params=PERIOD)
    assert r.status_code == 200 and r.headers["content-type"].startswith(XLSX)
    ws = load_workbook(io.BytesIO(r.content)).active
    assert ws.cell(4, 1).value == "Sector" and ws.max_row == 4 + 24
    r = client.get(f"/api/projects/{demo}/gestion/tabs/clientes/tables/mayores.csv", params=PERIOD)
    assert r.status_code == 200 and "C-017" in r.content.decode("utf-8-sig")
    assert client.get(f"/api/projects/{demo}/gestion/tabs/clientes/tables/nada.csv").status_code == 404
    html = client.get(f"/api/projects/{demo}/gestion/report.html", params=PERIOD).text
    assert "Informe mensual de gestión — APR gestión" in html and "Versión del modelo: 1" in html
    for title in ("Operación", "Clientes y consumo", "Pérdidas", "Activos y mantenimiento", "Cumplimiento",
                  "Planificación", "Equipo"):
        assert f"<h2>{title}</h2>" in html
    r = client.get(f"/api/projects/{demo}/gestion/report.xlsx", params=PERIOD)
    wb = load_workbook(io.BytesIO(r.content))
    assert wb.sheetnames[0] == "Indicadores" and len(wb.sheetnames) > 8


def test_registros_formulario_importacion_y_mantenciones(client, demo):
    specs = {s["kind"]: s for s in client.get(f"/api/projects/{demo}/gestion/records").json()}
    assert set(specs) == {"energia", "cloro", "cortes", "reclamos", "mantenciones", "lecturas"}
    base = f"/api/projects/{demo}/gestion/records"
    r = client.post(f"{base}/cloro", json=[{"measured_at": "2026-11-01 09:00", "point": "J-5", "mg_l": "0,8"}])
    assert r.status_code == 201 and r.json()["rows"][0]["mg_l"] == 0.8
    bad = client.post(f"{base}/cloro", json=[{"measured_at": "ayer", "point": "J-5", "mg_l": -1}])
    assert bad.status_code == 422 and len(bad.json()["detail"]["rows"][0]["errors"]) == 2
    # Corte en un tramo: clientes afectados calculados con su cuartel
    r = client.post(f"{base}/cortes", json=[{"kind": "emergencia", "started_at": "2026-11-02 08:00",
                                             "ended_at": "2026-11-02 10:00", "link_id": "P-08"}])
    row = r.json()["rows"][0]
    assert row["clients_affected"] > 0 and row["client_hours"] == pytest.approx(2 * row["clients_affected"])
    # Plantilla → importación con vista previa y errores por fila → solo válidas
    t = load_workbook(io.BytesIO(client.get(f"{base}/lecturas/template.xlsx").content)).active
    assert [c.value for c in t[1]] == ["N° cliente", "Período", "Consumo"]
    wb = Workbook()
    ws = wb.active
    for row_ in (["N° cliente", "Período", "Consumo"], ["1001", "2026-11", 17.5], ["C-002", "11/2026", "20,5"],
                 ["9999", "2026-11", 3], ["1004", "2026-13", 3]):
        ws.append(row_)
    buf = io.BytesIO()
    wb.save(buf)
    files = {"file": ("lecturas.xlsx", buf.getvalue(), XLSX)}
    pv = client.post(f"{base}/lecturas/import", files=files).json()
    assert pv["valid"] == 2 and pv["invalid"] == 2 and not pv["applied"]
    assert [r["row"] for r in pv["rows"] if r["errors"]] == [4, 5] and "inexistente" in pv["rows"][2]["errors"][0]
    assert client.post(f"{base}/lecturas/import", params={"apply": True}, files=files).status_code == 422
    ok = client.post(f"{base}/lecturas/import", params={"apply": True, "only_valid": True}, files=files).json()
    assert ok["applied"] and ok["created"] == 2
    again = client.post(f"{base}/lecturas/import", params={"apply": True, "only_valid": True}, files=files).json()
    assert again["created"] == 0 and again["updated"] == 2  # mismo cliente y mes: se actualiza
    rows = client.get(f"{base}/lecturas", params={"desde": "2026-11-01", "hasta": "2026-11-30"}).json()["rows"]
    assert {(r["client"], r["m3"]) for r in rows} == {("C-001", 17.5), ("C-002", 20.5)}
    csv = client.get(f"{base}/lecturas/export.csv", params={"desde": "2026-11-01"}).content.decode("utf-8-sig")
    assert csv.splitlines()[0] == "N° cliente;Período;Consumo" and "C-002;2026-11;20,5" in csv
    # Mantención periódica: cumplir avanza la próxima fecha y queda en el registro
    m = client.post(f"{base}/mantenciones", json=[{"kind": "probar grifos", "element": "G-1", "frequency_days": 90,
                                                   "next_date": "2026-11-01", "assignee": "Ana"}]).json()["rows"][0]
    assert m["status"] in ("atrasada", "pendiente")
    done = client.post(f"{base}/mantenciones/{m['id']}/complete", json={"done_on": "2026-11-05", "note": "OK"}).json()["rows"][0]
    assert done["next_date"] == "2027-02-03" and done["status"] == "pendiente"
    logs = client.get(f"{base}/mantenciones/logs", params={"task_id": m["id"]}).json()
    assert logs[0]["done_on"] == "2026-11-05" and logs[0]["scheduled_for"] == "2026-11-01"
    assert client.post(f"{base}/mantenciones", json=[{"kind": "otra", "next_date": "2026-11-01", "frequency_days": 30,
                                                      "done_on": "2026-11-01"}]).status_code == 422
    assert client.post(f"{base}/cloro/delete", json={"ids": [r["id"] for r in client.get(f"{base}/cloro", params={"desde": "2026-11-01"}).json()["rows"]]}).json()["deleted"] == 1


def test_factibilidad_queda_en_el_historial_y_trazo(client, demo):
    net = client.get(f"/api/projects/{demo}/network").json()["network"]
    lk = next(f for f in net["features"] if f["id"] == "P-05")
    (x0, y0), (x1, y1) = lk["geometry"]["coordinates"][0], lk["geometry"]["coordinates"][-1]
    r = client.post(f"/api/projects/{demo}/feasibility", json={"model_version": 1, "link": "P-05",
                                                              "point": [(x0 + x1) / 2, (y0 + y1) / 2],
                                                              "consumption_lps": 0.05, "elevation": 237.0, "name": "Loteo"})
    assert r.status_code == 200, r.text
    _, _, tab = _tab(client, demo, "planificacion", desde="2026-01-01", hasta=date.today().isoformat())
    assert tab["factibilidades"]["rows"][0]["nombre"] == "Loteo"
    # .trazo: los registros viajan con el proyecto
    trazo = client.get(f"/api/projects/{demo}/export.trazo")
    assert trazo.status_code == 200
    imp = client.post("/api/projects/import-trazo", files={"file": ("demo.trazo", trazo.content, "application/zip")})
    assert imp.status_code == 201, imp.text
    pid2 = imp.json()["project"]["id"]
    for kind in ("energia", "cloro", "cortes", "reclamos", "mantenciones", "lecturas"):
        a = client.get(f"/api/projects/{demo}/gestion/records/{kind}").json()["rows"]
        b = client.get(f"/api/projects/{pid2}/gestion/records/{kind}").json()["rows"]
        assert len(a) == len(b) > 0, kind
    la = client.get(f"/api/projects/{demo}/gestion/records/mantenciones/logs").json()
    lb = client.get(f"/api/projects/{pid2}/gestion/records/mantenciones/logs").json()
    assert len(la) == len(lb)
    _, _, tab2 = _tab(client, pid2, "planificacion", desde="2026-01-01", hasta=date.today().isoformat())
    assert tab2["factibilidades"]["rows"][0]["nombre"] == "Loteo"
    assert client.get(f"/api/projects/{pid2}/gestion/settings").json()["targets"]["nrw"]["good"] == 15
