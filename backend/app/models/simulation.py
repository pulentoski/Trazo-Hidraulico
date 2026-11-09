import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, Integer, SmallInteger, String, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class SimulationRun(Base):
    """Corrida del motor, ligada a una versión inmutable del modelo (reproducible)."""

    __tablename__ = "simulation_run"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("project_version.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    status: Mapped[str] = mapped_column(String(12))  # ok | warning | error
    engine: Mapped[dict] = mapped_column(JSONB)  # versión del wheel, SHA del tag, EN_getversion
    engine_version: Mapped[str] = mapped_column(String(20))
    options: Mapped[dict] = mapped_column(JSONB)
    inp_sha256: Mapped[str] = mapped_column(String(64))
    messages: Mapped[list] = mapped_column(JSONB, default=list)  # advertencias y errores traducidos
    report_start: Mapped[int] = mapped_column(Integer, default=0)
    report_step: Mapped[int] = mapped_column(Integer, default=3600)
    duration: Mapped[int] = mapped_column(Integer, default=0)
    n_periods: Mapped[int] = mapped_column(Integer, default=0)
    elapsed_ms: Mapped[float] = mapped_column(Float, default=0.0)


class ResultNode(Base):
    __tablename__ = "result_node"

    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("simulation_run.id", ondelete="CASCADE"), primary_key=True)
    node_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("network_node.id", ondelete="CASCADE"), primary_key=True)
    period: Mapped[int] = mapped_column(Integer, primary_key=True)
    t_seconds: Mapped[int] = mapped_column(Integer)
    demand: Mapped[float] = mapped_column(Float)  # L/s
    head: Mapped[float] = mapped_column(Float)  # m
    pressure: Mapped[float] = mapped_column(Float)  # m


class ResultLink(Base):
    __tablename__ = "result_link"

    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("simulation_run.id", ondelete="CASCADE"), primary_key=True)
    link_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("network_link.id", ondelete="CASCADE"), primary_key=True)
    period: Mapped[int] = mapped_column(Integer, primary_key=True)
    t_seconds: Mapped[int] = mapped_column(Integer)
    flow: Mapped[float] = mapped_column(Float)  # L/s
    velocity: Mapped[float] = mapped_column(Float)  # m/s
    headloss: Mapped[float] = mapped_column(Float)  # m/km (tuberías) o -altura (bombas)
    status: Mapped[int] = mapped_column(SmallInteger)
    setting: Mapped[float] = mapped_column(Float)
