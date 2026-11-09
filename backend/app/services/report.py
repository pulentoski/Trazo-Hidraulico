"""Informe de factibilidad en HTML imprimible (el navegador lo guarda como PDF con «Imprimir»)."""
from html import escape
from zoneinfo import ZoneInfo

from app.schemas.analysis import FeasibilityResult

TZ = ZoneInfo("America/Santiago")


def _n(x: float | None, nd: int = 2) -> str:
    if x is None:
        return "—"
    return f"{x:,.{nd}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def feasibility_html(r: FeasibilityResult) -> str:
    e = escape
    when = r.created_at.astimezone(TZ).strftime("%d-%m-%Y %H:%M")
    ok = r.feasible
    crit_rows = "".join(
        f"<tr><td>{e(c.label)}</td><td class=num>{_n(c.value, 1)} {e(c.unit)}</td><td>{e(c.source)}</td>"
        f"<td>{'verificado' if c.verified else '<b class=warn>no verificado</b>'}</td></tr>" for c in r.criteria)
    aff = "".join(
        f"<tr><td>{e(a.id)}</td><td>{e(a.name or '')}</td><td>{e(a.node)}</td><td class=num>{_n(a.before)}</td>"
        f"<td class=num>{_n(a.after)}</td><td>{'sí' if a.newly_below else 'ya estaba bajo el mínimo'}</td></tr>"
        for a in r.affected_clients) or "<tr><td colspan=6>Ninguno.</td></tr>"
    issues = "".join(
        f"<tr><td>{e(i.id)}</td><td class=num>{i.dn or '—'}</td><td class=num>{_n(i.velocity_before)} → {_n(i.velocity_after)}</td>"
        f"<td class=num>{_n(i.headloss_before)} → {_n(i.headloss_after)}</td>"
        f"<td>{', '.join(x for x, f in (('velocidad', i.over_velocity), ('pérdida unitaria', i.over_headloss)) if f)}</td></tr>"
        for i in r.link_issues) or "<tr><td colspan=5>Ninguno.</td></tr>"
    upg = "".join(
        f"<tr><td>{e(u.link)}</td><td>{e(u.material or '—')} {e(u.pipe_class or '')}</td>"
        f"<td class=num>{u.dn_from or '—'} → {u.dn_to or '—'}</td><td class=num>{_n(u.inner_from, 1)} → {_n(u.inner_to, 1)}</td>"
        f"<td class=num>{_n(u.pressure_new)}</td><td>{'FACTIBLE' if u.feasible else 'no factible'}{(' · ' + e(u.note)) if u.note else ''}</td></tr>"
        for u in r.upgrades)
    msgs = "".join(f"<li>{e(m.message)}</li>" for m in r.messages) or "<li>Sin advertencias del motor.</li>"
    reasons = "".join(f"<li>{e(x)}</li>" for x in r.reasons)
    pmin = next((c for c in r.criteria if c.key == "pressure_min"), None)
    upg_block = ""
    if r.upgrades:
        conclusion = ("Con el aumento de diámetro indicado la conexión <b>pasa a ser factible</b>."
                      if r.upgrade_feasible else "Aumentar el diámetro del cuello de botella <b>no basta</b> para hacerla factible.")
        upg_block = (f"<h2>Cuello de botella y aumento de DN</h2><p>Tramo cuello de botella: <b>{e(r.bottleneck or '—')}</b>. "
                     f"{conclusion}</p><table><tr><th>Tramo</th><th>Material</th><th>DN</th><th>Interior (mm)</th>"
                     f"<th>Presión punto (m)</th><th>Resultado</th></tr>{upg}</table>")
    return f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Factibilidad — {e(r.project_name)} v{r.model_version}</title>
<style>
 body {{ font: 14px/1.45 system-ui, "IBM Plex Sans", sans-serif; color: #1b2733; margin: 32px auto; max-width: 860px; padding: 0 16px; }}
 h1 {{ font-size: 22px; margin: 0 0 4px; }} h2 {{ font-size: 16px; margin: 22px 0 6px; border-bottom: 1px solid #d8dee5; padding-bottom: 3px; }}
 .verdict {{ display: inline-block; font-size: 20px; font-weight: 700; padding: 6px 14px; border-radius: 6px; margin: 12px 0;
   color: #fff; background: {'#2e7d4f' if ok else '#c0362c'}; }}
 table {{ width: 100%; border-collapse: collapse; margin: 6px 0; }} th, td {{ text-align: left; padding: 4px 6px; border-bottom: 1px solid #e3e8ee; vertical-align: top; }}
 th {{ background: #f3f5f7; font-weight: 600; }} .num {{ text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }}
 .muted {{ color: #5f6f7f; }} .warn {{ color: #b36b00; }} dl {{ display: grid; grid-template-columns: 220px 1fr; gap: 3px 12px; }} dt {{ color: #5f6f7f; }} dd {{ margin: 0; }}
 .print {{ position: fixed; top: 12px; right: 12px; }} @media print {{ .print {{ display: none; }} body {{ margin: 0; }} }}
</style></head><body>
<button class="print" onclick="window.print()">Imprimir / guardar PDF</button>
<h1>Informe de factibilidad de conexión</h1>
<div class="muted">Trazo Hidráulico · {e(when)} (hora de Chile)</div>
<div class="verdict">{e(r.verdict)}</div>
<ul>{reasons}</ul>
<h2>Proyecto y modelo</h2>
<dl>
 <dt>Proyecto</dt><dd>{e(r.project_name)}</dd>
 <dt>Versión del modelo</dt><dd>v{r.model_version} (el proyecto no se modificó)</dd>
 <dt>Motor</dt><dd>OWA-EPANET {e(r.engine.wheel_version)}, tag {e(r.engine.epanet_tag or '—')}</dd>
 <dt>SHA del motor</dt><dd style="font-family:monospace;word-break:break-all">{e(r.engine.epanet_sha or '—')}</dd>
 <dt>Análisis</dt><dd>{'DDA (por demanda)' if r.analysis == 'DDA' else 'PDA (por presión)'}</dd>
 <dt>Huella del modelo simulado</dt><dd style="font-family:monospace;word-break:break-all">{e(r.inp_sha256)}</dd>
</dl>
<h2>Nuevo cliente</h2>
<dl>
 <dt>Ubicación (conexión)</dt><dd>{r.location[1]:.6f}°, {r.location[0]:.6f}° (WGS84) sobre la tubería {e(r.link)}</dd>
 <dt>Consumo</dt><dd>{_n(r.consumption_lps, 3)} L/s</dd>
 <dt>Cota del terreno</dt><dd>{_n(r.elevation)} m</dd>
</dl>
<h2>Criterios aplicados</h2>
<table><tr><th>Criterio</th><th>Valor</th><th>Fuente</th><th>Estado</th></tr>{crit_rows}</table>
<h2>Resultados</h2>
<dl>
 <dt>Presión en el punto</dt><dd><b>{_n(r.pressure_new)} m.c.a.</b> (mínimo {_n(pmin.value if pmin else None, 1)} m.c.a.)</dd>
 <dt>Margen</dt><dd>{_n(r.margin)} m</dd>
</dl>
<h3>Consumos existentes bajo la presión mínima</h3>
<table><tr><th>ID</th><th>Nombre</th><th>Nudo</th><th>Antes (m)</th><th>Después (m)</th><th>Causado por la conexión</th></tr>{aff}</table>
<h3>Tramos sobre la velocidad o la pérdida unitaria máxima</h3>
<table><tr><th>Tramo</th><th>DN</th><th>Velocidad (m/s)</th><th>Pérdida (m/km)</th><th>Supera</th></tr>{issues}</table>
{upg_block}
<h2>Mensajes del motor</h2><ul>{msgs}</ul>
<p class="muted">Criterios y catálogo marcados «no verificado» deben revisarse contra la norma vigente y los
datos del fabricante antes de usar este informe para decisiones.</p>
</body></html>
"""
