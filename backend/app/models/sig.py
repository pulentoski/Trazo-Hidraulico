"""Ortofotos y consultas guardadas (por proyecto, fuera de las versiones del modelo)."""
import uuid
from datetime import date, datetime

from sqlalchemy import BigInteger, Boolean, Date, DateTime, Float, ForeignKey, Identity, Integer, String, Text, Uuid, func  # noqa: F401
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Orthophoto(Base):
    __tablename__ = "orthophoto"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("project.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    source: Mapped[str | None] = mapped_column(String(200), nullable=True)
    captured_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    georef: Mapped[str] = mapped_column(String(12))
    status: Mapped[str] = mapped_column(String(12))
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    original_name: Mapped[str] = mapped_column(String(255))
    original_ext: Mapped[str] = mapped_column(String(8))
    src_crs: Mapped[str | None] = mapped_column(String(40), nullable=True)
    world: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    gcps: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    residual_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bounds: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    opacity: Mapped[float] = mapped_column(Float, default=1.0)
    visible: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SavedQuery(Base):
    __tablename__ = "saved_query"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("project.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    definition: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


__all__ = ["Orthophoto", "SavedQuery"]
