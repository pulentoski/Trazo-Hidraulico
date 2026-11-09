"""Alertas de criterios de diseño a partir de los resultados (perfil 'no verificado' por defecto)."""
import math

from app.schemas.network import NetworkModel
from app.schemas.simulation import CriteriaAlert, LinkSeries, NodeSeries


def _fmt(x: float, nd: int = 2) -> str:
    return f"{x:.{nd}f}".replace(".", ",")


def _hhmm(t: int) -> str:
    return f"{t // 3600:02d}:{(t % 3600) // 60:02d}"


def peak_period(model: NetworkModel, times: list[int], nodes: dict[str, NodeSeries]) -> int:
    """Periodo de mayor demanda total de los nudos de consumo (hora punta)."""
    ids = [n.id for n in model.network.nodes() if n.properties.kind == "junction" and n.id in nodes]
    totals = [sum(max(0.0, nodes[i].demand[k]) for i in ids) for k in range(len(times))]
    return max(range(len(times)), key=lambda k: totals[k]) if totals else 0


def criteria_map(criteria: list[dict] | None) -> dict[str, dict]:
    return {c["key"]: c for c in (criteria or [])}


def criteria_alerts(model: NetworkModel, times: list[int], nodes: dict[str, NodeSeries],
                    links: dict[str, LinkSeries], criteria: dict[str, dict]) -> list[CriteriaAlert]:
    alerts: list[CriteriaAlert] = []
    if not times:
        return alerts
    pmin = (criteria.get("pressure_min") or {}).get("min")
    pmax = (criteria.get("pressure_max") or {}).get("max")
    vmin = (criteria.get("velocity_min") or {}).get("min")
    vmax = (criteria.get("velocity_max") or {}).get("max")
    hmax = (criteria.get("unit_headloss_max") or {}).get("max")

    eps = len(times) > 1
    peak = peak_period(model, times, nodes) if eps else 0
    for n in model.network.nodes():
        if n.properties.kind != "junction" or n.id not in nodes:
            continue
        series = nodes[n.id].pressure
        if eps and pmin is not None and series[peak] < pmin:
            alerts.append(CriteriaAlert(code="PRESSURE_PEAK", element_type="node", element_id=n.id, value=series[peak],
                                        limit=pmin, unit="m", time=times[peak],
                                        message=f"Hora punta ({_hhmm(times[peak])}): presión en el nudo {n.id} de "
                                                f"{_fmt(series[peak])} m, bajo el mínimo de {_fmt(pmin, 1)} m."))
            continue
        k_lo = min(range(len(series)), key=lambda k: series[k])
        k_hi = max(range(len(series)), key=lambda k: series[k])
        if pmin is not None and series[k_lo] < pmin:
            alerts.append(CriteriaAlert(code="PRESSURE_LOW", element_type="node", element_id=n.id, value=series[k_lo],
                                        limit=pmin, unit="m", time=times[k_lo],
                                        message=f"Presión baja en el nudo {n.id}: {_fmt(series[k_lo])} m "
                                                f"(mínimo {_fmt(pmin, 1)} m)."))
        if pmax is not None and series[k_hi] > pmax:
            alerts.append(CriteriaAlert(code="PRESSURE_HIGH", element_type="node", element_id=n.id, value=series[k_hi],
                                        limit=pmax, unit="m", time=times[k_hi],
                                        message=f"Presión alta en el nudo {n.id}: {_fmt(series[k_hi])} m "
                                                f"(máximo {_fmt(pmax, 1)} m)."))

    if eps:
        alerts += operation_alerts(model, times, nodes, links)
    for lk in model.network.links():
        if lk.properties.kind != "pipe" or lk.id not in links:
            continue
        s = links[lk.id]
        absv = [abs(v) for v in s.velocity]
        k_v = max(range(len(absv)), key=lambda k: absv[k])
        absq = max(abs(q) for q in s.flow)
        if vmax is not None and absv[k_v] > vmax:
            alerts.append(CriteriaAlert(code="VELOCITY_HIGH", element_type="link", element_id=lk.id, value=absv[k_v],
                                        limit=vmax, unit="m/s", time=times[k_v],
                                        message=f"Velocidad alta en el tramo {lk.id}: {_fmt(absv[k_v])} m/s "
                                                f"(máximo {_fmt(vmax, 1)} m/s)."))
        if vmin is not None and absq > 1e-6 and absv[k_v] < vmin:
            alerts.append(CriteriaAlert(code="VELOCITY_LOW", element_type="link", element_id=lk.id, value=absv[k_v],
                                        limit=vmin, unit="m/s", time=times[k_v],
                                        message=f"Velocidad baja en el tramo {lk.id}: {_fmt(absv[k_v])} m/s "
                                                f"(mínimo {_fmt(vmin, 1)} m/s); riesgo de sedimentación."))
        absh = [abs(h) for h in s.headloss]
        k_h = max(range(len(absh)), key=lambda k: absh[k])
        if hmax is not None and absh[k_h] > hmax:
            alerts.append(CriteriaAlert(code="BOTTLENECK", element_type="link", element_id=lk.id, value=absh[k_h],
                                        limit=hmax, unit="m/km", time=times[k_h],
                                        message=f"Cuello de botella en el tramo {lk.id}: pérdida unitaria "
                                                f"{_fmt(absh[k_h])} m/km supera el criterio de {_fmt(hmax, 1)} m/km."))
    return alerts


def operation_alerts(model: NetworkModel, times: list[int], nodes: dict[str, NodeSeries],
                     links: dict[str, LinkSeries]) -> list[CriteriaAlert]:
    """Período extendido: estanques llenos (rebalse) o vacíos/bajo el mínimo y bombas fuera de su curva."""
    out: list[CriteriaAlert] = []
    for n in model.network.nodes():
        p = n.properties
        if p.kind != "tank" or n.id not in nodes:
            continue
        level = nodes[n.id].pressure  # en un estanque, presión = nivel sobre el fondo
        inflow = nodes[n.id].demand  # caudal neto que entra al estanque (L/s)
        area = math.pi * p.tank_diameter ** 2 / 4 if p.tank_diameter and not p.volume_curve else None

        def projected(k: int) -> float:
            """Nivel al final del intervalo de reporte si el caudal neto se mantiene (se llena o vacía entre
            dos reportes: EPANET corta la entrada o la salida en ese instante)."""
            if area is None or k + 1 >= len(times):
                return level[k]
            return level[k] + inflow[k] / 1000 * (times[k + 1] - times[k]) / area

        if p.max_level is not None:
            k = next((i for i, v in enumerate(level) if max(v, projected(i)) >= p.max_level - 1e-3), None)
            if k is not None:
                what = ("rebalsa" if p.can_overflow else
                        "se llena: EPANET corta la entrada (el agua excedente rebalsaría)")
                out.append(CriteriaAlert(code="TANK_OVERFLOW", element_type="node", element_id=n.id,
                                         value=max(level[k], projected(k)),
                                         limit=p.max_level, unit="m", time=times[k],
                                         message=f"El estanque {n.id} {what} desde las {_hhmm(times[k])} "
                                                 f"(nivel máximo {_fmt(p.max_level)} m): ocurre entre ese reporte "
                                                 "y el siguiente."))
        if p.min_level is not None:
            k = next((i for i, v in enumerate(level) if min(v, projected(i)) <= p.min_level + 1e-3), None)
            if k is not None:
                out.append(CriteriaAlert(code="TANK_EMPTY", element_type="node", element_id=n.id,
                                         value=min(level[k], projected(k)),
                                         limit=p.min_level, unit="m", time=times[k],
                                         message=f"El estanque {n.id} queda vacío o bajo su nivel mínimo "
                                                 f"({_fmt(p.min_level)} m) a las {_hhmm(times[k])}: no entrega agua."))
    for lk in model.network.links():
        p = lk.properties
        if p.kind != "pump" or lk.id not in links:
            continue
        s = links[lk.id]
        qmax = max((q for q, _ in p.curve_points), default=None) if p.curve_points and len(p.curve_points) > 1 else None
        for k, st in enumerate(s.status):
            beyond = qmax is not None and s.flow[k] > qmax * 1.0001
            if st in (0, 5) or beyond:
                why = ("no alcanza la altura requerida (se detiene)" if st == 0 else
                       f"opera con {_fmt(s.flow[k])} L/s, fuera del rango de su curva")
                out.append(CriteriaAlert(code="PUMP_OFF_CURVE", element_type="link", element_id=lk.id, value=s.flow[k],
                                         limit=qmax or 0.0, unit="L/s", time=times[k],
                                         message=f"La bomba {lk.id} {why} a las {_hhmm(times[k])}."))
                break
    return out
