"""Ajustes por organización (perfil de diseño por defecto, vida útil y precios por metro).

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-11
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("organization", sa.Column("settings", JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("organization", "settings")
