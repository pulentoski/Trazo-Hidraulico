"""Informe mensual para la directiva del APR: lo principal de cada pestaña de «Gestión» en un HTML imprimible
(PDF desde el navegador) y en Excel, con fecha de emisión, período y versión del modelo."""
from __future__ import annotations

import io
from datetime import date, datetime
from html import escape
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.models import Project
from app.schemas.gestion import Chart, Indicator, TabResult, Table
from app.services import gestion

TZ = ZoneInfo("America/Santiago")
KEY_TABLES = {"operacion": ["energia", "pozo"], "clientes": ["movimientos", "mayores"], "perdidas": ["anc", "criticos"],
              "activos": ["atrasadas", "renovacion"], "cumplimiento": ["extraccion", "cortes", "cloro", "reclamos_tipo"],
              "planificacion": ["proyeccion", "inversiones"], "equipo": ["tareas"]}
MAX_ROWS = 15
STATUS = {"bueno": "Bueno", "regular": "Regular", "malo": "Malo"}


def build_all(session: Session, project: Project, start: date, end: date, sector: str | None, route: str | None) -> list[TabResult]:
    from app.services import gestion_capacity

    cap = None
    try:
        cap = gestion_capacity.for_project(session, project, gestion.settings_of(project))
    except Exception:  # noqa: BLE001 — sin simulación: el informe sigue sin la capacidad remanente
        cap = None
    return [gestion.build(session, project, t, start, end, sector, route, capacity=cap) for t in gestion.TABS]


def _num(v, unit: str = "") -> str:
    if v is None:
        return "—"
    if isinstance(v, (int, float)):
        s = f"{v:,.2f}" if abs(v) < 1000 else f"{v:,.0f}"
        s = s.replace(",", "§").replace(".", ",").replace("§", ".")
        if s.endswith(",00"):
            s = s[:-3]
        return f"{s} {unit}".strip()
    return escape(str(v))


def _delta(i: Indicator) -> str:
    if i.delta_pct is None:
        return "—"
    arrow = "▲" if i.delta_pct > 0 else "▼" if i.delta_pct < 0 else "="
    return f"{arrow} {abs(i.delta_pct):.1f} %".replace(".", ",")


def _bars(c: Chart | None) -> str:
    """Gráfico de barras simple (SVG) con la primera serie: se imprime sin JavaScript."""
    if c is None or not c.series or not c.x:
        return ""
    vals = [v for v in c.series[0].values]
    nums = [v for v in vals if v is not None]
    if not nums:
        return ""
    hi = max(max(nums), c.reference or 0) or 1
    w, h, n = 520, 110, len(vals)
    bw = w / max(n, 1)
    parts = [f'<svg viewBox="0 0 {w} {h + 18}" class="chart" role="img" aria-label="{escape(c.title)}">']
    for k, v in enumerate(vals):
        if v is None:
            continue
        bh = max(0.0, v) / hi * h
        parts.append(f'<rect x="{k * bw + 2:.1f}" y="{h - bh:.1f}" width="{max(bw - 4, 1):.1f}" height="{bh:.1f}" />')
    if c.reference:
        y = h - c.reference / hi * h
        parts.append(f'<line x1="0" x2="{w}" y1="{y:.1f}" y2="{y:.1f}" class="ref" />')
    step = max(1, n // 12)
    for k in range(0, n, step):
        parts.append(f'<text x="{k * bw + bw / 2:.1f}" y="{h + 13}" text-anchor="middle">{escape(c.x[k][-5:])}</text>')
    parts.append("</svg>")
    return f'<figure><figcaption>{escape(c.title)}{f" ({escape(c.unit)})" if c.unit else ""}' \
           f'{f" · línea: {escape(c.reference_label or "")}" if c.reference else ""}</figcaption>{"".join(parts)}</figure>'


def _table(t: Table) -> str:
    head = "".join(f"<th>{escape(c.label)}{f' ({escape(c.unit)})' if c.unit else ''}</th>" for c in t.columns)
    body = "".join("<tr>" + "".join(f'<td class="{"num" if c.num else ""}">{_num(r.get(c.key))}</td>' for c in t.columns) + "</tr>"
                   for r in t.rows[:MAX_ROWS])
    more = f'<p class="muted">… y {len(t.rows) - MAX_ROWS} filas más (ver Excel).</p>' if len(t.rows) > MAX_ROWS else ""
    empty = '<p class="muted">Sin datos en el período.</p>' if not t.rows else ""
    return f"<h3>{escape(t.title)}</h3>{empty or f'<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'}{more}"


def to_html(project: Project, tabs: list[TabResult], version: int | None) -> str:
    p = tabs[0].period
    now = datetime.now(TZ)
    filt = " · ".join(x for x in (f"Sector: {tabs[0].sector}" if tabs[0].sector else "",
                                  f"Ruta: {tabs[0].route}" if tabs[0].route else "") if x)
    sections = []
    for t in tabs:
        rows = "".join(
            f"<tr><td>{escape(i.label)}</td><td class='num'><b>{_num(i.value, i.unit)}</b></td>"
            f"<td class='num'>{_num(i.previous, i.unit)}</td><td class='num'>{_delta(i)}</td>"
            f"<td><span class='st {i.status or ''}'>{STATUS.get(i.status or '', '—')}</span>"
            f"{'' if i.target_verified or not i.status else ' <small>meta no verificada</small>'}</td>"
            f"<td>{escape(i.note or (i.empty.missing + ': ' + i.empty.how if i.empty else ''))}</td></tr>"
            for i in t.indicators)
        charts = "".join(_bars(i.chart) for i in t.indicators[:2] if i.chart)
        tables = "".join(_table(tb) for k in KEY_TABLES.get(t.tab, []) if (tb := gestion.table_of(t, k)))
        notes = "".join(f"<p class='muted'>{escape(n)}</p>" for n in t.notes)
        sections.append(f"<section><h2>{escape(t.title)}</h2><table class='kpi'><thead><tr><th>Indicador</th><th>Valor</th>"
                        f"<th>Período anterior</th><th>Variación</th><th>Estado</th><th>Detalle</th></tr></thead>"
                        f"<tbody>{rows}</tbody></table><div class='charts'>{charts}</div>{tables}{notes}</section>")
    return f"""<!doctype html><html lang="es"><head><meta charset="utf-8"><title>Informe mensual — {escape(project.name)}</title>
<style>
body{{font:13px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif;color:#1d2733;margin:24px auto;max-width:1000px;padding:0 16px}}
h1{{font-size:22px;margin:0 0 4px}} h2{{font-size:17px;border-bottom:2px solid #0b6aa8;padding-bottom:3px;margin:26px 0 8px}}
h3{{font-size:14px;margin:14px 0 4px}} table{{border-collapse:collapse;width:100%;margin:4px 0 8px}}
th,td{{border-bottom:1px solid #d9dee5;padding:3px 6px;text-align:left;vertical-align:top}} th{{background:#f1f4f7;font-weight:600}}
td.num,th.num{{text-align:right;white-space:nowrap}} .muted{{color:#5d6b7a;font-size:12px}}
.st{{padding:1px 6px;border-radius:8px;font-size:12px}} .st.bueno{{background:#d8f0dd}} .st.regular{{background:#fbecc4}} .st.malo{{background:#f8d3d0}}
.meta{{color:#5d6b7a}} .charts{{display:flex;gap:16px;flex-wrap:wrap}} figure{{margin:4px 0;flex:1 1 300px}}
figcaption{{font-size:12px;color:#5d6b7a}} svg.chart{{width:100%;height:auto}} svg.chart rect{{fill:#0b6aa8}}
svg.chart line.ref{{stroke:#c0392b;stroke-dasharray:4 3}} svg.chart text{{font-size:9px;fill:#5d6b7a}}
section{{break-inside:avoid-page}} .noprint{{margin:8px 0}} @media print{{.noprint{{display:none}} body{{margin:0}}}}
</style></head><body>
<div class="noprint"><button onclick="window.print()">Imprimir o guardar como PDF</button></div>
<h1>Informe mensual de gestión — {escape(project.name)}</h1>
<p class="meta">Período: <b>{p.start.strftime("%d-%m-%Y")}</b> a <b>{p.end.strftime("%d-%m-%Y")}</b> (comparado con
{p.prev_start.strftime("%d-%m-%Y")} a {p.prev_end.strftime("%d-%m-%Y")}){" · " + escape(filt) if filt else ""}<br>
Emitido el {now.strftime("%d-%m-%Y %H:%M")} · Versión del modelo: {version if version is not None else "—"} · Trazo Hidráulico</p>
<p class="muted">Metas y rangos marcados «no verificado» son valores sugeridos: revíselos en «Metas» antes de usarlos para
decidir. Los formatos de cumplimiento son referenciales y no declaran cumplimiento normativo.</p>
{"".join(sections)}
</body></html>"""


def to_xlsx(project: Project, tabs: list[TabResult], version: int | None) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill

    wb = Workbook()
    ws = wb.active
    ws.title = "Indicadores"
    p = tabs[0].period
    ws.append([f"Informe mensual de gestión — {project.name}"])
    ws.append([f"Período {p.start.isoformat()} a {p.end.isoformat()} · emitido {datetime.now(TZ).strftime('%Y-%m-%d %H:%M')} · "
               f"versión del modelo {version if version is not None else '—'}"])
    ws.append([])
    ws.append(["Pestaña", "Indicador", "Valor", "Unidad", "Período anterior", "Variación (%)", "Estado", "Meta verificada", "Detalle"])
    for c in range(1, 10):
        ws.cell(4, c).font = Font(bold=True)
    ws["A1"].font = Font(bold=True, size=13)
    fills = {"bueno": "D8F0DD", "regular": "FBECC4", "malo": "F8D3D0"}
    for t in tabs:
        for i in t.indicators:
            ws.append([t.title, i.label, i.value, i.unit, i.previous, i.delta_pct, STATUS.get(i.status or "", ""),
                       "sí" if i.target_verified else "no", i.note or (f"{i.empty.missing}: {i.empty.how}" if i.empty else "")])
            if i.status:
                ws.cell(ws.max_row, 7).fill = PatternFill("solid", fgColor=fills[i.status])
    for col, wdt in zip("ABCDEFGHI", (18, 34, 12, 14, 14, 12, 10, 10, 60)):
        ws.column_dimensions[col].width = wdt
    used: set[str] = {"Indicadores"}
    for t in tabs:
        for k in KEY_TABLES.get(t.tab, []):
            tb = gestion.table_of(t, k)
            if tb is None:
                continue
            name = tb.title[:28].replace("/", "-").replace(":", "")
            while name in used:
                name = name[:26] + "_2"
            used.add(name)
            sh = wb.create_sheet(name)
            sh.append([tb.title])
            sh.append([c.label + (f" ({c.unit})" if c.unit else "") for c in tb.columns])
            for r in tb.rows:
                sh.append([r.get(c.key) for c in tb.columns])
            sh["A1"].font = Font(bold=True)
            for c in range(1, len(tb.columns) + 1):
                sh.cell(2, c).font = Font(bold=True)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
