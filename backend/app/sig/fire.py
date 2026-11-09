"""Escenario de incendio por grifo: presión residual con el caudal de incendio y caudal disponible.

Para cada grifo se agrega el caudal de incendio como demanda en su nudo y se simula el modelo completo
(se toma la presión mínima del periodo en ese nudo). El caudal disponible es el mayor caudal adicional con
el que la presión mínima del nudo no baja de la presión residual exigida (búsqueda por bisección).
"""
from __future__ import annotations

from app.hydraulic.engine import run_model
from app.schemas.network import DemandCategory, NetworkModel
from app.schemas.sig import HydrantResult

MAX_FLOW_LPS = 200.0
ITERATIONS = 12
FIRE_PATTERN = "INCENDIO_TRAZO"


def _min_pressure(model: NetworkModel, node: str, extra_lps: float) -> float | None:
    m = model.model_copy(deep=True)
    if extra_lps > 0:
        # Demanda de incendio constante (sin modulación): patrón propio de factor 1.
        pat = m.aux.get("patterns", "")
        m.aux["patterns"] = (pat.rstrip("\n") + "\n" if pat.strip() else "") + f" {FIRE_PATTERN}\t1\n"
        for n in m.network.nodes():
            if n.id == node:
                n.properties.demands = [*n.properties.demands,
                                        DemandCategory(base=extra_lps, pattern=FIRE_PATTERN, name="incendio")]
                break
    run = run_model(m)
    if run.results is None or node not in run.results.node_ids:
        return None
    i = run.results.node_ids.index(node)
    return float(run.results.nodes["pressure"][:, i].min())


def assess(model: NetworkModel, ids: set[str] | None = None) -> list[HydrantResult]:
    out = []
    for h in model.network.hydrants():
        if ids and h.id not in ids:
            continue
        p = h.properties
        static = _min_pressure(model, p.node, 0.0)
        if static is None:
            out.append(HydrantResult(id=h.id, node=p.node, fire_flow_lps=p.fire_flow_lps,
                                     min_pressure_m=p.min_pressure_m, message="El motor no entregó resultados."))
            continue
        residual = _min_pressure(model, p.node, p.fire_flow_lps)
        if static < p.min_pressure_m:
            available = 0.0
        else:
            lo, hi = 0.0, MAX_FLOW_LPS
            hp = _min_pressure(model, p.node, hi)
            if hp is not None and hp >= p.min_pressure_m:
                lo = hi
            else:
                for _ in range(ITERATIONS):
                    mid = (lo + hi) / 2
                    pm = _min_pressure(model, p.node, mid)
                    if pm is not None and pm >= p.min_pressure_m:
                        lo = mid
                    else:
                        hi = mid
            available = lo
        ok = residual is not None and residual >= p.min_pressure_m
        msg = (f"Cumple: {p.fire_flow_lps:g} L/s con {residual:.1f} m de presión residual." if ok else
               f"No cumple: con {p.fire_flow_lps:g} L/s la presión baja a "
               f"{residual:.1f} m (mínimo {p.min_pressure_m:g} m)." if residual is not None else "Sin resultado.")
        out.append(HydrantResult(id=h.id, node=p.node, fire_flow_lps=p.fire_flow_lps, min_pressure_m=p.min_pressure_m,
                                 static_pressure_m=round(static, 3),
                                 residual_pressure_m=round(residual, 3) if residual is not None else None,
                                 available_flow_lps=round(available, 2), ok=ok, message=msg))
    return out
