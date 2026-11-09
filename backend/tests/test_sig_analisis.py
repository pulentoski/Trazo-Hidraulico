"""SIG — cuarteles de corta, consultas, búsqueda, grifos (incendio) y exportaciones DXF / GeoPackage."""
import os
import re
import sqlite3
import subprocess
import tempfile

import pytest

from tests.analysis_net import D100, LAT0, LON0, client_feature, create, item, network, shutoff_feature
from tests.helpers import node, pipe
from tests.test_sig_excel import create_demo


def _sector_net(client):
    """E1 → J1 → J2 → J3, y J2 → J4. Válvulas V1 (P2), V2 (P3) y V3 (P4) a mitad de tramo."""
    it = item(client, 110)
    cat = dict(material="PVC", dn=110, pipe_class="C10", catalog_pipe_id=it["id"],
               inner_diameter_mm=it["inner_diameter_mm"], roughness=it["hw_c"])
    j4 = (LON0 + 4 * D100, LAT0 - 0.0009)
    net = network(client, extra=[
        node("J4", lon=j4[0], lat=j4[1], elevation=30.0),
        pipe("P4", "J2", "J4", [[LON0 + 4 * D100, LAT0], list(j4)], length_choice="manual", length_hydraulic_m=100.0, **cat),
        client_feature("C4", "J3", LON0 + 5 * D100, LAT0, 0.1, name="Casa 4"),
        client_feature("C5", "J4", j4[0], j4[1], 0.1, name="Casa 5"),
        shutoff_feature("V1", "P2"), shutoff_feature("V2", "P3"), shutoff_feature("V3", "P4"),
    ])
    return create(client, "Cuarteles conocidos", net)


def test_cuarteles_en_red_de_prueba_con_resultado_conocido(client):
    pid, v = _sector_net(client)
    res = client.get(f"/api/projects/{pid}/sectors").json()
    s = {x["id"]: x for x in res["sectors"]}
    assert sorted(s) == ["C-01", "C-02", "C-03", "C-04"]
    assert s["C-01"]["valves"] == ["V1"] and s["C-01"]["has_source"] and s["C-01"]["clients"] == ["C1"]
    assert s["C-02"]["valves"] == ["V1", "V2", "V3"] and s["C-02"]["clients"] == ["C2"]
    assert sorted(s["C-02"]["downstream_clients"]) == ["C3", "C4", "C5"] and s["C-02"]["affected_clients"] == 4
    assert s["C-03"]["valves"] == ["V2"] and sorted(s["C-03"]["clients"]) == ["C3", "C4"]
    assert s["C-04"]["valves"] == ["V3"] and s["C-04"]["clients"] == ["C5"] and s["C-04"]["downstream_clients"] == []
    # Metros: C-01 = P1 (300) + ½ P2 (50); C-02 = ½ P2 + ½ P3 + ½ P4 = 150.
    assert s["C-01"]["length_m"] == pytest.approx(350.0) and s["C-02"]["length_m"] == pytest.approx(150.0)
    assert {p["link"] for p in s["C-02"]["pieces"]} == {"P2", "P3", "P4"}
    exp = client.get(f"/api/projects/{pid}/sectors/C-02/export", params={"fmt": "csv"})
    text = exp.content.decode("utf-8-sig")
    assert exp.status_code == 200 and "V3" in text and "C5;" in text and "aguas abajo" in text
    # Válvula inoperativa: no sirve para cortar; C-03 y C-02 se unen.
    doc = client.get(f"/api/projects/{pid}/network").json()
    for f in doc["network"]["features"]:
        if f["id"] == "V2":
            f["properties"]["condition"] = "inoperativo"
    r = client.put(f"/api/projects/{pid}/network", json={"base_version": v, "kind": "manual", "network": doc["network"]})
    assert r.status_code == 200
    res2 = client.get(f"/api/projects/{pid}/sectors").json()
    assert len(res2["sectors"]) == 3 and res2["inoperative_valves"] == ["V2"]


@pytest.fixture(scope="module")
def demo(client):
    return create_demo(client, "APR consultas")


def q(client, pid, element, *conds, logic="and"):
    r = client.post(f"/api/projects/{pid}/query", json={"element": element, "where": {"logic": logic, "conditions": list(conds)}})
    assert r.status_code == 200, r.text
    return r.json()


def test_consultas_con_conteo_esperado(client, demo):
    r = q(client, demo, "tramos", {"field": "material", "op": "eq", "value": "PVC"},
          {"field": "dn", "op": "le", "value": 63}, {"field": "install_year", "op": "lt", "value": 2000})
    assert r["count"] == 3 and sorted(x["id"] for x in r["rows"]) == ["P-08", "P-09", "P-13"]
    assert r["sums"]["length_hydraulic_m"] > 0
    r = q(client, demo, "clientes", {"field": "route", "op": "eq", "value": "3"})
    assert r["count"] == 10 and r["sums"]["_consumption_lps"] > 0
    r = q(client, demo, "clientes", {"field": "cuartel", "op": "eq", "value": "C-04"})
    assert r["count"] == 4
    r = q(client, demo, "tramos", {"field": "condition", "op": "eq", "value": "malo"})
    assert sorted(x["id"] for x in r["rows"]) == ["P-06", "P-08", "P-13"]
    r = q(client, demo, "tramos", {"field": "condition", "op": "eq", "value": "malo"},
          {"field": "network_type", "op": "eq", "value": "impulsión"}, logic="or")
    assert r["count"] == 4
    # Exportación de resultados
    body = {"element": "clientes", "where": {"conditions": [{"field": "route", "op": "eq", "value": "3"}]}}
    x = client.post(f"/api/projects/{demo}/query/export", params={"fmt": "xlsx"}, json=body)
    assert x.status_code == 200 and x.content[:2] == b"PK"
    c = client.post(f"/api/projects/{demo}/query/export", params={"fmt": "csv"}, json=body)
    assert len(c.content.decode("utf-8-sig").strip().splitlines()) == 11


def test_busqueda_y_consultas_guardadas(client, demo):
    hits = client.get(f"/api/projects/{demo}/search", params={"q": "MED-2405"}).json()
    assert hits[0]["id"] == "C-005" and hits[0]["match"] == "N° medidor"
    assert client.get(f"/api/projects/{demo}/search", params={"q": "p-13"}).json()[0]["id"] == "P-13"
    assert any(h["id"] == "C-012" for h in client.get(f"/api/projects/{demo}/search", params={"q": "los aromos 220"}).json())
    body = {"name": "Ruta 3", "definition": {"element": "clientes",
                                            "where": {"logic": "and", "conditions": [{"field": "route", "op": "eq", "value": "3"}]}}}
    r = client.post(f"/api/projects/{demo}/queries", json=body)
    assert r.status_code == 201
    assert [x["name"] for x in client.get(f"/api/projects/{demo}/queries").json()] == ["Ruta 3"]
    assert client.delete(f"/api/projects/{demo}/queries/{r.json()['id']}").status_code == 204


def test_grifo_presion_y_caudal_disponible(client, demo):
    r = client.post(f"/api/projects/{demo}/hydrants/fire")
    assert r.status_code == 200, r.text
    g = r.json()["hydrants"][0]
    assert g["id"] == "G-1" and g["node"] == "J-5"
    assert g["static_pressure_m"] > g["residual_pressure_m"]
    assert 0 < g["available_flow_lps"] < 200
    # Coherencia: con el caudal disponible la presión residual queda en el mínimo exigido.
    assert (g["available_flow_lps"] >= g["fire_flow_lps"]) == g["ok"]


def _ogrinfo(path: str) -> str:
    return subprocess.run(["ogrinfo", "-ro", "-so", "-al", path], capture_output=True, text=True, check=True).stdout


def test_exportaciones_dxf_y_geopackage(client, demo):
    with tempfile.TemporaryDirectory() as tmp:
        d = client.get(f"/api/projects/{demo}/export.dxf")
        assert d.status_code == 200
        path = os.path.join(tmp, "red.dxf")
        open(path, "wb").write(d.content)
        text = d.content.decode("cp1252")
        for layer in ("AP_DN110", "AP_DN63", "VALVULAS", "CLIENTES", "ESTANQUES", "GRIFOS", "POZOS"):
            assert f"\n2\n{layer}\n" in text
        info = subprocess.run(["ogrinfo", "-ro", "-al", "-q", path], capture_output=True, text=True, check=True).stdout
        assert "AP_DN110" in info
        # Coordenadas UTM 19S (Norte ≈ 6,68 millones de metros)
        assert re.search(r"\nVERTEX\n8\nAP_DN\d+\n10\n\d{6}\.\d{3}\n20\n66\d{5}\.\d{3}", text)
        g = client.get(f"/api/projects/{demo}/export.gpkg")
        assert g.status_code == 200
        gp = os.path.join(tmp, "red.gpkg")
        open(gp, "wb").write(g.content)
        db = sqlite3.connect(gp)
        assert db.execute("SELECT count(*) FROM clientes").fetchone()[0] == 30
        assert db.execute("SELECT count(*) FROM tramos").fetchone()[0] == 15
        db.close()
        out = _ogrinfo(gp)
        assert "Layer name: tramos" in out and "Feature Count: 30" in out and "32719" in out
