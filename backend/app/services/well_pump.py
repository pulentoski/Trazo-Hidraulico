"""Pozo y bombeo: altura manométrica, potencia y corriente (hoja BombaPozo1 y PotenciaH de ModeloPozo.xlsx).

Por defecto usa peso específico 9.810 N/m³, π exacto y la fórmula de pérdidas del proyecto (Hazen-Williams de
EPANET: 10,667·Q^1,852/(C^1,852·D^4,871)·L; Darcy-Weisbach con Swamee-Jain; Chezy-Manning 10,29·n²·Q²·L/D^5,33).
La planilla usa 10.000 N/m³, π = 3,14 y H-W con 10,7 y exponentes 1,85 / 4,87; con esos supuestos
(`Conventions.planilla()`) se reproducen sus valores (Hman 138,4 m, 12,3 kW).

Corriente: se usa la fórmula trifásica I = P_eléctrica / (√3·V·cos φ), con P_eléctrica = P_eje / η_motor.
La planilla también calcula P/V (monofásica sin factor de potencia), que sobrestima la corriente de un motor
trifásico; se informa como diferencia.
"""
from __future__ import annotations

import html
import math
from dataclasses import dataclass

from app.schemas.network import NetworkModel, PumpLine, WellFeature, WellPumpDesign
from app.schemas.well import PumpCalc, PumpSegment

G = 9.80665


@dataclass(frozen=True)
class Conventions:
    gamma: float = 9810.0  # N/m³
    pi: float = math.pi
    hw_coef: float = 10.667
    hw_q_exp: float = 1.852
    hw_d_exp: float = 4.871
    sqrt3: float = math.sqrt(3)
    label: str = "Trazo Hidráulico (γ = 9.810 N/m³, π exacto, H-W de EPANET)"

    @staticmethod
    def planilla() -> "Conventions":
        return Conventions(gamma=10000.0, pi=3.14, hw_coef=10.7, hw_q_exp=1.85, hw_d_exp=4.87, sqrt3=1.732,
                           label="Supuestos de la planilla BombaPozo1 (γ = 10.000 N/m³, π = 3,14, H-W 10,7/1,85/4,87)")


DEFAULT_ROUGHNESS = {"H-W": 140.0, "D-W": 0.0015, "C-M": 0.009}


def headloss(line: PumpLine, q_m3s: float, formula: str, c: Conventions) -> float:
    d = line.inner_diameter_mm / 1000
    L = line.length_m
    r = line.roughness or DEFAULT_ROUGHNESS.get(formula, 140.0)
    if L <= 0 or q_m3s <= 0:
        return 0.0
    if formula == "D-W":
        area = c.pi * d * d / 4
        v = q_m3s / area
        re = v * d / 1.004e-6
        eps = r / 1000
        f = 0.25 / math.log10(eps / (3.7 * d) + 5.74 / re ** 0.9) ** 2 if re > 2000 else 64 / re
        return f * L / d * v * v / (2 * G)
    if formula == "C-M":
        return 10.29 * r * r * q_m3s * q_m3s * L / d ** 5.33
    return c.hw_coef / r ** c.hw_q_exp / d ** c.hw_d_exp * q_m3s ** c.hw_q_exp * L


def arrival_elevation(model: NetworkModel, design: WellPumpDesign) -> float | None:
    if design.arrival_elevation_m is not None:
        return design.arrival_elevation_m
    tank = next((n for n in model.network.nodes() if n.id == design.arrival_tank), None)
    if tank and tank.properties.elevation is not None:
        return tank.properties.elevation + (tank.properties.max_level or 0.0)
    return None


def calculate(well: WellFeature, model: NetworkModel, conv: Conventions | None = None,
              formula: str | None = None) -> PumpCalc:
    p = well.properties
    d = p.pump_design
    if d is None:
        raise ValueError(f"El pozo {well.id} no tiene datos de bombeo.")
    if p.ground_elevation is None or p.dynamic_level_m is None:
        raise ValueError(f"El pozo {well.id} necesita cota de terreno y nivel dinámico.")
    c = conv or Conventions()
    f = formula or model.options.headloss
    q = d.design_flow_lps / 1000
    arrival = arrival_elevation(model, d)
    if arrival is None:
        raise ValueError("Indique la cota de llegada o el estanque de llegada (con cota y nivel máximo).")
    segs = []
    for name, line in (("Columna", d.column), ("Impulsión", d.impulsion)):
        area = c.pi * (line.inner_diameter_mm / 1000) ** 2 / 4
        segs.append(PumpSegment(name=name, material=line.material, dn=line.dn, inner_diameter_mm=line.inner_diameter_mm,
                                length_m=line.length_m, velocity_ms=q / area, headloss_m=headloss(line, q, f, c)))
    dyn = p.ground_elevation - p.dynamic_level_m
    stat = p.ground_elevation - p.static_level_m if p.static_level_m is not None else None
    pump_el = p.ground_elevation - d.pump_depth_m
    hgeo = arrival - dyn
    hf = sum(s.headloss_m for s in segs)
    hman = (hgeo + hf) * (1 + d.minor_loss_pct / 100)
    p_hyd = c.gamma * q * hman / 1000  # kW
    p_shaft = p_hyd / d.pump_efficiency
    p_elec = p_shaft / d.motor_efficiency
    current = p_elec * 1000 / (c.sqrt3 * d.voltage_v * d.power_factor)
    warnings = []
    if d.pump_depth_m <= p.dynamic_level_m:
        warnings.append(f"La bomba ({d.pump_depth_m:g} m) queda sobre el nivel dinámico ({p.dynamic_level_m:g} m): "
                        "quedaría sin sumergencia.")
    if p.depth_m is not None and d.pump_depth_m > p.depth_m:
        warnings.append("La bomba está más abajo que la profundidad del pozo.")
    if p.authorized_flow_lps is not None and d.design_flow_lps > p.authorized_flow_lps:
        warnings.append(f"El caudal de diseño ({d.design_flow_lps:g} L/s) supera el caudal autorizado "
                        f"({p.authorized_flow_lps:g} L/s).")
    for s in segs:
        if s.velocity_ms > 2.0:
            warnings.append(f"Velocidad alta en {s.name.lower()}: {s.velocity_ms:.2f} m/s.")
    notes = [
        f"Supuestos: {c.label}; fórmula de pérdidas {f}.",
        f"Pérdidas singulares: {d.minor_loss_pct:g} % de la altura geométrica más las pérdidas por fricción.",
        "Corriente trifásica: I = P_eje / η_motor / (√3 · V · cos φ). La planilla calcula además P/V "
        f"= {p_shaft * 1000 / d.voltage_v:.1f} A (monofásica, sin factor de potencia), que no corresponde a un "
        "motor trifásico.",
    ]
    if c.gamma != 10000.0 or c.pi != 3.14:
        ratio = 10000.0 / c.gamma
        notes.append(f"La planilla usa γ = 10.000 N/m³ y π = 3,14: su potencia resulta {100 * (ratio - 1):.1f} % mayor "
                     "y sus velocidades 0,05 % mayores que con γ = 9.810 N/m³ y π exacto.")
    return PumpCalc(
        well=well.id, formula=f, conventions=c.label, design_flow_lps=d.design_flow_lps,
        ground_elevation=p.ground_elevation, static_level_elevation=stat, dynamic_level_elevation=dyn,
        pump_elevation=pump_el, arrival_elevation=arrival, segments=segs, friction_loss_m=hf, geometric_head_m=hgeo,
        minor_loss_pct=d.minor_loss_pct, manometric_head_m=hman, hydraulic_power_kw=p_hyd, shaft_power_kw=p_shaft,
        shaft_power_hp=p_shaft / 0.7457, shaft_power_cv=p_shaft / 0.7355, electric_power_kw=p_elec,
        current_a=current, curve_points=design_curve(d.design_flow_lps, hman), warnings=warnings, notes=notes)


def design_curve(q_lps: float, h_m: float) -> list[tuple[float, float]]:
    """Curva de 3 puntos desde el punto de diseño (criterio de EPANET para curvas de un punto):
    altura de cierre 1,33·H a caudal 0, el punto de diseño y caudal máximo 2·Q a altura 0."""
    return [(0.0, round(1.33 * h_m, 3)), (round(q_lps, 4), round(h_m, 3)), (round(2 * q_lps, 4), 0.0)]


def report_html(project_name: str, well: WellFeature, calc: PumpCalc) -> str:
    e = html.escape
    p = well.properties

    def f(x, nd=2):
        return "—" if x is None else f"{x:,.{nd}f}".replace(",", "X").replace(".", ",").replace("X", ".")

    rows = "".join(
        f"<tr><td>{e(s.name)}</td><td>{e(s.material or '—')} {s.dn or ''}</td><td>{f(s.inner_diameter_mm, 1)}</td>"
        f"<td>{f(s.length_m, 1)}</td><td>{f(s.velocity_ms, 2)}</td><td>{f(s.headloss_m, 3)}</td></tr>"
        for s in calc.segments)
    curve = "".join(f"<tr><td>{f(q, 2)}</td><td>{f(h, 2)}</td></tr>" for q, h in calc.curve_points)
    warns = "".join(f"<li>{e(w)}</li>" for w in calc.warnings) or "<li>Sin observaciones.</li>"
    notes = "".join(f"<li>{e(n)}</li>" for n in calc.notes)
    return f"""<!doctype html><html lang="es"><head><meta charset="utf-8"><title>Ficha del pozo {e(well.id)}</title>
<style>body{{font:14px/1.45 system-ui,sans-serif;max-width:860px;margin:24px auto;color:#1b2733}}h1{{font-size:22px}}
table{{border-collapse:collapse;width:100%;margin:8px 0 16px}}td,th{{border:1px solid #ccd5de;padding:4px 8px;text-align:right}}
td:first-child,th:first-child{{text-align:left}}th{{background:#eef2f6}}.k{{font-size:20px;font-weight:600}}
.grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}}.box{{border:1px solid #ccd5de;border-radius:6px;padding:8px}}
.nv{{color:#9c5700}}@media print{{body{{margin:0}}}}</style></head><body>
<h1>Ficha del pozo {e(well.id)}</h1><p>Proyecto: <b>{e(project_name)}</b> · {e(p.description or '')}</p>
<p class="nv">Cálculo de partida no verificado: revise los datos antes de seleccionar la bomba.</p>
<h2>Datos del pozo</h2><table>
<tr><th>Cota de terreno</th><td>{f(p.ground_elevation)} m</td><th>Profundidad</th><td>{f(p.depth_m, 1)} m</td></tr>
<tr><th>Nivel estático</th><td>{f(p.static_level_m)} m (cota {f(calc.static_level_elevation)})</td>
<th>Nivel dinámico</th><td>{f(p.dynamic_level_m)} m (cota {f(calc.dynamic_level_elevation)})</td></tr>
<tr><th>Bomba a</th><td>{f(p.pump_design.pump_depth_m if p.pump_design else None, 1)} m (cota {f(calc.pump_elevation)})</td>
<th>Cota de llegada</th><td>{f(calc.arrival_elevation)} m</td></tr>
<tr><th>Caudal de diseño</th><td>{f(calc.design_flow_lps)} L/s</td><th>Caudal autorizado</th><td>{f(p.authorized_flow_lps)} L/s</td></tr>
</table>
<h2>Tramos</h2><table><tr><th>Tramo</th><th>Material y DN</th><th>D int. (mm)</th><th>Largo (m)</th><th>Velocidad (m/s)</th><th>Pérdida (m)</th></tr>{rows}</table>
<h2>Resultados</h2><div class="grid">
<div class="box">Altura geométrica<div class="k">{f(calc.geometric_head_m)} m</div></div>
<div class="box">Pérdidas por fricción<div class="k">{f(calc.friction_loss_m, 3)} m</div></div>
<div class="box">Altura manométrica (+{f(calc.minor_loss_pct, 0)} %)<div class="k">{f(calc.manometric_head_m)} m</div></div>
<div class="box">Potencia hidráulica<div class="k">{f(calc.hydraulic_power_kw)} kW</div></div>
<div class="box">Potencia al eje<div class="k">{f(calc.shaft_power_kw)} kW</div>{f(calc.shaft_power_hp, 1)} HP · {f(calc.shaft_power_cv, 1)} C.V.</div>
<div class="box">Corriente trifásica<div class="k">{f(calc.current_a, 1)} A</div>{f(calc.electric_power_kw)} kW eléctricos</div></div>
<h2>Curva de bomba sugerida (3 puntos)</h2><table><tr><th>Caudal (L/s)</th><th>Altura (m)</th></tr>{curve}</table>
<h2>Observaciones</h2><ul>{warns}</ul><h2>Supuestos y diferencias con la planilla</h2><ul>{notes}</ul>
<p style="color:#5f6f7f">Generado por Trazo Hidráulico.</p></body></html>"""
