"""Geometría: transformaciones EPSG:4326 ↔ SRID métrico del proyecto y cálculo de largos."""
from __future__ import annotations

import math
from functools import lru_cache

from pyproj import Transformer

from app.schemas.network import LinkFeature, NetworkFeatureCollection, NodeFeature


@lru_cache(maxsize=16)
def to_metric(srid: int) -> Transformer:
    return Transformer.from_crs("EPSG:4326", f"EPSG:{srid}", always_xy=True)


@lru_cache(maxsize=16)
def from_metric(srid: int) -> Transformer:
    return Transformer.from_crs(f"EPSG:{srid}", "EPSG:4326", always_xy=True)


def plan_length(coords: list[tuple[float, float]], srid: int) -> float:
    """Largo en planta (m) de una polilínea lon/lat, medido en el SRID métrico."""
    tr = to_metric(srid)
    xs, ys = tr.transform([c[0] for c in coords], [c[1] for c in coords])
    return sum(math.hypot(xs[i + 1] - xs[i], ys[i + 1] - ys[i]) for i in range(len(xs) - 1))


def slope_length(plan: float, z1: float | None, z2: float | None) -> float:
    if z1 is None or z2 is None:
        return plan
    return math.hypot(plan, z2 - z1)


def recompute_lengths(fc: NetworkFeatureCollection, srid: int) -> None:
    """Ajusta extremos de cada tramo a sus nudos y recalcula largos en planta, con pendiente e hidráulico.

    El largo hidráulico se toma según `length_choice`: plan, slope o manual (se respeta el valor dado).
    """
    nodes: dict[str, NodeFeature] = {n.id: n for n in fc.nodes()}
    for lk in fc.links():
        p = lk.properties
        a, b = nodes.get(p.from_node), nodes.get(p.to_node)
        coords = list(lk.geometry.coordinates)
        if a is not None:
            coords[0] = a.geometry.coordinates
        if b is not None:
            coords[-1] = b.geometry.coordinates
        lk.geometry.coordinates = coords
        if p.kind != "pipe":
            continue
        plan = plan_length(coords, srid)
        z1 = a.properties.elevation if a else None
        z2 = b.properties.elevation if b else None
        p.length_plan_m = round(plan, 4)
        p.length_slope_m = round(slope_length(plan, z1, z2), 4)
        if p.length_choice == "plan":
            p.length_hydraulic_m = p.length_plan_m
        elif p.length_choice == "slope":
            p.length_hydraulic_m = p.length_slope_m
        # manual: se conserva length_hydraulic_m tal como viene


def link_midpoint(lk: LinkFeature) -> tuple[float, float]:
    c = lk.geometry.coordinates
    return ((c[0][0] + c[-1][0]) / 2, (c[0][1] + c[-1][1]) / 2)
