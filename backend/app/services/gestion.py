"""Página «Gestión» de un proyecto: indicadores con variación respecto al período anterior, gráficos, tablas de
detalle y referencias al mapa, en 7 pestañas (operación, clientes y consumo, pérdidas, activos y mantenimiento,
cumplimiento, planificación y equipo). Usa los registros de operación, las mediciones, los eventos de pérdidas, el
modelo (última versión) y su última simulación."""
from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from statistics import mean
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (AuditLog, ChlorineRecord, ClientReading, Complaint, EnergyRecord, FeasibilityRecord, LeakEvent,
                        MaintenanceLog, MaintenanceTask, Measurement, Membership, Project, ProjectVersion, ServiceOutage,
                        User)
from app.schemas.gestion import (Chart, Column, EmptyState, Filters, GestionSettings, Indicator, MapRef, Period, Series,
                                 TabResult, Table, Target)
from app.schemas.network import NetworkModel
from app.services import gestion_calc as calc
from app.services import gestion_records as rec
from app.services import summary as summ
from app.services import summary_calc as scalc
from app.services.errors import NotFound
from app.services.network import get_version_or_404, load_model

TITLES = {"operacion": "Operación", "clientes": "Clientes y consumo", "perdidas": "Pérdidas",
          "activos": "Activos y mantenimiento", "cumplimiento": "Cumplimiento", "planificacion": "Planificación",
          "equipo": "Equipo"}
HOURS = [f"{h:02d}:00" for h in range(24)]
NO_SECTOR = "Sin sector"
REFERENTIAL = ("Formatos referenciales para la gestión interna del APR («no verificado»): no declaran cumplimiento "
               "normativo; los rangos y derechos se configuran en «Metas».")
HOW_MEASURE = "Pestaña «Mediciones» del editor (ingreso manual o planilla «Mediciones»)"


# ── Configuración ──

def settings_of(project: Project) -> GestionSettings:
    st = GestionSettings()
    if project.gestion_settings:
        try:
            st = GestionSettings.model_validate(project.gestion_settings)
        except ValueError:
            pass
    from app.schemas.gestion import DEFAULT_TARGETS

    for k, v in DEFAULT_TARGETS.items():  # metas nuevas agregadas después de guardar la configuración
        st.targets.setdefault(k, v.model_copy())
    return st


def save_settings(session: Session, project: Project, body: GestionSettings) -> GestionSettings:
    project.gestion_settings = body.model_dump(mode="json")
    session.commit()
    return settings_of(project)


# ── Contexto de cálculo ──

@dataclass
class G:
    session: Session
    project: Project
    version: ProjectVersion | None
    model: NetworkModel | None
    st: GestionSettings
    sector_attr: str
    start: date
    end: date
    pstart: date
    pend: date
    months: list[str]
    pmonths: list[str]
    sector: str | None
    route: str | None
    today: date
    client_sector: dict[str, str] = field(default_factory=dict)
    client_route: dict[str, str] = field(default_factory=dict)
    node_sector: dict[str, str] = field(default_factory=dict)
    selected: set[str] = field(default_factory=set)
    _hyd: Any = None
    _hyd_done: bool = False

    @property
    def clients(self):
        return self.model.network.clients() if self.model else []

    def period(self) -> Period:
        return Period(start=self.start, end=self.end, prev_start=self.pstart, prev_end=self.pend, months=self.months)

    def target(self, key: str) -> Target | None:
        return self.st.targets.get(key)

    def hyd(self):
        """Última simulación del modelo (None si está bloqueada o no hay versión)."""
        if not self._hyd_done:
            self._hyd_done = True
            if self.model is not None and self.version is not None:
                try:
                    self._hyd, _ = summ.hydraulics(self.session, self.project, self.version, self.model,
                                                   summ.MODEL_SCENARIO)
                except Exception:  # noqa: BLE001 — sin simulación: se informa como dato faltante
                    self._hyd = None
        return self._hyd

    def in_filter(self, client_id: str | None) -> bool:
        if not self.sector and not self.route:
            return True
        return client_id in self.selected


def _dt(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)


def _end_dt(d: date) -> datetime:
    return _dt(d) + timedelta(days=1)


def context(session: Session, project: Project, start: date, end: date, sector: str | None, route: str | None,
            today: date | None = None) -> G:
    if end < start:
        start, end = end, start
    pstart, pend = calc.previous_period(start, end)
    version = model = None
    try:
        version = get_version_or_404(session, project, None)
        model = load_model(session, version)
    except NotFound:
        pass
    ss = summ.settings_of(project)
    g = G(session=session, project=project, version=version, model=model, st=settings_of(project),
          sector_attr=ss.sector_attribute, start=start, end=end, pstart=pstart, pend=pend,
          months=calc.months_between(start, end), pmonths=calc.months_between(pstart, pend),
          sector=sector or None, route=route or None, today=today or date.today())
    by_node: dict[str, Counter] = defaultdict(Counter)
    for c in g.clients:
        sec = summ._sector(c.properties.attributes, g.sector_attr) or NO_SECTOR
        g.client_sector[c.id] = sec
        g.client_route[c.id] = c.properties.route or "Sin ruta"
        by_node[c.properties.node][sec] += 1
        if (not g.sector or sec == g.sector) and (not g.route or g.client_route[c.id] == g.route):
            g.selected.add(c.id)
    if model is not None:
        for n in model.network.nodes():
            cnt = by_node.get(n.id)
            g.node_sector[n.id] = cnt.most_common(1)[0][0] if cnt else NO_SECTOR
    return g


def ind(g: G, key: str, value: float | None, previous: float | None = None, *, label: str | None = None,
        unit: str | None = None, nd: int = 2, **kw) -> Indicator:
    t = g.target(key)
    v = None if value is None or (isinstance(value, float) and math.isnan(value)) else round(value, nd)
    p = None if previous is None else round(previous, nd)
    u = unit if unit is not None else (t.unit if t else "")
    chart = kw.get("chart")
    if t and chart is not None and chart.reference is None and chart.unit == u:
        chart.goal, chart.goal_label = t.good, f"Meta {t.good:g} {u}".replace(".", ",")
    return Indicator(key=key, label=label or (t.label if t else key), unit=u,
                     value=v, previous=p, delta_pct=calc.variation_pct(v, p),
                     status=calc.status_of(v, t.good, t.bad, t.higher_is_better) if t else None,
                     target_verified=bool(t and t.verified), higher_is_better=t.higher_is_better if t else None, **kw)


def _r(x: float | None, nd: int = 2) -> float | None:
    return None if x is None else round(x, nd)


def filters(session: Session, project: Project) -> Filters:
    g = context(session, project, date.today(), date.today(), None, None)
    sectors = sorted({s for s in g.client_sector.values()}, key=lambda s: (s == NO_SECTOR, s))
    routes = summ._natural({r for r in g.client_route.values()})
    lo, hi = [], []
    for spec in rec.SPECS.values():
        col = getattr(spec.model, spec.date_field)
        a, b = session.execute(select(func.min(col), func.max(col)).where(spec.model.project_id == project.id)).one()
        if a is not None:
            conv = (lambda v: calc.month_start(v)) if spec.kind == "lecturas" else (
                lambda v: v.date() if isinstance(v, datetime) else v)
            lo.append(conv(a))
            hi.append(conv(b) if spec.kind != "lecturas" else calc.next_month(calc.month_start(b)) - timedelta(days=1))
    for model_cls, col in ((Measurement, Measurement.measured_at), (LeakEvent, LeakEvent.event_date)):
        a, b = session.execute(select(func.min(col), func.max(col)).where(model_cls.project_id == project.id)).one()
        if a is not None:
            lo.append(a.date() if isinstance(a, datetime) else a)
            hi.append(b.date() if isinstance(b, datetime) else b)
    # Las mantenciones programadas a futuro no extienden el período con datos.
    hi = [h for h in hi if h <= date.today()] or hi
    return Filters(sectors=sectors, routes=routes, data_start=min(lo) if lo else None, data_end=max(hi) if hi else None,
                   model_version=g.version.number if g.version else None)


# ── Datos compartidos ──

def _measurements(g: G, kind: str, start: date, end: date, element_type: str | None = None) -> list[Measurement]:
    q = select(Measurement).where(Measurement.project_id == g.project.id, Measurement.kind == kind,
                                  Measurement.measured_at >= _dt(start), Measurement.measured_at < _end_dt(end))
    if element_type:
        q = q.where(Measurement.element_type == element_type)
    return list(g.session.scalars(q.order_by(Measurement.measured_at)))


def _meter_series(g: G) -> dict[tuple[str, str], list[tuple[datetime, float]]]:
    out: dict[tuple[str, str], list[tuple[datetime, float]]] = defaultdict(list)
    for m in g.session.scalars(select(Measurement).where(Measurement.project_id == g.project.id,
                                                         Measurement.kind == "meter",
                                                         Measurement.element_type.in_(("well", "link")))):
        out[(m.element_type, m.element_id)].append((m.measured_at, m.value))
    return out


def _well_monthly(g: G) -> dict[str, float]:
    tot: dict[str, float] = defaultdict(float)
    for (t, _i), pts in _meter_series(g).items():
        if t == "well":
            for k, v in calc.meter_volumes_by_month(pts).items():
                tot[k] += v
    return dict(tot)


def _readings(g: G, months: list[str], only_selected: bool = True) -> list[ClientReading]:
    if not months:
        return []
    rows = g.session.scalars(select(ClientReading).where(ClientReading.project_id == g.project.id,
                                                         ClientReading.period >= months[0],
                                                         ClientReading.period <= months[-1]))
    return [r for r in rows if not only_selected or g.in_filter(r.client)]


def _right(g: G) -> tuple[float | None, float | None]:
    wells = [w for w in g.model.network.wells()] if g.model else []
    lps = g.st.water_right_lps
    if lps is None:
        vals = [w.properties.authorized_flow_lps for w in wells if w.properties.authorized_flow_lps]
        lps = sum(vals) if vals else None
    m3y = g.st.water_right_m3_year if g.st.water_right_m3_year is not None else (lps * 31_536.0 if lps else None)
    return lps, m3y


def _sum_months(d: dict[str, float], months: list[str]) -> float | None:
    vals = [d[m] for m in months if m in d]
    return sum(vals) if vals else None


def _month_chart(title: str, months: list[str], series: dict[str, dict[str, float]], unit: str, kind: str = "bar",
                 **kw) -> Chart:
    return Chart(title=title, x=months, unit=unit, series=[Series(name=n, kind=kind, values=[_r(v.get(m)) for m in months])
                                                           for n, v in series.items()], **kw)


# ── 1. Operación ──

def operacion(g: G) -> TabResult:
    inds, tables, charts, notes = [], [], [], []
    hyd = g.hyd()
    junctions = {n.id for n in g.model.network.nodes() if n.properties.kind == "junction"} if g.model else set()
    tanks = {n.id: n for n in g.model.network.nodes() if n.properties.kind == "tank"} if g.model else {}

    def zone_ok(node: str) -> bool:
        return not g.sector or g.node_sector.get(node, NO_SECTOR) == g.sector

    # Presión medida por zona y hora
    pm = [m for m in _measurements(g, "pressure", g.start, g.end) if m.element_type == "node" and zone_ok(m.element_id)]
    pp = [m for m in _measurements(g, "pressure", g.pstart, g.pend) if m.element_type == "node" and zone_ok(m.element_id)]
    by_zh: dict[tuple[str, int], list[float]] = defaultdict(list)
    by_h: dict[int, list[float]] = defaultdict(list)
    by_month: dict[str, list[float]] = defaultdict(list)
    for m in pm:
        z = g.node_sector.get(m.element_id, NO_SECTOR)
        h = m.measured_at.astimezone(timezone.utc).hour
        by_zh[(z, h)].append(m.value)
        by_h[h].append(m.value)
        by_month[calc.month_key(m.measured_at)].append(m.value)
    model_h: dict[int, list[float]] = defaultdict(list)
    model_zh: dict[tuple[str, int], list[float]] = defaultdict(list)
    if hyd is not None:
        for nid in junctions:
            if nid in hyd.pressure and zone_ok(nid) and nid not in hyd.unsupplied:
                for k, t in enumerate(hyd.times):
                    h = int(t // 3600) % 24
                    model_h[h].append(hyd.pressure[nid][k])
                    model_zh[(g.node_sector.get(nid, NO_SECTOR), h)].append(hyd.pressure[nid][k])
    chart = Chart(title="Presión por hora (24 h)", x=HOURS, unit="m.c.a.", series=[
        Series(name="Mínima medida", values=[_r(min(by_h[h])) if by_h[h] else None for h in range(24)]),
        Series(name="Promedio medido", values=[_r(mean(by_h[h])) if by_h[h] else None for h in range(24)]),
        Series(name="Máxima medida", values=[_r(max(by_h[h])) if by_h[h] else None for h in range(24)]),
        Series(name="Promedio del modelo", values=[_r(mean(model_h[h])) if model_h[h] else None for h in range(24)])])
    tables.append(Table(key="presion", title="Presión por zona y hora", columns=[
        Column(key="zona", label="Zona (sector)"), Column(key="hora", label="Hora"),
        Column(key="min", label="Mínima", unit="m", num=True), Column(key="prom", label="Promedio", unit="m", num=True),
        Column(key="max", label="Máxima", unit="m", num=True), Column(key="n", label="Mediciones", num=True),
        Column(key="modelo", label="Promedio del modelo", unit="m", num=True)],
        rows=[{"zona": z, "hora": HOURS[h], "min": _r(min(v)), "prom": _r(mean(v)), "max": _r(max(v)), "n": len(v),
               "modelo": _r(mean(model_zh[(z, h)])) if model_zh.get((z, h)) else None}
              for (z, h), v in sorted(by_zh.items())] or
             [{"zona": z, "hora": HOURS[h], "min": None, "prom": None, "max": None, "n": 0, "modelo": _r(mean(v))}
              for (z, h), v in sorted(model_zh.items())]))
    measured_nodes = sorted({m.element_id for m in pm})
    inds.append(ind(g, "pressure_min", min((m.value for m in pm), default=None), min((m.value for m in pp), default=None),
                    chart=chart, table="presion", map=MapRef(type="node", ids=measured_nodes) if measured_nodes else None,
                    note=f"Promedio medido {mean(m.value for m in pm):.1f} m · máxima {max(m.value for m in pm):.1f} m"
                    .replace(".", ",") if pm else ("Solo modelo: sin mediciones en el período." if model_h else None),
                    empty=None if pm else EmptyState(missing="Mediciones de presión en nudos",
                                                     how=f"{HOW_MEASURE}, medición «presión»")))
    charts.append(_month_chart("Presión mínima medida por mes", g.months,
                               {"Mínima": {m: min(v) for m, v in by_month.items()}}, "m.c.a.", "line"))

    # Niveles del estanque
    lv = [m for m in _measurements(g, "level", g.start, g.end) if m.element_id in tanks]
    lvp = [m for m in _measurements(g, "level", g.pstart, g.pend) if m.element_id in tanks]
    lv_h: dict[int, list[float]] = defaultdict(list)
    for m in lv:
        lv_h[m.measured_at.astimezone(timezone.utc).hour].append(m.value)
    model_lv: dict[int, list[float]] = defaultdict(list)
    if hyd is not None:
        for tid, t in tanks.items():
            if tid in hyd.head and t.properties.elevation is not None:
                for k, tt in enumerate(hyd.times):
                    model_lv[int(tt // 3600) % 24].append(hyd.head[tid][k] - t.properties.elevation)
    tchart = Chart(title="Nivel del estanque por hora (24 h)", x=HOURS, unit="m", series=[
        Series(name="Promedio medido", values=[_r(mean(lv_h[h])) if lv_h[h] else None for h in range(24)]),
        Series(name="Modelo", values=[_r(mean(model_lv[h])) if model_lv[h] else None for h in range(24)])])
    per_tank = defaultdict(list)
    for m in lv:
        per_tank[m.element_id].append(m.value)
    tables.append(Table(key="estanques", title="Niveles del estanque", columns=[
        Column(key="estanque", label="Estanque"), Column(key="min", label="Mínimo", unit="m", num=True),
        Column(key="prom", label="Promedio", unit="m", num=True), Column(key="max", label="Máximo", unit="m", num=True),
        Column(key="n", label="Mediciones", num=True), Column(key="nivel_min", label="Nivel mínimo de operación", unit="m", num=True)],
        rows=[{"estanque": tid, "min": _r(min(per_tank[tid])) if per_tank[tid] else None,
               "prom": _r(mean(per_tank[tid])) if per_tank[tid] else None,
               "max": _r(max(per_tank[tid])) if per_tank[tid] else None, "n": len(per_tank[tid]),
               "nivel_min": t.properties.min_level} for tid, t in sorted(tanks.items())]))
    inds.append(ind(g, "tank_level_min", min((m.value for m in lv), default=None), min((m.value for m in lvp), default=None),
                    chart=tchart, table="estanques", map=MapRef(type="node", ids=sorted(tanks)) if tanks else None,
                    empty=None if lv else EmptyState(missing="Mediciones de nivel del estanque",
                                                     how=f"{HOW_MEASURE}, medición «nivel» en el estanque")))

    # Energía y horas de bomba
    en = rec.list_rows(g.session, g.project, "energia", g.start, g.end)
    enp = rec.list_rows(g.session, g.project, "energia", g.pstart, g.pend)
    days_h = {r.record_date: 0.0 for r in en if r.hours is not None}
    for r in en:
        if r.hours is not None:
            days_h[r.record_date] += r.hours
    pdays_h: dict[date, float] = defaultdict(float)
    for r in enp:
        if r.hours is not None:
            pdays_h[r.record_date] += r.hours
    hours_m: dict[str, list[float]] = defaultdict(list)
    for d, h in days_h.items():
        hours_m[calc.month_key(d)].append(h)
    inds.append(ind(g, "pump_hours", mean(days_h.values()) if days_h else None,
                    mean(pdays_h.values()) if pdays_h else None, nd=1,
                    chart=_month_chart("Horas de bomba por día (promedio mensual)", g.months,
                                       {"Horas/día": {m: mean(v) for m, v in hours_m.items()}}, "h/día"),
                    table="energia",
                    empty=None if days_h else EmptyState(missing="Registros de energía con horas de funcionamiento",
                                                         how="Registro «Energía» (formulario o plantilla Excel)",
                                                         record="energia")))
    well_m = _well_monthly(g)
    kwh_m: dict[str, float] = defaultdict(float)
    vol_m: dict[str, float] = defaultdict(float)
    for r in en:
        k = calc.month_key(r.record_date)
        kwh_m[k] += r.kwh
        if r.volume_m3:
            vol_m[k] += r.volume_m3
    for k in kwh_m:
        if k not in vol_m and k in well_m:
            vol_m[k] = well_m[k]

    def kwh_per_m3(rows, months):
        kw = sum(r.kwh for r in rows)
        vols = defaultdict(float)
        for r in rows:
            if r.volume_m3:
                vols[calc.month_key(r.record_date)] += r.volume_m3
        vol = sum(vols.get(m) or well_m.get(m, 0.0) for m in {calc.month_key(r.record_date) for r in rows})
        return kw / vol if kw and vol else None
    tables.append(Table(key="energia", title="Energía y bombeo por mes", columns=[
        Column(key="mes", label="Mes"), Column(key="kwh", label="Energía", unit="kWh", num=True),
        Column(key="m3", label="Volumen", unit="m³", num=True), Column(key="kwh_m3", label="kWh/m³", num=True),
        Column(key="horas", label="Horas/día", unit="h", num=True)],
        rows=[{"mes": m, "kwh": _r(kwh_m.get(m), 1), "m3": _r(vol_m.get(m), 1),
               "kwh_m3": _r(kwh_m[m] / vol_m[m], 3) if kwh_m.get(m) and vol_m.get(m) else None,
               "horas": _r(mean(hours_m[m]), 1) if hours_m.get(m) else None} for m in g.months]))
    inds.append(ind(g, "kwh", sum(r.kwh for r in en) if en else None, sum(r.kwh for r in enp) if enp else None,
                    label="Energía consumida", unit="kWh", nd=0,
                    chart=_month_chart("Energía por mes", g.months, {"kWh": kwh_m}, "kWh"), table="energia",
                    empty=None if en else EmptyState(missing="Registros de energía (kWh)",
                                                     how="Registro «Energía» (formulario o plantilla Excel)", record="energia")))
    inds.append(ind(g, "kwh_m3", kwh_per_m3(en, g.months), kwh_per_m3(enp, g.pmonths), nd=3,
                    chart=_month_chart("kWh por m³", g.months, {"kWh/m³": {m: kwh_m[m] / vol_m[m] for m in kwh_m if vol_m.get(m)}},
                                       "kWh/m³", "line"), table="energia",
                    empty=None if en else EmptyState(missing="Energía y volumen bombeado",
                                                      how="Registro «Energía» y lecturas del medidor del pozo", record="energia")))

    # Caudal del pozo medido contra autorizado
    lps_m = {m: v / (calc.days_in_month(m) * 86.4) for m, v in well_m.items()}
    right_lps, _ = _right(g)
    cur = [lps_m[m] for m in g.months if m in lps_m]
    prev = [lps_m[m] for m in g.pmonths if m in lps_m]
    wells = sorted(w.id for w in g.model.network.wells()) if g.model else []
    tables.append(Table(key="pozo", title="Caudal del pozo por mes", columns=[
        Column(key="mes", label="Mes"), Column(key="m3", label="Volumen", unit="m³", num=True),
        Column(key="lps", label="Caudal medio", unit="L/s", num=True),
        Column(key="autorizado", label="Autorizado", unit="L/s", num=True), Column(key="pct", label="% del autorizado", num=True)],
        rows=[{"mes": m, "m3": _r(well_m.get(m), 1), "lps": _r(lps_m.get(m), 3), "autorizado": right_lps,
               "pct": _r(lps_m[m] / right_lps * 100, 1) if right_lps and m in lps_m else None} for m in g.months]))
    inds.append(ind(g, "well_use", max(cur) / right_lps * 100 if cur and right_lps else None,
                    max(prev) / right_lps * 100 if prev and right_lps else None, nd=1,
                    note=f"Caudal medio máximo {max(cur):.2f} L/s de {right_lps:g} L/s autorizados".replace(".", ",")
                    if cur and right_lps else None,
                    chart=_month_chart("Caudal medio del pozo (medido) y autorizado", g.months, {"Caudal medio": lps_m}, "L/s",
                                       reference=right_lps, reference_label="Autorizado"),
                    table="pozo", map=MapRef(type="well", ids=wells) if wells else None,
                    empty=None if cur else EmptyState(missing="Lecturas del medidor del pozo (m³ acumulados)",
                                                      how=f"{HOW_MEASURE}, medición «medidor» del pozo")))
    charts.append(_month_chart("Volumen producido por mes", g.months, {"Pozo (m³)": well_m}, "m³"))
    if g.sector:
        notes.append("El filtro de sector se aplica a la presión por zona; energía, estanque y pozo son de todo el sistema.")
    return TabResult(tab="operacion", title=TITLES["operacion"], period=g.period(), sector=g.sector, route=g.route,
                     indicators=inds, charts=charts, tables=tables, notes=notes)


# ── 2. Clientes y consumo ──

def _connection_key(c) -> str:
    p = c.properties
    if p.connection:
        return f"{round(p.connection[0], 6)},{round(p.connection[1], 6)}"
    return f"{p.node}|{p.link or ''}|{c.id}"


def persons_per_dwelling(g: G) -> float:
    from app.services import demand

    try:
        return demand.inputs_for(g.session, g.project)[0].persons_per_dwelling
    except Exception:  # noqa: BLE001
        return 3.5


def clientes(g: G) -> TabResult:
    inds, tables, charts, notes = [], [], [], []
    cl = {c.id: c for c in g.clients}
    cur = _readings(g, g.months)
    prv = _readings(g, g.pmonths)
    all_rows = g.session.scalars(select(ClientReading).where(ClientReading.project_id == g.project.id))
    history: dict[str, list[str]] = defaultdict(list)
    by_month_clients: dict[str, set[str]] = defaultdict(set)
    for r in all_rows:
        if g.in_filter(r.client) and r.m3 > 0:
            history[r.client].append(r.period)
            by_month_clients[r.period].add(r.client)
    mov = calc.client_movements(g.months, by_month_clients, history)
    pmov = calc.client_movements(g.pmonths, by_month_clients, history)
    last = next((m for m in reversed(g.months) if mov[m][0]), None)
    plast = next((m for m in reversed(g.pmonths) if pmov[m][0]), None)
    empty_r = EmptyState(missing="Lecturas mensuales de clientes (m³ por cliente y mes)",
                         how="Registro «Lecturas de clientes»: formulario o planilla Excel (N° cliente, período, m³)",
                         record="lecturas")
    conn = {m: len({_connection_key(cl[c]) for c in by_month_clients[m] if c in cl}) for m in g.months}
    tables.append(Table(key="movimientos", title="Clientes y arranques por mes", columns=[
        Column(key="mes", label="Mes"), Column(key="activos", label="Activos", num=True),
        Column(key="arranques", label="Arranques activos", num=True), Column(key="nuevos", label="Nuevos", num=True),
        Column(key="bajas", label="Bajas", num=True)],
        rows=[{"mes": m, "activos": mov[m][0], "arranques": conn[m], "nuevos": mov[m][1], "bajas": mov[m][2]}
              for m in g.months]))
    mchart = Chart(title="Clientes activos, nuevos y bajas por mes", x=g.months, unit="clientes", series=[
        Series(name="Activos", kind="line", values=[mov[m][0] for m in g.months]),
        Series(name="Nuevos", kind="bar", values=[mov[m][1] for m in g.months]),
        Series(name="Bajas", kind="bar", values=[mov[m][2] for m in g.months])])
    active_ids = sorted(by_month_clients[last]) if last else []
    inds.append(ind(g, "active_clients", mov[last][0] if last else None, pmov[plast][0] if plast else None,
                    label="Clientes activos", unit="clientes", nd=0, chart=mchart, table="movimientos",
                    note=(f"{conn[last]} arranques activos · {sum(v[1] for v in mov.values())} nuevos · "
                          f"{sum(v[2] for v in mov.values())} bajas en el período") if last else None,
                    map=MapRef(type="client", ids=active_ids) if active_ids else None,
                    empty=None if last else empty_r))

    tot = sum(r.m3 for r in cur)
    ptot = sum(r.m3 for r in prv)
    per_month = defaultdict(float)
    for r in cur:
        per_month[r.period] += r.m3
    inds.append(ind(g, "consumption", tot if cur else None, ptot if prv else None, label="Consumo facturado", unit="m³",
                    nd=1, chart=_month_chart("Consumo facturado por mes", g.months, {"m³": per_month}, "m³"),
                    table="consumo_cliente", empty=None if cur else empty_r))
    nconn = sum(conn[m] for m in g.months)
    pconn = sum(len({_connection_key(cl[c]) for c in by_month_clients[m] if c in cl}) for m in g.pmonths)
    inds.append(ind(g, "per_connection", tot / nconn if nconn else None, ptot / pconn if pconn else None, nd=1,
                    table="consumo_ruta", empty=None if cur else empty_r))

    # Dotación real (clientes residenciales)
    ppd = persons_per_dwelling(g)

    def dot(rows, months):
        res = [r for r in rows if r.client in cl and cl[r.client].properties.client_type == "residencial"]
        if not res:
            return None
        m3 = sum(r.m3 for r in res)
        dw_days = sum(len({r.client for r in res if r.period == m}) * calc.days_in_month(m) for m in months)
        return calc.dotacion(m3, 1, ppd, dw_days) if dw_days else None
    dot_m = {m: d for m in g.months if (d := dot([r for r in cur if r.period == m], [m])) is not None}
    inds.append(ind(g, "dotacion", dot(cur, g.months), dot(prv, g.pmonths), nd=1,
                    note=f"Con {ppd:g} habitantes por vivienda (módulo de demanda)".replace(".", ","),
                    chart=_month_chart("Dotación real por mes", g.months, {"L/hab/día": dot_m}, "L/hab/día", "line"),
                    empty=None if cur else empty_r))

    # Por cliente, ruta y sector; mayores consumidores y tramos de consumo
    per_client: dict[str, float] = defaultdict(float)
    months_client: dict[str, set[str]] = defaultdict(set)
    for r in cur:
        per_client[r.client] += r.m3
        months_client[r.client].add(r.period)
    rows = []
    for cid, m3 in sorted(per_client.items(), key=lambda x: -x[1]):
        c = cl.get(cid)
        rows.append({"cliente": cid, "numero": c.properties.client_number if c else None,
                     "nombre": c.properties.name if c else None, "ruta": g.client_route.get(cid),
                     "sector": g.client_sector.get(cid), "tipo": c.properties.client_type if c else None,
                     "m3": _r(m3, 1), "m3_mes": _r(m3 / max(1, len(months_client[cid])), 2)})
    tables.append(Table(key="consumo_cliente", title="Consumo por cliente", columns=[
        Column(key="cliente", label="Cliente"), Column(key="numero", label="N° cliente"), Column(key="nombre", label="Nombre"),
        Column(key="ruta", label="Ruta"), Column(key="sector", label="Sector"), Column(key="tipo", label="Tipo"),
        Column(key="m3", label="Consumo", unit="m³", num=True), Column(key="m3_mes", label="Promedio", unit="m³/mes", num=True)],
        rows=rows))
    for key, title, getter in (("consumo_ruta", "Consumo por ruta", g.client_route), ("consumo_sector", "Consumo por sector", g.client_sector)):
        agg: dict[str, list] = defaultdict(lambda: [0.0, set()])
        for cid, m3 in per_client.items():
            k = getter.get(cid, "—")
            agg[k][0] += m3
            agg[k][1].add(cid)
        tables.append(Table(key=key, title=title, columns=[
            Column(key="grupo", label="Ruta" if key == "consumo_ruta" else "Sector"),
            Column(key="clientes", label="Clientes", num=True), Column(key="m3", label="Consumo", unit="m³", num=True),
            Column(key="m3_cliente", label="Promedio por cliente", unit="m³/mes", num=True)],
            rows=[{"grupo": k, "clientes": len(v[1]), "m3": _r(v[0], 1),
                   "m3_cliente": _r(v[0] / len(v[1]) / max(1, len(g.months)), 2)}
                  for k, v in sorted(agg.items(), key=lambda kv: kv[0])]))
    top = rows[:10]
    tables.append(Table(key="mayores", title="Mayores consumidores", columns=tables[-3].columns, rows=top))
    bins = Counter(calc.consumption_bin(r["m3_mes"]) for r in rows)
    labels = [b[2] for b in calc.CONSUMPTION_BINS]
    tables.append(Table(key="tramos_consumo", title="Distribución por tramos de consumo", columns=[
        Column(key="tramo", label="Tramo (m³/mes)"), Column(key="clientes", label="Clientes", num=True)],
        rows=[{"tramo": b, "clientes": bins.get(b, 0)} for b in labels]))
    inds.append(ind(g, "top_consumer", top[0]["m3_mes"] if top else None, label="Mayor consumidor", unit="m³/mes",
                    note=f"{top[0]['cliente']} · {top[0]['nombre'] or ''}" if top else None, table="mayores",
                    chart=Chart(title="Distribución por tramos de consumo", x=labels, unit="clientes",
                                series=[Series(name="Clientes", kind="bar", values=[bins.get(b, 0) for b in labels])]),
                    map=MapRef(type="client", ids=[r["cliente"] for r in top]) if top else None,
                    empty=None if cur else empty_r))
    if g.sector or g.route:
        notes.append("Filtro aplicado a los clientes por su sector y ruta de lectura.")
    return TabResult(tab="clientes", title=TITLES["clientes"], period=g.period(), sector=g.sector, route=g.route,
                     indicators=inds, charts=charts, tables=tables, notes=notes,
                     extra={"persons_per_dwelling": ppd})


# ── 3. Pérdidas ──

def _production_by_sector(g: G) -> dict[str, dict[str, float]]:
    st = summ.settings_of(g.project)
    series = _meter_series(g)
    links = {lk.id: lk for lk in g.model.network.links()} if g.model else {}
    meters = [(p.sector, p.element_type, p.element_id) for p in st.production_meters]
    if not meters:
        for (t, i) in sorted(series):
            if t == "well":
                meters.append(("Total", t, i))
            elif i in links:
                meters.append((summ._sector(links[i].properties.attributes, st.sector_attribute) or f"Tramo {i}", t, i))
    out: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for sector, t, i in meters:
        for m, v in calc.meter_volumes_by_month(series.get((t, i), [])).items():
            out[sector][m] += v
    return {k: dict(v) for k, v in out.items()}


def perdidas(g: G) -> TabResult:
    inds, tables, charts, notes = [], [], [], []
    prod = _production_by_sector(g)
    readings = [r for r in g.session.scalars(select(ClientReading).where(ClientReading.project_id == g.project.id))]
    cons: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for r in readings:
        cons["Total"][r.period] += r.m3
        cons[g.client_sector.get(r.client, NO_SECTOR)][r.period] += r.m3
    sector = g.sector or "Total"
    rows, chart_s = [], {}
    for sec in sorted(prod, key=lambda s: (s != "Total", s)):
        nr = calc.nrw_monthly({m: v for m, v in prod[sec].items() if m in g.months}, cons.get(sec, {}))
        for x in nr:
            rows.append({"sector": sec, "mes": x.month, "produccion": x.production_m3, "consumo": x.consumption_m3,
                         "anc": x.nrw_m3, "anc_pct": x.nrw_pct})
        chart_s[sec] = {x.month: x.nrw_pct for x in nr if x.nrw_pct is not None}
    tables.append(Table(key="anc", title="Agua no contabilizada por mes y sector", columns=[
        Column(key="sector", label="Sector"), Column(key="mes", label="Mes"),
        Column(key="produccion", label="Producción", unit="m³", num=True), Column(key="consumo", label="Consumo facturado", unit="m³", num=True),
        Column(key="anc", label="ANC", unit="m³", num=True), Column(key="anc_pct", label="ANC", unit="%", num=True)], rows=rows))

    def total_pct(months):
        p = sum(v for m, v in prod.get(sector, {}).items() if m in months)
        c = sum(v for m, v in cons.get(sector, {}).items() if m in months and m in prod.get(sector, {}))
        return calc.nrw(p, c)[1] if p else None
    has_reads = bool(readings)
    sec_clients = [c for c in g.client_sector if sector == "Total" or g.client_sector[c] == sector]
    inds.append(ind(g, "nrw", total_pct(g.months) if has_reads else None, total_pct(g.pmonths) if has_reads else None, nd=1,
                    label=f"Agua no contabilizada ({sector})",
                    chart=_month_chart("Agua no contabilizada mensual por sector", g.months, chart_s, "%", "line"),
                    table="anc", map=MapRef(type="client", ids=sec_clients) if sec_clients else None,
                    empty=None if (prod and has_reads) else EmptyState(
                        missing=("Lecturas del medidor de producción (pozo o macromedidor)" if not prod else
                                 "Lecturas mensuales de clientes (consumo facturado)"),
                        how=(f"{HOW_MEASURE}, medición «medidor»" if not prod else
                             "Registro «Lecturas de clientes» (formulario o planilla)"),
                        record=None if not prod else "lecturas")))

    # Eventos de fuga
    links = {lk.id: lk for lk in g.model.network.links()} if g.model else {}
    ev = list(g.session.scalars(select(LeakEvent).where(LeakEvent.project_id == g.project.id,
                                                       LeakEvent.event_date >= g.start, LeakEvent.event_date <= g.end)))
    evp = list(g.session.scalars(select(LeakEvent).where(LeakEvent.project_id == g.project.id,
                                                        LeakEvent.event_date >= g.pstart, LeakEvent.event_date <= g.pend)))
    if g.sector:
        sec_of_link = {i: (summ._sector(lk.properties.attributes, g.sector_attr) or
                           Counter(g.node_sector.get(n) for n in (lk.properties.from_node, lk.properties.to_node)).most_common(1)[0][0])
                       for i, lk in links.items()}
        ev = [e for e in ev if sec_of_link.get(e.link_id) == g.sector]
        evp = [e for e in evp if sec_of_link.get(e.link_id) == g.sector]
    leaks = [e for e in ev if e.kind in ("fuga", "rotura")]
    pleaks = [e for e in evp if e.kind in ("fuga", "rotura")]
    by_m = Counter(calc.month_key(e.event_date) for e in leaks)
    by_mat = Counter((links[e.link_id].properties.material or "sin dato") if e.link_id in links else "sin dato" for e in leaks)
    per_link: dict[str, list[LeakEvent]] = defaultdict(list)
    for e in ev:
        per_link[e.link_id].append(e)
    link_rows = []
    for lid, es in sorted(per_link.items(), key=lambda kv: (-sum(1 for e in kv[1] if e.kind != "reparacion"), kv[0])):
        p = links[lid].properties if lid in links else None
        n = sum(1 for e in es if e.kind != "reparacion")
        length = (p.length_hydraulic_m or p.length_plan_m or 0) if p else 0
        link_rows.append({"tramo": lid, "material": p.material if p else None, "dn": p.dn if p else None,
                          "anio": p.install_year if p else None, "estado": p.condition if p else None,
                          "fugas": n, "reparaciones": sum(1 for e in es if e.kind == "reparacion"),
                          "caudal": _r(sum(e.flow_lps or 0 for e in es), 3),
                          "fugas_km": _r(n / (length / 1000), 1) if length else None,
                          "ultima": max(e.event_date for e in es).isoformat()})
    tables.append(Table(key="fugas_tramo", title="Eventos por tramo", columns=[
        Column(key="tramo", label="Tramo"), Column(key="material", label="Material"), Column(key="dn", label="DN", num=True),
        Column(key="anio", label="Año", num=True), Column(key="estado", label="Estado"), Column(key="fugas", label="Fugas y roturas", num=True),
        Column(key="reparaciones", label="Reparaciones", num=True), Column(key="caudal", label="Caudal perdido", unit="L/s", num=True),
        Column(key="fugas_km", label="Fugas por km", num=True), Column(key="ultima", label="Último evento")], rows=link_rows))
    tables.append(Table(key="fugas_material", title="Fugas por material", columns=[
        Column(key="material", label="Material"), Column(key="eventos", label="Eventos", num=True)],
        rows=[{"material": k, "eventos": v} for k, v in by_mat.most_common()]))
    nmonths = max(1, len(g.months))
    weights = {r["tramo"]: float(r["fugas"]) for r in link_rows if r["fugas"]}
    inds.append(ind(g, "leaks", len(leaks) / nmonths if ev or evp else None, len(pleaks) / max(1, len(g.pmonths)) if evp else None,
                    nd=2, note=f"{len(leaks)} fugas y roturas en el período" if ev else None,
                    chart=_month_chart("Fugas y roturas por mes", g.months, {"Eventos": dict(by_m)}, "eventos"),
                    table="fugas_tramo",
                    map=MapRef(type="link", ids=list(weights), weights=weights) if weights else None,
                    empty=None if ev else EmptyState(missing="Eventos de fuga, rotura o reparación por tramo",
                                                     how="Pestaña «Resumen» del editor → Pérdidas (manual o planilla «Pérdidas»)")))
    critical = [r for r in link_rows if r["fugas"] >= 2 or r["estado"] == "malo"]
    tables.append(Table(key="criticos", title="Tramos críticos (2 o más fugas, o en mal estado con eventos)",
                        columns=tables[-2].columns, rows=critical))
    inds.append(ind(g, "critical_links", float(len(critical)) if ev else None, label="Tramos críticos", unit="tramos", nd=0,
                    table="criticos",
                    chart=Chart(title="Fugas por material", x=[k for k, _ in by_mat.most_common()], unit="eventos",
                                series=[Series(name="Eventos", kind="bar", values=[v for _, v in by_mat.most_common()])]),
                    map=MapRef(type="link", ids=[r["tramo"] for r in critical],
                               weights={r["tramo"]: float(r["fugas"]) for r in critical}) if critical else None,
                    empty=None if ev else EmptyState(missing="Eventos de fuga por tramo",
                                                     how="Pestaña «Resumen» del editor → Pérdidas")))
    if not has_reads and prod:
        notes.append("Sin lecturas de clientes no se puede calcular el agua no contabilizada mensual.")
    return TabResult(tab="perdidas", title=TITLES["perdidas"], period=g.period(), sector=g.sector, route=g.route,
                     indicators=inds, charts=charts, tables=tables, notes=notes, extra={"heat": weights})


# ── 4. Activos y mantenimiento ──

def activos(g: G) -> TabResult:
    inds, tables, charts, notes = [], [], [], []
    ss = summ.settings_of(g.project)
    pipes = [lk for lk in g.model.network.links() if lk.properties.kind == "pipe"] if g.model else []
    year = g.today.year

    def length(lk):
        p = lk.properties
        return p.length_hydraulic_m or p.length_plan_m or 0.0

    def group(keyf, order=None):
        agg: dict[str, list] = defaultdict(lambda: [0.0, []])
        for lk in pipes:
            k = keyf(lk)
            agg[k][0] += length(lk) / 1000
            agg[k][1].append(lk.id)
        keys = order or sorted(agg, key=lambda k: -agg[k][0])
        return [{"grupo": k, "km": _r(agg[k][0], 3), "tramos": len(agg[k][1]), "ids": agg[k][1]} for k in keys if k in agg]

    def age(lk):
        y = lk.properties.install_year
        if y is None:
            return "sin dato"
        a = year - y
        return next(lbl for lo, hi, lbl in summ.AGE_BINS if lo <= a < hi)
    inv = {"material": group(lambda lk: lk.properties.material or "sin dato"),
           "dn": group(lambda lk: f"DN {lk.properties.dn}" if lk.properties.dn else "sin dato"),
           "edad": group(age, [b[2] for b in summ.AGE_BINS] + ["sin dato"]),
           "estado": group(lambda lk: lk.properties.condition or "sin dato")}
    titles = {"material": "Material", "dn": "Diámetro", "edad": "Edad", "estado": "Estado"}
    for k, rows in inv.items():
        tables.append(Table(key=f"inventario_{k}", title=f"Inventario por {titles[k].lower()}", columns=[
            Column(key="grupo", label=titles[k]), Column(key="km", label="Largo", unit="km", num=True),
            Column(key="tramos", label="Tramos", num=True)], rows=[{x: r[x] for x in ("grupo", "km", "tramos")} for r in rows]))
    total_km = sum(length(lk) for lk in pipes) / 1000
    bad = [lk for lk in pipes if lk.properties.condition in summ.BAD]
    bad_km = sum(length(lk) for lk in bad) / 1000
    inds.append(ind(g, "pipes_bad", bad_km / total_km * 100 if total_km else None, nd=1,
                    note=f"{total_km:.2f} km de red · {len(pipes)} tramos".replace(".", ","),
                    chart=Chart(title="Red por material (km)", x=[r["grupo"] for r in inv["material"]], unit="km",
                                series=[Series(name="km", kind="bar", values=[r["km"] for r in inv["material"]])]),
                    table="inventario_estado", map=MapRef(type="link", ids=[lk.id for lk in bad]) if bad else None,
                    empty=None if pipes else EmptyState(missing="Tramos de la red", how="Dibuje o importe la red en el editor")))
    charts.append(Chart(title="Red por edad (km)", x=[r["grupo"] for r in inv["edad"]], unit="km",
                        series=[Series(name="km", kind="bar", values=[r["km"] for r in inv["edad"]])]))

    # Plan de renovación
    ages = [scalc.PipeAge(lk.id, lk.properties.material, lk.properties.dn, length(lk), lk.properties.install_year) for lk in pipes]
    prices = [(p.material, p.dn_max, p.price_m) for p in ss.prices]
    plan = scalc.renewal_plan(ages, ss.service_life, ss.default_life, year, 20, prices)
    exp_km, exp_ids = scalc.expired(ages, ss.service_life, ss.default_life, year)
    tables.append(Table(key="renovacion", title="Plan de renovación (20 años)", columns=[
        Column(key="anio", label="Año", num=True), Column(key="km", label="Largo", unit="km", num=True),
        Column(key="costo", label="Costo", unit="CLP", num=True), Column(key="tramos", label="Tramos")],
        rows=[{"anio": y, "km": km, "costo": cost, "tramos": ", ".join(ids)} for y, km, cost, ids in plan]))
    inds.append(ind(g, "renewal_due", exp_km if pipes else None, nd=3,
                    note=(f"Plan a 20 años: ${sum(p[2] for p in plan):,.0f} CLP".replace(",", ".") +
                          ("" if ss.prices_verified and ss.life_verified else " · vida útil y precios «no verificado»")) if plan else None,
                    chart=Chart(title="Costo de renovación por año", x=[str(p[0]) for p in plan], unit="CLP",
                                series=[Series(name="Costo", kind="bar", values=[p[2] for p in plan])]),
                    table="renovacion", map=MapRef(type="link", ids=exp_ids) if exp_ids else None))

    # Mantenciones
    tasks = list(g.session.scalars(select(MaintenanceTask).where(MaintenanceTask.project_id == g.project.id)
                                   .order_by(MaintenanceTask.next_date)))
    spec = rec.SPECS["mantenciones"]
    out = [rec.row_out(spec, t, g.today) for t in tasks]
    recurring_or_open = [r for r in out if r["status"] != "hecha"]
    ok = sum(1 for r in recurring_or_open if r["status"] == "pendiente")
    tables.append(Table(key="mantenciones", title="Mantenciones programadas", columns=[
        Column(key="kind", label="Tipo"), Column(key="element", label="Elemento"), Column(key="description", label="Descripción"),
        Column(key="frequency_days", label="Frecuencia", unit="días", num=True), Column(key="next_date", label="Próxima fecha"),
        Column(key="assignee", label="Responsable"), Column(key="status", label="Estado"),
        Column(key="overdue_days", label="Días de atraso", num=True), Column(key="last_done", label="Última vez")], rows=out))
    overdue = [r for r in out if r["status"] == "atrasada"]
    tables.append(Table(key="atrasadas", title="Mantenciones atrasadas", columns=tables[-1].columns, rows=overdue))
    lg = [x for x in rec.logs(g.session, g.project) if g.start <= x.done_on <= g.end]
    kinds = {t.id: t for t in tasks}
    tables.append(Table(key="cumplimiento_mant", title="Registro de cumplimiento", columns=[
        Column(key="fecha", label="Fecha"), Column(key="tipo", label="Tipo"), Column(key="elemento", label="Elemento"),
        Column(key="programada", label="Programada"), Column(key="por", label="Responsable"), Column(key="nota", label="Nota")],
        rows=[{"fecha": x.done_on.isoformat(), "tipo": kinds[x.task_id].kind if x.task_id in kinds else None,
               "elemento": kinds[x.task_id].element if x.task_id in kinds else None,
               "programada": x.scheduled_for.isoformat() if x.scheduled_for else None, "por": x.by, "nota": x.note} for x in lg]))
    done_m = Counter(calc.month_key(x.done_on) for x in lg)
    el_ids = sorted({r["element"] for r in overdue if r["element"]})
    inds.append(ind(g, "maintenance_ok", ok / len(recurring_or_open) * 100 if recurring_or_open else None, nd=1,
                    note=f"{len(overdue)} atrasadas de {len(recurring_or_open)} vigentes · {len(lg)} cumplidas en el período"
                    if out else None,
                    chart=_month_chart("Mantenciones cumplidas por mes", g.months, {"Cumplidas": dict(done_m)}, "mantenciones"),
                    table="atrasadas", map=_element_ref(g, el_ids),
                    empty=None if out else EmptyState(missing="Mantenciones programadas",
                                                      how="Registro «Mantenciones y tareas» (formulario o plantilla)",
                                                      record="mantenciones")))
    calendar = [{"date": r["next_date"], "kind": r["kind"], "element": r["element"], "status": r["status"], "id": r["id"],
                 "assignee": r["assignee"]} for r in out if r["status"] != "hecha"]
    return TabResult(tab="activos", title=TITLES["activos"], period=g.period(), sector=g.sector, route=g.route,
                     indicators=inds, charts=charts, tables=tables, notes=notes, extra={"calendar": calendar})


def _element_ref(g: G, ids: list[str]) -> MapRef | None:
    """Referencia al mapa para IDs de distinto tipo: se usa el tipo más frecuente."""
    if not ids or g.model is None:
        return None
    net = g.model.network
    pools = {"node": {n.id for n in net.nodes()}, "link": {lk.id for lk in net.links()},
             "shutoff": {s.id for s in net.shutoffs()}, "hydrant": {h.id for h in net.hydrants()},
             "well": {w.id for w in net.wells()}}
    best = max(pools, key=lambda t: sum(1 for i in ids if i in pools[t]))
    hit = [i for i in ids if i in pools[best]]
    return MapRef(type=best, ids=hit) if hit else None


# ── 5. Cumplimiento ──

def cumplimiento(g: G) -> TabResult:
    inds, tables, charts = [], [], []
    notes = [REFERENTIAL]
    # Extracción contra derecho de agua
    well_m = _well_monthly(g)
    right_lps, right_m3y = _right(g)
    days = (g.end - g.start).days + 1
    pdays = (g.pend - g.pstart).days + 1

    def annual_pct(months, ndays):
        v = _sum_months(well_m, months)
        return v / ndays * 365 / right_m3y * 100 if v is not None and right_m3y else None
    month_right = {m: right_m3y * calc.days_in_month(m) / 365 for m in g.months} if right_m3y else {}
    tables.append(Table(key="extraccion", title="Extracción del pozo contra derecho de agua", columns=[
        Column(key="mes", label="Mes"), Column(key="m3", label="Extraído", unit="m³", num=True),
        Column(key="lps", label="Caudal medio", unit="L/s", num=True), Column(key="derecho_m3", label="Derecho del mes", unit="m³", num=True),
        Column(key="pct", label="% del derecho", num=True)],
        rows=[{"mes": m, "m3": _r(well_m.get(m), 1), "lps": _r(well_m[m] / (calc.days_in_month(m) * 86.4), 3) if m in well_m else None,
               "derecho_m3": _r(month_right.get(m), 1),
               "pct": _r(well_m[m] / month_right[m] * 100, 1) if m in well_m and month_right.get(m) else None} for m in g.months]))
    vol = _sum_months(well_m, g.months)
    inds.append(ind(g, "extraction", annual_pct(g.months, days), annual_pct(g.pmonths, pdays), nd=1,
                    note=(f"{vol:,.0f} m³ extraídos; derecho {right_lps:g} L/s · {right_m3y:,.0f} m³/año"
                          .replace(",", ".") if vol is not None and right_lps else None),
                    chart=_month_chart("Volumen extraído y derecho mensual", g.months, {"Extraído": well_m}, "m³",
                                       reference=_r(right_m3y / 12, 0) if right_m3y else None,
                                       reference_label="Derecho (mes promedio)"),
                    table="extraccion",
                    empty=None if vol is not None and right_lps else EmptyState(
                        missing="Lecturas del medidor del pozo" if vol is None else "Derecho de agua (caudal autorizado)",
                        how=f"{HOW_MEASURE}, medición «medidor»" if vol is None else
                        "Caudal autorizado del pozo (editor) o «Metas» de esta página")))

    # Continuidad del servicio
    outs = list(g.session.scalars(select(ServiceOutage).where(ServiceOutage.project_id == g.project.id,
                                                             ServiceOutage.started_at < _end_dt(g.end))))
    now = datetime.now(timezone.utc)
    cur = [o for o in outs if (o.ended_at or now) >= _dt(g.start)]
    spans = [calc.OutageSpan(o.started_at, o.ended_at, o.clients_affected or 0) for o in outs]
    ch = calc.client_hours_by_month(spans, g.months, now)
    pch = calc.client_hours_by_month(spans, g.pmonths, now)
    n_clients = max(1, sum(1 for c in g.clients if c.properties.status == "activo"))
    spec = rec.SPECS["cortes"]
    tables.append(Table(key="cortes", title="Cortes del servicio", columns=[
        Column(key="kind", label="Tipo"), Column(key="started_at", label="Inicio"), Column(key="ended_at", label="Fin"),
        Column(key="sector", label="Cuartel"), Column(key="link_id", label="Tramo"),
        Column(key="clients_affected", label="Clientes afectados", num=True), Column(key="duration_h", label="Duración", unit="h", num=True),
        Column(key="client_hours", label="Horas-cliente", num=True), Column(key="note", label="Motivo")],
        rows=[rec.row_out(spec, o) for o in sorted(cur, key=lambda o: o.started_at, reverse=True)]))
    by_kind = {k: calc.client_hours_by_month([calc.OutageSpan(o.started_at, o.ended_at, o.clients_affected or 0)
                                              for o in outs if o.kind == k], g.months, now)
               for k in ("programado", "emergencia")}
    sectors = sorted({o.sector for o in cur if o.sector})
    inds.append(ind(g, "client_hours", sum(ch.values()) / n_clients / max(1, len(g.months)) if outs else None,
                    sum(pch.values()) / n_clients / max(1, len(g.pmonths)) if outs else None, nd=2,
                    note=f"{len(cur)} cortes · {sum(ch.values()):,.0f} horas-cliente sin servicio".replace(",", ".") if cur else None,
                    chart=_month_chart("Horas-cliente sin servicio por mes", g.months,
                                       {"Programados": by_kind["programado"], "Emergencia": by_kind["emergencia"]}, "h·cliente",
                                       stacked=True),
                    table="cortes", map=MapRef(type="link", ids=sorted({o.link_id for o in cur if o.link_id})) if any(o.link_id for o in cur) else None,
                    empty=None if outs else EmptyState(missing="Registro de cortes del servicio",
                                                       how="Registro «Cortes de servicio» (formulario o plantilla)", record="cortes")))
    if sectors:
        notes.append(f"Cuarteles con cortes en el período: {', '.join(sectors)}.")

    # Calidad: cloro residual libre
    lo, hi = g.st.chlorine_min, g.st.chlorine_max
    cl = rec.list_rows(g.session, g.project, "cloro", g.start, g.end)
    clp = rec.list_rows(g.session, g.project, "cloro", g.pstart, g.pend)

    def ok_pct(rows):
        return sum(1 for r in rows if calc.within(r.mg_l, lo, hi)) / len(rows) * 100 if rows else None
    per_point: dict[str, list[float]] = defaultdict(list)
    per_day: dict[str, list[float]] = defaultdict(list)
    for r in cl:
        per_point[r.point].append(r.mg_l)
        per_day[calc.month_key(r.measured_at)].append(r.mg_l)
    tables.append(Table(key="cloro", title=f"Cloro residual libre por punto (rango {lo:g}–{hi:g} mg/L)".replace(".", ","), columns=[
        Column(key="punto", label="Punto"), Column(key="n", label="Mediciones", num=True),
        Column(key="min", label="Mínimo", unit="mg/L", num=True), Column(key="prom", label="Promedio", unit="mg/L", num=True),
        Column(key="max", label="Máximo", unit="mg/L", num=True), Column(key="ok", label="Dentro de rango", unit="%", num=True)],
        rows=[{"punto": p, "n": len(v), "min": _r(min(v)), "prom": _r(mean(v)), "max": _r(max(v)),
               "ok": _r(sum(1 for x in v if calc.within(x, lo, hi)) / len(v) * 100, 1)} for p, v in sorted(per_point.items())]))
    out_rows = [rec.row_out(rec.SPECS["cloro"], r) for r in cl if not calc.within(r.mg_l, lo, hi)]
    tables.append(Table(key="cloro_fuera", title="Mediciones de cloro fuera de rango", columns=[
        Column(key="measured_at", label="Fecha y hora"), Column(key="point", label="Punto"),
        Column(key="mg_l", label="Cloro libre", unit="mg/L", num=True), Column(key="note", label="Observación")], rows=out_rows))
    inds.append(ind(g, "chlorine_ok", ok_pct(cl), ok_pct(clp), nd=1,
                    note=(f"{len(cl)} mediciones · {len(out_rows)} fuera de rango" +
                          ("" if g.st.chlorine_verified else " · rango «no verificado»")) if cl else None,
                    chart=Chart(title="Cloro residual libre (promedio mensual)", x=g.months, unit="mg/L",
                                series=[Series(name="Promedio", values=[_r(mean(per_day[m])) if per_day.get(m) else None for m in g.months]),
                                        Series(name="Mínimo", values=[_r(min(per_day[m])) if per_day.get(m) else None for m in g.months])],
                                reference=lo, reference_label=f"Mínimo {lo:g} mg/L".replace(".", ",")),
                    table="cloro",
                    empty=None if cl else EmptyState(missing="Mediciones de cloro residual libre",
                                                     how="Registro «Cloro residual» (formulario o plantilla)", record="cloro")))

    # Reclamos
    rc = [r for r in rec.list_rows(g.session, g.project, "reclamos", g.start, g.end) if g.in_filter(r.client)]
    rcp = [r for r in rec.list_rows(g.session, g.project, "reclamos", g.pstart, g.pend) if g.in_filter(r.client)]

    def resp(rows):
        v = [(r.responded_at - r.received_at).total_seconds() / 3600 for r in rows if r.responded_at]
        return mean(v) if v else None
    by_type = Counter(r.kind for r in rc)
    by_status = Counter(r.status for r in rc)
    spec_r = rec.SPECS["reclamos"]
    tables.append(Table(key="reclamos", title="Reclamos", columns=[
        Column(key="received_at", label="Fecha"), Column(key="client", label="Cliente"), Column(key="kind", label="Tipo"),
        Column(key="status", label="Estado"), Column(key="responded_at", label="Respuesta"),
        Column(key="response_h", label="Tiempo de respuesta", unit="h", num=True), Column(key="note", label="Detalle")],
        rows=[rec.row_out(spec_r, r) for r in rc]))
    tables.append(Table(key="reclamos_tipo", title="Reclamos por tipo y estado", columns=[
        Column(key="tipo", label="Tipo"), Column(key="n", label="Reclamos", num=True),
        Column(key="abiertos", label="Abiertos o en proceso", num=True)],
        rows=[{"tipo": k, "n": v, "abiertos": sum(1 for r in rc if r.kind == k and r.status != "cerrado")}
              for k, v in by_type.most_common()]))
    clients_rc = sorted({r.client for r in rc if r.client})
    inds.append(ind(g, "response_h", resp(rc), resp(rcp), nd=1,
                    note=f"{len(rc)} reclamos · {by_status.get('abierto', 0) + by_status.get('en proceso', 0)} abiertos" if rc else None,
                    chart=Chart(title="Reclamos por tipo", x=[k for k, _ in by_type.most_common()], unit="reclamos",
                                series=[Series(name="Reclamos", kind="bar", values=[v for _, v in by_type.most_common()])]),
                    table="reclamos", map=MapRef(type="client", ids=clients_rc) if clients_rc else None,
                    empty=None if rc else EmptyState(missing="Registro de reclamos",
                                                     how="Registro «Reclamos» (formulario o plantilla)", record="reclamos")))
    return TabResult(tab="cumplimiento", title=TITLES["cumplimiento"], period=g.period(), sector=g.sector, route=g.route,
                     indicators=inds, charts=charts, tables=tables, notes=notes,
                     extra={"chlorine_range": [lo, hi], "water_right_lps": right_lps, "water_right_m3_year": right_m3y})


# ── 6. Planificación ──

def planificacion(g: G, capacity=None) -> TabResult:
    from app.services import demand

    inds, tables, charts = [], [], []
    notes = ["Proyección del módulo de demanda (pestaña Demanda del editor); capacidades con los datos del modelo."]
    right_lps, _ = _right(g)
    tanks = [n for n in g.model.network.nodes() if n.properties.kind == "tank"] if g.model else []
    tank_m3 = 0.0
    for t in tanks:
        p = t.properties
        if p.tank_diameter and p.max_level is not None:
            tank_m3 += math.pi * p.tank_diameter ** 2 / 4 * (p.max_level - (p.min_level or 0))
    try:
        res = demand.result(g.session, g.project)
        rows = res.rows
    except Exception:  # noqa: BLE001
        rows = []
    sel = [r for r in rows if r.n in (0, 5, 10, 15, 20)]
    tables.append(Table(key="proyeccion", title="Proyección de demanda contra capacidad", columns=[
        Column(key="anio", label="Año", num=True), Column(key="n", label="Años", num=True),
        Column(key="poblacion", label="Población", unit="hab", num=True), Column(key="clientes", label="Clientes", num=True),
        Column(key="qmd", label="Caudal máximo diario", unit="L/s", num=True), Column(key="bombeo", label="Caudal de bombeo", unit="L/s", num=True),
        Column(key="pozo", label="Capacidad del pozo", unit="L/s", num=True), Column(key="regulacion", label="Regulación requerida", unit="m³", num=True),
        Column(key="estanque", label="Volumen útil del estanque", unit="m³", num=True)],
        rows=[{"anio": r.year, "n": r.n, "poblacion": round(r.population), "clientes": round(r.clients),
               "qmd": _r(r.qmd_lps, 3), "bombeo": _r(r.pump_lps, 3), "pozo": right_lps, "regulacion": _r(r.regulation_m3, 1),
               "estanque": _r(tank_m3, 1) if tanks else None} for r in sel]))
    r20 = next((r for r in rows if r.n == 20), rows[-1] if rows else None)
    r10 = next((r for r in rows if r.n == 10), None)
    inds.append(ind(g, "demand_vs_well", r20.pump_lps / right_lps * 100 if r20 and right_lps else None, nd=1,
                    note=(f"A 10 años: {r10.pump_lps:.2f} L/s · a 20 años: {r20.pump_lps:.2f} L/s de bombeo".replace(".", ",")
                          if r10 and r20 else None),
                    chart=Chart(title="Caudal de bombeo proyectado y capacidad del pozo", x=[str(r.year) for r in rows],
                                unit="L/s", series=[Series(name="Bombeo requerido", values=[_r(r.pump_lps, 3) for r in rows]),
                                                    Series(name="Caudal máximo diario", values=[_r(r.qmd_lps, 3) for r in rows])],
                                reference=right_lps, reference_label="Capacidad del pozo (autorizado)"),
                    table="proyeccion",
                    empty=None if rows and right_lps else EmptyState(
                        missing="Proyección de demanda" if not rows else "Caudal autorizado del pozo",
                        how="Pestaña «Demanda» del editor" if not rows else "Propiedades del pozo en el editor")))
    if tanks and r20:
        inds.append(ind(g, "tank_capacity", tank_m3 / r20.regulation_m3 * 100 if r20.regulation_m3 else None,
                        label="Estanque / regulación a 20 años", unit="%", nd=1, table="proyeccion",
                        note=f"{tank_m3:.0f} m³ útiles; se requieren {r20.regulation_m3:.0f} m³".replace(".", ",")))
    # Capacidad remanente (simulaciones)
    if capacity is not None:
        inds.append(ind(g, "capacity", float(capacity.capacity), nd=0,
                        note=(f"Cliente típico {capacity.typical_m3_month:.1f} m³/mes · presión mínima {capacity.pmin:g} m · "
                              f"primer cuello de botella: {capacity.bottleneck_node or '—'}"
                              f"{' (tramo ' + capacity.bottleneck_link + ')' if capacity.bottleneck_link else ''}").replace(".", ","),
                        table="capacidad",
                        chart=Chart(title="Clientes agregados por nudo", x=list(capacity.by_node), unit="clientes",
                                    series=[Series(name="Clientes", kind="bar", values=list(capacity.by_node.values()))]),
                        map=MapRef(type="node", ids=[capacity.bottleneck_node] if capacity.bottleneck_node else list(capacity.by_node))))
        tables.append(Table(key="capacidad", title="Capacidad remanente: pasos de la simulación", columns=[
            Column(key="clients", label="Clientes nuevos", num=True), Column(key="node", label="Nudo"),
            Column(key="min_pressure", label="Presión mínima", unit="m", num=True), Column(key="min_node", label="Nudo crítico")],
            rows=[s.model_dump() for s in capacity.steps]))
    # Historial de factibilidades
    fz = list(g.session.scalars(select(FeasibilityRecord).where(FeasibilityRecord.project_id == g.project.id)
                                .order_by(FeasibilityRecord.created_at.desc())))
    tables.append(Table(key="factibilidades", title="Historial de factibilidades", columns=[
        Column(key="fecha", label="Fecha"), Column(key="nombre", label="Solicitante"), Column(key="tramo", label="Tramo"),
        Column(key="consumo", label="Consumo", unit="L/s", num=True), Column(key="resultado", label="Resultado"),
        Column(key="presion", label="Presión en el punto", unit="m", num=True), Column(key="version", label="Versión", num=True),
        Column(key="por", label="Usuario")],
        rows=[{"fecha": f.created_at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M"), "nombre": f.name, "tramo": f.link_id,
               "consumo": f.consumption_lps, "resultado": "FACTIBLE" if f.feasible else "NO FACTIBLE",
               "presion": _r(f.pressure_new), "version": f.model_version, "por": f.created_by} for f in fz]))
    fz_cur = [f for f in fz if g.start <= f.created_at.date() <= g.end]
    inds.append(ind(g, "feasibilities", float(len(fz_cur)) if fz else None, label="Factibilidades evaluadas", unit="solicitudes",
                    nd=0, note=f"{sum(1 for f in fz_cur if f.feasible)} factibles" if fz_cur else None, table="factibilidades",
                    map=MapRef(type="link", ids=sorted({f.link_id for f in fz_cur})) if fz_cur else None,
                    empty=None if fz else EmptyState(missing="Factibilidades evaluadas",
                                                     how="Herramienta «Factibilidad» del editor (cada evaluación queda registrada)")))
    # Inversiones sugeridas
    inv = []
    ss = summ.settings_of(g.project)
    if g.model is not None:
        pipes = [lk for lk in g.model.network.links() if lk.properties.kind == "pipe"]
        ages = [scalc.PipeAge(lk.id, lk.properties.material, lk.properties.dn,
                              lk.properties.length_hydraulic_m or lk.properties.length_plan_m or 0.0, lk.properties.install_year)
                for lk in pipes]
        for y, km, cost, ids in scalc.renewal_plan(ages, ss.service_life, ss.default_life, g.today.year, 10,
                                                   [(p.material, p.dn_max, p.price_m) for p in ss.prices]):
            inv.append({"origen": "Plan de renovación", "anio": y, "detalle": f"Renovar {km:.2f} km: {', '.join(ids)}".replace(".", ","),
                        "costo": cost, "verificado": "sí" if ss.prices_verified else "no verificado"})
        try:
            from app.services import diagnosis

            d = diagnosis.diagnose(g.session, g.project, None)
            for s in d.suggestions:
                inv.append({"origen": "Diagnóstico", "anio": g.today.year, "detalle": s.text, "costo": None,
                            "verificado": "sí" if s.verified else "no verificado"})
        except Exception:  # noqa: BLE001 — sin simulación no hay diagnóstico
            notes.append("Sin diagnóstico hidráulico (la red no se puede simular): solo se listan las renovaciones.")
    tables.append(Table(key="inversiones", title="Inversiones sugeridas", columns=[
        Column(key="origen", label="Origen"), Column(key="anio", label="Año", num=True), Column(key="detalle", label="Detalle"),
        Column(key="costo", label="Costo", unit="CLP", num=True), Column(key="verificado", label="Verificación")], rows=inv))
    return TabResult(tab="planificacion", title=TITLES["planificacion"], period=g.period(), sector=g.sector, route=g.route,
                     indicators=inds, charts=charts, tables=tables, notes=notes,
                     extra={"capacity": capacity.model_dump() if capacity is not None else None})


# ── 7. Equipo ──

ACTION_LABEL = {"red.version": "Guardó una versión del modelo", "exportacion": "Exportó", "importacion": "Importó"}


def equipo(g: G) -> TabResult:
    inds, tables, charts, notes = [], [], [], []
    members = g.session.execute(select(User.email, User.name, Membership.role, Membership.active)
                                .join(Membership, Membership.user_id == User.id)
                                .where(Membership.org_id == g.project.org_id).order_by(User.email)).all()
    from app.services.auth import ROLE_LABEL

    tables.append(Table(key="usuarios", title="Usuarios del proyecto (organización)", columns=[
        Column(key="email", label="Correo"), Column(key="nombre", label="Nombre"), Column(key="rol", label="Rol"),
        Column(key="activo", label="Activo")],
        rows=[{"email": e, "nombre": n, "rol": ROLE_LABEL.get(r, r), "activo": "sí" if a else "no"} for e, n, r, a in members]))
    logs = list(g.session.scalars(select(AuditLog).where(AuditLog.project_id == g.project.id,
                                                         AuditLog.created_at >= _dt(g.start), AuditLog.created_at < _end_dt(g.end))
                                  .order_by(AuditLog.created_at.desc()).limit(5000)))
    plogs = g.session.scalar(select(func.count()).select_from(AuditLog).where(
        AuditLog.project_id == g.project.id, AuditLog.created_at >= _dt(g.pstart), AuditLog.created_at < _end_dt(g.pend)))
    recent = list(g.session.scalars(select(AuditLog).where(AuditLog.project_id == g.project.id)
                                    .order_by(AuditLog.created_at.desc()).limit(200)))
    per_user_day: Counter = Counter((x.user_email or "sistema", x.created_at.date().isoformat()) for x in logs)
    tables.append(Table(key="actividad", title="Actividad por usuario y fecha", columns=[
        Column(key="usuario", label="Usuario"), Column(key="fecha", label="Fecha"), Column(key="acciones", label="Acciones", num=True)],
        rows=[{"usuario": u, "fecha": d, "acciones": n} for (u, d), n in sorted(per_user_day.items(), key=lambda kv: (kv[0][1], kv[0][0]), reverse=True)]))
    tables.append(Table(key="acciones", title="Últimas acciones (todas las fechas)", columns=[
        Column(key="fecha", label="Fecha"), Column(key="usuario", label="Usuario"), Column(key="accion", label="Acción"),
        Column(key="version", label="Versión", num=True), Column(key="detalle", label="Detalle")],
        rows=[{"fecha": x.created_at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M"), "usuario": x.user_email or "sistema",
               "accion": ACTION_LABEL.get(x.action, x.action), "version": x.version,
               "detalle": ", ".join(f"{k}: {v}" for k, v in (x.detail or {}).items())[:160]} for x in recent]))
    per_month = Counter(calc.month_key(x.created_at) for x in logs)
    per_user = Counter(x.user_email or "sistema" for x in logs)
    inds.append(ind(g, "activity", float(len(logs)), float(plogs or 0), label="Acciones registradas", unit="acciones", nd=0,
                    note=(f"{len(per_user)} usuarios activos en el período" if logs else
                          f"Última actividad: {recent[0].created_at.astimezone(timezone.utc).strftime('%Y-%m-%d')} (fuera del período)"
                          if recent else None),
                    chart=Chart(title="Acciones por usuario", x=list(per_user), unit="acciones",
                                series=[Series(name="Acciones", kind="bar", values=list(per_user.values()))]),
                    table="actividad",
                    empty=None if logs or recent else EmptyState(missing="Actividad registrada del proyecto",
                                                       how="Se registra al guardar versiones, importar y exportar")))
    charts.append(_month_chart("Acciones por mes", g.months, {"Acciones": dict(per_month)}, "acciones"))
    tasks = list(g.session.scalars(select(MaintenanceTask).where(MaintenanceTask.project_id == g.project.id)
                                   .order_by(MaintenanceTask.next_date)))
    spec = rec.SPECS["mantenciones"]
    rows = [rec.row_out(spec, t, g.today) for t in tasks]
    tables.append(Table(key="tareas", title="Tareas asignadas (mantenciones y reparaciones)", columns=[
        Column(key="assignee", label="Responsable"), Column(key="kind", label="Tipo"), Column(key="element", label="Elemento"),
        Column(key="description", label="Descripción"), Column(key="next_date", label="Fecha"), Column(key="status", label="Estado")],
        rows=sorted(rows, key=lambda r: (r["assignee"] or "~", r["next_date"]))))
    overdue = [r for r in rows if r["status"] == "atrasada"]
    per_assignee = Counter(r["assignee"] or "sin asignar" for r in rows if r["status"] != "hecha")
    inds.append(ind(g, "tasks_overdue", float(len(overdue)) if rows else None, nd=0,
                    note=f"{sum(per_assignee.values())} tareas vigentes" if rows else None,
                    chart=Chart(title="Tareas vigentes por responsable", x=list(per_assignee), unit="tareas",
                                series=[Series(name="Tareas", kind="bar", values=list(per_assignee.values()))]),
                    table="tareas", map=_element_ref(g, sorted({r["element"] for r in overdue if r["element"]})),
                    empty=None if rows else EmptyState(missing="Tareas asignadas", how="Registro «Mantenciones y tareas»",
                                                       record="mantenciones")))
    return TabResult(tab="equipo", title=TITLES["equipo"], period=g.period(), sector=g.sector, route=g.route,
                     indicators=inds, charts=charts, tables=tables, notes=notes)


TABS = {"operacion": operacion, "clientes": clientes, "perdidas": perdidas, "activos": activos,
        "cumplimiento": cumplimiento, "planificacion": planificacion, "equipo": equipo}


def build(session: Session, project: Project, tab: str, start: date, end: date, sector: str | None = None,
          route: str | None = None, capacity=None) -> TabResult:
    g = context(session, project, start, end, sector, route)
    if tab == "planificacion":
        return planificacion(g, capacity)
    return TABS[tab](g)


def table_of(res: TabResult, key: str) -> Table | None:
    return next((t for t in res.tables if t.key == key), None)


def table_xlsx(t: Table, project_name: str, res: TabResult) -> bytes:
    import io

    from openpyxl import Workbook
    from openpyxl.styles import Font

    wb = Workbook()
    ws = wb.active
    ws.title = t.title[:31].replace("/", "-")
    ws.append([f"{project_name} — {t.title}"])
    ws.append([f"Período {res.period.start.isoformat()} a {res.period.end.isoformat()}"
               + (f" · sector {res.sector}" if res.sector else "") + (f" · ruta {res.route}" if res.route else "")])
    ws.append([])
    ws.append([c.label + (f" ({c.unit})" if c.unit else "") for c in t.columns])
    for r in t.rows:
        ws.append([r.get(c.key) for c in t.columns])
    ws["A1"].font = Font(bold=True, size=13)
    for i in range(1, len(t.columns) + 1):
        ws.cell(4, i).font = Font(bold=True)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def table_csv(t: Table) -> bytes:
    import csv
    import io

    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow([c.label + (f" ({c.unit})" if c.unit else "") for c in t.columns])
    for r in t.rows:
        w.writerow([rec._csv(r.get(c.key)) for c in t.columns])
    return ("﻿" + buf.getvalue()).encode("utf-8")
