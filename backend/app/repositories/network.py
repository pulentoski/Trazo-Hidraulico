"""Persistencia de la red de una versión (nudos y tramos con geometría PostGIS)."""
import uuid

from geoalchemy2.elements import WKTElement
from geoalchemy2.shape import to_shape
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import NetworkLink, NetworkNode, ProjectVersion
from app.schemas.network import (DemandCategory, LineStringGeometry, LinkFeature, LinkProperties,
                                 NetworkFeatureCollection, NodeFeature, NodeProperties, PointGeometry)

NODE_FIELDS = ("description", "elevation", "elevation_source", "elevation_method", "base_demand", "demand_pattern",
               "emitter_coeff", "initial_quality", "head", "head_pattern", "init_level", "min_level", "max_level",
               "tank_diameter", "min_volume", "volume_curve", "can_overflow")
LINK_FIELDS = ("description", "dn", "inner_diameter_mm", "material", "pipe_class", "catalog_pipe_id", "roughness",
               "minor_loss", "initial_status", "length_plan_m", "length_slope_m", "length_hydraulic_m",
               "length_choice", "pump_curve", "pump_power", "pump_speed", "pump_pattern", "valve_type",
               "valve_setting", "valve_curve")


def _uid(value: str | None) -> uuid.UUID:
    try:
        return uuid.UUID(value) if value else uuid.uuid4()
    except ValueError:
        return uuid.uuid4()


def insert_network(session: Session, version: ProjectVersion, fc: NetworkFeatureCollection) -> None:
    ids: dict[str, int] = {}
    node_rows = []
    for n in fc.nodes():
        p = n.properties
        lon, lat = n.geometry.coordinates
        row = NetworkNode(
            version_id=version.id, uid=_uid(p.uid), label=n.id, kind=p.kind,
            geom=WKTElement(f"POINT({lon!r} {lat!r})", srid=4326),
            demands=[d.model_dump() for d in p.demands], extra={},
            **{f: getattr(p, f) for f in NODE_FIELDS},
        )
        node_rows.append(row)
    session.add_all(node_rows)
    session.flush()
    for row in node_rows:
        ids[row.label] = row.id

    link_rows = []
    for lk in fc.links():
        p = lk.properties
        wkt = "LINESTRING(" + ", ".join(f"{x!r} {y!r}" for x, y in lk.geometry.coordinates) + ")"
        link_rows.append(NetworkLink(
            version_id=version.id, uid=_uid(p.uid), label=lk.id, kind=p.kind,
            from_node_id=ids[p.from_node], to_node_id=ids[p.to_node],
            geom=WKTElement(wkt, srid=4326), extra={},
            **{f: getattr(p, f) for f in LINK_FIELDS},
        ))
    session.add_all(link_rows)
    session.flush()


def load_network(session: Session, version_id: uuid.UUID) -> NetworkFeatureCollection:
    nodes = list(session.scalars(select(NetworkNode).where(NetworkNode.version_id == version_id).order_by(NetworkNode.id)))
    labels = {n.id: n.label for n in nodes}
    features: list = []
    for n in nodes:
        pt = to_shape(n.geom)
        props = {f: getattr(n, f) for f in NODE_FIELDS}
        features.append(NodeFeature(
            id=n.label, geometry=PointGeometry(coordinates=(pt.x, pt.y)),
            properties=NodeProperties(uid=str(n.uid), kind=n.kind,
                                      demands=[DemandCategory(**d) for d in (n.demands or [])], **props),
        ))
    links = select(NetworkLink).where(NetworkLink.version_id == version_id).order_by(NetworkLink.id)
    for lk in session.scalars(links):
        line = to_shape(lk.geom)
        props = {f: getattr(lk, f) for f in LINK_FIELDS}
        features.append(LinkFeature(
            id=lk.label, geometry=LineStringGeometry(coordinates=[(x, y) for x, y in line.coords]),
            properties=LinkProperties(uid=str(lk.uid), kind=lk.kind, from_node=labels[lk.from_node_id],
                                      to_node=labels[lk.to_node_id], **props),
        ))
    return NetworkFeatureCollection(features=features)


def node_ids(session: Session, version_id: uuid.UUID) -> dict[str, int]:
    return dict(session.execute(select(NetworkNode.label, NetworkNode.id).where(NetworkNode.version_id == version_id)).all())


def link_ids(session: Session, version_id: uuid.UUID) -> dict[str, int]:
    return dict(session.execute(select(NetworkLink.label, NetworkLink.id).where(NetworkLink.version_id == version_id)).all())
