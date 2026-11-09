"""Prueba de referencia: simulación de 24 h que reproduce SimulaEST1 (planilla ModeloEstanque).

Estanque de 200 m³ (altura útil 3,5 m), fuente de 10 L/s con el horario de bombeo de la columna F, consumo
Qmd = 6,9635 L/s modulado con la curva de SimulaEST1. La planilla no limita el rebalse (llega a 209,5 m³);
EPANET corta la entrada al llenarse. Se compara:

1. con la planilla, hora a hora, mientras no hay rebalse (diferencia < 0,1 m³);
2. con el balance de la planilla limitado a la capacidad (tolerancia según el paso hidráulico: con el
   estanque lleno EPANET cierra la entrada hasta el paso siguiente, así que el nivel baja como máximo
   consumo·paso).

El detalle queda en docs/validation/simulaest1.md.
"""
import math

import pytest

from tests.helpers import fc, node, pipe

# Planilla SimulaEST1 (valores calculados de la hoja; ver docs/referencias/analisis-planillas.md)
COEF = [0.3, 0.2, 0.1, 0.1, 0.3, 0.5, 0.9, 1.5, 1.5, 1.5, 1.45, 1.35, 1.4, 1.4, 1.3, 1.1, 1.0, 0.9, 1.0, 1.2, 1.25,
        1.2, 0.9, 0.5]
BOMBA = [1, 1, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 1, 1, 1]  # columna F (36 m³/h)
PLANILLA_M3 = [178.4794520547945, 209.46575342465752, 206.958904109589, 204.4520547945205, 196.931506849315,
               184.39726027397253, 161.83561643835608, 160.23287671232868, 158.63013698630127, 157.02739726027386,
               156.6780821917807, 158.83561643835606, 159.73972602739715, 160.64383561643825, 164.05479452054783,
               172.4794520547944, 183.41095890410946, 196.849315068493, 207.78082191780808, 177.69863013698617,
               146.36301369863, 152.28082191780808, 165.71917808219163, 189.18493150684915]  # columna I
QMD = 6.963470319634704  # L/s (U5)
VOL, ALTURA, V0, QB = 200.0, 3.5, 150.0, 10.0
AREA = VOL / ALTURA
DIAM = math.sqrt(4 * AREA / math.pi)


def capped_balance() -> list[float]:
    v, out = V0, []
    for h in range(24):
        v = max(0.0, min(VOL, v + BOMBA[h] * QB * 3.6 - COEF[h] * QMD * 3.6))
        out.append(v)
    return out


def _network():
    x = [-71.2 + 0.0005 * k for k in range(6)]
    lat = -29.9
    return fc(
        node("R1", "reservoir", lon=x[0], lat=lat, head=300.0),
        node("JA", lon=x[1], lat=lat, elevation=150.0),
        node("JB", lon=x[2], lat=lat, elevation=150.0),
        node("E1", "tank", lon=x[3], lat=lat, elevation=100.0, init_level=V0 / AREA, min_level=0.0, max_level=ALTURA,
             tank_diameter=DIAM, min_volume=0.0),
        node("JD", lon=x[4], lat=lat, elevation=50.0, base_demand=QMD, demand_pattern="SIMULA"),
        pipe("PA", "R1", "JA", [[x[0], lat], [x[1], lat]], length_choice="manual", length_hydraulic_m=1.0,
             inner_diameter_mm=300.0),
        {"type": "Feature", "id": "BOMBA", "geometry": {"type": "LineString", "coordinates": [[x[1], lat], [x[2], lat]]},
         "properties": {"element": "link", "kind": "valve", "from_node": "JA", "to_node": "JB", "valve_type": "FCV",
                        "valve_setting": QB, "inner_diameter_mm": 150.0, "initial_status": "active",
                        "schedule": BOMBA}},
        pipe("PB", "JB", "E1", [[x[2], lat], [x[3], lat]], length_choice="manual", length_hydraulic_m=1.0,
             inner_diameter_mm=300.0),
        pipe("PC", "E1", "JD", [[x[3], lat], [x[4], lat]], length_choice="manual", length_hydraulic_m=1.0,
             inner_diameter_mm=300.0),
    )


def _run(client, step_min: int):
    pid = client.post("/api/projects", json={"name": f"SimulaEST1 paso {step_min} min"}).json()["id"]
    options = {"duration_h": 24, "hydraulic_step_min": step_min, "pattern_step_min": 60, "report_step_min": 60}
    aux = {"patterns": " SIMULA\t" + "\t".join(str(c) for c in COEF)}
    r = client.put(f"/api/projects/{pid}/network", json={"base_version": 1, "kind": "manual", "network": _network(),
                                                         "options": options, "aux": aux})
    assert r.status_code == 200, r.text
    sim = client.post(f"/api/projects/{pid}/simulate", json={"model_version": r.json()["version"]})
    assert sim.status_code == 200, sim.text
    return pid, sim.json()


@pytest.fixture(scope="module")
def runs(client):
    return {step: _run(client, step) for step in (60, 1)}


def test_inp_tiene_patron_horario_y_controles_de_la_columna_f(client, runs):
    pid, _ = runs[60]
    inp = client.get(f"/api/projects/{pid}/export.inp").text
    assert "DURATION\t24:00" in inp and "HYDRAULIC TIMESTEP\t1:00" in inp
    assert " LINK BOMBA CLOSED AT CLOCKTIME 2:00" in inp and " LINK BOMBA 10 AT CLOCKTIME 7:00" in inp
    assert " LINK BOMBA CLOSED AT CLOCKTIME 19:00" in inp and " LINK BOMBA 10 AT CLOCKTIME 21:00" in inp


def test_nivel_horario_reproduce_simulaest1(runs, report_dir):
    capped = capped_balance()
    first_overflow = next(h for h, v in enumerate(PLANILLA_M3) if v > VOL)
    rows = []
    for step, (_pid, sim) in runs.items():
        times = sim["times"]
        assert len(times) == 25 and times[1] - times[0] == 3600
        level = sim["nodes"]["E1"]["pressure"]  # en un estanque la presión es el nivel sobre el fondo
        vol = [lv * AREA for lv in level]
        assert vol[0] == pytest.approx(V0, abs=0.05)
        assert max(vol) <= VOL + 0.05, "EPANET no supera la capacidad del estanque"
        tol = max(c for c in COEF) * QMD * 3.6 * step / 60 + 0.1  # consumo máximo durante un paso hidráulico
        for h in range(24):
            got = vol[h + 1]  # EPANET informa al inicio del paso: t = h+1 ↔ fila h de la planilla
            if h < first_overflow:
                assert got == pytest.approx(PLANILLA_M3[h], abs=0.1), (step, h)
            assert got == pytest.approx(capped[h], abs=tol), (step, h, got, capped[h])
            rows.append((step, h, PLANILLA_M3[h], capped[h], got))
        flows = sim["links"]["BOMBA"]["flow"]
        assert flows[3] == pytest.approx(0.0, abs=1e-6) and flows[8] == pytest.approx(QB, abs=1e-3)
    _write_report(report_dir, rows, first_overflow)


def test_alerta_de_rebalse(runs):
    _pid, sim = runs[60]
    codes = {(a["code"], a["element_id"]) for a in sim["alerts"]}
    assert ("TANK_OVERFLOW", "E1") in codes


def _write_report(report_dir, rows, first_overflow):
    lines = ["# SimulaEST1 — nivel horario del estanque: planilla vs EPANET", "",
             "Generado por `backend/tests/test_eps_simulaest1.py`. Volumen al final de cada hora (m³).", "",
             f"- La planilla no limita el rebalse: desde la hora {first_overflow} supera los 200 m³ (máx. 209,5 m³).",
             "- EPANET corta la entrada con el estanque lleno; por eso se compara también con el balance de la "
             "planilla limitado a la capacidad («planilla limitada»).",
             "- Con el estanque lleno, EPANET mantiene cerrada la entrada hasta el siguiente paso hidráulico y el "
             "nivel baja según el consumo de ese intervalo: con paso de 60 min la diferencia puede llegar a "
             "consumo·1 h; con paso de 1 min es despreciable.",
             "- Mientras el estanque no se llena la diferencia es menor que 0,1 m³ con ambos pasos.", "",
             "| Paso | Hora | Planilla (I) | Planilla limitada | EPANET | EPANET − limitada |",
             "|---:|---:|---:|---:|---:|---:|"]
    for step, h, raw, cap, got in rows:
        lines.append(f"| {step} min | {h} | {raw:.2f} | {cap:.2f} | {got:.2f} | {got - cap:+.2f} |")
    (report_dir / "simulaest1.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
