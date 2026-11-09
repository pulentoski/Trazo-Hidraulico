"""Etapa 3: operación de bombas (horario, control por nivel, curva por puntos) y proyección de demanda.

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-09
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("network_link", sa.Column("schedule", pg.JSONB, nullable=True))
    op.add_column("network_link", sa.Column("level_control", pg.JSONB, nullable=True))
    op.add_column("network_link", sa.Column("curve_points", pg.JSONB, nullable=True))
    op.add_column("project", sa.Column("demand_projection", pg.JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("project", "demand_projection")
    for c in ("curve_points", "level_control", "schedule"):
        op.drop_column("network_link", c)
