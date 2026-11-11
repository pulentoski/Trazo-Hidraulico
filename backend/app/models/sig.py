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


class Measurement(Base):
    """Medición real: lectura de medidor (m³), presión (m) o nivel (m) de un elemento, con fecha y hora."""

    __tablename__ = "measurement"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("project.id", ondelete="CASCADE"), index=True)
    element_type: Mapped[str] = mapped_column(String(12))
    element_id: Mapped[str] = mapped_column(String(31))
    kind: Mapped[str] = mapped_column(String(12))
    measured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    value: Mapped[float] = mapped_column(Float)
    note: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SavedQuery(Base):
    __tablename__ = "saved_query"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("project.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    definition: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LeakEvent(Base):
    """Evento de pérdidas en un tramo: fuga, rotura o reparación (registro del operador)."""
    __tablename__ = "leak_event"
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("project.id", ondelete="CASCADE"), index=True)
    link_id: Mapped[str] = mapped_column(String(31))
    event_date: Mapped[date] = mapped_column(Date)
    kind: Mapped[str] = mapped_column(String(12))
    flow_lps: Mapped[float | None] = mapped_column(Float, nullable=True)
    note: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


__all__ = ["LeakEvent", "Measurement", "Orthophoto", "SavedQuery"]
