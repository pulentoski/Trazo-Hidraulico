"""Red base de QA hidráulico y utilidades para comparar la API con runepanet sobre el mismo .inp.

Red base: E1 estanque (fondo 50 m, nivel inicial 3 m, mín 0,5 m, máx 4 m, diámetro 5 m)
→ P1 PVC DN 90 (C10), 300 m → J1 nudo (cota 20 m, demanda 2 L/s).
Las comparaciones usan las tolerancias de docs/validation/tolerancias.md (tests.helpers.TOLERANCES).
"""
from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path

import numpy as np

from app.hydraulic.inp_writer import write_inp
from app.hydraulic.out_reader import OutResults
from app.schemas.network import HydraulicOptions, NetworkFeatureCollection, NetworkModel
from tests.helpers import TOLERANCES, Collector, fc, node, pipe, run_runepanet

# Comparaciones de toda la batería QA; test_qa_report las escribe en docs/validation/resultados-qa.md.
QA = Collector()

LON0, LAT0 = -70.6500, -33.4500
DLON_300M = 0.003235  # ≈ 300 m en planta a la latitud de Santiago


def catalog_item(client, dn: int, material: str = "PVC", cls: str = "C10") -> dict:
    items = client.get("/api/catalog/pipes").json()
    return next(i for i in items if i["material"] == material and i["dn"] == dn and i["pipe_class"] == cls)


def base_network(client, *, demand: float = 2.0, dn: int = 90, length: float | None = 300.0,
                 formula: str = "H-W", j1_elevation: float | None = 20.0, plan_m: float = 300.0) -> dict:
    """Red base. `length` fija el largo hidráulico a mano; con None se usa el geométrico con pendiente."""
    item = catalog_item(client, dn)
    roughness = {"H-W": item["hw_c"], "D-W": item["dw_roughness_mm"], "C-M": item["manning_n"]}[formula]
    j1_lon = LON0 + DLON_300M * plan_m / 300.0
    link = dict(material="PVC", dn=item["dn"], pipe_class=item["pipe_class"], catalog_pipe_id=item["id"],
                inner_diameter_mm=item["inner_diameter_mm"], roughness=roughness)
    if length is not None:
        link.update(length_choice="manual", length_hydraulic_m=length)
    return fc(
        node("E1", "tank", lon=LON0, lat=LAT0, elevation=50.0, init_level=3.0, min_level=0.5, max_level=4.0,
             tank_diameter=5.0, min_volume=0.0),
        node("J1", lon=j1_lon, lat=LAT0, elevation=j1_elevation, base_demand=demand),
        pipe("P1", "E1", "J1", [[LON0, LAT0], [j1_lon, LAT0]], **link),
    )


def new_project(client, name: str, **options) -> str:
    body = {"name": name}
    if options:
        body["options"] = HydraulicOptions(**options).model_dump()
    r = client.post("/api/projects", json=body)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def save(client, pid: str, network: dict, *, options: dict | None = None, label: str | None = None) -> dict:
    latest = client.get(f"/api/projects/{pid}").json()["latest_version"]
    body = {"base_version": latest, "kind": "manual", "label": label, "network": network}
    if options is not None:
        body["options"] = HydraulicOptions(**options).model_dump()
    r = client.put(f"/api/projects/{pid}/network", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def simulate(client, pid: str, version: int) -> tuple[int, dict]:
    r = client.post(f"/api/projects/{pid}/simulate", json={"model_version": version})
    return r.status_code, r.json()


def model_of(client, pid: str, version: int) -> NetworkModel:
    doc = client.get(f"/api/projects/{pid}/network", params={"version": version}).json()
    return NetworkModel(options=doc["options"], aux=doc["aux"],
                        network=NetworkFeatureCollection.model_validate(doc["network"]))


def inp_of(client, pid: str, version: int) -> str:
    """El .inp exacto que la API entrega al motor para esa versión."""
    return write_inp(model_of(client, pid, version))


def runepanet_on(inp_text: str) -> OutResults:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "qa.inp"
        path.write_text(inp_text, encoding="latin-1")
        return run_runepanet(path)


def reference_for(client, pid: str, version: int, sim: dict) -> tuple[OutResults, str]:
    """Corre runepanet con el mismo .inp que simuló la API (verificado por SHA-256)."""
    text = inp_of(client, pid, version)
    assert hashlib.sha256(text.encode()).hexdigest() == sim["inp_sha256"], "el .inp de referencia no es el simulado"
    return runepanet_on(text), text


def within(variable: str, ref: float, got: float) -> bool:
    atol, rtol, _ = TOLERANCES[variable]
    return abs(ref - got) <= atol + rtol * abs(ref)


def compare_all(case: str, ref: OutResults, sim: dict, lengths: dict[str, float]) -> None:
    """Compara todos los nudos y tramos (todos los periodos) de la API contra runepanet y exige cumplir."""
    rows = []
    for var in ("pressure", "head", "demand"):
        got = np.array([[sim["nodes"][nid][var][k] for nid in ref.node_ids] for k in range(len(ref.times))])
        rows.append(QA.compare(case, var, ref.nodes[var], got))
    for var in ("flow", "velocity"):
        got = np.array([[sim["links"][lid][var][k] for lid in ref.link_ids] for k in range(len(ref.times))])
        rows.append(QA.compare(case, var, ref.links[var], got))
    # Pérdida: se compara la del tramo (m) = pérdida unitaria (m/km) · L / 1000, como en la validación del motor.
    scale = np.array([lengths[lid] / 1000.0 for lid in ref.link_ids])
    got = np.array([[sim["links"][lid]["headloss"][k] for lid in ref.link_ids] for k in range(len(ref.times))])
    rows.append(QA.compare(case, "headloss", np.asarray(ref.links["headloss"]) * scale, got * scale))
    bad = [r for r in rows if not r.ok]
    assert not bad, f"{case}: fuera de tolerancia: {bad}"


def node_value(ref: OutResults, var: str, nid: str, k: int = 0) -> float:
    return float(ref.nodes[var][k, ref.node_ids.index(nid)])


def link_value(ref: OutResults, var: str, lid: str, k: int = 0) -> float:
    return float(ref.links[var][k, ref.link_ids.index(lid)])
