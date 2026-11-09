"""Diagnóstico automático de una simulación: reglas sobre los resultados de EPANET, redactadas en español simple.

Cada afirmación lleva referencias al elemento y al dato. Las sugerencias (aumentar el DN del tramo causante al
siguiente del catálogo, cambiar el horario de la bomba o agregar control por nivel) se verifican con una
simulación del modelo modificado antes de proponerlas; si no resuelven el problema se informa así.
Sin IA externa.
"""
from __future__ import annotations

import heapq
from collections import defaultdict

from sqlalchemy.orm import Session

from app.hydraulic.engine import run_model
from app.models import Project
from app.repositories import catalog as catalog_repo
from app.schemas.diagnosis import DiagItem, DiagnosisResult, Ref, Suggestion
from app.schemas.network import LevelControl, NetworkModel
from app.schemas.simulation import SimulationResult
from app.services import design
from app.services.criteria import peak_period
from app.services.network import get_version_or_404, load_model
from app.services.simulation import simulate_version
from app.sig.tables import fmt_schedule

MAX_UPGRADE_STEPS = 6


def _f(x: float | None, nd: int = 1) -> str:
    return "—" if x is None else f"{x:,.{nd}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _hh(t: int) -> str:
    return f"{t // 3600:02d}:{(t % 3600) // 60:02d}"


def _join(xs: list[str]) -> str:
    return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " y " + xs[-1]


class _Ctx:
    def __init__(self, model: NetworkModel, res: SimulationResult, criteria: dict, catalog):
        self.model, self.res, self.catalog = model, res, catalog
        c = criteria
        self.pmin = (c.get("pressure_min") or {}).get("min")
        self.pmax = (c.get("pressure_max") or {}).get("max")
        self.vmax = (c.get("velocity_max") or {}).get("max")
        self.hmax = (c.get("unit_headloss_max") or {}).get("max")
        self.times = res.times
        self.eps = len(res.times) > 1
        self.peak = peak_period(model, res.times, res.nodes) if self.eps else 0
        self.nodes = {n.id: n for n in model.network.nodes()}
        self.links = {lk.id: lk for lk in model.network.links()}

    def when(self, k: int) -> str:
        return f"a las {_hh(self.times[k])}" if self.eps else "en régimen permanente"

    def next_dn(self, lk):
        p = lk.properties
        same = sorted((c for c in self.catalog if c.material == p.material and c.pipe_class == p.pipe_class
                       and p.dn is not None and c.dn > p.dn), key=lambda c: c.dn)
        return same[0] if same else None


def _path_to_source(ctx: _Ctx, node: str) -> list[str]:
    """Tramos del camino más corto (por largo) entre el nudo y la fuente más cercana."""
    adj = defaultdict(list)
    for lk in ctx.model.network.links():
        p = lk.properties
        w = p.length_hydraulic_m or 1.0
        adj[p.from_node].append((p.to_node, lk.id, w))
        adj[p.to_node].append((p.from_node, lk.id, w))
    sources = {n for n, f in ctx.nodes.items() if f.properties.kind in ("tank", "reservoir")}
    dist, prev, pq = {node: 0.0}, {}, [(0.0, node)]
    while pq:
        d, u = heapq.heappop(pq)
        if u in sources:
            path = []
            while u != node:
                u, lid = prev[u]
                path.append(lid)
            return path
        if d > dist.get(u, float("inf")):
            continue
        for v, lid, w in adj[u]:
            if d + w < dist.get(v, float("inf")):
                dist[v] = d + w
                prev[v] = (u, lid)
                heapq.heappush(pq, (d + w, v))
    return []


def _run(model: NetworkModel):
    run = run_model(model)
    return run.results


def _node_series(results, nid: str, field: str = "pressure"):
    if results is None or nid not in results.node_ids:
        return None
    return [float(x) for x in results.nodes[field][:, results.node_ids.index(nid)]]


def _link_series(results, lid: str, field: str):
    if results is None or lid not in results.link_ids:
        return None
    return [float(x) for x in results.links[field][:, results.link_ids.index(lid)]]


def _apply_dn(model: NetworkModel, link_id: str, item, formula: str) -> None:
    for lk in model.network.links():
        if lk.id == link_id:
            p = lk.properties
            p.dn, p.inner_diameter_mm, p.catalog_pipe_id, p.inner_diameter_source = item.dn, item.inner_diameter_mm, item.id, "catalogo"
            p.roughness = {"D-W": item.dw_roughness_mm, "C-M": item.manning_n}.get(formula, item.hw_c)


def _pressure_rules(ctx: _Ctx, items: list[DiagItem], suggestions: list[Suggestion]) -> None:
    if ctx.pmin is None:
        return
    k = ctx.peak
    low = []
    for nid, n in ctx.nodes.items():
        if n.properties.kind != "junction" or nid not in ctx.res.nodes:
            continue
        s = ctx.res.nodes[nid].pressure
        val = s[k] if ctx.eps else min(s)
        if val < ctx.pmin:
            low.append((val, nid))
    if not low:
        items.append(DiagItem(section="presion", severity="ok",
                              text=f"Todas las presiones {('en la hora punta (' + _hh(ctx.times[k]) + ')') if ctx.eps else ''} "
                                   f"cumplen el mínimo de {_f(ctx.pmin, 0)} m.".replace("  ", " "),
                              data={"presion_minima_m": ctx.pmin}))
        return
    low.sort()
    worst_v, worst = low[0]
    names = [f"{n} ({_f(v)} m)" for v, n in low[:6]]
    path = _path_to_source(ctx, worst)
    cause = None
    if path:
        def loss(lid):
            lk = ctx.links[lid]
            if lk.properties.kind != "pipe" or lid not in ctx.res.links:
                return -1.0
            return abs(ctx.res.links[lid].headloss[k]) * (lk.properties.length_hydraulic_m or 0) / 1000
        cause = max(path, key=loss)
    text = (f"{'En la hora punta (' + _hh(ctx.times[k]) + ')' if ctx.eps else 'En régimen permanente'}, "
            f"{len(low)} {'nudo queda' if len(low) == 1 else 'nudos quedan'} bajo la presión mínima de "
            f"{_f(ctx.pmin, 0)} m: {_join(names)}{'…' if len(low) > 6 else ''}.")
    refs = [Ref(type="node", id=n) for _v, n in low[:6]]
    if cause:
        cl = ctx.links[cause]
        unit = abs(ctx.res.links[cause].headloss[k])
        text += (f" En el camino desde la fuente, la mayor pérdida está en el tramo {cause} "
                 f"(DN {cl.properties.dn or '—'}, {_f(unit)} m/km).")
        refs.append(Ref(type="link", id=cause))
    items.append(DiagItem(section="presion", severity="problem", text=text, refs=refs,
                          data={"nudo": worst, "presion_m": round(worst_v, 3), "minimo_m": ctx.pmin,
                                "hora": _hh(ctx.times[k]) if ctx.eps else None}))
    # Sugerencia verificada: aumentar, paso a paso, el DN del tramo con más pérdida del camino al siguiente del
    # catálogo, simulando cada vez, hasta que todos los nudos afectados cumplan (máximo MAX_UPGRADE_STEPS pasos).
    if not path:
        return
    trial = ctx.model.model_copy(deep=True)
    original = {lid: ctx.links[lid].properties.dn for lid in path}
    final: dict[str, int] = {}
    res = None
    for _ in range(MAX_UPGRADE_STEPS):
        tlinks = {lk.id: lk for lk in trial.network.links()}

        def loss_now(lid):
            lk = tlinks[lid]
            if lk.properties.kind != "pipe":
                return -1.0
            if res is None:
                return abs(ctx.res.links[lid].headloss[k]) * (lk.properties.length_hydraulic_m or 0) if lid in ctx.res.links else 0
            hl = _link_series(res, lid, "headloss")
            return abs(hl[k if ctx.eps else 0]) * (lk.properties.length_hydraulic_m or 0) if hl else 0
        options = [lid for lid in sorted(path, key=loss_now, reverse=True)
                   if tlinks[lid].properties.kind == "pipe" and ctx.next_dn(tlinks[lid]) is not None]
        if not options:
            break
        lid = options[0]
        item = ctx.next_dn(tlinks[lid])
        _apply_dn(trial, lid, item, ctx.model.options.headloss)
        final[lid] = item.dn
        res = _run(trial)
        after = _node_series(res, worst)
        if after is None:
            break
        new_v = after[k] if ctx.eps else min(after)
        all_ok = all((_node_series(res, n) or [0])[k if ctx.eps else 0] >= ctx.pmin for _v, n in low)
        if new_v >= ctx.pmin and all_ok:
            what = _join([f"{lid} de DN {original[lid]} a DN {dn}" for lid, dn in final.items()])
            suggestions.append(Suggestion(
                kind="upgrade_dn", verified=True,
                text=f"Aumentar el diámetro del tramo {what} (diámetros del catálogo).",
                verification=f"Verificado con una simulación: la presión de {worst} {ctx.when(k)} sube de "
                             f"{_f(worst_v)} a {_f(new_v)} m y todos los nudos afectados cumplen el mínimo.",
                refs=[Ref(type="link", id=lid) for lid in final] + [Ref(type="node", id=worst)],
                action={"links": [{"link": lid, "dn_from": original[lid], "dn_to": dn} for lid, dn in final.items()]}))
            return
    if final:
        items.append(DiagItem(section="sugerencia", severity="warning",
                              text=f"Aumentar el DN de {_join(list(final))} (hasta {MAX_UPGRADE_STEPS} pasos del catálogo) no "
                                   "basta (verificado): revise la cota del estanque, la fuente o una matriz paralela.",
                              refs=[Ref(type="link", id=lid) for lid in final]))


def _link_rules(ctx: _Ctx, items: list[DiagItem], suggestions: list[Suggestion]) -> None:
    fast, bottleneck = [], []
    for lid, lk in ctx.links.items():
        if lk.properties.kind != "pipe" or lid not in ctx.res.links:
            continue
        s = ctx.res.links[lid]
        kv = max(range(len(s.velocity)), key=lambda i: abs(s.velocity[i]))
        if ctx.vmax is not None and abs(s.velocity[kv]) > ctx.vmax:
            fast.append((abs(s.velocity[kv]), lid, kv))
        kh = max(range(len(s.headloss)), key=lambda i: abs(s.headloss[i]))
        if ctx.hmax is not None and abs(s.headloss[kh]) > ctx.hmax:
            bottleneck.append((abs(s.headloss[kh]), lid, kh))
    for title, lst, unit, lim, sec in (("Velocidad alta", fast, "m/s", ctx.vmax, "velocidad"),
                                       ("Cuello de botella", bottleneck, "m/km", ctx.hmax, "cuello")):
        if not lst:
            continue
        lst.sort(reverse=True)
        names = [f"{lid} ({_f(v, 2)} {unit} {ctx.when(k)})" for v, lid, k in lst[:6]]
        items.append(DiagItem(section=sec, severity="warning",
                              text=f"{title} en {len(lst)} {'tramo' if len(lst) == 1 else 'tramos'} (límite {_f(lim, 1)} "
                                   f"{unit}): {_join(names)}.", refs=[Ref(type="link", id=lid) for _v, lid, _k in lst[:6]],
                              data={"tramo": lst[0][1], "valor": round(lst[0][0], 3), "limite": lim}))
    for v, lid, k in sorted(fast, reverse=True)[:2]:
        item = ctx.next_dn(ctx.links[lid])
        if item is None:
            continue
        trial = ctx.model.model_copy(deep=True)
        _apply_dn(trial, lid, item, ctx.model.options.headloss)
        after = _link_series(_run(trial), lid, "velocity")
        if after and max(abs(x) for x in after) <= ctx.vmax:
            suggestions.append(Suggestion(
                kind="upgrade_dn", verified=True,
                text=f"Cambiar el tramo {lid} de DN {ctx.links[lid].properties.dn} a DN {item.dn}.",
                verification=f"Verificado: la velocidad máxima baja de {_f(v, 2)} a {_f(max(abs(x) for x in after), 2)} m/s.",
                refs=[Ref(type="link", id=lid)],
                action={"links": [{"link": lid, "dn_from": ctx.links[lid].properties.dn, "dn_to": item.dn}]}))


def _tank_rules(ctx: _Ctx, items: list[DiagItem], suggestions: list[Suggestion]) -> None:
    if not ctx.eps:
        return
    for tid, t in ctx.nodes.items():
        p = t.properties
        if p.kind != "tank" or tid not in ctx.res.nodes:
            continue
        lv = ctx.res.nodes[tid].pressure
        inflow = ctx.res.nodes[tid].demand
        full = [k for k in range(len(lv)) if p.max_level is not None
                and max(lv[k], _projected(p, lv, inflow, ctx.times, k)) >= p.max_level - 1e-3]
        empty = [k for k in range(len(lv)) if p.min_level is not None and lv[k] <= p.min_level + 1e-3]
        text = (f"Estanque {tid}: el nivel varía entre {_f(min(lv), 2)} m ({_hh(ctx.times[lv.index(min(lv))])}) y "
                f"{_f(max(lv), 2)} m ({_hh(ctx.times[lv.index(max(lv))])}) en {_f(ctx.times[-1] / 3600, 0)} h")
        if p.max_level is not None:
            text += f"; nivel máximo {_f(p.max_level, 2)} m"
        sev = "ok"
        if full:
            sev = "warning"
            text += (f". Se llena (rebalse) cerca de las {_join([_hh(ctx.times[k]) for k in full[:4]])}: EPANET corta la "
                     "entrada y el agua bombeada en exceso rebalsaría")
        if empty:
            sev = "problem"
            text += f". Queda vacío o bajo el mínimo a las {_join([_hh(ctx.times[k]) for k in empty[:4]])}: no entrega agua"
        final = lv[-1] - lv[0]
        text += (f". Al final del día el nivel {'sube' if final > 0 else 'baja'} {_f(abs(final), 2)} m respecto del "
                 f"inicial{' (el ciclo no se repite igual al día siguiente)' if abs(final) > 0.3 else ''}.")
        items.append(DiagItem(section="estanque", severity=sev, text=text, refs=[Ref(type="node", id=tid)],
                              data={"nivel_min_m": round(min(lv), 3), "nivel_max_m": round(max(lv), 3),
                                    "horas_rebalse": [_hh(ctx.times[k]) for k in full],
                                    "horas_vacio": [_hh(ctx.times[k]) for k in empty]}))
        if full or empty:
            _pump_suggestion(ctx, tid, full, empty, suggestions)


def _projected(p, lv, inflow, times, k):
    import math

    if not p.tank_diameter or k + 1 >= len(times):
        return lv[k]
    area = math.pi * p.tank_diameter ** 2 / 4
    return lv[k] + inflow[k] / 1000 * (times[k + 1] - times[k]) / area


def _tank_ok(results, tid, p, times) -> tuple[bool, list[float]]:
    lv = _node_series(results, tid)
    inflow = _node_series(results, tid, "demand")
    if lv is None:
        return False, []
    full = any(_projected(p, lv, inflow, times, k) >= p.max_level - 1e-3 for k in range(len(lv) - 1)) \
        if p.max_level is not None else False
    empty = any(v <= (p.min_level or 0) + 1e-3 for v in lv)
    return not full and not empty, lv


def _pump_suggestion(ctx: _Ctx, tid: str, full: list[int], empty: list[int], suggestions: list[Suggestion]) -> None:
    pumps = [lk for lk in ctx.model.network.links() if lk.properties.kind == "pump"]
    if not pumps:
        return
    pump = pumps[0]
    tank = ctx.nodes[tid].properties
    sched = pump.properties.schedule
    if sched:
        trial_sched = list(sched)
        for _ in range(6):
            if full:
                hour = (ctx.times[full[0]] // 3600) % 24
                on = [h for h in range(int(hour), -1, -1) if trial_sched[h]]
                if not on:
                    break
                trial_sched[on[0]] = 0
            else:
                hour = (ctx.times[empty[0]] // 3600) % 24
                off = [h for h in range(int(hour), -1, -1) if not trial_sched[h]]
                if not off:
                    break
                trial_sched[off[0]] = 1
            trial = ctx.model.model_copy(deep=True)
            for lk in trial.network.links():
                if lk.id == pump.id:
                    lk.properties.schedule = trial_sched
            ok, lv = _tank_ok(_run(trial), tid, tank, ctx.times)
            if ok:
                suggestions.append(Suggestion(
                    kind="pump_schedule", verified=True,
                    text=f"Cambiar el horario de la bomba {pump.id} a «{fmt_schedule(trial_sched)}» "
                         f"(antes «{fmt_schedule(sched)}», {sum(trial_sched)} h de bombeo).",
                    verification=f"Verificado: el estanque {tid} queda entre {_f(min(lv), 2)} y {_f(max(lv), 2)} m, "
                                 "sin rebalse ni vaciado.",
                    refs=[Ref(type="link", id=pump.id), Ref(type="node", id=tid)],
                    action={"pump": pump.id, "schedule": trial_sched}))
                return
    if tank.max_level is not None:
        off = round(tank.max_level - 0.2, 2)
        on = round(max((tank.min_level or 0) + 0.5, tank.max_level * 0.45), 2)
        trial = ctx.model.model_copy(deep=True)
        for lk in trial.network.links():
            if lk.id == pump.id:
                lk.properties.level_control = LevelControl(tank=tid, on_below=on, off_above=off)
        ok, lv = _tank_ok(_run(trial), tid, tank, ctx.times)
        if ok:
            suggestions.append(Suggestion(
                kind="level_control", verified=True,
                text=f"Agregar control por nivel a la bomba {pump.id}: enciende bajo {_f(on, 2)} m y apaga sobre "
                     f"{_f(off, 2)} m en el estanque {tid}.",
                verification=f"Verificado: el estanque {tid} queda entre {_f(min(lv), 2)} y {_f(max(lv), 2)} m.",
                refs=[Ref(type="link", id=pump.id), Ref(type="node", id=tid)],
                action={"pump": pump.id, "level_control": {"tank": tid, "on_below": on, "off_above": off}}))


def _pump_rules(ctx: _Ctx, items: list[DiagItem]) -> None:
    for alert in ctx.res.alerts:
        if alert.code == "PUMP_OFF_CURVE":
            items.append(DiagItem(section="bomba", severity="problem", text=alert.message + " Revise su curva o el "
                                  "punto de operación (altura de la fuente y del estanque).",
                                  refs=[Ref(type="link", id=alert.element_id)], data={"caudal_lps": alert.value}))
    if not ctx.eps:
        return
    for lid, lk in ctx.links.items():
        if lk.properties.kind != "pump" or lid not in ctx.res.links:
            continue
        q = ctx.res.links[lid].flow
        on = [k for k, v in enumerate(q[:-1]) if abs(v) > 1e-6]
        if on:
            hours = len(on) * (ctx.times[1] - ctx.times[0]) / 3600
            avg = sum(q[k] for k in on) / len(on)
            items.append(DiagItem(section="bomba", severity="ok",
                                  text=f"La bomba {lid} funciona {_f(hours, 0)} h con un caudal medio de {_f(avg, 2)} L/s "
                                       f"({_f(avg * hours * 3.6, 0)} m³ en el día).",
                                  refs=[Ref(type="link", id=lid)], data={"horas": hours, "caudal_medio_lps": round(avg, 3)}))


def diagnose(session: Session, project: Project, number: int | None) -> DiagnosisResult:
    version = get_version_or_404(session, project, number)
    model = load_model(session, version)
    res = simulate_version(session, project, version.number)
    criteria = design.criteria_for(session, project)
    ctx = _Ctx(model, res, criteria, catalog_repo.list_pipes(session))
    items: list[DiagItem] = []
    suggestions: list[Suggestion] = []
    engine_errors = [m for m in res.messages if m.severity == "error"]
    for m in engine_errors:
        items.append(DiagItem(section="general", severity="problem", text=m.message))
    _pressure_rules(ctx, items, suggestions)
    _link_rules(ctx, items, suggestions)
    _tank_rules(ctx, items, suggestions)
    _pump_rules(ctx, items)
    problems = [i for i in items if i.severity == "problem"]
    warnings = [i for i in items if i.severity == "warning"]
    ok = not problems
    status = "cumple" if ok and not warnings else "cumple con observaciones" if ok else "no cumple"
    head = {"cumple": "La red cumple los criterios de diseño configurados.",
            "cumple con observaciones": f"La red cumple los criterios de presión, con {len(warnings)} "
                                        f"{'observación' if len(warnings) == 1 else 'observaciones'}.",
            "no cumple": f"La red no cumple: {len(problems)} {'problema' if len(problems) == 1 else 'problemas'}"
                         f"{f' y {len(warnings)} observaciones' if warnings else ''}."}[status]
    if ctx.eps:
        head += f" Simulación de {_f(res.times[-1] / 3600, 0)} h; hora punta {_hh(res.times[ctx.peak])}."
    summary = DiagItem(section="general", severity="ok" if ok else "problem", text=head,
                       data={"version": version.number, "pmin": ctx.pmin})
    return DiagnosisResult(project_id=str(project.id), model_version=version.number, run_id=str(res.run_id),
                           status=status, summary=summary, items=items, suggestions=suggestions,
                           criteria={k: v for k, v in (("presion_minima_m", ctx.pmin), ("presion_maxima_m", ctx.pmax),
                                                        ("velocidad_maxima_ms", ctx.vmax),
                                                        ("perdida_maxima_m_km", ctx.hmax)) if v is not None})
