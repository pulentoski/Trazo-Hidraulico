from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class CatalogPipe(Base):
    """Catálogo de tuberías comerciales (PVC, HDPE). Diámetros en mm."""

    __tablename__ = "catalog_pipe"
    __table_args__ = (UniqueConstraint("material", "dn", "pipe_class", name="uq_catalog_pipe"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    material: Mapped[str] = mapped_column(String(20))
    standard: Mapped[str] = mapped_column(String(60))
    dn: Mapped[int] = mapped_column(Integer)
    pipe_class: Mapped[str] = mapped_column(String(20))
    od_mm: Mapped[float] = mapped_column(Float)
    wall_mm: Mapped[float] = mapped_column(Float)
    inner_diameter_mm: Mapped[float] = mapped_column(Float)
    hw_c: Mapped[float] = mapped_column(Float)
    dw_roughness_mm: Mapped[float] = mapped_column(Float)
    manning_n: Mapped[float] = mapped_column(Float)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[str] = mapped_column(Text)


class DesignProfile(Base):
    """Perfil de criterios de diseño. Queda 'no verificado' hasta su revisión formal."""

    __tablename__ = "design_profile"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    source: Mapped[str] = mapped_column(Text)
    version: Mapped[str] = mapped_column(String(40))
    valid_from: Mapped[date] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(40), default="no verificado")
    # Lista de criterios: [{key, label, min, max, unit}]
    criteria: Mapped[list] = mapped_column(JSONB, default=list)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
