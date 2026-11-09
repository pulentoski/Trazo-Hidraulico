"""Etapa 2 (SIG): atributos de gestión, grifos, pozos, atributos libres, ortofotos y consultas guardadas.

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-09
"""
import geoalchemy2
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

JSON_EMPTY = sa.text("'{}'::jsonb")


def upgrade() -> None:
    # ── Tramos: estado físico, año de instalación y tipo de red (las observaciones usan «description») ──
    op.add_column("network_link", sa.Column("condition", sa.String(16), nullable=True))
    op.add_column("network_link", sa.Column("install_year", sa.Integer, nullable=True))
    op.add_column("network_link", sa.Column("network_type", sa.String(16), nullable=True))
    op.create_check_constraint("ck_link_condition", "network_link",
                               "condition IS NULL OR condition IN ('bueno','regular','malo','fuera_servicio')")
    op.create_check_constraint("ck_link_network_type", "network_link",
                               "network_type IS NULL OR network_type IN ('matriz','distribucion','aduccion','impulsion')")

    # ── Válvulas de corte: tipo, condición, diámetro, profundidad y atributos libres ──
    op.add_column("network_shutoff", sa.Column("valve_type", sa.String(16), nullable=True))
    op.add_column("network_shutoff", sa.Column("condition", sa.String(16), nullable=True))
    op.add_column("network_shutoff", sa.Column("diameter_mm", sa.Float, nullable=True))
    op.add_column("network_shutoff", sa.Column("depth_m", sa.Float, nullable=True))
    op.add_column("network_shutoff", sa.Column("extra", pg.JSONB, nullable=False, server_default=JSON_EMPTY))

    # ── Clientes: datos comerciales y atributos libres ──
    op.add_column("network_client", sa.Column("client_number", sa.String(40), nullable=True))
    op.add_column("network_client", sa.Column("address", sa.String(200), nullable=True))
    op.add_column("network_client", sa.Column("route", sa.String(40), nullable=True))
    op.add_column("network_client", sa.Column("meter_number", sa.String(40), nullable=True))
    op.add_column("network_client", sa.Column("extra", pg.JSONB, nullable=False, server_default=JSON_EMPTY))
    op.drop_constraint("ck_client_status", "network_client")
    op.create_check_constraint("ck_client_status", "network_client",
                               "status IN ('activo','proyectado','suspendido')")

    common = lambda: [  # noqa: E731
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("version_id", sa.Uuid, sa.ForeignKey("project_version.id", ondelete="CASCADE"), nullable=False,
                  index=True),
        sa.Column("uid", sa.Uuid, nullable=False),
        sa.Column("label", sa.String(31), nullable=False),
        sa.Column("geom", geoalchemy2.Geometry("POINT", srid=4326, spatial_index=False), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("condition", sa.String(16), nullable=True),
        sa.Column("extra", pg.JSONB, nullable=False, server_default=JSON_EMPTY),
    ]
    # ── Grifos: conectados a un nudo de consumo ──
    op.create_table(
        "network_hydrant", *common(),
        sa.Column("node_id", sa.BigInteger, sa.ForeignKey("network_node.id", ondelete="CASCADE"), nullable=False,
                  index=True),
        sa.Column("hydrant_type", sa.String(16), nullable=True),
        sa.Column("diameter_mm", sa.Float, nullable=True),
        sa.Column("fire_flow_lps", sa.Float, nullable=False, server_default="16"),
        sa.Column("min_pressure_m", sa.Float, nullable=False, server_default="5"),
        sa.UniqueConstraint("version_id", "label", name="uq_hydrant_label"),
    )
    # ── Pozos: fuente asociada (opcional) a un reservorio del modelo ──
    op.create_table(
        "network_well", *common(),
        sa.Column("node_id", sa.BigInteger, sa.ForeignKey("network_node.id", ondelete="CASCADE"), nullable=True,
                  index=True),
        sa.Column("ground_elevation", sa.Float, nullable=True),
        sa.Column("depth_m", sa.Float, nullable=True),
        sa.Column("static_level_m", sa.Float, nullable=True),
        sa.Column("dynamic_level_m", sa.Float, nullable=True),
        sa.Column("authorized_flow_lps", sa.Float, nullable=True),
        sa.UniqueConstraint("version_id", "label", name="uq_well_label"),
    )

    # ── Ortofotos por proyecto (el archivo vive en el almacenamiento compartido, no en la base) ──
    op.create_table(
        "orthophoto",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("project_id", sa.Uuid, sa.ForeignKey("project.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("source", sa.String(200), nullable=True),
        sa.Column("captured_on", sa.Date, nullable=True),
        sa.Column("georef", sa.String(12), nullable=False),  # geotiff | worldfile | gcp
        sa.Column("status", sa.String(12), nullable=False),  # uploaded | pending | processing | ready | error
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("original_name", sa.String(255), nullable=False),
        sa.Column("original_ext", sa.String(8), nullable=False),
        sa.Column("src_crs", sa.String(40), nullable=True),
        sa.Column("world", pg.JSONB, nullable=True),  # [A, D, B, E, C, F] del archivo world
        sa.Column("gcps", pg.JSONB, nullable=True),
        sa.Column("residual_m", sa.Float, nullable=True),
        sa.Column("width", sa.Integer, nullable=True),
        sa.Column("height", sa.Integer, nullable=True),
        sa.Column("bounds", pg.JSONB, nullable=True),  # [oeste, sur, este, norte] EPSG:4326
        sa.Column("size_bytes", sa.BigInteger, nullable=False),
        sa.Column("opacity", sa.Float, nullable=False, server_default="1"),
        sa.Column("visible", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("georef IN ('geotiff','worldfile','gcp')", name="ck_ortho_georef"),
        sa.CheckConstraint("status IN ('uploaded','pending','processing','ready','error')", name="ck_ortho_status"),
    )

    # ── Consultas guardadas por proyecto ──
    op.create_table(
        "saved_query",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("project_id", sa.Uuid, sa.ForeignKey("project.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("definition", pg.JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("project_id", "name", name="uq_saved_query_name"),
    )


def downgrade() -> None:
    op.drop_table("saved_query")
    op.drop_table("orthophoto")
    op.drop_table("network_well")
    op.drop_table("network_hydrant")
    op.drop_constraint("ck_client_status", "network_client")
    op.create_check_constraint("ck_client_status", "network_client", "status IN ('activo','proyectado')")
    for c in ("extra", "meter_number", "route", "address", "client_number"):
        op.drop_column("network_client", c)
    for c in ("extra", "depth_m", "diameter_mm", "condition", "valve_type"):
        op.drop_column("network_shutoff", c)
    op.drop_constraint("ck_link_network_type", "network_link")
    op.drop_constraint("ck_link_condition", "network_link")
    for c in ("network_type", "install_year", "condition"):
        op.drop_column("network_link", c)
