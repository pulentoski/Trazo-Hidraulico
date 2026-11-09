"""Escritura de archivos .inp de EPANET a partir del modelo de dominio (unidades SI, L/s).

El mismo escritor genera el archivo que se simula y el que se exporta; la
exportación agrega [COORDINATES] y [VERTICES] en el SRID métrico del proyecto.
"""
from __future__ import annotations

from collections.abc import Callable

from app.schemas.network import NetworkModel

# Secciones complementarias que se transcriben tal cual desde `aux`.
AUX_SECTIONS = ("patterns", "curves", "controls", "rules", "energy", "quality", "sources",
                "reactions", "mixing", "leakage")
# Opciones que el escritor controla y no se toman de options.extra.
MANAGED_OPTIONS = {"UNITS", "PRESSURE", "HEADLOSS", "DEMAND MODEL", "MINIMUM PRESSURE", "REQUIRED PRESSURE",
                   "PRESSURE EXPONENT", "MAP", "HYDRAULICS"}

Projector = Callable[[float, float], tuple[float, float]]


def num(x: float | int | None) -> str:
    """Formato numérico con precisión suficiente para ida y vuelta sin pérdida práctica."""
    if x is None:
        return ""
    if isinstance(x, bool):
        return "1" if x else "0"
    v = float(x)
    if v == 0:
        return "0"
    return f"{v:.12g}"


def _pad(*cols: str) -> str:
    return " " + "\t".join(c for c in cols)


def _times_lines(aux: dict[str, str]) -> list[str]:
    lines = []
    for raw in (aux.get("times") or "").splitlines():
        s = raw.strip()
        if not s or s.startswith(";"):
            continue
        # Se fuerza STATISTIC NONE para obtener resultados en todos los pasos de reporte.
        if s.upper().startswith("STATISTIC"):
            continue
        lines.append(" " + s)
    if not any(ln.strip().upper().startswith("DURATION") for ln in lines):
        lines.insert(0, " DURATION\t0")
    lines.append(" STATISTIC\tNONE")
    return lines


def write_inp(model: NetworkModel, *, projector: Projector | None = None, title: str | None = None,
              closed_shutoffs: set[str] | None = None) -> str:
    """Genera el texto .inp. Con `projector` (lon, lat) → (x, y) se incluyen coordenadas y vértices.

    La demanda de cada nudo es su demanda base manual + categorías + una categoría por cliente (con el
    ID del cliente como nombre, para trazabilidad). Las tuberías con una llave cerrada se escriben cerradas;
    `closed_shutoffs` reemplaza el estado de las llaves (escenarios).
    """
    nodes = model.network.nodes()
    links = model.network.links()
    opts = model.options
    out: list[str] = []

    def section(name: str) -> None:
        out.append("")
        out.append(f"[{name}]")

    out.append("[TITLE]")
    for line in (title or model.title or "Trazo Hidráulico").splitlines()[:3]:
        out.append(" " + line.replace("[", "(").replace("]", ")"))

    junctions = [n for n in nodes if n.properties.kind == "junction"]
    reservoirs = [n for n in nodes if n.properties.kind == "reservoir"]
    tanks = [n for n in nodes if n.properties.kind == "tank"]

    section("JUNCTIONS")
    for n in junctions:
        p = n.properties
        out.append(_pad(n.id, num(p.elevation or 0.0), num(p.base_demand), p.demand_pattern or ""))

    section("RESERVOIRS")
    for n in reservoirs:
        p = n.properties
        head = p.head if p.head is not None else p.elevation
        out.append(_pad(n.id, num(head), p.head_pattern or ""))

    section("TANKS")
    for n in tanks:
        p = n.properties
        cols = [n.id, num(p.elevation or 0.0), num(p.init_level), num(p.min_level), num(p.max_level),
                num(p.tank_diameter), num(p.min_volume or 0.0), p.volume_curve or "*"]
        if p.can_overflow:
            cols.append("YES")
        out.append(_pad(*cols))

    pipes = [lk for lk in links if lk.properties.kind == "pipe"]
    shut = model.closed_links(closed_shutoffs)
    pumps = [lk for lk in links if lk.properties.kind == "pump"]
    valves = [lk for lk in links if lk.properties.kind == "valve"]

    section("PIPES")
    for lk in pipes:
        p = lk.properties
        status = "Closed" if lk.id in shut else {"closed": "Closed", "cv": "CV"}.get(p.initial_status, "Open")
        out.append(_pad(lk.id, p.from_node, p.to_node, num(p.length_hydraulic_m), num(p.inner_diameter_mm),
                        num(p.roughness), num(p.minor_loss), status))

    section("PUMPS")
    for lk in pumps:
        p = lk.properties
        cols = [lk.id, p.from_node, p.to_node]
        if p.pump_curve:
            cols += ["HEAD", p.pump_curve]
        if p.pump_power:
            cols += ["POWER", num(p.pump_power)]
        if p.pump_speed is not None and p.pump_speed != 1.0:
            cols += ["SPEED", num(p.pump_speed)]
        if p.pump_pattern:
            cols += ["PATTERN", p.pump_pattern]
        out.append(_pad(*cols))

    section("VALVES")
    for lk in valves:
        p = lk.properties
        setting = p.valve_curve if p.valve_type == "GPV" and p.valve_curve else num(p.valve_setting or 0.0)
        cols = [lk.id, p.from_node, p.to_node, num(p.inner_diameter_mm), p.valve_type or "TCV", setting,
                num(p.minor_loss)]
        if p.valve_type == "PCV" and p.valve_curve:
            cols.append(p.valve_curve)
        out.append(_pad(*cols))

    by_node = model.client_demands()
    multi = [n for n in junctions if n.properties.demands or n.id in by_node]
    section("DEMANDS")
    for n in multi:
        p = n.properties
        # [DEMANDS] reemplaza la demanda de [JUNCTIONS]: se escriben todas las categorías.
        out.append(_pad(n.id, num(p.base_demand), p.demand_pattern or "") + "\t;manual")
        for d in p.demands:
            cols = [n.id, num(d.base), d.pattern or ""]
            line = _pad(*cols)
            if d.name:
                line += f"\t;{d.name}"
            out.append(line)
        for c in by_node.get(n.id, []):
            out.append(_pad(n.id, num(c.properties.consumption_lps), p.demand_pattern or "") + f"\t;cliente_{c.id}")

    section("EMITTERS")
    for n in junctions:
        if n.properties.emitter_coeff:
            out.append(_pad(n.id, num(n.properties.emitter_coeff)))

    section("STATUS")
    for lk in pumps:
        if lk.properties.initial_status == "closed":
            out.append(_pad(lk.id, "Closed"))
    for lk in valves:
        if lk.properties.initial_status in ("open", "closed"):
            out.append(_pad(lk.id, lk.properties.initial_status.capitalize()))

    for name in AUX_SECTIONS:
        text = model.aux.get(name)
        if not text:
            continue
        section(name.upper())
        for raw in text.splitlines():
            if raw.strip():
                out.append(raw if raw.startswith(" ") or raw.startswith(";") else " " + raw)

    section("TIMES")
    out.extend(_times_lines(model.aux))

    section("REPORT")
    out += [" STATUS\tYES", " SUMMARY\tNO", " PAGE\t0"]

    section("OPTIONS")
    out += [" UNITS\tLPS", " PRESSURE\tMETERS", f" HEADLOSS\t{opts.headloss}", f" DEMAND MODEL\t{opts.demand_model}"]
    if opts.demand_model == "PDA":
        out += [f" MINIMUM PRESSURE\t{num(opts.minimum_pressure)}",
                f" REQUIRED PRESSURE\t{num(opts.required_pressure)}",
                f" PRESSURE EXPONENT\t{num(opts.pressure_exponent)}"]
    for key, value in opts.extra.items():
        if key.upper() in MANAGED_OPTIONS:
            continue
        out.append(f" {key}\t{value}")

    if projector is not None:
        section("COORDINATES")
        for n in nodes:
            x, y = projector(*n.geometry.coordinates)
            out.append(_pad(n.id, f"{x:.3f}", f"{y:.3f}"))
        section("VERTICES")
        for lk in links:
            for lon, lat in lk.geometry.coordinates[1:-1]:
                x, y = projector(lon, lat)
                out.append(_pad(lk.id, f"{x:.3f}", f"{y:.3f}"))

    out.append("")
    out.append("[END]")
    out.append("")
    return "\n".join(out)
