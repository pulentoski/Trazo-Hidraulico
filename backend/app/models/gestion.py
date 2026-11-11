"""Registros de operación de un APR (página «Gestión»): energía, cloro, cortes, reclamos, mantenciones, lecturas de
clientes y el historial de factibilidades. Viven por proyecto, fuera de las versiones del modelo."""
import uuid
from datetime import date, datetime

from sqlalchemy import BigInteger, Boolean, Date, DateTime, Float, ForeignKey, Identity, Integer, String, UniqueConstraint, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class _Record:
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    project_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("project.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by: Mapped[str | None] = mapped_column(String(254), nullable=True)


class EnergyRecord(_Record, Base):
    """Consumo eléctrico de un equipo (bomba) en un día o en el período que termina esa fecha."""
    __tablename__ = "energy_record"
    record_date: Mapped[date] = mapped_column(Date)
    equipment: Mapped[str] = mapped_column(String(31))
    kwh: Mapped[float] = mapped_column(Float)
    hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume_m3: Mapped[float | None] = mapped_column(Float, nullable=True)
    note: Mapped[str | None] = mapped_column(String(300), nullable=True)


class ChlorineRecord(_Record, Base):
    """Cloro residual libre medido en un punto de la red."""
    __tablename__ = "chlorine_record"
    measured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    point: Mapped[str] = mapped_column(String(60))
    mg_l: Mapped[float] = mapped_column(Float)
    note: Mapped[str | None] = mapped_column(String(300), nullable=True)


class ServiceOutage(_Record, Base):
    """Corte del servicio (programado o de emergencia) en un cuartel o un tramo."""
    __tablename__ = "service_outage"
    kind: Mapped[str] = mapped_column(String(12))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sector: Mapped[str | None] = mapped_column(String(31), nullable=True)
    link_id: Mapped[str | None] = mapped_column(String(31), nullable=True)
    clients_affected: Mapped[int] = mapped_column(Integer, default=0)
    note: Mapped[str | None] = mapped_column(String(300), nullable=True)


class Complaint(_Record, Base):
    """Reclamo de un cliente."""
    __tablename__ = "complaint"
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    client: Mapped[str | None] = mapped_column(String(40), nullable=True)
    kind: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(12))
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    note: Mapped[str | None] = mapped_column(String(300), nullable=True)


class MaintenanceTask(_Record, Base):
    """Mantención programada (periódica) o tarea única (p. ej. una reparación)."""
    __tablename__ = "maintenance_task"
    kind: Mapped[str] = mapped_column(String(24))
    element: Mapped[str | None] = mapped_column(String(31), nullable=True)
    description: Mapped[str | None] = mapped_column(String(200), nullable=True)
    frequency_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    next_date: Mapped[date] = mapped_column(Date)
    assignee: Mapped[str | None] = mapped_column(String(120), nullable=True)
    done_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_done: Mapped[date | None] = mapped_column(Date, nullable=True)


class MaintenanceLog(Base):
    """Registro de cumplimiento de una mantención."""
    __tablename__ = "maintenance_log"
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    task_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("maintenance_task.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("project.id", ondelete="CASCADE"), index=True)
    done_on: Mapped[date] = mapped_column(Date)
    scheduled_for: Mapped[date | None] = mapped_column(Date, nullable=True)
    by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    note: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ClientReading(_Record, Base):
    """Lectura mensual facturada de un cliente (m³ del período)."""
    __tablename__ = "client_reading"
    __table_args__ = (UniqueConstraint("project_id", "client", "period", name="uq_client_reading"),)
    client: Mapped[str] = mapped_column(String(31))
    period: Mapped[str] = mapped_column(String(7))
    m3: Mapped[float] = mapped_column(Float)


class FeasibilityRecord(_Record, Base):
    """Factibilidad evaluada (historial): ubicación, consumo, resultado y versión del modelo."""
    __tablename__ = "feasibility_record"
    model_version: Mapped[int] = mapped_column(Integer)
    link_id: Mapped[str] = mapped_column(String(31))
    location: Mapped[list] = mapped_column(JSONB)
    consumption_lps: Mapped[float] = mapped_column(Float)
    elevation: Mapped[float | None] = mapped_column(Float, nullable=True)
    feasible: Mapped[bool] = mapped_column(Boolean)
    pressure_new: Mapped[float | None] = mapped_column(Float, nullable=True)
    bottleneck: Mapped[str | None] = mapped_column(String(31), nullable=True)
    name: Mapped[str | None] = mapped_column(String(200), nullable=True)


__all__ = ["ChlorineRecord", "ClientReading", "Complaint", "EnergyRecord", "FeasibilityRecord", "MaintenanceLog",
           "MaintenanceTask", "ServiceOutage"]
