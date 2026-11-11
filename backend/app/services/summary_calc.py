"""Cálculos del panel general (funciones puras, sin base de datos): se prueban con resultados conocidos.

Coordenadas en metros (SRID métrico del proyecto) salvo que se indique otra cosa.
"""
from __future__ import annotations

import bisect
from dataclasses import dataclass
from datetime import datetime

from shapely import MultiPoint, Point, Polygon, unary_union
from shapely.geometry import LineString
from shapely.geometry.base import BaseGeometry
from shapely.ops import voronoi_diagram


# ── Clientes sobre cota ──

@dataclass
class ClientHead:
    id: str
    ground: float  # cota de terreno del cliente (o del nudo si no tiene)
    head: float  # cota piezométrica disponible en su nudo (m)


def over_elevation(clients: list[ClientHead], pmin: float) -> list[tuple[str, float]]:
    """Clientes cuya cota de terreno + presión mínima supera la cota piezométrica disponible.

    Devuelve (id, déficit en m) ordenado de mayor a menor déficit.
    """
    out = [(c.id, c.ground + pmin - c.head) for c in clients]
    return sorted([(i, round(d, 3)) for i, d in out if d > 1e-9], key=lambda x: (-x[1], x[0]))


# ── Zonas por presión ──

def range_labels(breaks: list[float]) -> list[tuple[str, float | None, float | None]]:
    """Etiquetas de los rangos: «< 15», «15–30», …, «> 70»."""
    def f(x: float) -> str:
        return f"{x:g}"
    out: list[tuple[str, float | None, float | None]] = [(f"< {f(breaks[0])}", None, breaks[0])]
    for a, b in zip(breaks, breaks[1:]):
        out.append((f"{f(a)}–{f(b)}", a, b))
    out.append((f"> {f(breaks[-1])}", breaks[-1], None))
    return out


def range_of(p: float, breaks: list[float]) -> int:
    """Índice del rango de una presión (el límite inferior pertenece al rango superior)."""
    return bisect.bisect_right(breaks, p)


@dataclass
class Zone:
    node: str
    pressure: float
    cls: int
    cell: BaseGeometry  # área de influencia recortada al área operacional


def pressure_zones(points: list[tuple[str, float, float, float]], area: BaseGeometry, breaks: list[float]) -> list[Zone]:
    """Áreas de influencia (Voronoi) de cada nudo, recortadas al área operacional, con su rango de presión.

    `points`: (id, x, y, presión). Nudos en la misma posición comparten la celda del primero.
    """
    if not points or area.is_empty:
        return []
    seen: dict[tuple[float, float], int] = {}
    uniq: list[tuple[str, float, float, float]] = []
    for p in points:
        key = (round(p[1], 3), round(p[2], 3))
        if key not in seen:
            seen[key] = len(uniq)
            uniq.append(p)
    if len(uniq) == 1:
        cells = [area]
    else:
        env = area.envelope.buffer(max(area.envelope.length, 1.0))
        diagram = voronoi_diagram(MultiPoint([(p[1], p[2]) for p in uniq]), envelope=env)
        polys = list(diagram.geoms)
        cells = []
        for p in uniq:
            pt = Point(p[1], p[2])
            cells.append(next((c for c in polys if c.covers(pt)), Polygon()))
    out = []
    for p, cell in zip(uniq, cells):
        clipped = cell.intersection(area)
        if clipped.is_empty:
            continue
        out.append(Zone(node=p[0], pressure=p[3], cls=range_of(p[3], breaks), cell=clipped))
    return out


def zone_totals(zones: list[Zone], clients: list[tuple[str, float, float]], n_ranges: int):
    """Superficie (km²), nudos y clientes por rango. `clients`: (id, x, y)."""
    area = [0.0] * n_ranges
    nodes: list[list[str]] = [[] for _ in range(n_ranges)]
    cl: list[list[str]] = [[] for _ in range(n_ranges)]
    for z in zones:
        area[z.cls] += z.cell.area / 1e6
        nodes[z.cls].append(z.node)
    for cid, x, y in clients:
        pt = Point(x, y)
        hit = next((z for z in zones if z.cell.covers(pt)), None)
        if hit is not None:
            cl[hit.cls].append(cid)
    return area, nodes, cl


# ── Área operacional ──

def operational_area(lines: list[list[tuple[float, float]]], points: list[tuple[float, float]], margin: float) -> BaseGeometry:
    """Unión de la red (tramos) y los clientes/nudos con un margen (m)."""
    geoms: list[BaseGeometry] = []
    for coords in lines:
        if len(coords) >= 2:
            geoms.append(LineString(coords))
    geoms.extend(Point(p) for p in points)
    if not geoms:
        return Polygon()
    m = max(margin, 0.01)
    return unary_union([g.buffer(m, quad_segs=8) for g in geoms])


# ── Agua no contabilizada ──

def meter_production(readings: list[tuple[datetime, float]]) -> tuple[float, datetime, datetime] | None:
    """Lecturas acumuladas de un medidor (m³) → (m³/día, desde, hasta). None si no hay dos lecturas útiles."""
    pts = sorted(readings)
    if len(pts) < 2:
        return None
    (t0, v0), (t1, v1) = pts[0], pts[-1]
    days = (t1 - t0).total_seconds() / 86400
    if days <= 0 or v1 < v0:
        return None
    return (v1 - v0) / days, t0, t1


def nrw_pct(production: float, consumption: float) -> float | None:
    """Agua no contabilizada (%) = (producción − consumo facturado) / producción."""
    if production <= 0:
        return None
    return round((production - consumption) / production * 100, 2)


# ── Vencimientos y plan de renovación ──

@dataclass
class PipeAge:
    id: str
    material: str | None
    dn: int | None
    length_m: float
    install_year: int | None


def life_of(material: str | None, life: dict[str, int], default: int) -> int:
    if material:
        for k, v in life.items():
            if k.lower() == material.lower():
                return v
    return default


def expiry_year(p: PipeAge, life: dict[str, int], default: int) -> int | None:
    return None if p.install_year is None else p.install_year + life_of(p.material, life, default)


def price_for(material: str | None, dn: int | None, prices: list[tuple[str, int, float]]) -> float | None:
    """Precio por metro: primero filas del mismo material, luego las de «*»; la de menor DN máximo que cubra el DN."""
    d = dn or 0
    for pool in ([p for p in prices if material and p[0].lower() == material.lower()], [p for p in prices if p[0] == "*"]):
        fit = sorted((p for p in pool if d <= p[1]), key=lambda p: p[1])
        if fit:
            return fit[0][2]
    return None


def due_within(pipes: list[PipeAge], life: dict[str, int], default: int, year: int, horizon: int) -> tuple[float, list[str]]:
    """Km y tramos que vencen entre el año actual (incluido) y año + horizonte (incluido). No incluye los ya vencidos."""
    ids = []
    km = 0.0
    for p in pipes:
        y = expiry_year(p, life, default)
        if y is not None and year <= y <= year + horizon:
            ids.append(p.id)
            km += p.length_m / 1000
    return round(km, 4), ids


def expired(pipes: list[PipeAge], life: dict[str, int], default: int, year: int) -> tuple[float, list[str]]:
    ids = [p.id for p in pipes if (y := expiry_year(p, life, default)) is not None and y < year]
    return round(sum(p.length_m for p in pipes if p.id in ids) / 1000, 4), ids


def renewal_plan(pipes: list[PipeAge], life: dict[str, int], default: int, year: int, horizon: int,
                 prices: list[tuple[str, int, float]]) -> list[tuple[int, float, float, list[str]]]:
    """Plan por año (año, km, costo, tramos) hasta año + horizonte. Los vencidos se programan en el año actual."""
    plan: dict[int, list[PipeAge]] = {}
    for p in pipes:
        y = expiry_year(p, life, default)
        if y is None or y > year + horizon:
            continue
        plan.setdefault(max(y, year), []).append(p)
    out = []
    for y in sorted(plan):
        ps = plan[y]
        cost = sum(p.length_m * (price_for(p.material, p.dn, prices) or 0.0) for p in ps)
        out.append((y, round(sum(p.length_m for p in ps) / 1000, 4), round(cost), [p.id for p in ps]))
    return out
