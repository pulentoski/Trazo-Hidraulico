"""Exportación del panel general: Excel (una hoja por bloque) y HTML imprimible."""
from __future__ import annotations

import html
import io

from app.schemas.summary import SummaryResult

e = html.escape


def _f(x, nd=2) -> str:
    if x is None:
        return "—"
    return f"{x:,.{nd}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _hour(res: SummaryResult, k: int | None) -> str:
    if k is None or not res.times:
        return "—"
    t = res.times[k]
    return f"{t // 3600}:{(t % 3600) // 60:02d}"


def _scenario_name(res: SummaryResult) -> str:
    return next((s.name for s in res.scenarios if s.id == res.scenario), res.scenario)


def sections(res: SummaryResult) -> list[tuple[str, list[str], list[list]]]:
    """Bloques del resumen como tablas (título, encabezados, filas): base común de Excel y HTML."""
    c, n, p, m = res.clients, res.network, res.pressures, res.maintenance
    out: list[tuple[str, list[str], list[list]]] = []
    out.append(("Clientes", ["Indicador", "Valor"], [
        ["Total", c.total.count], ["Activos", c.active.count], ["Proyectados", c.projected.count],
        ["Suspendidos", c.suspended.count], ["N° de arranques", c.connections]]))
    out.append(("Clientes por ruta", ["Ruta", "Clientes", "Consumo activos (m³/día)"],
                [[g.key, g.count, g.m3_day] for g in c.by_route]))
    out.append(("Clientes por sector", ["Sector", "Clientes", "Consumo activos (m³/día)"],
                [[g.key, g.count, g.m3_day] for g in c.by_sector]))
    out.append(("Red", ["Indicador", "Valor"], [
        ["Km de tuberías", n.km_total], ["Tuberías", n.pipes.count], ["Válvulas de corte", n.valves.count],
        ["Válvulas de control", n.control_valves.count], ["Grifos", n.hydrants.count], ["Estanques", n.tanks.count],
        ["Pozos", n.wells.count], ["Bombas", n.pumps.count]]))
    for title, groups in (("Km por material", n.by_material), ("Km por diámetro", n.by_dn),
                          ("Km por estado", n.by_condition), ("Km por antigüedad", n.by_age)):
        out.append((title, ["Grupo", "Tramos", "Km"], [[g.key, g.count, g.km] for g in groups]))
    out.append(("Clientes por tubería", ["Tramo", "Clientes"], [[x.link, x.clients] for x in res.clients_per_pipe]))
    out.append(("Presiones", ["Indicador", "Valor"], [
        ["Escenario", _scenario_name(res)], ["Hora", _hour(res, res.period)],
        ["Presión mínima (m)", p.min.value if p.min else None], ["Nudo de presión mínima", p.min.id if p.min else None],
        ["Presión máxima (m)", p.max.value if p.max else None], ["Nudo de presión máxima", p.max.id if p.max else None],
        ["Presión promedio (m)", p.avg], [f"Nudos bajo {p.pmin:g} m", p.below_min.count],
        [f"Clientes bajo {p.pmin:g} m", p.clients_below.count], [f"Nudos sobre {p.pmax:g} m", p.above_max.count],
        ["Hora más crítica", _hour(res, p.critical_period)], ["Presión en la hora crítica (m)", p.critical_value],
        ["Nudo crítico", p.critical_node]]))
    out.append(("Zonas por presión", ["Rango (m.c.a.)", "Superficie (km²)", "Nudos", "Clientes"],
                [[r.label, r.area_km2, r.nodes.count, r.clients.count] for r in res.zones.ranges]))
    out.append(("Clientes sobre cota", ["Cliente", "Nombre", "Nudo", "Cota terreno (m)", "Cota piez. (m)",
                                        "Presión mínima (m)", "Déficit (m)"],
                [[o.client, o.name, o.node, o.ground, o.head, o.pmin, o.deficit] for o in res.over_elevation]))
    out.append(("Mayores consumidores", ["Cliente", "Nombre", "Ruta", "L/s", "m³/mes", "% del total"],
                [[x.client, x.name, x.route, x.lps, x.m3_month, x.pct] for x in res.top_consumers]))
    cs = res.consumption
    out.append(("Consumo", ["Indicador", "Valor"], [
        ["Consumo (L/s)", cs.lps], ["Consumo diario (m³)", cs.m3_day], ["Consumo mensual (m³)", cs.m3_month],
        *[[f"Proyección a {x.years} años ({x.year}), m³/día", x.m3_day] for x in cs.projection],
        ["Nota", cs.projection_note]]))
    out.append(("Consumo por sector", ["Sector", "Clientes activos", "m³/día"],
                [[g.key, g.count, g.m3_day] for g in cs.by_sector]))
    out.append(("Área operacional", ["Indicador", "Valor"], [["Margen (m)", res.area.margin_m],
                                                             ["Superficie (km²)", res.area.area_km2]]))
    lo = res.losses
    out.append(("Eventos de pérdidas", ["Fecha", "Tramo", "Tipo", "Caudal (L/s)", "Observación"],
                [[str(x.event_date), x.link_id, x.kind, x.flow_lps, x.note] for x in lo.events]))
    out.append(("Tramos con más eventos", ["Tramo", "Eventos", "Último", "Caudal estimado (L/s)"],
                [[x.link, x.events, str(x.last_date), x.flow_lps] for x in lo.top_links]))
    out.append(("Agua no contabilizada", ["Sector", "Medidores", "Producción (m³/día)", "Consumo (m³/día)",
                                          "No contabilizada (m³/día)", "ANC (%)"],
                [[b.sector, ", ".join(b.meters), b.production_m3_day, b.consumption_m3_day, b.nrw_m3_day, b.nrw_pct]
                 for b in lo.balance]))
    out.append(("Vida útil por material", ["Material", "Años", "Sugerido"],
                [[x.material, x.years, x.suggested] for x in m.life]))
    out.append(("Vencimientos", ["Horizonte", "Km", "Tramos"],
                [["Vencidos", m.expired.km, ", ".join(m.expired.ids)],
                 *[[f"En {d.years} años", d.km, ", ".join(d.ids)] for d in m.due],
                 ["En mal estado", m.bad_condition_km, ", ".join(m.bad_condition.ids)]]))
    out.append(("Plan de renovación", ["Año", "Km", "Costo (CLP)", "Tramos"],
                [[x.year, x.km, x.cost, ", ".join(x.ids)] for x in m.plan]))
    out.append(("Vencimiento por tramo", ["Tramo", "Material", "DN", "Largo (m)", "Año instalación",
                                               "Año vencimiento", "Estado", "Costo (CLP)"],
                [[x.link, x.material, x.dn, x.length_m, x.install_year, x.expiry_year, x.condition, x.cost]
                 for x in m.pipes]))
    tw = res.tank_well
    out.append(("Estanques", ["Estanque", "Volumen útil (m³)", "Consumo medio (L/s)", "Autonomía (h)",
                              "Nivel mín. (m)", "Nivel máx. (m)"],
                [[t.id, t.useful_m3, t.outflow_lps, t.autonomy_h, t.level_min, t.level_max] for t in tw.tanks]))
    out.append(("Pozos", ["Pozo", "Bomba", "Horas de bomba al día", "Caudal en marcha (L/s)", "Volumen (m³/día)",
                          "Autorizado (L/s)", "Autorizado (m³/día)", "Uso del derecho (%)"],
                [[w.id, w.pump, w.pump_hours_day, w.flow_running_lps, w.m3_day, w.authorized_lps,
                  w.authorized_m3_day, w.use_pct] for w in tw.wells]))
    out.append(("Alertas", ["Severidad", "Tema", "Mensaje", "Elemento"],
                [["Error" if a.severity == "error" else "Advertencia", a.topic, a.text, a.id] for a in res.alerts]))
    return out


def to_xlsx(res: SummaryResult, name: str) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font

    wb = Workbook()
    ws = wb.active
    ws.title = "Resumen"
    ws.append([f"Resumen del proyecto «{name}» — versión {res.model_version} — {_scenario_name(res)}, "
               f"hora {_hour(res, res.period)}"])
    ws.cell(1, 1).font = Font(bold=True)
    used: set[str] = {"Resumen"}
    for title, head, rows in sections(res):
        sheet = "".join("-" if ch in '[]:*?/\\' else ch for ch in title)[:31]
        while sheet in used:
            sheet = sheet[:29] + "_" + str(len(used))
        used.add(sheet)
        s = wb.create_sheet(sheet)
        s.append(head)
        for col in range(1, len(head) + 1):
            s.cell(1, col).font = Font(bold=True)
            s.column_dimensions[chr(64 + col)].width = 18 if col > 1 else 26
        for r in rows:
            s.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def to_html(res: SummaryResult, name: str) -> str:
    def cell(v) -> str:
        if isinstance(v, float):
            return f'<td class="n">{_f(v, 3 if abs(v) < 10 else 2)}</td>'
        if isinstance(v, int):
            return f'<td class="n">{v:,}</td>'.replace(",", ".")
        return f"<td>{e('' if v is None else str(v))}</td>"
    parts = []
    for title, head, rows in sections(res):
        body = "".join("<tr>" + "".join(cell(v) for v in r) + "</tr>" for r in rows) or \
            f'<tr><td colspan="{len(head)}" class="muted">Sin datos</td></tr>'
        parts.append(f"<section><h2>{e(title)}</h2><table><thead><tr>"
                     + "".join(f"<th>{e(h)}</th>" for h in head) + f"</tr></thead><tbody>{body}</tbody></table></section>")
    note = f'<p class="warn">{e(res.sim_note)}</p>' if res.sim_note else ""
    return f"""<!doctype html><html lang="es"><head><meta charset="utf-8"><title>Resumen — {e(name)}</title>
<style>
body{{font:13px/1.4 system-ui,sans-serif;color:#1b2733;margin:24px auto;max-width:980px;padding:0 16px}}
h1{{font-size:20px;margin:0 0 4px}} h2{{font-size:14px;margin:18px 0 6px;text-transform:uppercase;letter-spacing:.04em;color:#0b6aa8}}
table{{border-collapse:collapse;width:100%;margin-bottom:6px}} th,td{{border-bottom:1px solid #d8dee5;padding:3px 6px;text-align:left;vertical-align:top}}
th{{background:#f6f8fa;font-weight:600}} td.n{{text-align:right;font-variant-numeric:tabular-nums}} .muted{{color:#5f6f7f}}
.warn{{background:#fff4e0;border:1px solid #b36b00;padding:6px 10px;border-radius:6px}}
section{{break-inside:avoid}} @media print{{body{{margin:0}} button{{display:none}}}}
</style></head><body>
<button onclick="window.print()" style="float:right">Imprimir / PDF</button>
<h1>Resumen del proyecto — {e(name)}</h1>
<p class="muted">Versión {res.model_version} · {e(_scenario_name(res))} · hora {_hour(res, res.period)} (hora punta
{_hour(res, res.peak_period)}) · generado {res.generated_at:%Y-%m-%d %H:%M} UTC. Vida útil y precios
{"verificados" if res.maintenance.life_verified and res.maintenance.prices_verified else "«no verificado»"}.</p>
{note}{"".join(parts)}
</body></html>"""
