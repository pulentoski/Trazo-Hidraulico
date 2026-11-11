"""Página «Gestión»: registros de operación (energía, cloro, cortes, reclamos, mantenciones, lecturas de clientes),
historial de factibilidades y configuración de indicadores por proyecto.

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-11
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def _base() -> list[sa.Column]:
    return [
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("project_id", sa.Uuid, sa.ForeignKey("project.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_by", sa.String(254), nullable=True),
    ]


def upgrade() -> None:
    op.add_column("project", sa.Column("gestion_settings", JSONB, nullable=True))
    op.create_table("energy_record", *_base(),
                    sa.Column("record_date", sa.Date, nullable=False),
                    sa.Column("equipment", sa.String(31), nullable=False),
                    sa.Column("kwh", sa.Float, nullable=False),
                    sa.Column("hours", sa.Float, nullable=True),
                    sa.Column("volume_m3", sa.Float, nullable=True),
                    sa.Column("note", sa.String(300), nullable=True))
    op.create_table("chlorine_record", *_base(),
                    sa.Column("measured_at", sa.DateTime(timezone=True), nullable=False),
                    sa.Column("point", sa.String(60), nullable=False),
                    sa.Column("mg_l", sa.Float, nullable=False),
                    sa.Column("note", sa.String(300), nullable=True))
    op.create_table("service_outage", *_base(),
                    sa.Column("kind", sa.String(12), nullable=False),
                    sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
                    sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
                    sa.Column("sector", sa.String(31), nullable=True),
                    sa.Column("link_id", sa.String(31), nullable=True),
                    sa.Column("clients_affected", sa.Integer, nullable=False, server_default="0"),
                    sa.Column("note", sa.String(300), nullable=True))
    op.create_table("complaint", *_base(),
                    sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
                    sa.Column("client", sa.String(40), nullable=True),
                    sa.Column("kind", sa.String(20), nullable=False),
                    sa.Column("status", sa.String(12), nullable=False),
                    sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
                    sa.Column("note", sa.String(300), nullable=True))
    op.create_table("maintenance_task", *_base(),
                    sa.Column("kind", sa.String(24), nullable=False),
                    sa.Column("element", sa.String(31), nullable=True),
                    sa.Column("description", sa.String(200), nullable=True),
                    sa.Column("frequency_days", sa.Integer, nullable=True),
                    sa.Column("next_date", sa.Date, nullable=False),
                    sa.Column("assignee", sa.String(120), nullable=True),
                    sa.Column("done_on", sa.Date, nullable=True),
                    sa.Column("last_done", sa.Date, nullable=True))
    op.create_table("maintenance_log",
                    sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
                    sa.Column("task_id", sa.BigInteger, sa.ForeignKey("maintenance_task.id", ondelete="CASCADE"),
                              nullable=False, index=True),
                    sa.Column("project_id", sa.Uuid, sa.ForeignKey("project.id", ondelete="CASCADE"), nullable=False,
                              index=True),
                    sa.Column("done_on", sa.Date, nullable=False),
                    sa.Column("scheduled_for", sa.Date, nullable=True),
                    sa.Column("by", sa.String(120), nullable=True),
                    sa.Column("note", sa.String(300), nullable=True),
                    sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_table("client_reading", *_base(),
                    sa.Column("client", sa.String(31), nullable=False),
                    sa.Column("period", sa.String(7), nullable=False),
                    sa.Column("m3", sa.Float, nullable=False),
                    sa.UniqueConstraint("project_id", "client", "period", name="uq_client_reading"))
    op.create_table("feasibility_record", *_base(),
                    sa.Column("model_version", sa.Integer, nullable=False),
                    sa.Column("link_id", sa.String(31), nullable=False),
                    sa.Column("location", JSONB, nullable=False),
                    sa.Column("consumption_lps", sa.Float, nullable=False),
                    sa.Column("elevation", sa.Float, nullable=True),
                    sa.Column("feasible", sa.Boolean, nullable=False),
                    sa.Column("pressure_new", sa.Float, nullable=True),
                    sa.Column("bottleneck", sa.String(31), nullable=True),
                    sa.Column("name", sa.String(200), nullable=True))


def downgrade() -> None:
    for t in ("feasibility_record", "client_reading", "maintenance_log", "maintenance_task", "complaint",
              "service_outage", "chlorine_record", "energy_record"):
        op.drop_table(t)
    op.drop_column("project", "gestion_settings")
