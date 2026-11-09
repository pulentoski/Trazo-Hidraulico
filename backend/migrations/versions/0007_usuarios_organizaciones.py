"""Etapa 5: usuarios, organizaciones, roles, sesiones, invitaciones, recuperación, auditoría, uso y revisiones.

Los proyectos existentes pasan a la organización «Organización inicial».

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-09
"""
import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "organization",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False, server_default="apr"),  # apr | consultora | sanitaria | otra
        sa.Column("plan", sa.String(20), nullable=False, server_default="basico"),
        sa.Column("limits", pg.JSONB, nullable=True),
        sa.Column("suspended", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("name", name="uq_organization_name"),
    )
    op.create_table(
        "app_user",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("name", sa.String(200), nullable=False, server_default=""),
        sa.Column("password_hash", sa.String(255), nullable=True),
        sa.Column("is_superadmin", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("mfa_secret", sa.String(64), nullable=True),
        sa.Column("mfa_enabled", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("failed_logins", sa.Integer, nullable=False, server_default="0"),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("uq_app_user_email", "app_user", [sa.text("lower(email)")], unique=True)
    op.create_table(
        "membership",
        sa.Column("user_id", sa.Uuid, sa.ForeignKey("app_user.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("org_id", sa.Uuid, sa.ForeignKey("organization.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("role IN ('admin','proyectista','revisor','lector')", name="ck_membership_role"),
    )
    op.create_table(
        "user_session",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.Uuid, sa.ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("org_id", sa.Uuid, sa.ForeignKey("organization.id", ondelete="SET NULL"), nullable=True),
        sa.Column("mfa_pending", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("ip", sa.String(64), nullable=True),
        sa.Column("user_agent", sa.String(300), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "one_time_token",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("purpose", sa.String(16), nullable=False),  # reset | invite
        sa.Column("user_id", sa.Uuid, sa.ForeignKey("app_user.id", ondelete="CASCADE"), nullable=True),
        sa.Column("org_id", sa.Uuid, sa.ForeignKey("organization.id", ondelete="CASCADE"), nullable=True),
        sa.Column("email", sa.String(254), nullable=True),
        sa.Column("role", sa.String(16), nullable=True),
        sa.Column("created_by", sa.Uuid, sa.ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("org_id", sa.Uuid, sa.ForeignKey("organization.id", ondelete="CASCADE"), nullable=True, index=True),
        sa.Column("user_id", sa.Uuid, sa.ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True),
        sa.Column("user_email", sa.String(254), nullable=True),
        sa.Column("action", sa.String(60), nullable=False),
        sa.Column("project_id", sa.Uuid, nullable=True),
        sa.Column("version", sa.Integer, nullable=True),
        sa.Column("detail", pg.JSONB, nullable=True),
        sa.Column("ip", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False, index=True),
    )
    op.create_table(
        "usage_counter",
        sa.Column("org_id", sa.Uuid, sa.ForeignKey("organization.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("month", sa.String(7), primary_key=True),  # AAAA-MM
        sa.Column("kind", sa.String(20), primary_key=True),  # map_load | simulation
        sa.Column("count", sa.BigInteger, nullable=False, server_default="0"),
    )
    op.create_table(
        "version_review",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("version_id", sa.Uuid, sa.ForeignKey("project_version.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("user_id", sa.Uuid, sa.ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True),
        sa.Column("user_email", sa.String(254), nullable=True),
        sa.Column("status", sa.String(12), nullable=False),  # comentario | aprobada | observada
        sa.Column("comment", sa.Text, nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('comentario','aprobada','observada')", name="ck_review_status"),
    )
    # Proyectos existentes → organización inicial.
    org_id = uuid.uuid4()
    op.execute(sa.text("INSERT INTO organization (id, name, kind, plan) VALUES (:id, 'Organización inicial', 'otra', "
                       "'ilimitado')").bindparams(id=org_id))
    op.add_column("project", sa.Column("org_id", sa.Uuid, sa.ForeignKey("organization.id", ondelete="CASCADE"),
                                       nullable=True))
    op.execute(sa.text("UPDATE project SET org_id = :id").bindparams(id=org_id))
    op.alter_column("project", "org_id", nullable=False)
    op.create_index("ix_project_org", "project", ["org_id"])


def downgrade() -> None:
    op.drop_index("ix_project_org", "project")
    op.drop_column("project", "org_id")
    for t in ("version_review", "usage_counter", "audit_log", "one_time_token", "user_session", "membership"):
        op.drop_table(t)
    op.drop_index("uq_app_user_email", "app_user")
    op.drop_table("app_user")
    op.drop_table("organization")
