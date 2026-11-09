"""Catálogo de diámetros interiores desde ModeloPozo.xlsx (hoja «D=Interiores»)."""
import os
from collections import Counter
from pathlib import Path

import pytest

from app.data.modelopozo import eval_formula, load_json, read_sheet, review_markdown

XLSX = Path(os.environ.get("REFERENCIAS_DIR", "/app/docs/referencias")) / "ModeloPozo.xlsx"


@pytest.fixture(scope="module")
def rows():
    if not XLSX.exists():
        pytest.fail(f"No se encontró {XLSX} (make test monta docs/referencias)")
    return read_sheet(XLSX)


def test_formulas_se_evaluan_con_la_referencia_a_la_fila():
    assert eval_formula("=Tabla3[[#This Row],[(mm)]]-9.5-9.5", 160) == pytest.approx(141.0)
    assert eval_formula("=90-8.2-8.2", 40) == pytest.approx(73.6)
    with pytest.raises(ValueError):
        eval_formula("=__import__('os')", 1)


def test_lectura_y_conteo_de_combinaciones(rows):
    assert len(rows) == 62
    counts = Counter((r.material, r.pipe_class) for r in rows)
    assert counts == {("AC", "PN10"): 11, ("Acero", "PN10"): 12, ("FFD", "PN10"): 7, ("HA", "PN10"): 1,
                      ("PEAD", "PN10"): 15, ("PVC", "PN10"): 13, ("PEAD", "PN16"): 3}
    by = {(r.material, r.pipe_class, r.dn): r for r in rows}
    assert by[("PVC", "PN10", 110)].inner_diameter_mm == 99.4
    assert by[("PEAD", "PN10", 160)].inner_diameter_mm == pytest.approx(141.0)  # fórmula evaluada
    assert by[("Acero", "PN10", 600)].inner_diameter_mm == 571.46
    assert ("PVC", "PN10", 40) not in by and ("HA", "PN10", 400) not in by  # celdas vacías = no disponible
    assert not [r for r in rows if r.pipe_class == "PN16" and r.material != "PEAD"]


def test_filas_dudosas(rows, report_dir):
    flagged = {(r.material, r.pipe_class, r.dn): r.review for r in rows if r.review}
    for dn in (40, 65):
        assert any("calculado sobre 90 mm" in x for x in flagged[("PEAD", "PN16", dn)])
    assert ("PEAD", "PN16", 90) not in flagged  # 90 − 2·8,2 = 73,6 es correcto para SDR 11
    assert ("PVC", "PN10", 90) in flagged
    (report_dir / "catalogo-modelopozo-revision.md").write_text(review_markdown(rows), encoding="utf-8")


def test_semilla_congelada_coincide_con_la_planilla(rows):
    frozen = load_json()
    assert [(r["material"], r["pipe_class"], r["dn"], r["inner_diameter_mm"]) for r in frozen] == \
           [(r.material, r.pipe_class, r.dn, r.inner_diameter_mm) for r in rows]


def test_catalogo_en_la_base(client):
    items = [i for i in client.get("/api/catalog/pipes").json() if i["standard"] == "Planilla ModeloPozo"]
    assert len(items) == 62
    assert all(not i["verified"] and "Planilla ModeloPozo (ingeniero hidráulico), no verificado" in i["source"] for i in items)
    pead40 = next(i for i in items if (i["material"], i["pipe_class"], i["dn"]) == ("PEAD", "PN16", 40))
    assert "calculado sobre 90 mm" in pead40["review"]
    ac = next(i for i in items if (i["material"], i["dn"]) == ("AC", 100))
    assert ac["od_mm"] is None and ac["hw_c"] == 140


def test_diametro_interior_manual_conserva_su_fuente(client):
    from tests.analysis_net import create, network

    net = network(client, clients=False)
    p2 = next(f for f in net["features"] if f["id"] == "P2")["properties"]
    p2.update(inner_diameter_mm=100.0, inner_diameter_source="manual")
    pid, v = create(client, "Interior manual", net)
    doc = client.get(f"/api/projects/{pid}/network", params={"version": v}).json()
    p2 = next(f for f in doc["network"]["features"] if f["id"] == "P2")["properties"]
    assert p2["inner_diameter_mm"] == 100.0 and p2["inner_diameter_source"] == "manual" and p2["dn"] == 110
    p1 = next(f for f in doc["network"]["features"] if f["id"] == "P1")["properties"]
    assert p1["inner_diameter_source"] == "catalogo"
