"""Datos de la organización (RUT, contacto, comuna…) y modo soporte del superadministrador en la sesión.

Revision ID: 0013
Revises: 0012
Create Date: 2026-11-17
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("organization", sa.Column("info", JSONB, nullable=True))
    op.add_column("user_session", sa.Column("support_org_id", sa.Uuid, sa.ForeignKey("organization.id", ondelete="SET NULL"),
                                            nullable=True))


def downgrade() -> None:
    op.drop_column("user_session", "support_org_id")
    op.drop_column("organization", "info")
