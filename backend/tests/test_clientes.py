"""Clientes: demanda trazable por nudo, validación de referencias e importación desde CSV."""
import pytest

from app.hydraulic.inp_writer import write_inp
from app.schemas.network import NetworkFeatureCollection, NetworkModel
from tests.analysis_net import D100, LAT0, LON0, create, network


def _model(client, pid, v):
    doc = client.get(f"/api/projects/{pid}/network", params={"version": v}).json()
    return doc, NetworkModel(options=doc["options"], aux=doc["aux"], network=NetworkFeatureCollection.model_validate(doc["network"]))


def test_demanda_del_nudo_es_la_suma_de_sus_clientes_mas_la_manual(client):
    net = network(client)
    next(f for f in net["features"] if f["id"] == "J1")["properties"]["base_demand"] = 0.5  # manual
    pid, v = create(client, "Clientes demanda", net)
    doc, model = _model(client, pid, v)
    c2 = next(f for f in doc["network"]["features"] if f["id"] == "C2")["properties"]
    assert c2["consumption_unit"] == "m3/mes" and c2["consumption_value"] == pytest.approx(2592.0)
    inp = write_inp(model)
    demands = [ln.split(";")[0].split() + [ln.split(";")[1]] for ln in inp.split("[DEMANDS]")[1].split("[")[0].splitlines() if ";" in ln]
    assert ["J1", "0.5", "manual"] in [[d[0], d[1], d[-1]] for d in demands]
    assert any(d[0] == "J1" and float(d[1]) == 2.0 and d[-1] == "cliente_C1" for d in demands)
    assert any(d[0] == "J2" and float(d[1]) == pytest.approx(1.0) and d[-1] == "cliente_C2" for d in demands)  # 2592 m³/mes = 1 L/s
    sim = client.post(f"/api/projects/{pid}/simulate", json={"model_version": v}).json()
    assert sim["nodes"]["J1"]["demand"][0] == pytest.approx(2.5, abs=1e-3)
    assert sim["nodes"]["J2"]["demand"][0] == pytest.approx(1.0, abs=1e-3)
    assert sim["links"]["P1"]["flow"][0] == pytest.approx(4.0, abs=1e-3)


def test_cliente_proyectado_solo_suma_con_la_opcion(client):
    net = network(client)
    next(f for f in net["features"] if f["id"] == "C3")["properties"]["status"] = "proyectado"
    pid, v = create(client, "Clientes proyectados", net)
    sim = client.post(f"/api/projects/{pid}/simulate", json={"model_version": v}).json()
    assert sim["nodes"]["J3"]["demand"][0] == pytest.approx(0.0, abs=1e-6)
    r = client.put(f"/api/projects/{pid}/network", json={"base_version": v, "kind": "manual", "network": net,
                                                          "options": {"include_projected_clients": True}})
    sim = client.post(f"/api/projects/{pid}/simulate", json={"model_version": r.json()["version"]}).json()
    assert sim["nodes"]["J3"]["demand"][0] == pytest.approx(0.5, abs=1e-3)


def test_cliente_en_nudo_inexistente_o_fuente_no_se_puede_guardar(client):
    pid = client.post("/api/projects", json={"name": "Clientes inválidos"}).json()["id"]
    for target, code in (("J9", "E_CLIENT_NODE"), ("E1", "E_CLIENT_NODE")):
        net = network(client)
        next(f for f in net["features"] if f["id"] == "C1")["properties"]["node"] = target
        r = client.put(f"/api/projects/{pid}/network", json={"network": net})
        assert r.status_code == 422 and code in {e["code"] for e in r.json()["validation"]["errors"]}


CSV = """lat;lon;nombre;consumo;tipo;estado
{lat};{lon_a};Panadería;0,8;comercial;activo
{lat2};{lon_b};Casa esquina;0,05;residencial;activo
{lat};{lon_c};Loteo nuevo;1,2;residencial;proyectado
"""


def test_importacion_csv_asigna_al_nudo_correcto(client):
    pid, v = create(client, "Importar clientes", network(client, clients=False))
    # A: sobre P2 a 20 m de J1 → J1. B: sobre P3 a 80 m de J2 (20 m de J3) → J3. C: 40 m al norte de P1, cerca de E1 → J1
    # (el extremo E1 es una fuente: se usa el otro extremo de consumo).
    text = CSV.format(lat=f"{LAT0 + 0.00005:.7f}".replace(".", ","), lat2=f"{LAT0 - 0.0001:.7f}".replace(".", ","),
                      lon_a=f"{LON0 + D100 * 3.2:.7f}".replace(".", ","), lon_b=f"{LON0 + D100 * 4.8:.7f}".replace(".", ","),
                      lon_c=f"{LON0 + D100 * 0.5:.7f}".replace(".", ","))
    r = client.post(f"/api/projects/{pid}/clients/import", data={"base_version": str(v)},
                    files={"file": ("clientes.csv", text.encode("utf-8"), "text/csv")})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["created"] == 3 and body["version"] == v + 1
    by_name = {row["name"]: row for row in body["rows"]}
    assert (by_name["Panadería"]["link"], by_name["Panadería"]["node"]) == ("P2", "J1")
    assert (by_name["Casa esquina"]["link"], by_name["Casa esquina"]["node"]) == ("P3", "J3")
    assert (by_name["Loteo nuevo"]["link"], by_name["Loteo nuevo"]["node"]) == ("P1", "J1")
    assert by_name["Panadería"]["distance_m"] == pytest.approx(5.6, abs=0.5)
    doc = client.get(f"/api/projects/{pid}/network").json()
    clients = {f["properties"]["name"]: f for f in doc["network"]["features"] if f["properties"]["element"] == "client"}
    assert clients["Loteo nuevo"]["properties"]["status"] == "proyectado"
    assert clients["Panadería"]["properties"]["client_type"] == "comercial"
    sim = client.post(f"/api/projects/{pid}/simulate", json={"model_version": body["version"]}).json()
    assert sim["nodes"]["J1"]["demand"][0] == pytest.approx(0.8, abs=1e-3)  # el proyectado no suma
    assert sim["nodes"]["J3"]["demand"][0] == pytest.approx(0.05, abs=1e-3)


def test_importacion_csv_con_errores_no_importa_nada(client):
    pid, v = create(client, "Importar con errores", network(client, clients=False))
    bad = "lat,lon,nombre,consumo\n-33.45,-70.65,Uno,1\nxx,-70.65,Dos,1\n-33.45,-70.65,Tres,-1\n"
    r = client.post(f"/api/projects/{pid}/clients/import", files={"file": ("c.csv", bad.encode(), "text/csv")})
    assert r.status_code == 422
    errors = r.json()["detail"]["errors"]
    assert any("Línea 3" in e for e in errors) and any("Línea 4" in e for e in errors)
    assert client.get(f"/api/projects/{pid}").json()["latest_version"] == v
    r = client.post(f"/api/projects/{pid}/clients/import", files={"file": ("c.csv", b"x,y\n1,2\n", "text/csv")})
    assert r.status_code == 422 and "Faltan columnas" in r.json()["detail"]["errors"][0]
