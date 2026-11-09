import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class Project(Base):
    __tablename__ = "project"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200))
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organization.id", ondelete="CASCADE"), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    # SRID métrico usado para calcular largos en planta (UTM 19S por defecto).
    length_srid: Mapped[int] = mapped_column(Integer, default=32719)
    design_profile_id: Mapped[int | None] = mapped_column(
        ForeignKey("design_profile.id", ondelete="SET NULL"), nullable=True
    )
    # Parámetros de diseño editables del proyecto (criterios, dotación, pérdidas, curvas). None = valores
    # por defecto del perfil, marcados «no verificado».
    design_params: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    # Proyección de demanda (entradas editables); None = valores por defecto «no verificado».
    demand_projection: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # Registro de funcionamiento: tolerancias de comparación modelo/medición.
    monitoring: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    versions: Mapped[list["ProjectVersion"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", passive_deletes=True,
        order_by="ProjectVersion.number",
    )


class ProjectVersion(Base):
    """Versión inmutable del modelo. Se crea una en cada guardado (automático, manual o importación)."""

    __tablename__ = "project_version"
    __table_args__ = (UniqueConstraint("project_id", "number", name="uq_version_number"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("project.id", ondelete="CASCADE"), index=True)
    number: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(16))  # auto | manual | import
    label: Mapped[str | None] = mapped_column(String(200), nullable=True)
    parent_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # Opciones hidráulicas (fórmula de pérdida, DDA/PDA, tolerancias...).
    options: Mapped[dict] = mapped_column(JSONB, default=dict)
    # Secciones complementarias del modelo: patrones, curvas, controles, reglas, tiempos, energía, calidad.
    aux: Mapped[dict] = mapped_column(JSONB, default=dict)
    # Escenarios de llaves: [{id, name, closed: [IDs de llaves cerradas]}].
    scenarios: Mapped[list] = mapped_column(JSONB, default=list)
    content_sha256: Mapped[str] = mapped_column(String(64))

    project: Mapped[Project] = relationship(back_populates="versions")
