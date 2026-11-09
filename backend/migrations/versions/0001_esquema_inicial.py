"""Esquema inicial: proyectos, versiones inmutables, red, catálogo, perfiles y resultados.

Revision ID: 0001
Revises:
Create Date: 2026-11-08
"""
import geoalchemy2
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

IMMUTABLE_TABLES = ("project_version", "network_node", "network_link", "simulation_run", "result_node", "result_link")


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    op.create_table(
        "catalog_pipe",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("material", sa.String(20), nullable=False),
        sa.Column("standard", sa.String(60), nullable=False),
        sa.Column("dn", sa.Integer, nullable=False),
        sa.Column("pipe_class", sa.String(20), nullable=False),
        sa.Column("od_mm", sa.Float, nullable=False),
        sa.Column("wall_mm", sa.Float, nullable=False),
        sa.Column("inner_diameter_mm", sa.Float, nullable=False),
        sa.Column("hw_c", sa.Float, nullable=False),
        sa.Column("dw_roughness_mm", sa.Float, nullable=False),
        sa.Column("manning_n", sa.Float, nullable=False),
        sa.Column("verified", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("source", sa.Text, nullable=False),
        sa.UniqueConstraint("material", "dn", "pipe_class", name="uq_catalog_pipe"),
    )

    op.create_table(
        "design_profile",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("source", sa.Text, nullable=False),
        sa.Column("version", sa.String(40), nullable=False),
        sa.Column("valid_from", sa.Date, nullable=False),
        sa.Column("valid_to", sa.Date, nullable=True),
        sa.Column("verified", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("status", sa.String(40), nullable=False, server_default="no verificado"),
        sa.Column("criteria", pg.JSONB, nullable=False, server_default="[]"),
        sa.Column("notes", sa.Text, nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "project",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text, nullable=False, server_default=""),
        sa.Column("length_srid", sa.Integer, nullable=False, server_default="32719"),
        sa.Column("design_profile_id", sa.Integer, sa.ForeignKey("design_profile.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "project_version",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("project_id", sa.Uuid, sa.ForeignKey("project.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("number", sa.Integer, nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("label", sa.String(200)),
        sa.Column("parent_number", sa.Integer),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("options", pg.JSONB, nullable=False, server_default="{}"),
        sa.Column("aux", pg.JSONB, nullable=False, server_default="{}"),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.UniqueConstraint("project_id", "number", name="uq_version_number"),
        sa.CheckConstraint("kind IN ('auto','manual','import')", name="ck_version_kind"),
    )

    op.create_table(
        "network_node",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("version_id", sa.Uuid, sa.ForeignKey("project_version.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("uid", sa.Uuid, nullable=False),
        sa.Column("label", sa.String(31), nullable=False),
        sa.Column("kind", sa.String(12), nullable=False),
        sa.Column("geom", geoalchemy2.Geometry("POINT", srid=4326, spatial_index=False), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("elevation", sa.Float),
        sa.Column("elevation_source", sa.String(20), nullable=False, server_default="manual"),
        sa.Column("elevation_method", sa.String(160)),
        sa.Column("base_demand", sa.Float, nullable=False, server_default="0"),
        sa.Column("demand_pattern", sa.String(31)),
        sa.Column("demands", pg.JSONB, nullable=False, server_default="[]"),
        sa.Column("emitter_coeff", sa.Float),
        sa.Column("initial_quality", sa.Float),
        sa.Column("head", sa.Float),
        sa.Column("head_pattern", sa.String(31)),
        sa.Column("init_level", sa.Float),
        sa.Column("min_level", sa.Float),
        sa.Column("max_level", sa.Float),
        sa.Column("tank_diameter", sa.Float),
        sa.Column("min_volume", sa.Float),
        sa.Column("volume_curve", sa.String(31)),
        sa.Column("can_overflow", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("extra", pg.JSONB, nullable=False, server_default="{}"),
        sa.UniqueConstraint("version_id", "label", name="uq_node_label"),
        sa.CheckConstraint("kind IN ('junction','reservoir','tank')", name="ck_node_kind"),
        sa.CheckConstraint("elevation_source IN ('manual','inp','supuesta')", name="ck_elevation_source"),
    )
    op.create_index("idx_network_node_geom", "network_node", ["geom"], postgresql_using="gist")

    op.create_table(
        "network_link",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("version_id", sa.Uuid, sa.ForeignKey("project_version.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("uid", sa.Uuid, nullable=False),
        sa.Column("label", sa.String(31), nullable=False),
        sa.Column("kind", sa.String(8), nullable=False),
        sa.Column("from_node_id", sa.BigInteger, sa.ForeignKey("network_node.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("to_node_id", sa.BigInteger, sa.ForeignKey("network_node.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("geom", geoalchemy2.Geometry("LINESTRING", srid=4326, spatial_index=False), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("dn", sa.Integer),
        sa.Column("inner_diameter_mm", sa.Float),
        sa.Column("material", sa.String(20)),
        sa.Column("pipe_class", sa.String(20)),
        sa.Column("catalog_pipe_id", sa.Integer, sa.ForeignKey("catalog_pipe.id", ondelete="SET NULL")),
        sa.Column("roughness", sa.Float),
        sa.Column("minor_loss", sa.Float, nullable=False, server_default="0"),
        sa.Column("initial_status", sa.String(10), nullable=False, server_default="open"),
        sa.Column("length_plan_m", sa.Float),
        sa.Column("length_slope_m", sa.Float),
        sa.Column("length_hydraulic_m", sa.Float),
        sa.Column("length_choice", sa.String(10), nullable=False, server_default="slope"),
        sa.Column("pump_curve", sa.String(31)),
        sa.Column("pump_power", sa.Float),
        sa.Column("pump_speed", sa.Float),
        sa.Column("pump_pattern", sa.String(31)),
        sa.Column("valve_type", sa.String(4)),
        sa.Column("valve_setting", sa.Float),
        sa.Column("valve_curve", sa.String(31)),
        sa.Column("extra", pg.JSONB, nullable=False, server_default="{}"),
        sa.UniqueConstraint("version_id", "label", name="uq_link_label"),
        sa.CheckConstraint("kind IN ('pipe','pump','valve')", name="ck_link_kind"),
        sa.CheckConstraint("length_choice IN ('plan','slope','manual')", name="ck_length_choice"),
        sa.CheckConstraint("initial_status IN ('open','closed','cv')", name="ck_initial_status"),
    )
    op.create_index("idx_network_link_geom", "network_link", ["geom"], postgresql_using="gist")

    op.create_table(
        "simulation_run",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("version_id", sa.Uuid, sa.ForeignKey("project_version.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("engine", pg.JSONB, nullable=False),
        sa.Column("engine_version", sa.String(20), nullable=False),
        sa.Column("options", pg.JSONB, nullable=False),
        sa.Column("inp_sha256", sa.String(64), nullable=False),
        sa.Column("messages", pg.JSONB, nullable=False, server_default="[]"),
        sa.Column("report_start", sa.Integer, nullable=False, server_default="0"),
        sa.Column("report_step", sa.Integer, nullable=False, server_default="3600"),
        sa.Column("duration", sa.Integer, nullable=False, server_default="0"),
        sa.Column("n_periods", sa.Integer, nullable=False, server_default="0"),
        sa.Column("elapsed_ms", sa.Float, nullable=False, server_default="0"),
    )

    op.create_table(
        "result_node",
        sa.Column("run_id", sa.Uuid, sa.ForeignKey("simulation_run.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("node_id", sa.BigInteger, sa.ForeignKey("network_node.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("period", sa.Integer, primary_key=True),
        sa.Column("t_seconds", sa.Integer, nullable=False),
        sa.Column("demand", sa.Float, nullable=False),
        sa.Column("head", sa.Float, nullable=False),
        sa.Column("pressure", sa.Float, nullable=False),
    )
    op.create_table(
        "result_link",
        sa.Column("run_id", sa.Uuid, sa.ForeignKey("simulation_run.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("link_id", sa.BigInteger, sa.ForeignKey("network_link.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("period", sa.Integer, primary_key=True),
        sa.Column("t_seconds", sa.Integer, nullable=False),
        sa.Column("flow", sa.Float, nullable=False),
        sa.Column("velocity", sa.Float, nullable=False),
        sa.Column("headloss", sa.Float, nullable=False),
        sa.Column("status", sa.SmallInteger, nullable=False),
        sa.Column("setting", sa.Float, nullable=False),
    )

    # Inmutabilidad: las versiones del modelo y sus resultados no se modifican nunca (solo se borran en cascada).
    op.execute(
        """
        CREATE OR REPLACE FUNCTION trazo_prevent_update() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'La tabla % es inmutable: cree una nueva versión del modelo', TG_TABLE_NAME
                USING ERRCODE = 'restrict_violation';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    for table in IMMUTABLE_TABLES:
        op.execute(f"CREATE TRIGGER trg_{table}_immutable BEFORE UPDATE ON {table} "
                   f"FOR EACH ROW EXECUTE FUNCTION trazo_prevent_update()")


def downgrade() -> None:
    for table in ("result_link", "result_node", "simulation_run", "network_link", "network_node",
                  "project_version", "project", "design_profile", "catalog_pipe"):
        op.drop_table(table)
    op.execute("DROP FUNCTION IF EXISTS trazo_prevent_update()")
