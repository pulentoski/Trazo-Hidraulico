"""Panel general del proyecto («Resumen»): reúne clientes, red, presiones, zonas, consumo, área operacional,
pérdidas, mantenimiento, estanque y pozo, y alertas de una versión, usando la última simulación (o la de un
escenario de llaves) en la hora elegida (por defecto la hora punta)."""
from __future__ import annotations

import csv
import io
import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timezone

from shapely.geometry import mapping
import numpy as np
import shapely
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import LeakEvent, Measurement, Project, ProjectVersion
from app.schemas.network import NetworkModel
from app.schemas.summary import (DEFAULT_LIFE, AreaBlock, BalanceRow, ClientsBlock, Consumer, ConsumptionBlock,
                                 DueBlock, ElementList, Group, LeakEventIn, LeakEventOut, LifeRow, LinkEvents,
                                 LossesBlock, MaintenanceBlock, NetworkBlock, OverElevation, PipeClients, PipeLife,
                                 PlanYear, PressureBlock, ProjectionPoint, ScenarioOption, SummaryAlert, SummaryResult,
                                 SummarySettings, TankInfo, TankWellBlock, ValueAt, WellInfo, ZoneFeature, ZoneRange,
                                 ZonesBlock)
from app.services import design
from app.services import summary_calc as calc
from app.services.errors import NotFound, SimulationBlockedError
from app.services.geometry import from_metric, to_metric
from app.services.network import get_version_or_404, load_model

MODEL_SCENARIO = "modelo"
BAD = ("malo", "fuera_servicio")
AGE_BINS = [(0, 10, "< 10 años"), (10, 20, "10–20 años"), (20, 30, "20–30 años"), (30, 40, "30–40 años"),
            (40, 10_000, "≥ 40 años")]
LOSSES_HELP = ("Sin datos. Registre fugas, roturas y reparaciones por tramo (ingreso manual o planilla «Pérdidas»), "
               "y lecturas del medidor del pozo o de un macromedidor en la pestaña Mediciones (medición «medidor», "
               "m³ acumulados). El balance compara la producción con el consumo de los clientes del sector "
               "(atributo «{attr}» de clientes y tramos; sin atributo = «Total»).")


# ── Configuración y eventos ──

def settings_of(project: Project) -> SummarySettings:
    if project.summary_settings:
        try:
            return SummarySettings.model_validate(project.summary_settings)
        except ValueError:
            pass
    return SummarySettings()


def save_settings(session: Session, project: Project, body: SummarySettings) -> SummarySettings:
    project.summary_settings = body.model_dump(mode="json")
    session.commit()
    return body


def list_leaks(session: Session, project: Project) -> list[LeakEvent]:
    return list(session.scalars(select(LeakEvent).where(LeakEvent.project_id == project.id)
                                .order_by(LeakEvent.event_date.desc(), LeakEvent.id.desc())))


def leak_out(e: LeakEvent) -> LeakEventOut:
    return LeakEventOut(id=e.id, link_id=e.link_id, event_date=e.event_date, kind=e.kind, flow_lps=e.flow_lps,
                        note=e.note, created_at=e.created_at)


def add_leaks(session: Session, project: Project, items: list[LeakEventIn]) -> list[LeakEvent]:
    rows = [LeakEvent(project_id=project.id, **i.model_dump()) for i in items]
    session.add_all(rows)
    session.commit()
    for r in rows:
        session.refresh(r)
    return rows


def delete_leaks(session: Session, project: Project, ids: list[int]) -> int:
    n = 0
    for e in session.scalars(select(LeakEvent).where(LeakEvent.project_id == project.id, LeakEvent.id.in_(ids))):
        session.delete(e)
        n += 1
    session.commit()
    return n


KIND_ALIASES = {"fuga": "fuga", "rotura": "rotura", "reparacion": "reparacion", "reparación": "reparacion"}
LEAK_HEAD = ["Tramo", "Fecha", "Tipo", "Caudal estimado", "Observación"]


def leaks_template() -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font

    wb = Workbook()
    ws = wb.active
    ws.title = "Pérdidas"
    ws.append(LEAK_HEAD)
    ws.append(["ID del tramo", "AAAA-MM-DD", "fuga, rotura o reparación", "L/s (opcional)", "texto libre"])
    for c in range(1, 6):
        ws.cell(1, c).font = Font(bold=True)
        ws.cell(2, c).font = Font(italic=True, color="666666")
    ws.append(["P-06", "2026-03-14", "fuga", 0.05, "Filtración en unión"])
    for col, w in zip("ABCDE", (12, 14, 26, 16, 40)):
        ws.column_dimensions[col].width = w
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _parse_date(v) -> date | None:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = str(v or "").strip()
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s[:10], fmt).date()
        except ValueError:
            continue
    return None


def parse_leak_table(table: list[list], links: set[str] | None = None) -> tuple[list[LeakEventIn], list[str]]:
    """Filas de la hoja «Pérdidas» (encabezados en la fila 1; la fila de ayuda se omite)."""
    if not table:
        return [], ["El archivo está vacío."]
    head = [str(h or "").strip().lower() for h in table[0]]

    def col(*names: str) -> int | None:
        return next((i for i, h in enumerate(head) if any(h.startswith(n) for n in names)), None)
    ci, cd, ct, cq, cn = col("tramo"), col("fecha"), col("tipo"), col("caudal"), col("observ", "nota")
    if ci is None or cd is None or ct is None:
        return [], ["Faltan columnas: se requieren «Tramo», «Fecha» y «Tipo»."]
    items: list[LeakEventIn] = []
    errors: list[str] = []
    for n, row in enumerate(table[1:], start=2):
        cells = list(row) + [None] * 5
        if all(c in (None, "") for c in cells[:5]):
            continue
        if isinstance(cells[ci], str) and cells[ci].startswith("ID del tramo"):
            continue
        link = str(cells[ci] or "").strip()
        d = _parse_date(cells[cd])
        kind = KIND_ALIASES.get(str(cells[ct] or "").strip().lower())
        q = cells[cq] if cq is not None else None
        try:
            q = float(str(q).replace(",", ".")) if q not in (None, "") else None
        except ValueError:
            errors.append(f"Fila {n}: caudal «{q}» no es un número")
            continue
        if not link:
            errors.append(f"Fila {n}: falta el tramo")
        elif links is not None and link not in links:
            errors.append(f"Fila {n}: el tramo «{link}» no existe en el modelo")
        elif d is None:
            errors.append(f"Fila {n}: fecha «{cells[cd]}» inválida (use AAAA-MM-DD)")
        elif kind is None:
            errors.append(f"Fila {n}: tipo «{cells[ct]}» inválido (fuga, rotura o reparación)")
        else:
            note = cells[cn] if cn is not None else None
            items.append(LeakEventIn(link_id=link, event_date=d, kind=kind, flow_lps=q,
                                     note=str(note)[:300] if note not in (None, "") else None))
    return items, errors


def read_leak_file(filename: str, content: bytes, links: set[str] | None) -> tuple[list[LeakEventIn], list[str]]:
    if filename.lower().endswith(".xlsx") or content[:2] == b"PK":
        from openpyxl import load_workbook

        try:
            wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        except Exception:  # noqa: BLE001
            return [], ["El archivo no es una planilla .xlsx válida."]
        name = next((n for n in wb.sheetnames if n.lower().startswith(("pérdidas", "perdidas"))), wb.sheetnames[0])
        table = [list(r) for r in wb[name].iter_rows(values_only=True)]
        wb.close()
        return parse_leak_table(table, links)
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("latin-1")
    delim = ";" if text[:2000].count(";") >= text[:2000].count(",") else ","
    return parse_leak_table([list(r) for r in csv.reader(io.StringIO(text), delimiter=delim)], links)


# ── Hidráulica de la versión (modelo o escenario de llaves) ──

@dataclass
class Hyd:
    times: list[int]
    pressure: dict[str, list[float]]
    head: dict[str, list[float]]
    demand: dict[str, list[float]]
    flow: dict[str, list[float]]
    status: dict[str, list[int]]
    unsupplied: set[str] = field(default_factory=set)
    alerts: list = field(default_factory=list)


def scenario_options(model: NetworkModel) -> list[ScenarioOption]:
    from app.services.scenarios import BUILTIN_SCENARIOS

    out = [ScenarioOption(id=MODEL_SCENARIO, name="Modelo (última simulación)"),
           ScenarioOption(id="normal", name=BUILTIN_SCENARIOS["normal"])]
    out += [ScenarioOption(id=s.id, name=s.name) for s in model.scenarios]
    return out


def hydraulics(session: Session, project: Project, version: ProjectVersion, model: NetworkModel,
               scenario: str) -> tuple[Hyd | None, str | None]:
    from app.services.simulation import simulate_version, validation_for

    try:
        if scenario == MODEL_SCENARIO:
            r = simulate_version(session, project, version.number)
            if not r.times:
                return None, "La simulación no entregó resultados (revise los mensajes del motor)."
            return Hyd(times=r.times, pressure={k: v.pressure for k, v in r.nodes.items()},
                       head={k: v.head for k, v in r.nodes.items()}, demand={k: v.demand for k, v in r.nodes.items()},
                       flow={k: v.flow for k, v in r.links.items()}, status={k: v.status for k, v in r.links.items()},
                       alerts=r.alerts), None
        from app.services import scenarios as sc

        rep = validation_for(session, project, model)
        if not rep.ok:
            raise SimulationBlockedError(version.number, rep)
        _name, closed = sc.closed_set(model, scenario)
        supplied = sc.supplied_nodes(model, model.closed_links(closed))
        unsupplied = {n.id for n in model.network.nodes() if n.id not in supplied}
        run = sc._run(sc.without_unsupplied_demand(model, unsupplied), closed)
        res = run.results
        if res is None:
            return None, "El escenario no entregó resultados (revise los mensajes del motor)."
        nodes = {nid: i for i, nid in enumerate(res.node_ids)}
        links = {lid: j for j, lid in enumerate(res.link_ids)}
        return Hyd(times=list(res.times),
                   pressure={k: [float(v) for v in res.nodes["pressure"][:, i]] for k, i in nodes.items()},
                   head={k: [float(v) for v in res.nodes["head"][:, i]] for k, i in nodes.items()},
                   demand={k: [float(v) for v in res.nodes["demand"][:, i]] for k, i in nodes.items()},
                   flow={k: [float(v) for v in res.links["flow"][:, j]] for k, j in links.items()},
                   status={k: [int(v) for v in res.links["status"][:, j]] for k, j in links.items()},
                   unsupplied=unsupplied), None
    except SimulationBlockedError:
        return None, "La red tiene errores bloqueantes: no hay simulación (vea la pestaña Alertas)."
    except NotFound as exc:
        raise exc


def peak_period(hyd: Hyd, junctions: set[str]) -> int:
    """Hora punta: periodo de mayor demanda total de los nudos de consumo."""
    n = len(hyd.times)
    tot = [sum(hyd.demand[j][k] for j in junctions if j in hyd.demand) for k in range(n)]
    return max(range(n), key=lambda k: (tot[k], -k))


def critical_period(hyd: Hyd, junctions: set[str]) -> tuple[int, float, str] | None:
    """Hora más crítica: periodo con la menor presión en un nudo de consumo con suministro."""
    best = None
    for j in junctions:
        if j in hyd.unsupplied or j not in hyd.pressure:
            continue
        for k, p in enumerate(hyd.pressure[j]):
            if best is None or p < best[1] - 1e-12:
                best = (k, p, j)
    return best


# ── Armado del resumen ──

def _sector(attrs: dict, attr: str) -> str | None:
    for k, v in (attrs or {}).items():
        if k.strip().lower() == attr.strip().lower() and v not in (None, ""):
            return str(v)
    return None


def _natural(keys: set[str]) -> list[str]:
    """Orden natural («2» antes de «10»), con «sin …» al final."""
    import re

    def k(x: str):
        return (x.startswith("sin "), [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", x)])
    return sorted(keys, key=k)


def _groups(pairs: list[tuple[str, str]], extra: dict[str, float] | None = None, km: dict[str, float] | None = None,
            order: list[str] | None = None) -> list[Group]:
    ids: dict[str, list[str]] = defaultdict(list)
    for key, i in pairs:
        ids[key].append(i)
    keys = order or sorted(ids, key=lambda k: (str(k) == "sin dato", -len(ids[k]), str(k)))
    return [Group(key=k, count=len(ids[k]), ids=ids[k], m3_day=round(extra[k], 3) if extra and k in extra else None,
                  km=round(km[k], 4) if km and k in km else None) for k in keys if k in ids]


def build(session: Session, project: Project, number: int | None, scenario: str = MODEL_SCENARIO,
          period: int | None = None) -> SummaryResult:
    version = get_version_or_404(session, project, number)
    model = load_model(session, version)
    st = settings_of(project)
    params = design.effective(session, project)
    pmin = float(design.param(params, "pressure_min").value)
    pmax = float(design.param(params, "pressure_max").value)
    srid = project.length_srid
    tr = to_metric(srid)
    year = date.today().year

    options = scenario_options(model)
    if scenario not in {o.id for o in options}:
        raise NotFound(f"Escenario «{scenario}» no encontrado")
    nodes = {n.id: n for n in model.network.nodes()}
    links = {lk.id: lk for lk in model.network.links()}
    clients = model.network.clients()
    junctions = {i for i, n in nodes.items() if n.properties.kind == "junction"}

    # ── Clientes ──
    def el(type_, ids):
        return ElementList(type=type_, count=len(ids), ids=list(ids))
    by_status = defaultdict(list)
    for c in clients:
        by_status[c.properties.status].append(c.id)
    conn = {(round(c.properties.connection[0], 6), round(c.properties.connection[1], 6)) if c.properties.connection
            else ("c", c.id) for c in clients if c.properties.status != "proyectado"}
    active = [c for c in clients if c.properties.status == "activo"]
    m3d = {c.id: c.properties.consumption_lps * 86.4 for c in clients}
    sector_of = {c.id: _sector(c.properties.attributes, st.sector_attribute) or "sin sector" for c in clients}
    route_of = {c.id: c.properties.route or "sin ruta" for c in clients}
    route_m3 = defaultdict(float)
    sector_m3 = defaultdict(float)
    for c in active:
        route_m3[route_of[c.id]] += m3d[c.id]
        sector_m3[sector_of[c.id]] += m3d[c.id]
    clients_block = ClientsBlock(
        total=el("client", [c.id for c in clients]), active=el("client", by_status["activo"]),
        projected=el("client", by_status["proyectado"]), suspended=el("client", by_status["suspendido"]),
        connections=len(conn),
        by_route=_groups([(route_of[c.id], c.id) for c in clients], route_m3, order=_natural(set(route_of.values()))),
        by_sector=_groups([(sector_of[c.id], c.id) for c in clients], sector_m3))

    # ── Red ──
    pipes = [lk for lk in links.values() if lk.properties.kind == "pipe"]
    length = {lk.id: (lk.properties.length_hydraulic_m or lk.properties.length_plan_m or 0.0) for lk in pipes}

    def km_groups(keyf, order=None):
        pairs = [(keyf(lk), lk.id) for lk in pipes]
        km = defaultdict(float)
        for k, i in pairs:
            km[k] += length[i] / 1000
        return _groups(pairs, km=km, order=order)

    def age_key(lk):
        y = lk.properties.install_year
        if y is None:
            return "sin dato"
        a = year - y
        return next(lbl for lo, hi, lbl in AGE_BINS if lo <= a < hi)
    cond_lbl = {"bueno": "bueno", "regular": "regular", "malo": "malo", "fuera_servicio": "fuera de servicio"}
    network_block = NetworkBlock(
        km_total=round(sum(length.values()) / 1000, 4), pipes=el("link", [lk.id for lk in pipes]),
        by_material=km_groups(lambda lk: lk.properties.material or "sin dato"),
        by_dn=sorted(km_groups(lambda lk: f"DN {lk.properties.dn}" if lk.properties.dn else "sin dato"),
                     key=lambda g: (g.key == "sin dato", int(g.key[3:]) if g.key != "sin dato" else 0)),
        by_condition=km_groups(lambda lk: cond_lbl.get(lk.properties.condition or "", "sin dato"),
                               order=["bueno", "regular", "malo", "fuera de servicio", "sin dato"]),
        by_age=km_groups(age_key, order=[b[2] for b in AGE_BINS] + ["sin dato"]),
        valves=el("shutoff", [s.id for s in model.network.shutoffs()]),
        control_valves=el("link", [lk.id for lk in links.values() if lk.properties.kind == "valve"]),
        hydrants=el("hydrant", [h.id for h in model.network.hydrants()]),
        tanks=el("node", [i for i, n in nodes.items() if n.properties.kind == "tank"]),
        wells=el("well", [w.id for w in model.network.wells()]),
        pumps=el("link", [lk.id for lk in links.values() if lk.properties.kind == "pump"]))

    # ── Geometría métrica ──
    def xy(lonlat):
        return tr.transform(lonlat[0], lonlat[1])
    node_xy = {i: xy(n.geometry.coordinates) for i, n in nodes.items()}
    client_xy = {c.id: xy(c.geometry.coordinates) for c in clients}
    link_xy = {i: [xy(p) for p in lk.geometry.coordinates] for i, lk in links.items()}

    # ── Clientes por tubería (tramo del arranque; sin él, la tubería más cercana conectada a su nudo) ──
    from shapely.geometry import LineString, Point
    pipe_lines = {lk.id: LineString(link_xy[lk.id]) for lk in pipes if len(link_xy[lk.id]) >= 2}
    by_pipe: dict[str, list[str]] = defaultdict(list)
    for c in clients:
        if c.properties.status == "proyectado":
            continue
        lid = c.properties.link if c.properties.link in pipe_lines else None
        if lid is None:
            near = [i for i, lk in links.items() if i in pipe_lines and c.properties.node in
                    (lk.properties.from_node, lk.properties.to_node)] or list(pipe_lines)
            if near:
                pt = Point(client_xy[c.id])
                lid = min(near, key=lambda i: (pipe_lines[i].distance(pt), i))
        if lid:
            by_pipe[lid].append(c.id)
    clients_per_pipe = [PipeClients(link=k, clients=len(v), ids=v)
                        for k, v in sorted(by_pipe.items(), key=lambda kv: (-len(kv[1]), kv[0]))][:15]

    # ── Hidráulica ──
    hyd, note = hydraulics(session, project, version, model, scenario)
    times = hyd.times if hyd else []
    pk = peak_period(hyd, junctions) if hyd else None
    if hyd and period is not None and not (0 <= period < len(times)):
        raise NotFound(f"La hora {period} está fuera de la simulación (0–{len(times) - 1})")
    k = (period if period is not None else pk) if hyd else None
    crit = critical_period(hyd, junctions) if hyd else None

    def client_pressure(c, kk):
        n = nodes.get(c.properties.node)
        p = hyd.pressure.get(c.properties.node, [None])[kk]
        if p is None or n is None:
            return None
        if c.properties.elevation is not None and n.properties.elevation is not None:
            p += n.properties.elevation - c.properties.elevation
        return p

    supplied_j = [j for j in sorted(junctions) if hyd and j in hyd.pressure and j not in hyd.unsupplied]
    if hyd and supplied_j:
        ps = {j: hyd.pressure[j][k] for j in supplied_j}
        jmin = min(ps, key=lambda j: (ps[j], j))
        jmax = max(ps, key=lambda j: (ps[j], j))
        pressures = PressureBlock(
            pmin=pmin, pmax=pmax, min=ValueAt(value=round(ps[jmin], 3), id=jmin),
            max=ValueAt(value=round(ps[jmax], 3), id=jmax), avg=round(sum(ps.values()) / len(ps), 3),
            below_min=el("node", [j for j in supplied_j if ps[j] < pmin]),
            above_max=el("node", [j for j in supplied_j if ps[j] > pmax]),
            clients_below=el("client", [c.id for c in clients if c.properties.status != "proyectado"
                                        and c.properties.node not in hyd.unsupplied
                                        and (p := client_pressure(c, k)) is not None and p < pmin]),
            unsupplied=el("node", sorted(junctions & hyd.unsupplied)),
            critical_period=crit[0] if crit else None, critical_time=times[crit[0]] if crit else None,
            critical_value=round(crit[1], 3) if crit else None, critical_node=crit[2] if crit else None)
    else:
        empty = el("node", [])
        pressures = PressureBlock(pmin=pmin, pmax=pmax, below_min=empty, above_max=empty,
                                  clients_below=el("client", []), unsupplied=empty)

    # ── Área operacional ──
    area = calc.operational_area([link_xy[i] for i in links], [*node_xy.values(), *client_xy.values()],
                                 st.area_margin_m)
    back = from_metric(srid)

    def to_geo(g):
        if g.is_empty:
            return None
        return mapping(shapely.transform(g, lambda a: np.column_stack(back.transform(a[:, 0], a[:, 1]))))
    area_block = AreaBlock(margin_m=st.area_margin_m, area_km2=round(area.area / 1e6, 6), geometry=to_geo(area))

    # ── Zonas por presión ──
    labels = calc.range_labels(st.pressure_ranges)
    zones: list[calc.Zone] = []
    if hyd and supplied_j:
        zones = calc.pressure_zones([(j, *node_xy[j], hyd.pressure[j][k]) for j in supplied_j], area,
                                    st.pressure_ranges)
    zarea, znodes, zcl = calc.zone_totals(zones, [(c.id, *client_xy[c.id]) for c in clients
                                                  if c.properties.status != "proyectado"], len(labels))
    zones_block = ZonesBlock(
        ranges=[ZoneRange(cls=i, label=lbl, lo=lo, hi=hi, area_km2=round(zarea[i], 6), nodes=el("node", znodes[i]),
                          clients=el("client", zcl[i])) for i, (lbl, lo, hi) in enumerate(labels)],
        features=[ZoneFeature(node=z.node, pressure=round(z.pressure, 3), cls=z.cls,
                              geometry=to_geo(z.cell.simplify(0.5))) for z in zones])

    # ── Clientes sobre cota (hora crítica) ──
    over: list[OverElevation] = []
    if hyd and crit:
        kc = crit[0]
        heads = []
        info = {}
        for c in clients:
            n = nodes.get(c.properties.node)
            if (c.properties.status == "proyectado" or n is None or c.properties.node in hyd.unsupplied
                    or c.properties.node not in hyd.head):
                continue
            ground = c.properties.elevation if c.properties.elevation is not None else n.properties.elevation
            if ground is None:
                continue
            h = hyd.head[c.properties.node][kc]
            heads.append(calc.ClientHead(id=c.id, ground=ground, head=h))
            info[c.id] = (c, ground, h)
        for cid, deficit in calc.over_elevation(heads, pmin):
            c, ground, h = info[cid]
            over.append(OverElevation(client=cid, name=c.properties.name, node=c.properties.node, ground=ground,
                                      head=round(h, 3), pmin=pmin, deficit=deficit))

    # ── Mayores consumidores y consumo ──
    total_lps = sum(c.properties.consumption_lps for c in active)
    top = sorted(active, key=lambda c: (-c.properties.consumption_lps, c.id))[:st.top_n]
    top_consumers = [Consumer(client=c.id, name=c.properties.name, route=c.properties.route,
                              lps=round(c.properties.consumption_lps, 6),
                              m3_month=round(c.properties.consumption_lps * 86.4 * 30, 3),
                              pct=round(c.properties.consumption_lps / total_lps * 100, 2) if total_lps else 0.0)
                     for c in top]
    from app.services import demand as demand_svc

    inp, _saved = demand_svc.inputs_for(session, project)
    rows = demand_svc.compute(inp)
    ref = demand_svc._row_for(rows, inp.model_year).consumption_m3 or 1.0
    m3_day = total_lps * 86.4
    projection = []
    for n in (10, 20):
        r = demand_svc._row_for(rows, year + n)
        f = r.consumption_m3 / ref
        projection.append(ProjectionPoint(years=n, year=r.year, factor=round(f, 4), m3_day=round(m3_day * f, 3),
                                          m3_month=round(m3_day * f * 30, 3)))
    consumption = ConsumptionBlock(
        lps=round(total_lps, 6), m3_day=round(m3_day, 3), m3_month=round(m3_day * 30, 3),
        by_sector=_groups([(sector_of[c.id], c.id) for c in active], sector_m3),
        by_route=_groups([(route_of[c.id], c.id) for c in active], route_m3, order=_natural(set(route_of.values()))),
        projection=projection,
        projection_note=("Consumo actual de los clientes activos escalado con el crecimiento del módulo de demanda "
                         f"(año del modelo {inp.model_year}; valores «no verificado»)."))

    # ── Pérdidas y filtraciones ──
    events = list_leaks(session, project)
    per_link: dict[str, list[LeakEvent]] = defaultdict(list)
    for e in events:
        per_link[e.link_id].append(e)
    top_links = sorted((LinkEvents(link=lid, events=len(es), last_date=max(x.event_date for x in es),
                                   kinds=dict(Counter(x.kind for x in es)),
                                   flow_lps=round(sum(x.flow_lps or 0 for x in es), 4))
                        for lid, es in per_link.items()), key=lambda x: (-x.events, x.link))[:10]
    balance = _balance(session, project, model, st, sector_of, active)
    losses = LossesBlock(events=[leak_out(e) for e in events[:200]], total_events=len(events),
                         by_kind=dict(Counter(e.kind for e in events)), top_links=top_links, balance=balance,
                         has_events=bool(events), has_production=bool(balance),
                         help=LOSSES_HELP.format(attr=st.sector_attribute))

    # ── Mantenimiento a futuro ──
    ages = [calc.PipeAge(id=lk.id, material=lk.properties.material, dn=lk.properties.dn, length_m=length[lk.id],
                         install_year=lk.properties.install_year) for lk in pipes]
    prices = [(p.material, p.dn_max, p.price_m) for p in st.prices]
    life, dl = st.service_life, st.default_life
    materials = sorted({lk.properties.material for lk in pipes if lk.properties.material} | set(life))
    exp_km, exp_ids = calc.expired(ages, life, dl, year)
    plan = calc.renewal_plan(ages, life, dl, year, 20, prices)
    bad = [lk.id for lk in pipes if lk.properties.condition in BAD]
    maintenance = MaintenanceBlock(
        current_year=year,
        life=[LifeRow(material=m, years=calc.life_of(m, life, dl), suggested=DEFAULT_LIFE.get(m)) for m in materials],
        life_verified=st.life_verified, prices_verified=st.prices_verified,
        pipes=[PipeLife(link=a.id, material=a.material, dn=a.dn, length_m=round(a.length_m, 2),
                        install_year=a.install_year, expiry_year=calc.expiry_year(a, life, dl),
                        condition=links[a.id].properties.condition,
                        cost=round(a.length_m * p) if (p := calc.price_for(a.material, a.dn, prices)) is not None else None)
               for a in sorted(ages, key=lambda a: (calc.expiry_year(a, life, dl) or 9999, a.id))],
        expired=DueBlock(years=0, km=exp_km, ids=exp_ids),
        due=[DueBlock(years=h, km=(d := calc.due_within(ages, life, dl, year, h))[0], ids=d[1]) for h in (5, 10, 20)],
        bad_condition=el("link", bad), bad_condition_km=round(sum(length[i] for i in bad) / 1000, 4),
        unknown_year=el("link", [a.id for a in ages if a.install_year is None]),
        plan=[PlanYear(year=y, km=km, cost=cost, ids=ids) for y, km, cost, ids in plan],
        plan_cost=round(sum(p[2] for p in plan)))

    # ── Estanque y pozo ──
    tank_well = _tank_well(model, hyd)

    # ── Alertas ──
    alerts = _alerts(model, hyd, pressures, over, maintenance, tank_well, pmin, pmax, k, times)

    return SummaryResult(
        project_id=str(project.id), model_version=version.number, scenario=scenario, scenarios=options,
        simulated=hyd is not None, sim_note=note, times=times, period=k, peak_period=pk,
        generated_at=datetime.now(timezone.utc), settings=st, clients=clients_block, network=network_block,
        clients_per_pipe=clients_per_pipe, pressures=pressures, zones=zones_block, over_elevation=over,
        over_elevation_period=crit[0] if crit else None, top_consumers=top_consumers, consumption=consumption,
        area=area_block, losses=losses, maintenance=maintenance, tank_well=tank_well, alerts=alerts)


def _balance(session: Session, project: Project, model: NetworkModel, st: SummarySettings,
             sector_of: dict[str, str], active) -> list[BalanceRow]:
    readings: dict[tuple[str, str], list[tuple[datetime, float]]] = defaultdict(list)
    for m in session.scalars(select(Measurement).where(Measurement.project_id == project.id,
                                                       Measurement.kind == "meter",
                                                       Measurement.element_type.in_(("well", "link")))):
        readings[(m.element_type, m.element_id)].append((m.measured_at, m.value))
    if not readings:
        return []
    links = {lk.id: lk for lk in model.network.links()}
    meters: list[tuple[str, str, str]] = [(p.sector, p.element_type, p.element_id) for p in st.production_meters]
    if not meters:
        for (t, i) in sorted(readings):
            if t == "well":
                meters.append(("Total", t, i))
            elif i in links:
                meters.append((_sector(links[i].properties.attributes, st.sector_attribute) or f"Tramo {i}", t, i))
    rows: list[BalanceRow] = []
    by_sector: dict[str, list[tuple[str, tuple[float, datetime, datetime]]]] = defaultdict(list)
    for sector, t, i in meters:
        prod = calc.meter_production(readings.get((t, i), []))
        if prod:
            by_sector[sector].append((f"{'pozo' if t == 'well' else 'tramo'} {i}", prod))
    for sector, items in by_sector.items():
        members = [c for c in active if sector == "Total" or sector_of[c.id] == sector]
        cons = sum(c.properties.consumption_lps * 86.4 for c in members)
        prod = sum(p[0] for _, p in items)
        rows.append(BalanceRow(sector=sector, meters=[n for n, _ in items], period_from=min(p[1] for _, p in items),
                               period_to=max(p[2] for _, p in items), production_m3_day=round(prod, 3),
                               consumption_m3_day=round(cons, 3), nrw_m3_day=round(prod - cons, 3),
                               nrw_pct=calc.nrw_pct(prod, cons),
                               clients=ElementList(type="client", count=len(members), ids=[c.id for c in members])))
    return sorted(rows, key=lambda r: (r.sector != "Total", r.sector))


def _tank_well(model: NetworkModel, hyd: Hyd | None) -> TankWellBlock:
    nodes = {n.id: n for n in model.network.nodes()}
    links = model.network.links()
    junctions = [i for i, n in nodes.items() if n.properties.kind == "junction"]
    tanks: list[TankInfo] = []
    n_t = len(hyd.times) if hyd else 0
    step_h = ((hyd.times[1] - hyd.times[0]) / 3600) if hyd and n_t > 1 else 1.0
    span_days = (n_t * step_h) / 24 if hyd and n_t > 1 else None
    avg_demand = (sum(sum(hyd.demand[j]) / n_t for j in junctions if j in hyd.demand) if hyd and n_t else None)
    for i, n in nodes.items():
        p = n.properties
        if p.kind != "tank":
            continue
        useful = (math.pi / 4 * p.tank_diameter ** 2 * (p.max_level - p.min_level)
                  if p.tank_diameter and p.max_level is not None and p.min_level is not None else None)
        levels = hyd.pressure.get(i) if hyd else None
        aut = useful / (avg_demand * 3.6) if useful and avg_demand and avg_demand > 0 else None
        tanks.append(TankInfo(id=i, useful_m3=round(useful, 2) if useful else None,
                              outflow_lps=round(avg_demand, 4) if avg_demand is not None else None,
                              autonomy_h=round(aut, 2) if aut else None,
                              level_min=round(min(levels), 3) if levels else None,
                              level_max=round(max(levels), 3) if levels else None))
    wells: list[WellInfo] = []
    for w in model.network.wells():
        wp = w.properties
        pump = next((lk for lk in links if lk.properties.kind == "pump" and wp.node
                     and wp.node in (lk.properties.from_node, lk.properties.to_node)), None)
        hours = flow_run = m3 = None
        if hyd and pump is not None and pump.id in hyd.flow and span_days:
            q = hyd.flow[pump.id][:n_t]
            on = [abs(x) for x, s in zip(q, hyd.status.get(pump.id, [3] * n_t)) if s >= 3 and abs(x) > 1e-6]
            # Periodo final (24 h) repite la hora 0: se excluye del promedio diario.
            periods = n_t - 1 if n_t > 1 and (hyd.times[-1] - hyd.times[0]) % 86400 == 0 else n_t
            q_eff = [abs(x) if s >= 3 else 0.0 for x, s in zip(q[:periods], hyd.status.get(pump.id, [3] * n_t)[:periods])]
            days = periods * step_h / 24
            hours = sum(1 for x in q_eff if x > 1e-6) * step_h / days
            flow_run = sum(on) / len(on) if on else 0.0
            m3 = sum(q_eff) * step_h * 3.6 / days
        auth = wp.authorized_flow_lps
        auth_m3 = auth * 86.4 if auth else None
        use = (m3 / auth_m3 * 100) if m3 is not None and auth_m3 else None
        wells.append(WellInfo(id=w.id, pump=pump.id if pump else None, authorized_lps=auth,
                              pump_hours_day=round(hours, 2) if hours is not None else None,
                              flow_running_lps=round(flow_run, 3) if flow_run is not None else None,
                              m3_day=round(m3, 2) if m3 is not None else None,
                              authorized_m3_day=round(auth_m3, 2) if auth_m3 else None,
                              use_pct=round(use, 1) if use is not None else None,
                              over_authorized=bool(auth and flow_run is not None and flow_run > auth + 1e-6)))
    return TankWellBlock(tanks=tanks, wells=wells)


def _alerts(model, hyd, pr: PressureBlock, over, mt: MaintenanceBlock, tw: TankWellBlock, pmin, pmax, k, times):
    out: list[SummaryAlert] = []
    hour = f" a las {times[k] // 3600}:{(times[k] % 3600) // 60:02d} h" if hyd and k is not None and times else ""
    if hyd is None:
        out.append(SummaryAlert(severity="warning", topic="Simulación", text="Sin simulación: los bloques "
                                "hidráulicos quedan vacíos."))
    for j in pr.unsupplied.ids:
        out.append(SummaryAlert(severity="error", topic="Suministro", text=f"Nudo {j} sin suministro en el escenario",
                                type="node", id=j))
    if hyd is not None and k is not None:
        for j in pr.below_min.ids:
            out.append(SummaryAlert(severity="error", topic="Presión",
                                    text=f"Nudo {j}: {hyd.pressure[j][k]:.1f} m < mínima {pmin:g} m{hour}",
                                    type="node", id=j))
        for j in pr.above_max.ids:
            out.append(SummaryAlert(severity="warning", topic="Presión",
                                    text=f"Nudo {j}: {hyd.pressure[j][k]:.1f} m > máxima {pmax:g} m{hour}",
                                    type="node", id=j))
    for o in over:
        out.append(SummaryAlert(severity="error", topic="Clientes sobre cota",
                                text=f"Cliente {o.client}: faltan {o.deficit:.1f} m de carga en la hora crítica",
                                type="client", id=o.client))
    for w in tw.wells:
        if w.over_authorized:
            out.append(SummaryAlert(severity="error", topic="Pozo", text=f"Pozo {w.id}: caudal de bombeo "
                                    f"{w.flow_running_lps:.2f} L/s sobre el autorizado {w.authorized_lps:g} L/s",
                                    type="well", id=w.id))
    for t in tw.tanks:
        if t.level_min is not None:
            node = next(n for n in model.network.nodes() if n.id == t.id)
            if node.properties.min_level is not None and t.level_min <= node.properties.min_level + 1e-3:
                out.append(SummaryAlert(severity="error", topic="Estanque",
                                        text=f"Estanque {t.id}: llega al nivel mínimo en la simulación",
                                        type="node", id=t.id))
    for i in mt.expired.ids:
        out.append(SummaryAlert(severity="warning", topic="Mantenimiento", text=f"Tramo {i}: vida útil cumplida",
                                type="link", id=i))
    for i in mt.bad_condition.ids:
        out.append(SummaryAlert(severity="warning", topic="Mantenimiento", text=f"Tramo {i} en mal estado",
                                type="link", id=i))
    if hyd is not None:
        seen = {(a.type, a.id, a.topic) for a in out}
        for a in hyd.alerts:
            if a.code in ("VELOCITY_HIGH", "BOTTLENECK", "TANK_OVERFLOW"):
                key = (a.element_type, a.element_id, a.code)
                if key not in seen:
                    seen.add(key)
                    out.append(SummaryAlert(severity="warning", topic="Criterio", text=a.message,
                                            type=a.element_type, id=a.element_id))
    return out


# ── Exportaciones ──

def area_geojson(res: SummaryResult, name: str) -> dict:
    return {"type": "FeatureCollection", "features": [] if res.area.geometry is None else [{
        "type": "Feature", "geometry": res.area.geometry,
        "properties": {"proyecto": name, "margen_m": res.area.margin_m, "superficie_km2": res.area.area_km2}}]}


def zones_geojson(res: SummaryResult) -> dict:
    labels = {r.cls: r.label for r in res.zones.ranges}
    return {"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": z.geometry, "properties": {"nudo": z.node, "presion_m": z.pressure,
                                                                   "rango": labels[z.cls]}}
        for z in res.zones.features]}
