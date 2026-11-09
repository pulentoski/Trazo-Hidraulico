"""Ida y vuelta: importar .inp → guardar en BD → exportar .inp → simular (runepanet y API).

Los resultados del .inp exportado deben coincidir con los del .inp original dentro de la tolerancia.
"""
import numpy as np
import pytest

from app.hydraulic.units import to_si
from tests.helpers import Collector, run_runepanet, total_headloss

collector = Collector()


@pytest.fixture(scope="module", autouse=True)
def _report(report_dir):
    yield
    collector.write_markdown(
        report_dir / "resultados-ida-y-vuelta.md",
        "Resultados de la prueba de ida y vuelta (.inp → BD → .inp)",
        "Generado automáticamente por `tests/test_roundtrip_inp.py`. Se importa el `.inp` original, se guarda en "
        "PostGIS, se exporta con GET /export.inp y se simula el archivo exportado con `runepanet` y re-importado "
        "en la API. Ambos se comparan contra `runepanet` sobre el original, en todos los pasos de reporte.",
    )


@pytest.mark.parametrize("net", ["Net1", "Net2", "Net3"])
def test_roundtrip(client, networks_dir, net, tmp_path):
    original = networks_dir / f"{net}.inp"
    ref = run_runepanet(original)

    with open(original, "rb") as fh:
        imported = client.post("/api/projects/import", files={"file": (f"{net}.inp", fh)}).json()
    pid = imported["project"]["id"]
    doc1 = client.get(f"/api/projects/{pid}/network").json()
    kinds = {f["id"]: f["properties"]["kind"] for f in doc1["network"]["features"] if f["properties"]["element"] == "link"}
    lengths = {f["id"]: f["properties"]["length_hydraulic_m"] for f in doc1["network"]["features"]
               if f["properties"]["element"] == "link"}
    sg = float(doc1["options"]["extra"].get("SPECIFIC GRAVITY", "1") or 1)

    r = client.get(f"/api/projects/{pid}/export.inp")
    assert r.status_code == 200
    assert "attachment" in r.headers["content-disposition"]
    exported = tmp_path / f"{net}-exportado.inp"
    exported.write_bytes(r.content)
    text = r.content.decode("latin-1")
    assert "[COORDINATES]" in text and "UNITS\tLPS" in text

    # 1) El .inp exportado, simulado con runepanet
    out = run_runepanet(exported)
    assert out.node_ids == ref.node_ids and out.link_ids == ref.link_ids
    assert out.times == ref.times
    a, b = to_si(ref, kinds, sg), to_si(out, kinds, sg)
    for x in (a, b):
        x["headloss"] = total_headloss(x["headloss"], ref.link_ids, kinds, lengths)
    for var in ("pressure", "head", "demand", "flow", "velocity", "headloss"):
        row = collector.compare(f"{net} (exportado, runepanet)", var, a[var], b[var])
        assert row.ok, f"{net} {var}: máx |Δ| = {row.max_abs:.3e}"

    # 2) El .inp exportado, re-importado y simulado por la API (coordenadas UTM → misma geometría)
    with open(exported, "rb") as fh:
        re_imp = client.post("/api/projects/import", files={"file": (exported.name, fh)}).json()
    assert re_imp["georeference"].startswith("EPSG:")
    doc2 = client.get(f"/api/projects/{re_imp['project']['id']}/network").json()
    c1 = {f["id"]: f["geometry"]["coordinates"] for f in doc1["network"]["features"]}
    c2 = {f["id"]: f["geometry"]["coordinates"] for f in doc2["network"]["features"]}
    assert c1.keys() == c2.keys()
    sim = client.post(f"/api/projects/{re_imp['project']['id']}/simulate", json={"model_version": 1}).json()
    for var in ("pressure", "head"):
        got = np.array([sim["nodes"][n][var] for n in ref.node_ids]).T
        row = collector.compare(f"{net} (re-importado, API)", var, a[var], got)
        assert row.ok
    for var in ("flow", "headloss"):
        got = np.array([sim["links"][lk][var] for lk in ref.link_ids]).T
        if var == "headloss":
            got = total_headloss(got, ref.link_ids, kinds, lengths)
        row = collector.compare(f"{net} (re-importado, API)", var, a[var], got)
        assert row.ok
