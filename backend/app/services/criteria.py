"""Alertas de criterios de diseño a partir de los resultados (perfil 'no verificado' por defecto)."""
from app.schemas.network import NetworkModel
from app.schemas.simulation import CriteriaAlert, LinkSeries, NodeSeries


def _fmt(x: float, nd: int = 2) -> str:
    return f"{x:.{nd}f}".replace(".", ",")


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

    for n in model.network.nodes():
        if n.properties.kind != "junction" or n.id not in nodes:
            continue
        series = nodes[n.id].pressure
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
