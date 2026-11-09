"""Prueba de referencia: Net1, Net2 y Net3 (repositorio oficial, tag v2.3.5).

Para cada red se ejecuta runepanet (compilado desde el tag v2.3.5) y se lee su binario .out; en
paralelo se importa el mismo .inp en la API, se guarda en la base, se simula vía POST /simulate y se
comparan TODOS los pasos de reporte para todos los nudos y tramos.
"""
import pytest

from app.hydraulic.units import to_si
from tests.helpers import Collector, run_runepanet, total_headloss

NETWORKS = ["Net1", "Net2", "Net3"]
collector = Collector()


@pytest.fixture(scope="module", autouse=True)
def _report(report_dir):
    yield
    collector.write_markdown(
        report_dir / "resultados-referencia.md",
        "Resultados de la prueba de referencia (runepanet vs API)",
        "Generado automáticamente por `tests/test_reference_networks.py` en cada `make test`.\n"
        "Referencia: binario `.out` de `runepanet` (OWA-EPANET v2.3.5, SHA 444725f) sobre el `.inp` original, "
        "convertido a SI con las constantes internas de EPANET. Comparado con los resultados de la API "
        "(importación → base de datos → .inp generado → simulación) en todos los pasos de reporte. "
        "«Uso de la tolerancia» = máx(|Δ| / (atol + rtol·|ref|)); ≤ 100 % cumple.",
    )


@pytest.mark.parametrize("net", NETWORKS)
def test_reference_network(client, networks_dir, net):
    inp = networks_dir / f"{net}.inp"
    ref = run_runepanet(inp)

    with open(inp, "rb") as fh:
        r = client.post("/api/projects/import", files={"file": (f"{net}.inp", fh, "text/plain")},
                        data={"name": f"Referencia {net}"})
    assert r.status_code == 201, r.text
    imported = r.json()
    pid, version = imported["project"]["id"], imported["version"]

    doc = client.get(f"/api/projects/{pid}/network", params={"version": version}).json()
    kinds = {f["id"]: f["properties"]["kind"] for f in doc["network"]["features"]
             if f["properties"]["element"] == "link"}
    lengths = {f["id"]: f["properties"]["length_hydraulic_m"] for f in doc["network"]["features"]
               if f["properties"]["element"] == "link"}
    sg = float(doc["options"]["extra"].get("SPECIFIC GRAVITY", "1") or 1)

    r = client.post(f"/api/projects/{pid}/simulate", json={"model_version": version})
    assert r.status_code == 200, r.text
    sim = r.json()
    assert sim["status"] in ("ok", "warning"), sim["messages"]
    assert sim["engine"]["epanet_sha"] == "444725fbf16ab28b0470ef0ed281dc4849d49583"
    assert sim["times"] == ref.times, "Los pasos de reporte deben coincidir"

    exp = to_si(ref, kinds, specific_gravity=sg)
    import numpy as np

    for var in ("pressure", "head", "demand"):
        got = np.array([sim["nodes"][nid][var] for nid in ref.node_ids]).T
        row = collector.compare(net, var, exp[var], got)
        assert row.ok, f"{net} {var}: máx |Δ| = {row.max_abs:.3e}"
    for var in ("flow", "velocity", "headloss"):
        got = np.array([sim["links"][lid][var] for lid in ref.link_ids]).T
        want = exp[var]
        if var == "headloss":
            want = total_headloss(want, ref.link_ids, kinds, lengths)
            got = total_headloss(got, ref.link_ids, kinds, lengths)
        row = collector.compare(net, var, want, got)
        assert row.ok, f"{net} {var}: máx |Δ| = {row.max_abs:.3e}"
