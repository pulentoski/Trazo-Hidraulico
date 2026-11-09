"""Persistencia de la red de una versión (nudos y tramos con geometría PostGIS)."""
import uuid

from geoalchemy2.elements import WKTElement
from geoalchemy2.shape import to_shape
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import NetworkClient, NetworkLink, NetworkNode, NetworkShutoff, ProjectVersion
from app.schemas.network import (ClientFeature, ClientProperties, DemandCategory, LineStringGeometry, LinkFeature,
                                 LinkProperties, NetworkFeatureCollection, NodeFeature, NodeProperties, PointGeometry,
                                 ShutoffFeature, ShutoffProperties, to_lps)

NODE_FIELDS = ("description", "elevation", "elevation_source", "elevation_method", "base_demand", "demand_pattern",
               "emitter_coeff", "initial_quality", "head", "head_pattern", "init_level", "min_level", "max_level",
               "tank_diameter", "min_volume", "volume_curve", "can_overflow")
LINK_FIELDS = ("description", "dn", "inner_diameter_mm", "material", "pipe_class", "catalog_pipe_id", "roughness",
               "minor_loss", "initial_status", "inner_diameter_source", "length_plan_m", "length_slope_m", "length_hydraulic_m",
               "length_choice", "pump_curve", "pump_power", "pump_speed", "pump_pattern", "valve_type",
               "valve_setting", "valve_curve")


CLIENT_FIELDS = ("name", "client_type", "status", "consumption_value", "consumption_unit", "connection_mode", "elevation")


def _pt(lon: float, lat: float) -> WKTElement:
    return WKTElement(f"POINT({lon!r} {lat!r})", srid=4326)


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
    link_ids = {row.label: row.id for row in link_rows}

    client_rows = []
    for c in fc.clients():
        p = c.properties
        client_rows.append(NetworkClient(
            version_id=version.id, uid=_uid(p.uid), label=c.id, node_id=ids[p.node], link_label=p.link,
            consumption_lps=to_lps(p.consumption_value, p.consumption_unit), geom=_pt(*c.geometry.coordinates),
            connection_geom=_pt(*p.connection) if p.connection else None,
            **{f: getattr(p, f) for f in CLIENT_FIELDS},
        ))
    shutoff_rows = [NetworkShutoff(
        version_id=version.id, uid=_uid(sh.properties.uid), label=sh.id, name=sh.properties.name,
        link_id=link_ids[sh.properties.link], position=sh.properties.position, state=sh.properties.state,
        geom=_pt(*sh.geometry.coordinates),
    ) for sh in fc.shutoffs()]
    session.add_all(client_rows + shutoff_rows)
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
    link_labels: dict[int, str] = {}
    for lk in session.scalars(links):
        link_labels[lk.id] = lk.label
        line = to_shape(lk.geom)
        props = {f: getattr(lk, f) for f in LINK_FIELDS}
        features.append(LinkFeature(
            id=lk.label, geometry=LineStringGeometry(coordinates=[(x, y) for x, y in line.coords]),
            properties=LinkProperties(uid=str(lk.uid), kind=lk.kind, from_node=labels[lk.from_node_id],
                                      to_node=labels[lk.to_node_id], **props),
        ))
    clients = select(NetworkClient).where(NetworkClient.version_id == version_id).order_by(NetworkClient.id)
    for c in session.scalars(clients):
        pt = to_shape(c.geom)
        conn = to_shape(c.connection_geom) if c.connection_geom is not None else None
        features.append(ClientFeature(
            id=c.label, geometry=PointGeometry(coordinates=(pt.x, pt.y)),
            properties=ClientProperties(uid=str(c.uid), node=labels[c.node_id], link=c.link_label,
                                        connection=(conn.x, conn.y) if conn else None,
                                        **{f: getattr(c, f) for f in CLIENT_FIELDS}),
        ))
    shutoffs = select(NetworkShutoff).where(NetworkShutoff.version_id == version_id).order_by(NetworkShutoff.id)
    for sh in session.scalars(shutoffs):
        pt = to_shape(sh.geom)
        features.append(ShutoffFeature(
            id=sh.label, geometry=PointGeometry(coordinates=(pt.x, pt.y)),
            properties=ShutoffProperties(uid=str(sh.uid), name=sh.name, link=link_labels[sh.link_id],
                                         position=sh.position, state=sh.state),
        ))
    return NetworkFeatureCollection(features=features)


def node_ids(session: Session, version_id: uuid.UUID) -> dict[str, int]:
    return dict(session.execute(select(NetworkNode.label, NetworkNode.id).where(NetworkNode.version_id == version_id)).all())


def link_ids(session: Session, version_id: uuid.UUID) -> dict[str, int]:
    return dict(session.execute(select(NetworkLink.label, NetworkLink.id).where(NetworkLink.version_id == version_id)).all())
