"""Configuración de la plataforma (key de Google Maps y Map ID), con los valores sensibles cifrados.

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-11
"""
import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "platform_setting",
        sa.Column("key", sa.String(60), primary_key=True),
        sa.Column("value", sa.Text, nullable=False),  # cifrado (Fernet) si el valor es sensible
        sa.Column("encrypted", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_by", sa.String(200), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("platform_setting")
