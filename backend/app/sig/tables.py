"""Modelo → filas planas por hoja (exportación, comparación y consultas)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.schemas.network import (ClientFeature, HydrantFeature, LinkFeature, NetworkModel, NodeFeature, ShutoffFeature,
                                 WellFeature)
from app.services.geometry import to_metric

from .spec import SHEETS, Sheet

# Atributos reservados (no se exportan como columnas libres): datos de gestión de válvulas de control.
RESERVED_PREFIX = "__"


@dataclass
class Row:
    id: str
    values: dict[str, Any]
    attributes: dict[str, Any] = field(default_factory=dict)
    derived: set[str] = field(default_factory=set)  # columnas que no se comparan (geometría calculada)


def fmt_vertices(coords: list[tuple[float, float]]) -> str | None:
    inner = coords[1:-1]
    if not inner:
        return None
    return "; ".join(f"{lat!r} {lon!r}" for lon, lat in inner)


def public_attributes(attrs: dict[str, Any] | None) -> dict[str, Any]:
    return {k: v for k, v in (attrs or {}).items() if not k.startswith(RESERVED_PREFIX)}


class Exporter:
    def __init__(self, srid: int):
        self.tr = to_metric(srid)

    def geo(self, lon: float, lat: float) -> dict[str, Any]:
        e, n = self.tr.transform(lon, lat)
        return {"_lat": lat, "_lon": lon, "_east": round(float(e), 3), "_north": round(float(n), 3)}

    def node_row(self, sheet: Sheet, f: NodeFeature) -> Row:
        p = f.properties
        values = {c.key: getattr(p, c.key) for c in sheet.cols if not c.key.startswith("_") and c.key != "id"}
        values.update(self.geo(*f.geometry.coordinates))
        return Row(f.id, values, public_attributes(p.attributes), {"_east", "_north"})

    def link_row(self, sheet: Sheet, f: LinkFeature) -> Row:
        p = f.properties
        values = {c.key: getattr(p, c.key) for c in sheet.cols
                  if not c.key.startswith("_") and c.key != "id" and hasattr(p, c.key)}
        values["_vertices"] = fmt_vertices(f.geometry.coordinates)
        if sheet.col("_length_manual"):
            values["_length_manual"] = p.length_hydraulic_m if p.length_choice == "manual" else None
        return Row(f.id, values, public_attributes(p.attributes))

    def shutoff_row(self, f: ShutoffFeature) -> Row:
        p = f.properties
        values = {"_class": "corte", "_type": p.valve_type, "_state": p.state, "condition": p.condition,
                  "_diameter": p.diameter_mm, "_depth": p.depth_m, "link": p.link, "position": p.position,
                  "from_node": None, "to_node": None, "valve_setting": None, "valve_curve": None, "name": p.name}
        values.update(self.geo(*f.geometry.coordinates))
        return Row(f.id, values, public_attributes(p.attributes), {"_lat", "_lon", "_east", "_north"})

    def control_valve_row(self, f: LinkFeature) -> Row:
        p = f.properties
        attrs = p.attributes or {}
        c = f.geometry.coordinates
        mid = ((c[0][0] + c[-1][0]) / 2, (c[0][1] + c[-1][1]) / 2)
        values = {"_class": "control", "_type": p.valve_type, "_state": p.initial_status,
                  "condition": attrs.get("__condition"), "_diameter": p.inner_diameter_mm,
                  "_depth": attrs.get("__depth_m"), "link": None, "position": None, "from_node": p.from_node,
                  "to_node": p.to_node, "valve_setting": p.valve_setting, "valve_curve": p.valve_curve,
                  "name": p.description}
        values.update(self.geo(*mid))
        return Row(f.id, values, public_attributes(attrs), {"_lat", "_lon", "_east", "_north"})

    def point_row(self, sheet: Sheet, f: HydrantFeature | WellFeature | ClientFeature) -> Row:
        p = f.properties
        values = {c.key: getattr(p, c.key) for c in sheet.cols if not c.key.startswith("_") and c.key != "id"}
        values.update(self.geo(*f.geometry.coordinates))
        return Row(f.id, values, public_attributes(p.attributes), {"_east", "_north"})


def model_rows(model: NetworkModel, srid: int) -> dict[str, list[Row]]:
    """Filas de cada hoja en el orden del modelo."""
    ex = Exporter(srid)
    by_key = {s.key: s for s in SHEETS}
    out: dict[str, list[Row]] = {s.key: [] for s in SHEETS}
    node_sheet = {"junction": "nudos", "tank": "estanques", "reservoir": "reservorios"}
    for n in model.network.nodes():
        key = node_sheet[n.properties.kind]
        out[key].append(ex.node_row(by_key[key], n))
    for lk in model.network.links():
        if lk.properties.kind == "pipe":
            out["tramos"].append(ex.link_row(by_key["tramos"], lk))
        elif lk.properties.kind == "pump":
            out["bombas"].append(ex.link_row(by_key["bombas"], lk))
        else:
            out["valvulas"].append(ex.control_valve_row(lk))
    for sh in model.network.shutoffs():
        out["valvulas"].append(ex.shutoff_row(sh))
    for h in model.network.hydrants():
        out["grifos"].append(ex.point_row(by_key["grifos"], h))
    for w in model.network.wells():
        out["pozos"].append(ex.point_row(by_key["pozos"], w))
    for c in model.network.clients():
        row = ex.point_row(by_key["clientes"], c)
        out["clientes"].append(row)
    return out


def model_sheet_rows(model: NetworkModel) -> list[tuple[str, str]]:
    """Hoja «Modelo»: opciones hidráulicas y secciones complementarias del .inp (para ida y vuelta sin pérdida)."""
    import json

    rows = [("Opciones", json.dumps(model.options.model_dump(mode="json"), ensure_ascii=False, sort_keys=True))]
    for name in sorted(model.aux):
        rows.append((f"Sección {name}", model.aux[name]))
    return rows
