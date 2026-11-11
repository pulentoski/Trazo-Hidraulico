"""Capacidad remanente de la red: cuántos clientes nuevos de consumo típico caben manteniendo la presión mínima.

Se agregan clientes de forma incremental en el nudo de consumo con más margen de presión (simulación completa de
24 h con OWA-EPANET en cada paso). El paso empieza en `STEP0` clientes y se reduce a la mitad cada vez que una
prueba viola la presión mínima, hasta un cliente: el resultado es el máximo exacto para esa secuencia de nudos.
Un nudo que ya estaba bajo la presión mínima en el modelo no puede empeorar más de `TOL_M`.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.hydraulic.engine import run_model
from app.schemas.gestion import CapacityResult, CapacityStep
from app.schemas.network import NetworkModel

STEP0 = 16
TOL_M = 0.5
MAX_SIMULATIONS = 120


@dataclass
class _Eval:
    ok: bool
    min_p: dict[str, float]
    worst_node: str
    worst_margin: float
    max_headloss_link: str | None


class CapacityError(ValueError):
    pass


def _run(model: NetworkModel, adds: dict[str, int], q_lps: float, consumers: list[str],
         thresholds: dict[str, float] | None) -> _Eval:
    m = model.model_copy(deep=True)
    by_id = {n.id: n for n in m.network.nodes()}
    for nid, k in adds.items():
        if k:
            by_id[nid].properties.base_demand = (by_id[nid].properties.base_demand or 0.0) + k * q_lps
    run = run_model(m)
    res = run.results
    if res is None:
        raise CapacityError("El motor no entregó resultados para la red (revise los mensajes de la simulación).")
    idx = {nid: i for i, nid in enumerate(res.node_ids)}
    p = res.nodes["pressure"]
    min_p = {n: float(np.min(p[:, idx[n]])) for n in consumers if n in idx}
    th = thresholds or {}
    margins = {n: v - th.get(n, -1e9) for n, v in min_p.items()}
    worst = min(margins, key=lambda n: margins[n])
    hl_link = None
    if "headloss" in res.links and res.links["headloss"].size:
        kinds = {lk.id: lk.properties.kind for lk in model.network.links()}
        hl = np.max(np.abs(res.links["headloss"]), axis=0)
        cands = [(float(hl[j]), lid) for j, lid in enumerate(res.link_ids) if kinds.get(lid) == "pipe"]
        if cands:
            hl_link = max(cands)[1]
    return _Eval(ok=margins[worst] >= 0, min_p=min_p, worst_node=worst, worst_margin=margins[worst], max_headloss_link=hl_link)


def compute(model: NetworkModel, *, q_lps: float, m3_month: float, pmin: float, cap: int, version: int,
            consumers: list[str] | None = None) -> CapacityResult:
    """Capacidad remanente. `consumers`: nudos donde se pueden conectar clientes (por defecto, los nudos de consumo
    con clientes o demanda base)."""
    if q_lps <= 0:
        raise CapacityError("El consumo típico de un cliente debe ser mayor que cero.")
    nodes = {n.id: n for n in model.network.nodes()}
    if consumers is None:
        with_clients = {c.properties.node for c in model.network.clients()}
        consumers = [n.id for n in nodes.values() if n.properties.kind == "junction"
                     and (n.id in with_clients or (n.properties.base_demand or 0) > 0)]
    if not consumers:
        raise CapacityError("La red no tiene nudos de consumo donde agregar clientes.")
    base = _run(model, {}, q_lps, consumers, None)
    thresholds = {n: min(pmin, v - TOL_M) for n, v in base.min_p.items()}
    cur = base  # mismas presiones; los márgenes se miden contra los umbrales por nudo
    sims = 1
    adds: dict[str, int] = {n: 0 for n in consumers}
    count, step = 0, STEP0
    steps: list[CapacityStep] = []
    bottleneck: tuple[str, str | None, float] | None = None
    limited = False
    while step >= 1 and sims < MAX_SIMULATIONS:
        if count >= cap:
            limited = True
            break
        k = min(step, cap - count)
        margins = {n: cur.min_p[n] - thresholds[n] for n in consumers}
        target = max(consumers, key=lambda n: (margins[n], n))
        trial = dict(adds)
        trial[target] += k
        ev = _run(model, trial, q_lps, consumers, thresholds)
        sims += 1
        if ev.ok:
            adds, cur, count = trial, ev, count + k
            steps.append(CapacityStep(clients=count, node=target, min_pressure=round(min(ev.min_p.values()), 3),
                                      min_node=min(ev.min_p, key=lambda n: ev.min_p[n])))
        else:
            if bottleneck is None:
                bottleneck = (ev.worst_node, ev.max_headloss_link, ev.min_p[ev.worst_node])
            step //= 2
    if bottleneck is None and not limited and sims >= MAX_SIMULATIONS:
        limited = True
    note = ("Clientes agregados uno a uno (en pasos que se reducen a la mitad) en el nudo de consumo con más margen de "
            f"presión; simulación de período extendido completa en cada paso ({sims} simulaciones). "
            f"Un nudo que ya estaba bajo {pmin:g} m no puede bajar más de {TOL_M:g} m.")
    if limited:
        note += f" Se alcanzó el tope de {cap} clientes sin violar la presión mínima."
    return CapacityResult(model_version=version, typical_lps=round(q_lps, 5), typical_m3_month=round(m3_month, 3), pmin=pmin,
                          capacity=count, limited_by_cap=limited,
                          bottleneck_node=bottleneck[0] if bottleneck else None,
                          bottleneck_link=bottleneck[1] if bottleneck else None,
                          bottleneck_pressure=round(bottleneck[2], 3) if bottleneck else None, simulations=sims,
                          by_node={n: v for n, v in sorted(adds.items(), key=lambda kv: -kv[1]) if v}, steps=steps, note=note)


# ── Caché por versión del modelo y parámetros ──

_CACHE: dict[tuple, CapacityResult] = {}


def for_project(session, project, settings) -> CapacityResult:
    from app.services import design
    from app.services.network import get_version_or_404, load_model
    from app.services.simulation import validation_for
    from app.services.errors import SimulationBlockedError

    version = get_version_or_404(session, project, None)
    model = load_model(session, version)
    report = validation_for(session, project, model)
    if not report.ok:
        raise SimulationBlockedError(version.number, report)
    pmin = float(design.param(design.effective(session, project), "pressure_min").value)
    m3 = settings.typical_client_m3_month
    if m3 is None:
        res = [c.properties.consumption_lps for c in model.network.clients()
               if c.properties.status == "activo" and c.properties.client_type == "residencial"]
        m3 = (sum(res) / len(res) * 30 * 86.4) if res else 15.0
    q = m3 / (30 * 86.4)
    key = (str(project.id), version.content_sha256, round(q, 8), pmin, settings.capacity_max_clients)
    if key not in _CACHE:
        if len(_CACHE) > 64:
            _CACHE.clear()
        _CACHE[key] = compute(model, q_lps=q, m3_month=m3, pmin=pmin, cap=settings.capacity_max_clients,
                              version=version.number)
    return _CACHE[key]
