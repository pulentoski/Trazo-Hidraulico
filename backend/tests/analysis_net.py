"""Red de ensayo para clientes, factibilidad y escenarios.

E1 (estanque, fondo 50 m, nivel 3 m) → P1 (PVC DN 90, 300 m) → J1 → P2 (PVC DN 110, 100 m) → J2 → P3 (PVC DN 110,
100 m) → J3. Cotas de J1–J3 configurables. Los consumos van como clientes (C1 en J1, C2 en J2, C3 en J3).
"""
from tests.helpers import fc, node, pipe

LON0, LAT0 = -70.6500, -33.4500
D100 = 0.0010783  # ≈ 100 m en longitud a esta latitud


def item(client, dn, material="PVC", cls="C10"):
    return next(i for i in client.get("/api/catalog/pipes").json()
                if i["material"] == material and i["dn"] == dn and i["pipe_class"] == cls)


def client_feature(cid, node_id, lon, lat, value, unit="L/s", **props):
    return {"type": "Feature", "id": cid, "geometry": {"type": "Point", "coordinates": [lon, lat + 0.0002]},
            "properties": {"element": "client", "node": node_id, "consumption_value": value,
                           "consumption_unit": unit, **props}}


def shutoff_feature(sid, link, position=0.5, state="open", name=None):
    return {"type": "Feature", "id": sid, "geometry": {"type": "Point", "coordinates": [0, 0]},
            "properties": {"element": "shutoff", "link": link, "position": position, "state": state, "name": name}}


def network(client, *, elev=(30.0, 30.0, 30.0), demands=(2.0, 1.0, 0.5), dn1=90, clients=True, extra=()):
    x = [LON0 + D100 * k for k in (0, 3, 4, 5)]  # E1, J1 (300 m), J2 (+100), J3 (+100)

    def cat(dn):
        it = item(client, dn)
        return dict(material="PVC", dn=dn, pipe_class="C10", catalog_pipe_id=it["id"],
                    inner_diameter_mm=it["inner_diameter_mm"], roughness=it["hw_c"])

    feats = [
        node("E1", "tank", lon=x[0], lat=LAT0, elevation=50.0, init_level=3.0, min_level=0.5, max_level=4.0,
             tank_diameter=5.0, min_volume=0.0),
        node("J1", lon=x[1], lat=LAT0, elevation=elev[0]),
        node("J2", lon=x[2], lat=LAT0, elevation=elev[1]),
        node("J3", lon=x[3], lat=LAT0, elevation=elev[2]),
        pipe("P1", "E1", "J1", [[x[0], LAT0], [x[1], LAT0]], length_choice="manual", length_hydraulic_m=300.0, **cat(dn1)),
        pipe("P2", "J1", "J2", [[x[1], LAT0], [x[2], LAT0]], length_choice="manual", length_hydraulic_m=100.0, **cat(110)),
        pipe("P3", "J2", "J3", [[x[2], LAT0], [x[3], LAT0]], length_choice="manual", length_hydraulic_m=100.0, **cat(110)),
    ]
    if clients:
        feats += [client_feature("C1", "J1", x[1], LAT0, demands[0], name="Escuela"),
                  client_feature("C2", "J2", x[2], LAT0, demands[1] * 2592.0, unit="m3/mes", name="Almacén"),
                  client_feature("C3", "J3", x[3], LAT0, demands[2], name="Casa 3")]
    feats += list(extra)
    return fc(*feats)


def create(client, name, net, **save_kw):
    pid = client.post("/api/projects", json={"name": name}).json()["id"]
    body = {"base_version": 1, "kind": "manual", "network": net, **save_kw}
    r = client.put(f"/api/projects/{pid}/network", json=body)
    assert r.status_code == 200, r.text
    return pid, r.json()["version"]
