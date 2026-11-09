"""Etapa 4: diseño de bombeo del pozo, registro de mediciones y tolerancias de comparación.

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-09
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("network_well", sa.Column("pump_design", pg.JSONB, nullable=True))
    op.add_column("project", sa.Column("monitoring", pg.JSONB, nullable=True))
    op.create_table(
        "measurement",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("project_id", sa.Uuid, sa.ForeignKey("project.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("element_type", sa.String(12), nullable=False),  # node | link | client | well
        sa.Column("element_id", sa.String(31), nullable=False),
        sa.Column("kind", sa.String(12), nullable=False),  # meter | pressure | level
        sa.Column("measured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("value", sa.Float, nullable=False),
        sa.Column("note", sa.String(200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("element_type IN ('node','link','client','well')", name="ck_measurement_element"),
        sa.CheckConstraint("kind IN ('meter','pressure','level')", name="ck_measurement_kind"),
    )
    op.create_index("ix_measurement_element", "measurement", ["project_id", "element_type", "element_id", "kind",
                                                              "measured_at"])


def downgrade() -> None:
    op.drop_index("ix_measurement_element", "measurement")
    op.drop_table("measurement")
    op.drop_column("project", "monitoring")
    op.drop_column("network_well", "pump_design")
