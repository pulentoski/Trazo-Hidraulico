"""Panel general del proyecto: eventos de pérdidas por tramo y configuración del resumen.

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-10
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("project", sa.Column("summary_settings", pg.JSONB, nullable=True))
    op.create_table(
        "leak_event",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("project_id", sa.Uuid, sa.ForeignKey("project.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("link_id", sa.String(31), nullable=False),  # ID del tramo (etiqueta EPANET)
        sa.Column("event_date", sa.Date, nullable=False),
        sa.Column("kind", sa.String(12), nullable=False),  # fuga | rotura | reparacion
        sa.Column("flow_lps", sa.Float, nullable=True),
        sa.Column("note", sa.String(300), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("kind IN ('fuga','rotura','reparacion')", name="ck_leak_kind"),
    )


def downgrade() -> None:
    op.drop_table("leak_event")
    op.drop_column("project", "summary_settings")
