"""Página «Gestión»: configuración de indicadores, estructura de cada pestaña y registros de operación."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Tab = Literal["operacion", "clientes", "perdidas", "activos", "cumplimiento", "planificacion", "equipo"]
RecordKind = Literal["energia", "cloro", "cortes", "reclamos", "mantenciones", "lecturas"]
Status = Literal["bueno", "regular", "malo"]
MapType = Literal["node", "link", "client", "shutoff", "hydrant", "well"]


class Target(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str
    unit: str
    good: float = Field(description="Umbral «bueno»")
    bad: float = Field(description="Umbral «malo»")
    higher_is_better: bool = False
    verified: bool = Field(False, description="Meta revisada por el usuario (si no, valor sugerido «no verificado»)")


# Metas sugeridas (valores de partida típicos para un APR rural; no verificados).
DEFAULT_TARGETS: dict[str, Target] = {
    "pressure_min": Target(label="Presión mínima medida", unit="m.c.a.", good=15, bad=10, higher_is_better=True),
    "tank_level_min": Target(label="Nivel mínimo del estanque", unit="m", good=1.0, bad=0.5, higher_is_better=True),
    "pump_hours": Target(label="Horas de bomba por día", unit="h/día", good=16, bad=20),
    "well_use": Target(label="Caudal del pozo / autorizado", unit="%", good=80, bad=100),
    "kwh_m3": Target(label="Energía por m³ producido", unit="kWh/m³", good=0.6, bad=1.0),
    "per_connection": Target(label="Consumo promedio por arranque", unit="m³/mes", good=20, bad=30),
    "dotacion": Target(label="Dotación real", unit="L/hab/día", good=150, bad=200),
    "nrw": Target(label="Agua no contabilizada", unit="%", good=20, bad=35),
    "leaks": Target(label="Eventos de fuga", unit="eventos/mes", good=1, bad=3),
    "pipes_bad": Target(label="Red en mal estado", unit="%", good=5, bad=15),
    "renewal_due": Target(label="Renovación vencida", unit="km", good=0, bad=0.5),
    "maintenance_ok": Target(label="Mantenciones al día", unit="%", good=90, bad=70, higher_is_better=True),
    "extraction": Target(label="Extracción / derecho de agua", unit="%", good=85, bad=100),
    "client_hours": Target(label="Horas sin servicio por cliente", unit="h/cliente/mes", good=1, bad=4),
    "chlorine_ok": Target(label="Cloro dentro de rango", unit="%", good=95, bad=80, higher_is_better=True),
    "response_h": Target(label="Tiempo de respuesta a reclamos", unit="h", good=24, bad=72),
    "capacity": Target(label="Capacidad remanente", unit="clientes", good=50, bad=10, higher_is_better=True),
    "demand_vs_well": Target(label="Demanda a 20 años / capacidad del pozo", unit="%", good=80, bad=100),
    "tasks_overdue": Target(label="Tareas atrasadas", unit="tareas", good=0, bad=3),
}


class GestionSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    targets: dict[str, Target] = Field(default_factory=lambda: {k: v.model_copy() for k, v in DEFAULT_TARGETS.items()})
    water_right_lps: float | None = Field(None, ge=0, description="Derecho de agua (L/s). Vacío = caudal autorizado del pozo")
    water_right_m3_year: float | None = Field(None, ge=0, description="Volumen anual del derecho (m³). Vacío = derecho × año")
    chlorine_min: float = Field(0.2, ge=0, description="Cloro residual libre mínimo (mg/L)")
    chlorine_max: float = Field(2.0, ge=0, description="Cloro residual libre máximo (mg/L)")
    chlorine_verified: bool = False
    typical_client_m3_month: float | None = Field(None, gt=0, description="Consumo típico de un cliente nuevo (m³/mes). "
                                                  "Vacío = promedio de los clientes residenciales activos")
    capacity_max_clients: int = Field(400, ge=1, le=5000, description="Tope de clientes a probar en la capacidad remanente")
    tank_reserve_pct: float = Field(25.0, ge=0, le=100, description="Volumen de regulación exigido (% del consumo diario)")


class EmptyState(BaseModel):
    missing: str = Field(description="Qué dato falta")
    how: str = Field(description="Cómo cargarlo (manual o planilla)")
    record: RecordKind | None = None


class Series(BaseModel):
    name: str
    values: list[float | None]
    kind: Literal["line", "bar"] = "line"


class Chart(BaseModel):
    title: str
    x: list[str]
    series: list[Series]
    unit: str = ""
    reference: float | None = Field(None, description="Línea de referencia (p. ej. caudal autorizado)")
    reference_label: str | None = None
    goal: float | None = Field(None, description="Línea de meta (umbral «bueno» del indicador)")
    goal_label: str | None = None
    stacked: bool = False


class Column(BaseModel):
    key: str
    label: str
    unit: str | None = None
    num: bool = False


class Table(BaseModel):
    key: str
    title: str
    columns: list[Column]
    rows: list[dict[str, Any]]


class MapRef(BaseModel):
    type: MapType
    ids: list[str]
    weights: dict[str, float] | None = Field(None, description="Intensidad por elemento (mapa de calor)")


class Indicator(BaseModel):
    key: str
    label: str
    unit: str
    value: float | None
    previous: float | None = None
    delta_pct: float | None = None
    status: Status | None = None
    target_verified: bool = False
    higher_is_better: bool | None = Field(None, description="Sentido deseado (None = sin meta)")
    note: str | None = None
    chart: Chart | None = None
    table: str | None = Field(None, description="Clave de la tabla de detalle")
    map: MapRef | None = None
    empty: EmptyState | None = None


class Period(BaseModel):
    start: date
    end: date
    prev_start: date
    prev_end: date
    months: list[str]


class TabResult(BaseModel):
    tab: Tab
    title: str
    period: Period
    sector: str | None
    route: str | None
    indicators: list[Indicator]
    charts: list[Chart] = Field(default_factory=list)
    tables: list[Table]
    notes: list[str] = Field(default_factory=list)
    extra: dict[str, Any] = Field(default_factory=dict)


class Filters(BaseModel):
    sectors: list[str]
    routes: list[str]
    data_start: date | None
    data_end: date | None
    model_version: int | None


class CapacityStep(BaseModel):
    clients: int
    node: str
    min_pressure: float
    min_node: str


class CapacityResult(BaseModel):
    model_version: int
    typical_lps: float
    typical_m3_month: float
    pmin: float
    capacity: int = Field(description="Clientes nuevos que caben manteniendo la presión mínima")
    limited_by_cap: bool = Field(description="Se alcanzó el tope de clientes a probar sin violar la presión mínima")
    bottleneck_node: str | None = Field(None, description="Primer nudo que baja de la presión mínima")
    bottleneck_link: str | None = Field(None, description="Tramo con mayor pérdida unitaria en ese momento")
    bottleneck_pressure: float | None = None
    simulations: int
    by_node: dict[str, int]
    steps: list[CapacityStep]
    note: str


# ── Registros ──

class FieldSpec(BaseModel):
    key: str
    label: str
    type: Literal["date", "datetime", "month", "float", "int", "str", "choice", "element"]
    required: bool
    choices: list[str] = Field(default_factory=list)
    help: str = ""
    element_types: list[str] = Field(default_factory=list)


class RecordSpec(BaseModel):
    kind: RecordKind
    title: str
    help: str
    fields: list[FieldSpec]
    computed: list[Column] = Field(default_factory=list)


class RowError(BaseModel):
    row: int
    field: str | None
    message: str


class PreviewRow(BaseModel):
    row: int
    values: dict[str, Any]
    errors: list[str]


class RecordImportPreview(BaseModel):
    kind: RecordKind
    rows: list[PreviewRow]
    valid: int
    invalid: int
    created: int = 0
    updated: int = 0
    applied: bool = False


class RecordList(BaseModel):
    kind: RecordKind
    rows: list[dict[str, Any]]


class CompleteTask(BaseModel):
    model_config = ConfigDict(extra="forbid")
    done_on: date
    by: str | None = Field(None, max_length=120)
    note: str | None = Field(None, max_length=300)


class MaintenanceLogOut(BaseModel):
    id: int
    task_id: int
    done_on: date
    scheduled_for: date | None
    by: str | None
    note: str | None
    created_at: datetime


class ReportMeta(BaseModel):
    project: str
    generated_at: datetime
    period: Period
    model_version: int | None
