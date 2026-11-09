"""Escenarios de llaves: suministro (topología), presiones (motor) y comparación entre escenarios."""
from __future__ import annotations

from collections import defaultdict

from app.hydraulic.engine import run_model
from app.schemas.analysis import (BUILTIN_SCENARIOS, ClientState, CompareResult, CompareRow, NodeState,
                                  ScenarioResult)
from app.schemas.network import NetworkModel
from app.services.errors import NotFound


def closed_set(model: NetworkModel, scenario: str) -> tuple[str, set[str]]:
    ids = {sh.id for sh in model.network.shutoffs()}
    if scenario == "normal":
        return BUILTIN_SCENARIOS["normal"], set()
    if scenario == "todas_cerradas":
        return BUILTIN_SCENARIOS["todas_cerradas"], ids
    if scenario == "actual":
        return BUILTIN_SCENARIOS["actual"], {sh.id for sh in model.network.shutoffs() if sh.properties.state == "closed"}
    sc = next((x for x in model.scenarios if x.id == scenario), None)
    if sc is None:
        raise NotFound(f"Escenario «{scenario}» no encontrado")
    return sc.name, set(sc.closed) & ids


def supplied_nodes(model: NetworkModel, closed_links: set[str]) -> set[str]:
    """Nudos con camino a alguna fuente por tramos abiertos (las bombas y válvulas cuentan como abiertas
    salvo estado inicial cerrado)."""
    adj: dict[str, list[str]] = defaultdict(list)
    for lk in model.network.links():
        if lk.id in closed_links or lk.properties.initial_status == "closed":
            continue
        adj[lk.properties.from_node].append(lk.properties.to_node)
        adj[lk.properties.to_node].append(lk.properties.from_node)
    seen = {n.id for n in model.network.nodes() if n.properties.kind in ("reservoir", "tank")}
    stack = list(seen)
    while stack:
        for m in adj[stack.pop()]:
            if m not in seen:
                seen.add(m)
                stack.append(m)
    return seen


def without_unsupplied_demand(model: NetworkModel, unsupplied: set[str]) -> NetworkModel:
    """Copia del modelo sin demanda en los nudos sin suministro (EPANET daría presiones sin sentido)."""
    m = model.model_copy(deep=True)
    for n in m.network.nodes():
        if n.id in unsupplied and n.properties.kind == "junction":
            n.properties.base_demand = 0.0
            n.properties.demands = []
            n.properties.emitter_coeff = None
    m.network.features = [f for f in m.network.features
                          if not (getattr(f.properties, "element", "") == "client" and f.properties.node in unsupplied)]
    return m


def simulate_scenario(model: NetworkModel, scenario: str, *, project_id: str, version: int,
                      pressure_min: float) -> ScenarioResult:
    name, closed = closed_set(model, scenario)
    closed_links = model.closed_links(closed)
    supplied = supplied_nodes(model, closed_links)
    all_nodes = [n for n in model.network.nodes()]
    unsupplied = {n.id for n in all_nodes if n.id not in supplied}
    run_input = without_unsupplied_demand(model, unsupplied)
    # El estado de las llaves del escenario se aplica al escribir el .inp.
    run = _run(run_input, closed)
    res = run.results
    pmin_by_node: dict[str, float] = {}
    if res is not None:
        p = res.nodes["pressure"]
        for i, nid in enumerate(res.node_ids):
            pmin_by_node[nid] = float(p[:, i].min())
    demand_by_node = defaultdict(float)
    for n in all_nodes:
        demand_by_node[n.id] += n.properties.base_demand + sum(d.base for d in n.properties.demands)
    for nid, cs in model.client_demands().items():
        demand_by_node[nid] += sum(c.properties.consumption_lps for c in cs)

    nodes = [NodeState(id=n.id, supplied=n.id in supplied,
                       pressure=round(pmin_by_node[n.id], 4) if n.id in supplied and n.id in pmin_by_node else None,
                       demand=round(demand_by_node[n.id], 6))
             for n in all_nodes if n.properties.kind == "junction"]
    node_p = {x.id: x.pressure for x in nodes}
    elev = {n.id: n.properties.elevation for n in all_nodes}
    clients = []
    for c in model.network.clients():
        p = c.properties
        ok = p.node in supplied
        pressure = node_p.get(p.node) if ok else None
        if pressure is not None and p.elevation is not None and elev.get(p.node) is not None:
            pressure = round(pressure + elev[p.node] - p.elevation, 4)  # presión en la cota del cliente
        below = pressure is not None and pressure < pressure_min
        clients.append(ClientState(id=c.id, name=p.name, node=p.node, status=p.status,
                                   consumption_lps=round(p.consumption_lps, 6), supplied=ok, pressure=pressure,
                                   below_min=below, affected=(not ok) or below))
    unsupplied_links = sorted(lk.id for lk in model.network.links()
                              if lk.properties.from_node in unsupplied and lk.properties.to_node in unsupplied)
    affected = [c for c in clients if c.affected]
    summary = {
        "clientes": len(clients), "clientes_sin_suministro": sum(1 for c in clients if not c.supplied),
        "clientes_bajo_minimo": sum(1 for c in clients if c.below_min),
        "consumo_sin_suministro_lps": round(sum(c.consumption_lps for c in clients if not c.supplied), 6),
        "nudos_sin_suministro": len([n for n in nodes if not n.supplied]), "afectados": len(affected),
    }
    return ScenarioResult(project_id=project_id, model_version=version, scenario=scenario, scenario_name=name,
                          closed_shutoffs=sorted(closed), closed_links=sorted(closed_links),
                          pressure_min=pressure_min, nodes=nodes, clients=clients,
                          unsupplied_nodes=sorted(n for n in unsupplied
                                                  if next(x for x in all_nodes if x.id == n).properties.kind == "junction"),
                          unsupplied_links=unsupplied_links, summary=summary, messages=run.messages,
                          inp_sha256=run.inp_sha256)


def _run(model: NetworkModel, closed: set[str]):
    """Corre el motor con el estado de llaves del escenario."""
    from app.hydraulic import engine

    return engine.run_model(model, closed_shutoffs=closed)


def compare(a: ScenarioResult, b: ScenarioResult) -> CompareResult:
    rows: list[CompareRow] = []

    def diff(x, y):
        return round(y - x, 4) if x is not None and y is not None else None

    bn = {n.id: n for n in b.nodes}
    for n in a.nodes:
        m = bn[n.id]
        rows.append(CompareRow(kind="nudo", id=n.id, a=n.pressure, b=m.pressure, diff=diff(n.pressure, m.pressure),
                               supplied_a=n.supplied, supplied_b=m.supplied))
    bc = {c.id: c for c in b.clients}
    for c in a.clients:
        d = bc[c.id]
        rows.append(CompareRow(kind="cliente", id=c.id, name=c.name, a=c.pressure, b=d.pressure,
                               diff=diff(c.pressure, d.pressure), supplied_a=c.supplied, supplied_b=d.supplied))
    return CompareResult(a=a, b=b, rows=rows)


__all__ = ["closed_set", "compare", "run_model", "simulate_scenario", "supplied_nodes"]
