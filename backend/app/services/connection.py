"""Conexión de puntos a la red: proyección sobre tuberías, asignación de nudo y división de tramos.

Los cálculos se hacen en el SRID métrico del proyecto (largos y distancias en metros).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from app.schemas.network import (LineStringGeometry, LinkFeature, NetworkFeatureCollection, NodeFeature,
                                 NodeProperties, PointGeometry)
from app.services.geometry import from_metric, to_metric


@dataclass
class Projection:
    link: str  # ID de la tubería
    point: tuple[float, float]  # punto de conexión [lon, lat]
    distance_m: float  # distancia del punto original a la tubería
    segment: int  # índice del segmento de la polilínea
    fraction: float  # posición a lo largo de la tubería (0–1, por largo en planta)
    along_m: float  # distancia desde el inicio de la tubería
    length_m: float  # largo en planta de la tubería


def _xy(coords, srid: int) -> list[tuple[float, float]]:
    tr = to_metric(srid)
    xs, ys = tr.transform([c[0] for c in coords], [c[1] for c in coords])
    return list(zip(xs, ys))


def project_on_link(lk: LinkFeature, lon: float, lat: float, srid: int) -> Projection:
    pts = _xy(lk.geometry.coordinates, srid)
    px, py = to_metric(srid).transform(lon, lat)
    best = None
    acc = 0.0
    seg_start = []
    for i in range(len(pts) - 1):
        seg_start.append(acc)
        acc += math.dist(pts[i], pts[i + 1])
    total = acc
    for i in range(len(pts) - 1):
        (ax, ay), (bx, by) = pts[i], pts[i + 1]
        dx, dy = bx - ax, by - ay
        L2 = dx * dx + dy * dy
        t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
        qx, qy = ax + t * dx, ay + t * dy
        d = math.hypot(px - qx, py - qy)
        if best is None or d < best[0]:
            best = (d, i, qx, qy, seg_start[i] + t * math.sqrt(L2))
    d, i, qx, qy, along = best
    lon2, lat2 = from_metric(srid).transform(qx, qy)
    return Projection(link=lk.id, point=(float(lon2), float(lat2)), distance_m=d, segment=i,
                      fraction=(along / total) if total > 0 else 0.0, along_m=along, length_m=total)


def nearest_pipe(fc: NetworkFeatureCollection, lon: float, lat: float, srid: int) -> Projection | None:
    best = None
    for lk in fc.links():
        if lk.properties.kind != "pipe":
            continue
        pr = project_on_link(lk, lon, lat, srid)
        if best is None or pr.distance_m < best.distance_m:
            best = pr
    return best


def assign_node(fc: NetworkFeatureCollection, pr: Projection, srid: int) -> tuple[str, float] | None:
    """Nudo de consumo más cercano al punto de conexión: primero los extremos de la tubería; si ninguno es
    nudo de consumo, el nudo de consumo más cercano de la red. Devuelve (ID, distancia en m)."""
    nodes = {n.id: n for n in fc.nodes()}
    lk = next(x for x in fc.links() if x.id == pr.link)
    cx, cy = to_metric(srid).transform(*pr.point)

    def dist(n: NodeFeature) -> float:
        x, y = to_metric(srid).transform(*n.geometry.coordinates)
        return math.hypot(x - cx, y - cy)

    ends = [nodes[i] for i in (lk.properties.from_node, lk.properties.to_node) if i in nodes]
    candidates = [n for n in ends if n.properties.kind == "junction"] or [
        n for n in nodes.values() if n.properties.kind == "junction"]
    if not candidates:
        return None
    n = min(candidates, key=dist)
    return n.id, dist(n)


def point_at(lk: LinkFeature, fraction: float, srid: int) -> tuple[float, float]:
    """Punto a una fracción del largo en planta de la tubería."""
    pts = _xy(lk.geometry.coordinates, srid)
    lens = [math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]
    target = max(0.0, min(1.0, fraction)) * sum(lens)
    for i, L in enumerate(lens):
        if target <= L or i == len(lens) - 1:
            t = 0.0 if L == 0 else min(1.0, target / L)
            x = pts[i][0] + t * (pts[i + 1][0] - pts[i][0])
            y = pts[i][1] + t * (pts[i + 1][1] - pts[i][1])
            lon, lat = from_metric(srid).transform(x, y)
            return float(lon), float(lat)
        target -= L
    return lk.geometry.coordinates[-1]


def unique_id(existing: set[str], prefix: str) -> str:
    n = 1
    while f"{prefix}{n}" in existing:
        n += 1
    return f"{prefix}{n}"


def split_pipe(fc: NetworkFeatureCollection, pr: Projection, node_id: str, elevation: float | None,
               base_demand: float = 0.0) -> tuple[str, str]:
    """Divide la tubería en el punto de conexión con un nudo nuevo. Devuelve los IDs de las dos partes.

    Las partes heredan las propiedades del tramo. Si el largo hidráulico era manual, se reparte en
    proporción al largo en planta; si no, se recalcula desde la geometría al guardar.
    """
    lk = next(x for x in fc.links() if x.id == pr.link)
    p = lk.properties
    coords = list(lk.geometry.coordinates)
    first = coords[: pr.segment + 1] + [pr.point]
    second = [pr.point] + coords[pr.segment + 1:]
    fc.features.append(NodeFeature(id=node_id, geometry=PointGeometry(coordinates=pr.point),
                                   properties=NodeProperties(kind="junction", elevation=elevation,
                                                             base_demand=base_demand)))
    link_ids = {x.id for x in fc.links()}
    id_b = unique_id(link_ids, f"{lk.id}_")
    b = lk.model_copy(deep=True)
    b.id = id_b
    b.properties.uid = None
    b.properties.from_node, b.properties.to_node = node_id, p.to_node
    b.geometry = LineStringGeometry(coordinates=second)
    p.to_node = node_id
    lk.geometry = LineStringGeometry(coordinates=first)
    if p.length_choice == "manual" and p.length_hydraulic_m:
        total = p.length_hydraulic_m
        p.length_hydraulic_m = total * pr.fraction
        b.properties.length_hydraulic_m = total * (1 - pr.fraction)
    fc.features.append(b)
    # Llaves sobre la tubería original: pasan a la parte que corresponda según su posición.
    for sh in fc.shutoffs():
        if sh.properties.link != lk.id:
            continue
        pos = sh.properties.position
        if pos <= pr.fraction and pr.fraction > 0:
            sh.properties.position = pos / pr.fraction
        else:
            sh.properties.link = id_b
            sh.properties.position = (pos - pr.fraction) / (1 - pr.fraction) if pr.fraction < 1 else 0.0
    return lk.id, id_b
