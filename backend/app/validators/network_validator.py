"""Validación del modelo antes de simular.

Errores bloqueantes (impiden simular):
  E_EMPTY_NETWORK, E_NO_SOURCE, E_LINK_NODE, E_DIAMETER_NOT_IN_CATALOG, E_DUPLICATE_ID,
  E_INVALID_ID, E_ISOLATED_NODE, E_DISCONNECTED_NODE, E_MISSING_PARAM
Advertencias:
  W_ELEVATION_ASSUMED, W_ELEVATION_DOUBTFUL, W_SHORT_PIPE, W_NO_DEMAND, W_CRITERIA

La cota nunca se supone en silencio: un nudo o estanque sin cota es un error bloqueante
(E_MISSING_PARAM). Solo una importación puede traer una cota supuesta (p. ej. un .inp sin la
columna de cota, que EPANET toma como 0 m), y en ese caso se advierte explícitamente.
"""
from __future__ import annotations

import re
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from app.schemas.network import NetworkModel
from app.schemas.validation import ValidationIssue, ValidationReport

ID_RE = re.compile(r'^[^\s;"]{1,31}$')
# Rango típico de rugosidad por fórmula (fuera de él se advierte: probable confusión de unidades).
ROUGHNESS_RANGE = {"H-W": (60.0, 160.0, "C"), "D-W": (0.0, 10.0, "mm"), "C-M": (0.007, 0.035, "")}


@dataclass
class CatalogIndex:
    ids: set[int] = field(default_factory=set)
    materials: set[str] = field(default_factory=set)
    combos: set[tuple[str, int, str]] = field(default_factory=set)  # (material, dn, clase)
    dns: set[tuple[str, int]] = field(default_factory=set)


@dataclass
class ValidatorSettings:
    short_pipe_m: float = 1.0
    elevation_jump_m: float = 50.0
    criteria: dict[str, dict] = field(default_factory=dict)  # key -> {min, max, unit, label}


def _fmt(x: float) -> str:
    return f"{x:g}".replace(".", ",")


def _section_ids(text: str | None) -> set[str]:
    ids = set()
    for line in (text or "").splitlines():
        s = line.strip()
        if s and not s.startswith(";"):
            ids.add(s.split()[0])
    return ids


def validate_model(model: NetworkModel, catalog: CatalogIndex | None = None,
                   settings: ValidatorSettings | None = None, structural_only: bool = False) -> ValidationReport:
    catalog = catalog or CatalogIndex()
    settings = settings or ValidatorSettings()
    errors: list[ValidationIssue] = []
    warnings: list[ValidationIssue] = []

    def err(code, msg, etype=None, eid=None):
        errors.append(ValidationIssue(code=code, severity="error", message=msg, element_type=etype, element_id=eid))

    def warn(code, msg, etype=None, eid=None):
        warnings.append(ValidationIssue(code=code, severity="warning", message=msg, element_type=etype, element_id=eid))

    nodes = model.network.nodes()
    links = model.network.links()
    node_by_id = {n.id: n for n in nodes}

    # IDs duplicados e inválidos
    for kind, items, etype in (("nudo", nodes, "node"), ("tramo", links, "link")):
        for ident, count in Counter(f.id for f in items).items():
            if count > 1:
                err("E_DUPLICATE_ID", f"El ID de {kind} «{ident}» está repetido {count} veces.", etype, ident)
        for f in items:
            if not ID_RE.match(f.id):
                err("E_INVALID_ID", f"El ID de {kind} «{f.id}» no es válido: máximo 31 caracteres, "
                                    "sin espacios, punto y coma ni comillas.", etype, f.id)

    # Topología de tramos
    for lk in links:
        p = lk.properties
        missing = [n for n in (p.from_node, p.to_node) if n not in node_by_id]
        if missing:
            err("E_LINK_NODE", f"El tramo {lk.id} referencia nudos inexistentes: {', '.join(missing)}.", "link", lk.id)
        elif p.from_node == p.to_node:
            err("E_LINK_NODE", f"El tramo {lk.id} tiene el mismo nudo inicial y final ({p.from_node}).", "link", lk.id)

    if structural_only:
        return ValidationReport(ok=not errors, errors=errors, warnings=warnings)

    if not nodes:
        err("E_EMPTY_NETWORK", "La red está vacía: agregue nudos, una fuente y tramos.", "network")
    elif not any(n.properties.kind in ("reservoir", "tank") for n in nodes):
        err("E_NO_SOURCE", "La red no tiene fuente: agregue al menos un reservorio o un estanque.", "network")

    patterns = _section_ids(model.aux.get("patterns"))
    curves = _section_ids(model.aux.get("curves"))

    def need(cond: bool, f, etype: str, what: str) -> None:
        if not cond:
            err("E_MISSING_PARAM", f"Falta {what} en {('el nudo' if etype == 'node' else 'el tramo')} {f.id}.",
                etype, f.id)

    def need_pattern(pid: str | None, f, etype: str) -> None:
        if pid and pid not in patterns:
            err("E_MISSING_PARAM", f"El patrón «{pid}» usado por {f.id} no está definido.", etype, f.id)

    connected: dict[str, list[str]] = defaultdict(list)
    for lk in links:
        connected[lk.properties.from_node].append(lk.properties.to_node)
        connected[lk.properties.to_node].append(lk.properties.from_node)

    for n in nodes:
        p = n.properties
        if p.kind == "junction":
            need(p.elevation is not None, n, "node", "la cota")
            need_pattern(p.demand_pattern, n, "node")
            for d in p.demands:
                need_pattern(d.pattern, n, "node")
        elif p.kind == "reservoir":
            need(p.head is not None or p.elevation is not None, n, "node", "la carga total del reservorio")
            need_pattern(p.head_pattern, n, "node")
        else:
            need(p.elevation is not None, n, "node", "la cota de fondo del estanque")
            need(p.tank_diameter is not None and p.tank_diameter > 0 or bool(p.volume_curve), n, "node",
                 "el diámetro del estanque")
            levels = (p.min_level, p.init_level, p.max_level)
            need(all(v is not None for v in levels), n, "node", "algún nivel del estanque (mínimo, inicial o máximo)")
            if all(v is not None for v in levels) and not (p.min_level <= p.init_level <= p.max_level):
                err("E_MISSING_PARAM", f"Los niveles del estanque {n.id} deben cumplir mínimo ≤ inicial ≤ máximo.",
                    "node", n.id)
            if p.volume_curve and p.volume_curve not in curves:
                err("E_MISSING_PARAM", f"La curva de volumen «{p.volume_curve}» no está definida.", "node", n.id)
        if not connected.get(n.id):
            err("E_ISOLATED_NODE", f"El nudo {n.id} no tiene tramos conectados.", "node", n.id)

    # Nudos con tramos pero sin camino a ninguna fuente (islas): el motor no puede resolverlos.
    sources = [n.id for n in nodes if n.properties.kind in ("reservoir", "tank")]
    if sources:
        reached = set(sources)
        stack = list(sources)
        while stack:
            for m in connected.get(stack.pop(), []):
                if m not in reached and m in node_by_id:
                    reached.add(m)
                    stack.append(m)
        for n in nodes:
            if n.id not in reached and connected.get(n.id):
                err("E_DISCONNECTED_NODE", f"El nudo {n.id} no está conectado a ninguna fuente (reservorio o estanque).",
                    "node", n.id)

    for lk in links:
        p = lk.properties
        if p.kind == "pipe":
            need(p.length_hydraulic_m is not None and p.length_hydraulic_m > 0, lk, "link", "el largo hidráulico")
            need(p.roughness is not None and p.roughness > 0, lk, "link", "la rugosidad")
            if p.catalog_pipe_id is not None and p.catalog_pipe_id not in catalog.ids:
                err("E_DIAMETER_NOT_IN_CATALOG", f"El tramo {lk.id} referencia un ítem de catálogo inexistente.",
                    "link", lk.id)
            elif p.material and p.material in catalog.materials and p.dn is not None:
                if (p.material, p.dn) not in catalog.dns:
                    err("E_DIAMETER_NOT_IN_CATALOG",
                        f"El DN {p.dn} no existe en el catálogo de {p.material} (tramo {lk.id}).", "link", lk.id)
                elif p.pipe_class and (p.material, p.dn, p.pipe_class) not in catalog.combos:
                    err("E_DIAMETER_NOT_IN_CATALOG",
                        f"El DN {p.dn} clase {p.pipe_class} no existe en el catálogo de {p.material} (tramo {lk.id}).",
                        "link", lk.id)
            need(p.inner_diameter_mm is not None and p.inner_diameter_mm > 0, lk, "link", "el diámetro interior")
        elif p.kind == "pump":
            need(bool(p.pump_curve) or (p.pump_power or 0) > 0, lk, "link", "la curva o potencia de la bomba")
            if p.pump_curve and p.pump_curve not in curves:
                err("E_MISSING_PARAM", f"La curva «{p.pump_curve}» de la bomba {lk.id} no está definida.", "link", lk.id)
            need_pattern(p.pump_pattern, lk, "link")
        else:
            need(bool(p.valve_type), lk, "link", "el tipo de válvula")
            need(p.inner_diameter_mm is not None and p.inner_diameter_mm > 0, lk, "link", "el diámetro de la válvula")
            if p.valve_type == "GPV":
                need(bool(p.valve_curve), lk, "link", "la curva de la válvula GPV")
            else:
                need(p.valve_setting is not None, lk, "link", "la consigna de la válvula")

    o = model.options
    if o.demand_model == "PDA" and o.required_pressure <= o.minimum_pressure:
        err("E_MISSING_PARAM", "Análisis PDA: la presión requerida debe ser mayor que la presión mínima.", "network")

    # ── Advertencias ──
    for n in nodes:
        p = n.properties
        if p.kind == "reservoir" or p.elevation is None:
            continue
        if p.elevation_source == "supuesta":
            why = f" {p.elevation_method.rstrip('.')}." if p.elevation_method else ""
            warn("W_ELEVATION_ASSUMED", f"La cota del nudo {n.id} es supuesta ({_fmt(p.elevation)} m), no un dato "
                                        f"ingresado.{why} Ingrese la cota real.", "node", n.id)
            continue
        neigh = [node_by_id[m].properties.elevation for m in connected.get(n.id, [])
                 if m in node_by_id and node_by_id[m].properties.elevation is not None
                 and node_by_id[m].properties.kind != "reservoir"]
        if neigh:
            ref = statistics.median(neigh)
            if abs(p.elevation - ref) > settings.elevation_jump_m:
                warn("W_ELEVATION_DOUBTFUL",
                     f"La cota del nudo {n.id} ({_fmt(p.elevation)} m) difiere más de {_fmt(settings.elevation_jump_m)} m "
                     f"de sus vecinos ({_fmt(ref)} m).", "node", n.id)

    for lk in links:
        p = lk.properties
        if p.kind == "pipe" and p.length_hydraulic_m is not None and 0 < p.length_hydraulic_m < settings.short_pipe_m:
            warn("W_SHORT_PIPE", f"El tramo {lk.id} es muy corto ({_fmt(round(p.length_hydraulic_m, 3))} m).", "link", lk.id)

    for n in nodes:
        p = n.properties
        if p.kind == "junction" and p.base_demand == 0 and not any(d.base for d in p.demands):
            warn("W_NO_DEMAND", f"El nudo {n.id} no tiene demanda asignada.", "node", n.id)

    dn_min = (settings.criteria.get("dn_min") or {}).get("min")
    lo, hi, unit = ROUGHNESS_RANGE[o.headloss]
    for lk in links:
        p = lk.properties
        if p.kind != "pipe":
            continue
        if dn_min is not None and p.dn is not None and p.dn < dn_min:
            warn("W_CRITERIA", f"El tramo {lk.id} tiene DN {p.dn} mm, menor que el mínimo del perfil ({_fmt(dn_min)} mm).",
                 "link", lk.id)
        if p.roughness is not None and p.roughness > 0 and not (lo <= p.roughness <= hi):
            warn("W_CRITERIA", f"La rugosidad del tramo {lk.id} ({_fmt(p.roughness)} {unit}) está fuera del rango típico "
                               f"para {o.headloss} ({_fmt(lo)}–{_fmt(hi)} {unit}).", "link", lk.id)

    return ValidationReport(ok=not errors, errors=errors, warnings=warnings)
