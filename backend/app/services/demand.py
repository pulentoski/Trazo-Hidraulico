"""Demanda sanitaria: proyección anual de población y caudales de diseño, y escenarios de demanda.

Reproduce la hoja «Proyecc10-30HospChamp» de la planilla ModeloEstanque (docs/referencias/analisis-planillas.md):
población → clientes → consumo → producción (con pérdidas) → Qmedio, QMD, QMH, caudal de bombeo y volumen de
regulación. Todos los valores son editables y quedan «no verificado».

Los escenarios de demanda (año actual, año horizonte) escalan las demandas de nudos y clientes con el
multiplicador global de EPANET (DEMAND MULTIPLIER): población del año / población del año que representa el
modelo, por el coeficiente de día de máximo consumo si se indica.
"""
from __future__ import annotations

import calendar
import io
from datetime import date

from sqlalchemy.orm import Session

from app.models import Project
from app.repositories import projects as projects_repo
from app.schemas.demand import DemandInputs, DemandResult, DemandRow, DemandScenario, GrowthStep
from app.services import design
from app.services.errors import NotFound
from app.services.network import create_version, load_model

NOT_VERIFIED = ("Valores de partida típicos (planilla ModeloEstanque y parámetros de diseño del proyecto): "
                "no verificados. Revíselos antes de usarlos en un diseño.")


def defaults(session: Session, project: Project) -> DemandInputs:
    params = {p.key: p.value for p in design.effective(session, project)}
    year = date.today().year
    return DemandInputs(
        base_year=year, model_year=year, current_year=year, base_mode="arranques", base_connections=100,
        base_population=None, persons_per_dwelling=float(params.get("densidad", 5.0)), extra_population=0.0,
        growth=[GrowthStep(from_year=year + 1, rate_pct=1.5)], additions=[], horizon_years=20,
        dotation_lphd=float(params.get("dotacion", 150.0)), losses_pct=float(params.get("perdidas", 20.0)),
        coef_day=float(params.get("coef_max_diario", 1.5)), coef_hour=float(params.get("coef_max_horario", 1.5)),
        pump_hours=12.0, regulation_pct=20.0, scenario_peak_day=False,
    )


def inputs_for(session: Session, project: Project) -> tuple[DemandInputs, bool]:
    if project.demand_projection:
        return DemandInputs.model_validate(project.demand_projection), True
    return defaults(session, project), False


def compute(inp: DemandInputs) -> list[DemandRow]:
    base = (inp.base_population if inp.base_mode == "poblacion" and inp.base_population is not None
            else (inp.base_connections or 0) * inp.persons_per_dwelling) + inp.extra_population
    rates = sorted(inp.growth, key=lambda g: g.from_year)
    adds: dict[int, float] = {}
    for a in inp.additions:
        adds[a.year] = adds.get(a.year, 0.0) + a.dwellings * inp.persons_per_dwelling
    rows: list[DemandRow] = []
    pop = base
    for n in range(inp.horizon_years + 1):
        year = inp.base_year + n
        if n > 0:
            rate = next((g.rate_pct for g in reversed(rates) if year >= g.from_year), 0.0)
            pop = pop * (1 + rate / 100)
        pop_y = pop + adds.get(year, 0.0)
        pop = pop_y
        days = 366 if calendar.isleap(year) else 365
        consumption = pop_y * inp.dotation_lphd / 1000 * days  # m³/año
        production = consumption / (1 - inp.losses_pct / 100)
        qmed = production / days / 86400 * 1000
        qmd = qmed * inp.coef_day
        rows.append(DemandRow(
            n=n, year=year, population=pop_y, clients=pop_y / inp.persons_per_dwelling, consumption_m3=consumption,
            production_m3=production, qmed_lps=qmed, qmd_lps=qmd, qmh_lps=qmd * inp.coef_hour,
            pump_lps=qmd * 24 / inp.pump_hours if inp.pump_hours > 0 else 0.0,
            regulation_m3=qmd * 86.4 * inp.regulation_pct / 100))
    return rows


def _row_for(rows: list[DemandRow], year: int) -> DemandRow:
    if year <= rows[0].year:
        return rows[0]
    return next((r for r in rows if r.year == year), rows[-1])


def scenarios(inp: DemandInputs, rows: list[DemandRow]) -> list[DemandScenario]:
    ref = _row_for(rows, inp.model_year).population or 1.0
    coef = inp.coef_day if inp.scenario_peak_day else 1.0
    out = [DemandScenario(id="base", name=f"Demanda del modelo ({inp.model_year})", year=inp.model_year,
                          multiplier=1.0)]
    for sid, name, year in (("actual", "Año actual", inp.current_year),
                            ("horizonte", "Año horizonte", inp.base_year + inp.horizon_years)):
        r = _row_for(rows, year)
        out.append(DemandScenario(id=sid, name=f"{name} ({r.year})", year=r.year,
                                  multiplier=round(r.population / ref * coef, 6)))
    return out


def result(session: Session, project: Project) -> DemandResult:
    inp, saved = inputs_for(session, project)
    rows = compute(inp)
    latest = projects_repo.get_version(session, project.id, None)
    opts = latest.options if latest else {}
    return DemandResult(project_id=str(project.id), inputs=inp, customized=saved, verified=False, note=NOT_VERIFIED,
                        rows=rows, scenarios=scenarios(inp, rows),
                        active_scenario=opts.get("demand_scenario"), active_multiplier=opts.get("demand_multiplier", 1.0))


def save_inputs(session: Session, project: Project, inp: DemandInputs) -> DemandResult:
    project.demand_projection = inp.model_dump(mode="json")
    session.commit()
    return result(session, project)


def apply_scenario(session: Session, project: Project, scenario_id: str) -> tuple[int, float]:
    """Crea una versión con el multiplicador de demanda del escenario (base = 1)."""
    inp, _ = inputs_for(session, project)
    sc = next((s for s in scenarios(inp, compute(inp)) if s.id == scenario_id), None)
    if sc is None:
        raise NotFound(f"Escenario de demanda «{scenario_id}» no encontrado")
    latest = projects_repo.get_version(session, project.id, None)
    if latest is None:
        raise NotFound("El proyecto no tiene versiones")
    model = load_model(session, latest)
    model.options.demand_multiplier = sc.multiplier
    model.options.demand_scenario = None if sc.id == "base" else sc.id
    v = create_version(session, project, model, kind="manual", label=f"Escenario de demanda: {sc.name}", parent=latest)
    session.commit()
    return v.number, sc.multiplier


def export_xlsx(res: DemandResult) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font

    wb = Workbook()
    ws = wb.active
    ws.title = "Proyección"
    ws.append(["Proyección de demanda — " + res.note])
    ws.cell(1, 1).font = Font(italic=True, color="9C5700")
    i = res.inputs
    params = [("Año base", i.base_year), ("Habitantes por vivienda", i.persons_per_dwelling),
              ("Dotación (L/hab/día)", i.dotation_lphd), ("Pérdidas (%)", i.losses_pct),
              ("Coef. día máximo consumo", i.coef_day), ("Coef. hora máximo consumo", i.coef_hour),
              ("Horas de bombeo", i.pump_hours), ("Regulación (% del volumen diario a QMD)", i.regulation_pct),
              ("Tasas de crecimiento", "; ".join(f"desde {g.from_year}: {g.rate_pct} %" for g in i.growth))]
    for k, v in params:
        ws.append([k, v])
    ws.append([])
    head = ["Año", "n", "Población (hab)", "Clientes", "Consumo (m³/año)", "Producción (m³/año)", "Qmedio (L/s)",
            "QMD (L/s)", "QMH (L/s)", "Caudal de bombeo (L/s)", "Volumen de regulación (m³)"]
    ws.append(head)
    for c in range(1, len(head) + 1):
        ws.cell(ws.max_row, c).font = Font(bold=True)
    for r in res.rows:
        ws.append([r.year, r.n, round(r.population, 1), round(r.clients, 1), round(r.consumption_m3, 1),
                   round(r.production_m3, 1), round(r.qmed_lps, 3), round(r.qmd_lps, 3), round(r.qmh_lps, 3),
                   round(r.pump_lps, 3), round(r.regulation_m3, 1)])
    ws.append([])
    ws.append(["Escenarios de demanda", "Año", "Multiplicador"])
    for s in res.scenarios:
        ws.append([s.name, s.year, s.multiplier])
    for col, w in zip("ABCDEFGHIJK", (34, 6, 16, 10, 17, 19, 13, 11, 11, 20, 24)):
        ws.column_dimensions[col].width = w
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
