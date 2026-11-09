"""Clientes, llaves de corte, escenarios, parámetros de diseño por proyecto y catálogo ModeloPozo.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-09
"""
import geoalchemy2
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

from app.data.modelopozo import ROUGHNESS, SOURCE, load_json

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Catálogo: diámetro exterior y espesor opcionales; observaciones de revisión ──
    op.alter_column("catalog_pipe", "od_mm", nullable=True)
    op.alter_column("catalog_pipe", "wall_mm", nullable=True)
    op.add_column("catalog_pipe", sa.Column("review", sa.Text, nullable=True))
    catalog = sa.table("catalog_pipe", *(sa.column(c) for c in (
        "material", "standard", "dn", "pipe_class", "od_mm", "wall_mm", "inner_diameter_mm", "hw_c",
        "dw_roughness_mm", "manning_n", "verified", "source", "review")))
    rows = []
    for r in load_json():
        c, eps, n = ROUGHNESS[r["material"]]
        cell = f" Celda {r['cell']}" + (f" ({r['formula']})" if r["formula"] else "") + "."
        rows.append(dict(material=r["material"], standard="Planilla ModeloPozo", dn=r["dn"], pipe_class=r["pipe_class"],
                         od_mm=r["od_mm"], wall_mm=r["wall_mm"], inner_diameter_mm=r["inner_diameter_mm"],
                         hw_c=c, dw_roughness_mm=eps, manning_n=n, verified=False, source=SOURCE + "." + cell,
                         review="; ".join(r["review"]) or None))
    op.bulk_insert(catalog, rows)

    # ── Tramos: origen del diámetro interior (catálogo o manual) ──
    op.add_column("network_link", sa.Column("inner_diameter_source", sa.String(10), nullable=False,
                                            server_default="catalogo"))
    op.execute("ALTER TABLE network_link DISABLE TRIGGER trg_network_link_immutable")
    op.execute("UPDATE network_link SET inner_diameter_source = 'manual' WHERE catalog_pipe_id IS NULL")
    op.execute("ALTER TABLE network_link ENABLE TRIGGER trg_network_link_immutable")

    # ── Versiones: escenarios de llaves; proyectos: parámetros de diseño editables ──
    op.add_column("project_version", sa.Column("scenarios", pg.JSONB, nullable=False, server_default="[]"))
    op.add_column("project", sa.Column("design_params", pg.JSONB, nullable=True))

    # ── Clientes (arranques) ──
    op.create_table(
        "network_client",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("version_id", sa.Uuid, sa.ForeignKey("project_version.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("uid", sa.Uuid, nullable=False),
        sa.Column("label", sa.String(31), nullable=False),
        sa.Column("name", sa.String(200), nullable=True),
        sa.Column("client_type", sa.String(12), nullable=False),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("consumption_value", sa.Float, nullable=False),
        sa.Column("consumption_unit", sa.String(8), nullable=False),
        sa.Column("consumption_lps", sa.Float, nullable=False),
        sa.Column("node_id", sa.BigInteger, sa.ForeignKey("network_node.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("link_label", sa.String(31), nullable=True),
        sa.Column("connection_mode", sa.String(10), nullable=False, server_default="nearest"),
        sa.Column("elevation", sa.Float, nullable=True),
        sa.Column("geom", geoalchemy2.Geometry("POINT", srid=4326, spatial_index=False), nullable=False),
        sa.Column("connection_geom", geoalchemy2.Geometry("POINT", srid=4326, spatial_index=False), nullable=True),
        sa.UniqueConstraint("version_id", "label", name="uq_client_label"),
        sa.CheckConstraint("client_type IN ('residencial','comercial','industrial','publico')", name="ck_client_type"),
        sa.CheckConstraint("status IN ('activo','proyectado')", name="ck_client_status"),
        sa.CheckConstraint("consumption_unit IN ('L/s','m3/mes')", name="ck_client_unit"),
    )
    op.create_index("idx_network_client_geom", "network_client", ["geom"], postgresql_using="gist")

    # ── Llaves (válvulas de corte) sobre tuberías ──
    op.create_table(
        "network_shutoff",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("version_id", sa.Uuid, sa.ForeignKey("project_version.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("uid", sa.Uuid, nullable=False),
        sa.Column("label", sa.String(31), nullable=False),
        sa.Column("name", sa.String(200), nullable=True),
        sa.Column("link_id", sa.BigInteger, sa.ForeignKey("network_link.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("position", sa.Float, nullable=False),
        sa.Column("state", sa.String(8), nullable=False),
        sa.Column("geom", geoalchemy2.Geometry("POINT", srid=4326, spatial_index=False), nullable=False),
        sa.UniqueConstraint("version_id", "label", name="uq_shutoff_label"),
        sa.CheckConstraint("state IN ('open','closed')", name="ck_shutoff_state"),
        sa.CheckConstraint("position >= 0 AND position <= 1", name="ck_shutoff_position"),
    )
    for table in ("network_client", "network_shutoff"):
        op.execute(f"CREATE TRIGGER trg_{table}_immutable BEFORE UPDATE ON {table} "
                   f"FOR EACH ROW EXECUTE FUNCTION trazo_prevent_update()")


def downgrade() -> None:
    op.drop_table("network_shutoff")
    op.drop_table("network_client")
    op.drop_column("project", "design_params")
    op.drop_column("project_version", "scenarios")
    op.drop_column("network_link", "inner_diameter_source")
    op.execute("DELETE FROM catalog_pipe WHERE standard = 'Planilla ModeloPozo'")
    op.drop_column("catalog_pipe", "review")
