import uuid

from geoalchemy2 import Geometry
from sqlalchemy import (BigInteger, Boolean, CheckConstraint, Float, ForeignKey, Identity, Integer, String,
                        Text, UniqueConstraint, Uuid)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class NetworkNode(Base):
    """Nudo de la red: junction (nudo de consumo), reservoir (reservorio) o tank (estanque)."""

    __tablename__ = "network_node"
    __table_args__ = (
        UniqueConstraint("version_id", "label", name="uq_node_label"),
        CheckConstraint("kind IN ('junction','reservoir','tank')", name="ck_node_kind"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("project_version.id", ondelete="CASCADE"), index=True)
    uid: Mapped[uuid.UUID] = mapped_column(Uuid)
    label: Mapped[str] = mapped_column(String(31))
    kind: Mapped[str] = mapped_column(String(12))
    geom = mapped_column(Geometry("POINT", srid=4326, spatial_index=True), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Cota (m): valor + fuente (manual | inp | supuesta) + método (texto libre).
    elevation: Mapped[float | None] = mapped_column(Float, nullable=True)
    elevation_source: Mapped[str] = mapped_column(String(20), default="manual")
    elevation_method: Mapped[str | None] = mapped_column(String(160), nullable=True)

    # Junction
    base_demand: Mapped[float] = mapped_column(Float, default=0.0)  # L/s
    demand_pattern: Mapped[str | None] = mapped_column(String(31), nullable=True)
    demands: Mapped[list] = mapped_column(JSONB, default=list)  # categorías adicionales
    emitter_coeff: Mapped[float | None] = mapped_column(Float, nullable=True)
    initial_quality: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Reservoir
    head: Mapped[float | None] = mapped_column(Float, nullable=True)  # carga total (m)
    head_pattern: Mapped[str | None] = mapped_column(String(31), nullable=True)

    # Tank (m, m³)
    init_level: Mapped[float | None] = mapped_column(Float, nullable=True)
    min_level: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_level: Mapped[float | None] = mapped_column(Float, nullable=True)
    tank_diameter: Mapped[float | None] = mapped_column(Float, nullable=True)
    min_volume: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume_curve: Mapped[str | None] = mapped_column(String(31), nullable=True)
    can_overflow: Mapped[bool] = mapped_column(Boolean, default=False)

    extra: Mapped[dict] = mapped_column(JSONB, default=dict)


class NetworkLink(Base):
    """Tramo de la red. La geometría (LineString con vértices) es independiente de la topología."""

    __tablename__ = "network_link"
    __table_args__ = (
        UniqueConstraint("version_id", "label", name="uq_link_label"),
        CheckConstraint("kind IN ('pipe','pump','valve')", name="ck_link_kind"),
        CheckConstraint("length_choice IN ('plan','slope','manual')", name="ck_length_choice"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("project_version.id", ondelete="CASCADE"), index=True)
    uid: Mapped[uuid.UUID] = mapped_column(Uuid)
    label: Mapped[str] = mapped_column(String(31))
    kind: Mapped[str] = mapped_column(String(8))
    from_node_id: Mapped[int] = mapped_column(ForeignKey("network_node.id", ondelete="CASCADE"), index=True)
    to_node_id: Mapped[int] = mapped_column(ForeignKey("network_node.id", ondelete="CASCADE"), index=True)
    geom = mapped_column(Geometry("LINESTRING", srid=4326, spatial_index=True), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Tubería
    dn: Mapped[int | None] = mapped_column(Integer, nullable=True)  # diámetro nominal (mm)
    inner_diameter_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    material: Mapped[str | None] = mapped_column(String(20), nullable=True)
    pipe_class: Mapped[str | None] = mapped_column(String(20), nullable=True)
    catalog_pipe_id: Mapped[int | None] = mapped_column(
        ForeignKey("catalog_pipe.id", ondelete="SET NULL"), nullable=True
    )
    inner_diameter_source: Mapped[str] = mapped_column(String(10), default="catalogo")  # catalogo | manual
    # Rugosidad: C (H-W), ε en mm (D-W) o n (C-M) según la fórmula de la versión.
    roughness: Mapped[float | None] = mapped_column(Float, nullable=True)
    minor_loss: Mapped[float] = mapped_column(Float, default=0.0)
    initial_status: Mapped[str] = mapped_column(String(10), default="open")  # open | closed | cv | active

    # Largos (m)
    length_plan_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    length_slope_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    length_hydraulic_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    length_choice: Mapped[str] = mapped_column(String(10), default="slope")

    # Bomba
    pump_curve: Mapped[str | None] = mapped_column(String(31), nullable=True)
    pump_power: Mapped[float | None] = mapped_column(Float, nullable=True)  # kW
    pump_speed: Mapped[float | None] = mapped_column(Float, nullable=True)
    pump_pattern: Mapped[str | None] = mapped_column(String(31), nullable=True)

    # Válvula
    valve_type: Mapped[str | None] = mapped_column(String(4), nullable=True)
    valve_setting: Mapped[float | None] = mapped_column(Float, nullable=True)
    valve_curve: Mapped[str | None] = mapped_column(String(31), nullable=True)

    # Gestión (SIG): estado físico, año de instalación y tipo de red. Observaciones = description.
    condition: Mapped[str | None] = mapped_column(String(16), nullable=True)
    install_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    network_type: Mapped[str | None] = mapped_column(String(16), nullable=True)

    # Operación (bombas y válvulas de control): horario 0/1 por hora, control por nivel y curva H-Q por puntos.
    schedule: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    level_control: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    curve_points: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    extra: Mapped[dict] = mapped_column(JSONB, default=dict)  # atributos libres


class NetworkClient(Base):
    """Cliente (arranque): consumo asignado a un nudo de consumo. Su demanda se suma a la del nudo."""

    __tablename__ = "network_client"
    __table_args__ = (UniqueConstraint("version_id", "label", name="uq_client_label"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("project_version.id", ondelete="CASCADE"), index=True)
    uid: Mapped[uuid.UUID] = mapped_column(Uuid)
    label: Mapped[str] = mapped_column(String(31))
    name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    client_type: Mapped[str] = mapped_column(String(12))
    status: Mapped[str] = mapped_column(String(12))
    consumption_value: Mapped[float] = mapped_column(Float)
    consumption_unit: Mapped[str] = mapped_column(String(8))
    consumption_lps: Mapped[float] = mapped_column(Float)
    node_id: Mapped[int] = mapped_column(ForeignKey("network_node.id", ondelete="CASCADE"), index=True)
    link_label: Mapped[str | None] = mapped_column(String(31), nullable=True)
    connection_mode: Mapped[str] = mapped_column(String(10), default="nearest")
    elevation: Mapped[float | None] = mapped_column(Float, nullable=True)
    geom = mapped_column(Geometry("POINT", srid=4326, spatial_index=False), nullable=False)
    connection_geom = mapped_column(Geometry("POINT", srid=4326, spatial_index=False), nullable=True)
    client_number: Mapped[str | None] = mapped_column(String(40), nullable=True)
    address: Mapped[str | None] = mapped_column(String(200), nullable=True)
    route: Mapped[str | None] = mapped_column(String(40), nullable=True)
    meter_number: Mapped[str | None] = mapped_column(String(40), nullable=True)
    extra: Mapped[dict] = mapped_column(JSONB, default=dict)


class NetworkShutoff(Base):
    """Llave (válvula de corte) sobre una tubería: abierta o cerrada. Cerrada = tramo cerrado en EPANET."""

    __tablename__ = "network_shutoff"
    __table_args__ = (UniqueConstraint("version_id", "label", name="uq_shutoff_label"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("project_version.id", ondelete="CASCADE"), index=True)
    uid: Mapped[uuid.UUID] = mapped_column(Uuid)
    label: Mapped[str] = mapped_column(String(31))
    name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    link_id: Mapped[int] = mapped_column(ForeignKey("network_link.id", ondelete="CASCADE"), index=True)
    position: Mapped[float] = mapped_column(Float)
    state: Mapped[str] = mapped_column(String(8))
    geom = mapped_column(Geometry("POINT", srid=4326, spatial_index=False), nullable=False)
    valve_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    condition: Mapped[str | None] = mapped_column(String(16), nullable=True)
    diameter_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    depth_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    extra: Mapped[dict] = mapped_column(JSONB, default=dict)


class NetworkHydrant(Base):
    """Grifo contra incendio conectado a un nudo de consumo."""

    __tablename__ = "network_hydrant"
    __table_args__ = (UniqueConstraint("version_id", "label", name="uq_hydrant_label"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("project_version.id", ondelete="CASCADE"), index=True)
    uid: Mapped[uuid.UUID] = mapped_column(Uuid)
    label: Mapped[str] = mapped_column(String(31))
    geom = mapped_column(Geometry("POINT", srid=4326, spatial_index=False), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    condition: Mapped[str | None] = mapped_column(String(16), nullable=True)
    extra: Mapped[dict] = mapped_column(JSONB, default=dict)
    node_id: Mapped[int] = mapped_column(ForeignKey("network_node.id", ondelete="CASCADE"), index=True)
    hydrant_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    diameter_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    fire_flow_lps: Mapped[float] = mapped_column(Float, default=16.0)
    min_pressure_m: Mapped[float] = mapped_column(Float, default=5.0)


class NetworkWell(Base):
    """Pozo (captación). Puede asociarse al reservorio que lo representa en el modelo hidráulico."""

    __tablename__ = "network_well"
    __table_args__ = (UniqueConstraint("version_id", "label", name="uq_well_label"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("project_version.id", ondelete="CASCADE"), index=True)
    uid: Mapped[uuid.UUID] = mapped_column(Uuid)
    label: Mapped[str] = mapped_column(String(31))
    geom = mapped_column(Geometry("POINT", srid=4326, spatial_index=False), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    condition: Mapped[str | None] = mapped_column(String(16), nullable=True)
    extra: Mapped[dict] = mapped_column(JSONB, default=dict)
    node_id: Mapped[int | None] = mapped_column(ForeignKey("network_node.id", ondelete="CASCADE"), nullable=True,
                                                index=True)
    ground_elevation: Mapped[float | None] = mapped_column(Float, nullable=True)
    depth_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    static_level_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    dynamic_level_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    authorized_flow_lps: Mapped[float | None] = mapped_column(Float, nullable=True)
