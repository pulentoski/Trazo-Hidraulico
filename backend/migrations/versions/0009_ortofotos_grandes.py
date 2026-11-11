"""Ortofotos grandes: subida por partes (estado «uploading» y bytes recibidos) y reducción de resolución.

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-11
"""
import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("orthophoto", sa.Column("upload_offset", sa.BigInteger, nullable=True))
    op.add_column("orthophoto", sa.Column("target_res_m", sa.Float, nullable=True))
    op.add_column("orthophoto", sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                                          nullable=True))
    op.drop_constraint("ck_ortho_status", "orthophoto", type_="check")
    op.create_check_constraint("ck_ortho_status", "orthophoto",
                               "status IN ('uploading','uploaded','pending','processing','ready','error')")


def downgrade() -> None:
    op.execute("DELETE FROM orthophoto WHERE status = 'uploading'")
    op.drop_constraint("ck_ortho_status", "orthophoto", type_="check")
    op.create_check_constraint("ck_ortho_status", "orthophoto",
                               "status IN ('uploaded','pending','processing','ready','error')")
    op.drop_column("orthophoto", "updated_at")
    op.drop_column("orthophoto", "target_res_m")
    op.drop_column("orthophoto", "upload_offset")
