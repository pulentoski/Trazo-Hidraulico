"""QA hidráulico (pruebas 1–6 y 12): la API contra runepanet con el mismo .inp, alertas y mensajes."""
import math
import re

import pytest

from tests.qa.common import (QA, base_network, compare_all, link_value, new_project, node_value, reference_for,
                             save, simulate, within)

PRESSURE_CODES = {"PRESSURE_LOW", "PRESSURE_HIGH"}
TOL_P = 1e-3  # atol de presión documentado (m)


def _run(client, name, *, options=None, **net_kw):
    pid = new_project(client, name, **(options or {}))
    saved = save(client, pid, base_network(client, **net_kw))
    code, sim = simulate(client, pid, saved["version"])
    assert code == 200, sim
    ref, inp = reference_for(client, pid, saved["version"], sim)
    lengths = {lid: v["length_hydraulic_m"] for lid, v in saved["lengths"].items()}
    return pid, saved, sim, ref, inp, lengths


# 1 ─ Red base
def test_01_red_base_presion_igual_a_runepanet_y_sin_alertas(client):
    _, _, sim, ref, _, lengths = _run(client, "QA 1 red base")
    compare_all("1 · red base (2 L/s, DN 90)", ref, sim, lengths)
    p = sim["nodes"]["J1"]["pressure"][0]
    assert within("pressure", node_value(ref, "pressure", "J1"), p)
    assert 31.0 < p < 33.0  # 50 + 3 − 20 = 33 m estáticos menos ~0,6 m de pérdida
    assert sim["status"] == "ok" and sim["messages"] == []
    assert not [a for a in sim["alerts"] if a["code"] in PRESSURE_CODES]


# 2 ─ Cuello de botella con 10 L/s
def test_02_cuello_de_botella_con_perdida_unitaria_de_runepanet(client):
    _, _, sim, ref, _, lengths = _run(client, "QA 2 cuello de botella", demand=10.0)
    compare_all("2 · 10 L/s, DN 90", ref, sim, lengths)
    alert = next(a for a in sim["alerts"] if a["code"] == "BOTTLENECK")
    assert alert["element_id"] == "P1" and alert["unit"] == "m/km"
    ref_unit = abs(link_value(ref, "headloss", "P1"))
    # Tolerancia documentada de la pérdida del tramo (m) expresada en m/km para P1 (300 m).
    atol, rtol = 1e-4 * 1000 / 300, 1e-4
    assert abs(alert["value"] - ref_unit) <= atol + rtol * ref_unit
    assert alert["value"] > alert["limit"] == 10.0
    assert "P1" in alert["message"] and "m/km" in alert["message"]


# 3 ─ DN 160 elimina el cuello de botella
def test_03_dn160_elimina_cuello_de_botella(client):
    _, _, sim, ref, _, lengths = _run(client, "QA 3 DN 160", demand=10.0, dn=160)
    compare_all("3 · 10 L/s, DN 160", ref, sim, lengths)
    assert not [a for a in sim["alerts"] if a["code"] == "BOTTLENECK"]
    assert abs(sim["links"]["P1"]["headloss"][0]) < 10.0


# 4 ─ 5500 m en DDA: presión negativa y advertencia del motor en español
def test_04_dda_presion_negativa_con_advertencia_en_espanol(client):
    _, _, sim, ref, _, lengths = _run(client, "QA 4 DDA 5500 m", demand=10.0, length=5500.0)
    compare_all("4 · DDA, 5500 m, 10 L/s", ref, sim, lengths)
    p = sim["nodes"]["J1"]["pressure"][0]
    assert p < 0
    assert sim["nodes"]["J1"]["demand"][0] == pytest.approx(10.0, abs=1e-3)  # DDA entrega toda la demanda
    assert sim["status"] == "warning"
    engine = next(m for m in sim["messages"] if m["code"] == "NEGATIVE_PRESSURE")
    assert engine["original"].startswith("WARNING: Negative pressures")
    assert engine["message"].startswith("Presiones negativas en la red")
    detail = next(m for m in sim["messages"] if m["code"] == "NEGATIVE_PRESSURE_NODE")
    assert detail["element_id"] == "J1" and "Presión negativa en el nudo J1" in detail["message"]
    for m in sim["messages"]:  # todo mensaje visible está en español
        assert not re.search(r"\b(WARNING|Negative|pressure|hrs)\b", m["message"]), m["message"]
    assert any(a["code"] == "PRESSURE_LOW" and a["element_id"] == "J1" for a in sim["alerts"])


# 5 ─ Mismo caso en PDA
def test_05_pda_entrega_parcial_presion_no_negativa(client):
    opts = {"demand_model": "PDA", "minimum_pressure": 0.0, "required_pressure": 15.0, "pressure_exponent": 0.5}
    _, _, sim, ref, inp, lengths = _run(client, "QA 5 PDA 5500 m", options=opts, demand=10.0, length=5500.0)
    assert "DEMAND MODEL\tPDA" in inp
    compare_all("5 · PDA, 5500 m, 10 L/s", ref, sim, lengths)
    delivered = sim["nodes"]["J1"]["demand"][0]
    assert 0 < delivered < 10.0
    assert sim["nodes"]["J1"]["pressure"][0] >= -TOL_P
    assert not [m for m in sim["messages"] if m["code"].startswith("NEGATIVE_PRESSURE")]


# 6 ─ Darcy-Weisbach: rugosidad en mm
def test_06_darcy_weisbach_rugosidad_en_mm(client):
    _, saved, sim, ref, inp, lengths = _run(client, "QA 6 Darcy-Weisbach", options={"headloss": "D-W"},
                                            demand=10.0, formula="D-W")
    compare_all("6 · Darcy-Weisbach, 10 L/s, DN 90", ref, sim, lengths)
    assert "HEADLOSS\tD-W" in inp and "UNITS\tLPS" in inp
    line = next(ln.split() for ln in inp.splitlines() if ln.split()[:1] == ["P1"])
    d_mm, eps_mm = float(line[4]), float(line[5])
    assert eps_mm == pytest.approx(0.0015)  # ε del catálogo PVC, enviado en mm (EPANET SI: mm)
    # Verificación independiente: Swamee-Jain con ε en mm reproduce la pérdida del motor (±2 %);
    # si el valor se interpretara en metros (ε = 1,5 mm) la pérdida sería varias veces mayor.
    q, d, nu = 0.010, d_mm / 1000, 1.1e-5 * 0.3048 ** 2  # ν por defecto de EPANET: 1,1·10⁻⁵ ft²/s
    v = q / (math.pi * d * d / 4)
    re_ = v * d / nu

    def unit_loss(eps_m):
        f = 0.25 / math.log10(eps_m / (3.7 * d) + 5.74 / re_ ** 0.9) ** 2
        return f * (1000 / d) * v * v / (2 * 9.81)

    got = abs(sim["links"]["P1"]["headloss"][0])
    assert got == pytest.approx(unit_loss(eps_mm / 1000), rel=0.02)
    assert unit_loss(eps_mm) > 2 * got
    report = client.post(f"/api/projects/{sim['project_id']}/validate",
                         json={"model_version": saved["version"]}).json()
    assert not [w for w in report["warnings"] if "rugosidad" in w["message"]]

    # Un coeficiente C de Hazen-Williams enviado con D-W se advierte (probable confusión de unidades).
    wrong = base_network(client, demand=10.0, formula="H-W")
    report = client.post(f"/api/projects/{sim['project_id']}/validate", json={"network": wrong}).json()
    assert any(w["code"] == "W_CRITERIA" and w["element_id"] == "P1" and "mm" in w["message"]
               for w in report["warnings"])


# 12 ─ Largo hidráulico: el que se envía al motor; manual prevalece sobre el geométrico
def test_12_largo_manual_prevalece_y_es_el_que_usa_el_motor(client):
    pid = new_project(client, "QA 12 largo")
    geo = save(client, pid, base_network(client, length=None))
    lg = geo["lengths"]["P1"]
    assert lg["length_plan_m"] == pytest.approx(300.0, abs=1.0)
    assert lg["length_hydraulic_m"] == lg["length_slope_m"] == pytest.approx(math.hypot(lg["length_plan_m"], 30.0))

    manual = save(client, pid, base_network(client, length=450.0))
    lm = manual["lengths"]["P1"]
    assert lm["length_hydraulic_m"] == 450.0 and lm["length_plan_m"] == pytest.approx(300.0, abs=1.0)
    code, sim = simulate(client, pid, manual["version"])
    assert code == 200
    ref, inp = reference_for(client, pid, manual["version"], sim)
    line = next(ln.split() for ln in inp.splitlines() if ln.split()[:1] == ["P1"])
    assert float(line[3]) == 450.0  # largo enviado al motor
    compare_all("12 · largo manual 450 m", ref, sim, {"P1": 450.0})

    # Mover el nudo (otro largo geométrico) no altera el largo manual.
    moved = save(client, pid, base_network(client, length=450.0, plan_m=600.0))
    assert moved["lengths"]["P1"]["length_plan_m"] == pytest.approx(600.0, abs=2.0)
    assert moved["lengths"]["P1"]["length_hydraulic_m"] == 450.0
