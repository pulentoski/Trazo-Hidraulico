"""Informe técnico imprimible (HTML): datos del proyecto, criterios, resultados, gráficos principales y diagnóstico."""
from __future__ import annotations

import html
import math
from datetime import datetime

from sqlalchemy.orm import Session

from app.hydraulic.version import engine_info
from app.models import Project
from app.services import design
from app.services.diagnosis import diagnose
from app.services.network import get_version_or_404, load_model
from app.services.simulation import simulate_version

e = html.escape
COLORS = ["#0b6aa8", "#e07b00", "#2e9d5b", "#c0362c"]
SEV = {"ok": ("✔", "#2e7d4f"), "warning": ("▲", "#b36b00"), "problem": ("✖", "#c0362c")}


def _f(x, nd=2):
    if x is None or (isinstance(x, float) and not math.isfinite(x)):
        return "—"
    return f"{x:,.{nd}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def svg_chart(title: str, x: list[float], series: list[tuple[str, list[float]]], ylabel: str,
              ref: tuple[float, str] | None = None, w: int = 640, h: int = 220) -> str:
    vals = [v for _, s in series for v in s if v is not None and math.isfinite(v)] + ([ref[0]] if ref else [])
    if not vals or not x:
        return ""
    y0, y1 = min(vals), max(vals)
    if y0 == y1:
        y0, y1 = y0 - 1, y1 + 1
    pad = (y1 - y0) * 0.08
    y0, y1 = y0 - pad, y1 + pad
    ml, mr, mt, mb = 52, 12, 34, 30
    xa, xb = min(x), max(x) or 1

    def sx(v):
        return ml + (v - xa) / ((xb - xa) or 1) * (w - ml - mr)

    def sy(v):
        return h - mb - (v - y0) / (y1 - y0) * (h - mt - mb)

    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="100%" font-family="system-ui" font-size="11">',
             f'<text x="{ml}" y="15" font-size="13" font-weight="600">{e(title)}</text>']
    for i in range(5):
        v = y0 + (y1 - y0) * i / 4
        parts.append(f'<line x1="{ml}" x2="{w - mr}" y1="{sy(v):.1f}" y2="{sy(v):.1f}" stroke="#dde3ea"/>'
                     f'<text x="{ml - 5}" y="{sy(v) + 4:.1f}" text-anchor="end" fill="#5f6f7f">{_f(v, 1)}</text>')
    for t in sorted(set(int(v) for v in x))[:: max(1, len(x) // 12)]:
        parts.append(f'<text x="{sx(t):.1f}" y="{h - mb + 14}" text-anchor="middle" fill="#5f6f7f">{t}</text>')
    parts.append(f'<text x="{(w) / 2}" y="{h - 3}" text-anchor="middle" fill="#5f6f7f">Hora</text>'
                 f'<text transform="translate(12,{h / 2}) rotate(-90)" text-anchor="middle" fill="#5f6f7f">{e(ylabel)}</text>')
    if ref:
        parts.append(f'<line x1="{ml}" x2="{w - mr}" y1="{sy(ref[0]):.1f}" y2="{sy(ref[0]):.1f}" stroke="#c0362c" '
                     f'stroke-dasharray="6 4"/><text x="{w - mr - 4}" y="{sy(ref[0]) - 4:.1f}" text-anchor="end" '
                     f'fill="#c0362c">{e(ref[1])}</text>')
    for i, (name, s) in enumerate(series):
        pts = " ".join(f"{sx(xv):.1f},{sy(v):.1f}" for xv, v in zip(x, s) if v is not None)
        col = COLORS[i % len(COLORS)]
        parts.append(f'<polyline points="{pts}" fill="none" stroke="{col}" stroke-width="2"/>'
                     f'<text x="{ml + 8 + i * 170}" y="{mt - 6}" fill="{col}">— {e(name)}</text>')
    parts.append("</svg>")
    return "".join(parts)


def build(session: Session, project: Project, number: int | None) -> str:
    version = get_version_or_404(session, project, number)
    model = load_model(session, version)
    res = simulate_version(session, project, version.number)
    diag = diagnose(session, project, version.number)
    params = design.effective(session, project)
    x = [t / 3600 for t in res.times]
    net = model.network
    junctions = [n for n in net.nodes() if n.properties.kind == "junction" and n.id in res.nodes]
    tanks = [n for n in net.nodes() if n.properties.kind == "tank" and n.id in res.nodes]
    pumps = [lk for lk in net.links() if lk.properties.kind == "pump" and lk.id in res.links]
    pmin = diag.criteria.get("presion_minima_m")

    charts = []
    for t in tanks:
        charts.append(svg_chart(f"Estanque {t.id}: nivel (m)", x, [("Nivel", res.nodes[t.id].pressure)], "Nivel (m)",
                                (t.properties.max_level, "Nivel máximo") if t.properties.max_level is not None else None))
    if junctions:
        worst = min(junctions, key=lambda n: min(res.nodes[n.id].pressure))
        charts.append(svg_chart(f"Presión del nudo más desfavorable ({worst.id})", x,
                                [("Presión", res.nodes[worst.id].pressure)], "Presión (m)",
                                (pmin, f"Mínimo {_f(pmin, 0)} m") if pmin is not None else None))
    for p in pumps:
        charts.append(svg_chart(f"Caudal de la bomba {p.id}", x, [("Caudal", res.links[p.id].flow)], "Caudal (L/s)"))
    charts = [c for c in charts if c and len(x) > 1]

    def ref_text(refs):
        return " ".join(f'<span class="ref">{e(r.id)}</span>' for r in refs)

    diag_html = "".join(
        f'<li style="color:{SEV[i.severity][1]}"><b>{SEV[i.severity][0]}</b> <span style="color:#1b2733">{e(i.text)}</span> '
        f'{ref_text(i.refs)}</li>' for i in diag.items)
    sug_html = "".join(f"<li><b>{e(s.text)}</b><br><span class='muted'>{e(s.verification)}</span></li>"
                       for s in diag.suggestions) or "<li>Sin sugerencias: no hay problemas que corregir.</li>"
    rows_nodes = "".join(
        f"<tr><td>{e(n.id)}</td><td>{_f(n.properties.elevation)}</td><td>{_f(min(res.nodes[n.id].pressure))}</td>"
        f"<td>{_f(max(res.nodes[n.id].pressure))}</td><td>{_f(max(res.nodes[n.id].demand), 3)}</td></tr>"
        for n in sorted(junctions, key=lambda n: min(res.nodes[n.id].pressure))[:25])
    pipes = [lk for lk in net.links() if lk.properties.kind == "pipe" and lk.id in res.links]
    rows_links = "".join(
        f"<tr><td>{e(lk.id)}</td><td>{e(lk.properties.material or '—')} {lk.properties.dn or ''}</td>"
        f"<td>{_f(lk.properties.length_hydraulic_m, 1)}</td><td>{_f(max(abs(v) for v in res.links[lk.id].flow), 3)}</td>"
        f"<td>{_f(max(abs(v) for v in res.links[lk.id].velocity))}</td>"
        f"<td>{_f(max(abs(v) for v in res.links[lk.id].headloss))}</td></tr>"
        for lk in sorted(pipes, key=lambda lk: -max(abs(v) for v in res.links[lk.id].headloss))[:25])
    crit = "".join(f"<tr><td>{e(p.label)}</td><td>{_f(p.value) if isinstance(p.value, float) else e(str(p.value))}</td>"
                   f"<td>{e(p.unit or '')}</td><td>{'verificado' if p.verified else 'no verificado'}</td></tr>"
                   for p in params if p.group == "criterio")
    eng = engine_info()
    opts = model.options
    sim = (f"Período extendido de {_f(opts.duration_h, 0)} h, paso hidráulico {opts.hydraulic_step_min} min"
           if opts.duration_h else "Régimen permanente")
    return f"""<!doctype html><html lang="es"><head><meta charset="utf-8"><title>Informe técnico — {e(project.name)}</title>
<style>body{{font:13.5px/1.45 system-ui,sans-serif;max-width:900px;margin:24px auto;color:#1b2733}}h1{{font-size:22px;margin:0}}
h2{{font-size:16px;border-bottom:2px solid #0b6aa8;padding-bottom:3px;margin-top:22px}}table{{border-collapse:collapse;width:100%;margin:6px 0}}
td,th{{border:1px solid #ccd5de;padding:3px 7px;text-align:right}}td:first-child,th:first-child{{text-align:left}}th{{background:#eef2f6}}
.muted{{color:#5f6f7f}}.ref{{font-family:monospace;background:#eef2f6;border-radius:3px;padding:0 4px;margin-left:2px;font-size:12px}}
.status{{font-size:18px;font-weight:700;padding:6px 10px;border-radius:6px;display:inline-block}}
.cumple{{background:#e3f4ea;color:#2e7d4f}}.obs{{background:#fff4e0;color:#b36b00}}.no{{background:#fde8e6;color:#c0362c}}
ul{{padding-left:20px}}li{{margin:4px 0}}@media print{{body{{margin:0}}h2{{break-after:avoid}}svg{{break-inside:avoid}}}}</style></head>
<body><h1>Informe técnico — {e(project.name)}</h1>
<p class="muted">Versión {version.number} del modelo · {datetime.now().strftime('%d-%m-%Y %H:%M')} · Motor OWA-EPANET {e(eng.get('wheel_version') or '')}
· {e(sim)} · Fórmula {e(opts.headloss)} · Análisis {e(opts.demand_model)}{f" · demandas × {_f(opts.demand_multiplier, 3)}" if opts.demand_multiplier != 1 else ""}</p>
<p>{e(project.description or '')}</p>
<h2>Diagnóstico</h2>
<p><span class="status {'cumple' if diag.status == 'cumple' else 'obs' if diag.status == 'cumple con observaciones' else 'no'}">{e(diag.status.capitalize())}</span></p>
<p>{e(diag.summary.text)}</p><ul>{diag_html}</ul>
<h3>Sugerencias (verificadas con simulación)</h3><ul>{sug_html}</ul>
<h2>Datos del proyecto</h2><table>
<tr><th>Nudos</th><td>{len(net.nodes())}</td><th>Tramos</th><td>{len(net.links())}</td><th>Clientes</th><td>{len(net.clients())}</td></tr>
<tr><th>Red (km)</th><td>{_f(sum(lk.properties.length_hydraulic_m or 0 for lk in pipes) / 1000, 2)}</td><th>Estanques</th><td>{len(tanks)}</td><th>Bombas</th><td>{len(pumps)}</td></tr></table>
<h2>Criterios de diseño</h2><table><tr><th>Criterio</th><th>Valor</th><th>Unidad</th><th>Estado</th></tr>{crit}</table>
<h2>Gráficos principales</h2>{''.join(charts) or '<p class="muted">Simulación estática: sin series horarias.</p>'}
<h2>Resultados por nudo (más desfavorables)</h2><table><tr><th>Nudo</th><th>Cota (m)</th><th>Presión mín. (m)</th><th>Presión máx. (m)</th><th>Demanda máx. (L/s)</th></tr>{rows_nodes}</table>
<h2>Resultados por tramo (mayor pérdida)</h2><table><tr><th>Tramo</th><th>Material DN</th><th>Largo (m)</th><th>Caudal máx. (L/s)</th><th>Velocidad máx. (m/s)</th><th>Pérdida máx. (m/km)</th></tr>{rows_links}</table>
<p class="muted">Generado por Trazo Hidráulico a partir de la corrida {e(str(res.run_id))}. Los criterios marcados «no verificado» deben revisarse.</p>
</body></html>"""
