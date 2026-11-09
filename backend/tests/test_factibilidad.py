"""Factibilidad de un nuevo cliente: factible, no factible y factible al aumentar el DN; igual a runepanet."""
import hashlib

import pytest

from app.hydraulic.inp_writer import write_inp
from app.schemas.analysis import FeasibilityRequest
from app.schemas.network import NetworkFeatureCollection, NetworkModel
from app.services.feasibility import build_scenario
from tests.analysis_net import D100, LAT0, LON0, create, network
from tests.helpers import TOLERANCES
from tests.qa.common import runepanet_on

POINT_P2 = (LON0 + D100 * 3.5, LAT0 + 0.00002)  # a mitad de P2, 2 m al norte


def _assess(client, pid, v, consumption, elevation, link="P2", point=POINT_P2):
    body = {"model_version": v, "link": link, "point": list(point), "consumption_lps": consumption, "elevation": elevation}
    r = client.post(f"/api/projects/{pid}/feasibility", json=body)
    assert r.status_code == 200, r.text
    return body, r.json()


def _same_as_runepanet(client, pid, v, body, res, case):
    doc = client.get(f"/api/projects/{pid}/network", params={"version": v}).json()
    model = NetworkModel(options=doc["options"], aux=doc["aux"], network=NetworkFeatureCollection.model_validate(doc["network"]))
    scen, *_ = build_scenario(model, FeasibilityRequest(**body), 32719)
    text = write_inp(scen)
    assert hashlib.sha256(text.encode()).hexdigest() == res["inp_sha256"]  # mismo .inp que simuló la API
    ref = runepanet_on(text)
    i = ref.node_ids.index(res["new_node"])
    atol, rtol, _ = TOLERANCES["pressure"]
    assert abs(float(ref.nodes["pressure"][:, i].min()) - res["pressure_new"]) <= atol + rtol * abs(res["pressure_new"]), case


@pytest.fixture(scope="module")
def project(client):
    return create(client, "Factibilidad", network(client))


def test_factible(client, project):
    pid, v = project
    body, r = _assess(client, pid, v, 1.0, 30.0)
    assert r["feasible"] and r["verdict"] == "FACTIBLE" and r["reasons"] == []
    assert r["pressure_new"] > 15 and r["margin"] == pytest.approx(r["pressure_new"] - 15, abs=1e-3)
    assert r["link"] == "P2" and r["split_links"] == ["P2", "P2_1"] and r["distance_m"] == pytest.approx(2.2, abs=0.3)
    assert r["analysis"] == "DDA" and r["engine"]["epanet_sha"]
    pmin = next(c for c in r["criteria"] if c["key"] == "pressure_min")
    assert pmin["value"] == 15 and pmin["verified"] is False and "Perfil" in pmin["source"]
    assert r["affected_clients"] == [] and r["upgrades"] == []
    # El proyecto no cambió.
    assert client.get(f"/api/projects/{pid}").json()["latest_version"] == v
    _same_as_runepanet(client, pid, v, body, r, "Factibilidad · factible (1 L/s)")


def test_no_factible_por_cota(client, project):
    pid, v = project
    body, r = _assess(client, pid, v, 1.0, 45.0)  # carga estática 53 − 45 = 8 m < 15 m
    assert not r["feasible"] and r["verdict"] == "NO FACTIBLE"
    assert r["pressure_new"] < 15 and r["margin"] < 0
    assert r["bottleneck"] and r["upgrades"]
    assert r["upgrade_feasible"] is False  # ningún DN compensa la falta de carga
    _same_as_runepanet(client, pid, v, body, r, "Factibilidad · no factible (cota 45 m)")


def test_pasa_a_factible_al_aumentar_el_dn_del_cuello_de_botella(client, project):
    pid, v = project
    body, r = _assess(client, pid, v, 8.0, 30.0)
    assert not r["feasible"]
    assert r["bottleneck"] == "P1"
    newly = {a["id"] for a in r["affected_clients"] if a["newly_below"]}
    assert "C1" in newly  # el cliente existente en J1 queda bajo el mínimo
    assert any(i["id"] == "P1" and i["over_headloss"] for i in r["link_issues"])
    first = r["upgrades"][0]
    assert (first["link"], first["dn_from"], first["dn_to"]) == ("P1", 90, 110)
    assert first["inner_to"] > first["inner_from"]
    assert r["upgrade_feasible"] is True and r["upgrades"][-1]["feasible"]
    _same_as_runepanet(client, pid, v, body, r, "Factibilidad · 8 L/s antes de aumentar DN")


def test_informe_html(client, project):
    pid, v = project
    body = {"model_version": v, "link": "P2", "point": list(POINT_P2), "consumption_lps": 8.0, "elevation": 30.0}
    r = client.post(f"/api/projects/{pid}/feasibility/report", json=body)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
    html = r.text
    for text in ("NO FACTIBLE", "Factibilidad", f"v{v}", "OWA-EPANET 2.3.5", "444725fbf16ab28b0470ef0ed281dc4849d49583",
                 "no verificado", "DDA (por demanda)", "Presión mínima de servicio", "pasa a ser factible", "8,000 L/s"):
        assert text in html, text


def test_tuberia_inexistente_404(client, project):
    pid, v = project
    r = client.post(f"/api/projects/{pid}/feasibility", json={"model_version": v, "link": "P99", "point": [0, 0],
                                                              "consumption_lps": 1, "elevation": 30})
    assert r.status_code == 404
